# Copyright Sierra

from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared

from .generate_new_address import GenerateNewAddress
from .get_order_details import GetOrderDetails
from .get_product_variants import GetProductVariants
from .get_user_details import GetUserDetails
from .get_user_ids_with_n_orders import GetUserIdsWithNOrders
from .get_users_with_orders import GetUsersWithOrders
from .list_all_product_types import ListAllProductTypes

ALL_TOOLS = [
    GenerateNewAddress,
    GetOrderDetails,
    GetUserIdsWithNOrders,
    GetProductVariants,
    GetUserDetails,
    GetUsersWithOrders,
    ListAllProductTypes,
    Think,
]
