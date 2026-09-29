import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListCoursesByTermTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], term: str) -> str:
        results = [
            {
                "course_id": c["course_id"],
                "course_code": c["course_code"],
                "title": c["title"],
            }
            for c in data["courses"].values()
            if c["term"] == term
        ]
        return json.dumps(results)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_courses_by_term",
                "description": "List all courses for a given term.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Term in the format YYYY-TERM, e.g. 2025-SPRING.",
                        },
                    },
                    "required": ["term"],
                },
            },
        }
