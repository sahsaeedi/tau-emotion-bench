import json
import random
from typing import Any, Dict

from tracer.envs.tool import Tool

# Max number of user IDs to return per call (paginated batch)
_MAX_USER_IDS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different IDs
_call_counter = 0


class GetUserIdsWithNOrders(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        n: int,
    ) -> str:
        global _call_counter
        users = data["users"]
        user_ids_with_n_orders = [
            user_id
            for user_id, user in users.items()
            if len(user.get("orders", [])) >= n
        ]
        # Randomize the list, then return the offset-based batch
        random.shuffle(user_ids_with_n_orders)
        if not user_ids_with_n_orders:
            return json.dumps([])
        # Rotating offset: each call returns the next batch, wrapping when past the end
        offset = (_call_counter * _MAX_USER_IDS) % len(user_ids_with_n_orders)
        _call_counter += 1
        ids_doubled = user_ids_with_n_orders + user_ids_with_n_orders
        result = ids_doubled[offset : offset + _MAX_USER_IDS]
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_user_ids_with_n_orders",
                "description": (
                    "Get a list of user IDs that have at least n orders. "
                    "The list is randomized; each call returns up to 5 IDs with a rotating offset (different batch on subsequent calls). "
                    "Takes the number of orders (n) as parameter."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "integer",
                            "description": "The minimum number of orders the user must have.",
                        },
                    },
                    "required": ["n"],
                },
            },
        }
