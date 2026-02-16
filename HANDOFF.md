# RigBooks — HANDOFF

**Date:** 2026-02-16
**Status:** Batch 1 complete. SQLite migration done. app.py rewritten.

## Done ✅

1. **`helpers/database.py`** — Full SQLite layer with typed functions
   - 12 tables: fiscal_years, transactions, cash_expenses, personal_expenses,
     vehicle_summary, vehicle_trips, phone_bills, other_expenses, home_office, users
   - WAL mode, foreign keys, context-managed connections
   - Upsert/CRUD for every data type
   - 18 pytest tests, all passing

2. **`execution/migrate_to_sqlite.py`** — One-shot migration
   - Migrated 528 transactions (FY 2024-2025) with all 17 category names preserved
   - Migrated 528 transactions (FY 2025-2026)
   - Phone bills: Greg $944.88/yr @ 60%, Lilibeth $1081.44/yr @ 60%
   - Home office data from rigbooks_data.json
   - Handles missing files, corrupt pickles, format variations

3. **`app.py`** — Complete rewrite (817 lines, down from 1188)
   - Zero pickle/JSON imports — all reads/writes go through database.py
   - All 11 pages preserved: Upload, Revenue, Cash, Personal, Vehicle, Phone, Other, GST, Shareholders, Summary, Export
   - Preserves existing classified categories (Revenue - Oilfield Services, etc.)
   - Delete operations use DB row IDs (no more fragile index-based deletion)
   - Syntax verified, DB round-trip verified

4. **`directives/sqlite-migration.md`** — DOE directive

5. **Data verified:**
   - `data/rigbooks.db` = 500KB, all data intact
   - 17 unique CRA categories preserved exactly

## Next Steps 🔜

### Task 3: Deploy to Oracle Cloud Free Tier
- Oracle Cloud always-free tier: 1 OCPU, 1GB RAM ARM instance
- Docker container with Streamlit + SQLite
- Reverse proxy with Caddy for HTTPS
- `data/rigbooks.db` on persistent block storage
- GitHub Actions for CI/CD on push

### Task 4: Password Login for Accountant
- `users` table already exists in schema
- bcrypt hashing (in requirements.txt)
- Streamlit native auth via session_state
- Roles: admin (Lily), viewer (accountant)
- Admin can create/manage user accounts
- Viewer can see all pages but not delete data

## Blockers

- Need Oracle Cloud account credentials (or use existing)
- Need accountant's preferred username
- Old pickle/JSON files in `data/2024-2025/` can be deleted after verifying SQLite is working locally

## Files Changed
```
NEW:    helpers/database.py
NEW:    execution/migrate_to_sqlite.py
NEW:    execution/tests/test_database.py
NEW:    directives/sqlite-migration.md
REWRITE: app.py (pickle/JSON → SQLite)
UPDATED: requirements.txt (+bcrypt, +pytest)
```

## Run Locally
```bash
cd ~/Projects/rigbooks
pip install -r requirements.txt
python3 execution/migrate_to_sqlite.py   # one-time
streamlit run app.py
```
