"""
RigBooks - CRA-Compliant Corporate Bookkeeping
Cape Bretoner's Oilfield Services Ltd.

SQLite-backed version. All data persists in data/rigbooks.db.
"""
import logging
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1

from helpers.auth import (
    ensure_accountant_exists,
    ensure_admin_exists,
    is_admin,
    login_page,
    logout_button,
)
from helpers.database import (
    add_cash_expense,
    add_other_expense,
    add_personal_expense,
    add_vehicle_trip,
    bulk_update_categories,
    delete_all_transactions,
    delete_cash_expense,
    delete_other_expense,
    delete_personal_expense,
    delete_vehicle_trip,
    get_cash_expenses,
    get_home_office,
    get_other_expenses,
    get_personal_expenses,
    get_phone_bills,
    get_transactions,
    get_vehicle_summary,
    get_vehicle_trips,
    init_db,
    save_home_office,
    save_phone_bills,
    save_vehicle_summary,
    upsert_transactions,
)

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
#  INIT
# ════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="RigBooks - Cape Bretoner's", page_icon="🛢️", layout="wide")
init_db()
ensure_admin_exists()
ensure_accountant_exists()

# ── Auth Gate ─────────────────────────────────────────────────────────────
if not login_page():
    st.stop()

if "fiscal_year" not in st.session_state:
    st.session_state.fiscal_year = "2024-2025"

# ════════════════════════════════════════════════════════════════════════════
#  CRA CLASSIFICATION ENGINE
# ════════════════════════════════════════════════════════════════════════════

CRA_CATEGORIES = {
    "Fuel & Petroleum":       {"keywords": ["SHELL", "ESSO", "PETRO", "HUSKY", "GAS", "FUEL", "PIONEER", "MOBIL", "CHEVRON", "CO-OP", "CENTEX", "DOMO", "FAS GA", "FGP", "CIRCLE K"], "itc_pct": 1.0},
    "Vehicle Repairs":        {"keywords": ["CANADIAN TIRE", "NAPA", "LORDCO", "KAL TIRE", "OK TIRE", "JIFFY", "PART SOURCE", "CARWASH", "REGISTR"], "itc_pct": 1.0},
    "Meals (50% ITC)":        {"keywords": ["TIM HORTON", "SUBWAY", "MCDON", "A&W", "WENDY", "BOSTON PIZZA", "DENNY", "SMITTY", "RESTAURANT", "DAIRY QUEEN", "ACHTI", "PIZZA", "CAFE", "COFFEE", "J&R DRIVE"], "itc_pct": 0.5},
    "Equipment & Supplies":   {"keywords": ["OFFICE", "STAPLES", "WALMART", "COSTCO", "HOME DEPOT", "LOWES", "MARKS WORK", "PRINCESS AUTO", "HOME HARDWARE"], "itc_pct": 1.0},
    "Insurance":              {"keywords": ["INSURANCE", "INTACT", "MANULIFE", "WAWANESA"], "itc_pct": 0.0},
    "Professional Fees":      {"keywords": ["LAWYER", "LEGAL", "ACCOUNTANT", "CPA", "BOOKKEEP", "NOTARY", "WCB", "WORKERS COMP"], "itc_pct": 1.0},
    "Bank Charges":           {"keywords": ["BANK FEE", "SERVICE CHARGE", "INTEREST", "NSF", "MONTHLY FEE", "BANK CHARGE"], "itc_pct": 0.0},
    "Telephone":              {"keywords": ["KOODO", "TELUS", "BELL", "ROGERS", "FIDO"], "itc_pct": 1.0},
    "Rent":                   {"keywords": ["RENT", "REALTYFOCUS", "LANDLORD"], "itc_pct": 0.0},
    "Utilities":              {"keywords": ["ATCO", "EPCOR", "ENMAX", "DIRECT ENERGY", "FORTIS"], "itc_pct": 1.0},
    "Subcontractor":          {"keywords": ["SUBCONTRACT"], "itc_pct": 1.0},
    "Wages & Payroll":        {"keywords": ["PAYROLL", "SALARY", "WAGES"], "itc_pct": 0.0},
    "GST Remittance":         {"keywords": ["RECEIVER GENERAL", "GST", "CRA", "GOVERNMENT"], "itc_pct": 0.0},
    "Loan Payment":           {"keywords": ["LOAN", "FINANCING", "LEASE PMT"], "itc_pct": 0.0},
    "Shareholder Distribution": {"keywords": ["LILIBETH", "SEJERA", "GREG", "MACDONALD"], "itc_pct": 0.0},
}

REVENUE_KEYWORDS = ["WIRE TSF", "MOBILE DEP", "BRANCH DEP", "DEPOSIT", "E-TRANSFER", "INTERAC"]

