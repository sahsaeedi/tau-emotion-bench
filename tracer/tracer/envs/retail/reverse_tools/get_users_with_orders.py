import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of users to return per call (paginated batch)
_MAX_USERS = 5

_call_counter = 0


def _normalize_status(status: Optional[str]) -> Optional[str]:
    if isinstance(status, str) and status.startswith("delivered"):
        return "delivered"
    return status


def _user_ids_filtered_by_status(
    data: Dict[str, Any],
    status_filters: Optional[List[str]],
) -> List[str]:
    """Return user_ids that have at least one order.

    If status_filters is provided, user must have at least one order for EACH
    requested status (e.g. ["pending", "delivered"]).
    """
    users = data["users"]
    orders = data["orders"]
    result = []
    for user_id, user in users.items():
        order_ids = user.get("orders", [])
        if not order_ids:
            continue
        if not status_filters:
            result.append(user_id)
            continue
        # a status listed twice means "at least two orders in that status", so a
        # trace that cancels one pending order and modifies another can find a user
        from collections import Counter

        user_statuses = Counter(
            _normalize_status(orders.get(oid, {}).get("status")) for oid in order_ids
        )
        need = Counter(status_filters)
        if all(user_statuses.get(status, 0) >= n for status, n in need.items()):
            result.append(user_id)
    return result


def _counts_by_status(data: Dict[str, Any], user_id: str) -> Dict[str, int]:
    users = data["users"]
    orders = data["orders"]
    order_ids = users.get(user_id, {}).get("orders", [])
    counts = {"delivered": 0, "pending": 0, "cancelled": 0, "processed": 0}
    for oid in order_ids:
        status = _normalize_status(orders.get(oid, {}).get("status"))
        if status in counts:
            counts[status] += 1
    return counts


class GetUsersWithOrders(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        statuses: Optional[List[str]] = None,
    ) -> str:
        global _call_counter
        users = data["users"]
        user_ids = _user_ids_filtered_by_status(data, statuses)
        random.shuffle(user_ids)
        if not user_ids:
            return json.dumps([])
        offset = (_call_counter * _MAX_USERS) % len(user_ids)
        _call_counter += 1
        ids_doubled = user_ids + user_ids
        batch_ids = ids_doubled[offset : offset + _MAX_USERS]
        result = []
        for uid in batch_ids:
            order_ids = users[uid].get("orders", [])
            counts = _counts_by_status(data, uid)
            row = {
                "user_id": uid,
                "email": users[uid].get("email"),
                "total_orders": len(order_ids),
                "delivered_count": counts["delivered"],
                "pending_count": counts["pending"],
                "cancelled_count": counts["cancelled"],
            }
            # a status requested twice = "cancel one, modify another": name the two
            # DIFFERENT orders so the writes never land on the same one
            for status in set(statuses or []) | {"pending", "delivered"}:
                same = sorted(
                    oid
                    for oid in order_ids
                    if _normalize_status(data["orders"].get(oid, {}).get("status"))
                    == status
                )
                if len(same) >= 2:
                    row[f"{status}_pair"] = {
                        "modify_target": {
                            "order_id": same[0],
                            "status": status,
                            "why": f"{status} -> modify_pending_* / return / exchange accept it",
                        },
                        "cancel_target": {
                            "order_id": same[1],
                            "status": status,
                            "why_cancellable": f"another {status} order of this user",
                        },
                    }
            result.append(row)
        return json.dumps(result)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_users_with_orders",
                "description": (
                    "Get users who have at least one order. "
                    "Returns for each user: user_id, email, total_orders, delivered_count, pending_count, cancelled_count (no full user or order details). "
                    "Optional parameter statuses: return users who have at least one order for EACH requested status "
                    "(e.g. ['pending', 'delivered']); repeat a status to require several orders in it "
                    "(['pending', 'pending'] = users with two pending orders; the row then carries pending_pair with "
                    "modify_target and cancel_target -- two DIFFERENT order ids, copy them into the two writes). "
                    "If no filter is provided, return all users with orders (paginated). "
                    "Results are randomized; each call returns up to 5 users with a rotating offset."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "statuses": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["pending", "delivered"],
                            },
                            "description": (
                                "Optional. Multi-status filter. If provided, returns only users who have at least one order "
                                "for EACH status in this list (e.g. ['pending', 'delivered']). Repeat a status to require "
                                "that many orders in it: ['pending', 'pending'] = at least two pending orders."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
