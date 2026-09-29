from tracer.envs.telecom.tools.add_device import AddDevice
from tracer.envs.telecom.tools.create_support_ticket import CreateSupportTicket
from tracer.envs.telecom.tools.find_customer_by_email import FindCustomerByEmail
from tracer.envs.telecom.tools.find_customer_by_phone import FindCustomerByPhone
from tracer.envs.telecom.tools.get_billing_details import GetBillingDetails
from tracer.envs.telecom.tools.get_device_details import GetDeviceDetails
from tracer.envs.telecom.tools.get_senior_discount import GetSeniorDiscount
from tracer.envs.telecom.tools.get_service_details import GetServiceDetails
from tracer.envs.telecom.tools.get_services import GetServices
from tracer.envs.telecom.tools.get_support_ticket_details import GetSupportTicketDetails
from tracer.envs.telecom.tools.manage_billing import ManageBilling
from tracer.envs.telecom.tools.manage_service import ManageService
from tracer.envs.telecom.tools.modify_support_ticket import ModifySupportTicket
from tracer.envs.telecom.tools.record_payment import RecordPayment
from tracer.envs.telecom.tools.think import Think
from tracer.envs.telecom.tools.troubleshoot_device import TroubleshootDevice

from .calculate import Calculate
from .get_customer_candidates import GetCustomerCandidates
from .get_customer_details import GetCustomerDetails
from .get_customers_by_service import GetCustomersByService
from .get_customers_with_devices import GetCustomersWithDevices
from .get_customers_with_open_tickets import GetCustomersWithOpenTickets
from .get_customers_with_outstanding_balance import GetCustomersWithOutstandingBalance
from .get_customers_with_senior_plan import GetCustomersWithSeniorPlan
from .get_user_ids import GetUserIds

ALL_TOOLS = [
    # Reverse tools (read-only, for task grounding)
    GetUserIds,
    GetCustomersWithSeniorPlan,
    GetCustomersWithOutstandingBalance,
    GetCustomersWithOpenTickets,
    GetCustomersByService,
    GetCustomersWithDevices,
    # Forward tools (used by the agent to solve tasks)
    # AddDevice,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    Calculate,
    # CreateSupportTicket,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    FindCustomerByEmail,
    FindCustomerByPhone,
    GetBillingDetails,
    GetCustomerDetails,
    GetDeviceDetails,
    GetSeniorDiscount,
    GetServiceDetails,
    GetServices,
    GetSupportTicketDetails,
    # ManageBilling,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    # ManageService,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    # ModifySupportTicket,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    # RecordPayment,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    Think,
    # TroubleshootDevice,   # WRITE tool: removed from the grounding set (the generator created a ghost ticket through it)
    GetCustomerCandidates,
]
