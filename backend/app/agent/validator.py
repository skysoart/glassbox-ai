class Validator:
    @staticmethod
    def validate_tool_call(tool_name: str, arguments: dict, available_tools: list) -> tuple[bool, str]:
        tool_names = [t["function"]["name"] for t in available_tools]
        if tool_name not in tool_names:
            return False, f"Wrong tool selection: '{tool_name}' is not a valid tool."
        
        # basic argument validation
        schema = next((t["function"]["parameters"] for t in available_tools if t["function"]["name"] == tool_name), None)
        if schema:
            required = schema.get("required", [])
            for req in required:
                if req not in arguments:
                    return False, f"Malformed tool arguments: missing required argument '{req}'."
                    
        return True, "Valid"

    @staticmethod
    def validate_tool_result(tool_name: str, result: str) -> tuple[bool, str]:
        if result.startswith("Error") or "failed:" in result.lower():
            return False, f"Tool execution failure: {result}"
        return True, "Valid"
