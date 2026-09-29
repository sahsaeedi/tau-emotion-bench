# invoke() is from tau-bench: tau_bench/envs/telecom/tools/get_support_ticket_details.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

import json
from typing import Any, Dict

from tracer.envs.tool import Tool


class GetSupportTicketDetails(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], ticket_id: str) -> str:
        tickets = data.get("support_tickets", {})

        if ticket_id not in tickets:
            return f"Error: Support ticket not found: {ticket_id}"

        return json.dumps(tickets[ticket_id])

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_support_ticket_details",
                "description": (
                    "Get details of a support ticket, including ticket_id, customer_id, "
                    "current status, and priority. Returns an error string if the ticket "
                    "does not exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "The support ticket identifier, such as 'TICKET001'.",
                        },
                    },
                    "required": ["ticket_id"],
                },
                "response": {
                    "type": "object",
                    "description": (
                        "The support ticket details. If the ticket_id does not exist, "
                        "the function returns the string 'Error: Support ticket not found: <ticket_id>'."
                    ),
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "The unique identifier of the support ticket.",
                        },
                        "customer_id": {
                            "type": "string",
                            "description": "The ID of the customer who created the ticket.",
                        },
                        "status": {
                            "type": "string",
                            "description": "The current status of the ticket, e.g., 'open', 'closed'.",
                        },
                        "priority": {
                            "type": "string",
                            "description": "The ticket's priority level, such as 'low', 'medium', 'high', 'urgent'.",
                        },
                    },
                    "required": ["ticket_id", "customer_id", "status", "priority"],
                    "examples": [
                        {
                            "ticket_id": "TICKET001",
                            "customer_id": "john_smith_1234",
                            "status": "closed",
                            "priority": "medium",
                        },
                        {
                            "ticket_id": "TICKET002",
                            "customer_id": "sarah_johnson_5678",
                            "status": "open",
                            "priority": "high",
                        },
                        "Error: Support ticket not found: TICKET999",
                    ],
                },
            },
        }
