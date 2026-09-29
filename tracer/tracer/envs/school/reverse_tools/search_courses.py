import json
from typing import Any, Dict, Optional

from tracer.envs.school.tools.register_courses import (
    _meeting_conflict,  # the tool's own rule
)
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
        compatible_with_registration_id: Optional[str] = None,
    ) -> str:
        # courses that could be ADDED to this registration: not already in it and no
        # weekly-meeting clash with any course it holds (the same predicate
        # update_registration_courses applies, so a hit here will not be refused there)
        held = []
        if compatible_with_registration_id is not None:
            reg = data["registrations"].get(compatible_with_registration_id)
            if reg is None:
                return (
                    f"Error: Registration {compatible_with_registration_id} not found"
                )
            held = [
                data["courses"][rc["course_id"]]
                for rc in reg["courses"]
                if rc["course_id"] in data["courses"]
            ]
        held_ids = {h["course_id"] for h in held}
        results = []
        for c in data["courses"].values():
            if c["term"] != term:
                continue
            if compatible_with_registration_id is not None and (
                c["course_id"] in held_ids
                or any(
                    _meeting_conflict(c["meeting_pattern"], h["meeting_pattern"])
                    for h in held
                )
            ):
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
                        "compatible_with_registration_id": {
                            "type": "string",
                            "description": (
                                "Optional registration_id. Return only courses that are NOT already in that "
                                "registration and do not clash with any of its weekly meetings, i.e. courses "
                                "update_registration_courses would accept as adds (combine with open_only=true "
                                "for capacity)."
                            ),
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
