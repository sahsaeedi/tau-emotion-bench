"""Pydantic models for the telecom domain (account-management CRM).

Schema is reverse-engineered from TRACER's telecom data files
(tracer/tracer/envs/telecom/data/) merged into db.json.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from tau_emotion.domains.telecom.utils import TELECOM_DB_PATH
from tau_emotion.environment.db import DB

# ---------------------------------------------------------------------------
# Sub-records inside a customer
# ---------------------------------------------------------------------------


class Name(BaseModel):
    first_name: str
    last_name: str


class Demographics(BaseModel):
    date_of_birth: str
    phone: str
    email: str


class Address(BaseModel):
    address1: str
    address2: Optional[str] = ""
    city: str
    state: str
    zip: str
    country: str


class Account(BaseModel):
    account_number: str
    account_type: Literal["residential", "business", "senior"]
    created_date: str
    credit_score: int
    payment_method: str
    status: Optional[str] = None


class BillingPreferences(BaseModel):
    paperless: bool
    auto_pay: bool
    billing_cycle: Literal["monthly", "quarterly", "annual"]


class CustomerDevice(BaseModel):
    """A device instance attached to a customer's account."""

    device_id: str
    name: str
    # Tools (add_device, manage_service.remove) can clear this back to None.
    service: Optional[str] = None


class Customer(BaseModel):
    customer_id: str
    name: Name
    demographics: Demographics
    address: Address
    account: Account
    services: List[str] = Field(default_factory=list)
    devices: List[CustomerDevice] = Field(default_factory=list)
    billing_preferences: BillingPreferences


# ---------------------------------------------------------------------------
# Device catalog (model spec, not a customer-owned instance)
# ---------------------------------------------------------------------------


class DeviceModel(BaseModel):
    category: str
    manufacturer: str
    model: str


# ---------------------------------------------------------------------------
# Service catalog
# ---------------------------------------------------------------------------


class Service(BaseModel):
    service_id: str
    name: str
    category: str
    price: float


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


class PaymentRecord(BaseModel):
    date: str
    amount: float
    status: str


class LastPayment(BaseModel):
    amount: float
    date: str
    method: str
    status: str


class Billing(BaseModel):
    customer_id: str
    account_number: str
    current_balance: float
    last_payment: Optional[LastPayment] = None
    next_bill_date: str
    # Free-form: keys are service_ids plus surcharge labels
    # (e.g. "taxes_fees", "late_fee", "senior_discount").
    monthly_charges: Dict[str, float] = Field(default_factory=dict)
    payment_history: List[PaymentRecord] = Field(default_factory=list)
    auto_pay: bool = False
    paperless: bool = False
    # Set by manage_billing, which (like v1) writes the cycle here rather than
    # to the customer's billing_preferences.
    billing_cycle: Optional[str] = None


# ---------------------------------------------------------------------------
# Support tickets
# ---------------------------------------------------------------------------


class SupportTicket(BaseModel):
    ticket_id: str
    customer_id: str
    # Free-form: v1's modify_support_ticket stores any status and priority.
    status: str
    priority: str
    # Added at creation time by the create_support_ticket tool; absent on
    # seed records.
    category: Optional[str] = None
    created_at: Optional[str] = None
    description: Optional[str] = None
    resolution: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level DB
# ---------------------------------------------------------------------------


class TelecomDB(DB):
    """Telecom CRM database: customers, device catalog, services, billing,
    support tickets."""

    customers: Dict[str, Customer]
    devices: Dict[str, DeviceModel]
    services: Dict[str, Service]
    billing: Dict[str, Billing]
    support_tickets: Dict[str, SupportTicket]

    def get_statistics(self) -> dict[str, Any]:
        return {
            "num_customers": len(self.customers),
            "num_device_models": len(self.devices),
            "num_services": len(self.services),
            "num_billing_records": len(self.billing),
            "num_support_tickets": len(self.support_tickets),
        }


def get_db() -> TelecomDB:
    return TelecomDB.load(TELECOM_DB_PATH)


if __name__ == "__main__":
    db = get_db()
    print(db.get_statistics())
