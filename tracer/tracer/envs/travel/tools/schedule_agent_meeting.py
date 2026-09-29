from typing import Any, Dict

from tracer.envs.tool import Tool


class ScheduleAgentMeetingTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        agent_id: str,
        date: str,
        time_range: str,
        traveler_id: str,
    ) -> str:
        agent = data["agents"].get(agent_id)
        if agent is None:
            return "Error: Agent not found"
        if data["travelers"].get(traveler_id) is None:
            return "Error: Traveler not found"

        if date not in agent["availability"]:
            return f"Error: Agent is not available on {date}"
        avail_day = agent["availability"][date]
        if time_range not in avail_day["slots"]:
            return f"Error: Time slot {time_range} not available on {date}"

        avail_day["slots"].remove(time_range)
        return f"Meeting scheduled with agent {agent_id} on {date} at {time_range}"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "schedule_agent_meeting",
                "description": (
                    "Schedule a meeting with an agent by reserving one of their available time "
                    "slots. Removes the slot from availability once reserved. The agent needs to "
                    "explain the details and ask for explicit user confirmation (yes/no) before "
                    "calling."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "The agent id."},
                        "date": {
                            "type": "string",
                            "description": "Meeting date in YY-MM-DD format.",
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Time slot in HH:MM-HH:MM format.",
                        },
                        "traveler_id": {
                            "type": "string",
                            "description": "The traveler id requesting the meeting.",
                        },
                    },
                    "required": ["agent_id", "date", "time_range", "traveler_id"],
                },
            },
        }
