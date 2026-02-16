"""Tests for helpers/database.py — happy path + edge cases."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Use a temp directory for each test so tests are isolated."""
    import helpers.database as db_mod
    orig_dir = db_mod.DB_DIR
    orig_path = db_mod.DB_PATH
    db_mod.DB_DIR = tmp_path
    db_mod.DB_PATH = tmp_path / "rigbooks.db"
    try:
        db_mod.init_db()
        yield tmp_path
    finally:
        db_mod.DB_DIR = orig_dir
        db_mod.DB_PATH = orig_path


# ── Fiscal Years ──────────────────────────────────────────────────────────

class TestFiscalYears:
    def test_default_fiscal_year_created(self, tmp_db):
        from helpers.database import list_fiscal_years
        years = list_fiscal_years()
        assert any(y["name"] == "2024-2025" for y in years)

    def test_get_fiscal_year_auto_creates(self, tmp_db):
        from helpers.database import get_fiscal_year_id
        fy_id = get_fiscal_year_id("2025-2026")
        assert fy_id > 0

    def test_get_same_fiscal_year_returns_same_id(self, tmp_db):
        from helpers.database import get_fiscal_year_id
        id1 = get_fiscal_year_id("2024-2025")
        id2 = get_fiscal_year_id("2024-2025")
        assert id1 == id2


# ── Transactions ──────────────────────────────────────────────────────────

class TestTransactions:
    def test_upsert_and_get(self, tmp_db):
        from helpers.database import get_transactions, upsert_transactions
        df = pd.DataFrame([
            {"date": "2025-01-15", "description": "SHELL GAS", "debit": 80.0, "credit": 0,
             "cra_category": "Fuel & Petroleum", "itc_pct": 1.0, "itc_amount": 3.81,
             "is_personal": False, "needs_review": False, "notes": ""},
        ])
        count = upsert_transactions("2024-2025", df)
        assert count == 1
        result = get_transactions("2024-2025")
        assert len(result) == 1
        assert result.iloc[0]["description"] == "SHELL GAS"

    def test_upsert_replaces_duplicates(self, tmp_db):
        from helpers.database import get_transactions, upsert_transactions
        df = pd.DataFrame([
            {"date": "2025-01-15", "description": "SHELL GAS", "debit": 80.0, "credit": 0,
             "cra_category": "Fuel & Petroleum", "itc_pct": 1.0, "itc_amount": 3.81,
             "is_personal": False, "needs_review": False, "notes": ""},
        ])
        upsert_transactions("2024-2025", df)
        upsert_transactions("2024-2025", df)  # Same data again
        result = get_transactions("2024-2025")
        assert len(result) == 1  # No duplicates

    def test_empty_dataframe_returns_empty(self, tmp_db):
        from helpers.database import get_transactions
        result = get_transactions("2024-2025")
        assert result.empty or len(result) == 0

    def test_bulk_update_categories(self, tmp_db):
        import helpers.database as db
        df = pd.DataFrame([
            {"date": "2025-01-15", "description": "UNKNOWN", "debit": 50.0, "credit": 0,
             "cra_category": "Other / Unclassified", "itc_pct": 1.0, "itc_amount": 2.38,
             "is_personal": False, "needs_review": False, "notes": ""},
        ])
        db.upsert_transactions("2024-2025", df)
        txns = db.get_transactions("2024-2025")
        txn_id = int(txns.iloc[0]["id"])

        db.bulk_update_categories([{
            "id": txn_id, "cra_category": "Equipment & Supplies",
            "itc_pct": 1.0, "itc_amount": 2.38,
        }])

        updated = db.get_transactions("2024-2025")
        assert updated.iloc[0]["cra_category"] == "Equipment & Supplies"


# ── Cash Expenses ─────────────────────────────────────────────────────────

