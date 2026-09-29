# invoke() is from tau-bench: tau_bench/envs/telecom/tools/modify_support_ticket.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

from typing import Any, Dict

from tracer.envs.tool import Tool


class ModifySupportTicket(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], ticket_id: str, status: str, priority: str) -> str:
        tickets = data.get("support_tickets", {})

        if ticket_id not in tickets:
            return f"Error: Support ticket not found: {ticket_id}"

        tickets[ticket_id]["status"] = status
        tickets[ticket_id]["priority"] = priority

        return f"Success: Modified support ticket {ticket_id} with status {status} and priority {priority}"

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "modify_support_ticket",
                "description": (
                    "Modify the status and priority of a support ticket. "
                    "If the ticket_id does not exist, an error string is returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "The support ticket identifier, such as 'TICKET001'.",
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "open",
                                "closed",
                                "pending",
                                "in_progress",
                                "resolved",
                            ],
                            "description": (
                                "New status for the ticket. Typical values include 'open', 'closed', "
                                "'pending', 'in_progress', or 'resolved'."
                            ),
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "urgent"],
                            "description": (
                                "New priority for the ticket: 'low', 'medium', 'high', or 'urgent'."
                            ),
                        },
                    },
                    "required": ["ticket_id", "status", "priority"],
                },
                "response": {
                    "type": "string",
                    "description": (
                        "Returns a success message indicating the ticket was modified, or an error "
                        "string if the ticket_id does not exist."
                    ),
                    "examples": [
                        # Success cases
                        "Success: Modified support ticket TICKET001 with status open and priority high",
                        "Success: Modified support ticket TICKET002 with status resolved and priority urgent",
                        # Error cases
                        "Error: Support ticket not found: TICKET999",
                    ],
                },
            },
        }
