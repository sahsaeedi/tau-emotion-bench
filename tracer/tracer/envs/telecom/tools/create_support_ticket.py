# invoke() is from tau-bench: tau_bench/envs/telecom/tools/create_support_ticket.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

from typing import Any, Dict

from tracer.envs.tool import Tool


class CreateSupportTicket(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any], customer_id: str, category: str, priority: str = "medium"
    ) -> str:
        tickets = data.get("support_tickets", {})
        customers = data.get("customers", {})

        if customer_id not in customers:
            return f"Error: Customer not found: {customer_id}"

        valid_categories = [
            "mobile",
            "internet",
            "tv",
            "billing",
            "account",
            "device",
            "security",
            "phone",
        ]
        if category not in valid_categories:
            return f"Error: Invalid category: {category}. Valid categories: {', '.join(valid_categories)}"

        valid_priorities = ["low", "medium", "high", "urgent"]
        if priority not in valid_priorities:
            return f"Error: Invalid priority: {priority}. Valid priorities: {', '.join(valid_priorities)}"

        # Generate ticket ID (in real system, this would be more sophisticated)
        # get the len of the tickets and add 1
        ticket_id = f"TICKET{len(tickets) + 1:03d}"

        tickets[ticket_id] = {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "status": "open",
            "priority": priority,
            "category": category,
        }

        return f"Success: Created support ticket {ticket_id} for customer {customer_id}"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "create_support_ticket",
                "description": (
                    "Create a new support ticket for a customer. Validates the customer_id, "
                    "ticket category, and priority. On success, a ticket ID is generated and "
                    "the ticket is stored with status 'open'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": (
                                "The customer's unique identifier, such as 'john_smith_1234'. "
                                "Must exist in the system."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "enum": [
                                "mobile",
                                "internet",
                                "tv",
                                "billing",
                                "account",
                                "device",
                                "security",
                                "phone",
                            ],
                            "description": (
                                "Ticket category. Must be one of: mobile, internet, tv, billing, "
                                "account, device, security, or phone."
                            ),
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "urgent"],
                            "description": (
                                "Priority level. Defaults to 'medium'. "
                                "low = non-urgent, medium = standard, high = important, urgent = critical."
                            ),
                        },
                    },
                    "required": ["customer_id", "category"],
                },
                "response": {
                    "type": "string",
                    "description": (
                        "Returns a success message such as "
                        "'Success: Created support ticket TICKET001 for customer john_smith_1234' "
                        "or an error message starting with 'Error:' if validation fails."
                    ),
                    "examples": [
                        # Success
                        "Success: Created support ticket TICKET001 for customer john_smith_1234",
                        # Customer not found
                        "Error: Customer not found: unknown_cust_9999",
                        # Invalid category
                        "Error: Invalid category: plumbing. Valid categories: mobile, internet, tv, billing, account, device, security, phone",
                        # Invalid priority
                        "Error: Invalid priority: extreme. Valid priorities: low, medium, high, urgent",
                    ],
                },
            },
        }
