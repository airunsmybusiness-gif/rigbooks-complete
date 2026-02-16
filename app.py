"""
RigBooks - CRA-Compliant Corporate Bookkeeping
Cape Bretoner's Oilfield Services Ltd.
ROBUST AUTO-SAVE VERSION — Every entry persists to disk immediately.
"""
import streamlit as st
import streamlit.components.v1
import pandas as pd
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import pickle
import re

# ════════════════════════════════════════════════════════════════════════════
#  PERSISTENCE LAYER — All data saved per fiscal year
# ════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="RigBooks - Cape Bretoner's", page_icon="🛢️", layout="wide")

BASE_DATA_DIR = Path("data")
BASE_DATA_DIR.mkdir(exist_ok=True)

if 'fiscal_year' not in st.session_state:
    st.session_state.fiscal_year = "2024-2025"

def data_dir():
    d = BASE_DATA_DIR / st.session_state.fiscal_year
    d.mkdir(exist_ok=True)
    return d

def load_json(name, default):
    p = data_dir() / name
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return default

def save_json(name, obj):
    with open(data_dir() / name, 'w') as f:
        json.dump(obj, f, indent=2, default=str)

def load_df(name):
    p = data_dir() / name
    if p.exists():
        return pd.read_pickle(p)
    return None

def save_df(name, df):
    if df is not None and not df.empty:
        df.to_pickle(data_dir() / name)

def save_csv_backup(name, df):
    """Also save a CSV copy for safety"""
    if df is not None and not df.empty:
        df.to_csv(data_dir() / name, index=False)


# ════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INIT — Load from disk on first run
# ════════════════════════════════════════════════════════════════════════════

def init_state():
    defaults = {
        'corporate_df': ('corporate_df.pkl', 'df'),
        'classified_df': ('classified_df.pkl', 'df'),
    }
    json_defaults = {
        'cash_expenses': ('cash_expenses.json', []),
        'personal_expenses': ('personal_expenses.json', []),
        'vehicle_mileage': ('vehicle_mileage.json', {'trips': [], 'start_odo': 0, 'end_odo': 0, 'fuel_total': 0}),
        'other_expenses': ('other_expenses.json', {'training': [], 'ppe': [], 'software': [], 'other': []}),
        'phone_bill': ('phone_bill.json', {
            'greg': {'months': {m: 0.0 for m in ['Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov']}, 'business_pct': 100},
            'lilibeth': {'months': {m: 0.0 for m in ['Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov']}, 'business_pct': 100}
        }),
    }
    for key, (fname, _) in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = load_df(fname)
    for key, (fname, default) in json_defaults.items():
        if key not in st.session_state:
            st.session_state[key] = load_json(fname, default)

init_state()


# ════════════════════════════════════════════════════════════════════════════
#  CRA CLASSIFICATION ENGINE
# ════════════════════════════════════════════════════════════════════════════

CRA_CATEGORIES = {
    'Fuel & Petroleum':       {'keywords': ['SHELL','ESSO','PETRO','HUSKY','GAS','FUEL','PIONEER','MOBIL','CHEVRON','CO-OP','CENTEX','DOMO','FAS GA','FGP','CIRCLE K'], 'itc_pct': 1.0},
    'Vehicle Repairs':        {'keywords': ['CANADIAN TIRE','NAPA','LORDCO','KAL TIRE','OK TIRE','JIFFY','PART SOURCE','CARWASH','REGISTR'], 'itc_pct': 1.0},
    'Meals (50% ITC)':        {'keywords': ['TIM HORTON','SUBWAY','MCDON','A&W','WENDY','BOSTON PIZZA','DENNY','SMITTY','RESTAURANT','DAIRY QUEEN','ACHTI','PIZZA','CAFE','COFFEE','J&R DRIVE'], 'itc_pct': 0.5},
    'Equipment & Supplies':   {'keywords': ['OFFICE','STAPLES','WALMART','COSTCO','HOME DEPOT','LOWES','MARKS WORK','PRINCESS AUTO','HOME HARDWARE'], 'itc_pct': 1.0},
    'Insurance':              {'keywords': ['INSURANCE','INTACT','MANULIFE','WAWANESA'], 'itc_pct': 0.0},
    'Professional Fees':      {'keywords': ['LAWYER','LEGAL','ACCOUNTANT','CPA','BOOKKEEP','NOTARY','WCB','WORKERS COMP'], 'itc_pct': 1.0},
    'Bank Charges':           {'keywords': ['BANK FEE','SERVICE CHARGE','INTEREST','NSF','MONTHLY FEE','BANK CHARGE'], 'itc_pct': 0.0},
    'Telephone':              {'keywords': ['KOODO','TELUS','BELL','ROGERS','FIDO'], 'itc_pct': 1.0},
    'Rent':                   {'keywords': ['RENT','REALTYFOCUS','LANDLORD'], 'itc_pct': 0.0},
    'Utilities':              {'keywords': ['ATCO','EPCOR','ENMAX','DIRECT ENERGY','FORTIS'], 'itc_pct': 1.0},
    'Subcontractor':          {'keywords': ['SUBCONTRACT'], 'itc_pct': 1.0},
    'Wages & Payroll':        {'keywords': ['PAYROLL','SALARY','WAGES'], 'itc_pct': 0.0},
    'GST Remittance':         {'keywords': ['RECEIVER GENERAL','GST','CRA','GOVERNMENT'], 'itc_pct': 0.0},
    'Loan Payment':           {'keywords': ['LOAN','FINANCING','LEASE PMT'], 'itc_pct': 0.0},
    'Shareholder Distribution': {'keywords': ['LILIBETH','SEJERA','GREG','MACDONALD'], 'itc_pct': 0.0},
}

REVENUE_KEYWORDS = ['WIRE TSF', 'MOBILE DEP', 'BRANCH DEP', 'DEPOSIT', 'E-TRANSFER', 'INTERAC']

