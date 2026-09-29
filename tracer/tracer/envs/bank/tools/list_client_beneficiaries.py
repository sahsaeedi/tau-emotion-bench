import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListClientBeneficiariesTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], client_id: str) -> str:
        client = data["clients"].get(client_id)
        if client is None:
            return "Error: Client not found"
        result = {}
        for beneficiary_id in client["beneficiary_ids"]:
            beneficiary = data["beneficiaries"].get(beneficiary_id)
            if beneficiary is None:
                continue
            name = beneficiary["name"]
            display = (
                name.get("display_name")
                or name.get("business_name")
                or " ".join(
                    filter(None, [name.get("first_name"), name.get("last_name")])
                )
                or "Unnamed Beneficiary"
            )
            result[beneficiary_id] = display
        return json.dumps(result, sort_keys=True)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_client_beneficiaries",
                "description": "List all beneficiaries for a client as a JSON mapping beneficiary_id to a display name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_id": {
                            "type": "string",
                            "description": "The client id.",
                        },
                    },
                    "required": ["client_id"],
                },
            },
        }
