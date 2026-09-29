from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.restaurant.reverse_tools.get_dish_details import GetDishDetailsTool
from tracer.envs.restaurant.reverse_tools.get_patron_candidates import (
    GetPatronCandidates,
)
from tracer.envs.restaurant.reverse_tools.get_patron_details import GetPatronDetailsTool
from tracer.envs.restaurant.reverse_tools.get_ticket_details import GetTicketDetailsTool
from tracer.envs.restaurant.reverse_tools.list_all_dishes import ListAllDishesTool

ALL_TOOLS = [
    GetTicketDetailsTool,
    GetDishDetailsTool,
    GetPatronDetailsTool,
    ListAllDishesTool,
    GetPatronCandidates,
    Think,
]