class TestCashExpenses:
    def test_add_and_get(self, tmp_db):
        from helpers.database import add_cash_expense, get_cash_expenses
        row_id = add_cash_expense("2024-2025", "2025-03-01", "Safety boots", 150.0, "PPE & Safety", True)
        assert row_id > 0
        items = get_cash_expenses("2024-2025")
        assert len(items) == 1
        assert items[0]["description"] == "Safety boots"

    def test_delete(self, tmp_db):
        from helpers.database import add_cash_expense, delete_cash_expense, get_cash_expenses
        row_id = add_cash_expense("2024-2025", "2025-03-01", "Lunch", 25.0, "Meals", True)
        delete_cash_expense(row_id)
        assert len(get_cash_expenses("2024-2025")) == 0

    def test_empty_fiscal_year(self, tmp_db):
        from helpers.database import get_cash_expenses
        assert get_cash_expenses("2024-2025") == []


# ── Phone Bills ───────────────────────────────────────────────────────────

class TestPhoneBills:
    def test_save_and_get(self, tmp_db):
        from helpers.database import get_phone_bills, save_phone_bills
        MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
        data = {
            "greg": {"months": {m: 78.88 for m in MONTHS}, "business_pct": 60},
            "lilibeth": {"months": {m: 90.12 for m in MONTHS}, "business_pct": 60},
        }
        save_phone_bills("2024-2025", data)
        result = get_phone_bills("2024-2025")
        assert abs(sum(result["greg"]["months"].values()) - 78.88 * 12) < 0.01
        assert result["greg"]["business_pct"] == 60

    def test_defaults_for_missing_person(self, tmp_db):
        from helpers.database import get_phone_bills
        result = get_phone_bills("2024-2025")
        assert "greg" in result
        assert "lilibeth" in result
        assert all(v == 0.0 for v in result["greg"]["months"].values())

    def test_upsert_overwrites(self, tmp_db):
        from helpers.database import get_phone_bills, save_phone_bills
        MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
        save_phone_bills("2024-2025", {"greg": {"months": {m: 50.0 for m in MONTHS}, "business_pct": 100}})
        save_phone_bills("2024-2025", {"greg": {"months": {m: 75.0 for m in MONTHS}, "business_pct": 80}})
        result = get_phone_bills("2024-2025")
        assert result["greg"]["months"]["Jan"] == 75.0
        assert result["greg"]["business_pct"] == 80


# ── Vehicle ───────────────────────────────────────────────────────────────

class TestVehicle:
    def test_save_and_get_summary(self, tmp_db):
        from helpers.database import get_vehicle_summary, save_vehicle_summary
        save_vehicle_summary("2024-2025", 97178, 111306, 12041.21)
        result = get_vehicle_summary("2024-2025")
        assert result["start_odo"] == 97178
        assert result["end_odo"] == 111306
        assert abs(result["fuel_total"] - 12041.21) < 0.01

    def test_add_and_get_trips(self, tmp_db):
        from helpers.database import add_vehicle_trip, get_vehicle_trips
        add_vehicle_trip("2024-2025", "2025-01-15", "Sherwood Park", "Redwater", 45.0, "Operations", 98000)
        trips = get_vehicle_trips("2024-2025")
        assert len(trips) == 1
        assert trips[0]["to_loc"] == "Redwater"

    def test_delete_trip(self, tmp_db):
        from helpers.database import add_vehicle_trip, delete_vehicle_trip, get_vehicle_trips
        tid = add_vehicle_trip("2024-2025", "2025-01-15", "A", "B", 10.0, "Test", 0)
        delete_vehicle_trip(tid)
        assert len(get_vehicle_trips("2024-2025")) == 0


# ── Other Expenses ────────────────────────────────────────────────────────

class TestOtherExpenses:
    def test_add_and_get_by_subcategory(self, tmp_db):
        from helpers.database import add_other_expense, get_other_expenses
        add_other_expense("2024-2025", "training", "2025-02-01", "H2S Alive", 350.0, True)
        add_other_expense("2024-2025", "ppe", "2025-02-01", "Hard hat", 45.0, True)
        result = get_other_expenses("2024-2025")
        assert len(result["training"]) == 1
        assert len(result["ppe"]) == 1
        assert result["training"][0]["description"] == "H2S Alive"

    def test_empty_subcategories(self, tmp_db):
        from helpers.database import get_other_expenses
        result = get_other_expenses("2024-2025")
        assert result == {"training": [], "ppe": [], "software": [], "other": []}
