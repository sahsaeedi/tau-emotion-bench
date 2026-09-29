# invoke() is from tau-bench: tau_bench/envs/telecom/tools/troubleshoot_device.py
# (MIT License, Copyright (c) 2024 Sierra); get_info() is TRACER's.

from enum import Enum
from typing import Any, Dict

from tracer.envs.tool import Tool


class Issue(Enum):
    NO_SERVICE = "no_service"
    SLOW_SPEEDS = "slow_speeds"
    BATTERY_DRAIN = "battery_drain"


class TroubleshootDevice(Tool):
    @staticmethod
    def invoke(data: Dict[str, Any], device_name: str, issue: str) -> str:
        devices = data.get("devices", {})
        issue = Issue(issue)

        if device_name not in devices:
            return f"Error: Device not found: {device_name}"

        device = devices[device_name]
        device_category = device.get("category", "")
        # Return troubleshooting steps based on device category and issue type
        if device_category == "mobile_phone" or device_category == "phone":
            if issue == Issue.BATTERY_DRAIN:
                return """
Troubleshooting steps: 
1) Restart device 
2) Check brightness settings and reduce if needed
3) Close background apps
4) Contact support if issue persists
"""
            elif issue == Issue.NO_SERVICE:
                return """
Troubleshooting steps: 
1) Restart device 
2) Check signal coverage 
3) Reset network settings 
4) Contact support if issue persists
"""
            elif issue == Issue.SLOW_SPEEDS:
                return """
Troubleshooting steps: 
1) Restart device 
2) Check data usage and plan limits
3) Reset network settings 
4) Contact support if issue persists
"""
            else:
                return """Unknown issue"""

        elif device_category == "networking":
            if issue == Issue.NO_SERVICE:
                return """
Troubleshooting steps: 
1) Restart router by unplugging for 30 seconds
2) Check all cable connections 
3) Update firmware if available
4) Contact support if needed
"""
            elif issue == Issue.SLOW_SPEEDS:
                return """
Troubleshooting steps: 
1) Restart router by unplugging for 30 seconds
2) Check cable connections 
3) Run speed test 
4) Contact support if needed
"""
            else:
                return """Unknown issue"""

        elif device_category == "tv":
            if issue == Issue.NO_SERVICE or issue == Issue.NO_SIGNAL:
                return """
Troubleshooting steps: 
1) Check correct input/source 
2) Verify cable connections 
3) Restart cable box 
4) Contact support if needed
"""
            else:
                return """Unknown issue"""
        else:
            return """Unknown issue"""

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "troubleshoot_device",
                "description": (
                    "Provide troubleshooting steps for a given device and issue type. "
                    "If the device is not found or the issue is not recognized for the device category, "
                    "an error string or 'Unknown issue' is returned."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string",
                            "description": (
                                "Name of the device, such as 'iPhone 15 Pro' or 'WiFi 6 Router'. "
                                "Must exist in the device catalog."
                            ),
                        },
                        "issue": {
                            "type": "string",
                            "enum": ["no_service", "slow_speeds", "battery_drain"],
                            "description": (
                                "Issue type to troubleshoot. Supported issues: "
                                "'no_service', 'slow_speeds', 'battery_drain'."
                            ),
                        },
                    },
                    "required": ["device_name", "issue"],
                },
                "response": {
                    "type": "string",
                    "description": (
                        "Returns troubleshooting steps as a multi-line string. "
                        "If the device is not found, returns an error string "
                        "'Error: Device not found: <device_name>'. "
                        "If the issue is unsupported for the device category, returns 'Unknown issue'."
                    ),
                    "examples": [
                        # Success (mobile phone battery issue)
                        (
                            "Troubleshooting steps: \n"
                            "1) Restart device \n"
                            "2) Check brightness settings and reduce if needed\n"
                            "3) Close background apps\n"
                            "4) Contact support if issue persists\n"
                        ),
                        # Success (mobile phone no service)
                        (
                            "Troubleshooting steps: \n"
                            "1) Restart device \n"
                            "2) Check signal coverage \n"
                            "3) Reset network settings \n"
                            "4) Contact support if issue persists\n"
                        ),
                        # Error (device not in dataset)
                        "Error: Device not found: Nokia 3310",
                        # Error (unknown / unsupported issue)
                        "Unknown issue",
                    ],
                },
            },
        }