ALL_CATEGORIES = list(dict.fromkeys(["Revenue"] + sorted([
    "Fuel & Petroleum", "Vehicle Repairs & Maintenance", "Vehicle Insurance",
    "Vehicle Lease/Loan Payment", "Office Supplies", "Office Rent - Commercial",
    "Home Office Expenses", "Telephone & Internet", "Software & Subscriptions",
    "Postage & Shipping", "Equipment & Supplies", "Subcontractor Payments",
    "Training & Certifications", "PPE & Safety Equipment", "Travel & Accommodation",
    "Meals & Entertainment (50%)", "Professional Fees", "Management & Admin Fees",
    "Business Insurance", "Bank Charges & Interest", "Loan Payment - Principal",
    "Loan Payment - Interest", "Wages & Payroll", "Shareholder Distribution",
    "Shareholder Loan - Personal", "GST Remittance", "Corporate Tax Payment",
    "Income Tax Installment", "Personal - Not Deductible", "Transfer - Non-Taxable",
    "Utilities", "CCA - Capital Asset", "Other / Unclassified",
    "Revenue - Oilfield Services", "Rent - Commercial", "Insurance - Business",
    "Loan Payment - Personal", "Loan Payment - Business Vehicle",
    "Shareholder Loan - Personal Expense", "Other Expense",
    "Telephone & Communications",
])))

ZERO_ITC_CATEGORIES = {
    "Vehicle Insurance", "Vehicle Lease/Loan Payment", "Business Insurance",
    "Insurance", "Insurance - Business", "Bank Charges & Interest", "Bank Charges",
    "Loan Payment - Principal", "Loan Payment - Interest", "Loan Payment",
    "Loan Payment - Personal", "Loan Payment - Business Vehicle",
    "Wages & Payroll", "Shareholder Distribution",
    "Shareholder Loan - Personal", "Shareholder Loan - Personal Expense",
    "GST Remittance", "Corporate Tax Payment", "Income Tax Installment",
    "Personal - Not Deductible", "Transfer - Non-Taxable",
    "CCA - Capital Asset", "Revenue", "Revenue - Oilfield Services",
    "Rent", "Rent - Commercial", "Office Rent - Commercial",
}
HALF_ITC_CATEGORIES = {"Meals & Entertainment (50%)", "Meals (50% ITC)"}
REVENUE_CATEGORIES = {"Revenue", "Revenue - Oilfield Services"}


def get_itc_rate(category: str) -> float:
    if category in ZERO_ITC_CATEGORIES:
        return 0.0
    if category in HALF_ITC_CATEGORIES:
        return 0.5
    return 1.0


def classify_transaction(desc: str) -> tuple[str, float]:
    desc_upper = desc.upper()
    for kw in REVENUE_KEYWORDS:
        if kw in desc_upper:
            return "Revenue", 0.0
    for cat, info in CRA_CATEGORIES.items():
        for kw in info["keywords"]:
            if kw in desc_upper:
                return cat, info["itc_pct"]
    return "Other / Unclassified", 1.0


def classify_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    results = [classify_transaction(str(row.get("description", ""))) for _, row in df.iterrows()]
    df["cra_category"] = [r[0] for r in results]
    df["itc_pct"] = df["cra_category"].apply(get_itc_rate)
    df["itc_amount"] = df["debit"] * df["itc_pct"] * 0.05 / 1.05
    df.loc[df["cra_category"].isin(REVENUE_CATEGORIES), "itc_amount"] = 0.0
    return df


def load_cibc_csv(content: str) -> pd.DataFrame:
    lines = content.strip().split("\n")
    data = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) >= 3:
            try:
                date_str = parts[0].strip().strip('"')
                date = pd.to_datetime(date_str).strftime("%Y-%m-%d")
                desc = parts[1].strip().strip('"')
                debit = float(parts[2].strip().strip('"')) if parts[2].strip().strip('"') else 0
                credit = float(parts[3].strip().strip('"')) if len(parts) > 3 and parts[3].strip().strip('"') else 0
                data.append({"date": date, "description": desc, "debit": abs(debit), "credit": abs(credit)})
            except (ValueError, IndexError):
                continue
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["date", "description", "debit", "credit"])


# ════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════════════════

fy = st.session_state.fiscal_year
fy_start, fy_end = fy.split("-")

st.sidebar.title("🛢️ RigBooks")
logout_button()
st.sidebar.markdown("**Cape Bretoner's Oilfield Services**")
st.sidebar.markdown(f"FY {fy} (Dec 1, {fy_start} → Nov 30, {fy_end})")
st.sidebar.markdown("---")
st.sidebar.markdown("👨 Greg: 51% | 👩 Lilibeth: 49%")
st.sidebar.markdown("---")

txn_df = get_transactions(fy)
has_data = not txn_df.empty
cash_list = get_cash_expenses(fy)
personal_list = get_personal_expenses(fy)

st.sidebar.markdown("**Data Status:**")
st.sidebar.markdown(f"{'✅' if has_data else '❌'} Bank Statement ({len(txn_df)} txns)")
st.sidebar.markdown(f"{'✅' if cash_list else '⬜'} Cash Expenses ({len(cash_list)})")
st.sidebar.markdown(f"{'✅' if personal_list else '⬜'} Personal Exp ({len(personal_list)})")
st.sidebar.markdown("---")

