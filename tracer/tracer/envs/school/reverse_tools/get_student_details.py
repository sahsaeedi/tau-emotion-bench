import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetStudentDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], student_id: str) -> str:
        student = data["students"].get(student_id)
        if student is None:
            return f"Error: Student {student_id} not found"
        return json.dumps(student)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_student_details",
                "description": "Get the details of a student.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "string",
                            "description": "The student id.",
                        },
                    },
                    "required": ["student_id"],
                },
            },
        }
