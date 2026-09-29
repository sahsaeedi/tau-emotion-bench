import json
import random
from typing import Any, Dict, List, Optional

from tracer.envs.tool import Tool

# Max number of clients to return per call (paginated batch)
_MAX_CLIENTS = 5

# Call counter: each invoke returns the "next" batch so subsequent calls get different clients
_call_counter = 0


def _has_account_status(client: Dict[str, Any], status: str) -> bool:
    return any(a.get("status") == status for a in client.get("accounts", {}).values())


def _has_min_active_accounts_same_currency(client: Dict[str, Any], n: int) -> bool:
    by_currency: Dict[str, int] = {}
    for a in client.get("accounts", {}).values():
        if a.get("status") == "active":
            cur = a.get("currency")
            by_currency[cur] = by_currency.get(cur, 0) + 1
    return any(count >= n for count in by_currency.values())


def _has_card_status(client: Dict[str, Any], status: str) -> bool:
    return any(c.get("status") == status for c in client.get("cards", {}).values())


def _client_beneficiaries(
    client: Dict[str, Any], beneficiaries: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [
        beneficiaries[bid]
        for bid in client.get("beneficiary_ids", [])
        if bid in beneficiaries
    ]


def _has_beneficiary_status(benefs: List[Dict[str, Any]], status: str) -> bool:
    return any(b.get("status") == status for b in benefs)


def _has_beneficiary_verification(benefs: List[Dict[str, Any]], status: str) -> bool:
    return any(b.get("verification", {}).get("status") == status for b in benefs)


def _client_loans(
    client: Dict[str, Any], loans: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [loans[lid] for lid in client.get("loan_ids", []) if lid in loans]


def _has_loan_type(client_loans: List[Dict[str, Any]], loan_type: str) -> bool:
    return any(loan.get("type") == loan_type for loan in client_loans)


def _has_loan_status(client_loans: List[Dict[str, Any]], status: str) -> bool:
    return any(loan.get("status") == status for loan in client_loans)


def _has_loan_payment_status(client_loans: List[Dict[str, Any]], status: str) -> bool:
    for loan in client_loans:
        for payment in loan.get("payment_schedule", []):
            if payment.get("status") == status:
                return True
    return False


def _has_transaction_status(
    client_id: str, transactions: Dict[str, Any], status: str
) -> bool:
    return any(
        t.get("client_id") == client_id and t.get("status") == status
        for t in transactions.values()
    )


def _has_transaction_type(
    client_id: str, transactions: Dict[str, Any], txn_type: str
) -> bool:
    return any(
        t.get("client_id") == client_id and t.get("type") == txn_type
        for t in transactions.values()
    )


class GetClientCandidates(Tool):
    @staticmethod
    def invoke(
        data: Dict[str, Any],
        account_status: Optional[str] = None,
        min_active_accounts_same_currency: Optional[int] = None,
        card_status: Optional[str] = None,
        beneficiary_status: Optional[str] = None,
        beneficiary_verification: Optional[str] = None,
        min_beneficiaries: Optional[int] = None,
        loan_type: Optional[str] = None,
        loan_status: Optional[str] = None,
        loan_payment_status: Optional[str] = None,
        transaction_status: Optional[str] = None,
        transaction_type: Optional[str] = None,
        min_available_balance: Optional[float] = None,
    ) -> str:
        global _call_counter

        clients: Dict[str, Any] = data.get("clients") or {}
        loans: Dict[str, Any] = data.get("loans") or {}
        beneficiaries: Dict[str, Any] = data.get("beneficiaries") or {}
        transactions: Dict[str, Any] = data.get("transactions") or {}

        candidates: List[Dict[str, Any]] = []

        for client_id, client in clients.items():
            if account_status is not None and not _has_account_status(
                client, account_status
            ):
                continue
            # an ACTIVE, non-credit account with at least this much available: what any
            # transfer / loan payment needs as its source (2 failed tasks moved 100 from
            # accounts holding 27-38)
            if min_available_balance is not None and not any(
                a.get("status") == "active"
                and a.get("type") != "credit"
                and float((a.get("balance") or {}).get("available", 0) or 0)
                >= float(min_available_balance)
                for a in client.get("accounts", {}).values()
            ):
                continue
            if min_active_accounts_same_currency is not None:
                try:
                    if not _has_min_active_accounts_same_currency(
                        client, int(min_active_accounts_same_currency)
                    ):
                        continue
                except (TypeError, ValueError):
                    pass
            if card_status is not None and not _has_card_status(client, card_status):
                continue

            client_benefs = _client_beneficiaries(client, beneficiaries)
            if beneficiary_status is not None and not _has_beneficiary_status(
                client_benefs, beneficiary_status
            ):
                continue
            if (
                beneficiary_verification is not None
                and not _has_beneficiary_verification(
                    client_benefs, beneficiary_verification
                )
            ):
                continue
            if min_beneficiaries is not None:
                try:
                    if len(client.get("beneficiary_ids", [])) < int(min_beneficiaries):
                        continue
                except (TypeError, ValueError):
                    pass

            client_loans = _client_loans(client, loans)
            if loan_type is not None and not _has_loan_type(client_loans, loan_type):
                continue
            if loan_status is not None and not _has_loan_status(
                client_loans, loan_status
            ):
                continue
            if loan_payment_status is not None and not _has_loan_payment_status(
                client_loans, loan_payment_status
            ):
                continue

            if transaction_status is not None and not _has_transaction_status(
                client_id, transactions, transaction_status
            ):
                continue
            if transaction_type is not None and not _has_transaction_type(
                client_id, transactions, transaction_type
            ):
                continue

            name = client.get("name", {})
            display_name = (
                " ".join(
                    p for p in [name.get("first_name"), name.get("last_name")] if p
                ).strip()
                or "Unknown"
            )
            candidates.append(
                {
                    "client_id": client_id,
                    "name": display_name,
                    "email": client.get("contact", {}).get("email", ""),
                    "num_accounts": len(client.get("accounts", {})),
                    "num_cards": len(client.get("cards", {})),
                    "num_loans": len(client.get("loan_ids", [])),
                    "num_beneficiaries": len(client.get("beneficiary_ids", [])),
                }
            )

        random.shuffle(candidates)
        total = len(candidates)
        if total == 0:
            return json.dumps(
                {"total_matching": 0, "returned_count": 0, "clients": []}, indent=2
            )

        offset = (_call_counter * _MAX_CLIENTS) % total
        _call_counter += 1
        doubled = candidates + candidates
        batch = doubled[offset : offset + _MAX_CLIENTS]

        payload = {
            "total_matching": total,
            "returned_count": len(batch),
            "clients": batch,
        }
        return json.dumps(payload, indent=2)

    @staticmethod
    def get_info() -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "get_client_candidates",
                "description": (
                    "Read-only roster of clients matching zero or more filters, for finding a real client whose "
                    "data already satisfies a scenario precondition (e.g. a client with a frozen account, or a "
                    "client with a beneficiary still pending verification). All filter parameters are optional; "
                    "when a filter is omitted, no constraint is applied for that field. Filters combine with AND "
                    "semantics — a client must satisfy every filter provided to match. Returns concise summaries "
                    "(client_id, name, email, and counts of accounts/cards/loans/beneficiaries), not full records — "
                    "use get_client_details, list_client_accounts, get_loan_details, etc. for full details once a "
                    "candidate client_id is chosen. The list is randomized; each call returns the next batch "
                    f"(up to {_MAX_CLIENTS} clients, different from previous calls)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_status": {
                            "type": "string",
                            "enum": ["active", "frozen"],
                            "description": (
                                "If set, only clients with at least one account in this status. Use 'frozen' to "
                                "find a client who already has a frozen account (e.g. to ground an unfreeze_account "
                                "task), or 'active' to find one eligible to have an account frozen."
                            ),
                        },
                        "min_active_accounts_same_currency": {
                            "type": "integer",
                            "description": (
                                "If set, only clients with at least this many ACTIVE accounts sharing the same "
                                "currency. Internal transfers require two active, same-currency accounts owned by "
                                "the same client, so use 2 here to find a client eligible for initiate_internal_transfer."
                            ),
                        },
                        "card_status": {
                            "type": "string",
                            "enum": ["active", "blocked", "expired"],
                            "description": (
                                "If set, only clients with at least one card in this status. Use 'blocked' to find "
                                "a client who already has a blocked card (e.g. to ground an unfreeze_card task), or "
                                "'active' to find one eligible to have a card frozen. Note: expired cards cannot be "
                                "frozen or unfrozen."
                            ),
                        },
                        "beneficiary_status": {
                            "type": "string",
                            "enum": ["active", "suspended", "revoked"],
                            "description": "If set, only clients with at least one beneficiary in this status.",
                        },
                        "beneficiary_verification": {
                            "type": "string",
                            "enum": ["pending", "verified", "failed"],
                            "description": (
                                "If set, only clients with at least one beneficiary whose verification status "
                                "matches. Use 'pending' to find a client eligible for verify_beneficiary, or "
                                "'verified' (combined with beneficiary_status='active') to find a client eligible "
                                "for initiate_transfer_to_beneficiary, which requires a verified, active beneficiary."
                            ),
                        },
                        "min_beneficiaries": {
                            "type": "integer",
                            "description": "If set, only clients with at least this many beneficiaries on file.",
                        },
                        "loan_type": {
                            "type": "string",
                            "enum": ["mortgage", "auto", "credit_line", "personal"],
                            "description": (
                                "If set, only clients with at least one loan of this type. Useful for grounding "
                                "tasks where the customer refers to the loan by a natural-language type, e.g. "
                                "'my car loan' (auto) or 'my mortgage'."
                            ),
                        },
                        "loan_status": {
                            "type": "string",
                            "enum": ["active", "delinquent"],
                            "description": "If set, only clients with at least one loan in this status.",
                        },
                        "loan_payment_status": {
                            "type": "string",
                            "enum": ["due", "late", "deferred", "paid"],
                            "description": (
                                "If set, only clients with at least one loan payment-schedule entry in this "
                                "status. Useful for grounding a make_loan_payment task in a genuinely upcoming or "
                                "overdue payment (e.g. 'due' or 'late')."
                            ),
                        },
                        "transaction_status": {
                            "type": "string",
                            "enum": ["pending", "posted"],
                            "description": "If set, only clients with at least one transaction in this status.",
                        },
                        "transaction_type": {
                            "type": "string",
                            "enum": [
                                "payment",
                                "transfer",
                                "withdrawal",
                                "deposit",
                                "interest",
                            ],
                            "description": "If set, only clients with at least one transaction of this type.",
                        },
                        "min_available_balance": {
                            "type": "number",
                            "description": (
                                "If set, only clients with an ACTIVE non-credit account whose available balance is "
                                "at least this amount -- the source account a transfer or loan payment needs. "
                                "Pick the amount from get_account_details afterwards; never exceed available."
                            ),
                        },
                    },
                    "required": [],
                },
            },
        }
