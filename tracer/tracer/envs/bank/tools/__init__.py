from tracer.envs.bank.tools.add_beneficiary import AddBeneficiaryTool
from tracer.envs.bank.tools.calculate import Calculate
from tracer.envs.bank.tools.find_client_id_by_email import FindClientIdByEmail
from tracer.envs.bank.tools.freeze_account import FreezeAccountTool
from tracer.envs.bank.tools.freeze_card import FreezeCardTool
from tracer.envs.bank.tools.get_account_details import GetAccountDetailsTool
from tracer.envs.bank.tools.get_beneficiary_details import GetBeneficiaryDetails
from tracer.envs.bank.tools.get_card_details import GetCardDetailsTool
from tracer.envs.bank.tools.get_client_details import GetClientDetails
from tracer.envs.bank.tools.get_loan_details import GetLoanDetailsTool
from tracer.envs.bank.tools.get_recent_transactions import GetRecentTransactionsTool
from tracer.envs.bank.tools.initiate_internal_transfer import (
    InitiateInternalTransferTool,
)
from tracer.envs.bank.tools.initiate_transfer_to_beneficiary import (
    InitiateTransferToBeneficiaryTool,
)
from tracer.envs.bank.tools.list_client_accounts import ListClientAccountsTool
from tracer.envs.bank.tools.list_client_beneficiaries import ListClientBeneficiariesTool
from tracer.envs.bank.tools.make_loan_payment import MakeLoanPaymentTool
from tracer.envs.bank.tools.search_transactions import SearchTransactionsTool
from tracer.envs.bank.tools.think import Think
from tracer.envs.bank.tools.transfer_to_human_agents import TransferToHumanAgents
from tracer.envs.bank.tools.unfreeze_account import UnfreezeAccountTool
from tracer.envs.bank.tools.unfreeze_card import UnfreezeCardTool
from tracer.envs.bank.tools.verify_beneficiary import VerifyBeneficiaryTool

ALL_TOOLS = [
    FindClientIdByEmail,
    Calculate,
    TransferToHumanAgents,
    GetClientDetails,
    GetAccountDetailsTool,
    GetCardDetailsTool,
    GetLoanDetailsTool,
    GetBeneficiaryDetails,
    ListClientAccountsTool,
    ListClientBeneficiariesTool,
    GetRecentTransactionsTool,
    SearchTransactionsTool,
    InitiateInternalTransferTool,
    AddBeneficiaryTool,
    VerifyBeneficiaryTool,
    InitiateTransferToBeneficiaryTool,
    FreezeCardTool,
    UnfreezeCardTool,
    FreezeAccountTool,
    UnfreezeAccountTool,
    MakeLoanPaymentTool,
    Think,
]
