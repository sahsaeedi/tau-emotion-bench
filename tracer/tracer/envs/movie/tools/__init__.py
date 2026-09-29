from tracer.envs.movie.tools.calculate import Calculate
from tracer.envs.movie.tools.cancel_booking import CancelBookingTool
from tracer.envs.movie.tools.create_booking import CreateBookingTool
from tracer.envs.movie.tools.get_booking_details import GetBookingDetailsTool
from tracer.envs.movie.tools.get_movie_details import GetMovieDetailsTool
from tracer.envs.movie.tools.get_seat_availability import GetSeatAvailabilityTool
from tracer.envs.movie.tools.get_show_details import GetShowDetailsTool
from tracer.envs.movie.tools.get_show_status import GetShowStatusTool
from tracer.envs.movie.tools.get_theater_details import GetTheaterDetailsTool
from tracer.envs.movie.tools.list_movies import ListMoviesTool
from tracer.envs.movie.tools.list_shows import ListShowsTool
from tracer.envs.movie.tools.list_theaters import ListTheatersTool
from tracer.envs.movie.tools.price_preview import PricePreviewTool
from tracer.envs.movie.tools.transfer_to_human_agents import TransferToHumanAgents
from tracer.envs.movie.tools.update_booking_seats import UpdateBookingSeatsTool

ALL_TOOLS = [
    ListMoviesTool,
    ListTheatersTool,
    GetMovieDetailsTool,
    GetTheaterDetailsTool,
    ListShowsTool,
    GetShowDetailsTool,
    GetShowStatusTool,
    GetSeatAvailabilityTool,
    PricePreviewTool,
    CreateBookingTool,
    CancelBookingTool,
    UpdateBookingSeatsTool,
    GetBookingDetailsTool,
    # Calculate,
    # TransferToHumanAgents,
]
