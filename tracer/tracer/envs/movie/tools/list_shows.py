import json
from typing import Any, Dict, Optional

from tracer.envs.tool import Tool


class ListShowsTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        theater_id: str,
        date: str,
        movie_id: Optional[str] = None,
    ) -> str:
        theater = data["theaters"].get(theater_id)
        if theater is None:
            return f"Error: Theater {theater_id} not found"
        if date not in theater["dates"]:
            return json.dumps([])
        shows = theater["dates"][date]["shows"]
        if movie_id is not None:
            shows = [s for s in shows if s["movie_id"] == movie_id]
        return json.dumps(shows)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_shows",
                "description": "List shows at a given theater for a date, optionally filtered by movie_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "theater_id": {
                            "type": "string",
                            "description": "The theater id.",
                        },
                        "date": {
                            "type": "string",
                            "description": "Date to list shows for, in the format YY-MM-DD, e.g. 24-05-01.",
                        },
                        "movie_id": {
                            "type": "string",
                            "description": "Optional movie id to filter shows by.",
                        },
                    },
                    "required": ["theater_id", "date"],
                },
            },
        }