ALL_CATEGORIES = ['Revenue'] + sorted([
    'Fuel & Petroleum',
    'Vehicle Repairs & Maintenance',
    'Vehicle Insurance',
    'Vehicle Lease/Loan Payment',
    'Office Supplies',
    'Office Rent - Commercial',
    'Home Office Expenses',
    'Telephone & Internet',
    'Software & Subscriptions',
    'Postage & Shipping',
    'Equipment & Supplies',
    'Subcontractor Payments',
    'Training & Certifications',
    'PPE & Safety Equipment',
    'Travel & Accommodation',
    'Meals & Entertainment (50%)',
    'Professional Fees',
    'Management & Admin Fees',
    'Business Insurance',
    'Bank Charges & Interest',
    'Loan Payment - Principal',
    'Loan Payment - Interest',
    'Wages & Payroll',
    'Shareholder Distribution',
    'Shareholder Loan - Personal',
    'GST Remittance',
    'Corporate Tax Payment',
    'Income Tax Installment',
    'Personal - Not Deductible',
    'Transfer - Non-Taxable',
    'Utilities',
    'CCA - Capital Asset',
    'Other / Unclassified',
])

ITC_RATES = {
    'Revenue': 0.0,
    'Fuel & Petroleum': 1.0,
    'Vehicle Repairs & Maintenance': 1.0,
    'Vehicle Insurance': 0.0,
    'Vehicle Lease/Loan Payment': 0.0,
    'Office Supplies': 1.0,
    'Office Rent - Commercial': 1.0,
    'Home Office Expenses': 1.0,
    'Telephone & Internet': 1.0,
    'Software & Subscriptions': 1.0,
    'Postage & Shipping': 1.0,
    'Equipment & Supplies': 1.0,
    'Subcontractor Payments': 1.0,
    'Training & Certifications': 1.0,
    'PPE & Safety Equipment': 1.0,
    'Travel & Accommodation': 1.0,
    'Meals & Entertainment (50%)': 0.5,
    'Professional Fees': 1.0,
    'Management & Admin Fees': 1.0,
    'Business Insurance': 0.0,
    'Bank Charges & Interest': 0.0,
    'Loan Payment - Principal': 0.0,
    'Loan Payment - Interest': 0.0,
    'Wages & Payroll': 0.0,
    'Shareholder Distribution': 0.0,
    'Shareholder Loan - Personal': 0.0,
    'GST Remittance': 0.0,
    'Corporate Tax Payment': 0.0,
    'Income Tax Installment': 0.0,
    'Personal - Not Deductible': 0.0,
    'Transfer - Non-Taxable': 0.0,
    'Utilities': 1.0,
    'CCA - Capital Asset': 0.0,
    'Other / Unclassified': 1.0,
}


def classify_transaction(desc):
    """Classify a transaction description into a CRA category."""
    desc_upper = desc.upper()
    # Check revenue first
    for kw in REVENUE_KEYWORDS:
        if kw in desc_upper:
            return 'Revenue', 0.0
    # Check expense categories
    for cat, info in CRA_CATEGORIES.items():
        for kw in info['keywords']:
            if kw in desc_upper:
                return cat, info['itc_pct']
    return 'Other / Unclassified', 1.0

def classify_dataframe(df):
    """Classify entire DataFrame and compute ITC amounts."""
    df = df.copy()
    cats = []
    itc_pcts = []
    for _, row in df.iterrows():
        cat, pct = classify_transaction(row.get('description', ''))
        cats.append(cat)
        itc_pcts.append(pct)
    df['cra_category'] = cats
    df['itc_pct'] = itc_pcts
    df['itc_amount'] = df['debit'] * df['itc_pct'] * 0.05 / 1.05
    df.loc[df['cra_category'] == 'Revenue', 'itc_amount'] = 0.0
    return df

def load_cibc_csv(content):
    """Parse CIBC CSV format into a DataFrame."""
    lines = content.strip().split('\n')
    data = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                date_str = parts[0].strip().strip('"')
                date = pd.to_datetime(date_str).strftime('%Y-%m-%d')
                desc = parts[1].strip().strip('"')
                debit = float(parts[2].strip().strip('"')) if parts[2].strip().strip('"') else 0
                credit = float(parts[3].strip().strip('"')) if len(parts) > 3 and parts[3].strip().strip('"') else 0
                data.append({'date': date, 'description': desc, 'debit': abs(debit), 'credit': abs(credit)})
            except:
                continue
    return pd.DataFrame(data) if data else pd.DataFrame(columns=['date','description','debit','credit'])


# ════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════════════════

fy_start, fy_end = st.session_state.fiscal_year.split('-')

st.sidebar.title("🛢️ RigBooks")
st.sidebar.markdown(f"**Cape Bretoner's Oilfield Services**")
st.sidebar.markdown(f"FY {st.session_state.fiscal_year} (Dec 1, {fy_start} → Nov 30, {fy_end})")
st.sidebar.markdown("---")
st.sidebar.markdown("👨 Greg: 51% | 👩 Lilibeth: 49%")
st.sidebar.markdown("---")

# Data status indicator
has_bank = st.session_state.corporate_df is not None
has_classified = st.session_state.classified_df is not None
n_cash = len(st.session_state.cash_expenses)
n_personal = len(st.session_state.personal_expenses)

