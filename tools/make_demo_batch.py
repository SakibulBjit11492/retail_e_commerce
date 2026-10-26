"""Generate a small, deterministic "new month" batch (January 2026) for the live demo.

The batch continues the NOVACART_MINI_V2 dataset: new IDs follow the existing maximum IDs,
prices come from the product list, and it reuses existing customers so that "returning
customer" metrics move. It also plants a few realistic problems for Silver to handle.

Usage:
    python tools/make_demo_batch.py DATASET_DIR [OUTPUT_DIR]

DATASET_DIR must contain the 2025 CSV files (including products_2025_USD.csv).
OUTPUT_DIR defaults to data/demo_batch_2026_01. Python 3.10+, no third-party packages.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

SEED = 20260101
TAG = "NOVACART_MINI_V2"
MONTH = "2026-01"
SUFFIX = "2026_01_USD"
N_NEW_CUSTOMERS = 12
N_ORDERS = 40
N_BROWSE_SESSIONS = 60
FMT = "%Y-%m-%d %H:%M:%S"

COLUMNS = {
    "customers": ["dataset_tag", "record_month", "customer_id", "customer_label", "signup_date", "country_code",
                  "country", "city", "customer_tier", "signup_channel"],
    "orders": ["dataset_tag", "record_month", "order_id", "order_datetime", "customer_id", "order_status",
               "sales_channel", "country_code", "currency", "order_total_usd", "campaign_id", "session_id"],
    "order_items": ["dataset_tag", "record_month", "order_item_id", "order_id", "product_id", "quantity",
                    "unit_price_usd", "discount_pct", "line_total_usd"],
    "payments": ["dataset_tag", "record_month", "payment_id", "order_id", "payment_datetime", "payment_status",
                 "payment_method", "currency", "amount_usd"],
    "website_sessions": ["dataset_tag", "record_month", "session_id", "session_start", "customer_id",
                         "country_code", "sales_channel", "device_type", "campaign_id", "order_id"],
    "website_events": ["dataset_tag", "record_month", "event_id", "session_id", "event_datetime", "event_type",
                       "product_id", "order_id"],
}


def read(directory, name):
    with (directory / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def next_id(rows, column, prefix):
    width = len(rows[0][column]) - len(prefix)
    current = max(int(r[column][len(prefix):]) for r in rows)

    def generator():
        nonlocal current
        current += 1
        return f"{prefix}{current:0{width}d}"
    return generator


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def main(dataset_dir, out_dir):
    rng = random.Random(SEED)
    customers = read(dataset_dir, "customers_2025_USD.csv")
    products = [p for p in read(dataset_dir, "products_2025_USD.csv") if p["product_status"] == "active"]
    orders_2025 = read(dataset_dir, "orders_2025_USD.csv")
    items_2025 = read(dataset_dir, "order_items_2025_USD.csv")
    payments_2025 = read(dataset_dir, "payments_2025_USD.csv")
    sessions_2025 = read(dataset_dir, "website_sessions_2025_USD.csv")
    events_2025 = read(dataset_dir, "website_events_2025_USD.csv")

    new_customer_id = next_id(customers, "customer_id", "C")
    new_order_id = next_id(orders_2025, "order_id", "ORD")
    new_item_id = next_id(items_2025, "order_item_id", "LI")
    new_payment_id = next_id(payments_2025, "payment_id", "PAY")
    new_session_id = next_id(sessions_2025, "session_id", "SES")
    new_event_id = next_id(events_2025, "event_id", "EVT")

    out = defaultdict(list)
    base = lambda **kw: {"dataset_tag": TAG, "record_month": MONTH, **kw}  # noqa: E731

    # --- customers: a few new sign-ups in January 2026 -----------------------------------------
    places = sorted({(c["country_code"], c["country"], c["city"]) for c in customers})
    new_customers = []
    for _ in range(N_NEW_CUSTOMERS):
        cid = new_customer_id()
        cc, country, city = rng.choice(places)
        row = base(customer_id=cid, customer_label=f"Customer {cid[1:]}",
                   signup_date=f"2026-01-{rng.randint(1, 20):02d}", country_code=cc, country=country, city=city,
                   customer_tier=rng.choices(["basic", "silver", "gold", "premium"], [50, 29, 16, 5])[0],
                   signup_channel=rng.choice(["web", "mobile_app", "marketplace"]))
        out["customers"].append(row)
        new_customers.append(row)

    # Returning buyers: existing customers who already had a paid order in 2025.
    paid_2025 = sorted({o["customer_id"] for o in orders_2025
                        if o["order_status"].strip().lower() in ("paid", "completed") and o["customer_id"]})
    by_id = {c["customer_id"]: c for c in customers}
    returning = [by_id[c] for c in rng.sample(paid_2025, 22)]

    buyers = new_customers + returning + rng.sample(returning, 6)  # 40 orders, some customers buy twice
    rng.shuffle(buyers)
    campaigns = ["ORGANIC"] * 6 + ["DIRECT"] * 4 + [f"MKT{n:03d}" for n in range(1, 16)]

    # --- orders, items, payments, linked sessions and events -----------------------------------
    def add_events(session_id, start, product_id, steps, order_id=""):
        for i, event_type in enumerate(steps):
            out["website_events"].append(base(
                event_id=new_event_id(), session_id=session_id,
                event_datetime=(start + timedelta(minutes=3 * i)).strftime(FMT), event_type=event_type,
                product_id=product_id, order_id=order_id if event_type == "purchase" else ""))

    for n, customer in enumerate(buyers[:N_ORDERS]):
        oid = new_order_id()
        ordered_at = datetime(2026, 1, 1) + timedelta(days=rng.randint(0, 27), hours=rng.randint(8, 22),
                                                        minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        status = rng.choices(["paid", "cancelled", "returned"], [86, 9, 5])[0]
        channel = rng.choices(["web", "mobile_app", "marketplace"], [35, 25, 40])[0]
        campaign = rng.choice(campaigns)

        total = Decimal("0.00")
        first_product = None
        for product in rng.sample(products, rng.choices([1, 2, 3], [70, 24, 6])[0]):
            qty = rng.choices([1, 2, 3], [80, 15, 5])[0]
            discount = rng.choices([0, 5, 10, 15, 20], [55, 17, 15, 9, 4])[0]
            price = money(product["list_price_usd"])
            line = money(price * qty * (Decimal(100 - discount) / 100))
            total += line
            first_product = first_product or product["product_id"]
            out["order_items"].append(base(order_item_id=new_item_id(), order_id=oid,
                                           product_id=product["product_id"], quantity=qty, unit_price_usd=price,
                                           discount_pct=discount, line_total_usd=line))

        session_id = ""
        if channel != "marketplace":
            session_id = new_session_id()
            start = ordered_at - timedelta(minutes=9)
            out["website_sessions"].append(base(
                session_id=session_id, session_start=start.strftime(FMT), customer_id=customer["customer_id"],
                country_code=customer["country_code"], sales_channel=channel,
                device_type="mobile" if channel == "mobile_app" else rng.choice(["desktop", "mobile", "tablet"]),
                campaign_id=campaign, order_id=oid))
            add_events(session_id, start, first_product, ["view", "add_to_cart", "checkout", "purchase"], oid)

        out["orders"].append(base(order_id=oid, order_datetime=ordered_at.strftime(FMT),
                                  customer_id=customer["customer_id"], order_status=status, sales_channel=channel,
                                  country_code=customer["country_code"], currency="USD", order_total_usd=total,
                                  campaign_id=campaign, session_id=session_id))

        method = rng.choice(["credit_card", "digital_wallet", "debit_card", "bank_transfer", "cash_on_delivery"])
        pay = lambda when, st: out["payments"].append(base(  # noqa: E731
            payment_id=new_payment_id(), order_id=oid, payment_datetime=when.strftime(FMT), payment_status=st,
            payment_method=method, currency="USD", amount_usd=total))
        if status == "cancelled":
            pay(ordered_at, "failed")
        else:
            pay(ordered_at, "captured")
            if status == "returned":
                pay(ordered_at + timedelta(days=rng.randint(2, 6)), "refunded")

    # --- browsing-only sessions (not converted), anonymous like in the 2025 data ----------------
    for _ in range(N_BROWSE_SESSIONS):
        sid = new_session_id()
        start = datetime(2026, 1, 1) + timedelta(days=rng.randint(0, 27), hours=rng.randint(7, 23),
                                                  minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        cc = rng.choice(places)[0]
        channel = rng.choice(["web", "web", "mobile_app"])
        out["website_sessions"].append(base(
            session_id=sid, session_start=start.strftime(FMT), customer_id="", country_code=cc,
            sales_channel=channel,
            device_type="mobile" if channel == "mobile_app" else rng.choice(["desktop", "mobile", "tablet"]),
            campaign_id=rng.choice(campaigns), order_id=""))
        steps = rng.choices([["view"], ["view", "add_to_cart"], ["view", "add_to_cart", "checkout"]], [64, 22, 14])[0]
        add_events(sid, start, rng.choice(products)["product_id"], steps)

    # --- planted data problems -----------------------------------------------------------------
    new_orders = out["orders"]
    notes = []
    # 1) inconsistent status spelling
    completed = next(o for o in new_orders if o["order_status"] == "paid")
    completed["order_status"] = "Completed"
    notes.append(f"{completed['order_id']}: status spelled 'Completed' (Silver maps it to 'paid')")
    # 2) US-style date format
    us_order = next(o for o in new_orders if o is not completed)
    us_order["order_datetime"] = datetime.strptime(us_order["order_datetime"], FMT).strftime("%m/%d/%Y %H:%M:%S")
    notes.append(f"{us_order['order_id']}: order_datetime in MM/DD/YYYY format")
    # 3) missing customer_id that can be recovered from the linked session
    blank = next(o for o in new_orders if o["session_id"] and o is not us_order and o is not completed)
    blank["customer_id"] = ""
    notes.append(f"{blank['order_id']}: blank customer_id, recoverable from session {blank['session_id']}")
    # 4) event with an unknown product key (quarantined in Silver)
    bad_event = next(e for e in out["website_events"] if e["event_type"] == "view" and not e["order_id"])
    bad_event["product_id"] = "P_MISSING"
    notes.append(f"{bad_event['event_id']}: product_id P_MISSING (goes to silver_rejected_website_events)")
    # 5) exact re-send of a 2025 order (duplicate across files)
    dup = dict(next(o for o in orders_2025 if o["order_id"] == "ORD0031451"))
    out["orders"].append(dup)
    notes.append(f"{dup['order_id']}: 2025 order re-sent unchanged (Silver keeps one row)")
    # 6) late return of a December 2025 order: order re-sent as 'returned' + refund in January
    payments_by_order = defaultdict(list)
    for p in payments_2025:
        payments_by_order[p["order_id"]].append(p)
    late = next(o for o in sorted(orders_2025, key=lambda o: o["order_id"], reverse=True)
                if o["order_status"] == "paid" and o["record_month"] == "2025-12"
                and [p["payment_status"] for p in payments_by_order[o["order_id"]]] == ["captured"]
                and o["order_id"] != dup["order_id"])
    returned = dict(late, order_status="returned")
    out["orders"].append(returned)
    captured = payments_by_order[late["order_id"]][0]
    out["payments"].append(base(payment_id=new_payment_id(), order_id=late["order_id"],
                                payment_datetime="2026-01-05 10:15:00", payment_status="refunded",
                                payment_method=captured["payment_method"], currency="USD",
                                amount_usd=captured["amount_usd"]))
    notes.append(f"{late['order_id']}: Dec-2025 order now 'returned' with a refund of "
                 f"{captured['amount_usd']} USD dated 2026-01-05 (newer version wins in Silver)")

    # --- write files + manifest ----------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    for entity, columns in COLUMNS.items():
        path = out_dir / f"{entity}_{SUFFIX}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(out[entity])

    signed = {"captured": 1, "refunded": -1}
    net_change = sum(Decimal(p["amount_usd"]) * signed.get(p["payment_status"], 0) for p in out["payments"])
    manifest = {
        "batch": "demo_batch_2026_01",
        "rows": {entity: len(out[entity]) for entity in COLUMNS},
        "new_orders": N_ORDERS,
        "expected_net_revenue_change_usd": str(net_change),
        "planted_problems": notes,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: python tools/make_demo_batch.py DATASET_DIR [OUTPUT_DIR]")
    root = Path(__file__).resolve().parents[1]
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else root / "data" / "demo_batch_2026_01")
