import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool

# Max number of user IDs to return per call (subset, not all)
_MAX_USER_IDS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different IDs
_call_counter = 0


class GetUserIdsWithNReservations(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        n: int,
    ) -> str:
        global _call_counter
        users = data["users"]
        user_ids_with_n_reservations = []
        for user_id, user in users.items():
            reservations = user.get("reservations", [])
            if len(reservations) >= n:
                user_ids_with_n_reservations.append(user_id)
        # Randomize the list, then return the offset-based batch
        random.shuffle(user_ids_with_n_reservations)
        if not user_ids_with_n_reservations:
            return json.dumps([])
        # Rotating offset: each call returns the next batch, wrapping when past the end
        offset = (_call_counter * _MAX_USER_IDS) % len(user_ids_with_n_reservations)
        _call_counter += 1
        ids_doubled = user_ids_with_n_reservations + user_ids_with_n_reservations
        result = ids_doubled[offset : offset + _MAX_USER_IDS]
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_user_ids_with_n_reservations",
                "description": (
                    "Get a list of up to a few user IDs with at least n reservations. "
                    "The list is randomized; each call returns the next offset batch (different from previous calls). "
                    "Takes the number of reservations as parameter. "
                    "Useful to find users with a certain number of reservations when the trace has that many TURNs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "integer",
                            "description": "The number of reservations to filter by.",
                        },
                    },
                    "required": [],
                },
            },
        }
