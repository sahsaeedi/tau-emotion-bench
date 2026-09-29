import json
from typing import Any, Dict, Optional, Tuple

from tracer.envs.tool import Tool


def _find_show(
    data: Dict[str, Any], theater_id: str, show_id: str, date: Optional[str] = None
) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """Find a show by ID in a given theater, optionally constrained by date.

    Returns (show, date, error) - show and date are None if error is set.
    """
    theater = data["theaters"].get(theater_id)
    if theater is None:
        return None, None, f"Error: Theater {theater_id} not found"
    if date is not None:
        if date not in theater["dates"]:
            return (
                None,
                None,
                f"Error: No schedule for date {date} at theater {theater_id}",
            )
        for show in theater["dates"][date]["shows"]:
            if show["show_id"] == show_id:
                return show, date, None
        return (
            None,
            None,
            f"Error: Show {show_id} not found on date {date} at theater {theater_id}",
        )
    for d, day in theater["dates"].items():
        for show in day["shows"]:
            if show["show_id"] == show_id:
                return show, d, None
    return None, None, f"Error: Show {show_id} not found at theater {theater_id}"


class GetShowDetailsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        theater_id: str,
        show_id: str,
        date: Optional[str] = None,
    ) -> str:
        show, _, err = _find_show(data, theater_id, show_id, date)
        if err:
            return err
        return json.dumps(show)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_show_details",
                "description": "Get show details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "show_id": {"type": "string", "description": "The show id."},
                        "date": {
                            "type": "string",
                            "description": "Optional date to constrain the search, in the format YY-MM-DD.",
                        },
                    },
                    "required": ["theater_id", "show_id"],
                },
            },
        }
