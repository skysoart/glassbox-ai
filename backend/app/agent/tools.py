import json
import ast
import operator
import urllib.request
import urllib.parse
import re

def calculator(expression: str) -> str:
    """Safe eval for simple math"""
    allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
    }
    
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return allowed_ops[type(node.op)](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -_eval(node.operand)
            elif isinstance(node.op, ast.UAdd):
                return _eval(node.operand)
        raise ValueError(f"Unsupported syntax")

    try:
        node = ast.parse(expression, mode='eval').body
        result = _eval(node)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"

def web_search(query: str) -> str:
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            results = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            clean_results = [re.sub(r'<[^>]+>', '', r).strip() for r in results]
            if clean_results:
                return "\n".join(clean_results[:3])
            return "No results found."
    except Exception as e:
        return f"Web search failed: {str(e)}"

import os
import pathlib
import re
from collections import Counter

RAG_STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 
    'any', 'are', 'aren', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 
    'below', 'between', 'both', 'but', 'by', 'can', 'cant', 'cannot', 'could', 
    'did', 'do', 'does', 'doing', 'dont', 'down', 'during', 'each', 'few', 'for', 
    'from', 'further', 'had', 'has', 'have', 'having', 'he', 'her', 'here', 'hers', 
    'herself', 'him', 'himself', 'his', 'how', 'if', 'in', 'into', 'is', 'it', 'its', 
    'itself', 'let', 'me', 'more', 'most', 'my', 'myself', 'no', 'nor', 'not', 'of', 
    'off', 'on', 'once', 'only', 'or', 'other', 'ought', 'our', 'ours', 'ourselves', 
    'out', 'over', 'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than', 
    'that', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'these', 
    'they', 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 
    'was', 'we', 'were', 'what', 'when', 'where', 'which', 'while', 'who', 'whom', 
    'why', 'with', 'would', 'you', 'your', 'yours', 'yourself', 'yourselves', 'tell', 
    'show', 'give', 'please', 'hello', 'hi', 'ok', 'hey', 'joke', 'say', 'good', 'can'
}

def file_search(query: str) -> str:
    """Accurate RAG implementation with stopword elimination and token frequency scoring"""
    try:
        base_dir = pathlib.Path(__file__).resolve().parent.parent.parent.parent
        docs_dir = base_dir / "docs"
        if not docs_dir.exists():
            docs_dir = pathlib.Path("d:/glassbox/docs")
        if not docs_dir.exists():
            docs_dir = pathlib.Path("docs")
        if not docs_dir.exists():
            return "Docs directory not found."

        # Extract substantive terms of 3+ letters
        raw_words = re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', query.lower())
        query_terms = [w for w in raw_words if w not in RAG_STOPWORDS]

        if not query_terms:
            return f"NO_RELEVANT_DOCS: Conversational or general query with no knowledge-base matches."

        results = []
        for file_path in docs_dir.glob("**/*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                chunks = content.split("\n\n")
                file_stem = file_path.stem.lower()

                for chunk in chunks:
                    chunk_text = chunk.strip()
                    if not chunk_text:
                        continue
                    chunk_words = re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', chunk_text.lower())
                    counts = Counter(chunk_words)

                    score = 0
                    for term in query_terms:
                        if term in counts:
                            score += counts[term] * 2
                        if term in file_stem:
                            score += 5

                    if score > 0:
                        results.append({
                            "file": file_path.name,
                            "chunk": chunk_text,
                            "score": score
                        })
            except Exception:
                pass

        if not results:
            return f"NO_RELEVANT_DOCS: No documents matched query terms '{', '.join(query_terms)}'."

        results.sort(key=lambda x: x["score"], reverse=True)
        top_results = results[:3]

        output = f"RAG Search Results for '{query}':\n\n"
        for r in top_results:
            output += f"--- From {r['file']} ---\n{r['chunk']}\n\n"

        return output.strip()
    except Exception as e:
        return f"File search failed: {str(e)}"

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
                        "description": "The math expression, e.g. '2 + 2 * 3'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Searches the internal document knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search in files"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def execute_tool(name: str, arguments: dict) -> str:
    if name == "calculator":
        return calculator(arguments.get("expression", ""))
    elif name == "web_search":
        return web_search(arguments.get("query", ""))
    elif name == "file_search":
        return file_search(arguments.get("query", ""))
    return f"Unknown tool: {name}"
