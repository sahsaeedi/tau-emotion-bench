from typing import Any, Dict, Optional, Tuple

from tracer.envs.tool import Tool


def _find_show(
    data: Dict[str, Any], theater_id: str, show_id: str
) -> Tuple[Optional[dict], Optional[str]]:
    """Find a show by ID in a given theater, searching across all dates.

    Returns (show, error) - show is None if error is set.
    """
    theater = data["theaters"].get(theater_id)
    if theater is None:
        return None, f"Error: Theater {theater_id} not found"
    for day in theater["dates"].values():
        for show in day["shows"]:
            if show["show_id"] == show_id:
                return show, None
    return None, f"Error: Show {show_id} not found at theater {theater_id}"


class GetShowStatusTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], theater_id: str, show_id: str) -> str:
        show, err = _find_show(data, theater_id, show_id)
        if err:
            return err
        return show["status"]

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_show_status",
                "description": "Get current status of a show.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "show_id": {"type": "string", "description": "The show id."},
                    },
                    "required": ["theater_id", "show_id"],
                },
            },
        }
