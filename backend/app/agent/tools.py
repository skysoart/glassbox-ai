import ast
import operator
import pathlib
import re
import urllib.parse
import urllib.request
from collections import Counter
from typing import Dict, Tuple

from app import config

# --- calculator -------------------------------------------------------------

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# ** on large operands can hang the process long before it runs out of memory,
# so the exponent and base are bounded.
_MAX_EXPONENT = 1000
_MAX_POW_BASE = 10 ** 6


def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression without using eval()."""

    def _eval(node):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError("Only numeric literals are allowed")
            return node.value
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPS:
                raise ValueError("Unsupported operator")
            left, right = _eval(node.left), _eval(node.right)
            if op_type is ast.Pow:
                if abs(right) > _MAX_EXPONENT or abs(left) > _MAX_POW_BASE:
                    raise ValueError("Exponent out of supported range")
            return _ALLOWED_OPS[op_type](left, right)
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -_eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +_eval(node.operand)
        raise ValueError("Unsupported syntax")

    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except ZeroDivisionError:
        return "Error evaluating expression: division by zero"
    except Exception as exc:  # noqa: BLE001 - message goes back to the model
        return "Error evaluating expression: " + str(exc)


# --- web search -------------------------------------------------------------

WEB_SEARCH_TIMEOUT_SECONDS = 10


def web_search(query: str) -> str:
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        # Without a timeout a hung request blocks the whole worker thread.
        with urllib.request.urlopen(req, timeout=WEB_SEARCH_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")

        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        cleaned = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets]
        cleaned = [s for s in cleaned if s]
        if cleaned:
            return "\n".join(cleaned[:3])
        return "No results found."
    except Exception as exc:  # noqa: BLE001 - message goes back to the model
        return "Web search failed: " + str(exc)


# --- retrieval over the local docs ------------------------------------------

RAG_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cant", "cannot", "could",
    "did", "do", "does", "doing", "dont", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "if", "in", "into", "is", "it", "its",
    "itself", "let", "me", "more", "most", "my", "myself", "no", "nor", "not", "of",
    "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves", "tell",
    "show", "give", "please", "hello", "hi", "ok", "hey", "joke", "say", "good",
}

_WORD_RE = re.compile(r"\b[a-zA-Z0-9_-]{3,}\b")
RAG_TOP_K = 3
RAG_MAX_CHUNK_CHARS = 2000


def _docs_dir() -> pathlib.Path:
    return pathlib.Path(config.DOCS_DIR)


def search_docs(query: str) -> Tuple[str, bool, Dict]:
    """Retrieve relevant documentation chunks.

    Returns ``(text, matched, details)``. The explicit ``matched`` flag replaces
    the old convention of sniffing the rendered output for a marker string.
    """
    docs_dir = _docs_dir()
    if not docs_dir.exists():
        return (
            "Docs directory not found at " + str(docs_dir) + ".",
            False,
            {"reason": "DOCS_DIR_MISSING", "path": str(docs_dir)},
        )

    terms = [w for w in _WORD_RE.findall(query.lower()) if w not in RAG_STOPWORDS]
    if not terms:
        return (
            "NO_RELEVANT_DOCS: conversational or general query with no knowledge-base terms.",
            False,
            {"reason": "NO_QUERY_TERMS", "terms": []},
        )

    results = []
    files_scanned = 0
    for file_path in sorted(docs_dir.glob("**/*.md")):
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        files_scanned += 1
        file_stem = file_path.stem.lower()
        # Filename relevance is a property of the file, not of each chunk; the
        # old code added it once per matching term per chunk, which let a long
        # file outrank a genuinely better passage.
        filename_bonus = 5 * sum(1 for term in terms if term in file_stem)

        for chunk in content.split("\n\n"):
            chunk_text = chunk.strip()
            if not chunk_text:
                continue
            counts = Counter(_WORD_RE.findall(chunk_text.lower()))
            score = sum(counts[term] * 2 for term in terms if term in counts)
            if score > 0:
                results.append({
                    "file": file_path.name,
                    "chunk": chunk_text[:RAG_MAX_CHUNK_CHARS],
                    "score": score + filename_bonus,
                })

    if not results:
        return (
            "NO_RELEVANT_DOCS: no documents matched '" + ", ".join(terms) + "'.",
            False,
            {"reason": "NO_MATCH", "terms": terms, "files_scanned": files_scanned},
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:RAG_TOP_K]

    output = "RAG Search Results for '" + query + "':\n\n"
    for r in top:
        output += "--- From " + r["file"] + " ---\n" + r["chunk"] + "\n\n"

    details = {
        "terms": terms,
        "files_scanned": files_scanned,
        "matches": len(results),
        "top_sources": [{"file": r["file"], "score": r["score"]} for r in top],
    }
    return output.strip(), True, details


def file_search(query: str) -> str:
    """Tool-facing wrapper: the model only needs the text."""
    text, _, _ = search_docs(query)
    return text


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluates a mathematical expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression, e.g. '2 + 2 * 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Searches the internal document knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The query to search in files"}
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_REGISTRY = {
    "calculator": lambda args: calculator(args.get("expression", "")),
    "web_search": lambda args: web_search(args.get("query", "")),
    "file_search": lambda args: file_search(args.get("query", "")),
}


def execute_tool(name: str, arguments: dict) -> str:
    handler = TOOL_REGISTRY.get(name)
    if handler is None:
        return "Error: unknown tool '" + str(name) + "'."
    try:
        return handler(arguments or {})
    except Exception as exc:  # noqa: BLE001 - a crashing tool must not kill the run
        return "Error: tool '" + str(name) + "' raised " + type(exc).__name__ + ": " + str(exc)
