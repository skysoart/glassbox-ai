"""Model price lookup.

The previous implementation hardcoded three models and silently returned a
cost of 0.0 for anything else, which made every run in the dashboard read
$0.00. Here an unknown model is reported as unknown (``None``) so the UI can
say so instead of showing a fabricated zero.
"""
import json
import os
import threading
from typing import Dict, Optional, Tuple

from app import config

_lock = threading.Lock()
_table: Optional[Dict[str, Dict[str, float]]] = None
_warned: set = set()


def _load_table() -> Dict[str, Dict[str, float]]:
    global _table
    with _lock:
        if _table is None:
            try:
                with open(config.PRICING_FILE, "r", encoding="utf-8") as fh:
                    _table = json.load(fh).get("models", {})
            except (OSError, ValueError) as exc:
                print(f"[pricing] could not read {config.PRICING_FILE}: {exc}")
                _table = {}
        return _table


def reset_cache() -> None:
    """Drop the cached table (used by the tests)."""
    global _table
    with _lock:
        _table = None
    _warned.clear()


def lookup(model: str) -> Optional[Dict[str, float]]:
    """Return {'input': x, 'output': y} in USD per 1M tokens, or None."""
    if not model:
        return None

    # An explicit override always wins, so an unlisted model can still be priced.
    if config.LLM_PRICE_INPUT is not None and config.LLM_PRICE_OUTPUT is not None:
        if model == config.LLM_MODEL or config.LLM_MODEL.startswith(model) or model.startswith(config.LLM_MODEL):
            return {"input": config.LLM_PRICE_INPUT, "output": config.LLM_PRICE_OUTPUT}

    table = _load_table()
    if model in table:
        return table[model]

    # Longest-prefix match, so "gemini-2.5-flash-001" finds "gemini-2.5-flash".
    candidates = [name for name in table if model.startswith(name)]
    if candidates:
        return table[max(candidates, key=len)]

    if model not in _warned:
        _warned.add(model)
        print(
            f"[pricing] no price known for model '{model}'. Cost will be reported "
            f"as unknown. Add it to {os.path.basename(config.PRICING_FILE)} or set "
            f"LLM_PRICE_INPUT / LLM_PRICE_OUTPUT in .env."
        )
    return None


def calculate(model: str, prompt_tokens: int, completion_tokens: int) -> Tuple[float, bool]:
    """Return (cost_usd, is_known).

    When the model has no known price the cost is 0.0 *and* is_known is False,
    so callers can distinguish "free" from "we don't know".
    """
    prices = lookup(model)
    if prices is None:
        return 0.0, False
    cost = (prompt_tokens / 1_000_000) * prices["input"] + (completion_tokens / 1_000_000) * prices["output"]
    return cost, True
