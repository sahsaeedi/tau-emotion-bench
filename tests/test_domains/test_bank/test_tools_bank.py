"""Tests for the bank domain, ported from TRACER\'s environment.

These run against the real data/tau_emotion/domains/bank/db.json rather than
a synthetic fixture, so they also assert that the shipped data validates
against the pydantic models. Each test gets its own freshly loaded db.
"""

import pytest

from tau_emotion.domains.bank.data_model import BankDB
from tau_emotion.domains.bank.environment import get_environment
from tau_emotion.domains.bank.tools import BankTools
from tau_emotion.domains.bank.utils import BANK_DB_PATH

# Known-good records from the shipped db.json.
CLIENT_ID = "C59CL8RDW"
CLIENT_EMAIL = "bilal.de vries47474@example.com"
CHECKING = "AYM8PVB59"
SAVINGS = "A36LYJ7D4"
CARD_ID = "KWADVNR69"
BENEFICIARY_ID = "BKNFT7G7K"
LOAN_ID = "LCDDXPE76"

EXPECTED_TOOLS = {
    "add_beneficiary",
    "calculate",
    "find_client_id_by_email",
    "freeze_account",
    "freeze_card",
    "get_account_details",
    "get_beneficiary_details",
    "get_card_details",
    "get_client_details",
    "get_loan_details",
    "get_recent_transactions",
    "initiate_internal_transfer",
    "initiate_transfer_to_beneficiary",
    "list_client_accounts",
    "list_client_beneficiaries",
    "make_loan_payment",
    "search_transactions",
    "think",
    "transfer_to_human_agents",
    "unfreeze_account",
    "unfreeze_card",
    "verify_beneficiary",
}


@pytest.fixture
def db() -> BankDB:
    return BankDB.load(BANK_DB_PATH)


@pytest.fixture
def tools(db: BankDB) -> BankTools:
    return BankTools(db)


def test_shipped_db_validates(db: BankDB):
    stats = db.get_statistics()
    assert stats["num_clients"] > 0
    assert stats["num_accounts"] > 0
    assert stats["num_beneficiaries"] > 0
    assert stats["num_loans"] > 0
    assert stats["num_transactions"] > 0


def test_environment_exposes_expected_tools():
    env = get_environment()
    assert set(env.tools.get_tools()) == EXPECTED_TOOLS
    assert env.domain_name == "bank"
    assert env.policy.strip()


def test_every_tool_has_a_valid_openai_schema():
    env = get_environment()
    for name, tool in env.tools.get_tools().items():
        schema = tool.openai_schema
        assert schema["function"]["name"] == name
        assert schema["function"]["description"].strip(), f"{name} has no description"


def test_solo_mode_is_rejected():
    with pytest.raises(ValueError, match="solo mode"):
        get_environment(solo_mode=True)


# --- lookups ---------------------------------------------------------------


def test_find_client_id_by_email_is_case_insensitive(tools: BankTools):
    assert tools.find_client_id_by_email(CLIENT_EMAIL) == CLIENT_ID
    assert tools.find_client_id_by_email(CLIENT_EMAIL.upper()) == CLIENT_ID
    with pytest.raises(ValueError, match="Client not found"):
        tools.find_client_id_by_email("nobody@example.com")


def test_get_details(tools: BankTools):
    assert tools.get_client_details(CLIENT_ID).client_id == CLIENT_ID
    assert tools.get_account_details(CHECKING).account_id == CHECKING
    assert tools.get_card_details(CARD_ID).card_id == CARD_ID
    assert tools.get_loan_details(LOAN_ID).loan_id == LOAN_ID
    assert (
        tools.get_beneficiary_details(BENEFICIARY_ID).beneficiary_id == BENEFICIARY_ID
    )


def test_accounts_and_cards_are_reached_through_their_client(tools: BankTools):
    """Neither has a top-level collection; both hang off the client."""
    client, account = tools._find_account(CHECKING)
    assert client.client_id == CLIENT_ID
    assert account.account_id == CHECKING

    client, card = tools._find_card(CARD_ID)
    assert client.client_id == CLIENT_ID
    assert card.card_id == CARD_ID


def test_missing_records_raise(tools: BankTools):
    with pytest.raises(ValueError, match="Client not found"):
        tools.get_client_details("NOPE")
    with pytest.raises(ValueError, match="Account not found"):
        tools.get_account_details("NOPE")
    with pytest.raises(ValueError, match="Card not found"):
        tools.get_card_details("NOPE")
    with pytest.raises(ValueError, match="Loan not found"):
        tools.get_loan_details("NOPE")
    with pytest.raises(ValueError, match="Beneficiary not found"):
        tools.get_beneficiary_details("NOPE")