st.sidebar.markdown("**Data Status:**")
st.sidebar.markdown(f"{'✅' if has_bank else '❌'} Bank Statement")
st.sidebar.markdown(f"{'✅' if has_classified else '❌'} Classified")
st.sidebar.markdown(f"{'✅' if n_cash > 0 else '⬜'} Cash Expenses ({n_cash})")
st.sidebar.markdown(f"{'✅' if n_personal > 0 else '⬜'} Personal Exp ({n_personal})")
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

    # Show existing data
    if st.session_state.corporate_df is not None:
        st.success(f"✅ Bank statement loaded: {len(st.session_state.corporate_df)} transactions (saved to disk)")
        if st.session_state.classified_df is not None:
            st.success(f"✅ Classified: {len(st.session_state.classified_df)} transactions")

        with st.expander("⚠️ Clear & Re-upload"):
            if st.button("🗑️ Clear All Bank Data", type="secondary"):
                st.session_state.corporate_df = None
                st.session_state.classified_df = None
                for f in ['corporate_df.pkl', 'classified_df.pkl', 'corporate_backup.csv', 'classified_backup.csv']:
                    p = data_dir() / f
                    if p.exists():
                        p.unlink()
                st.rerun()

    # Upload
    corp_file = st.file_uploader("Upload Corporate Bank Statement (CIBC CSV)", type=['csv'], key='csv_upload')

    if corp_file:
        content = corp_file.getvalue().decode('utf-8', errors='replace')
        df = load_cibc_csv(content)

        if df.empty:
            st.error("Could not parse CSV. Check format.")
        else:
            st.session_state.corporate_df = df
            save_df('corporate_df.pkl', df)
            save_csv_backup('corporate_backup.csv', df)
            st.success(f"✅ Loaded & SAVED {len(df)} transactions to disk!")
            st.info(f"💾 Saved: data/{st.session_state.fiscal_year}/corporate_df.pkl")

            # Auto-classify immediately
            with st.spinner("Classifying transactions..."):
                classified = classify_dataframe(df)
                st.session_state.classified_df = classified
                save_df('classified_df.pkl', classified)
                save_csv_backup('classified_backup.csv', classified)

            st.success(f"✅ Classified & SAVED {len(classified)} transactions!")

            # Show summary
            cats = classified['cra_category'].value_counts()
            st.markdown("### Classification Summary")
            st.dataframe(cats.reset_index().rename(columns={'index': 'Category', 'cra_category': 'Category', 'count': 'Count'}))
            st.balloons()

    # Manual re-classify button
    if st.session_state.corporate_df is not None and st.session_state.classified_df is not None:
        if st.button("🔄 Re-classify All Transactions"):
            with st.spinner("Re-classifying..."):
                classified = classify_dataframe(st.session_state.corporate_df)
                st.session_state.classified_df = classified
                save_df('classified_df.pkl', classified)
                save_csv_backup('classified_backup.csv', classified)
            st.success("✅ Re-classified and saved!")
            st.rerun()

    # Show classified data with EDITABLE categories
    if st.session_state.classified_df is not None:
        st.markdown("### All Transactions")
        st.caption("Click any cell in the **Category** column to reclassify. Hit Save when done.")

        display_cols = ['date', 'description', 'debit', 'credit', 'cra_category', 'itc_amount']
        cols_available = [c for c in display_cols if c in st.session_state.classified_df.columns]
        edit_df = st.session_state.classified_df[cols_available].copy().reset_index(drop=True)

        column_config = {
            "cra_category": st.column_config.SelectboxColumn(
                "Category",
                options=ALL_CATEGORIES,
                required=True,
                width="medium",
            ),
            "date": st.column_config.TextColumn("Date", disabled=True, width="small"),
            "description": st.column_config.TextColumn("Description", disabled=True, width="large"),
            "debit": st.column_config.NumberColumn("Debit", disabled=True, format="$%.2f", width="small"),
            "credit": st.column_config.NumberColumn("Credit", disabled=True, format="$%.2f", width="small"),
            "itc_amount": st.column_config.NumberColumn("ITC", disabled=True, format="$%.2f", width="small"),
        }

        edited = st.data_editor(
            edit_df,
            column_config=column_config,
            use_container_width=True,
            height=500,
            num_rows="fixed",
            key="upload_editor",
        )

        if st.button("💾 Save All Category Changes", type="primary", key="save_upload_cats"):
            # Apply edits back to classified_df
            for i, row in edited.iterrows():
                new_cat = row['cra_category']
                if i < len(st.session_state.classified_df):
                    st.session_state.classified_df.loc[st.session_state.classified_df.index[i], 'cra_category'] = new_cat
                    # Recalc ITC
                    if new_cat in CRA_CATEGORIES:
                        pct = CRA_CATEGORIES[new_cat]['itc_pct']
                    elif new_cat == 'Revenue':
                        pct = 0.0
                    else:
                        pct = 1.0
                    idx = st.session_state.classified_df.index[i]
                    st.session_state.classified_df.loc[idx, 'itc_pct'] = pct
                    debit = st.session_state.classified_df.loc[idx, 'debit']
                    st.session_state.classified_df.loc[idx, 'itc_amount'] = debit * pct * 0.05 / 1.05 if new_cat != 'Revenue' else 0.0

            save_df('classified_df.pkl', st.session_state.classified_df)
            save_csv_backup('classified_backup.csv', st.session_state.classified_df)
            st.success(f"✅ Saved {len(edited)} transactions with updated categories!")
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: REVENUE — with inline re-classification + auto-save
# ════════════════════════════════════════════════════════════════════════════

