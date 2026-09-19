from app.agent.context_manager import ContextManager


def _cm(fake_provider, budget, summary="SUMMARY"):
    fake_provider([{"content": summary}] * 10)
    return ContextManager(max_tokens=budget)


def test_short_history_is_kept_whole(fake_provider):
    cm = _cm(fake_provider, budget=8000)
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]

    result = cm.build_context("system", history, tracer=None)

    assert result["metadata"]["discarded_turns_count"] == 0
    assert result["metadata"]["reduction_percentage"] == 0.0
    assert len(result["messages"]) == 3  # system + 2 turns


def test_oversized_history_is_compacted(fake_provider):
    cm = _cm(fake_provider, budget=300)
    history = [{"role": "user", "content": "padding " * 100} for _ in range(10)]

    result = cm.build_context("system", history, tracer=None)

    meta = result["metadata"]
    assert meta["discarded_turns_count"] > 0
    # The old code hardcoded this to 0 regardless of what it dropped.
    assert meta["reduction_percentage"] > 0
    assert meta["final_tokens"] < meta["original_tokens"]
    assert meta["budget_tokens"] == 300


def test_compaction_inserts_a_summary_and_rewrites_history(fake_provider):
    cm = _cm(fake_provider, budget=300, summary="THE SUMMARY")
    history = [{"role": "user", "content": "padding " * 100} for _ in range(10)]

    cm.build_context("system", history, tracer=None)

    # The caller's history is replaced with the compacted version.
    assert history[0]["role"] == "system"
    assert "THE SUMMARY" in history[0]["content"]


def test_orphaned_tool_results_are_dropped(fake_provider):
    """A tool result whose assistant tool_calls message was cut would 400 the API."""
    cm = _cm(fake_provider, budget=200)
    history = [
        {"role": "user", "content": "padding " * 200},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "calculator", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "c1", "name": "calculator", "content": "4"},
    ]

    result = cm.build_context("system", history, tracer=None)

    kept = [m for m in result["messages"] if m["role"] not in ("system",)]
    assert not kept or kept[0]["role"] != "tool"


def test_memories_are_injected_when_they_fit(fake_provider):
    cm = _cm(fake_provider, budget=8000)

    result = cm.build_context("system", [], memories=["The code is OMEGA-99."])

    assert result["metadata"]["retained_memories"] == ["The code is OMEGA-99."]
    assert any("OMEGA-99" in m["content"] for m in result["messages"])


def test_oversized_memories_are_skipped(fake_provider):
    cm = _cm(fake_provider, budget=100)

    result = cm.build_context("system", [], memories=["fact " * 500])

    assert result["metadata"]["retained_memories"] == []


def test_summarization_is_traced_and_billed(fake_provider, tracer):
    fake_provider([{"content": "SUMMARY", "cost": 0.5, "prompt_tokens": 100, "completion_tokens": 10}])
    cm = ContextManager(max_tokens=200)
    history = [{"role": "user", "content": "padding " * 100} for _ in range(5)]

    cm.build_context("system", history, tracer=tracer)

    step_types = [s.step_type for s in tracer.current_run.traces]
    assert "CONTEXT_COMPACTION" in step_types
    # The summariser is a real LLM call, so it must show up in the trace.
    assert "SUMMARIZATION" in step_types
    assert tracer.current_run.total_cost == 0.5
    assert tracer.current_run.llm_call_count == 1


def test_failed_summarization_degrades_gracefully(fake_provider):
    cm = _cm(fake_provider, budget=200)
    cm.provider.responses = [{"error": "boom"}]
    history = [{"role": "user", "content": "padding " * 100} for _ in range(5)]

    result = cm.build_context("system", history, tracer=None)

    assert any("summarization failed" in m.get("content", "") for m in result["messages"])


def test_token_counting_handles_non_string_content(fake_provider):
    cm = _cm(fake_provider, budget=8000)

    assert cm.count_tokens(None) == 0
    assert cm.count_tokens(1234) > 0
    assert cm.count_message_tokens({"role": "user", "content": None}) > 0


def test_memories_sit_next_to_the_current_turn(fake_provider):
    """Placed at the top of the prompt, memories were reliably ignored."""
    cm = _cm(fake_provider, budget=8000)
    history = [
        {"role": "user", "content": "turn one"},
        {"role": "assistant", "content": "reply one"},
        {"role": "user", "content": "what is the code?"},
    ]

    result = cm.build_context("system", history, memories=["The code is OMEGA-99."])
    messages = result["messages"]

    # The user's question stays last, with the memories immediately before it.
    assert messages[-1] == {"role": "user", "content": "what is the code?"}
    assert "OMEGA-99" in messages[-2]["content"]
    assert messages[-2]["role"] == "system"


def test_memories_go_last_when_history_does_not_end_with_a_user_turn(fake_provider):
    cm = _cm(fake_provider, budget=8000)
    history = [{"role": "assistant", "content": "reply"}]

    messages = cm.build_context("system", history, memories=["fact"])["messages"]

    assert "fact" in messages[-1]["content"]
