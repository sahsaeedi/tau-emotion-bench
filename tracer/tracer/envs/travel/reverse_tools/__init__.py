from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.travel.reverse_tools.get_agent_details import GetAgentDetailsTool
from tracer.envs.travel.reverse_tools.get_booking_details import GetBookingDetailsTool
from tracer.envs.travel.reverse_tools.get_package_details import GetPackageDetailsTool
from tracer.envs.travel.reverse_tools.get_traveler_candidates import (
    GetTravelerCandidates,
)
from tracer.envs.travel.reverse_tools.get_traveler_details import GetTravelerDetailsTool
from tracer.envs.travel.reverse_tools.list_all_destinations import (
    ListAllDestinationsTool,
)
from tracer.envs.travel.reverse_tools.search_packages import SearchPackagesTool

from .preview_booking_price import PreviewBookingPrice

ALL_TOOLS = [
    GetTravelerDetailsTool,
    GetAgentDetailsTool,
    GetPackageDetailsTool,
    GetBookingDetailsTool,
    SearchPackagesTool,
    ListAllDestinationsTool,
    GetTravelerCandidates,
    Think,
    PreviewBookingPrice,
]
