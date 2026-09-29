import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


def _parse_time_hhmm(hhmm: str) -> int:
    # "HH-MM" -> minutes since midnight
    parts = hhmm.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format: {hhmm}")
    h = int(parts[0])
    m = int(parts[1])
    return h * 60 + m


class SearchCoursesTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        term: str,
        department: Optional[str] = None,
        campus: Optional[str] = None,
        day: Optional[str] = None,
        start_after: Optional[str] = None,
        end_before: Optional[str] = None,
        open_only: bool = False,
    ) -> str:
        results = []
        for c in data["courses"].values():
            if c["term"] != term:
                continue
            if department and c["department"] != department:
                continue
            if campus and c["location"]["campus"] != campus:
                continue
            if day and day not in c["meeting_pattern"]["days"]:
                continue
            if start_after and _parse_time_hhmm(
                c["meeting_pattern"]["start_time_est"]
            ) < _parse_time_hhmm(start_after):
                continue
            if end_before and _parse_time_hhmm(
                c["meeting_pattern"]["end_time_est"]
            ) > _parse_time_hhmm(end_before):
                continue
            if open_only and not (c["current_enrollment"] < c["capacity"]):
                continue
            results.append(c)
        return json.dumps(results)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_courses",
                "description": "Search for courses with common filters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Term in the format YYYY-TERM.",
                        },
                        "department": {
                            "type": "string",
                            "description": "Optional department code to filter.",
                        },
                        "campus": {
                            "type": "string",
                            "description": "Optional campus name to filter.",
                        },
                        "day": {
                            "type": "string",
                            "enum": [
                                "Monday",
                                "Tuesday",
                                "Wednesday",
                                "Thursday",
                                "Friday",
                                "Saturday",
                                "Sunday",
                            ],
                            "description": "Optional day of week filter.",
                        },
                        "start_after": {
                            "type": "string",
                            "description": 'Optional earliest start time ("HH-MM").',
                        },
                        "end_before": {
                            "type": "string",
                            "description": 'Optional latest end time ("HH-MM").',
                        },
                        "open_only": {
                            "type": "boolean",
                            "description": "If True, only return courses with open seats.",
                        },
                    },
                    "required": ["term"],
                },
            },
        }
