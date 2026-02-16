"""
RigBooks Database Layer — SQLite persistence for CRA-compliant bookkeeping.

Cape Bretoner's Oilfield Services Ltd.
Replaces pickle/JSON with a single rigbooks.db file.
"""
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

DB_DIR = Path("data")
DB_PATH = DB_DIR / "rigbooks.db"

# ════════════════════════════════════════════════════════════════════════════
#  CONNECTION MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════


@contextmanager
def get_connection() -> sqlite3.Connection:
    """Yield a SQLite connection with WAL mode and foreign keys enabled."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist. Idempotent."""
    with get_connection() as conn:
        conn.executescript(_SCHEMA_SQL)
        _ensure_default_fiscal_year(conn)
    logger.info("Database initialized at %s", DB_PATH)


def _ensure_default_fiscal_year(conn: sqlite3.Connection) -> None:
    """Insert 2024-2025 fiscal year if not present."""
    row = conn.execute(
        "SELECT id FROM fiscal_years WHERE name = ?", ("2024-2025",)
    ).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO fiscal_years (name, start_date, end_date) VALUES (?, ?, ?)",
            ("2024-2025", "2024-12-01", "2025-11-30"),
        )


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fiscal_years (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    debit REAL NOT NULL DEFAULT 0,
    credit REAL NOT NULL DEFAULT 0,
    cra_category TEXT NOT NULL DEFAULT 'Other / Unclassified',
    itc_pct REAL NOT NULL DEFAULT 0,
    itc_amount REAL NOT NULL DEFAULT 0,
    is_personal INTEGER NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE(fiscal_year_id, date, description, debit, credit)
);

CREATE TABLE IF NOT EXISTS cash_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    has_receipt INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS personal_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    has_receipt INTEGER NOT NULL DEFAULT 1,
    card TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS vehicle_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL UNIQUE,
    start_odo INTEGER NOT NULL DEFAULT 0,
    end_odo INTEGER NOT NULL DEFAULT 0,
    fuel_total REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS vehicle_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    from_loc TEXT NOT NULL DEFAULT '',
    to_loc TEXT NOT NULL DEFAULT '',
    km REAL NOT NULL DEFAULT 0,
    purpose TEXT NOT NULL DEFAULT '',
    odometer INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS phone_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    person TEXT NOT NULL,
    month TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    business_pct INTEGER NOT NULL DEFAULT 100,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id),
    UNIQUE(fiscal_year_id, person, month)
);

