import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Conjunctive finder. The single-purpose lists (get_customers_with_senior_plan,
# _with_devices, _with_outstanding_balance, _with_open_tickets) cannot be intersected
# by the generator: a trace needing a senior customer WITH devices AND a balance due
# AND an open ticket (26 of 1000 exist) cost it 20+ steps of paging. One call here.

_MAX_CUSTOMERS = 5
_call_counter = 0
_OPEN_STATUSES = ("open", "in_progress", "pending")


class GetCustomerCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        senior_plan: Optional[bool] = None,
        has_devices: Optional[bool] = None,
        has_outstanding_balance: Optional[bool] = None,
        has_open_ticket: Optional[bool] = None,
        service_id: Optional[str] = None,
        min_services: Optional[int] = None,
        min_devices: Optional[int] = None,
    ) -> str:
        global _call_counter
        customers = data["customers"]
        billing = data.get("billing", {})
        tickets = data.get("support_tickets", {})

        open_by_customer: Dict[str, List[str]] = {}
        for tid, t in tickets.items():
            if t.get("status") in _OPEN_STATUSES:
                open_by_customer.setdefault(t.get("customer_id"), []).append(tid)

        candidates = []
        for cid, c in customers.items():
            services = c.get("services", [])
            devices = c.get("devices") or []
            balance = (billing.get(cid) or {}).get("current_balance", 0) or 0
            open_tickets = open_by_customer.get(cid, [])

            if senior_plan is not None and ("mobile_senior" in services) != bool(
                senior_plan
            ):
                continue
            if has_devices is not None and bool(devices) != bool(has_devices):
                continue
            if has_outstanding_balance is not None and (balance > 0) != bool(
                has_outstanding_balance
            ):
                continue
            if has_open_ticket is not None and bool(open_tickets) != bool(
                has_open_ticket
            ):
                continue
            if service_id is not None and service_id not in services:
                continue
            if min_services is not None and len(services) < int(min_services):
                continue
            if min_devices is not None and len(devices) < int(min_devices):
                continue
            candidates.append(
                {
                    "customer_id": cid,
                    "email": c.get("demographics", {}).get("email", ""),
                    "services": services,
                    "devices": [
                        {
                            "device_id": d.get("device_id"),
                            "name": d.get("name"),
                            "service": d.get("service"),
                        }
                        for d in devices
                    ],
                    "current_balance": balance,
                    "open_ticket_ids": sorted(open_tickets),
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "customers": []}, indent=2
            )
        offset = (_call_counter * _MAX_CUSTOMERS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_CUSTOMERS]
        return json.dumps(
            {"total_matching": total, "returned_count": len(batch), "customers": batch},
            indent=2,
        )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_customer_candidates",
                "description": (
                    "Read-only finder: customers matching ALL given filters at once (senior plan, "
                    "devices, balance due, open ticket, a specific service), for grounding a trace "
                    "that needs several preconditions on ONE customer. Returns up to 5 randomized "
                    "customers per call with customer_id, email, services, devices, current_balance "
                    "and open_ticket_ids; call again for another batch. Prefer this over intersecting "
                    "the single-purpose lists by hand."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "senior_plan": {
                            "type": "boolean",
                            "description": "True = on mobile_senior (get_senior_discount scenarios); False = not.",
                        },
                        "has_devices": {
                            "type": "boolean",
                            "description": "True = at least one device (troubleshoot_device / device tickets).",
                        },
                        "has_outstanding_balance": {
                            "type": "boolean",
                            "description": "True = current_balance > 0, i.e. record_payment can apply a positive amount.",
                        },
                        "has_open_ticket": {
                            "type": "boolean",
                            "description": "True = has a ticket in open / in_progress / pending status (modify_support_ticket).",
                        },
                        "service_id": {
                            "type": "string",
                            "description": "Only customers subscribed to this service id (e.g. internet_fiber_1gb).",
                        },
                        "min_services": {
                            "type": "integer",
                            "description": "At least this many services (manage_service removal needs one to remove).",
                        },
                        "min_devices": {
                            "type": "integer",
                            "description": "At least this many devices.",
                        },
                    },
                    "required": [],
                },
            },
        }
