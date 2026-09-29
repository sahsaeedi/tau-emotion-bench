from tracer.envs.telecom.tools.transfer_to_human_agents import TransferToHumanAgents

from .add_device import AddDevice
from .calculate import Calculate
from .create_support_ticket import CreateSupportTicket
from .find_customer_by_email import FindCustomerByEmail
from .find_customer_by_phone import FindCustomerByPhone
from .get_billing_details import GetBillingDetails
from .get_customer_details import GetCustomerDetails
from .get_device_details import GetDeviceDetails
from .get_senior_discount import GetSeniorDiscount
from .get_service_details import GetServiceDetails
from .get_services import GetServices
from .get_support_ticket_details import GetSupportTicketDetails
from .manage_billing import ManageBilling
from .manage_service import ManageService
from .modify_support_ticket import ModifySupportTicket
from .record_payment import RecordPayment
from .think import Think
from .troubleshoot_device import TroubleshootDevice

ALL_TOOLS = [
    TransferToHumanAgents,
    # Calculate,
    # Think,
    # FindCustomerByEmail,
    # FindCustomerByPhone,
    # GetCustomerDetails,
    GetServiceDetails,
    GetDeviceDetails,
    GetBillingDetails,
    ManageService,
    TroubleshootDevice,
    CreateSupportTicket,
    GetSupportTicketDetails,
    AddDevice,
    ManageBilling,
    GetServices,
    GetSeniorDiscount,
    ModifySupportTicket,
    RecordPayment,
]
