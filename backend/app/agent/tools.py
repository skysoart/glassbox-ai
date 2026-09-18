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

def file_search(query: str) -> str:
    """Real RAG implementation scanning the docs directory"""
    try:
        docs_dir = pathlib.Path("d:/epoch/docs")
        if not docs_dir.exists():
            return "Docs directory not found."
            
        results = []
        query_terms = query.lower().split()
        
        for file_path in docs_dir.glob("**/*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                # Simple chunking by double newlines (paragraphs)
                chunks = content.split("\n\n")
                
                for i, chunk in enumerate(chunks):
                    chunk_lower = chunk.lower()
                    # Count how many query terms are in this chunk
                    score = sum(1 for term in query_terms if term in chunk_lower)
                    
                    if score > 0:
                        results.append({
                            "file": file_path.name,
                            "chunk": chunk.strip(),
                            "score": score
                        })
            except Exception:
                pass
                
        if not results:
            return f"No results found for '{query}' in knowledge base."
            
        # Sort by score descending and take top 3 chunks
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
