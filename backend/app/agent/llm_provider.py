import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app import config
from app.agent import pricing

# Errors worth retrying: rate limits and transient upstream failures.
_RETRYABLE_MARKERS = ("429", "rate limit", "resource_exhausted", "500", "502", "503", "504", "overloaded")


def _is_retryable(error: str) -> bool:
    lowered = error.lower()
    return any(marker in lowered for marker in _RETRYABLE_MARKERS)


def _extra_content(tool_call) -> Optional[Dict[str, Any]]:
    """Read a provider-specific extra_content field off a tool call, if present.

    The OpenAI SDK keeps unrecognised response fields in the model's extras, so
    this reaches for them without assuming the field exists.
    """
    extra = getattr(tool_call, "extra_content", None)
    if extra:
        return extra
    if hasattr(tool_call, "model_dump"):
        try:
            return tool_call.model_dump().get("extra_content")
        except Exception:  # noqa: BLE001 - never fail a response over an optional field
            return None
    return None


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return a normalised result dict.

        Keys always present: content, tool_calls, prompt_tokens,
        completion_tokens, duration_ms, model, cost, cost_known, error.
        """

    def _error_result(self, error: str, start_time: float) -> Dict[str, Any]:
        return {
            "content": "",
            "tool_calls": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "duration_ms": (time.time() - start_time) * 1000,
            "model": getattr(self, "model", "unknown"),
            "cost": 0.0,
            "cost_known": False,
            "error": error,
        }


class OpenAIProvider(LLMProvider):
    """Works against OpenAI and any OpenAI-compatible endpoint.

    This is the path the project is configured for by default, including
    Gemini via its OpenAI-compatible base URL.
    """

    def __init__(self):
        import openai  # imported here so the module can load without the SDK present

        self.api_key = config.LLM_API_KEY
        self.base_url = config.LLM_BASE_URL
        self.model = config.LLM_MODEL
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        max_attempts = 3
        for attempt in range(max_attempts):
            start_time = time.time()

            kwargs: Dict[str, Any] = {"model": self.model, "messages": messages}
            if tools:
                kwargs["tools"] = tools

            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as exc:  # noqa: BLE001 - the error is surfaced in the trace
                error = str(exc)
                if _is_retryable(error) and attempt < max_attempts - 1:
                    backoff = 2 ** attempt * 5
                    print("[llm] retryable error (" + error[:120] + "); retrying in "
                          + str(backoff) + "s (attempt " + str(attempt + 1) + "/" + str(max_attempts) + ")")
                    time.sleep(backoff)
                    continue
                return self._error_result(error, start_time)

            duration_ms = (time.time() - start_time) * 1000
            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0

            # Bill against the model the API actually served, falling back to
            # the configured id when the response omits it.
            billed_model = response.model or self.model
            cost, cost_known = pricing.calculate(billed_model, prompt_tokens, completion_tokens)

            message = response.choices[0].message
            result = {
                "content": message.content or "",
                "tool_calls": [],
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": duration_ms,
                "model": billed_model,
                "cost": cost,
                "cost_known": cost_known,
                "error": None,
            }

            for tc in (message.tool_calls or []):
                call = {
                    "id": tc.id,
                    "type": getattr(tc, "type", "function"),
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                # Gemini 3.x returns a thought_signature on each tool call and
                # rejects the follow-up request unless it is sent back
                # unchanged. It arrives as a provider-specific extra field, so
                # carry through whatever is there rather than naming it.
                extra = _extra_content(tc)
                if extra:
                    call["extra_content"] = extra
                result["tool_calls"].append(call)
            return result

        return self._error_result("Exhausted retries without a response.", time.time())


class GeminiProvider(LLMProvider):
    """Native google-generativeai path.

    Note: the google-generativeai SDK is end-of-life. The supported route for
    Gemini in this project is OpenAIProvider pointed at Gemini's
    OpenAI-compatible base URL (see .env.example).
    """

    def __init__(self):
        # Lazy import: the package is optional, and importing it at module
        # scope used to break startup for everyone on the OpenAI path.
        import google.generativeai as genai

        self._genai = genai
        self.api_key = config.LLM_API_KEY
        self.model = config.LLM_MODEL
        genai.configure(api_key=self.api_key)

    def _to_gemini_messages(self, messages: List[Dict[str, Any]]):
        """Map OpenAI-shaped messages onto Gemini contents.

        Tool calls and tool results are carried across rather than dropped, so
        a multi-turn tool conversation keeps its history.
        """
        system_prompt = ""
        contents: List[Dict[str, Any]] = []

        for m in messages:
            role = m.get("role")
            if role == "system":
                system_prompt += (m.get("content") or "") + "\n"
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": m.get("content") or ""}]})
            elif role == "assistant":
                parts: List[Dict[str, Any]] = []
                if m.get("content"):
                    parts.append({"text": m["content"]})
                for tc in (m.get("tool_calls") or []):
                    try:
                        args = json.loads(tc["function"]["arguments"] or "{}")
                    except (ValueError, TypeError):
                        args = {}
                    parts.append({"function_call": {"name": tc["function"]["name"], "args": args}})
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{"function_response": {
                        "name": m.get("name") or "tool",
                        "response": {"result": m.get("content") or ""},
                    }}],
                })

        return system_prompt, contents

    def _to_gemini_tools(self, tools: Optional[List[Dict[str, Any]]]):
        if not tools:
            return None
        from google.generativeai.types import FunctionDeclaration, Tool

        declarations = []
        for t in tools:
            f = t["function"]
            declarations.append(FunctionDeclaration(
                name=f["name"],
                description=f.get("description", ""),
                parameters=f.get("parameters", {"type": "object", "properties": {}}),
            ))
        return [Tool(function_declarations=declarations)]

    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        max_attempts = 3
        for attempt in range(max_attempts):
            start_time = time.time()
            try:
                system_prompt, contents = self._to_gemini_messages(messages)
                gemini_tools = self._to_gemini_tools(tools)

                client = self._genai.GenerativeModel(
                    model_name=self.model,
                    system_instruction=system_prompt or None,
                    tools=gemini_tools,
                )
                response = client.generate_content(contents)
                duration_ms = (time.time() - start_time) * 1000

                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = usage.prompt_token_count if usage else 0
                completion_tokens = usage.candidates_token_count if usage else 0
                cost, cost_known = pricing.calculate(self.model, prompt_tokens, completion_tokens)

                content_text = ""
                tool_calls = []
                if response.candidates and response.candidates[0].content.parts:
                    for index, part in enumerate(response.candidates[0].content.parts):
                        text = getattr(part, "text", None)
                        if text:
                            content_text += text
                        fc = getattr(part, "function_call", None)
                        if fc and getattr(fc, "name", None):
                            tool_calls.append({
                                # Deterministic per-response id. The old code used a
                                # 1-second-resolution timestamp, so two tool calls in
                                # one response were given the same id.
                                "id": "call_" + str(int(start_time * 1000)) + "_" + str(index),
                                "type": "function",
                                "function": {
                                    "name": fc.name,
                                    "arguments": json.dumps({k: v for k, v in fc.args.items()}),
                                },
                            })

                return {
                    "content": content_text,
                    "tool_calls": tool_calls,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "duration_ms": duration_ms,
                    "model": self.model,
                    "cost": cost,
                    "cost_known": cost_known,
                    "error": None,
                }

            except Exception as exc:  # noqa: BLE001 - the error is surfaced in the trace
                error = str(exc)
                if _is_retryable(error) and attempt < max_attempts - 1:
                    backoff = 2 ** attempt * 5
                    print("[llm] retryable error (" + error[:120] + "); retrying in "
                          + str(backoff) + "s (attempt " + str(attempt + 1) + "/" + str(max_attempts) + ")")
                    time.sleep(backoff)
                    continue
                return self._error_result(error, start_time)

        return self._error_result("Exhausted retries without a response.", time.time())


_provider_cache: Dict[str, LLMProvider] = {}


def get_provider(force_new: bool = False) -> LLMProvider:
    """Return the configured provider.

    Cached: the agent and the context manager both need one, and building a
    fresh HTTP client per request is pure overhead.
    """
    key = config.LLM_PROVIDER + ":" + config.LLM_MODEL + ":" + config.LLM_BASE_URL
    if force_new or key not in _provider_cache:
        _provider_cache[key] = GeminiProvider() if config.LLM_PROVIDER == "gemini" else OpenAIProvider()
    return _provider_cache[key]
