from typing import Any, Dict

from tracer.envs.tool import Tool


class FindPatronRefByNameZipTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], given: str, family: str, postal_code: str) -> str:
        for guest_ref, patron in data["patron_registry"].items():
            identity = patron["identity"]
            if (
                identity["given"].lower() == given.lower()
                and identity["family"].lower() == family.lower()
                and patron["location"]["postal_code"] == postal_code
            ):
                return guest_ref
        return "Error: Patron not found"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "find_patron_ref_by_name_zip",
                "description": "Find patron reference by name and postal code. Use when email is unknown or not found.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "given": {
                            "type": "string",
                            "description": "The given (first) name, such as 'John'.",
                        },
                        "family": {
                            "type": "string",
                            "description": "The family (last) name, such as 'Doe'.",
                        },
                        "postal_code": {
                            "type": "string",
                            "description": "The postal code, such as '12345'.",
                        },
                    },
                    "required": ["given", "family", "postal_code"],
                },
            },
        }