def test_list_client_accounts(tools: BankTools):
    accounts = tools.list_client_accounts(CLIENT_ID)
    assert list(accounts) == sorted(accounts)
    assert set(accounts[CHECKING]) == {"type", "status", "masked", "currency"}
    assert accounts[CHECKING]["status"] == "active"


def test_list_client_beneficiaries(tools: BankTools):
    beneficiaries = tools.list_client_beneficiaries(CLIENT_ID)
    assert BENEFICIARY_ID in beneficiaries
    assert beneficiaries[BENEFICIARY_ID]


def test_list_client_beneficiaries_skips_dangling_ids(tools: BankTools):
    client = tools.get_client_details(CLIENT_ID)
    client.beneficiary_ids.append("DOES_NOT_EXIST")
    listed = tools.list_client_beneficiaries(CLIENT_ID)
    assert "DOES_NOT_EXIST" not in listed


# --- transactions ----------------------------------------------------------


def test_get_recent_transactions_is_newest_first(tools: BankTools):
    transactions = tools.get_recent_transactions(CHECKING, limit=50)
    timestamps = [t.timestamp for t in transactions]
    assert timestamps == sorted(timestamps, reverse=True)
    assert all(t.account_id == CHECKING for t in transactions)
    assert all(t.status in ("posted", "pending") for t in transactions)


def test_get_recent_transactions_respects_limit(tools: BankTools):
    assert tools.get_recent_transactions(CHECKING, limit=0) == []
    assert len(tools.get_recent_transactions(CHECKING, limit=1)) <= 1
    with pytest.raises(ValueError, match="Account not found"):
        tools.get_recent_transactions("NOPE")


def test_search_transactions_filters(tools: BankTools):
    everything = tools.search_transactions(CLIENT_ID, CHECKING)
    assert all(t.account_id == CHECKING for t in everything)

    # an impossible amount window returns nothing
    assert tools.search_transactions(CLIENT_ID, CHECKING, min_amount=1e12) == []
    # an impossible date window returns nothing
    assert tools.search_transactions(CLIENT_ID, CHECKING, start_date="2999-01-01") == []


def test_search_transactions_requires_the_clients_own_account(tools: BankTools):
    with pytest.raises(ValueError, match="Account not found for this client"):
        tools.search_transactions(CLIENT_ID, "NOPE")


# --- freezing --------------------------------------------------------------


def test_freeze_and_unfreeze_account(tools: BankTools):
    assert tools.freeze_account(CHECKING, "lost card").status == "frozen"
    assert tools.unfreeze_account(CHECKING).status == "active"


def test_closed_accounts_cannot_be_frozen(tools: BankTools):
    account = tools.get_account_details(CHECKING)
    account.status = "closed"
    with pytest.raises(ValueError, match="closed and cannot be frozen"):
        tools.freeze_account(CHECKING, "reason")
    with pytest.raises(ValueError, match="closed and cannot be unfrozen"):
        tools.unfreeze_account(CHECKING)


def test_freeze_and_unfreeze_card(tools: BankTools):
    assert tools.freeze_card(CARD_ID, "stolen").status == "blocked"
    # blocking an already-blocked card leaves it unchanged
    assert tools.freeze_card(CARD_ID, "stolen again").status == "blocked"
    assert tools.unfreeze_card(CARD_ID).status == "active"
    assert tools.unfreeze_card(CARD_ID).status == "active"


def test_unmanageable_card_states_are_rejected(tools: BankTools):
    card = tools.get_card_details(CARD_ID)
    card.status = "expired"
    with pytest.raises(ValueError, match="manageable state"):
        tools.freeze_card(CARD_ID, "reason")
    with pytest.raises(ValueError, match="manageable state"):
        tools.unfreeze_card(CARD_ID)


# --- beneficiaries ---------------------------------------------------------


def test_add_beneficiary_starts_pending(tools: BankTools):
    beneficiary = tools.add_beneficiary(
        client_id=CLIENT_ID,
        beneficiary_type="individual",
        bank_name="Test Bank",
        account_number_masked="****1234",
        address1="1 Test St",
        address2="",
        city="Prague",
        state="",
        zip="11000",
        country="CZ",
        allowed_from_account_ids=[CHECKING],
        per_transfer_limit=1000.0,
        daily_limit=2000.0,
        display_name="Test Payee",
    )

    # the system assigns the first free BEN000001-style id
    assert beneficiary.beneficiary_id == "BEN000001"
    assert beneficiary.verification.status == "pending"
    assert beneficiary.status == "active"
    assert "BEN000001" in tools.get_client_details(CLIENT_ID).beneficiary_ids
    assert tools.get_beneficiary_details("BEN000001") is beneficiary


