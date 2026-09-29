from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Sequence,
    Tuple,
)

from faker import Faker


def _repo_root(start: Path) -> Path:
    cur = start.resolve()
    while cur != cur.parent and not (cur / "tracer").exists():
        cur = cur.parent
    if not (cur / "tracer").exists():
        raise RuntimeError(
            "Could not locate repo root (expected a `tracer/` directory)."
        )
    return cur


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=4, ensure_ascii=False, sort_keys=False)
        f.write("\n")


def _choice_weighted(rng: random.Random, items: Sequence[Tuple[Any, float]]) -> Any:
    population = [x for x, _w in items]
    weights = [float(w) for _x, w in items]
    return rng.choices(population, weights=weights, k=1)[0]


def _load_yaml_config(path: Path) -> Dict[str, Any]:
    """
    Loads a YAML config file.

    Requires PyYAML (`pip install pyyaml`). We keep this optional to avoid forcing
    a new dependency on the repo.
    """
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "YAML config requested but PyYAML is not installed. "
            "Install it with `pip install pyyaml` or run without --config."
        ) from e

    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg is None:
        return {}
    if not isinstance(cfg, dict):
        raise ValueError("Config YAML must parse to a mapping at the top level.")
    return cfg


def _deep_update(dst: Dict[str, Any], src: Mapping[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)  # type: ignore[index]
        else:
            dst[k] = v
    return dst


def _default_config() -> Dict[str, Any]:
    return {
        "account_type_weights": {"residential": 0.85, "business": 0.15},
        "residential": {
            "mobile_weights": {
                "mobile_basic": 0.30,
                "mobile_unlimited": 0.45,
                "mobile_senior": 0.10,
                "mobile_family_4lines": 0.15,
            },
            "internet_weights": {
                "internet_cable_100mb": 0.25,
                "internet_cable_500mb": 0.35,
                "internet_fiber_500mb": 0.20,
                "internet_fiber_1gb": 0.20,
            },
            "tv_weights": {"none": 0.40, "tv_basic": 0.35, "tv_premium": 0.25},
            "security_probability": 0.15,
        },
        "business": {
            "internet_weights": {
                "internet_fiber_2gb": 0.75,
                "internet_fiber_1gb": 0.25,
            },
            "phone_system_probability": 0.70,
            "tv_weights": {"none": 0.30, "tv_sports_package": 0.50, "tv_premium": 0.20},
        },
        "billing_preferences": {
            "paperless_probability": 0.70,
            "auto_pay_probability": {"residential": 0.60, "business": 0.40},
        },
        "billing_dates": {
            "next_bill_year_month": "2025-10",
            "next_bill_day_range": [5, 28],
            "payment_history_months_range": [3, 5],
            "payment_history_earliest_year_month": "2025-06",
        },
        "delinquency": {
            "if_no_autopay_probability": 0.15,
            "base_probability": 0.05,
            "late_fee_amount": 25.00,
            "balance_min": 20.0,
            "balance_cap": 250.0,
        },
        "tickets": {
            "count_weights": {0: 0.60, 1: 0.30, 2: 0.07, 3: 0.03},
            "status_weights": {"closed": 0.70, "open": 0.30},
            "priority_weights": {"low": 0.25, "medium": 0.55, "high": 0.20},
            "more_devices_threshold": 6,
            "more_devices_bump_probability": 0.25,
        },
        "devices": {
            "family_lines_range": [3, 5],
            "business_lines_range": [2, 12],
            "router_rental_probability": 0.55,
            "tv_additional_set_probability": 0.60,
            "tv_cable_box_probability": 0.70,
        },
        "taxes_fees_rate_range": [0.06, 0.12],
        "created_date_range": ["2016-01-01", "2025-09-01"],
    }


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    if end < start:
        start, end = end, start
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def _add_months(d: date, months: int) -> date:
    # simple, deterministic month stepping without extra deps
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # clamp day to month length
    day = min(
        d.day,
        [
            31,
            29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][m - 1],
    )
    return date(y, m, day)


def _iso(d: date) -> str:
    return d.isoformat()


def _round_money(x: float) -> float:
    return float(f"{x:.2f}")


def _parse_year_month(s: str) -> Tuple[int, int]:
    # "YYYY-MM"
    parts = s.split("-")
    if len(parts) != 2:
        raise ValueError(f"Expected YYYY-MM, got: {s}")
    y, m = int(parts[0]), int(parts[1])
    if not (1 <= m <= 12):
        raise ValueError(f"Invalid month in {s}")
    return y, m


def _months_between_inclusive(later: date, earlier: date) -> int:
    # Count whole months inclusive, assuming day-of-month is irrelevant.
    # Example: later=2025-09-xx, earlier=2025-06-01 => 4 (Jun,Jul,Aug,Sep)
    return (later.year - earlier.year) * 12 + (later.month - earlier.month) + 1


@dataclass(frozen=True)
class Service:
    service_id: str
    name: str
    category: str
    price: float


def _load_services(services_json: Mapping[str, Any]) -> Dict[str, Service]:
    out: Dict[str, Service] = {}
    for sid, rec in services_json.items():
        out[sid] = Service(
            service_id=rec["service_id"],
            name=rec["name"],
            category=rec["category"],
            price=float(rec["price"]),
        )
    return out


def _device_names_by_category(devices_json: Mapping[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for device_name, rec in devices_json.items():
        cat = rec.get("category", "unknown")
        out.setdefault(cat, []).append(device_name)
    for cat in out:
        out[cat].sort()
    return out


def _faker_us_address(fake: Faker) -> Dict[str, str]:
    """Build address dict matching tracer telecom schema; uses fake.random (shared rng)."""
    addr2 = fake.secondary_address() if fake.random.random() < 0.35 else ""
    return {
        "address1": fake.street_address(),
        "address2": addr2,
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip": fake.zipcode(),
        "country": "USA",
    }


def _make_customer_id(first: str, last: str, suffix: int) -> str:
    return f"{first.lower()}_{last.lower()}_{suffix:04d}"


def _make_account_number(n: int) -> str:
    return f"ACC{n:09d}"


def _pick_account_type(rng: random.Random) -> str:
    # Backwards-compatible default; overridden by config in generate_telecom_dataset
    return _choice_weighted(rng, [("residential", 0.85), ("business", 0.15)])


def _pick_residential_services(
    rng: random.Random, services: Mapping[str, Service], cfg: Mapping[str, Any]
) -> List[str]:
    mobile_weights = cfg["residential"]["mobile_weights"]
    internet_weights = cfg["residential"]["internet_weights"]
    tv_weights = cfg["residential"]["tv_weights"]
    security_p = float(cfg["residential"]["security_probability"])

    mobile = _choice_weighted(rng, list(mobile_weights.items()))
    internet = _choice_weighted(rng, list(internet_weights.items()))
    out = [mobile, internet]

    # optional TV
    tv_choice = _choice_weighted(rng, list(tv_weights.items()))
    if tv_choice != "none":
        out.append(tv_choice)

    # optional security
    if rng.random() < security_p:
        out.append("home_security")

    # ensure valid
    return [sid for sid in out if sid in services]


def _pick_business_services(
    rng: random.Random, services: Mapping[str, Service], cfg: Mapping[str, Any]
) -> List[str]:
    out = ["mobile_business_10lines"]
    internet_weights = cfg["business"]["internet_weights"]
    internet = _choice_weighted(rng, list(internet_weights.items()))
    out.append(internet)
    if rng.random() < float(cfg["business"]["phone_system_probability"]):
        out.append("business_phone_system")
    tv_choice = _choice_weighted(rng, list(cfg["business"]["tv_weights"].items()))
    if tv_choice != "none":
        out.append(tv_choice)
    return [sid for sid in out if sid in services]


def _pick_services_for_customer(
    rng: random.Random,
    account_type: str,
    services: Mapping[str, Service],
    cfg: Mapping[str, Any],
) -> List[str]:
    if account_type == "business":
        return _pick_business_services(rng, services, cfg)
    return _pick_residential_services(rng, services, cfg)


def _pick_dob(rng: random.Random, services_list: Sequence[str]) -> date:
    # Senior plan skews older; otherwise broad adult distribution
    today = date(2025, 10, 1)
    if "mobile_senior" in services_list:
        # 60-85 years old
        age = rng.randint(60, 85)
    else:
        age = rng.randint(18, 70)
    # pick day within year window
    start = date(today.year - age - 1, 1, 1)
    end = date(today.year - age, 12, 31)
    return _rand_date(rng, start, end)


def _pick_payment_method(rng: random.Random, account_type: str) -> str:
    if account_type == "business":
        return _choice_weighted(
            rng, [("invoice", 0.60), ("bank_transfer", 0.20), ("credit_card", 0.20)]
        )
    return _choice_weighted(
        rng,
        [
            ("auto_pay_credit_card", 0.35),
            ("credit_card", 0.30),
            ("bank_transfer", 0.20),
            ("auto_pay_bank", 0.15),
        ],
    )


def _pick_credit_score(rng: random.Random) -> int:
    # Mildly realistic bounded normal-ish
    score = int(rng.gauss(690, 55))
    return max(520, min(820, score))


def _pick_billing_prefs(
    rng: random.Random, account_type: str, cfg: Mapping[str, Any]
) -> Dict[str, Any]:
    bp = cfg["billing_preferences"]
    paperless = rng.random() < float(bp["paperless_probability"])
    auto_pay_probs = bp["auto_pay_probability"]
    auto_pay = rng.random() < float(
        auto_pay_probs.get(account_type, auto_pay_probs.get("residential", 0.6))
    )
    return {"paperless": paperless, "auto_pay": auto_pay, "billing_cycle": "monthly"}


def _pick_device_name(
    rng: random.Random, by_cat: Mapping[str, List[str]], cat: str, fallback: str
) -> str:
    choices = by_cat.get(cat) or []
    if not choices:
        return fallback
    return rng.choice(choices)


def _gen_devices(
    rng: random.Random,
    services_list: Sequence[str],
    service_catalog: Mapping[str, Service],
    device_names_by_cat: Mapping[str, List[str]],
    cfg: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    next_id = 1

    def add_device(name: str, service: str) -> None:
        nonlocal next_id
        devices.append({"device_id": str(next_id), "name": name, "service": service})
        next_id += 1

    # Mobile devices
    mobile_services = [
        s for s in services_list if service_catalog[s].category == "mobile"
    ]
    dev_cfg = cfg["devices"]
    fam_lo, fam_hi = map(int, dev_cfg["family_lines_range"])
    biz_lo, biz_hi = map(int, dev_cfg["business_lines_range"])

    for ms in mobile_services:
        if ms == "mobile_family_4lines":
            n = rng.randint(fam_lo, fam_hi)
        elif ms == "mobile_business_10lines":
            n = rng.randint(biz_lo, biz_hi)
        else:
            n = 1
        for _ in range(n):
            phone = _pick_device_name(
                rng, device_names_by_cat, "mobile_phone", "iPhone 15"
            )
            add_device(phone, ms)

    # Internet router (one per internet service)
    internet_services = [
        s for s in services_list if service_catalog[s].category == "internet"
    ]
    for ins in internet_services:
        router = _pick_device_name(
            rng, device_names_by_cat, "networking", "WiFi 6 Router"
        )
        add_device(router, ins)

    # TV devices
    tv_services = [s for s in services_list if service_catalog[s].category == "tv"]
    for tvs in tv_services:
        # Cable box common
        if "HD Cable Box" in device_names_by_cat.get("tv", []) or True:
            add_device("HD Cable Box", tvs)
        # Sometimes a TV set
        if rng.random() < float(dev_cfg["tv_additional_set_probability"]):
            tv_set = _pick_device_name(
                rng, device_names_by_cat, "tv", 'Samsung 65" Smart TV'
            )
            add_device(tv_set, tvs)

    # Security device
    if "home_security" in services_list:
        sec = _pick_device_name(
            rng, device_names_by_cat, "security", "Home Security System"
        )
        add_device(sec, "home_security")

    return devices


def _compute_monthly_charges(
    rng: random.Random,
    services_list: Sequence[str],
    service_catalog: Mapping[str, Service],
    devices: Sequence[Mapping[str, Any]],
    cfg: Mapping[str, Any],
) -> Dict[str, float]:
    charges: Dict[str, float] = {}
    subtotal = 0.0
    for sid in services_list:
        price = float(service_catalog[sid].price)
        charges[sid] = _round_money(price)
        subtotal += price

    # Rentals / add-ons
    has_internet = any(service_catalog[s].category == "internet" for s in services_list)
    has_tv = any(service_catalog[s].category == "tv" for s in services_list)
    dev_cfg = cfg["devices"]
    if has_internet and rng.random() < float(dev_cfg["router_rental_probability"]):
        router_fee = _choice_weighted(rng, [(5.0, 0.55), (10.0, 0.35), (15.0, 0.10)])
        charges[
            _choice_weighted(rng, [("router_basic", 0.5), ("router_enterprise", 0.5)])
        ] = _round_money(float(router_fee))
        subtotal += float(router_fee)
    if has_tv and rng.random() < float(dev_cfg["tv_cable_box_probability"]):
        cable_fee = _choice_weighted(rng, [(10.0, 0.8), (15.0, 0.2)])
        charges["cable_box_hd"] = _round_money(float(cable_fee))
        subtotal += float(cable_fee)

    # Discounts
    if "mobile_senior" in services_list:
        disc = _round_money(rng.uniform(5.0, 15.0))
        charges["senior_discount"] = _round_money(-disc)
        subtotal -= disc

    taxes_lo, taxes_hi = map(float, cfg["taxes_fees_rate_range"])
    taxes = _round_money(subtotal * rng.uniform(taxes_lo, taxes_hi))
    charges["taxes_fees"] = taxes
    subtotal += taxes

    # Late fee handled later when current_balance > 0
    return charges


def _make_payment_history(
    rng: random.Random,
    total_due: float,
    months: int,
    last_bill_date: date,
    delinquent: bool,
) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for i in range(months):
        bill_date = _add_months(last_bill_date, -i)
        status = "completed"
        amount = total_due
        if delinquent and i == 0:
            # most recent bill has partial/late
            status = _choice_weighted(rng, [("late", 0.6), ("completed", 0.4)])
            if status == "late":
                amount = _round_money(total_due * rng.uniform(0.3, 0.8))
        history.append(
            {
                "date": _iso(bill_date),
                "amount": _round_money(float(amount)),
                "status": status,
            }
        )
    return history


def _compute_billing_record(
    rng: random.Random,
    customer: Mapping[str, Any],
    service_catalog: Mapping[str, Service],
    cfg: Mapping[str, Any],
) -> Dict[str, Any]:
    cid = str(customer["customer_id"])
    services_list = list(customer.get("services", []))
    devices = list(customer.get("devices", []))

    charges = _compute_monthly_charges(
        rng, services_list, service_catalog, devices, cfg
    )
    subtotal = sum(float(v) for v in charges.values())

    auto_pay = bool(customer.get("billing_preferences", {}).get("auto_pay", False))
    del_cfg = cfg["delinquency"]
    delinquent = (
        (not auto_pay) and (rng.random() < float(del_cfg["if_no_autopay_probability"]))
    ) or (rng.random() < float(del_cfg["base_probability"]))

    current_balance = 0.0
    if delinquent:
        bal_min = float(del_cfg["balance_min"])
        bal_cap = float(del_cfg["balance_cap"])
        current_balance = _round_money(
            rng.uniform(bal_min, min(bal_cap, max(bal_min + 10.0, subtotal)))
        )
        # late fee appears as line item
        late_fee = float(del_cfg["late_fee_amount"])
        charges["late_fee"] = _round_money(late_fee)
        subtotal += late_fee

    bdcfg = cfg["billing_dates"]
    ny, nm = _parse_year_month(str(bdcfg["next_bill_year_month"]))
    day_lo, day_hi = map(int, bdcfg["next_bill_day_range"])
    next_bill = date(ny, nm, rng.randint(day_lo, day_hi))

    # Payment history is monthly payments up through last bill date (month before next bill).
    last_bill_date = _add_months(next_bill, -1)

    hist_lo, hist_hi = map(int, bdcfg["payment_history_months_range"])
    earliest_y, earliest_m = _parse_year_month(
        str(bdcfg["payment_history_earliest_year_month"])
    )
    earliest_allowed = date(earliest_y, earliest_m, 1)
    max_months = _months_between_inclusive(last_bill_date, earliest_allowed)
    months_hist = rng.randint(hist_lo, hist_hi)
    months_hist = max(hist_lo, min(months_hist, max_months))

    hist = _make_payment_history(rng, subtotal, months_hist, last_bill_date, delinquent)
    last_payment = hist[0]

    # If balance is zero, make last payment match due for clean accounting
    if current_balance == 0.0:
        last_payment = {
            **last_payment,
            "amount": _round_money(subtotal),
            "status": "completed",
        }
        hist[0] = last_payment

    return {
        "customer_id": cid,
        "account_number": str(customer["account"]["account_number"]),
        "current_balance": _round_money(current_balance),
        "last_payment": {
            "amount": float(last_payment["amount"]),
            "date": last_payment["date"],
            "method": str(customer["account"].get("payment_method", "credit_card")),
            "status": last_payment["status"],
        },
        "next_bill_date": _iso(next_bill),
        "monthly_charges": {k: _round_money(float(v)) for k, v in charges.items()},
        "payment_history": hist,
        "auto_pay": bool(
            customer.get("billing_preferences", {}).get("auto_pay", False)
        ),
        "paperless": bool(
            customer.get("billing_preferences", {}).get("paperless", False)
        ),
    }


def _maybe_make_tickets(
    rng: random.Random,
    cid: str,
    ticket_start: int,
    customer: Mapping[str, Any],
    cfg: Mapping[str, Any],
) -> Tuple[Dict[str, Any], int]:
    tcfg = cfg["tickets"]
    count_weights = [(int(k), float(v)) for k, v in tcfg["count_weights"].items()]
    k = int(_choice_weighted(rng, count_weights))
    out: Dict[str, Any] = {}
    seq = ticket_start

    # slightly higher chance if many devices
    if len(customer.get("devices", [])) >= int(
        tcfg["more_devices_threshold"]
    ) and rng.random() < float(tcfg["more_devices_bump_probability"]):
        k = min(3, k + 1)

    status_weights = list(tcfg["status_weights"].items())
    priority_weights = list(tcfg["priority_weights"].items())
    for _ in range(k):
        tid = f"TICKET{seq:05d}"
        out[tid] = {
            "ticket_id": tid,
            "customer_id": cid,
            "status": _choice_weighted(rng, status_weights),
            "priority": _choice_weighted(rng, priority_weights),
        }
        seq += 1
    return out, seq


def _validate(
    customers: Mapping[str, Any],
    billing: Mapping[str, Any],
    tickets: Mapping[str, Any],
    service_catalog: Mapping[str, Service],
    devices_json: Mapping[str, Any],
) -> None:
    device_names = set(devices_json.keys())
    service_ids = set(service_catalog.keys())
    for cid, c in customers.items():
        if cid != c.get("customer_id"):
            raise ValueError(f"Customer key/id mismatch for {cid}")
        acct = c.get("account", {})
        if not acct.get("account_number"):
            raise ValueError(f"Missing account_number for {cid}")

        sl = c.get("services", [])
        for sid in sl:
            if sid not in service_ids:
                raise ValueError(f"Unknown service {sid} for {cid}")

        for d in c.get("devices", []):
            if d.get("name") not in device_names:
                raise ValueError(f"Unknown device name {d.get('name')} for {cid}")
            if d.get("service") not in sl:
                raise ValueError(
                    f"Device service {d.get('service')} not in customer services for {cid}"
                )

        b = billing.get(cid)
        if not b:
            raise ValueError(f"Missing billing for {cid}")
        if b.get("customer_id") != cid:
            raise ValueError(f"Billing customer_id mismatch for {cid}")
        if b.get("account_number") != acct.get("account_number"):
            raise ValueError(f"Billing account_number mismatch for {cid}")

        monthly = b.get("monthly_charges", {})
        for sid in sl:
            if sid not in monthly:
                raise ValueError(f"Billing missing service line item {sid} for {cid}")

    for tid, t in tickets.items():
        if t.get("ticket_id") != tid:
            raise ValueError(f"Ticket key/id mismatch for {tid}")
        if t.get("customer_id") not in customers:
            raise ValueError(
                f"Ticket references unknown customer {t.get('customer_id')}"
            )


# The split's own files; services.json and devices.json are a shared catalog.
OWNED_FILES = ("customers", "billing", "support_tickets")


def generate_telecom_dataset(
    n_customers: int,
    seed: int,
    out_dir: Path,
    repo_root: Path,
    cfg: Mapping[str, Any],
    split: str = "test",
) -> None:
    """Add `n_customers` new customers to one split of the telecom data.

    Reads `tracer/envs/telecom/data/` (the catalog, plus the split's customers,
    billing and tickets) and writes the split's files, existing records plus the
    new ones, to `out_dir/<split>/`. Copy them over `data/<split>/` to use them.
    New ids, account numbers, emails and ticket ids never collide with existing ones.
    """
    base_dir = repo_root / "tracer" / "envs" / "telecom" / "data"
    services_json = _read_json(base_dir / "services.json")
    devices_json = _read_json(base_dir / "devices.json")
    existing = {
        name: _read_json(base_dir / split / f"{name}.json") for name in OWNED_FILES
    }

    service_catalog = _load_services(services_json)
    device_names_by_cat = _device_names_by_category(devices_json)

    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.random = rng

    customers_out: Dict[str, Any] = dict(existing["customers"])
    billing_out: Dict[str, Any] = dict(existing["billing"])
    tickets_out: Dict[str, Any] = dict(existing["support_tickets"])

    used_customer_ids: set[str] = set(customers_out)
    used_account_numbers: set[str] = {
        c["account"]["account_number"] for c in customers_out.values()
    }
    used_email: set[str] = {c["demographics"]["email"] for c in customers_out.values()}

    # Number new accounts and tickets after the existing ones.
    next_acc = 1 + max([999_999] + [int(a[len("ACC") :]) for a in used_account_numbers])
    ticket_seq = 1 + max([0] + [int(t[len("TICKET") :]) for t in tickets_out])

    acct_weights = [(k, float(v)) for k, v in cfg["account_type_weights"].items()]

    for _i in range(n_customers):
        # Generate unique name/id
        for _try in range(2000):
            first = fake.first_name()
            last = fake.last_name()
            suffix = rng.randint(0, 9999)
            cid = _make_customer_id(first, last, suffix)
            if cid not in used_customer_ids:
                used_customer_ids.add(cid)
                break
        else:
            raise RuntimeError("Failed to generate unique customer_id")

        account_type = _choice_weighted(rng, acct_weights)
        services_list = _pick_services_for_customer(
            rng, account_type, service_catalog, cfg
        )

        # Unique account number
        for _try in range(2000):
            acc = _make_account_number(next_acc)
            next_acc += 1
            if acc not in used_account_numbers:
                used_account_numbers.add(acc)
                break
        else:
            raise RuntimeError("Failed to generate unique account_number")

        # Email (keep unique to avoid accidental joins)
        email = f"{first.lower()}.{last.lower()}{rng.randint(0, 9999):04d}@email.com"
        while email in used_email:
            email = (
                f"{first.lower()}.{last.lower()}{rng.randint(0, 999999):06d}@email.com"
            )
        used_email.add(email)

        addr = _faker_us_address(fake)

        created = _rand_date(rng, date(2016, 1, 1), date(2025, 9, 1))
        payment_method = _pick_payment_method(rng, account_type)
        credit_score = _pick_credit_score(rng)

        prefs = _pick_billing_prefs(rng, account_type, cfg)

        devices = _gen_devices(
            rng, services_list, service_catalog, device_names_by_cat, cfg
        )

        customer = {
            "customer_id": cid,
            "name": {"first_name": first, "last_name": last},
            "demographics": {
                "date_of_birth": _iso(_pick_dob(rng, services_list)),
                "phone": f"(555) {rng.randint(100, 999)}-{rng.randint(0, 9999):04d}",
                "email": email,
            },
            "address": addr,
            "account": {
                "account_number": acc,
                "account_type": account_type,
                "created_date": _iso(created),
                "credit_score": credit_score,
                "payment_method": payment_method,
            },
            "services": services_list,
            "devices": devices,
            "billing_preferences": prefs,
        }

        customers_out[cid] = customer
        billing_out[cid] = _compute_billing_record(rng, customer, service_catalog, cfg)
        ticket_block, ticket_seq = _maybe_make_tickets(
            rng, cid, ticket_seq, customer, cfg
        )
        tickets_out.update(ticket_block)

    _validate(customers_out, billing_out, tickets_out, service_catalog, devices_json)

    _write_json(out_dir / split / "customers.json", customers_out)
    _write_json(out_dir / split / "billing.json", billing_out)
    _write_json(out_dir / split / "support_tickets.json", tickets_out)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="data_extender.telecom",
        description="Generate an extended telecom benchmark dataset.",
    )
    parser.add_argument(
        "N", type=int, help="Number of customers to generate (e.g., 200-500)"
    )
    parser.add_argument(
        "--seed", type=int, default=1337, help="RNG seed for reproducible generation"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path("data_extender") / "telecom" / "telecom_config.yaml"),
        help="YAML config path for weights/ranges.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(Path("data_extender") / "generated_telecom"),
        help="Output directory; the split's files are written to <out>/<split>/.",
    )
    parser.add_argument(
        "--split",
        choices=["test", "train"],
        default="test",
        help="Which split of tracer/envs/telecom/data/ to add customers to.",
    )
    args = parser.parse_args()

    if args.N <= 0:
        raise SystemExit("N must be > 0")

    repo_root = _repo_root(Path.cwd())

    cfg: Dict[str, Any] = _default_config()
    config_path = Path(args.config)
    resolved_config = (
        config_path if config_path.is_absolute() else (repo_root / config_path)
    )
    # Without a config file, the defaults are used.
    if resolved_config.exists():
        _deep_update(cfg, _load_yaml_config(resolved_config))

    out_dir = (
        (repo_root / args.out).resolve()
        if not Path(args.out).is_absolute()
        else Path(args.out).resolve()
    )
    generate_telecom_dataset(
        args.N, args.seed, out_dir, repo_root, cfg, split=args.split
    )
    print(f"Wrote the extended {args.split} split to: {out_dir / args.split}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
