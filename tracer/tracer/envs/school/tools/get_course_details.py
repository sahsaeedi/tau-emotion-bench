import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetCourseDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], course_id: str) -> str:
        course = data["courses"].get(course_id)
        if course is None:
            return f"Error: Course {course_id} not found"
        return json.dumps(course)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_course_details",
                "description": "Get the details of a course.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "course_id": {
                            "type": "string",
                            "description": "The course id.",
                        },
                    },
                    "required": ["course_id"],
                },
            },
        }
