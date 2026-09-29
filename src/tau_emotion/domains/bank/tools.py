"""Toolkit for the bank domain, ported from TRACER's environment
(tracer/tracer/envs/bank/).

21 tools mirroring TRACER's `ALL_TOOLS`. Conversion rules from TRACER's tools:

- `data["clients"]` → `self.db.clients`.
- `return json.dumps(x)` → return the pydantic record.
- `return "Error: ..."` → `raise ValueError("...")`.
- Free-function `invoke(data, ...)` → instance method with `@is_tool(...)`.

Accounts and cards have no top-level collection: they live inside the client
who holds them, so `_find_account` and `_find_card` scan clients, as TRACER's
tools do.

Generated values follow TRACER's tools exactly, so the ground-truth replay and
the agent's run store identical records: a fixed clock, `TXN000001`-style
transaction ids, and `BEN000001`-style beneficiary ids assigned by the system.
"""

from __future__ import annotations

import inspect
from typing import Dict, List, Literal, Optional, Tuple

from tau_emotion.domains.bank.data_model import (
    Account,
    BankDB,
    BankDetails,
    Beneficiary,
    BeneficiaryName,
    Card,
    Client,
    Loan,
    Repayment,
    Transaction,
    TransferLimits,
    Verification,
)
from tau_emotion.domains.bank.data_model import Address as BankAddress
from tau_emotion.environment.toolkit import ToolKitBase, ToolType, is_tool


def _hide_params(*names: str):
    """Hide parameters from the agent's tool schema but keep accepting them.

    The schema is built from the signature, so dropping a name from
    `__signature__` hides it, while the function still accepts it and older
    task files that pass it still replay.
    """

    def decorator(func):
        # eval_str: this module uses `from __future__ import annotations`, so
        # without it the kept parameters' annotations stay strings and the
        # schema loses what they say (an enum becomes unresolvable).
        try:
            sig = inspect.signature(func, eval_str=True)
        except Exception:
            sig = inspect.signature(func)
        func.__signature__ = sig.replace(
            parameters=[p for p in sig.parameters.values() if p.name not in names]
        )
        return func

    return decorator


# Fixed clock, matching TRACER's tools, so replays store identical timestamps.
NOW = "2025-10-02T12:00:00Z"
MANAGEABLE_CARD_STATUSES = ("active", "blocked")


# TRACER declares these as enums in its tool schemas, so the agent is told the
# allowed values; the strings are stored in the database verbatim.
VerificationMethod = Literal["micro_deposits", "document", "instant"]


