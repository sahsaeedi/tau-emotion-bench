import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetAgentDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], agent_id: str) -> str:
        agent = data["agents"].get(agent_id)
        if agent is None:
            return "Error: Agent not found"
        return json.dumps(agent)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_agent_details",
                "description": "Get agent profile.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "The agent id.",
                        },
                    },
                    "required": ["agent_id"],
                },
            },
        }
