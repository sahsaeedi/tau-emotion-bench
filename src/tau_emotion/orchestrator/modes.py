"""
Communication modes for orchestrator.

This module defines the communication modes that the orchestrator can use
to manage interactions between agents, users, and the environment.
"""

from enum import Enum


class CommunicationMode(str, Enum):
    """
    Communication modes for orchestrator.

    Modes:
        HALF_DUPLEX: Traditional turn-based communication (default).
                     Agent and user alternate sending complete messages.
                     This is the classic request-response pattern.
    """

    HALF_DUPLEX = "half_duplex"