elif page == "💰 Revenue":
    st.title(f"💰 Revenue — FY {st.session_state.fiscal_year}")

    if st.session_state.classified_df is None:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    df = st.session_state.classified_df.copy()
    all_credits = df[df['credit'] > 0].copy()

    # Only count transactions classified as Revenue toward totals
    if 'cra_category' in df.columns:
        credits = all_credits[all_credits['cra_category'] == 'Revenue'].copy()
        non_revenue_credits = all_credits[all_credits['cra_category'] != 'Revenue'].copy()
    else:
        credits = all_credits.copy()
        non_revenue_credits = all_credits.iloc[0:0].copy()

    # Revenue breakdown
    wire_mask = credits['description'].str.contains('WIRE TSF', case=False, na=False)
    mobile_mask = credits['description'].str.contains('MOBILE DEP', case=False, na=False) & ~wire_mask
    branch_mask = credits['description'].str.contains('BRANCH DEP|DEPOSIT', case=False, na=False) & ~wire_mask & ~mobile_mask
    etransfer_mask = credits['description'].str.contains('E-TRANSFER|INTERAC', case=False, na=False) & ~wire_mask & ~mobile_mask & ~branch_mask
    other_mask = ~wire_mask & ~mobile_mask & ~branch_mask & ~etransfer_mask

    wire_total = credits[wire_mask]['credit'].sum()
    mobile_total = credits[mobile_mask]['credit'].sum()
    branch_total = credits[branch_mask]['credit'].sum()
    etransfer_total = credits[etransfer_mask]['credit'].sum()
    other_total = credits[other_mask]['credit'].sum()
    grand_total = credits['credit'].sum()

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Wire Transfers", f"${wire_total:,.2f}")
    col2.metric("Mobile Deposits", f"${mobile_total:,.2f}")
    col3.metric("Branch Deposits", f"${branch_total:,.2f}")
    col4.metric("E-Transfers", f"${etransfer_total:,.2f}")

    st.metric("TOTAL REVENUE", f"${grand_total:,.2f}")
    st.metric("GST Collected (5%)", f"${grand_total * 0.05:,.2f}")

    # Detail tables
    for label, mask in [("Wire Transfers (Long Run / PWC)", wire_mask),
                        ("Mobile Deposits", mobile_mask),
                        ("Branch Deposits", branch_mask),
                        ("E-Transfers", etransfer_mask),
                        ("Other Credits", other_mask)]:
        subset = credits[mask]
        if not subset.empty:
            with st.expander(f"{label} ({len(subset)} transactions — ${subset['credit'].sum():,.2f})"):
                st.dataframe(subset[['date','description','credit']].reset_index(drop=True), use_container_width=True)

    # Non-revenue credits (excluded from totals)
    if not non_revenue_credits.empty:
        st.markdown("---")
        st.markdown("### Non-Revenue Credits (excluded from totals above)")
        st.caption("These credits are NOT counted as revenue. Reclassify below if needed.")
        for cat in non_revenue_credits['cra_category'].unique():
            cat_df = non_revenue_credits[non_revenue_credits['cra_category'] == cat]
            with st.expander(f"{cat} ({len(cat_df)} transactions — ${cat_df['credit'].sum():,.2f})"):
                st.dataframe(cat_df[['date','description','credit','cra_category']].reset_index(drop=True), use_container_width=True)

    # Reclassify transactions inline
    st.markdown("---")
    st.markdown("### Reclassify Transactions")
    st.caption("Click any **Category** cell to change it. Hit Save when done.")

    rev_edit = df.copy().reset_index(drop=True)
    rev_display = ['date', 'description', 'debit', 'credit', 'cra_category']
    rev_cols = [c for c in rev_display if c in rev_edit.columns]

    rev_column_config = {
        "cra_category": st.column_config.SelectboxColumn(
            "Category",
            options=ALL_CATEGORIES,
            required=True,
            width="medium",
        ),
        "date": st.column_config.TextColumn("Date", disabled=True, width="small"),
        "description": st.column_config.TextColumn("Description", disabled=True, width="large"),
        "debit": st.column_config.NumberColumn("Debit", disabled=True, format="$%.2f", width="small"),
        "credit": st.column_config.NumberColumn("Credit", disabled=True, format="$%.2f", width="small"),
    }

    rev_edited = st.data_editor(
        rev_edit[rev_cols],
        column_config=rev_column_config,
        use_container_width=True,
        height=400,
        num_rows="fixed",
        key="revenue_editor",
    )

    if st.button("\U0001f4be Save All Changes", type="primary", key="rev_save_all"):
        for i, row in rev_edited.iterrows():
            new_cat = row['cra_category']
            if i < len(st.session_state.classified_df):
                idx = st.session_state.classified_df.index[i]
                st.session_state.classified_df.loc[idx, 'cra_category'] = new_cat
                if new_cat in CRA_CATEGORIES:
                    pct = CRA_CATEGORIES[new_cat]['itc_pct']
                elif new_cat == 'Revenue':
                    pct = 0.0
                else:
                    pct = 1.0
                st.session_state.classified_df.loc[idx, 'itc_pct'] = pct
                debit = st.session_state.classified_df.loc[idx, 'debit']
                st.session_state.classified_df.loc[idx, 'itc_amount'] = debit * pct * 0.05 / 1.05 if new_cat != 'Revenue' else 0.0

        save_df('classified_df.pkl', st.session_state.classified_df)
        save_csv_backup('classified_backup.csv', st.session_state.classified_df)
        st.success("\u2705 All category changes saved!")
        st.rerun()



# ════════════════════════════════════════════════════════════════════════════
#  PAGE: CASH EXPENSES — auto-save every entry
# ════════════════════════════════════════════════════════════════════════════

