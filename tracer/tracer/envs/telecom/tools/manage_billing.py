# invoke() is from tau-bench: tau_bench/envs/telecom/tools/manage_billing.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class ManageBilling(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        customer_id: str,
        paperless: bool,
        auto_pay: bool,
        billing_cycle: str,
    ) -> str:
        customers = data.get("customers", {})
        billing = data.get("billing", {})

        # check to make sure the customer exists
        if customer_id not in customers:
            return f"Error: Customer not found: {customer_id}"

        customer_billing = billing[customer_id]

        customer_billing["paperless"] = paperless
        customer_billing["auto_pay"] = auto_pay
        customer_billing["billing_cycle"] = billing_cycle

        return json.dumps({"customer_id": customer_id, "billing": customer_billing})

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_billing",
                "description": (
                    "Update a customer's billing preferences, including paperless billing, auto-pay, "
                    "and billing cycle. Returns the updated billing record for that customer. "
                    "If the customer does not exist, returns an error string."
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
                        "paperless": {
                            "type": "boolean",
                            "description": (
                                "Whether the customer is enrolled in paperless billing. "
                                "True enables paperless, False disables it."
                            ),
                        },
                        "auto_pay": {
                            "type": "boolean",
                            "description": (
                                "Whether auto-pay is enabled for the customer's account. "
                                "True enables auto-pay, False disables it."
                            ),
                        },
                        "billing_cycle": {
                            "type": "string",
                            "enum": ["monthly", "quarterly", "annual"],
                            "description": (
                                "The billing cycle for the customer's account. "
                                "Allowed values: 'monthly', 'quarterly', 'annual'."
                            ),
                        },
                    },
                    "required": [
                        "customer_id",
                        "paperless",
                        "auto_pay",
                        "billing_cycle",
                    ],
                },
                "response": {
                    "type": "object",
                    "description": (
                        "The updated billing information for the customer. "
                        "If the customer_id is not found, the function returns the string "
                        "'Error: Customer not found: <customer_id>'."
                    ),
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "The customer's unique identifier.",
                        },
                        "billing": {
                            "type": "object",
                            "description": (
                                "The full billing record for the customer after the update."
                            ),
                            "properties": {
                                "customer_id": {
                                    "type": "string",
                                    "description": "The customer's unique identifier.",
                                },
                                "account_number": {
                                    "type": "string",
                                    "description": "The account number associated with billing.",
                                },
                                "current_balance": {
                                    "type": "number",
                                    "description": "Current outstanding balance on the account.",
                                },
                                "last_payment": {
                                    "type": "object",
                                    "description": "Information about the most recent payment.",
                                    "properties": {
                                        "amount": {
                                            "type": "number",
                                            "description": "Last payment amount.",
                                        },
                                        "date": {
                                            "type": "string",
                                            "description": "Date of the last payment in 'YYYY-MM-DD' format.",
                                        },
                                        "method": {
                                            "type": "string",
                                            "description": "Payment method used for the last payment.",
                                        },
                                        "status": {
                                            "type": "string",
                                            "description": "Status of the last payment, e.g., 'completed'.",
                                        },
                                    },
                                    "required": ["amount", "date", "method", "status"],
                                },
                                "next_bill_date": {
                                    "type": "string",
                                    "description": "Next bill date in 'YYYY-MM-DD' format.",
                                },
                                "monthly_charges": {
                                    "type": "object",
                                    "description": (
                                        "Breakdown of recurring monthly charges by service "
                                        "plus taxes/fees."
                                    ),
                                    "additionalProperties": {
                                        "type": "number",
                                        "description": "Charge amount for the given line item.",
                                    },
                                },
                                "payment_history": {
                                    "type": "array",
                                    "description": "Historical list of payments made on the account.",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {
                                                "type": "string",
                                                "description": "Payment date in 'YYYY-MM-DD' format.",
                                            },
                                            "amount": {
                                                "type": "number",
                                                "description": "Payment amount.",
                                            },
                                            "status": {
                                                "type": "string",
                                                "description": "Payment status, e.g., 'completed'.",
                                            },
                                        },
                                        "required": ["date", "amount", "status"],
                                    },
                                },
                                "auto_pay": {
                                    "type": "boolean",
                                    "description": "Whether auto-pay is enabled after the update.",
                                },
                                "paperless": {
                                    "type": "boolean",
                                    "description": "Whether paperless billing is enabled after the update.",
                                },
                                "billing_cycle": {
                                    "type": "string",
                                    "description": (
                                        "The updated billing cycle, e.g., 'monthly', 'quarterly', or 'annual'."
                                    ),
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
                        },
                    },
                    "required": ["customer_id", "billing"],
                    "examples": [
                        {
                            "customer_id": "john_smith_1234",
                            "billing": {
                                "customer_id": "john_smith_1234",
                                "account_number": "ACC001234567",
                                "current_balance": 0.0,
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
                                "auto_pay": False,
                                "paperless": False,
                                "billing_cycle": "quarterly",
                            },
                        },
                        "Error: Customer not found: unknown_customer",
                    ],
                },
            },
        }
