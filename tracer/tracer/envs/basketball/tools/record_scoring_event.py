import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class RecordScoringEventTool(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        game_id: str,
        event_type: str,
        points: int,
        club_id: str,
        player_id: str,
        timestamp: str,
    ) -> str:
        game = data["games"].get(game_id)
        if game is None:
            return "Error: Game not found"
        if game["status"] != "in_progress":
            return "Error: Scoring can only be recorded for games in progress"

        expected_points = {"2PT": 2, "3PT": 3, "FT": 1}.get(event_type)
        if expected_points is None:
            return "Error: Invalid event type"
        if points != expected_points:
            return "Error: Points do not match the event type"

        home_id = game["clubs"]["home"]["club_id"]
        away_id = game["clubs"]["away"]["club_id"]
        if club_id not in (home_id, away_id):
            return "Error: Club is not part of this game"

        if player_id not in data["players"]:
            return "Error: Player not found"

        event = {
            "event_type": event_type,
            "points": points,
            "club_id": club_id,
            "player_id": player_id,
            "timestamp": timestamp,
        }
        game["scoring_history"].append(event)

        if club_id == home_id:
            game["clubs"]["home"]["score"] += points
        else:
            game["clubs"]["away"]["score"] += points

        return json.dumps(game)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "record_scoring_event",
                "description": (
                    "Record a scoring event for an in-progress game, update the team's score, and append "
                    "to scoring history. The agent needs to explain the modification detail and ask for "
                    "explicit user confirmation (yes/no) to proceed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {"type": "string", "description": "The game ID."},
                        "event_type": {
                            "type": "string",
                            "enum": ["2PT", "3PT", "FT"],
                            "description": "Type of scoring event.",
                        },
                        "points": {
                            "type": "integer",
                            "description": "Points scored (must match the event type: 2 for 2PT, 3 for 3PT, 1 for FT).",
                        },
                        "club_id": {
                            "type": "string",
                            "description": "The club credited with the score (must be either home or away club of the game).",
                        },
                        "player_id": {
                            "type": "string",
                            "description": "The player credited with the score (must exist in the database).",
                        },
                        "timestamp": {
                            "type": "string",
                            "description": "Timestamp string within the game context (e.g., 'Q2 03:21').",
                        },
                    },
                    "required": [
                        "game_id",
                        "event_type",
                        "points",
                        "club_id",
                        "player_id",
                        "timestamp",
                    ],
                },
            },
        }
