# invoke() is from tau-bench: tau_bench/envs/telecom/tools/get_billing_details.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetBillingDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], customer_id: str) -> str:
        billing = data.get("billing", {})

        if customer_id not in billing:
            return f"Error: No billing information found for customer: {customer_id}"

        return json.dumps(billing[customer_id])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_billing_details",
                "description": (
                    "Get billing information for a customer, including current balance, last payment, "
                    "monthly charges, payment history, and bill settings (auto-pay, paperless). "
                    "If no billing information exists for the customer, an error string is returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": (
                                "The customer's unique identifier, such as 'john_smith_1234'."
                            ),
                        },
                    },
                    "required": ["customer_id"],
                },
                "response": {
                    "type": "object",
                    "description": (
                        "The billing record for the specified customer. "
                        "If the customer has no billing record, the function returns the string "
                        "'Error: No billing information found for customer: <customer_id>'."
                    ),
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "The customer's unique identifier.",
                        },
                        "account_number": {
                            "type": "string",
                            "description": "The customer's billing account number.",
                        },
                        "current_balance": {
                            "type": "number",
                            "description": "The customer's current outstanding balance.",
                        },
                        "last_payment": {
                            "type": "object",
                            "description": "Most recent payment made by the customer.",
                            "properties": {
                                "amount": {"type": "number"},
                                "date": {"type": "string"},
                                "method": {"type": "string"},
                                "status": {"type": "string"},
                            },
                            "required": ["amount", "date", "method", "status"],
                        },
                        "next_bill_date": {
                            "type": "string",
                            "description": "The date the next bill will be issued.",
                        },
                        "monthly_charges": {
                            "type": "object",
                            "description": (
                                "Recurring monthly charges broken down by service type. "
                                "Keys are service names; values are charge amounts."
                            ),
                            "additionalProperties": {"type": "number"},
                        },
                        "payment_history": {
                            "type": "array",
                            "description": "List of previous payments.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {"type": "string"},
                                    "amount": {"type": "number"},
                                    "status": {"type": "string"},
                                },
                                "required": ["date", "amount", "status"],
                            },
                        },
                        "auto_pay": {
                            "type": "boolean",
                            "description": "Indicates whether auto-pay is enabled.",
                        },
                        "paperless": {
                            "type": "boolean",
                            "description": "Indicates whether paperless billing is enabled.",
                        },
                    },
                    "required": [
                        "customer_id",
                        "account_number",
                        "current_balance",
                        "last_payment",
                        "next_bill_date",
                        "monthly_charges",
                        "payment_history",
                        "auto_pay",
                        "paperless",
                    ],
                    "examples": [
                        {
                            "customer_id": "john_smith_1234",
                            "account_number": "ACC001234567",
                            "current_balance": 0.00,
                            "last_payment": {
                                "amount": 245.50,
                                "date": "2025-09-15",
                                "method": "auto_pay_credit_card",
                                "status": "completed",
                            },
                            "next_bill_date": "2025-10-15",
                            "monthly_charges": {
                                "mobile_unlimited": 85.00,
                                "internet_fiber_1gb": 80.00,
                                "tv_premium": 95.00,
                                "taxes_fees": 18.50,
                            },
                            "payment_history": [
                                {
                                    "date": "2025-09-15",
                                    "amount": 245.50,
                                    "status": "completed",
                                },
                                {
                                    "date": "2025-08-15",
                                    "amount": 245.50,
                                    "status": "completed",
                                },
                                {
                                    "date": "2025-07-15",
                                    "amount": 245.50,
                                    "status": "completed",
                                },
                            ],
                            "auto_pay": True,
                            "paperless": True,
                        },
                        "Error: No billing information found for customer: john_smith_1234",
                    ],
                },
            },
        }