elif page == "💵 Cash Expenses":
    st.title(f"💵 Cash Expenses — FY {st.session_state.fiscal_year}")
    st.caption("Expenses paid in cash (not in bank statement). Auto-saves on add/delete.")

    st.info("**CRA Receipt Rules:** Under $30: statement OK | $30-$150: keep receipt | Over $150: receipt REQUIRED")

    # Add new expense
    with st.form("add_cash", clear_on_submit=True):
        st.markdown("### Add Cash Expense")
        c1, c2 = st.columns(2)
        with c1:
            cash_date = st.date_input("Date")
            cash_desc = st.text_input("Description", placeholder="e.g., Safety boots from Marks")
            cash_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01)
        with c2:
            cash_cat = st.selectbox("Category", [
                'Fuel & Petroleum', 'Vehicle Repairs', 'Meals (50% ITC)',
                'Equipment & Supplies', 'Professional Fees', 'Training & Certifications',
                'PPE & Safety', 'Software & Subscriptions', 'Office Expenses', 'Other'
            ])
            cash_receipt = st.checkbox("Has receipt?", value=True)

        submitted = st.form_submit_button("➕ Add & Save", type="primary")
        if submitted and cash_amount > 0 and cash_desc:
            entry = {
                'date': cash_date.strftime('%Y-%m-%d'),
                'description': cash_desc,
                'amount': cash_amount,
                'category': cash_cat,
                'has_receipt': cash_receipt,
                'added': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            st.session_state.cash_expenses.append(entry)
            save_json('cash_expenses.json', st.session_state.cash_expenses)
            st.success(f"✅ Saved! {cash_desc} — ${cash_amount:.2f}")
            st.rerun()

    # Display existing
    if st.session_state.cash_expenses:
        st.markdown("### Recorded Cash Expenses")
        cash_df = pd.DataFrame(st.session_state.cash_expenses)
        cash_df['itc'] = cash_df['amount'] * 0.05 / 1.05
        # Meals at 50%
        meals_mask = cash_df['category'].str.contains('Meal', case=False, na=False)
        cash_df.loc[meals_mask, 'itc'] = cash_df.loc[meals_mask, 'amount'] * 0.5 * 0.05 / 1.05

        st.dataframe(cash_df[['date','description','category','amount','itc','has_receipt']], use_container_width=True)

        total = cash_df['amount'].sum()
        total_itc = cash_df['itc'].sum()
        c1, c2 = st.columns(2)
        c1.metric("Total Cash Expenses", f"${total:,.2f}")
        c2.metric("Total ITCs", f"${total_itc:,.2f}")

        # Delete
        st.markdown("### Delete an Entry")
        del_options = [f"{e['date']} | {e['description']} | ${e['amount']:.2f}" for e in st.session_state.cash_expenses]
        del_sel = st.selectbox("Select to delete", del_options, key="cash_del")
        if st.button("🗑️ Delete & Save", key="cash_del_btn"):
            idx = del_options.index(del_sel)
            st.session_state.cash_expenses.pop(idx)
            save_json('cash_expenses.json', st.session_state.cash_expenses)
            st.success("Deleted and saved!")
            st.rerun()
    else:
        st.info("No cash expenses recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: PERSONAL BANK/CC EXPENSES
# ════════════════════════════════════════════════════════════════════════════

elif page == "💳 Personal Bank/CC":
    st.title(f"💳 Personal Bank/CC Business Expenses — FY {st.session_state.fiscal_year}")
    st.caption("Business expenses paid from personal bank or credit card. Auto-saves.")

    with st.form("add_personal", clear_on_submit=True):
        st.markdown("### Add Personal Bank/CC Expense")
        c1, c2 = st.columns(2)
        with c1:
            p_date = st.date_input("Date", key="p_date")
            p_desc = st.text_input("Description", placeholder="e.g., Home Depot - plywood for rig", key="p_desc")
            p_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01, key="p_amt")
        with c2:
            p_cat = st.selectbox("Category", [
                'Fuel & Petroleum', 'Vehicle Repairs', 'Meals (50% ITC)',
                'Equipment & Supplies', 'Professional Fees', 'Training & Certifications',
                'PPE & Safety', 'Software & Subscriptions', 'Office Expenses', 'Other'
            ], key="p_cat")
            p_receipt = st.checkbox("Has receipt?", value=True, key="p_receipt")
            p_card = st.text_input("Card/Account used", placeholder="e.g., Visa ending 4532", key="p_card")

        submitted = st.form_submit_button("➕ Add & Save", type="primary")
        if submitted and p_amount > 0 and p_desc:
            entry = {
                'date': p_date.strftime('%Y-%m-%d'),
                'description': p_desc,
                'amount': p_amount,
                'category': p_cat,
                'has_receipt': p_receipt,
                'card': p_card,
                'added': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            st.session_state.personal_expenses.append(entry)
            save_json('personal_expenses.json', st.session_state.personal_expenses)
            st.success(f"✅ Saved! {p_desc} — ${p_amount:.2f}")
            st.rerun()

    if st.session_state.personal_expenses:
        st.markdown("### Recorded Personal Bank/CC Expenses")
        p_df = pd.DataFrame(st.session_state.personal_expenses)
        p_df['itc'] = p_df['amount'] * 0.05 / 1.05
        meals_mask = p_df['category'].str.contains('Meal', case=False, na=False)
        p_df.loc[meals_mask, 'itc'] = p_df.loc[meals_mask, 'amount'] * 0.5 * 0.05 / 1.05

        st.dataframe(p_df[['date','description','category','amount','itc','has_receipt','card']], use_container_width=True)

        c1, c2 = st.columns(2)
        c1.metric("Total Personal Expenses", f"${p_df['amount'].sum():,.2f}")
        c2.metric("Total ITCs", f"${p_df['itc'].sum():,.2f}")

        del_options = [f"{e['date']} | {e['description']} | ${e['amount']:.2f}" for e in st.session_state.personal_expenses]
        del_sel = st.selectbox("Delete an entry", del_options, key="p_del")
        if st.button("🗑️ Delete & Save", key="p_del_btn"):
            idx = del_options.index(del_sel)
            st.session_state.personal_expenses.pop(idx)
            save_json('personal_expenses.json', st.session_state.personal_expenses)
            st.success("Deleted and saved!")
            st.rerun()
    else:
        st.info("No personal bank/CC expenses recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: VEHICLE & MILEAGE
# ════════════════════════════════════════════════════════════════════════════

elif page == "🚗 Vehicle & Mileage":
    st.title(f"🚗 Vehicle & Mileage — FY {st.session_state.fiscal_year}")
    st.caption("CRA-compliant vehicle log. All changes auto-save.")

    vm = st.session_state.vehicle_mileage

    # Odometer & fuel summary
    st.markdown("### Vehicle Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        new_start = st.number_input("Start Odometer (km)", value=int(vm.get('start_odo', 0)), step=1, key="vm_start")
    with c2:
        new_end = st.number_input("End Odometer (km)", value=int(vm.get('end_odo', 0)), step=1, key="vm_end")
    with c3:
        new_fuel = st.number_input("Total Fuel Charges ($)", value=float(vm.get('fuel_total', 0)), step=0.01, key="vm_fuel")

    if st.button("💾 Save Vehicle Summary", type="primary", key="vm_save"):
        vm['start_odo'] = new_start
        vm['end_odo'] = new_end
        vm['fuel_total'] = new_fuel
        st.session_state.vehicle_mileage = vm
        save_json('vehicle_mileage.json', vm)
        st.success("✅ Vehicle summary saved!")

    total_km = new_end - new_start
    cost_per_km = new_fuel / total_km if total_km > 0 else 0
    st.markdown(f"**Total Distance:** {total_km:,} km | **Cost/km:** ${cost_per_km:.4f} | **Business Use:** 100%")

    # Add trip
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
            trip = {
                'date': trip_date.strftime('%Y-%m-%d'),
                'from': trip_from, 'to': trip_to,
                'km': trip_km, 'purpose': trip_purpose,
                'odometer': trip_odo,
                'added': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            vm['trips'].append(trip)
            st.session_state.vehicle_mileage = vm
            save_json('vehicle_mileage.json', vm)
            st.success(f"✅ Trip saved! {trip_from} → {trip_to}")
            st.rerun()

    if vm['trips']:
        st.markdown("### Trip Log")
        trip_df = pd.DataFrame(vm['trips'])
        st.dataframe(trip_df, use_container_width=True)
        st.metric("Total Logged Trips", len(vm['trips']))

        del_options = [f"{t['date']} | {t.get('from','')} → {t.get('to','')} | {t.get('km',0)} km" for t in vm['trips']]
        del_sel = st.selectbox("Delete a trip", del_options, key="trip_del")
        if st.button("🗑️ Delete Trip & Save", key="trip_del_btn"):
            idx = del_options.index(del_sel)
            vm['trips'].pop(idx)
            st.session_state.vehicle_mileage = vm
            save_json('vehicle_mileage.json', vm)
            st.success("Deleted and saved!")
            st.rerun()



    # ── CRA Mileage Log Viewer ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📄 CRA-Compliant Mileage Log (FY 2024-2025)")
    st.caption("Full mileage log with 297 trips, odometer readings, and monthly breakdown. CRA audit-ready.")

    mileage_html_path = Path("mileage_log_FY2024-2025.html")
    if mileage_html_path.exists():
        with open(mileage_html_path, 'r') as mf:
            mileage_html = mf.read()

        # Render inline
        with st.expander("🔍 View Full Mileage Log (click to expand)", expanded=False):
            st.components.v1.html(mileage_html, height=800, scrolling=True)

        # Download button
        st.download_button(
            "⬇️ Download CRA Mileage Log (HTML)",
            mileage_html,
            "RigBooks_CRA_Compliant_Mileage_Log_FY2024-2025.html",
            "text/html",
            use_container_width=True
        )

        # Key stats from the log
        st.markdown("#### Key Stats from Mileage Log")
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Total Trips", "297")
        mc2.metric("Total Distance", "14,128 km")
        mc3.metric("Fuel Charges", "$12,041.21")
        mc4.metric("Cost/km", "$0.8523")

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Start Odometer", "97,178 km")
        mc2.metric("End Odometer", "111,306 km")
        mc3.metric("Business Use", "100%")
    else:
        st.warning("⚠️ Mileage log HTML file not found. Place `mileage_log_FY2024-2025.html` in the project root.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: PHONE BILLS
# ════════════════════════════════════════════════════════════════════════════

elif page == "📱 Phone Bills":
    st.title(f"📱 Phone Bills — FY {st.session_state.fiscal_year}")
    st.caption("Monthly phone bills for Greg & Lilibeth. Auto-saves on every change.")

    MONTHS = ['Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov']
    phone = st.session_state.phone_bill
    changed = False

    for person, label in [('greg', '👨 Greg MacDonald'), ('lilibeth', '👩 Lilibeth Sejera')]:
        st.markdown(f"### {label}")
        person_data = phone.get(person, {'months': {m: 0.0 for m in MONTHS}, 'business_pct': 100})
        months = person_data.get('months', {m: 0.0 for m in MONTHS})

        cols = st.columns(6)
        for i, m in enumerate(MONTHS):
            with cols[i % 6]:
                val = st.number_input(f"{m}", value=float(months.get(m, 0)), step=0.01,
                                      key=f"phone_{person}_{m}", min_value=0.0)
                if val != months.get(m, 0):
                    months[m] = val
                    changed = True

        biz_pct = st.slider(f"{label.split(' ')[1]} Business %", 0, 100,
                            int(person_data.get('business_pct', 100)), key=f"phone_pct_{person}")
        if biz_pct != person_data.get('business_pct', 100):
            changed = True

        annual = sum(months.values())
        deductible = annual * biz_pct / 100
        itc = deductible * 0.05 / 1.05

        phone[person] = {'months': months, 'business_pct': biz_pct}

        c1, c2, c3 = st.columns(3)
        c1.metric("Annual Total", f"${annual:,.2f}")
        c2.metric("Deductible", f"${deductible:,.2f}")
        c3.metric("ITC", f"${itc:,.2f}")
        st.markdown("---")

    # Combined
    greg_ded = sum(phone['greg']['months'].values()) * phone['greg']['business_pct'] / 100
    lili_ded = sum(phone['lilibeth']['months'].values()) * phone['lilibeth']['business_pct'] / 100
    combined_itc = (greg_ded + lili_ded) * 0.05 / 1.05

    st.markdown("### Combined Phone Deductions")
    c1, c2 = st.columns(2)
    c1.metric("Total Deductible", f"${greg_ded + lili_ded:,.2f}")
    c2.metric("Total ITC", f"${combined_itc:,.2f}")

    if st.button("💾 Save Phone Bills", type="primary"):
        st.session_state.phone_bill = phone
        save_json('phone_bill.json', phone)
        st.success("✅ Phone bills saved to disk!")

    if changed:
        st.session_state.phone_bill = phone
        save_json('phone_bill.json', phone)


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: OTHER EXPENSES — Training, PPE, Software, etc.
# ════════════════════════════════════════════════════════════════════════════

elif page == "📦 Other Expenses":
    st.title(f"📦 Other Expenses — FY {st.session_state.fiscal_year}")
    st.caption("Training, PPE, Software, and miscellaneous. Auto-saves on add/delete.")

    other = st.session_state.other_expenses
    sub_cats = {
        'training': '🎓 Training & Certifications',
        'ppe': '🦺 PPE & Safety Equipment',
        'software': '💻 Software & Subscriptions',
        'other': '📎 Other Business Expenses'
    }

    tab_keys = list(sub_cats.keys())
    tabs = st.tabs(list(sub_cats.values()))

    for tab, key in zip(tabs, tab_keys):
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
                        entry = {
                            'date': o_date.strftime('%Y-%m-%d'),
                            'description': o_desc,
                            'amount': o_amount,
                            'has_receipt': o_receipt,
                            'added': datetime.now().strftime('%Y-%m-%d %H:%M')
                        }
                        other[key].append(entry)
                        st.session_state.other_expenses = other
                        save_json('other_expenses.json', other)
                        st.success(f"✅ Saved! {o_desc} — ${o_amount:.2f}")
                        st.rerun()

            if items:
                o_df = pd.DataFrame(items)
                o_df['itc'] = o_df['amount'] * 0.05 / 1.05
                st.dataframe(o_df, use_container_width=True)
                st.metric(f"Total {sub_cats[key].split(' ', 1)[1]}", f"${o_df['amount'].sum():,.2f}")

                del_opts = [f"{e['date']} | {e['description']} | ${e['amount']:.2f}" for e in items]
                del_sel = st.selectbox("Delete", del_opts, key=f"del_{key}")
                if st.button("🗑️ Delete & Save", key=f"del_btn_{key}"):
                    idx = del_opts.index(del_sel)
                    other[key].pop(idx)
                    st.session_state.other_expenses = other
                    save_json('other_expenses.json', other)
                    st.success("Deleted and saved!")
                    st.rerun()
            else:
                st.info(f"No {sub_cats[key].split(' ', 1)[1].lower()} recorded yet.")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: GST FILING
# ════════════════════════════════════════════════════════════════════════════

elif page == "💰 GST Filing":
    st.title(f"💰 GST/HST Filing — FY {st.session_state.fiscal_year}")

    if st.session_state.classified_df is None:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    df = st.session_state.classified_df

    # Revenue
    revenue = df[df['credit'] > 0]['credit'].sum()
    gst_collected = revenue * 0.05

    # Bank ITCs
    bank_itc = df[df['itc_amount'] > 0]['itc_amount'].sum()

    # Cash ITCs
    cash_itc = 0
    for e in st.session_state.cash_expenses:
        amt = e.get('amount', 0)
        if 'Meal' in e.get('category', ''):
            cash_itc += amt * 0.5 * 0.05 / 1.05
        else:
            cash_itc += amt * 0.05 / 1.05

    # Personal ITCs
    personal_itc = 0
    for e in st.session_state.personal_expenses:
        amt = e.get('amount', 0)
        if 'Meal' in e.get('category', ''):
            personal_itc += amt * 0.5 * 0.05 / 1.05
        else:
            personal_itc += amt * 0.05 / 1.05

    # Phone ITCs
    phone = st.session_state.phone_bill
    greg_ded = sum(phone.get('greg', {}).get('months', {}).values()) * phone.get('greg', {}).get('business_pct', 100) / 100
    lili_ded = sum(phone.get('lilibeth', {}).get('months', {}).values()) * phone.get('lilibeth', {}).get('business_pct', 100) / 100
    phone_itc = (greg_ded + lili_ded) * 0.05 / 1.05

    # Other Expenses ITCs
    other_itc = 0
    for key in st.session_state.other_expenses:
        for e in st.session_state.other_expenses[key]:
            other_itc += e.get('amount', 0) * 0.05 / 1.05

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
    itc_data = {
        'Bank Statement ITCs': bank_itc,
        'Cash Expense ITCs': cash_itc,
        'Personal Bank/CC ITCs': personal_itc,
        'Phone Bill ITCs': phone_itc,
        'Other Expense ITCs': other_itc,
    }
    for label, val in itc_data.items():
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

    # Breakdown by category
    with st.expander("ITC Breakdown by CRA Category"):
        if 'cra_category' in df.columns and 'itc_amount' in df.columns:
            itc_by_cat = df[df['itc_amount'] > 0].groupby('cra_category')['itc_amount'].sum().sort_values(ascending=False)
            st.dataframe(itc_by_cat.reset_index().rename(columns={'cra_category': 'Category', 'itc_amount': 'ITC Amount'}))


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: SHAREHOLDERS
# ════════════════════════════════════════════════════════════════════════════

elif page == "👥 Shareholders":
    st.title(f"👥 Shareholders — FY {st.session_state.fiscal_year}")

    if st.session_state.classified_df is None:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    df = st.session_state.classified_df
    revenue = df[df['credit'] > 0]['credit'].sum()
    total_expenses = df[df['debit'] > 0]['debit'].sum()
    cash_total = sum(e.get('amount', 0) for e in st.session_state.cash_expenses)
    personal_total = sum(e.get('amount', 0) for e in st.session_state.personal_expenses)
    other_total = sum(e.get('amount', 0) for key in st.session_state.other_expenses for e in st.session_state.other_expenses[key])

    net_income = revenue - total_expenses - cash_total - personal_total - other_total
    greg_share = net_income * 0.51
    lili_share = net_income * 0.49

    st.markdown("### Income Split")
    c1, c2, c3 = st.columns(3)
    c1.metric("Net Income", f"${net_income:,.2f}")
    c2.metric("Greg (51%)", f"${greg_share:,.2f}")
    c3.metric("Lilibeth (49%)", f"${lili_share:,.2f}")

    # Shareholder distributions from bank
    if 'cra_category' in df.columns:
        dist = df[df['cra_category'] == 'Shareholder Distribution']
        if not dist.empty:
            st.markdown("### Shareholder Distributions (from Bank)")
            st.dataframe(dist[['date','description','debit','credit']], use_container_width=True)
            st.metric("Total Distributions", f"${dist['debit'].sum():,.2f}")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: SUMMARY
# ════════════════════════════════════════════════════════════════════════════

elif page == "📋 Summary":
    st.title(f"📋 Summary — FY {st.session_state.fiscal_year}")

    if st.session_state.classified_df is None:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    df = st.session_state.classified_df
    revenue = df[df['credit'] > 0]['credit'].sum()
    bank_expenses = df[df['debit'] > 0]['debit'].sum()
    cash_total = sum(e.get('amount', 0) for e in st.session_state.cash_expenses)
    personal_total = sum(e.get('amount', 0) for e in st.session_state.personal_expenses)
    other_total = sum(e.get('amount', 0) for key in st.session_state.other_expenses for e in st.session_state.other_expenses[key])

    st.markdown("### Financial Overview")
    c1, c2 = st.columns(2)
    c1.metric("Total Revenue", f"${revenue:,.2f}")
    c2.metric("Bank Expenses", f"${bank_expenses:,.2f}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Cash Expenses", f"${cash_total:,.2f}")
    c2.metric("Personal Bank/CC", f"${personal_total:,.2f}")
    c3.metric("Other Expenses", f"${other_total:,.2f}")

    all_expenses = bank_expenses + cash_total + personal_total + other_total
    net = revenue - all_expenses
    st.metric("NET INCOME", f"${net:,.2f}")

    # Expense breakdown
    if 'cra_category' in df.columns:
        st.markdown("### Expenses by CRA Category")
        exp_by_cat = df[df['debit'] > 0].groupby('cra_category').agg(
            Count=('debit', 'count'),
            Total=('debit', 'sum'),
            ITC=('itc_amount', 'sum')
        ).sort_values('Total', ascending=False)
        st.dataframe(exp_by_cat, use_container_width=True)

    # Data files on disk
    st.markdown("### Data Files on Disk")
    data_path = data_dir()
    if data_path.exists():
        files = list(data_path.iterdir())
        for f in sorted(files):
            size = f.stat().st_size
            st.markdown(f"✅ `{f.name}` — {size:,} bytes")

    # Download all data
    st.markdown("### Download")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("📥 All Transactions (CSV)", df.to_csv(index=False),
                           f"transactions_FY{st.session_state.fiscal_year}.csv", "text/csv")
    with c2:
        if 'itc_amount' in df.columns:
            itc_df = df[df['itc_amount'] > 0][['date','description','debit','cra_category','itc_amount']]
            st.download_button("📥 ITC Report (CSV)", itc_df.to_csv(index=False),
                               f"itc_report_FY{st.session_state.fiscal_year}.csv", "text/csv")


# ════════════════════════════════════════════════════════════════════════════
#  PAGE: EXPORT FOR ACCOUNTANT
# ════════════════════════════════════════════════════════════════════════════

elif page == "📧 Export for Accountant":
    st.title("📧 Export for Accountant")
    st.markdown("Generate **PDF** and **Excel** files ready to email — your accountant opens them like any normal file.")

    if st.session_state.classified_df is None:
        st.warning("⚠️ Upload and process a bank statement first.")
        st.stop()

    try:
        from helpers.export_accountant import generate_pdf, generate_excel
        export_available = True
    except ImportError:
        export_available = False
        st.error("Export module not found. Make sure helpers/export_accountant.py exists.")

    if export_available:
        st.markdown("""**What's included in both files:**
- Revenue breakdown (Wire Transfers, Mobile Deposits, Branch, E-Transfers)
- Expenses by CRA category with ITC calculations
- Cash expenses with receipt tracking
- Phone bill deductions (Greg + Lilibeth monthly)
- GST/HST filing summary (Lines 101, 105, 108, 109)
- Shareholder income split (51/49)
- Complete transaction list
        """)

        st.markdown("---")
        c1, c2 = st.columns(2)

        with c1:
            if st.button("📄 Generate PDF", type="primary", use_container_width=True):
                with st.spinner("Building PDF..."):
                    pdf_bytes = generate_pdf(
                        st.session_state.classified_df,
                        st.session_state.cash_expenses,
                        st.session_state.phone_bill,
                        st.session_state.fiscal_year
                    )
                    st.session_state['_pdf_bytes'] = pdf_bytes
                st.success("✅ PDF ready!")

            if '_pdf_bytes' in st.session_state:
                st.download_button("⬇️ Download PDF", st.session_state['_pdf_bytes'],
                    f"CapeBretonerOilfield_FY{st.session_state.fiscal_year}.pdf",
                    "application/pdf", use_container_width=True)

        with c2:
            if st.button("📊 Generate Excel", type="primary", use_container_width=True):
                with st.spinner("Building Excel..."):
                    xlsx_bytes = generate_excel(
                        st.session_state.classified_df,
                        st.session_state.cash_expenses,
                        st.session_state.phone_bill,
                        st.session_state.fiscal_year
                    )
                    st.session_state['_xlsx_bytes'] = xlsx_bytes
                st.success("✅ Excel ready!")

            if '_xlsx_bytes' in st.session_state:
                st.download_button("⬇️ Download Excel", st.session_state['_xlsx_bytes'],
                    f"CapeBretonerOilfield_FY{st.session_state.fiscal_year}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True)

        st.markdown("---")
        st.info("💡 Download both and email them. PDF is print-ready. Excel has 6 tabs she can filter/sort.")