page = st.sidebar.radio("Navigation", [
    "📤 Upload & Process",
    "💰 Revenue",
    "💵 Cash Expenses",
    "💳 Personal Bank/CC",
    "🚗 Vehicle & Mileage",
    "📱 Phone Bills",
    "📦 Other Expenses",
    "💰 GST Filing",
    "👥 Shareholders",
    "📋 Summary",
    "📧 Export for Accountant",
])


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: UPLOAD & PROCESS
# ════════════════════════════════════════════════════════════════════════════

if page == "📤 Upload & Process":
    st.title("📤 Upload & Process Bank Statement")
    st.caption(f"Fiscal Year: Dec 1, {fy_start} → Nov 30, {fy_end}")

    if has_data:
        st.success(f"✅ {len(txn_df)} transactions in database")
        if is_admin():
            with st.expander("⚠️ Clear & Re-upload"):
                if st.button("🗑️ Clear All Bank Data", type="secondary"):
                    delete_all_transactions(fy)
                    st.rerun()

    corp_file = st.file_uploader("Upload Corporate Bank Statement (CIBC CSV)", type=["csv"], key="csv_upload")

    if corp_file:
        content = corp_file.getvalue().decode("utf-8", errors="replace")
        raw_df = load_cibc_csv(content)
        if raw_df.empty:
            st.error("Could not parse CSV. Check format.")
        else:
            with st.spinner("Classifying transactions..."):
                classified = classify_dataframe(raw_df)
                classified["is_personal"] = False
                classified["needs_review"] = False
                classified["notes"] = ""
                count = upsert_transactions(fy, classified)
            st.success(f"✅ Loaded & classified {count} transactions into database!")
            cats = classified["cra_category"].value_counts()
            st.markdown("### Classification Summary")
            st.dataframe(cats.reset_index().rename(columns={"cra_category": "Category", "count": "Count"}))
            st.balloons()

    if has_data:
        if st.button("🔄 Re-classify All Transactions"):
            with st.spinner("Re-classifying..."):
                base = txn_df[["date", "description", "debit", "credit"]].copy()
                recl = classify_dataframe(base)
                for col in ("is_personal", "needs_review", "notes"):
                    recl[col] = txn_df[col].values
                delete_all_transactions(fy)
                upsert_transactions(fy, recl)
            st.success("✅ Re-classified and saved!")
            st.rerun()

        st.markdown("### All Transactions")
        st.caption("Click any **Category** cell to reclassify. Hit Save when done.")

        display_cols = ["id", "date", "description", "debit", "credit", "cra_category", "itc_amount"]
        edit_df = txn_df[[c for c in display_cols if c in txn_df.columns]].copy().reset_index(drop=True)

        column_config = {
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "cra_category": st.column_config.SelectboxColumn("Category", options=ALL_CATEGORIES, required=True, width="medium"),
            "date": st.column_config.TextColumn("Date", disabled=True, width="small"),
            "description": st.column_config.TextColumn("Description", disabled=True, width="large"),
            "debit": st.column_config.NumberColumn("Debit", disabled=True, format="$%.2f", width="small"),
            "credit": st.column_config.NumberColumn("Credit", disabled=True, format="$%.2f", width="small"),
            "itc_amount": st.column_config.NumberColumn("ITC", disabled=True, format="$%.2f", width="small"),
        }

        edited = st.data_editor(edit_df, column_config=column_config, use_container_width=True, height=500, num_rows="fixed", key="upload_editor")

        if st.button("💾 Save All Category Changes", type="primary", key="save_upload_cats"):
            updates = []
            for _, row in edited.iterrows():
                cat = row["cra_category"]
                pct = get_itc_rate(cat)
                itc = row["debit"] * pct * 0.05 / 1.05 if cat not in REVENUE_CATEGORIES else 0.0
                updates.append({"id": row["id"], "cra_category": cat, "itc_pct": pct, "itc_amount": itc})
            bulk_update_categories(updates)
            st.success(f"✅ Saved {len(updates)} transactions!")
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: REVENUE
# ════════════════════════════════════════════════════════════════════════════

