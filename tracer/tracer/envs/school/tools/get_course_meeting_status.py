import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetCourseMeetingStatusTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], course_id: str, date: str) -> str:
        course = data["courses"].get(course_id)
        if course is None:
            return f"Error: Course {course_id} not found"
        if date not in course["dates"]:
            return f"Error: No record for course {course_id} on date {date}"
        return json.dumps(course["dates"][date])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_course_meeting_status",
                "description": "Get the per-date meeting status for a course.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "course_id": {
                            "type": "string",
                            "description": "Course ID.",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date key in the format YY-MM-DD.",
                        },
                    },
                    "required": ["course_id", "date"],
                },
            },
        }
