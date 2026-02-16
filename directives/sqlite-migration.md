# RigBooks SQLite Migration — Directive

## Objective
Replace pickle/JSON persistence with SQLite so data survives deployment, is queryable,
and enables multi-user (accountant) access. Foundation for Oracle Cloud deploy.

## Inputs
- Current `data/2024-2025/classified_df.pkl` (528 rows, 9 cols)
- Current `data/2024-2025/corporate_df.pkl` (528 rows, 4 cols)
- Current `data/2024-2025/phone_bill.json`
- Current `rigbooks_data.json` (phone bills with amounts, home_office data)
- Current `data/2024-2025/cash_expenses.json` (may not exist yet)
- Current `data/2024-2025/personal_expenses.json` (may not exist yet)
- Current `data/2024-2025/vehicle_mileage.json` (may not exist yet)
- Current `data/2024-2025/other_expenses.json` (may not exist yet)

## Outputs
- `helpers/database.py` — SQLite layer with typed functions
- `app.py` — full rewrite using database.py instead of pickle/JSON
- `execution/migrate_to_sqlite.py` — one-shot migration script
- `rigbooks.db` — SQLite database with all data migrated

## Schema Design
```
fiscal_years       — id, name (e.g. "2024-2025"), start_date, end_date
transactions       — id, fiscal_year_id, date, description, debit, credit,
                     cra_category, itc_pct, itc_amount, is_personal, needs_review, notes
cash_expenses      — id, fiscal_year_id, date, description, amount, category,
                     has_receipt, created_at
personal_expenses  — id, fiscal_year_id, date, description, amount, category,
                     has_receipt, card, created_at
vehicle_mileage    — id, fiscal_year_id, start_odo, end_odo, fuel_total
vehicle_trips      — id, fiscal_year_id, date, from_loc, to_loc, km,
                     purpose, odometer, created_at
phone_bills        — id, fiscal_year_id, person, month, amount, business_pct
other_expenses     — id, fiscal_year_id, sub_category, date, description,
                     amount, has_receipt, created_at
home_office        — id, fiscal_year_id, rent, property_tax, insurance,
                     electricity, gas, water, internet, office_pct
users              — id, username, password_hash, role, full_name, created_at
```

## Constraints
- Preserve ALL existing classified categories exactly as-is (don't rename)
- Must handle empty/missing JSON files gracefully
- SQLite file at `data/rigbooks.db` (single file, easy backup)
- All DB operations use context managers — no leaked connections
- bcrypt for password hashing (not SHA256)

## Edge Cases
| Scenario | Handling |
|---|---|
| Missing pickle/JSON files | Skip with warning, don't crash |
| Duplicate transactions on re-migrate | REPLACE on conflict (date+description+debit+credit) |
| Empty DataFrames | Skip table insert, log warning |
| Corrupt pickle | Fall back to CSV backup if exists |
| Category mismatch (old names) | Preserve as-is, don't force-rename |

## Definition of Done
- [ ] `helpers/database.py` passes pytest (happy path + 2 edge cases per function)
- [ ] `app.py` runs with `streamlit run app.py` using SQLite
- [ ] Migration script imports all 528 transactions with categories intact
- [ ] All pages functional: Upload, Revenue, Cash, Personal, Vehicle, Phone, Other, GST, Shareholders, Summary, Export
- [ ] No pickle imports remain in app.py
- [ ] `rigbooks.db` file created and populated

## Self-Annealing Rules
- On migration error: log failed row, continue remaining, report summary
- On missing column: add with default value, log ANNEALING tag
- On schema change: migration script handles both old and new schemas