class BankTools(ToolKitBase):
    """All the tools for the bank domain."""

    db: BankDB

    def __init__(self, db: BankDB) -> None:
        super().__init__(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_client(self, client_id: str) -> Client:
        client = self.db.clients.get(client_id)
        if client is None:
            raise ValueError("Client not found")
        return client

    def _find_account(self, account_id: str) -> Tuple[Client, Account]:
        """Resolve an account id to its holder and the account itself."""
        for client in self.db.clients.values():
            if account_id in client.accounts:
                return client, client.accounts[account_id]
        raise ValueError("Account not found")

    def _find_card(self, card_id: str) -> Tuple[Client, Card]:
        """Resolve a card id to its holder and the card itself."""
        for client in self.db.clients.values():
            if card_id in client.cards:
                return client, client.cards[card_id]
        raise ValueError("Card not found")

    def _get_loan(self, loan_id: str) -> Loan:
        loan = self.db.loans.get(loan_id)
        if loan is None:
            raise ValueError("Loan not found")
        return loan

    def _get_beneficiary(self, beneficiary_id: str) -> Beneficiary:
        beneficiary = self.db.beneficiaries.get(beneficiary_id)
        if beneficiary is None:
            raise ValueError("Beneficiary not found")
        return beneficiary

    def _client_account(self, client: Client, account_id: str) -> Account:
        account = client.accounts.get(account_id)
        if account is None:
            raise ValueError("Source account must belong to the client")
        return account

    def _new_transaction_id(self) -> str:
        """First free id of the form TXN000001, as TRACER assigns it."""
        n = 1
        while f"TXN{n:06d}" in self.db.transactions:
            n += 1
        return f"TXN{n:06d}"

    def _new_beneficiary_id(self) -> str:
        """First free id of the form BEN000001, as TRACER assigns it."""
        n = 1
        while f"BEN{n:06d}" in self.db.beneficiaries:
            n += 1
        return f"BEN{n:06d}"

    @staticmethod
    def _debit(account: Account, amount: float) -> None:
        account.balance.available = round(account.balance.available - amount, 2)
        account.balance.current = round(account.balance.current - amount, 2)

    @staticmethod
    def _credit(account: Account, amount: float) -> None:
        account.balance.available = round(account.balance.available + amount, 2)
        account.balance.current = round(account.balance.current + amount, 2)

    @staticmethod
    def _require_positive(amount: float) -> None:
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")

    @staticmethod
    def _require_sufficient_funds(account: Account, amount: float) -> None:
        if account.balance.available < amount:
            raise ValueError("Insufficient available balance")

    @staticmethod
    def _require_active(account: Account, label: str = "Source") -> None:
        if account.status != "active":
            raise ValueError(f"{label} account is not active")

    def _record_transaction(
        self,
        client_id: str,
        account: Account,
        account_id: str,
        *,
        amount: float,
        type: str,
        direction: str,
        description: str,
        method: str,
        related_transaction_id: Optional[str] = None,
    ) -> Transaction:
        """Create, store and return a posted transaction on an account."""
        transaction = Transaction(
            transaction_id=self._new_transaction_id(),
            client_id=client_id,
            account_id=account_id,
            timestamp=NOW,
            type=type,
            direction=direction,
            amount=round(amount, 2),
            currency=account.currency,
            description=description,
            method=method,
            status="posted",
            merchant=None,
            related_transaction_id=related_transaction_id,
            exchange=None,
            fees=[],
            hold=None,
            balance_after=account.balance.current,
        )
        self.db.transactions[transaction.transaction_id] = transaction
        return transaction

    # ------------------------------------------------------------------
    # Client and account lookups
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_client_details(self, client_id: str) -> Client:
        """
        Get the details of a client.

        Args:
            client_id: The client id.

        Returns:
            The client record, including their accounts and cards.

        Raises:
            ValueError: If the client is not found.
        """
        return self._get_client(client_id)

    @is_tool(ToolType.READ)
    def find_client_id_by_email(self, email: str) -> str:
        """
        Find a client id by email address.

        Args:
            email: The client's email address.

        Returns:
            The matching client id.

        Raises:
            ValueError: If no client has that email.
        """
        email_lower = email.lower()
        for client_id, client in self.db.clients.items():
            if client.contact.email.lower() == email_lower:
                return client_id
        raise ValueError("Client not found")

    @is_tool(ToolType.READ)
    def list_client_accounts(self, client_id: str) -> Dict[str, dict]:
        """
        List a client's accounts in summary form.

        Args:
            client_id: The client id.

        Returns:
            A mapping of account id to {type, status, masked, currency},
            sorted by account id.

        Raises:
            ValueError: If the client is not found.
        """
        client = self._get_client(client_id)
        summary = {
            account_id: {
                "type": account.type,
                "status": account.status,
                "masked": account.account_number_masked,
                "currency": account.currency,
            }
            for account_id, account in client.accounts.items()
        }
        return dict(sorted(summary.items()))

    @is_tool(ToolType.READ)
    def get_account_details(self, account_id: str) -> Account:
        """
        Get the details of an account by account id.

        Args:
            account_id: The account id.

        Returns:
            The account record, including balances and features.

        Raises:
            ValueError: If the account is not found.
        """
        _, account = self._find_account(account_id)
        return account

    @is_tool(ToolType.READ)
    def get_card_details(self, card_id: str) -> Card:
        """
        Get the details of a card by card id.

        Args:
            card_id: The card id.

        Returns:
            The card record, including its status and limits.

        Raises:
            ValueError: If the card is not found.
        """
        _, card = self._find_card(card_id)
        return card

    @is_tool(ToolType.READ)
    def get_loan_details(self, loan_id: str) -> Loan:
        """
        Get the details of a loan.

        Args:
            loan_id: The loan id.

        Returns:
            The loan record, including its schedule and repayment history.

        Raises:
            ValueError: If the loan is not found.
        """
        return self._get_loan(loan_id)

    @is_tool(ToolType.READ)
    def get_beneficiary_details(self, beneficiary_id: str) -> Beneficiary:
        """
        Get the details of a beneficiary.

        Args:
            beneficiary_id: The beneficiary id.

        Returns:
            The beneficiary record, including verification state and limits.

        Raises:
            ValueError: If the beneficiary is not found.
        """
        return self._get_beneficiary(beneficiary_id)

    @is_tool(ToolType.READ)
    def list_client_beneficiaries(self, client_id: str) -> Dict[str, str]:
        """
        List a client's beneficiaries by display name.

        Args:
            client_id: The client id.

        Returns:
            A mapping of beneficiary id to a display name, sorted by id.
            Beneficiary ids the client references but which no longer exist
            are skipped.

        Raises:
            ValueError: If the client is not found.
        """
        client = self._get_client(client_id)
        result: Dict[str, str] = {}
        for beneficiary_id in client.beneficiary_ids:
            beneficiary = self.db.beneficiaries.get(beneficiary_id)
            if beneficiary is None:
                continue
            name = beneficiary.name
            display = (
                name.display_name
                or name.business_name
                or " ".join(filter(None, [name.first_name, name.last_name]))
                or "Unnamed Beneficiary"
            )
            result[beneficiary_id] = display
        return dict(sorted(result.items()))

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    @is_tool(ToolType.READ)
    def get_recent_transactions(
        self, account_id: str, limit: int = 10
    ) -> List[Transaction]:
        """
        Get the most recent posted or pending transactions on an account.

        Args:
            account_id: The account id.
            limit: The maximum number to return, newest first.

        Returns:
            The matching transactions, newest first.

        Raises:
            ValueError: If the account is not found.
        """
        self._find_account(account_id)
        transactions = [
            t
            for t in self.db.transactions.values()
            if t.account_id == account_id and t.status in ("posted", "pending")
        ]
        transactions.sort(key=lambda t: t.timestamp, reverse=True)
        return transactions[: max(0, limit)]

    @is_tool(ToolType.READ)
    def search_transactions(
        self,
        client_id: str,
        account_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        transaction_type: Optional[str] = None,
        status: Optional[str] = None,
        merchant_name_contains: Optional[str] = None,
    ) -> List[Transaction]:
        """
        Search an account's transactions with optional filters.

        Args:
            client_id: The client who holds the account.
            account_id: The account to search.
            start_date: Optional inclusive lower bound on the timestamp.
            end_date: Optional inclusive upper bound on the timestamp.
            min_amount: Optional minimum amount.
            max_amount: Optional maximum amount.
            transaction_type: Optional transaction type filter.
            status: Optional status filter.
            merchant_name_contains: Optional case-insensitive merchant substring.

        Returns:
            The matching transactions, newest first.

        Raises:
            ValueError: If the client is not found, or the account does not
                belong to them.
        """
        client = self._get_client(client_id)
        if account_id not in client.accounts:
            raise ValueError("Account not found for this client")

        needle = merchant_name_contains.lower() if merchant_name_contains else None
        results = []
        for transaction in self.db.transactions.values():
            if transaction.account_id != account_id:
                continue
            if start_date and transaction.timestamp < start_date:
                continue
            if end_date and transaction.timestamp > end_date:
                continue
            if min_amount is not None and transaction.amount < min_amount:
                continue
            if max_amount is not None and transaction.amount > max_amount:
                continue
            if transaction_type and transaction.type != transaction_type:
                continue
            if status and transaction.status != status:
                continue
            if needle is not None:
                merchant_name = (
                    transaction.merchant.name if transaction.merchant else ""
                )
                if needle not in merchant_name.lower():
                    continue
            results.append(transaction)

        results.sort(key=lambda t: t.timestamp, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Account and card status
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def freeze_account(self, account_id: str, reason: str) -> Account:
        """
        Freeze an account.

        The agent must explain the effect and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            account_id: The account id.
            reason: Why the account is being frozen.

        Returns:
            The updated account.

        Raises:
            ValueError: If the account is not found or is closed.
        """
        _, account = self._find_account(account_id)
        if account.status == "closed":
            raise ValueError("Account is closed and cannot be frozen")
        account.status = "frozen"
        return account

    @is_tool(ToolType.WRITE)
    def unfreeze_account(self, account_id: str) -> Account:
        """
        Unfreeze an account, returning it to active.

        The agent must explain the effect and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            account_id: The account id.

        Returns:
            The updated account.

        Raises:
            ValueError: If the account is not found or is closed.
        """
        _, account = self._find_account(account_id)
        if account.status == "closed":
            raise ValueError("Account is closed and cannot be unfrozen")
        account.status = "active"
        return account

    @is_tool(ToolType.WRITE)
    def freeze_card(self, card_id: str, reason: str) -> Card:
        """
        Block a card. A card that is already blocked is returned unchanged.

        The agent must explain the effect and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            card_id: The card id.
            reason: Why the card is being blocked.

        Returns:
            The updated card.

        Raises:
            ValueError: If the card is not found, or is not active or blocked.
        """
        _, card = self._find_card(card_id)
        if card.status not in MANAGEABLE_CARD_STATUSES:
            raise ValueError("Card not in a manageable state")
        card.status = "blocked"
        return card

    @is_tool(ToolType.WRITE)
    def unfreeze_card(self, card_id: str) -> Card:
        """
        Unblock a card. A card that is already active is returned unchanged.

        The agent must explain the effect and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            card_id: The card id.

        Returns:
            The updated card.

        Raises:
            ValueError: If the card is not found, or is not active or blocked.
        """
        _, card = self._find_card(card_id)
        if card.status not in MANAGEABLE_CARD_STATUSES:
            raise ValueError("Card not in a manageable state")
        card.status = "active"
        return card

    # ------------------------------------------------------------------
    # Beneficiaries
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    def add_beneficiary(
        self,
        client_id: str,
        beneficiary_type: Literal["individual", "business"],
        bank_name: str,
        account_number_masked: str,
        address1: str,
        city: str,
        state: str,
        zip: str,
        country: str,
        allowed_from_account_ids: List[str],
        per_transfer_limit: float,
        daily_limit: float,
        address2: Optional[str] = None,
        display_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        business_name: Optional[str] = None,
        routing_number: Optional[str] = None,
        iban: Optional[str] = None,
        swift_bic: Optional[str] = None,
        verification_method: VerificationMethod = "document",
        beneficiary_id: Optional[str] = None,
    ) -> Beneficiary:
        """
        Add a beneficiary for a client. It starts unverified and cannot receive
        transfers until it is verified. The system assigns the beneficiary_id and
        returns it in the response.

        The agent must list the details and ask for explicit user confirmation
        (yes/no) before calling.

        Args:
            client_id: The client the beneficiary belongs to.
            beneficiary_type: The beneficiary type, e.g. 'individual' or 'business'.
            bank_name: The beneficiary's bank.
            account_number_masked: Their masked account number.
            address1: Primary address line.
            address2: Secondary address line (apartment, suite). Leave empty if
                there is none.
            city: City.
            state: State or province.
            zip: Postal or ZIP code.
            country: Country.
            allowed_from_account_ids: The client accounts allowed to send to them.
                Every id must belong to the client.
            per_transfer_limit: Maximum amount for a single transfer.
            daily_limit: Maximum total per day.
            display_name: Optional display name.
            first_name: Optional first name, for an individual.
            last_name: Optional last name, for an individual.
            business_name: Optional business name, for a business.
            routing_number: Optional routing number.
            iban: Optional IBAN.
            swift_bic: Optional SWIFT/BIC code.
            verification_method: How the beneficiary will be verified.
            beneficiary_id: Ignored; the id is assigned by the system. Accepted
                so older task files still replay.

        Returns:
            The newly created beneficiary, with verification status 'pending'.

        Raises:
            ValueError: If the client is not found, or an allowed account does
                not belong to them.
        """
        # No second line may arrive as "", a placeholder, or not at all; store all of them as "".
        if address2 is None or address2.strip().lower() in (
            "",
            "n/a",
            "na",
            "none",
            "-",
        ):
            address2 = ""
        client = self._get_client(client_id)
        for account_id in allowed_from_account_ids:
            if account_id not in client.accounts:
                raise ValueError(
                    f"Allowed account {account_id} does not belong to client"
                )

        beneficiary_id = self._new_beneficiary_id()
        beneficiary = Beneficiary(
            beneficiary_id=beneficiary_id,
            client_id=client_id,
            name=BeneficiaryName(
                display_name=display_name,
                first_name=first_name,
                last_name=last_name,
                business_name=business_name,
            ),
            type=beneficiary_type,
            bank_details=BankDetails(
                bank_name=bank_name,
                account_number_masked=account_number_masked,
                routing_number=routing_number,
                iban=iban,
                swift_bic=swift_bic,
            ),
            address=BankAddress(
                address1=address1,
                address2=address2,
                city=city,
                state=state,
                zip=zip,
                country=country,
            ),
            allowed_from_account_ids=allowed_from_account_ids,
            transfer_limits=TransferLimits(
                per_transfer_limit=per_transfer_limit, daily_limit=daily_limit
            ),
            verification=Verification(
                status="pending", method=verification_method, verified_at=None
            ),
            status="active",
            created_at=NOW,
            notes=None,
        )

        self.db.beneficiaries[beneficiary_id] = beneficiary
        if beneficiary_id not in client.beneficiary_ids:
            client.beneficiary_ids.append(beneficiary_id)
        return beneficiary

    @is_tool(ToolType.WRITE)
    def verify_beneficiary(
        self,
        client_id: str,
        beneficiary_id: str,
        method: VerificationMethod = "document",
    ) -> Beneficiary:
        """
        Mark a client's beneficiary as verified, which allows transfers to it.

        The agent must explain the effect and ask for explicit user
        confirmation (yes/no) before calling.

        Args:
            client_id: The client who owns the beneficiary.
            beneficiary_id: The beneficiary to verify.
            method: How verification was performed.

        Returns:
            The updated beneficiary.

        Raises:
            ValueError: If the client or beneficiary is not found, or the
                beneficiary is not owned by this client.
        """
        client = self._get_client(client_id)
        if beneficiary_id not in client.beneficiary_ids:
            raise ValueError("Beneficiary not owned by this client")
        beneficiary = self._get_beneficiary(beneficiary_id)

        beneficiary.verification.status = "verified"
        beneficiary.verification.method = method
        beneficiary.verification.verified_at = NOW
        return beneficiary

    # ------------------------------------------------------------------
    # Money movement
    # ------------------------------------------------------------------

    @is_tool(ToolType.WRITE)
    @_hide_params("description")
    def initiate_internal_transfer(
        self,
        client_id: str,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        description: Optional[
            str
        ] = None,  # ignored: the memo is always the default; accepted for older task files
    ) -> List[Transaction]:
        """
        Move money between two accounts held by the same client.

        Both accounts must be active and share a currency, and the source
        cannot be a credit account. The agent must list the details and ask for
        explicit user confirmation (yes/no) before calling.

        Args:
            client_id: The client who holds both accounts.
            from_account_id: The account to debit.
            to_account_id: The account to credit.
            amount: The amount to move. Must be greater than zero.

        Returns:
            The two posted transactions, debit first, linked to each other.

        Raises:
            ValueError: If the amount is not positive, the client is not found,
                either account does not belong to them or is not active, the
                source is a credit account, the currencies differ, or there are
                insufficient funds.
        """
        self._require_positive(amount)
        client = self._get_client(client_id)
        if (
            from_account_id not in client.accounts
            or to_account_id not in client.accounts
        ):
            raise ValueError("Both accounts must belong to the same client")

        source = client.accounts[from_account_id]
        target = client.accounts[to_account_id]

        self._require_active(source, "Source")
        self._require_active(target, "Destination")
        if source.type == "credit":
            raise ValueError("Transfers from a credit account are not supported")
        if source.currency != target.currency:
            raise ValueError("Cross-currency internal transfers are not supported")
        self._require_sufficient_funds(source, amount)

        self._debit(source, amount)
        self._credit(target, amount)

        debit = self._record_transaction(
            client_id,
            source,
            from_account_id,
            amount=amount,
            type="transfer",
            direction="debit",
            description=f"Internal transfer to {to_account_id}",
            method="Internal",
        )
        credit = self._record_transaction(
            client_id,
            target,
            to_account_id,
            amount=amount,
            type="transfer",
            direction="credit",
            description=f"Internal transfer from {from_account_id}",
            method="Internal",
            related_transaction_id=debit.transaction_id,
        )
        debit.related_transaction_id = credit.transaction_id
        return [debit, credit]

    @is_tool(ToolType.WRITE)
    @_hide_params("description")
    def initiate_transfer_to_beneficiary(
        self,
        client_id: str,
        from_account_id: str,
        beneficiary_id: str,
        amount: float,
        method: Literal["ACH", "Wire"] = "ACH",
        description: Optional[
            str
        ] = None,  # ignored: the memo is always the default; accepted for older task files
    ) -> Transaction:
        """
        Send money from a client's account to one of their verified beneficiaries.

        The agent must list the details and ask for explicit user confirmation
        (yes/no) before calling.

        Args:
            client_id: The client sending the money.
            from_account_id: The account to debit. Must belong to the client
                and be authorised for this beneficiary.
            beneficiary_id: The beneficiary to pay.
            amount: The amount to send. Must be greater than zero.
            method: The transfer rail, e.g. 'ACH' or 'Wire'.

        Returns:
            The posted debit transaction.

        Raises:
            ValueError: If the amount is not positive, the client, account or
                beneficiary is not found or not owned, the account is inactive
                or unauthorised, the beneficiary is inactive or unverified, the
                amount exceeds the per-transfer limit, or there are
                insufficient funds.
        """
        self._require_positive(amount)
        client = self._get_client(client_id)
        account = self._client_account(client, from_account_id)
        self._require_active(account, "Source")

        if beneficiary_id not in client.beneficiary_ids:
            raise ValueError("Beneficiary not owned by this client")
        beneficiary = self._get_beneficiary(beneficiary_id)

        if beneficiary.status != "active":
            raise ValueError("Beneficiary is not active")
        if beneficiary.verification.status != "verified":
            raise ValueError("Beneficiary must be verified before transfers")
        if from_account_id not in beneficiary.allowed_from_account_ids:
            raise ValueError(
                "This account is not authorized for transfers to the beneficiary"
            )
        if amount > beneficiary.transfer_limits.per_transfer_limit:
            raise ValueError("Amount exceeds per-transfer limit for beneficiary")
        self._require_sufficient_funds(account, amount)

        self._debit(account, amount)
        display_name = beneficiary.name.display_name or beneficiary_id
        return self._record_transaction(
            client_id,
            account,
            from_account_id,
            amount=amount,
            type="transfer",
            direction="debit",
            description=f"Transfer to beneficiary {display_name}",
            method=method,
        )

    @is_tool(ToolType.WRITE)
    @_hide_params("description")
    def make_loan_payment(
        self,
        client_id: str,
        loan_id: str,
        from_account_id: str,
        amount: float,
        method: str = "Internal",
        description: Optional[
            str
        ] = None,  # ignored: the memo is always the default; accepted for older task files
    ) -> Transaction:
        """
        Pay a loan from one of the client's accounts.

        The whole amount is recorded against principal; interest and fee
        components are zero. The agent must list the details and ask for
        explicit user confirmation (yes/no) before calling.

        Args:
            client_id: The client making the payment.
            loan_id: The loan to pay.
            from_account_id: The account to debit. Must belong to the client.
            amount: The amount to pay. Must be greater than zero.
            method: The payment method.

        Returns:
            The posted debit transaction.

        Raises:
            ValueError: If the amount is not positive, the client, account or
                loan is not found, the loan does not belong to the client, the
                account is not active, or there are insufficient funds.
        """
        self._require_positive(amount)
        client = self._get_client(client_id)
        account = self._client_account(client, from_account_id)

        loan = self._get_loan(loan_id)
        if loan.client_id != client_id:
            raise ValueError("Loan does not belong to the client")

        self._require_active(account, "Source")
        self._require_sufficient_funds(account, amount)

        self._debit(account, amount)
        transaction = self._record_transaction(
            client_id,
            account,
            from_account_id,
            amount=amount,
            type="payment",
            direction="debit",
            description=f"Loan payment {loan_id}",
            method=method,
        )

        loan.repayment_history.append(
            Repayment(
                transaction_id=transaction.transaction_id,
                posted_at=transaction.timestamp,
                amount=transaction.amount,
                currency=transaction.currency,
                method=transaction.method,
                principal_component=transaction.amount,
                interest_component=0.0,
                fees_component=0.0,
            )
        )
        return transaction

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @is_tool(ToolType.THINK)
    def think(self, thought: str) -> str:
        """Use the tool to think about something. It will not obtain new
        information or change the database, but just append the thought to
        the log. Use it when complex reasoning or some cache memory is needed.

        Args:
            thought: A thought to think about.

        Returns:
            An empty string.
        """
        return ""

    @is_tool(ToolType.GENERIC)
    def calculate(self, expression: str) -> str:
        """
        Calculate the result of a mathematical expression.

        Args:
            expression: The mathematical expression to calculate, such as '2 + 2'. The expression can contain numbers, operators (+, -, *, /), parentheses, and spaces.

        Returns:
            The result of the mathematical expression.

        Raises:
            ValueError: If the expression is invalid.
        """
        if not all(char in "0123456789+-*/(). " for char in expression):
            raise ValueError("Invalid characters in expression")
        return str(round(float(eval(expression, {"__builtins__": None}, {})), 2))

    @is_tool(ToolType.GENERIC)
    def transfer_to_human_agents(self, summary: str) -> str:
        """
        Transfer the user to a human agent, with a summary of the user's issue.
        Only transfer if
         -  the user explicitly asks for a human agent
         -  given the policy and the available tools, you cannot solve the user's issue.

        Args:
            summary: A summary of the user's issue.

        Returns:
            A message indicating the user has been transferred to a human agent.
        """
        return "Transfer successful"
