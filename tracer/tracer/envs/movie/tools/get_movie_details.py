import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetMovieDetailsTool(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], movie_id: str) -> str:
        movie = data["movies"].get(movie_id)
        if movie is None:
            return f"Error: Movie {movie_id} not found"
        return json.dumps(movie)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_movie_details",
                "description": "Get details for a movie.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "movie_id": {
                            "type": "string",
                            "description": "The movie id.",
                        },
                    },
                    "required": ["movie_id"],
                },
            },
        }
