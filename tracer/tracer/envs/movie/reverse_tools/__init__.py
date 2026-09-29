from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.movie.reverse_tools.get_booking_candidates import GetBookingCandidates
from tracer.envs.movie.reverse_tools.get_booking_details import GetBookingDetailsTool
from tracer.envs.movie.reverse_tools.get_movie_details import GetMovieDetailsTool
from tracer.envs.movie.reverse_tools.get_seat_availability import (
    GetSeatAvailabilityTool,
)
from tracer.envs.movie.reverse_tools.get_show_candidates import GetShowCandidates
from tracer.envs.movie.reverse_tools.get_show_details import GetShowDetailsTool
from tracer.envs.movie.reverse_tools.get_show_status import GetShowStatusTool
from tracer.envs.movie.reverse_tools.get_theater_details import GetTheaterDetailsTool
from tracer.envs.movie.reverse_tools.list_movies import ListMoviesTool
from tracer.envs.movie.reverse_tools.list_shows import ListShowsTool
from tracer.envs.movie.reverse_tools.list_theaters import ListTheatersTool
from tracer.envs.movie.reverse_tools.price_preview import PricePreviewTool

from .preview_seat_update import PreviewSeatUpdate

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
    GetBookingDetailsTool,
    GetBookingCandidates,
    GetShowCandidates,
    Think,
    PreviewSeatUpdate,
]