elif page == "💰 Revenue":
    st.title(f"💰 Revenue — FY {fy}")
    if txn_df.empty:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    all_credits = txn_df[txn_df["credit"] > 0].copy()
    credits = all_credits[all_credits["cra_category"].isin(REVENUE_CATEGORIES)].copy()
    non_rev = all_credits[~all_credits["cra_category"].isin(REVENUE_CATEGORIES)].copy()

    wire_mask = credits["description"].str.contains("WIRE TSF", case=False, na=False)
    mobile_mask = credits["description"].str.contains("MOBILE DEP", case=False, na=False) & ~wire_mask
    branch_mask = credits["description"].str.contains("BRANCH DEP|DEPOSIT", case=False, na=False) & ~wire_mask & ~mobile_mask
    etransfer_mask = credits["description"].str.contains("E-TRANSFER|INTERAC", case=False, na=False) & ~wire_mask & ~mobile_mask & ~branch_mask
    other_mask = ~wire_mask & ~mobile_mask & ~branch_mask & ~etransfer_mask
    grand_total = credits["credit"].sum()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Wire Transfers", f"${credits.loc[wire_mask, 'credit'].sum():,.2f}")
    col2.metric("Mobile Deposits", f"${credits.loc[mobile_mask, 'credit'].sum():,.2f}")
    col3.metric("Branch Deposits", f"${credits.loc[branch_mask, 'credit'].sum():,.2f}")
    col4.metric("E-Transfers", f"${credits.loc[etransfer_mask, 'credit'].sum():,.2f}")

    st.metric("TOTAL REVENUE", f"${grand_total:,.2f}")
    st.metric("GST Collected (5%)", f"${grand_total * 0.05:,.2f}")

    for label, mask in [("Wire Transfers (Long Run / PWC)", wire_mask), ("Mobile Deposits", mobile_mask),
                        ("Branch Deposits", branch_mask), ("E-Transfers", etransfer_mask), ("Other Credits", other_mask)]:
        subset = credits[mask]
        if not subset.empty:
            with st.expander(f"{label} ({len(subset)} txns — ${subset['credit'].sum():,.2f})"):
                st.dataframe(subset[["date", "description", "credit"]].reset_index(drop=True), use_container_width=True)

    if not non_rev.empty:
        st.markdown("---")
        st.markdown("### Non-Revenue Credits (excluded from totals)")
        for cat in non_rev["cra_category"].unique():
            cat_df = non_rev[non_rev["cra_category"] == cat]
            with st.expander(f"{cat} ({len(cat_df)} txns — ${cat_df['credit'].sum():,.2f})"):
                st.dataframe(cat_df[["date", "description", "credit"]].reset_index(drop=True), use_container_width=True)

    st.markdown("---")
    st.markdown("### Reclassify Transactions")
    rev_edit = txn_df[["id", "date", "description", "debit", "credit", "cra_category"]].reset_index(drop=True)
    rev_edited = st.data_editor(
        rev_edit,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "cra_category": st.column_config.SelectboxColumn("Category", options=ALL_CATEGORIES, required=True, width="medium"),
            "date": st.column_config.TextColumn("Date", disabled=True, width="small"),
            "description": st.column_config.TextColumn("Description", disabled=True, width="large"),
            "debit": st.column_config.NumberColumn("Debit", disabled=True, format="$%.2f", width="small"),
            "credit": st.column_config.NumberColumn("Credit", disabled=True, format="$%.2f", width="small"),
        },
        use_container_width=True, height=400, num_rows="fixed", key="revenue_editor",
    )
    if st.button("💾 Save All Changes", type="primary", key="rev_save_all"):
        updates = []
        for _, row in rev_edited.iterrows():
            cat = row["cra_category"]
            pct = get_itc_rate(cat)
            itc = row["debit"] * pct * 0.05 / 1.05 if cat not in REVENUE_CATEGORIES else 0.0
            updates.append({"id": row["id"], "cra_category": cat, "itc_pct": pct, "itc_amount": itc})
        bulk_update_categories(updates)
        st.success("✅ All category changes saved!")
        st.rerun()


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: CASH EXPENSES
# ════════════════════════════════════════════════════════════════════════════

