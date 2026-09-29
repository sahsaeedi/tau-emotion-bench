from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, List, Mapping


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _pct(n: int, d: int) -> str:
    if d == 0:
        return "0.0%"
    return f"{(100.0 * n / d):.1f}%"


def _money_stats(xs: List[float]) -> str:
    if not xs:
        return "n=0"
    xs_sorted = sorted(xs)
    return (
        f"n={len(xs)} min={xs_sorted[0]:.2f} p50={statistics.median(xs_sorted):.2f} "
        f"p90={xs_sorted[int(0.9 * (len(xs_sorted) - 1))]:.2f} max={xs_sorted[-1]:.2f} mean={statistics.mean(xs):.2f}"
    )


def _validate(
    customers: Mapping[str, Any],
    billing: Mapping[str, Any],
    tickets: Mapping[str, Any],
    services: Mapping[str, Any],
    devices_catalog: Mapping[str, Any],
) -> List[str]:
    errors: List[str] = []
    service_ids = set(services.keys())
    device_names = set(devices_catalog.keys())

    # Basic key alignment
    if set(customers.keys()) != set(billing.keys()):
        missing_billing = set(customers.keys()) - set(billing.keys())
        extra_billing = set(billing.keys()) - set(customers.keys())
        if missing_billing:
            errors.append(f"Billing missing {len(missing_billing)} customers")
        if extra_billing:
            errors.append(f"Billing has {len(extra_billing)} extra customers")

    for cid, c in customers.items():
        if c.get("customer_id") != cid:
            errors.append(f"Customer key/id mismatch: {cid}")

        acct = c.get("account") or {}
        acct_num = acct.get("account_number")
        if not acct_num:
            errors.append(f"Missing account_number for {cid}")

        # Service validity
        svcs = c.get("services") or []
        for sid in svcs:
            if sid not in service_ids:
                errors.append(f"Unknown service_id {sid} for {cid}")

        # Device validity and membership
        for d in c.get("devices") or []:
            name = d.get("name")
            if name not in device_names:
                errors.append(f"Unknown device name {name!r} for {cid}")
            svc = d.get("service")
            if svc not in svcs:
                errors.append(
                    f"Device service {svc!r} not in customer services for {cid}"
                )

        # Billing alignment
        b = billing.get(cid)
        if not b:
            continue
        if b.get("customer_id") != cid:
            errors.append(f"Billing customer_id mismatch: {cid}")
        if acct_num and b.get("account_number") != acct_num:
            errors.append(f"Billing account_number mismatch: {cid}")

        monthly = b.get("monthly_charges") or {}
        for sid in svcs:
            if sid not in monthly:
                errors.append(f"Billing missing service line item {sid} for {cid}")

        # Payment history months monotonic-ish (allow duplicates if same day)
        ph = b.get("payment_history") or []
        for rec in ph:
            if "date" not in rec or "amount" not in rec or "status" not in rec:
                errors.append(f"Bad payment_history record for {cid}")
                break

    for tid, t in tickets.items():
        if t.get("ticket_id") != tid:
            errors.append(f"Ticket key/id mismatch: {tid}")
        tcid = t.get("customer_id")
        if tcid not in customers:
            errors.append(f"Ticket {tid} references unknown customer_id {tcid!r}")

    return errors


def _flatten_iter(it: Iterable[Iterable[Any]]) -> Iterable[Any]:
    for sub in it:
        for x in sub:
            yield x