def test_add_beneficiary_ignores_a_caller_supplied_id(tools: BankTools):
    """Older task files pass beneficiary_id; it is accepted but not used."""
    beneficiary = tools.add_beneficiary(
        client_id=CLIENT_ID,
        beneficiary_id="CALLER-CHOSEN",
        beneficiary_type="individual",
        bank_name="Test Bank",
        account_number_masked="****1234",
        address1="1 Test St",
        address2="",
        city="Prague",
        state="",
        zip="11000",
        country="CZ",
        allowed_from_account_ids=[CHECKING],
        per_transfer_limit=1000.0,
        daily_limit=2000.0,
    )
    assert beneficiary.beneficiary_id == "BEN000001"
    assert "CALLER-CHOSEN" not in tools.db.beneficiaries


@pytest.mark.parametrize("address2", ["", "N/A", "n/a", "none", "-", None])
def test_add_beneficiary_stores_a_missing_second_address_line_as_empty(
    tools: BankTools, address2
):
    kwargs = {} if address2 is None else {"address2": address2}
    beneficiary = tools.add_beneficiary(
        client_id=CLIENT_ID,
        beneficiary_type="individual",
        bank_name="Test Bank",
        account_number_masked="****1111",
        address1="1 Main St",
        city="Springfield",
        state="IL",
        zip="62701",
        country="USA",
        allowed_from_account_ids=[CHECKING],
        per_transfer_limit=100.0,
        daily_limit=200.0,
        display_name="Test Person",
        **kwargs,
    )
    assert beneficiary.address.address2 == ""
    schema = tools.get_tools()["add_beneficiary"].openai_schema["function"][
        "parameters"
    ]
    assert "address2" not in schema.get("required", [])


def test_add_beneficiary_rejects_foreign_accounts(tools: BankTools):
    with pytest.raises(ValueError, match="does not belong to client"):
        tools.add_beneficiary(
            client_id=CLIENT_ID,
            beneficiary_type="individual",
            bank_name="Test Bank",
            account_number_masked="****1234",
            address1="1 Test St",
            address2="",
            city="Prague",
            state="",
            zip="11000",
            country="CZ",
            allowed_from_account_ids=["NOT_MY_ACCOUNT"],
            per_transfer_limit=1000.0,
            daily_limit=2000.0,
        )


def test_verify_beneficiary(tools: BankTools):
    beneficiary = tools.get_beneficiary_details(BENEFICIARY_ID)
    beneficiary.verification.status = "pending"
    beneficiary.verification.verified_at = None

    verified = tools.verify_beneficiary(
        CLIENT_ID, BENEFICIARY_ID, method="micro_deposit"
    )

    assert verified.verification.status == "verified"
    assert verified.verification.method == "micro_deposit"
    assert (
        verified.verification.verified_at == "2025-10-02T12:00:00Z"
    )  # the toolkit's fixed clock


def test_verify_beneficiary_requires_ownership(tools: BankTools):
    other = next(b for b in tools.db.beneficiaries.values() if b.client_id != CLIENT_ID)
    with pytest.raises(ValueError, match="not owned by this client"):
        tools.verify_beneficiary(CLIENT_ID, other.beneficiary_id)


# --- money movement --------------------------------------------------------


def test_initiate_internal_transfer(tools: BankTools):
    source = tools.get_account_details(CHECKING)
    target = tools.get_account_details(SAVINGS)
    source_before = source.balance.available
    target_before = target.balance.available

    debit, credit = tools.initiate_internal_transfer(
        CLIENT_ID, CHECKING, SAVINGS, 1000.0
    )

    assert source.balance.available == round(source_before - 1000.0, 2)
    assert target.balance.available == round(target_before + 1000.0, 2)
    assert debit.direction == "debit" and credit.direction == "credit"
    assert debit.related_transaction_id == credit.transaction_id
    assert credit.related_transaction_id == debit.transaction_id
    # first free TXN000001-style ids, so replays assign the same ones
    assert (debit.transaction_id, credit.transaction_id) == ("TXN000001", "TXN000002")
    assert tools.db.transactions[debit.transaction_id] is debit


def test_initiate_internal_transfer_validates(tools: BankTools):
    with pytest.raises(ValueError, match="greater than zero"):
        tools.initiate_internal_transfer(CLIENT_ID, CHECKING, SAVINGS, 0)
    with pytest.raises(ValueError, match="Insufficient available balance"):
        tools.initiate_internal_transfer(CLIENT_ID, CHECKING, SAVINGS, 1e12)
    with pytest.raises(ValueError, match="must belong to the same client"):
        tools.initiate_internal_transfer(CLIENT_ID, CHECKING, "NOPE", 1.0)


def test_initiate_internal_transfer_requires_active_accounts(tools: BankTools):
    tools.freeze_account(CHECKING, "reason")
    with pytest.raises(ValueError, match="Source account is not active"):
        tools.initiate_internal_transfer(CLIENT_ID, CHECKING, SAVINGS, 1.0)


