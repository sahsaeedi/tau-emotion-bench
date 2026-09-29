from tracer.envs.airline.reverse_tools.think import Think  # no-op scratchpad, shared
from tracer.envs.bank.reverse_tools.get_account_details import GetAccountDetailsTool
from tracer.envs.bank.reverse_tools.get_beneficiary_details import GetBeneficiaryDetails
from tracer.envs.bank.reverse_tools.get_card_details import GetCardDetailsTool
from tracer.envs.bank.reverse_tools.get_client_candidates import GetClientCandidates
from tracer.envs.bank.reverse_tools.get_client_details import GetClientDetails
from tracer.envs.bank.reverse_tools.get_loan_details import GetLoanDetailsTool
from tracer.envs.bank.reverse_tools.get_recent_transactions import (
    GetRecentTransactionsTool,
)
from tracer.envs.bank.reverse_tools.list_client_accounts import ListClientAccountsTool
from tracer.envs.bank.reverse_tools.list_client_beneficiaries import (
    ListClientBeneficiariesTool,
)
from tracer.envs.bank.reverse_tools.search_transactions import SearchTransactionsTool

ALL_TOOLS = [
    GetClientDetails,
    GetAccountDetailsTool,
    GetCardDetailsTool,
    GetLoanDetailsTool,
    GetBeneficiaryDetails,
    ListClientAccountsTool,
    ListClientBeneficiariesTool,
    GetRecentTransactionsTool,
    SearchTransactionsTool,
    GetClientCandidates,
    Think,
]
