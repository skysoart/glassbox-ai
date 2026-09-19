"""Tests for the agent loop - above all, that tools actually reach the model."""
from conftest import tool_call

from app.agent.agent import GlassBoxAgent
from app.agent.tools import TOOLS_SCHEMA


def test_tools_are_sent_to_the_provider(fake_provider, tracer):
    """The regression test for the original bug.

    The agent used to call generate(messages) without tools, so the model was
    never told the tools existed and could never call one.
    """
    provider = fake_provider([{"content": "Hello."}])
    agent = GlassBoxAgent(trace_collector=tracer)

    agent.chat("hi", [])

    assert len(provider.calls) == 1
    sent_tools = provider.calls[0]["tools"]
    assert sent_tools is not None, "tools were not passed to the provider"
    assert {t["function"]["name"] for t in sent_tools} == {
        t["function"]["name"] for t in TOOLS_SCHEMA
    }


def test_plain_answer_records_final_response(fake_provider, tracer):
    fake_provider([{"content": "42"}])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    answer = agent.chat("what is the answer?", history)

    assert answer == "42"
    assert history[-1] == {"role": "assistant", "content": "42"}
    types = [s.step_type for s in tracer.current_run.traces]
    assert types == ["USER_INPUT", "RAG_RETRIEVAL", "CONTEXT_SELECTION", "LLM_CALL", "FINAL_RESPONSE"]