def test_initiate_transfer_to_beneficiary(tools: BankTools):
    account = tools.get_account_details(CHECKING)
    before = account.balance.available

    transaction = tools.initiate_transfer_to_beneficiary(
        CLIENT_ID, CHECKING, BENEFICIARY_ID, 500.0
    )

    assert account.balance.available == round(before - 500.0, 2)
    assert transaction.direction == "debit"
    assert transaction.method == "ACH"
    assert transaction.balance_after == account.balance.current


def test_transfer_to_beneficiary_requires_verification(tools: BankTools):
    beneficiary = tools.get_beneficiary_details(BENEFICIARY_ID)
    beneficiary.verification.status = "pending"
    with pytest.raises(ValueError, match="must be verified"):
        tools.initiate_transfer_to_beneficiary(
            CLIENT_ID, CHECKING, BENEFICIARY_ID, 10.0
        )


def test_transfer_to_beneficiary_enforces_limits_and_authorisation(tools: BankTools):
    beneficiary = tools.get_beneficiary_details(BENEFICIARY_ID)
    with pytest.raises(ValueError, match="exceeds per-transfer limit"):
        tools.initiate_transfer_to_beneficiary(
            CLIENT_ID,
            CHECKING,
            BENEFICIARY_ID,
            beneficiary.transfer_limits.per_transfer_limit + 1,
        )

    beneficiary.allowed_from_account_ids = []
    with pytest.raises(ValueError, match="not authorized"):
        tools.initiate_transfer_to_beneficiary(
            CLIENT_ID, CHECKING, BENEFICIARY_ID, 10.0
        )


def test_make_loan_payment_records_repayment(tools: BankTools):
    account = tools.get_account_details(CHECKING)
    loan = tools.get_loan_details(LOAN_ID)
    before = account.balance.available
    repayments_before = len(loan.repayment_history)

    transaction = tools.make_loan_payment(CLIENT_ID, LOAN_ID, CHECKING, 2500.0)

    assert account.balance.available == round(before - 2500.0, 2)
    assert transaction.type == "payment"
    assert len(loan.repayment_history) == repayments_before + 1
    repayment = loan.repayment_history[-1]
    assert repayment.transaction_id == transaction.transaction_id
    assert repayment.principal_component == 2500.0
    assert repayment.interest_component == 0.0


def test_make_loan_payment_requires_ownership(tools: BankTools):
    other_loan = next(
        loan for loan in tools.db.loans.values() if loan.client_id != CLIENT_ID
    )
    with pytest.raises(ValueError, match="does not belong to the client"):
        tools.make_loan_payment(CLIENT_ID, other_loan.loan_id, CHECKING, 1.0)


def test_memo_is_hidden_and_ignored(tools: BankTools):
    # The agent never sees `description`; a caller-supplied memo (older task
    # files still pass one) is ignored and the default memo is stored.
    schemas = {name: t.openai_schema for name, t in tools.get_tools().items()}
    for name in (
        "initiate_internal_transfer",
        "initiate_transfer_to_beneficiary",
        "make_loan_payment",
    ):
        assert (
            "description" not in schemas[name]["function"]["parameters"]["properties"]
        )
    debit, credit = tools.initiate_internal_transfer(
        CLIENT_ID, CHECKING, SAVINGS, 10.0, description="my own memo"
    )
    assert debit.description == f"Internal transfer to {SAVINGS}"
    assert credit.description == f"Internal transfer from {CHECKING}"
    payment = tools.make_loan_payment(
        CLIENT_ID, LOAN_ID, CHECKING, 5.0, description="memo"
    )
    assert payment.description == f"Loan payment {LOAN_ID}"


def test_whole_amounts_are_stored_as_floats(tools: BankTools):
    debit, _ = tools.initiate_internal_transfer(CLIENT_ID, CHECKING, SAVINGS, 10)
    assert isinstance(debit.amount, float)


def test_timestamps_are_deterministic(tools: BankTools):
    """TRACER uses datetime.utcnow(); a fixed clock keeps runs reproducible."""
    first = tools.make_loan_payment(CLIENT_ID, LOAN_ID, CHECKING, 1.0)
    second = tools.make_loan_payment(CLIENT_ID, LOAN_ID, CHECKING, 1.0)
    assert first.timestamp == second.timestamp
    assert first.transaction_id != second.transaction_id


# --- utility ---------------------------------------------------------------


def test_calculate(tools: BankTools):
    assert tools.calculate("85000.50 - 1000") == "84000.5"
    with pytest.raises(ValueError, match="Invalid characters"):
        tools.calculate("import os")


def test_transfer_to_human_agents(tools: BankTools):
    assert tools.transfer_to_human_agents("out of scope") == "Transfer successful"
