import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ListMoviesTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any]) -> str:
        movies = [
            {"movie_id": m["movie_id"], "title": m["title"]}
            for m in data["movies"].values()
        ]
        return json.dumps(movies)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "list_movies",
                "description": "List all movies.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