CREATE TABLE IF NOT EXISTS other_expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL,
    sub_category TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    has_receipt INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS home_office (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL UNIQUE,
    rent REAL NOT NULL DEFAULT 0,
    property_tax REAL NOT NULL DEFAULT 0,
    insurance REAL NOT NULL DEFAULT 0,
    electricity REAL NOT NULL DEFAULT 0,
    gas REAL NOT NULL DEFAULT 0,
    water REAL NOT NULL DEFAULT 0,
    internet REAL NOT NULL DEFAULT 0,
    office_pct REAL NOT NULL DEFAULT 10,
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(id)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    full_name TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_fy ON transactions(fiscal_year_id);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(cra_category);
CREATE INDEX IF NOT EXISTS idx_cash_expenses_fy ON cash_expenses(fiscal_year_id);
CREATE INDEX IF NOT EXISTS idx_personal_expenses_fy ON personal_expenses(fiscal_year_id);
CREATE INDEX IF NOT EXISTS idx_other_expenses_fy ON other_expenses(fiscal_year_id);
"""


# ════════════════════════════════════════════════════════════════════════════
#  FISCAL YEAR HELPERS
# ════════════════════════════════════════════════════════════════════════════


def get_fiscal_year_id(name: str) -> int:
    """Get fiscal year ID by name, creating it if needed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM fiscal_years WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        # Auto-create: parse "YYYY-YYYY" → Dec 1 start, Nov 30 end
        parts = name.split("-")
        start_year = int(parts[0])
        end_year = int(parts[1]) if len(parts) > 1 else start_year + 1
        conn.execute(
            "INSERT INTO fiscal_years (name, start_date, end_date) VALUES (?, ?, ?)",
            (name, f"{start_year}-12-01", f"{end_year}-11-30"),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def list_fiscal_years() -> list[dict[str, Any]]:
    """Return all fiscal years as list of dicts."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, start_date, end_date FROM fiscal_years ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════════════════
#  TRANSACTIONS (bank statement data)
# ════════════════════════════════════════════════════════════════════════════


def get_transactions(fy_name: str) -> pd.DataFrame:
    """Load all transactions for a fiscal year as a DataFrame."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM transactions WHERE fiscal_year_id = ? ORDER BY date DESC, id",
            conn,
            params=(fy_id,),
        )
    if df.empty:
        return pd.DataFrame(
            columns=[
                "id", "date", "description", "debit", "credit",
                "cra_category", "itc_pct", "itc_amount",
                "is_personal", "needs_review", "notes",
            ]
        )
    # Convert int booleans back
    for col in ("is_personal", "needs_review"):
        if col in df.columns:
            df[col] = df[col].astype(bool)
    return df


def upsert_transactions(fy_name: str, df: pd.DataFrame) -> int:
    """Insert or replace transactions from a DataFrame. Returns count inserted."""
    fy_id = get_fiscal_year_id(fy_name)
    count = 0
    with get_connection() as conn:
        for _, row in df.iterrows():
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO transactions
                    (fiscal_year_id, date, description, debit, credit,
                     cra_category, itc_pct, itc_amount, is_personal, needs_review, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fy_id,
                        str(row.get("date", "")),
                        str(row.get("description", "")),
                        float(row.get("debit", 0)),
                        float(row.get("credit", 0)),
                        str(row.get("cra_category", "Other / Unclassified")),
                        float(row.get("itc_pct", 0)),
                        float(row.get("itc_amount", 0)),
                        int(bool(row.get("is_personal", False))),
                        int(bool(row.get("needs_review", False))),
                        str(row.get("notes", "") or ""),
                    ),
                )
                count += 1
            except sqlite3.Error as e:
                logger.error(
                    "ANNEALING: Failed to insert transaction: %s | row: %s",
                    e, row.to_dict(),
                )
    logger.info("Upserted %d transactions for FY %s", count, fy_name)
    return count


def update_transaction_category(
    txn_id: int, category: str, itc_pct: float, itc_amount: float
) -> None:
    """Update a single transaction's CRA category and ITC values."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE transactions
            SET cra_category = ?, itc_pct = ?, itc_amount = ?
            WHERE id = ?""",
            (category, itc_pct, itc_amount, txn_id),
        )


def bulk_update_categories(updates: list[dict[str, Any]]) -> int:
    """Batch update categories. Each dict needs: id, cra_category, itc_pct, itc_amount."""
    count = 0
    with get_connection() as conn:
        for u in updates:
            conn.execute(
                """UPDATE transactions
                SET cra_category = ?, itc_pct = ?, itc_amount = ?
                WHERE id = ?""",
                (u["cra_category"], u["itc_pct"], u["itc_amount"], u["id"]),
            )
            count += 1
    logger.info("Bulk updated %d transaction categories", count)
    return count


