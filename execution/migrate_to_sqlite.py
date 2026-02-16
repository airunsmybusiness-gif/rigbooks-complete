#!/usr/bin/env python3
"""
RigBooks Migration — Pickle/JSON → SQLite

One-shot script. Reads existing data files and inserts into rigbooks.db.
Safe to re-run (uses INSERT OR REPLACE for transactions).

Usage:
    cd ~/Projects/rigbooks && python3 execution/migrate_to_sqlite.py
"""
import json
import logging
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from helpers.database import (
    add_cash_expense,
    add_other_expense,
    add_personal_expense,
    add_vehicle_trip,
    get_fiscal_year_id,
    init_db,
    save_home_office,
    save_phone_bills,
    save_vehicle_summary,
    upsert_transactions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate")

DATA_DIR = PROJECT_ROOT / "data"
FISCAL_YEARS = ["2024-2025", "2025-2026"]


def migrate_transactions(fy_name: str) -> int:
    """Migrate classified_df.pkl (or corporate_df.pkl) into transactions table."""
    fy_dir = DATA_DIR / fy_name

    # Try classified first (has categories), fall back to corporate
    classified_path = fy_dir / "classified_df.pkl"
    corporate_path = fy_dir / "corporate_df.pkl"
    csv_backup_path = fy_dir / "classified_backup.csv"

    df = None
    source = ""

    if classified_path.exists():
        try:
            df = pd.read_pickle(classified_path)
            source = "classified_df.pkl"
        except Exception as e:
            logger.warning("ANNEALING: Failed to read %s: %s", classified_path, e)

    if df is None and csv_backup_path.exists():
        try:
            df = pd.read_csv(csv_backup_path)
            source = "classified_backup.csv"
        except Exception as e:
            logger.warning("ANNEALING: Failed to read %s: %s", csv_backup_path, e)

    if df is None and corporate_path.exists():
        try:
            df = pd.read_pickle(corporate_path)
            source = "corporate_df.pkl (unclassified)"
        except Exception as e:
            logger.warning("ANNEALING: Failed to read %s: %s", corporate_path, e)

    if df is None or df.empty:
        logger.info("No transaction data found for FY %s — skipping", fy_name)
        return 0

    logger.info("Migrating %d transactions from %s for FY %s", len(df), source, fy_name)

    # Ensure required columns exist with defaults
    defaults = {
        "cra_category": "Other / Unclassified",
        "itc_pct": 0.0,
        "itc_amount": 0.0,
        "is_personal": False,
        "needs_review": False,
        "notes": "",
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
            logger.info("ANNEALING: Added missing column '%s' with default", col)

    # Fill NaN values
    df = df.fillna({"debit": 0, "credit": 0, "notes": "", "cra_category": "Other / Unclassified"})

    count = upsert_transactions(fy_name, df)
    logger.info("✅ Migrated %d transactions for FY %s", count, fy_name)
    return count


def migrate_json_list(
    fy_name: str, filename: str, add_func: callable, field_map: dict[str, str]
) -> int:
    """Generic migration for JSON list files (cash_expenses, personal_expenses)."""
    json_path = DATA_DIR / fy_name / filename
    if not json_path.exists():
        logger.info("No %s found for FY %s — skipping", filename, fy_name)
        return 0

    try:
        with open(json_path, encoding="utf-8") as f:
            items = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ANNEALING: Failed to read %s: %s", json_path, e)
        return 0

    if not isinstance(items, list) or not items:
        return 0

    count = 0
    for item in items:
        kwargs = {}
        for db_field, json_field in field_map.items():
            kwargs[db_field] = item.get(json_field, "")
        try:
            add_func(fy_name, **kwargs)
            count += 1
        except Exception as e:
            logger.error("ANNEALING: Failed to insert %s item: %s | data: %s", filename, e, item)

    logger.info("✅ Migrated %d items from %s for FY %s", count, filename, fy_name)
    return count


def migrate_phone_bills(fy_name: str) -> int:
    """Migrate phone_bill.json into phone_bills table."""
    # Check per-FY file first
    json_path = DATA_DIR / fy_name / "phone_bill.json"
    if not json_path.exists():
        # Try root-level rigbooks_data.json
        root_json = DATA_DIR.parent / "rigbooks_data.json"
        if root_json.exists():
            try:
                with open(root_json, encoding="utf-8") as f:
                    root_data = json.load(f)
                phone_bills_list = root_data.get("phone_bills", [])
                if phone_bills_list:
                    return _migrate_phone_from_root(fy_name, phone_bills_list)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("ANNEALING: Failed to read rigbooks_data.json: %s", e)
        logger.info("No phone bill data found for FY %s — skipping", fy_name)
        return 0

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ANNEALING: Failed to read %s: %s", json_path, e)
        return 0

    if not data:
        return 0

    # Handle both formats:
    # Format A: {"greg": {"months": {...}, "business_pct": 100}, "lilibeth": {...}}
    # Format B: {"greg": {"monthly": 78.88, "business_pct": 100}, ...}
    MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov"]

    phone_data: dict = {}
    for person in ("greg", "lilibeth"):
        person_data = data.get(person, {})
        if "months" in person_data:
            phone_data[person] = person_data
        elif "monthly" in person_data:
            # Convert flat monthly amount to per-month
            monthly_amt = float(person_data.get("monthly", 0))
            phone_data[person] = {
                "months": {m: monthly_amt for m in MONTHS},
                "business_pct": int(person_data.get("business_pct", 100)),
            }
        else:
            phone_data[person] = {
                "months": {m: 0.0 for m in MONTHS},
                "business_pct": 100,
            }

    save_phone_bills(fy_name, phone_data)
    count = sum(1 for p in phone_data.values() for m, a in p["months"].items() if a > 0)
    logger.info("✅ Migrated phone bills for FY %s (%d non-zero months)", fy_name, count)
    return count


def _migrate_phone_from_root(fy_name: str, phone_list: list[dict]) -> int:
    """Migrate phone data from rigbooks_data.json format."""
    MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov"]
    phone_data: dict = {}
    for entry in phone_list:
        owner = entry.get("owner", "").lower()
        if owner not in ("greg", "lilibeth"):
            continue
        total = float(entry.get("amount", 0))
        monthly = total / 12.0 if total > 0 else 0.0
        biz_pct = int(entry.get("biz_pct", 100))
        phone_data[owner] = {
            "months": {m: round(monthly, 2) for m in MONTHS},
            "business_pct": biz_pct,
        }

    if phone_data:
        save_phone_bills(fy_name, phone_data)
        logger.info("✅ Migrated phone bills from rigbooks_data.json for FY %s", fy_name)
        return len(phone_data)
    return 0


def migrate_vehicle(fy_name: str) -> int:
    """Migrate vehicle_mileage.json into vehicle_summary + vehicle_trips."""
    json_path = DATA_DIR / fy_name / "vehicle_mileage.json"
    if not json_path.exists():
        logger.info("No vehicle data found for FY %s — skipping", fy_name)
        return 0

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ANNEALING: Failed to read %s: %s", json_path, e)
        return 0

    save_vehicle_summary(
        fy_name,
        int(data.get("start_odo", 0)),
        int(data.get("end_odo", 0)),
        float(data.get("fuel_total", 0)),
    )

    trips = data.get("trips", [])
    count = 0
    for trip in trips:
        try:
            add_vehicle_trip(
                fy_name,
                date=trip.get("date", ""),
                from_loc=trip.get("from", ""),
                to_loc=trip.get("to", ""),
                km=float(trip.get("km", 0)),
                purpose=trip.get("purpose", ""),
                odometer=int(trip.get("odometer", 0)),
            )
            count += 1
        except Exception as e:
            logger.error("ANNEALING: Failed to insert trip: %s | data: %s", e, trip)

    logger.info("✅ Migrated vehicle summary + %d trips for FY %s", count, fy_name)
    return count


def migrate_other_expenses(fy_name: str) -> int:
    """Migrate other_expenses.json into other_expenses table."""
    json_path = DATA_DIR / fy_name / "other_expenses.json"
    if not json_path.exists():
        return 0

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ANNEALING: Failed to read %s: %s", json_path, e)
        return 0

    if not isinstance(data, dict):
        return 0

    count = 0
    for sub_cat, items in data.items():
        if not isinstance(items, list):
            continue
        for item in items:
            try:
                add_other_expense(
                    fy_name,
                    sub_category=sub_cat,
                    date=item.get("date", ""),
                    description=item.get("description", ""),
                    amount=float(item.get("amount", 0)),
                    has_receipt=bool(item.get("has_receipt", True)),
                )
                count += 1
            except Exception as e:
                logger.error("ANNEALING: Failed to insert other expense: %s | data: %s", e, item)

    logger.info("✅ Migrated %d other expenses for FY %s", count, fy_name)
    return count


def migrate_home_office() -> int:
    """Migrate home_office from rigbooks_data.json."""
    root_json = DATA_DIR.parent / "rigbooks_data.json"
    if not root_json.exists():
        return 0

    try:
        with open(root_json, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("ANNEALING: Failed to read rigbooks_data.json: %s", e)
        return 0

    ho = data.get("home_office", {})
    if not ho or all(v == 0 for v in ho.values()):
        return 0

    save_home_office("2024-2025", ho)
    logger.info("✅ Migrated home office data")
    return 1


def main() -> None:
    """Run full migration."""
    logger.info("=" * 60)
    logger.info("RigBooks Migration — Pickle/JSON → SQLite")
    logger.info("=" * 60)

    init_db()

    total = 0
    for fy in FISCAL_YEARS:
        logger.info("--- Migrating FY %s ---", fy)
        total += migrate_transactions(fy)
        total += migrate_json_list(
            fy, "cash_expenses.json", add_cash_expense,
            {"date": "date", "description": "description", "amount": "amount",
             "category": "category", "has_receipt": "has_receipt"},
        )
        total += migrate_json_list(
            fy, "personal_expenses.json", add_personal_expense,
            {"date": "date", "description": "description", "amount": "amount",
             "category": "category", "has_receipt": "has_receipt", "card": "card"},
        )
        total += migrate_phone_bills(fy)
        total += migrate_vehicle(fy)
        total += migrate_other_expenses(fy)

    total += migrate_home_office()

    logger.info("=" * 60)
    logger.info("Migration complete! Total items migrated: %d", total)
    logger.info("Database: %s", DATA_DIR / "rigbooks.db")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
