from tracer.envs.restaurant.tools.add_tip_to_ticket import AddTipToTicketTool
from tracer.envs.restaurant.tools.calculate import CalculateTool
from tracer.envs.restaurant.tools.cancel_placed_ticket import CancelPlacedTicketTool
from tracer.envs.restaurant.tools.find_patron_ref_by_email import (
    FindPatronRefByEmailTool,
)
from tracer.envs.restaurant.tools.find_patron_ref_by_name_zip import (
    FindPatronRefByNameZipTool,
)
from tracer.envs.restaurant.tools.get_dish_details import GetDishDetailsTool
from tracer.envs.restaurant.tools.get_patron_details import GetPatronDetailsTool
from tracer.envs.restaurant.tools.get_ticket_details import GetTicketDetailsTool
from tracer.envs.restaurant.tools.list_all_dishes import ListAllDishesTool
from tracer.envs.restaurant.tools.modify_placed_ticket_dropoff import (
    ModifyPlacedTicketDropoffTool,
)
from tracer.envs.restaurant.tools.modify_placed_ticket_instrument import (
    ModifyPlacedTicketInstrumentTool,
)
from tracer.envs.restaurant.tools.modify_placed_ticket_items import (
    ModifyPlacedTicketItemsTool,
)
from tracer.envs.restaurant.tools.modify_placed_ticket_table import (
    ModifyPlacedTicketTableTool,
)
from tracer.envs.restaurant.tools.think import ThinkTool
from tracer.envs.restaurant.tools.transfer_to_human_agents import (
    TransferToHumanAgentsTool,
)

ALL_TOOLS = [
    CalculateTool,
    TransferToHumanAgentsTool,
    GetTicketDetailsTool,
    GetDishDetailsTool,
    GetPatronDetailsTool,
    ListAllDishesTool,
    FindPatronRefByEmailTool,
    FindPatronRefByNameZipTool,
    CancelPlacedTicketTool,
    ModifyPlacedTicketDropoffTool,
    ModifyPlacedTicketTableTool,
    ModifyPlacedTicketItemsTool,
    ModifyPlacedTicketInstrumentTool,
    AddTipToTicketTool,
    ThinkTool,
]
