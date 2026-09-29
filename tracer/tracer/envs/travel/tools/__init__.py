from tracer.envs.travel.tools.book_package import BookPackageTool
from tracer.envs.travel.tools.calculate import CalculateTool
from tracer.envs.travel.tools.cancel_booking import CancelBookingTool
from tracer.envs.travel.tools.get_agent_details import GetAgentDetailsTool
from tracer.envs.travel.tools.get_booking_details import GetBookingDetailsTool
from tracer.envs.travel.tools.get_package_details import GetPackageDetailsTool
from tracer.envs.travel.tools.get_traveler_details import GetTravelerDetailsTool
from tracer.envs.travel.tools.list_all_destinations import ListAllDestinationsTool
from tracer.envs.travel.tools.schedule_agent_meeting import ScheduleAgentMeetingTool
from tracer.envs.travel.tools.search_packages import SearchPackagesTool
from tracer.envs.travel.tools.think import ThinkTool
from tracer.envs.travel.tools.transfer_to_human_agents import TransferToHumanAgentsTool
from tracer.envs.travel.tools.update_booking_add_ons import UpdateBookingAddOnsTool
from tracer.envs.travel.tools.update_booking_departure_date import (
    UpdateBookingDepartureDateTool,
)
from tracer.envs.travel.tools.update_booking_rooming import UpdateBookingRoomingTool
from tracer.envs.travel.tools.update_booking_travelers import UpdateBookingTravelersTool

ALL_TOOLS = [
    GetTravelerDetailsTool,
    GetAgentDetailsTool,
    GetPackageDetailsTool,
    GetBookingDetailsTool,
    SearchPackagesTool,
    ListAllDestinationsTool,
    BookPackageTool,
    CancelBookingTool,
    UpdateBookingAddOnsTool,
    UpdateBookingDepartureDateTool,
    UpdateBookingTravelersTool,
    UpdateBookingRoomingTool,
    ScheduleAgentMeetingTool,
    TransferToHumanAgentsTool,
    CalculateTool,
    ThinkTool,
]
