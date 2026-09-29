"""Pydantic models for the bank domain.

Schema is reverse-engineered from TRACER's bank data files
(tracer/tracer/envs/bank/data/) merged into
db.json.

A client's `accounts` and `cards` are keyed maps (by account id and card id)
rather than fixed-field objects. Accounts and cards therefore have no
top-level collection: they are reached through the client who holds them,
which is why the tools scan clients to resolve an account or card id.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.bank.utils import BANK_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class Address(BaseModel):
    address1: str
    address2: str
    city: str
    state: str
    zip: str
    country: str


class Contact(BaseModel):
    email: str
    phone: str


class ClientName(BaseModel):
    first_name: str
    last_name: str
    middle_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Accounts and cards
# ---------------------------------------------------------------------------


class Balance(BaseModel):
    current: float
    available: float
    on_hold: float


class AccountFeatures(BaseModel):
    online_banking: bool
    checks_enabled: bool
    atm_access: bool


class Account(BaseModel):
    account_id: str
    type: str
    status: str
    currency: str
    account_number_masked: str
    routing_number: str
    opened_at: str
    balance: Balance
    features: AccountFeatures
    interest_rate_apr: Optional[float] = None
    overdraft_limit: Optional[float] = None


class CardExtraInfo(BaseModel):
    brand: str
    last_four: str
    exp_month: str
    exp_year: str


class CardLimits(BaseModel):
    daily_atm_limit: float
    daily_pos_limit: float


class Card(BaseModel):
    card_id: str
    type: str
    status: str
    issuer: str
    linked_account_id: str
    pin_set: bool
    extra_info: CardExtraInfo
    limits: CardLimits


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


class Kyc(BaseModel):
    status: str
    last_reviewed_at: str
    tax_id_masked: str


class Client(BaseModel):
    client_id: str
    name: ClientName
    contact: Contact
    address: Address
    kyc: Kyc
    created_at: str
    accounts: Dict[str, Account]
    cards: Dict[str, Card]
    loan_ids: List[str] = Field(default_factory=list)
    beneficiary_ids: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Beneficiaries
# ---------------------------------------------------------------------------


class BeneficiaryName(BaseModel):
    """Either a person (first/last) or a business, with a display name."""

    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    business_name: Optional[str] = None


class BankDetails(BaseModel):
    bank_name: str
    account_number_masked: str
    routing_number: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None


class TransferLimits(BaseModel):
    per_transfer_limit: float
    daily_limit: float


class Verification(BaseModel):
    status: str
    method: str
    verified_at: Optional[str] = None


class Beneficiary(BaseModel):
    beneficiary_id: str
    client_id: str
    name: BeneficiaryName
    type: str
    bank_details: BankDetails
    address: Address
    allowed_from_account_ids: List[str] = Field(default_factory=list)
    transfer_limits: TransferLimits
    verification: Verification
    status: str
    created_at: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------


class ScheduledPayment(BaseModel):
    due_date: str
    amount: float
    currency: str
    status: str
    transaction_id: Optional[str] = None


class Repayment(BaseModel):
    transaction_id: str
    posted_at: str
    amount: float
    currency: str
    method: str
    principal_component: float
    interest_component: float
    fees_component: float


class Collateral(BaseModel):
    type: str
    description: str
    value_amount: float
    value_currency: str


class Escrow(BaseModel):
    account_id: str
    balance: float
    currency: str


class Loan(BaseModel):
    loan_id: str
    client_id: str
    type: str
    status: str
    currency: str
    principal: float
    outstanding_principal: Optional[float] = None
    interest_rate_apr: float
    term_months: int
    amortization: str
    origination_date: str
    first_payment_date: str
    maturity_date: str
    linked_repayment_account_id: str
    payment_schedule: List[ScheduledPayment] = Field(default_factory=list)
    repayment_history: List[Repayment] = Field(default_factory=list)
    collateral: Optional[Collateral] = None
    escrow: Optional[Escrow] = None


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


class Merchant(BaseModel):
    name: str
    mcc: str
    city: str
    country: str


class Fee(BaseModel):
    type: str
    amount: float
    currency: str


class Exchange(BaseModel):
    source_currency: str
    source_amount: float
    target_currency: str
    target_amount: float
    rate: float


class Hold(BaseModel):
    is_hold: bool
    reason: Optional[str] = None
    release_at: Optional[str] = None


class Transaction(BaseModel):
    transaction_id: str
    client_id: str
    account_id: str
    timestamp: str
    type: str
    direction: str
    amount: float
    currency: str
    description: str
    method: str
    status: str
    fees: List[Fee] = Field(default_factory=list)
    merchant: Optional[Merchant] = None
    related_transaction_id: Optional[str] = None
    exchange: Optional[Exchange] = None
    hold: Optional[Hold] = None
    balance_after: Optional[float] = None


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


class BankDB(DB):
    """Database for the bank domain."""

    clients: Dict[str, Client]
    beneficiaries: Dict[str, Beneficiary]
    loans: Dict[str, Loan]
    transactions: Dict[str, Transaction]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_clients": len(self.clients),
            "num_accounts": sum(len(c.accounts) for c in self.clients.values()),
            "num_cards": sum(len(c.cards) for c in self.clients.values()),
            "num_beneficiaries": len(self.beneficiaries),
            "num_loans": len(self.loans),
            "num_transactions": len(self.transactions),
        }


def get_db() -> BankDB:
    return BankDB.load(BANK_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
