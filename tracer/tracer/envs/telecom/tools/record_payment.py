# invoke() is from tau-bench: tau_bench/envs/telecom/tools/record_payment.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class RecordPayment(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        customer_id: str,
        amount: float | int | str,
        method: str,
        date: str,
    ) -> str:
        billing = data.get("billing", {})
        if customer_id not in billing:
            return f"Error: No billing information found for customer: {customer_id}"

        try:
            amount_value = round(float(amount), 2)
        except (TypeError, ValueError):
            return "Error: amount must be a number"

        entry = billing[customer_id]
        current_balance = float(entry.get("current_balance", 0.0))
        new_balance = max(round(current_balance - amount_value, 2), 0.0)
        entry["current_balance"] = new_balance

        payment_record = {
            "date": date,
            "amount": amount_value,
            "status": "completed",
        }
        history = entry.setdefault("payment_history", [])
        history.append(payment_record)

        entry["last_payment"] = {
            "amount": amount_value,
            "date": date,
            "method": method,
            "status": "completed",
        }

        return json.dumps(
            {
                "customer_id": customer_id,
                "amount": f"{amount_value:.2f}",
                "method": method,
                "date": date,
                "current_balance": f"{new_balance:.2f}",
            }
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "record_payment",
                "description": (
                    "Apply a payment to a customer account, update the remaining balance, and "
                    "record the payment in billing history. "
                    "Returns an error string if the customer has no billing information or "
                    "if the amount is not a valid number."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": (
                                "Unique customer identifier, e.g. 'john_smith_1234'. "
                                "Must exist in the billing data."
                            ),
                        },
                        "amount": {
                            "type": "number",
                            "description": (
                                "Payment amount to apply. It will be rounded to two decimals. "
                                "If a non-numeric value is provided, the tool returns an error."
                            ),
                        },
                        "method": {
                            "type": "string",
                            "enum": ["credit_card", "bank_transfer"],
                            "description": (
                                "Payment method used. Supported values: 'credit_card', 'bank_transfer'."
                            ),
                        },
                        "date": {
                            "type": "string",
                            "description": (
                                "Payment date in ISO format, e.g. '2025-09-18'. "
                                "This value is recorded as-is in the billing history."
                            ),
                        },
                    },
                    "required": ["customer_id", "amount", "method", "date"],
                },
                "response": {
                    "type": "object",
                    "description": (
                        "On success, returns a JSON object describing the applied payment and "
                        "the updated balance. On failure, the tool instead returns an error "
                        "string starting with 'Error:'."
                    ),
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "The customer id the payment was applied to.",
                        },
                        "amount": {
                            "type": "string",
                            "description": (
                                "Payment amount applied, formatted as a string with two decimals, "
                                "e.g. '245.50'."
                            ),
                        },
                        "method": {
                            "type": "string",
                            "description": "Payment method used, e.g. 'credit_card'.",
                        },
                        "date": {
                            "type": "string",
                            "description": "Payment date as provided, e.g. '2025-09-18'.",
                        },
                        "current_balance": {
                            "type": "string",
                            "description": (
                                "Updated account balance after applying the payment, formatted "
                                "as a string with two decimals, e.g. '0.00'."
                            ),
                        },
                    },
                    "required": [
                        "customer_id",
                        "amount",
                        "method",
                        "date",
                        "current_balance",
                    ],
                    "examples": [
                        {
                            "customer_id": "john_smith_1234",
                            "amount": "100.00",
                            "method": "credit_card",
                            "date": "2025-09-18",
                            "current_balance": "0.00",
                        }
                        # Error cases (returned as plain strings from the tool, not objects):
                        # "Error: No billing information found for customer: jane_doe_9999"
                        # "Error: amount must be a number"
                    ],
                },
            },
        }
