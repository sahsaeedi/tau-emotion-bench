from typing import Any, Dict

from tracer.envs.tool import Tool


class TransferToHumanAgents(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], summary: str) -> str:
        return "Transfer successful"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "transfer_to_human_agents",
                "description": (
                    "Transfer the user to a human agent, with a concise summary. "
                    "Only transfer if requested by the user or the issue cannot be "
                    "solved by the available tools/policies."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "A concise summary of the user's issue.",
                        },
                    },
                    "required": ["summary"],
                },
            },
        }
