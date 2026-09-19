import pytest

from app.agent.pricing import calculate, lookup, reset_cache
from app.agent.tools import TOOLS_SCHEMA, calculator, execute_tool, search_docs
from app.agent.validator import Validator


# --- validator --------------------------------------------------------------

def test_valid_call_passes():
    ok, message = Validator.validate_tool_call(
        "calculator", {"expression": "2 + 2"}, TOOLS_SCHEMA
    )
    assert ok is True
    assert message == "Valid"


def test_unknown_tool_is_rejected_and_lists_alternatives():
    ok, message = Validator.validate_tool_call("send_email", {}, TOOLS_SCHEMA)
    assert ok is False
    assert "not a valid tool" in message
    assert "calculator" in message


def test_missing_required_argument_is_rejected():
    ok, message = Validator.validate_tool_call("calculator", {}, TOOLS_SCHEMA)
    assert ok is False
    assert "missing required argument 'expression'" in message


def test_unexpected_argument_is_rejected():
    ok, message = Validator.validate_tool_call(
        "calculator", {"expression": "1+1", "precision": 2}, TOOLS_SCHEMA
    )
    assert ok is False
    assert "unexpected argument 'precision'" in message


def test_wrong_argument_type_is_rejected():
    ok, message = Validator.validate_tool_call("calculator", {"expression": 42}, TOOLS_SCHEMA)
    assert ok is False
    assert "should be of type string" in message


def test_non_dict_arguments_are_rejected():
    ok, _ = Validator.validate_tool_call("calculator", ["2+2"], TOOLS_SCHEMA)
    assert ok is False


def test_tool_result_error_prefix_is_detected():
    ok, message = Validator.validate_tool_result("calculator", "Error evaluating expression: bad")
    assert ok is False
    assert "Tool execution failure" in message


def test_result_merely_containing_the_word_failed_is_still_valid():
    """The old check searched the whole string for 'failed:', so a real search
    result about a failed deploy was misread as a tool failure."""
    ok, _ = Validator.validate_tool_result(
        "web_search", "The deployment failed: here is what the postmortem said."
    )
    assert ok is True


# --- calculator -------------------------------------------------------------

@pytest.mark.parametrize("expression,expected", [
    ("2 + 2", "4"),
    ("25 * 4", "100"),
    ("10 / 4", "2.5"),
    ("10 // 3", "3"),
    ("10 % 3", "1"),
    ("2 ** 8", "256"),
    ("-5 + 3", "-2"),
])
def test_calculator_arithmetic(expression, expected):
    assert calculator(expression) == expected


def test_calculator_rejects_division_by_zero():
    assert "division by zero" in calculator("1 / 0")


def test_calculator_rejects_huge_exponents():
    """2 ** 10**9 would hang the worker before it ran out of memory."""
    assert "out of supported range" in calculator("2 ** 999999999")


def test_calculator_rejects_arbitrary_code():
    assert calculator("__import__('os').system('echo hi')").startswith("Error")
    assert calculator("open('x')").startswith("Error")


# --- retrieval --------------------------------------------------------------

def test_search_docs_matches_known_documentation():
    text, matched, details = search_docs("context engineering token budget")
    assert matched is True
    assert "--- From " in text
    assert details["files_scanned"] > 0


def test_search_docs_reports_a_miss_explicitly():
    """The agent used to detect misses by sniffing for a marker in the text."""
    _, matched, details = search_docs("hello")
    assert matched is False
    assert details["reason"] == "NO_QUERY_TERMS"


def test_unknown_tool_execution_returns_an_error_string():
    assert execute_tool("send_email", {}).startswith("Error")


def test_tool_exceptions_do_not_escape(monkeypatch):
    def boom(_args):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(__import__("app.agent.tools", fromlist=["x"]).TOOL_REGISTRY, "calculator", boom)
    result = execute_tool("calculator", {"expression": "1+1"})
    assert result.startswith("Error") and "kaboom" in result


# --- pricing ----------------------------------------------------------------

def test_known_model_is_priced():
    cost, known = calculate("gemini-2.5-flash", 1_000_000, 0)
    assert known is True
    assert cost == pytest.approx(0.30)


def test_dated_model_id_resolves_by_prefix():
    assert lookup("gemini-2.5-flash-001") == lookup("gemini-2.5-flash")


def test_unknown_model_is_reported_as_unknown_not_as_zero():
    """The old table silently returned 0.0, so the dashboard showed $0.00."""
    reset_cache()
    cost, known = calculate("some-model-we-have-never-seen", 1000, 1000)
    assert known is False
    assert cost == 0.0


def test_env_override_prices_an_unlisted_model(monkeypatch):
    monkeypatch.setattr("app.config.LLM_MODEL", "gemini-9-ultra")
    monkeypatch.setattr("app.config.LLM_PRICE_INPUT", 1.0)
    monkeypatch.setattr("app.config.LLM_PRICE_OUTPUT", 2.0)
    reset_cache()

    cost, known = calculate("gemini-9-ultra", 1_000_000, 1_000_000)

    assert known is True
    assert cost == pytest.approx(3.0)
