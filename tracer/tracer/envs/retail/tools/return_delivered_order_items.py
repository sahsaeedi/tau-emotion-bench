# Copyright Sierra

import json
from typing import Any, Dict, List

from tracer.envs.tool import Tool


class ReturnDeliveredOrderItems(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], order_id: str, item_ids: List[str], payment_method_id: str
    ) -> str:
        orders = data["orders"]

        # Check if the order exists and is delivered
        if order_id not in orders:
            return "Error: order not found"
        order = orders[order_id]
        if not order["status"].startswith("delivered"):
            return "Error: non-delivered order cannot be returned"
        if "return requested" in order["status"]:
            return "Error: a return has already been requested for this order"

        # Check if the payment method exists and is either the original payment method or a gift card
        if payment_method_id not in data["users"][order["user_id"]]["payment_methods"]:
            return "Error: payment method not found"
        if (
            "gift_card" not in payment_method_id
            and payment_method_id != order["payment_history"][0]["payment_method_id"]
        ):
            return "Error: payment method should be either the original payment method or a gift card"

        # Check if the items to be returned exist (there could be duplicate items in either list)
        all_item_ids = [item["item_id"] for item in order["items"]]
        exchange_items = order.get("exchange_items", [])
        for item_id in item_ids:
            if item_ids.count(item_id) > all_item_ids.count(item_id):
                return "Error: some item not found"
            # each unit can be in only one request: units already being exchanged cannot be returned
            if item_ids.count(item_id) + exchange_items.count(
                item_id
            ) > all_item_ids.count(item_id):
                return f"Error: {item_id} is already part of an exchange request"

        # Update the order status
        order["status"] = order["status"] + " (return requested)"
        order["return_items"] = sorted(item_ids)
        order["return_payment_method_id"] = payment_method_id

        return json.dumps(order)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "return_delivered_order_items",
                "description": (
                    "Return some items of a delivered order (status 'delivered', possibly with an existing exchange request). "
                    "' (return requested)' is added to the order status. An order can have at most one return request, "
                    "and an item that is already part of an exchange request cannot be returned. "
                    "The agent needs to explain the return detail and ask for explicit user confirmation (yes/no) to proceed. "
                    "The user will receive follow-up email for how and where to return the item."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": (
                                "The order id, such as '#W0000000'. Be careful there is a '#' symbol at the beginning of the order id."
                            ),
                        },
                        "item_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "The item ids to be returned, each such as '1008292230'. There could be duplicate items in the list."
                            ),
                        },
                        "payment_method_id": {
                            "type": "string",
                            "description": (
                                "The payment method id to pay or receive refund for the item price difference, such as 'gift_card_0000000' or 'credit_card_0000000'. "
                                "These can be looked up from the user or order details."
                            ),
                        },
                    },
                    "required": ["order_id", "item_ids", "payment_method_id"],
                },
            },
        }