def delete_all_transactions(fy_name: str) -> int:
    """Delete all transactions for a fiscal year. Returns count deleted."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM transactions WHERE fiscal_year_id = ?", (fy_id,)
        )
        count = cursor.rowcount
    logger.info("Deleted %d transactions for FY %s", count, fy_name)
    return count


# ════════════════════════════════════════════════════════════════════════════
#  CASH EXPENSES
# ════════════════════════════════════════════════════════════════════════════


def get_cash_expenses(fy_name: str) -> list[dict[str, Any]]:
    """Return cash expenses for a fiscal year."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM cash_expenses WHERE fiscal_year_id = ? ORDER BY date DESC",
            (fy_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_cash_expense(
    fy_name: str, date: str, description: str, amount: float,
    category: str, has_receipt: bool = True,
) -> int:
    """Add a cash expense. Returns the new row ID."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO cash_expenses
            (fiscal_year_id, date, description, amount, category, has_receipt)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (fy_id, date, description, amount, category, int(has_receipt)),
        )
        return cursor.lastrowid or 0


def delete_cash_expense(expense_id: int) -> None:
    """Delete a cash expense by ID."""
    with get_connection() as conn:
        conn.execute("DELETE FROM cash_expenses WHERE id = ?", (expense_id,))


# ════════════════════════════════════════════════════════════════════════════
#  PERSONAL EXPENSES
# ════════════════════════════════════════════════════════════════════════════


def get_personal_expenses(fy_name: str) -> list[dict[str, Any]]:
    """Return personal bank/CC expenses for a fiscal year."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM personal_expenses WHERE fiscal_year_id = ? ORDER BY date DESC",
            (fy_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_personal_expense(
    fy_name: str, date: str, description: str, amount: float,
    category: str, has_receipt: bool = True, card: str = "",
) -> int:
    """Add a personal expense. Returns the new row ID."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO personal_expenses
            (fiscal_year_id, date, description, amount, category, has_receipt, card)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fy_id, date, description, amount, category, int(has_receipt), card),
        )
        return cursor.lastrowid or 0


def delete_personal_expense(expense_id: int) -> None:
    """Delete a personal expense by ID."""
    with get_connection() as conn:
        conn.execute("DELETE FROM personal_expenses WHERE id = ?", (expense_id,))


# ════════════════════════════════════════════════════════════════════════════
#  VEHICLE & MILEAGE
# ════════════════════════════════════════════════════════════════════════════


def get_vehicle_summary(fy_name: str) -> dict[str, Any]:
    """Return vehicle odometer/fuel summary for a fiscal year."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM vehicle_summary WHERE fiscal_year_id = ?", (fy_id,)
        ).fetchone()
        if row:
            return dict(row)
        return {"start_odo": 0, "end_odo": 0, "fuel_total": 0.0}


def save_vehicle_summary(
    fy_name: str, start_odo: int, end_odo: int, fuel_total: float
) -> None:
    """Upsert vehicle summary for a fiscal year."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO vehicle_summary (fiscal_year_id, start_odo, end_odo, fuel_total)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fiscal_year_id)
            DO UPDATE SET start_odo=excluded.start_odo,
                          end_odo=excluded.end_odo,
                          fuel_total=excluded.fuel_total""",
            (fy_id, start_odo, end_odo, fuel_total),
        )


def get_vehicle_trips(fy_name: str) -> list[dict[str, Any]]:
    """Return all vehicle trips for a fiscal year."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM vehicle_trips WHERE fiscal_year_id = ? ORDER BY date DESC",
            (fy_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_vehicle_trip(
    fy_name: str, date: str, from_loc: str, to_loc: str,
    km: float, purpose: str, odometer: int,
) -> int:
    """Add a vehicle trip. Returns the new row ID."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO vehicle_trips
            (fiscal_year_id, date, from_loc, to_loc, km, purpose, odometer)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fy_id, date, from_loc, to_loc, km, purpose, odometer),
        )
        return cursor.lastrowid or 0


def delete_vehicle_trip(trip_id: int) -> None:
    """Delete a vehicle trip by ID."""
    with get_connection() as conn:
        conn.execute("DELETE FROM vehicle_trips WHERE id = ?", (trip_id,))


# ════════════════════════════════════════════════════════════════════════════
#  PHONE BILLS
# ════════════════════════════════════════════════════════════════════════════

MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov"]


def get_phone_bills(fy_name: str) -> dict[str, dict[str, Any]]:
    """Return phone bill data as {person: {months: {...}, business_pct: int}}."""
    fy_id = get_fiscal_year_id(fy_name)
    result: dict[str, dict[str, Any]] = {}
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT person, month, amount, business_pct FROM phone_bills WHERE fiscal_year_id = ?",
            (fy_id,),
        ).fetchall()

    for row in rows:
        person = row["person"]
        if person not in result:
            result[person] = {
                "months": {m: 0.0 for m in MONTHS},
                "business_pct": row["business_pct"],
            }
        result[person]["months"][row["month"]] = row["amount"]
        result[person]["business_pct"] = row["business_pct"]

    # Ensure both people exist
    for person in ("greg", "lilibeth"):
        if person not in result:
            result[person] = {
                "months": {m: 0.0 for m in MONTHS},
                "business_pct": 100,
            }
    return result