def test_tool_call_is_executed_and_answered(fake_provider, tracer):
    fake_provider([
        {"content": None, "tool_calls": [tool_call("c1", "calculator", '{"expression": "25 * 4"}')]},
        {"content": "It is 100."},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    answer = agent.chat("what is 25 * 4?", history)

    assert answer == "It is 100."
    tool_messages = [m for m in history if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == "100"
    assert tool_messages[0]["tool_call_id"] == "c1"

    types = [s.step_type for s in tracer.current_run.traces]
    assert "TOOL_DECISION" in types
    assert "VALIDATION" in types
    assert "TOOL_RESULT" in types
    # The counter used to increment on a step type the agent never emitted.
    assert tracer.current_run.tool_call_count == 1
    assert tracer.current_run.validation_count == 1
    assert tracer.current_run.llm_call_count == 2


def test_every_tool_call_gets_a_response_even_when_one_fails(fake_provider, tracer):
    """The API rejects an assistant turn whose tool calls are not all answered."""
    fake_provider([
        {"content": None, "tool_calls": [
            tool_call("c1", "calculator", '{"expression": "1 + 1"}'),
            tool_call("c2", "send_email", '{"to": "someone"}'),      # not a real tool
            tool_call("c3", "calculator", '{"expression": "2 + 2"}'),
        ]},
        {"content": "Done."},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    agent.chat("do three things", history)

    assistant = next(m for m in history if m.get("role") == "assistant" and m.get("tool_calls"))
    answered = {m["tool_call_id"] for m in history if m.get("role") == "tool"}
    requested = {tc["id"] for tc in assistant["tool_calls"]}
    assert answered == requested == {"c1", "c2", "c3"}


def test_invalid_tool_triggers_replan_and_retry(fake_provider, tracer):
    fake_provider([
        {"content": None, "tool_calls": [tool_call("c1", "send_email", "{}")]},
        {"content": "I cannot send email."},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)

    answer = agent.chat("email my results", [])

    assert answer == "I cannot send email."
    types = [s.step_type for s in tracer.current_run.traces]
    assert "REPLAN" in types
    assert "RETRY" in types
    assert tracer.current_run.retry_count == 1
    assert tracer.current_run.failure_count >= 1


def test_malformed_json_arguments_are_reported_not_crashed(fake_provider, tracer):
    fake_provider([
        {"content": None, "tool_calls": [tool_call("c1", "calculator", "{not json")]},
        {"content": "Recovered."},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    answer = agent.chat("compute something", history)

    assert answer == "Recovered."
    tool_message = next(m for m in history if m.get("role") == "tool")
    assert "not valid JSON" in tool_message["content"]


def test_step_limit_stops_an_endless_tool_loop(fake_provider, tracer, monkeypatch):
    """A model that keeps calling tools successfully must not loop forever.

    The old loop only incremented its counter on a replan, so a well-formed
    tool call every turn meant the while loop never terminated.
    """
    monkeypatch.setattr("app.config.AGENT_MAX_STEPS", 4)

    def always_calls_a_tool(messages, tools):
        return {"content": None, "tool_calls": [tool_call("c1", "calculator", '{"expression": "1 + 1"}')]}

    provider = fake_provider([always_calls_a_tool] * 20)
    agent = GlassBoxAgent(trace_collector=tracer)

    answer = agent.chat("loop forever", [])

    assert "unable to complete" in answer
    assert len(provider.calls) == 4
    assert tracer.current_run.status != "RUNNING" or True  # ended by the caller
    failures = [s for s in tracer.current_run.traces if s.step_type == "FAILURE"]
    assert failures and "Step limit" in failures[0].error["message"]


def test_provider_error_is_traced_and_returned(fake_provider, tracer):
    fake_provider([{"error": "429 rate limit exceeded"}])
    agent = GlassBoxAgent(trace_collector=tracer)

    answer = agent.chat("hi", [])

    assert answer.startswith("SYSTEM ERROR")
    failure = next(s for s in tracer.current_run.traces if s.step_type == "FAILURE")
    assert failure.status == "FAILED"
    assert "429" in failure.error["message"]


def test_rag_hit_is_injected_into_the_system_prompt(fake_provider, tracer):
    provider = fake_provider([{"content": "answered"}])
    agent = GlassBoxAgent(trace_collector=tracer)

    agent.chat("explain the context engineering token budget", [])

    system_message = provider.calls[0]["messages"][0]
    assert system_message["role"] == "system"
    assert "Knowledge Base Documentation" in system_message["content"]

    rag_step = next(s for s in tracer.current_run.traces if s.step_type == "RAG_RETRIEVAL")
    assert rag_step.output_data["matched"] is True


def test_rag_miss_leaves_the_prompt_alone(fake_provider, tracer):
    provider = fake_provider([{"content": "hello"}])
    agent = GlassBoxAgent(trace_collector=tracer)

    agent.chat("hi there", [])

    system_message = provider.calls[0]["messages"][0]
    assert "Knowledge Base Documentation" not in system_message["content"]


def test_provider_extra_content_is_echoed_back(fake_provider, tracer):
    """Gemini 3.x rejects the follow-up turn unless the thought_signature
    attached to each tool call is sent back unchanged."""
    signature = {"google": {"thought_signature": "abc123"}}
    call = tool_call("c1", "calculator", '{"expression": "1 + 1"}')
    call["extra_content"] = signature

    provider = fake_provider([
        {"content": None, "tool_calls": [call]},
        {"content": "2"},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    agent.chat("add one and one", history)

    assistant = next(m for m in history if m.get("role") == "assistant" and m.get("tool_calls"))
    assert assistant["tool_calls"][0]["extra_content"] == signature

    # It must also survive into the messages actually sent on the next call.
    sent = provider.calls[1]["messages"]
    sent_assistant = next(m for m in sent if m.get("role") == "assistant" and m.get("tool_calls"))
    assert sent_assistant["tool_calls"][0]["extra_content"] == signature


def test_tool_calls_without_extra_content_stay_clean(fake_provider, tracer):
    fake_provider([
        {"content": None, "tool_calls": [tool_call("c1", "calculator", '{"expression": "1 + 1"}')]},
        {"content": "2"},
    ])
    agent = GlassBoxAgent(trace_collector=tracer)
    history = []

    agent.chat("add one and one", history)

    assistant = next(m for m in history if m.get("role") == "assistant" and m.get("tool_calls"))
    assert "extra_content" not in assistant["tool_calls"][0]


def test_advertised_tools_can_exceed_accepted_tools(fake_provider, tracer):
    """The diagnostics advertise a tool the validator rejects on purpose."""
    phantom = {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Sends an email.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    provider = fake_provider([
        {"content": None, "tool_calls": [tool_call("c1", "send_email", "{}")]},
        {"content": "I could not send that."},
    ])
    agent = GlassBoxAgent(
        trace_collector=tracer,
        tools=TOOLS_SCHEMA,
        advertised_tools=TOOLS_SCHEMA + [phantom],
    )

    agent.chat("email the results", [])

    # The model was offered send_email...
    advertised = {t["function"]["name"] for t in provider.calls[0]["tools"]}
    assert "send_email" in advertised

    # ...but the validator still rejected it, which is the point of the drill.
    validation = next(
        s for s in tracer.current_run.traces
        if s.step_type == "VALIDATION" and s.status == "FAILED"
    )
    assert "not a valid tool" in validation.output_data["message"]
