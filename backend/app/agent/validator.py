from typing import Any, Dict, List, Tuple

# A tool signals failure by starting its result with one of these. Matching on
# a prefix rather than searching the whole string keeps a legitimate result
# that merely contains the word "failed" from being treated as an error.
TOOL_ERROR_PREFIXES = (
    "Error",
    "Web search failed:",
    "Docs directory not found",
)

_JSON_TYPES = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "object": dict,
    "array": list,
}


class Validator:
    @staticmethod
    def validate_tool_call(
        tool_name: str, arguments: dict, available_tools: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        schemas = {t["function"]["name"]: t["function"] for t in available_tools}

        if tool_name not in schemas:
            return False, (
                "Wrong tool selection: '" + str(tool_name) + "' is not a valid tool. "
                "Available tools: " + ", ".join(sorted(schemas)) + "."
            )

        if not isinstance(arguments, dict):
            return False, "Malformed tool arguments: expected a JSON object."

        parameters = schemas[tool_name].get("parameters") or {}
        properties = parameters.get("properties", {})

        for required in parameters.get("required", []):
            if required not in arguments:
                return False, "Malformed tool arguments: missing required argument '" + required + "'."

        for name, value in arguments.items():
            if name not in properties:
                return False, (
                    "Malformed tool arguments: unexpected argument '" + name + "'. "
                    "Expected one of: " + ", ".join(sorted(properties)) + "."
                )
            expected = properties[name].get("type")
            python_type = _JSON_TYPES.get(expected)
            if python_type is not None:
                ok = isinstance(value, python_type)
                # bool is a subclass of int; don't let True pass as a number.
                if expected in ("number", "integer") and isinstance(value, bool):
                    ok = False
                if not ok:
                    return False, (
                        "Malformed tool arguments: '" + name + "' should be of type "
                        + str(expected) + ", got " + type(value).__name__ + "."
                    )

        return True, "Valid"

    @staticmethod
    def validate_tool_result(tool_name: str, result: Any) -> Tuple[bool, str]:
        if not isinstance(result, str):
            return False, "Tool '" + str(tool_name) + "' returned a non-string result."
        if result.startswith(TOOL_ERROR_PREFIXES):
            return False, "Tool execution failure: " + result
        return True, "Valid"