def save_phone_bills(
    fy_name: str, phone_data: dict[str, dict[str, Any]]
) -> None:
    """Save phone bill data for all persons/months."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        for person, data in phone_data.items():
            months = data.get("months", {})
            biz_pct = data.get("business_pct", 100)
            for month, amount in months.items():
                conn.execute(
                    """INSERT INTO phone_bills
                    (fiscal_year_id, person, month, amount, business_pct)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(fiscal_year_id, person, month)
                    DO UPDATE SET amount=excluded.amount,
                                  business_pct=excluded.business_pct""",
                    (fy_id, person, month, float(amount), int(biz_pct)),
                )


# ════════════════════════════════════════════════════════════════════════════
#  OTHER EXPENSES
# ════════════════════════════════════════════════════════════════════════════


def get_other_expenses(fy_name: str) -> dict[str, list[dict[str, Any]]]:
    """Return other expenses grouped by sub_category."""
    fy_id = get_fiscal_year_id(fy_name)
    result: dict[str, list[dict[str, Any]]] = {
        "training": [], "ppe": [], "software": [], "other": [],
    }
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM other_expenses WHERE fiscal_year_id = ? ORDER BY date DESC",
            (fy_id,),
        ).fetchall()
    for row in rows:
        d = dict(row)
        sub = d.get("sub_category", "other")
        if sub not in result:
            result[sub] = []
        result[sub].append(d)
    return result


def add_other_expense(
    fy_name: str, sub_category: str, date: str,
    description: str, amount: float, has_receipt: bool = True,
) -> int:
    """Add an other expense. Returns the new row ID."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO other_expenses
            (fiscal_year_id, sub_category, date, description, amount, has_receipt)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (fy_id, sub_category, date, description, amount, int(has_receipt)),
        )
        return cursor.lastrowid or 0


def delete_other_expense(expense_id: int) -> None:
    """Delete an other expense by ID."""
    with get_connection() as conn:
        conn.execute("DELETE FROM other_expenses WHERE id = ?", (expense_id,))


# ════════════════════════════════════════════════════════════════════════════
#  HOME OFFICE
# ════════════════════════════════════════════════════════════════════════════


def get_home_office(fy_name: str) -> dict[str, float]:
    """Return home office deduction data."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM home_office WHERE fiscal_year_id = ?", (fy_id,)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "rent": 0, "property_tax": 0, "insurance": 0,
            "electricity": 0, "gas": 0, "water": 0,
            "internet": 0, "office_pct": 10,
        }


def save_home_office(fy_name: str, data: dict[str, float]) -> None:
    """Upsert home office data."""
    fy_id = get_fiscal_year_id(fy_name)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO home_office
            (fiscal_year_id, rent, property_tax, insurance,
             electricity, gas, water, internet, office_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fiscal_year_id)
            DO UPDATE SET rent=excluded.rent, property_tax=excluded.property_tax,
                          insurance=excluded.insurance, electricity=excluded.electricity,
                          gas=excluded.gas, water=excluded.water,
                          internet=excluded.internet, office_pct=excluded.office_pct""",
            (
                fy_id,
                data.get("rent", 0), data.get("property_tax", 0),
                data.get("insurance", 0), data.get("electricity", 0),
                data.get("gas", 0), data.get("water", 0),
                data.get("internet", 0), data.get("office_pct", 10),
            ),
        )


# ════════════════════════════════════════════════════════════════════════════
#  USERS / AUTH
# ════════════════════════════════════════════════════════════════════════════


def get_user(username: str) -> Optional[dict[str, Any]]:
    """Look up a user by username."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, full_name FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def create_user(
    username: str, password_hash: str, role: str = "viewer", full_name: str = ""
) -> int:
    """Create a new user. Returns the new user ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, role, full_name)
            VALUES (?, ?, ?, ?)""",
            (username, password_hash, role, full_name),
        )
        return cursor.lastrowid or 0


def list_users() -> list[dict[str, Any]]:
    """Return all users (without password hashes)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, full_name, created_at FROM users"
        ).fetchall()
        return [dict(r) for r in rows]
