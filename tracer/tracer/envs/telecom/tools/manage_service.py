# invoke() is from tau-bench: tau_bench/envs/telecom/tools/manage_service.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

import json
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool


class ManageService(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        customer_id: str,
        action: str,
        service_id: Optional[str] = None,
        devices_ids: Optional[List[str]] = None,
    ) -> str:
        customers = data.get("customers", {})
        services = data.get("services", {})
        billing = data.get("billing", {})

        # check to make sure the customer exists
        if customer_id not in customers:
            return f"Error: Customer not found: {customer_id}"

        customer = customers[customer_id]
        customer_services = customer.get("services", [])

        devices = customer.get("devices", [])

        if action == "list":
            result = []
            for svc_id in customer_services:
                if svc_id in services:
                    svc = services[svc_id]
                    result.append(svc)
            return json.dumps({"customer_id": customer_id, "services": result})

        # check to make sure the service exists
        if not service_id:
            return f"Error: Service ID is required for action: {action}"

        if action == "add":
            if service_id not in services:
                return f"Error: Service not found: {service_id}"

            if service_id in customer_services:
                return (
                    f"Error: Customer {customer_id} already has service: {service_id}"
                )

            if devices_ids:
                for device_id in devices_ids:
                    if device_id not in [d["device_id"] for d in devices]:
                        return (
                            f"Error: Device not found: {device_id} in devices {devices}"
                        )

                    for device in devices:
                        if device["device_id"] == device_id:
                            device["service"] = service_id
                            break

            customer_services.append(service_id)
            service_name = services.get(service_id, {}).get("name", service_id)

            billing_entry = billing.get(customer_id)
            if isinstance(billing_entry, dict):
                billing_entry["monthly_charges"][service_id] = services.get(
                    service_id, {}
                ).get("price", 0.0)

            return f"Success: Added service '{service_name}' to customer {customer_id}"

        elif action == "remove":
            if service_id not in customer_services:
                return (
                    f"Error: Customer {customer_id} does not have service: {service_id}"
                )

            # loop through the devices and remove any devices that were associated with the service
            removed_devices = []
            for device in devices:
                if device.get("service") == service_id:
                    device["service"] = None
                    removed_devices.append(device.get("name"))

            customer_services.remove(service_id)

            service_name = services.get(service_id, {}).get("name", service_id)

            billing_entry = billing.get(customer_id)
            if isinstance(billing_entry, dict):
                billing_entry["monthly_charges"].pop(service_id)

            return f"Success: Removed service '{service_name}' from customer {customer_id}. Devices {removed_devices} are now no longer associated with the service."

        else:
            return (
                f"Error: Invalid action: {action}. Valid actions are: add, remove, list"
            )

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "manage_service",
                "description": (
                    "Manage customer services: add, remove, or list services on an account. "
                    "For 'list', the function returns a JSON object of the customer's services. "
                    "For 'add' and 'remove', it returns a human-readable status string. "
                    "On failure (e.g., invalid customer, service, action, or device), it returns an error string."
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
                        "action": {
                            "type": "string",
                            "enum": ["add", "remove", "list"],
                            "description": (
                                "Action to perform on the customer's services: "
                                "'list' to retrieve all services, "
                                "'add' to add a service, "
                                "'remove' to remove a service."
                            ),
                        },
                        "service_id": {
                            "type": "string",
                            "description": (
                                "The service identifier, such as 'mobile_unlimited'. "
                                "Required when action is 'add' or 'remove'. "
                                "Ignored for 'list'."
                            ),
                        },
                        "devices_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional list of device IDs to associate with the service when action is 'add'. "
                                "Each ID must match a 'device_id' in the customer's devices list. "
                                "Ignored for 'list'. When removing a service, all devices currently "
                                "associated with that service are automatically detached."
                            ),
                        },
                    },
                    "required": ["customer_id", "action"],
                },
                "response": {
                    "anyOf": [
                        {
                            "type": "object",
                            "description": (
                                "Returned when action is 'list': the customer's current services enriched "
                                "with service details."
                            ),
                            "properties": {
                                "customer_id": {
                                    "type": "string",
                                    "description": "The customer's unique identifier.",
                                },
                                "services": {
                                    "type": "array",
                                    "description": (
                                        "List of service objects for this customer. Each entry comes from the "
                                        "global 'services' catalog."
                                    ),
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "service_id": {
                                                "type": "string",
                                                "description": "Service identifier, e.g. 'mobile_unlimited'.",
                                            },
                                            "name": {
                                                "type": "string",
                                                "description": "Human-readable service name.",
                                            },
                                            "category": {
                                                "type": "string",
                                                "description": "Service category, e.g. 'mobile', 'internet', 'tv'.",
                                            },
                                            "price": {
                                                "type": "number",
                                                "description": "Standard monthly price of the service.",
                                            },
                                        },
                                        "required": [
                                            "service_id",
                                            "name",
                                            "category",
                                            "price",
                                        ],
                                    },
                                },
                            },
                            "required": ["customer_id", "services"],
                        },
                        {
                            "type": "string",
                            "description": (
                                "Status or error message returned when action is 'add' or 'remove', "
                                "or when an error occurs. For example:\n"
                                "- 'Success: Added service ...'\n"
                                "- 'Success: Removed service ...'\n"
                                "- 'Error: Customer not found: ...'\n"
                                "- 'Error: Service not found: ...'"
                            ),
                        },
                    ],
                    "examples": [
                        {
                            "customer_id": "john_smith_1234",
                            "services": [
                                {
                                    "service_id": "mobile_unlimited",
                                    "name": "Unlimited Mobile Plan",
                                    "category": "mobile",
                                    "price": 85.00,
                                },
                                {
                                    "service_id": "internet_fiber_1gb",
                                    "name": "Fiber Internet 1 Gbps",
                                    "category": "internet",
                                    "price": 80.00,
                                },
                                {
                                    "service_id": "tv_premium",
                                    "name": "Premium TV Package",
                                    "category": "tv",
                                    "price": 95.00,
                                },
                            ],
                        },
                        "Success: Added service 'Unlimited Mobile Plan' to customer john_smith_1234",
                        (
                            "Success: Removed service 'Unlimited Mobile Plan' from customer john_smith_1234. "
                            "Devices ['iPhone 15 Pro'] are now no longer associated with the service."
                        ),
                        "Error: Customer not found: unknown_customer",
                        "Error: Service not found: mobile_unlimited_plus",
                        "Error: Invalid action: update. Valid actions are: add, remove, list",
                    ],
                },
            },
        }