def print_stats(
    dataset_dir: Path, split: str, *, catalog_dir: Path, max_errors: int = 25
) -> int:
    """Validate and summarize `dataset_dir/<split>/`, against the service and
    device catalog in `catalog_dir`."""
    customers_path = dataset_dir / split / "customers.json"
    billing_path = dataset_dir / split / "billing.json"
    tickets_path = dataset_dir / split / "support_tickets.json"
    services_path = catalog_dir / "services.json"
    devices_path = catalog_dir / "devices.json"

    missing = [
        str(p)
        for p in [
            customers_path,
            billing_path,
            tickets_path,
            services_path,
            devices_path,
        ]
        if not p.exists()
    ]
    if missing:
        raise SystemExit(f"Missing files: {', '.join(missing)}")

    customers = _read_json(customers_path)
    billing = _read_json(billing_path)
    tickets = _read_json(tickets_path)
    services = _read_json(services_path)
    devices_catalog = _read_json(devices_path)

    n_customers = len(customers)
    n_tickets = len(tickets)

    errors = _validate(customers, billing, tickets, services, devices_catalog)
    print("## Telecom dataset stats")
    print(f"- path: {dataset_dir}")
    print(f"- customers: {n_customers}")
    print(f"- tickets: {n_tickets}")
    print(f"- validation_errors: {len(errors)}")
    if errors:
        for e in errors[:max_errors]:
            print(f"  - {e}")
        if len(errors) > max_errors:
            print(f"  - ... {len(errors) - max_errors} more")

    # Account type mix
    acct_types = Counter(
        (c.get("account") or {}).get("account_type", "unknown")
        for c in customers.values()
    )
    print("\n## Account types")
    for k, v in acct_types.most_common():
        print(f"- {k}: {v} ({_pct(v, n_customers)})")

    # Services mix
    svc_counts = Counter(
        _flatten_iter((c.get("services") or []) for c in customers.values())
    )
    print("\n## Services (top 15)")
    for sid, cnt in svc_counts.most_common(15):
        cat = (services.get(sid) or {}).get("category", "?")
        price = (services.get(sid) or {}).get("price", "?")
        print(f"- {sid} ({cat}, ${price}): {cnt} ({_pct(cnt, n_customers)})")

    # Devices
    device_total = 0
    device_cat_counts = Counter()
    devices_per_customer: List[int] = []
    for c in customers.values():
        ds = c.get("devices") or []
        devices_per_customer.append(len(ds))
        device_total += len(ds)
        for d in ds:
            name = d.get("name")
            cat = (devices_catalog.get(name) or {}).get("category", "unknown")
            device_cat_counts[cat] += 1

    print("\n## Devices")
    print(f"- total_devices: {device_total}")
    if devices_per_customer:
        print(
            f"- devices_per_customer: min={min(devices_per_customer)} "
            f"p50={statistics.median(devices_per_customer)} "
            f"p90={sorted(devices_per_customer)[int(0.9 * (len(devices_per_customer) - 1))]} "
            f"max={max(devices_per_customer)} mean={statistics.mean(devices_per_customer):.2f}"
        )
    print("- device_categories:")
    for cat, cnt in device_cat_counts.most_common():
        print(f"  - {cat}: {cnt} ({_pct(cnt, device_total)})")

    # Billing stats
    balances = [float((b.get("current_balance") or 0.0)) for b in billing.values()]
    delinquent = sum(1 for x in balances if x > 0.0)
    print("\n## Billing")
    print(
        f"- delinquent_customers(balance>0): {delinquent} ({_pct(delinquent, n_customers)})"
    )
    print(f"- current_balance: {_money_stats(balances)}")

    totals: List[float] = []
    taxes: List[float] = []
    late_fees = 0
    payment_months = Counter()
    ph_lengths: List[int] = []

    for b in billing.values():
        monthly = b.get("monthly_charges") or {}
        total = sum(float(v) for v in monthly.values())
        totals.append(total)
        if "taxes_fees" in monthly:
            taxes.append(float(monthly["taxes_fees"]))
        if "late_fee" in monthly:
            late_fees += 1
        ph = b.get("payment_history") or []
        ph_lengths.append(len(ph))
        for rec in ph:
            dt = rec.get("date")
            if isinstance(dt, str) and len(dt) >= 7:
                payment_months[dt[:7]] += 1

    print(f"- monthly_total_due(sum monthly_charges): {_money_stats(totals)}")
    if taxes:
        print(f"- taxes_fees: {_money_stats(taxes)}")
    print(f"- late_fee_line_item_present: {late_fees} ({_pct(late_fees, n_customers)})")
    if ph_lengths:
        print(
            f"- payment_history_length: min={min(ph_lengths)} "
            f"p50={statistics.median(ph_lengths)} "
            f"max={max(ph_lengths)} mean={statistics.mean(ph_lengths):.2f}"
        )
    if payment_months:
        months_sorted = sorted(payment_months.items())
        lo, hi = months_sorted[0][0], months_sorted[-1][0]
        print(f"- payment_history_month_range: {lo} .. {hi}")
        print("- payment_history_month_counts:")
        for ym, cnt in months_sorted:
            print(f"  - {ym}: {cnt}")

    # Tickets
    print("\n## Support tickets")
    if n_tickets == 0:
        print("- none")
    else:
        status_counts = Counter(t.get("status", "unknown") for t in tickets.values())
        priority_counts = Counter(
            t.get("priority", "unknown") for t in tickets.values()
        )
        print("- status:")
        for k, v in status_counts.most_common():
            print(f"  - {k}: {v} ({_pct(v, n_tickets)})")
        print("- priority:")
        for k, v in priority_counts.most_common():
            print(f"  - {k}: {v} ({_pct(v, n_tickets)})")

        tickets_per_customer = Counter(t.get("customer_id") for t in tickets.values())
        per = [tickets_per_customer.get(cid, 0) for cid in customers.keys()]
        print(
            f"- tickets_per_customer: min={min(per)} p50={statistics.median(per)} "
            f"p90={sorted(per)[int(0.9 * (len(per) - 1))]} max={max(per)} mean={statistics.mean(per):.2f}"
        )

    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="data_extender.telecom.telecom_stats",
        description="Validate and summarize a generated telecom dataset.",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=str(Path("tracer") / "envs" / "telecom" / "data"),
        help="Directory holding <split>/customers.json, billing.json and "
        "support_tickets.json, e.g. the extender's --out directory.",
    )
    parser.add_argument("--split", choices=["test", "train"], default="test")
    parser.add_argument(
        "--catalog",
        type=str,
        default=str(Path("tracer") / "envs" / "telecom" / "data"),
        help="Directory holding services.json and devices.json.",
    )
    parser.add_argument(
        "--max-errors", type=int, default=25, help="Max validation errors to print"
    )
    args = parser.parse_args()

    return print_stats(
        Path(args.path).resolve(),
        args.split,
        catalog_dir=Path(args.catalog).resolve(),
        max_errors=int(args.max_errors),
    )


if __name__ == "__main__":
    raise SystemExit(main())