elif page == "💵 Cash Expenses":
    st.title(f"💵 Cash Expenses — FY {fy}")
    st.info("**CRA Receipt Rules:** Under $30: statement OK | $30-$150: keep receipt | Over $150: receipt REQUIRED")

    with st.form("add_cash", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            cash_date = st.date_input("Date")
            cash_desc = st.text_input("Description", placeholder="e.g., Safety boots from Marks")
            cash_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01)
        with c2:
            cash_cat = st.selectbox("Category", ["Fuel & Petroleum", "Vehicle Repairs", "Meals (50% ITC)", "Equipment & Supplies", "Professional Fees", "Training & Certifications", "PPE & Safety", "Software & Subscriptions", "Office Expenses", "Other"])
            cash_receipt = st.checkbox("Has receipt?", value=True)
        if st.form_submit_button("➕ Add & Save", type="primary"):
            if cash_amount > 0 and cash_desc:
                add_cash_expense(fy, cash_date.strftime("%Y-%m-%d"), cash_desc, cash_amount, cash_cat, cash_receipt)
                st.success(f"✅ Saved! {cash_desc} — ${cash_amount:.2f}")
                st.rerun()

    if cash_list:
        cash_df = pd.DataFrame(cash_list)
        cash_df["itc"] = cash_df["amount"] * 0.05 / 1.05
        meals_m = cash_df["category"].str.contains("Meal", case=False, na=False)
        cash_df.loc[meals_m, "itc"] = cash_df.loc[meals_m, "amount"] * 0.5 * 0.05 / 1.05
        st.dataframe(cash_df[["date", "description", "category", "amount", "itc", "has_receipt"]], use_container_width=True)
        c1, c2 = st.columns(2)
        c1.metric("Total Cash Expenses", f"${cash_df['amount'].sum():,.2f}")
        c2.metric("Total ITCs", f"${cash_df['itc'].sum():,.2f}")

        del_opts = {f"{e['date']} | {e['description']} | ${e['amount']:.2f}": e["id"] for e in cash_list}
        del_sel = st.selectbox("Delete", list(del_opts.keys()), key="cash_del")
        if st.button("🗑️ Delete", key="cash_del_btn"):
            delete_cash_expense(del_opts[del_sel])
            st.rerun()
    else:
        st.info("No cash expenses recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: PERSONAL BANK/CC
# ════════════════════════════════════════════════════════════════════════════

elif page == "💳 Personal Bank/CC":
    st.title(f"💳 Personal Bank/CC Business Expenses — FY {fy}")

    with st.form("add_personal", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            p_date = st.date_input("Date", key="p_date")
            p_desc = st.text_input("Description", key="p_desc")
            p_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01, key="p_amt")
        with c2:
            p_cat = st.selectbox("Category", ["Fuel & Petroleum", "Vehicle Repairs", "Meals (50% ITC)", "Equipment & Supplies", "Professional Fees", "Training & Certifications", "PPE & Safety", "Software & Subscriptions", "Office Expenses", "Other"], key="p_cat")
            p_receipt = st.checkbox("Has receipt?", value=True, key="p_receipt")
            p_card = st.text_input("Card/Account", placeholder="e.g., Visa ending 4532", key="p_card")
        if st.form_submit_button("➕ Add & Save", type="primary"):
            if p_amount > 0 and p_desc:
                add_personal_expense(fy, p_date.strftime("%Y-%m-%d"), p_desc, p_amount, p_cat, p_receipt, p_card)
                st.success(f"✅ Saved! {p_desc} — ${p_amount:.2f}")
                st.rerun()

    if personal_list:
        p_df = pd.DataFrame(personal_list)
        p_df["itc"] = p_df["amount"] * 0.05 / 1.05
        meals_m = p_df["category"].str.contains("Meal", case=False, na=False)
        p_df.loc[meals_m, "itc"] = p_df.loc[meals_m, "amount"] * 0.5 * 0.05 / 1.05
        st.dataframe(p_df[["date", "description", "category", "amount", "itc", "has_receipt", "card"]], use_container_width=True)
        c1, c2 = st.columns(2)
        c1.metric("Total", f"${p_df['amount'].sum():,.2f}")
        c2.metric("ITCs", f"${p_df['itc'].sum():,.2f}")
        del_opts = {f"{e['date']} | {e['description']} | ${e['amount']:.2f}": e["id"] for e in personal_list}
        del_sel = st.selectbox("Delete", list(del_opts.keys()), key="p_del")
        if st.button("🗑️ Delete", key="p_del_btn"):
            delete_personal_expense(del_opts[del_sel])
            st.rerun()
    else:
        st.info("No personal bank/CC expenses recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: VEHICLE & MILEAGE
# ════════════════════════════════════════════════════════════════════════════

elif page == "🚗 Vehicle & Mileage":
    st.title(f"🚗 Vehicle & Mileage — FY {fy}")
    vm = get_vehicle_summary(fy)

    st.markdown("### Vehicle Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        new_start = st.number_input("Start Odometer (km)", value=int(vm.get("start_odo", 0)), step=1, key="vm_start")
    with c2:
        new_end = st.number_input("End Odometer (km)", value=int(vm.get("end_odo", 0)), step=1, key="vm_end")
    with c3:
        new_fuel = st.number_input("Total Fuel Charges ($)", value=float(vm.get("fuel_total", 0)), step=0.01, key="vm_fuel")

    if st.button("💾 Save Vehicle Summary", type="primary", key="vm_save"):
        save_vehicle_summary(fy, new_start, new_end, new_fuel)
        st.success("✅ Vehicle summary saved!")

    total_km = new_end - new_start
    cost_per_km = new_fuel / total_km if total_km > 0 else 0
    st.markdown(f"**Total Distance:** {total_km:,} km | **Cost/km:** ${cost_per_km:.4f} | **Business Use:** 100%")

    st.markdown("---")
    with st.form("add_trip", clear_on_submit=True):
        st.markdown("### Log a Trip")
        t1, t2, t3 = st.columns(3)
        with t1:
            trip_date = st.date_input("Date", key="trip_date")
            trip_from = st.text_input("From", placeholder="Sherwood Park", key="trip_from")
        with t2:
            trip_to = st.text_input("To", placeholder="Redwater Oilfields", key="trip_to")
            trip_km = st.number_input("Distance (km)", min_value=0.0, step=0.1, key="trip_km")
        with t3:
            trip_purpose = st.text_input("Purpose", placeholder="Daily operations - Long Run", key="trip_purpose")
            trip_odo = st.number_input("Odometer reading", min_value=0, step=1, key="trip_odo")
        if st.form_submit_button("➕ Add Trip & Save", type="primary"):
            add_vehicle_trip(fy, trip_date.strftime("%Y-%m-%d"), trip_from, trip_to, trip_km, trip_purpose, trip_odo)
            st.success(f"✅ Trip saved! {trip_from} → {trip_to}")
            st.rerun()

    trips = get_vehicle_trips(fy)
    if trips:
        trip_df = pd.DataFrame(trips)
        st.dataframe(trip_df[["date", "from_loc", "to_loc", "km", "purpose", "odometer"]], use_container_width=True)
        st.metric("Total Logged Trips", len(trips))
        del_opts = {f"{t['date']} | {t['from_loc']} → {t['to_loc']} | {t['km']} km": t["id"] for t in trips}
        del_sel = st.selectbox("Delete a trip", list(del_opts.keys()), key="trip_del")
        if st.button("🗑️ Delete Trip", key="trip_del_btn"):
            delete_vehicle_trip(del_opts[del_sel])
            st.rerun()

    # CRA Mileage Log Viewer
    st.markdown("---")
    mileage_html_path = Path("mileage_log_FY2024-2025.html")
    if mileage_html_path.exists():
        with st.expander("📄 CRA-Compliant Mileage Log (click to expand)"):
            mileage_html = mileage_html_path.read_text(encoding="utf-8")
            st.components.v1.html(mileage_html, height=800, scrolling=True)
        st.download_button("⬇️ Download CRA Mileage Log (HTML)", mileage_html_path.read_text(encoding="utf-8"),
                           "RigBooks_CRA_Mileage_Log_FY2024-2025.html", "text/html", use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
#  PAGE: PHONE BILLS
# ════════════════════════════════════════════════════════════════════════════

elif page == "📱 Phone Bills":
    st.title(f"📱 Phone Bills — FY {fy}")
    st.caption("Monthly phone bills for Greg & Lilibeth.")

    MONTHS = ["Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]
    phone = get_phone_bills(fy)
    changed = False

    for person, label in [("greg", "👨 Greg MacDonald"), ("lilibeth", "👩 Lilibeth Sejera")]:
        st.markdown(f"### {label}")
        person_data = phone.get(person, {"months": {m: 0.0 for m in MONTHS}, "business_pct": 100})
        months = person_data.get("months", {m: 0.0 for m in MONTHS})

        cols = st.columns(6)
        for i, m in enumerate(MONTHS):
            with cols[i % 6]:
                val = st.number_input(f"{m}", value=float(months.get(m, 0)), step=0.01,
                                      key=f"phone_{person}_{m}", min_value=0.0)
                if val != months.get(m, 0):
                    months[m] = val
                    changed = True

        biz_pct = st.slider(f"{label.split(' ')[1]} Business %", 0, 100,
                            int(person_data.get("business_pct", 100)), key=f"phone_pct_{person}")
        if biz_pct != person_data.get("business_pct", 100):
            changed = True

        annual = sum(months.values())
        deductible = annual * biz_pct / 100
        itc = deductible * 0.05 / 1.05

        phone[person] = {"months": months, "business_pct": biz_pct}

        c1, c2, c3 = st.columns(3)
        c1.metric("Annual Total", f"${annual:,.2f}")
        c2.metric("Deductible", f"${deductible:,.2f}")
        c3.metric("ITC", f"${itc:,.2f}")
        st.markdown("---")

    greg_ded = sum(phone["greg"]["months"].values()) * phone["greg"]["business_pct"] / 100
    lili_ded = sum(phone["lilibeth"]["months"].values()) * phone["lilibeth"]["business_pct"] / 100
    combined_itc = (greg_ded + lili_ded) * 0.05 / 1.05

    st.markdown("### Combined Phone Deductions")
    c1, c2 = st.columns(2)
    c1.metric("Total Deductible", f"${greg_ded + lili_ded:,.2f}")
    c2.metric("Total ITC", f"${combined_itc:,.2f}")

    if st.button("💾 Save Phone Bills", type="primary"):
        save_phone_bills(fy, phone)
        st.success("✅ Phone bills saved!")

    if changed:
        save_phone_bills(fy, phone)


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: OTHER EXPENSES
# ════════════════════════════════════════════════════════════════════════════

elif page == "📦 Other Expenses":
    st.title(f"📦 Other Expenses — FY {fy}")

    other = get_other_expenses(fy)
    sub_cats = {
        "training": "🎓 Training & Certifications",
        "ppe": "🦺 PPE & Safety Equipment",
        "software": "💻 Software & Subscriptions",
        "other": "📎 Other Business Expenses",
    }

    tabs = st.tabs(list(sub_cats.values()))
    for tab, key in zip(tabs, sub_cats.keys()):
        with tab:
            items = other.get(key, [])
            with st.form(f"add_{key}", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    o_date = st.date_input("Date", key=f"o_date_{key}")
                    o_desc = st.text_input("Description", key=f"o_desc_{key}")
                with c2:
                    o_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01, key=f"o_amt_{key}")
                    o_receipt = st.checkbox("Has receipt?", value=True, key=f"o_rec_{key}")
                if st.form_submit_button(f"➕ Add {sub_cats[key].split(' ', 1)[1]}", type="primary"):
                    if o_amount > 0 and o_desc:
                        add_other_expense(fy, key, o_date.strftime("%Y-%m-%d"), o_desc, o_amount, o_receipt)
                        st.success(f"✅ Saved! {o_desc} — ${o_amount:.2f}")
                        st.rerun()

            if items:
                o_df = pd.DataFrame(items)
                o_df["itc"] = o_df["amount"] * 0.05 / 1.05
                st.dataframe(o_df[["date", "description", "amount", "itc", "has_receipt"]], use_container_width=True)
                st.metric(f"Total {sub_cats[key].split(' ', 1)[1]}", f"${o_df['amount'].sum():,.2f}")
                del_opts = {f"{e['date']} | {e['description']} | ${e['amount']:.2f}": e["id"] for e in items}
                del_sel = st.selectbox("Delete", list(del_opts.keys()), key=f"del_{key}")
                if st.button("🗑️ Delete", key=f"del_btn_{key}"):
                    delete_other_expense(del_opts[del_sel])
                    st.rerun()
            else:
                st.info(f"No {sub_cats[key].split(' ', 1)[1].lower()} recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: GST FILING
# ════════════════════════════════════════════════════════════════════════════

elif page == "💰 GST Filing":
    st.title(f"💰 GST/HST Filing — FY {fy}")

    if txn_df.empty:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    # Revenue — only from revenue-categorized transactions
    rev_df = txn_df[txn_df["cra_category"].isin(REVENUE_CATEGORIES)]
    revenue = rev_df["credit"].sum()
    gst_collected = revenue * 0.05

    # Bank ITCs
    bank_itc = txn_df[txn_df["itc_amount"] > 0]["itc_amount"].sum()

    # Cash ITCs
    cash_itc = 0.0
    for e in cash_list:
        amt = e.get("amount", 0)
        if "Meal" in e.get("category", ""):
            cash_itc += amt * 0.5 * 0.05 / 1.05
        else:
            cash_itc += amt * 0.05 / 1.05

    # Personal ITCs
    personal_itc = 0.0
    for e in personal_list:
        amt = e.get("amount", 0)
        if "Meal" in e.get("category", ""):
            personal_itc += amt * 0.5 * 0.05 / 1.05
        else:
            personal_itc += amt * 0.05 / 1.05

    # Phone ITCs
    phone = get_phone_bills(fy)
    greg_ded = sum(phone.get("greg", {}).get("months", {}).values()) * phone.get("greg", {}).get("business_pct", 100) / 100
    lili_ded = sum(phone.get("lilibeth", {}).get("months", {}).values()) * phone.get("lilibeth", {}).get("business_pct", 100) / 100
    phone_itc = (greg_ded + lili_ded) * 0.05 / 1.05

    # Other ITCs
    other = get_other_expenses(fy)
    other_itc = sum(e.get("amount", 0) * 0.05 / 1.05 for items in other.values() for e in items)

    total_itc = bank_itc + cash_itc + personal_itc + phone_itc + other_itc
    net_gst = gst_collected - total_itc

    st.markdown("### GST Summary")
    st.markdown("---")
    st.markdown("**Revenue & GST Collected**")
    c1, c2 = st.columns(2)
    c1.metric("Line 101 — Total Revenue", f"${revenue:,.2f}")
    c2.metric("Line 105 — GST Collected (5%)", f"${gst_collected:,.2f}")

    st.markdown("---")
    st.markdown("**Input Tax Credits (ITCs)**")
    for label, val in [("Bank Statement ITCs", bank_itc), ("Cash Expense ITCs", cash_itc),
                       ("Personal Bank/CC ITCs", personal_itc), ("Phone Bill ITCs", phone_itc),
                       ("Other Expense ITCs", other_itc)]:
        c1, c2 = st.columns([3, 1])
        c1.write(label)
        c2.write(f"${val:,.2f}")

    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("Line 108 — Total ITCs", f"${total_itc:,.2f}")
    if net_gst > 0:
        c2.metric("Line 109 — NET GST OWING", f"${net_gst:,.2f}")
    else:
        c2.metric("Line 109 — GST REFUND", f"${abs(net_gst):,.2f}")

    with st.expander("ITC Breakdown by CRA Category"):
        itc_by_cat = txn_df[txn_df["itc_amount"] > 0].groupby("cra_category")["itc_amount"].sum().sort_values(ascending=False)
        if not itc_by_cat.empty:
            st.dataframe(itc_by_cat.reset_index().rename(columns={"cra_category": "Category", "itc_amount": "ITC Amount"}))


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: SHAREHOLDERS
# ════════════════════════════════════════════════════════════════════════════

elif page == "👥 Shareholders":
    st.title(f"👥 Shareholders — FY {fy}")
    if txn_df.empty:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    rev_total = txn_df[txn_df["cra_category"].isin(REVENUE_CATEGORIES)]["credit"].sum()
    bank_exp = txn_df[txn_df["debit"] > 0]["debit"].sum()
    cash_total = sum(e.get("amount", 0) for e in cash_list)
    personal_total = sum(e.get("amount", 0) for e in personal_list)
    other = get_other_expenses(fy)
    other_total = sum(e.get("amount", 0) for items in other.values() for e in items)

    net_income = rev_total - bank_exp - cash_total - personal_total - other_total
    greg_share = net_income * 0.51
    lili_share = net_income * 0.49

    st.markdown("### Income Split")
    c1, c2, c3 = st.columns(3)
    c1.metric("Net Income", f"${net_income:,.2f}")
    c2.metric("Greg (51%)", f"${greg_share:,.2f}")
    c3.metric("Lilibeth (49%)", f"${lili_share:,.2f}")

    dist = txn_df[txn_df["cra_category"].isin({"Shareholder Distribution"})]
    if not dist.empty:
        st.markdown("### Shareholder Distributions (from Bank)")
        st.dataframe(dist[["date", "description", "debit", "credit"]], use_container_width=True)
        st.metric("Total Distributions", f"${dist['debit'].sum():,.2f}")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: SUMMARY
# ════════════════════════════════════════════════════════════════════════════

elif page == "📋 Summary":
    st.title(f"📋 Summary — FY {fy}")
    if txn_df.empty:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    revenue = txn_df[txn_df["cra_category"].isin(REVENUE_CATEGORIES)]["credit"].sum()
    bank_exp = txn_df[txn_df["debit"] > 0]["debit"].sum()
    cash_total = sum(e.get("amount", 0) for e in cash_list)
    personal_total = sum(e.get("amount", 0) for e in personal_list)
    other = get_other_expenses(fy)
    other_total = sum(e.get("amount", 0) for items in other.values() for e in items)

    st.markdown("### Financial Overview")
    c1, c2 = st.columns(2)
    c1.metric("Total Revenue", f"${revenue:,.2f}")
    c2.metric("Bank Expenses", f"${bank_exp:,.2f}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Cash Expenses", f"${cash_total:,.2f}")
    c2.metric("Personal Bank/CC", f"${personal_total:,.2f}")
    c3.metric("Other Expenses", f"${other_total:,.2f}")

    all_exp = bank_exp + cash_total + personal_total + other_total
    st.metric("NET INCOME", f"${revenue - all_exp:,.2f}")

    st.markdown("### Expenses by CRA Category")
    exp_by_cat = txn_df[txn_df["debit"] > 0].groupby("cra_category").agg(
        Count=("debit", "count"), Total=("debit", "sum"), ITC=("itc_amount", "sum")
    ).sort_values("Total", ascending=False)
    if not exp_by_cat.empty:
        st.dataframe(exp_by_cat, use_container_width=True)

    st.markdown("### Download")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("📥 All Transactions (CSV)", txn_df.to_csv(index=False),
                           f"transactions_FY{fy}.csv", "text/csv")
    with c2:
        itc_df = txn_df[txn_df["itc_amount"] > 0][["date", "description", "debit", "cra_category", "itc_amount"]]
        if not itc_df.empty:
            st.download_button("📥 ITC Report (CSV)", itc_df.to_csv(index=False),
                               f"itc_report_FY{fy}.csv", "text/csv")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: EXPORT FOR ACCOUNTANT
# ════════════════════════════════════════════════════════════════════════════

elif page == "📧 Export for Accountant":
    st.title("📧 Export for Accountant")
    st.markdown("Generate **PDF** and **Excel** files ready to email.")

    if txn_df.empty:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    try:
        from helpers.export_accountant import generate_excel, generate_pdf
        export_available = True
    except ImportError:
        export_available = False
        st.error("Export module not found. Ensure helpers/export_accountant.py exists.")

    if export_available:
        st.markdown("**Includes:** Revenue breakdown, expenses by CRA category, ITCs, cash expenses, phone bills, GST summary, shareholder split, full transaction list.")
        st.markdown("---")
        c1, c2 = st.columns(2)
        phone = get_phone_bills(fy)

        with c1:
            if st.button("📄 Generate PDF", type="primary", use_container_width=True):
                with st.spinner("Building PDF..."):
                    pdf_bytes = generate_pdf(txn_df, cash_list, phone, fy)
                    st.session_state["_pdf_bytes"] = pdf_bytes
                st.success("✅ PDF ready!")
            if "_pdf_bytes" in st.session_state:
                st.download_button("⬇️ Download PDF", st.session_state["_pdf_bytes"],
                    f"CapeBretonerOilfield_FY{fy}.pdf", "application/pdf", use_container_width=True)

        with c2:
            if st.button("📊 Generate Excel", type="primary", use_container_width=True):
                with st.spinner("Building Excel..."):
                    xlsx_bytes = generate_excel(txn_df, cash_list, phone, fy)
                    st.session_state["_xlsx_bytes"] = xlsx_bytes
                st.success("✅ Excel ready!")
            if "_xlsx_bytes" in st.session_state:
                st.download_button("⬇️ Download Excel", st.session_state["_xlsx_bytes"],
                    f"CapeBretonerOilfield_FY{fy}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        st.markdown("---")
        st.info("💡 Download both and email them. PDF is print-ready. Excel has tabs she can filter/sort.")
