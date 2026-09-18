import os
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import openai

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        pass

class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        
        # basic pricing config
        self.pricing = {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
            "gemini-1.5-pro": {"input": 1.25, "output": 5.00}
        }

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        # Default to 0.0 if model not in dict
        prices = self.pricing.get(model, {"input": 0.0, "output": 0.0})
        cost = (prompt_tokens / 1_000_000) * prices["input"] + (completion_tokens / 1_000_000) * prices["output"]
        return cost

    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        start_time = time.time()
        
        kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            
        try:
            response = self.client.chat.completions.create(**kwargs)
            end_time = time.time()
            
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            
            result = {
                "content": response.choices[0].message.content,
                "tool_calls": [],
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": (end_time - start_time) * 1000,
                "model": response.model,
                "cost": self._calculate_cost(self.model, prompt_tokens, completion_tokens),
                "error": None
            }
            
            if response.choices[0].message.tool_calls:
                for tc in response.choices[0].message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            return result
        except Exception as e:
            end_time = time.time()
            return {
                "error": str(e),
                "duration_ms": (end_time - start_time) * 1000,
                "model": self.model,
                "cost": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0
            }

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

class GeminiProvider(LLMProvider):
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
        os.environ["GOOGLE_API_KEY"] = self.api_key
        genai.configure(api_key=self.api_key)
        
        self.pricing = {
            "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
            "gemini-1.5-pro": {"input": 1.25, "output": 5.00}
        }
        
    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        prices = self.pricing.get(model, {"input": 0.0, "output": 0.0})
        cost = (prompt_tokens / 1_000_000) * prices["input"] + (completion_tokens / 1_000_000) * prices["output"]
        return cost
        
    def generate(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        max_retries = 3
        for attempt in range(max_retries):
            start_time = time.time()
            try:
                # We map openai messages to gemini format
                system_prompt = ""
                gemini_messages = []
                
                for m in messages:
                    if m["role"] == "system":
                        system_prompt += m["content"] + "\n"
                    elif m["role"] == "user":
                        gemini_messages.append({"role": "user", "parts": [m["content"]]})
                    elif m["role"] == "assistant":
                        if m.get("content"):
                            gemini_messages.append({"role": "model", "parts": [m["content"]]})
                    elif m["role"] == "tool":
                        pass
                
                gemini_tools = []
                if tools:
                    for t in tools:
                        f = t["function"]
                        schema = f.get("parameters", {"type": "OBJECT", "properties": {}})
                        gemini_tools.append(Tool(function_declarations=[
                            FunctionDeclaration(
                                name=f["name"],
                                description=f["description"],
                                parameters=schema
                            )
                        ]))
                
                client = genai.GenerativeModel(
                    model_name=self.model,
                    system_instruction=system_prompt if system_prompt else None,
                    tools=gemini_tools if gemini_tools else None
                )
                
                response = client.generate_content(gemini_messages)
                end_time = time.time()
                
                prompt_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
                completion_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
                
                content_text = ""
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        try:
                            if part.text:
                                content_text += part.text
                        except Exception:
                            pass
                            
                result = {
                    "content": content_text,
                    "tool_calls": [],
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "duration_ms": (end_time - start_time) * 1000,
                    "model": self.model,
                    "cost": self._calculate_cost(self.model, prompt_tokens, completion_tokens),
                    "error": None
                }
                
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            import json
                            args = {k: v for k, v in part.function_call.args.items()}
                            result["tool_calls"].append({
                                "id": "call_" + str(int(time.time())),
                                "type": "function",
                                "function": {
                                    "name": part.function_call.name,
                                    "arguments": json.dumps(args)
                                }
                            })
                
                return result
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    print(f"Rate limited (429). Retrying in 30 seconds... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(30)
                    continue
                
                end_time = time.time()
                return {
                    "error": error_str,
                    "duration_ms": (end_time - start_time) * 1000,
                    "model": self.model,
                    "cost": 0.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0
                }

def get_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "gemini":
        return GeminiProvider()
    return OpenAIProvider()
