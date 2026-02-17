"""
CRA-Compliant Corporate Bookkeeping Dashboard
Cape Bretoner's Oilfield Services Ltd.

CORRECTED VERSION (Feb 17, 2026) — All audit findings resolved:
1. GST collected uses 5/105 extraction (not 5% addition)
2. Revenue only counts 'Revenue' category (not all credits)
3. T5 duplicate page removed
4. T5 dividend split is editable (not hardcoded 51/49)
5. Shareholder loan tracks by individual, not pooled 51/49
6. GST display formula matches actual calculation (5/105)
7. Transaction Review page has CSV export button
8. Mileage log summary page added
9. is_personal flag preserved in exports
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO
import json
from pathlib import Path
import pickle

from helpers.transaction_classifier import TransactionClassifier
from helpers.gst_calculator import GSTCalculator
from helpers.shareholder_tracker import ShareholderTracker
from helpers.report_generator import ReportGenerator

st.set_page_config(
    page_title="CRA-Ready Books - Cape Bretoner's Oilfield",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DATA_DIR = Path("data")
BASE_DATA_DIR.mkdir(exist_ok=True)

# Seed data directory — pre-populated phone bills, etc.
# These survive redeploys because they're committed to the repo.
SEED_DATA_DIR = Path("data_seed")


def seed_data_if_needed(year_dir: Path):
    """Copy seed data into year directory if it doesn't exist yet.
    
    This ensures phone bills and other manually-entered data survive
    Railway redeploys without requiring re-entry.
    """
    if not SEED_DATA_DIR.exists():
        return
    for seed_file in SEED_DATA_DIR.glob("*.json"):
        target = year_dir / seed_file.name
        if not target.exists():
            import shutil
            shutil.copy2(seed_file, target)

if 'fiscal_year' not in st.session_state:
    current_month = datetime.now().month
    current_year = datetime.now().year
    if current_month >= 12:
        fy_start = current_year
        fy_end = current_year + 1
    else:
        fy_start = current_year - 1
        fy_end = current_year
    st.session_state.fiscal_year = f"{fy_start}-{fy_end}"

def get_year_data_dir():
    year_dir = BASE_DATA_DIR / st.session_state.fiscal_year
    year_dir.mkdir(exist_ok=True)
    seed_data_if_needed(year_dir)
    return year_dir

def load_json(filename, default):
    path = get_year_data_dir() / filename
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(get_year_data_dir() / filename, 'w') as f:
        json.dump(data, f, indent=2)

def load_dataframe(filename):
    path = get_year_data_dir() / filename
    if path.exists():
        return pd.read_pickle(path)
    return None

def save_dataframe(filename, df):
    if df is not None:
        df.to_pickle(get_year_data_dir() / filename)

def get_available_years():
    if not BASE_DATA_DIR.exists():
        return ["2024-2025", "2025-2026", "2026-2027"]
    years = [d.name for d in BASE_DATA_DIR.iterdir() if d.is_dir() and '-' in d.name]
    if not years:
        return ["2024-2025", "2025-2026", "2026-2027"]
    return sorted(years, reverse=True)

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("🛢️ Cape Bretoner's Oilfield")
st.sidebar.markdown("**Fiscal Year End:** November 30")
st.sidebar.markdown("---")

available_years = get_available_years()
selected_year = st.sidebar.selectbox("📅 Fiscal Year", available_years, index=0)

if selected_year != st.session_state.fiscal_year:
    st.session_state.fiscal_year = selected_year
    st.session_state.corporate_df = load_dataframe('corporate_df.pkl')
    st.session_state.classified_df = load_dataframe('classified_df.pkl')
    st.session_state.cash_expenses = load_json('cash_expenses.json', [])
    st.session_state.phone_bill = load_json('phone_bill.json', {
        'greg': {'monthly': 0.0, 'business_pct': 100},
        'lilibeth': {'monthly': 0.0, 'business_pct': 100}
    })
    st.session_state.missing_receipts = load_json('missing_receipts.json', [])
    st.rerun()

fy_start, fy_end = st.session_state.fiscal_year.split('-')
st.sidebar.markdown(f"**Active:** FY {st.session_state.fiscal_year}")
st.sidebar.markdown(f"Dec 1, {fy_start} → Nov 30, {fy_end}")
st.sidebar.markdown("---")
st.sidebar.markdown("### Ownership")
st.sidebar.markdown("👨 **Greg:** 51%")
st.sidebar.markdown("👩 **Lilibeth:** 49%")

# Session state initialization
if 'corporate_df' not in st.session_state:
    st.session_state.corporate_df = load_dataframe('corporate_df.pkl')
if 'classified_df' not in st.session_state:
    st.session_state.classified_df = load_dataframe('classified_df.pkl')
if 'cash_expenses' not in st.session_state:
    st.session_state.cash_expenses = load_json('cash_expenses.json', [])
if 'phone_bill' not in st.session_state:
    phone_data = load_json('phone_bill.json', {
        'greg': {'monthly': 0.0, 'business_pct': 100},
        'lilibeth': {'monthly': 0.0, 'business_pct': 100}
    })
    if 'monthly' in phone_data:
        phone_data = {'greg': {'monthly': 0.0, 'business_pct': 100}, 'lilibeth': {'monthly': 0.0, 'business_pct': 100}}
    st.session_state.phone_bill = phone_data
if 'shareholder_tracker' not in st.session_state:
    st.session_state.shareholder_tracker = ShareholderTracker()
if 'missing_receipts' not in st.session_state:
    st.session_state.missing_receipts = load_json('missing_receipts.json', [])

page = st.sidebar.radio("Navigation", [
    "📤 Upload & Process", "💵 Cash Expenses", "📱 Phone & Utilities",
    "💰 Revenue", "📊 Transaction Review", "💰 GST Filing", "👥 Shareholder Accounts",
    "📄 T5 Slips", "🚛 Mileage Log", "🧾 Receipt Tracker", "📋 Final Summary", "🛡️ Audit Guide"
])


# ============================================================
# HELPER: CIBC CSV LOADER
# ============================================================
def load_cibc_csv(content):
    lines = content.strip().split('\n')
    data = []
    seen = set()
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                date = pd.to_datetime(parts[0].strip()).strftime('%Y-%m-%d')
                desc = parts[1].strip()
                debit = float(parts[2].strip()) if parts[2].strip() else 0
                credit = float(parts[3].strip()) if len(parts) > 3 and parts[3].strip() else 0
                key = (date, desc, debit, credit)
                if key not in seen:
                    seen.add(key)
                    data.append({'date': date, 'description': desc, 'debit': debit, 'credit': credit})
            except:
                continue
    return pd.DataFrame(data)


# ============================================================
# HELPER: Get clean deduplicated df
# ============================================================
def get_clean_df():
    """Return deduplicated classified dataframe or None."""
    if st.session_state.classified_df is None:
        return None
    df = st.session_state.classified_df.copy()
    df = df.drop_duplicates(subset=['date', 'description', 'debit', 'credit'], keep='first')
    return df


# ============================================================
# HELPER: Taxable revenue only (FIX #2)
# ============================================================
def get_taxable_revenue(df):
    """Return only confirmed taxable oilfield revenue credits.
    
    This is the CORRECTED version that excludes non-revenue credits
    like SHL repayments, reversals, and miscoded deposits.
    """
    # The category name in the CSV export is 'Revenue' but in the classifier it's 
    # 'Revenue - Oilfield Services'. Handle both.
    revenue_categories = ['Revenue', 'Revenue - Oilfield Services']
    mask = df['cra_category'].isin(revenue_categories) & (df['credit'] > 0)
    return df.loc[mask, 'credit'].sum()


# ============================================================
# HELPER: GST collected using 5/105 extraction (FIX #1)
# ============================================================
def calc_gst_collected(taxable_revenue):
    """Extract GST from GST-inclusive revenue using 5/105.
    
    Client wire transfers include GST. To extract:
    GST = Revenue × 5 ÷ 105 (NOT Revenue × 5%)
    """
    return taxable_revenue * 0.05 / 1.05


# ============================================================
# PAGE: Upload & Process
# ============================================================
if page == "📤 Upload & Process":
    st.title(f"📤 Upload Bank Statement - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    st.info("Upload your corporate CIBC statement. The system will automatically classify all transactions.")
    
    if st.session_state.corporate_df is not None:
        st.success(f"✅ Existing statement loaded: {len(st.session_state.corporate_df)} transactions")
        if st.button("🗑️ Clear Existing Statement"):
            st.session_state.corporate_df = None
            st.session_state.classified_df = None
            save_dataframe('corporate_df.pkl', None)
            save_dataframe('classified_df.pkl', None)
            st.rerun()
    
    corp_file = st.file_uploader("Corporate Bank Statement (CIBC CSV)", type=['csv'])
    
    if corp_file:
        content = corp_file.getvalue().decode('utf-8', errors='replace')
        st.session_state.corporate_df = load_cibc_csv(content)
        save_dataframe('corporate_df.pkl', st.session_state.corporate_df)
        st.success(f"✓ Loaded {len(st.session_state.corporate_df)} transactions")
        
        if st.button("🔄 Process Statement", type="primary"):
            with st.spinner("Classifying transactions..."):
                classifier = TransactionClassifier()
                st.session_state.classified_df = classifier.classify_dataframe(
                    st.session_state.corporate_df, 'corporate'
                )
                save_dataframe('classified_df.pkl', st.session_state.classified_df)
            st.success("✅ Processing complete!")
            st.balloons()


# ============================================================
# PAGE: Cash Expenses
# ============================================================
elif page == "💵 Cash Expenses":
    st.title(f"💵 Cash Paid Expenses - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    
    st.warning("""**CRA Receipt Rules:**
    - Under $30: Bank statement sufficient
    - $30-$150: Keep receipt if possible
    - Over $150: Receipt REQUIRED for ITC""")
    
    col1, col2 = st.columns(2)
    with col1:
        cash_date = st.date_input("Date", value=datetime.now())
        cash_desc = st.text_input("Description", placeholder="e.g., Fuel at Petro-Canada")
        cash_amount = st.number_input("Amount ($)", min_value=0.0, step=0.01)
    with col2:
        cash_category = st.selectbox("Category", [
            'Fuel & Petroleum', 'Vehicle Repairs & Maintenance', 'Equipment & Supplies',
            'Meals & Entertainment (50%)', 'Office Expenses', 'Other Business Expense'
        ])
        has_receipt = st.checkbox("I have the receipt", value=True)
        cash_notes = st.text_input("Business Purpose")
    
    if st.button("➕ Add Cash Expense"):
        expense = {
            'date': cash_date.strftime('%Y-%m-%d'),
            'description': f"CASH: {cash_desc}",
            'amount': cash_amount,
            'category': cash_category,
            'has_receipt': has_receipt,
            'notes': cash_notes
        }
        st.session_state.cash_expenses.append(expense)
        save_json('cash_expenses.json', st.session_state.cash_expenses)
        if not has_receipt and cash_amount > 30:
            st.session_state.missing_receipts.append(expense)
            save_json('missing_receipts.json', st.session_state.missing_receipts)
        st.success(f"✅ Added: {cash_desc} - ${cash_amount:.2f}")
    
    if st.session_state.cash_expenses:
        st.markdown("### Cash Expenses Entered")
        cash_df = pd.DataFrame(st.session_state.cash_expenses)
        st.dataframe(cash_df, use_container_width=True)
        total_cash = sum(e['amount'] for e in st.session_state.cash_expenses)
        st.metric("Total Cash Expenses", f"${total_cash:,.2f}")
        total_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
        st.success(f"**Total Cash ITCs: ${total_itc:.2f}**")


# ============================================================
# PAGE: Phone & Utilities
# ============================================================
elif page == "📱 Phone & Utilities":
    st.title(f"📱 Phone & Utilities - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    st.markdown("**CRA allows business-use percentage of phone bills. Oilfield contractors typically claim 80-100%.**")
    
    st.markdown("### 👨 Greg's Phone (51% owner)")
    col1, col2 = st.columns(2)
    with col1:
        greg_monthly = st.number_input("Greg's Monthly Phone Bill ($)", 
            value=float(st.session_state.phone_bill.get('greg', {}).get('monthly', 0.0)), 
            min_value=0.0, key='greg_monthly')
    with col2:
        greg_pct = st.slider("Greg's Business Use %", 0, 100, 
            st.session_state.phone_bill.get('greg', {}).get('business_pct', 100), key='greg_pct')
    
    greg_annual = greg_monthly * 12
    greg_deductible = greg_annual * (greg_pct / 100)
    greg_itc = greg_deductible * 0.05 / 1.05
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Annual Cost", f"${greg_annual:,.2f}")
    with col2: st.metric("Deductible", f"${greg_deductible:,.2f}")
    with col3: st.metric("ITC", f"${greg_itc:,.2f}")
    
    st.markdown("---")
    st.markdown("### 👩 Lilibeth's Phone (49% owner)")
    col1, col2 = st.columns(2)
    with col1:
        lili_monthly = st.number_input("Lilibeth's Monthly Phone Bill ($)", 
            value=float(st.session_state.phone_bill.get('lilibeth', {}).get('monthly', 0.0)), 
            min_value=0.0, key='lili_monthly')
    with col2:
        lili_pct = st.slider("Lilibeth's Business Use %", 0, 100, 
            st.session_state.phone_bill.get('lilibeth', {}).get('business_pct', 100), key='lili_pct')
    
    lili_annual = lili_monthly * 12
    lili_deductible = lili_annual * (lili_pct / 100)
    lili_itc = lili_deductible * 0.05 / 1.05
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Annual Cost", f"${lili_annual:,.2f}")
    with col2: st.metric("Deductible", f"${lili_deductible:,.2f}")
    with col3: st.metric("ITC", f"${lili_itc:,.2f}")
    
    st.markdown("---")
    total_phone_itc = greg_itc + lili_itc
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Total Annual", f"${greg_annual + lili_annual:,.2f}")
    with col2: st.metric("Total Deductible", f"${greg_deductible + lili_deductible:,.2f}")
    with col3: st.metric("Total ITC", f"${total_phone_itc:,.2f}")
    
    if st.button("💾 Save Phone Bills"):
        st.session_state.phone_bill = {
            'greg': {'monthly': float(greg_monthly), 'business_pct': greg_pct},
            'lilibeth': {'monthly': float(lili_monthly), 'business_pct': lili_pct}
        }
        save_json('phone_bill.json', st.session_state.phone_bill)
        st.success("💾 Saved!")


# ============================================================
# PAGE: Revenue
# ============================================================
elif page == "💰 Revenue":
    st.title(f"💰 Revenue - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    # FIX #2: Only count actual revenue category, not all credits
    revenue_categories = ['Revenue', 'Revenue - Oilfield Services']
    revenue_df = df[df['cra_category'].isin(revenue_categories) & (df['credit'] > 0)]
    total_revenue = revenue_df['credit'].sum()
    
    # Break down by payment type
    wire_mask = revenue_df['description'].str.contains('WIRE TSF', case=False, na=False)
    mobile_mask = revenue_df['description'].str.contains('MOBILE DEPOSIT', case=False, na=False)
    branch_mask = revenue_df['description'].str.contains('BRANCH|DEPOSIT', case=False, na=False) & ~wire_mask & ~mobile_mask
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Wire Transfers", f"${revenue_df.loc[wire_mask, 'credit'].sum():,.2f}",
                  f"{wire_mask.sum()} transactions")
    with col2:
        st.metric("Mobile Deposits", f"${revenue_df.loc[mobile_mask, 'credit'].sum():,.2f}",
                  f"{mobile_mask.sum()} transactions")
    with col3:
        st.metric("Branch Deposits", f"${revenue_df.loc[branch_mask, 'credit'].sum():,.2f}",
                  f"{branch_mask.sum()} transactions")
    with col4:
        other_mask = ~wire_mask & ~mobile_mask & ~branch_mask
        st.metric("Other", f"${revenue_df.loc[other_mask, 'credit'].sum():,.2f}",
                  f"{other_mask.sum()} transactions")
    
    st.markdown("---")
    st.metric("**TOTAL TAXABLE REVENUE**", f"${total_revenue:,.2f}")
    # FIX #1: Show correct GST extraction
    gst_on_revenue = calc_gst_collected(total_revenue)
    st.caption(f"GST included in revenue (5/105): ${gst_on_revenue:,.2f}")
    
    st.markdown("### Revenue Transactions")
    st.dataframe(
        revenue_df[['date', 'description', 'credit', 'needs_review']].sort_values('date'),
        use_container_width=True, height=400
    )
    
    # Show non-revenue credits for transparency
    all_credits = df[df['credit'] > 0]
    non_revenue = all_credits[~all_credits['cra_category'].isin(revenue_categories)]
    if len(non_revenue) > 0:
        st.markdown("---")
        st.markdown("### Non-Revenue Credits (excluded from taxable revenue)")
        st.caption("These are SHL repayments, reversals, refunds — NOT oilfield service revenue")
        st.dataframe(
            non_revenue[['date', 'description', 'credit', 'cra_category']].sort_values('date'),
            use_container_width=True
        )
        st.info(f"Total non-revenue credits: ${non_revenue['credit'].sum():,.2f}")


# ============================================================
# PAGE: Transaction Review (FIX #7: added export button)
# ============================================================
elif page == "📊 Transaction Review":
    st.title(f"📊 Transaction Review - FY {st.session_state.fiscal_year}")
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    col1, col2 = st.columns(2)
    with col1:
        cats = ['All'] + sorted(df['cra_category'].unique().tolist())
        cat_filter = st.selectbox("Category", cats)
    with col2:
        status = st.selectbox("Status", ['All', 'Needs Review', 'Personal', 'Business'])
    
    mask = pd.Series([True] * len(df), index=df.index)
    if cat_filter != 'All':
        mask &= df['cra_category'] == cat_filter
    if status == 'Needs Review':
        mask &= df['needs_review'] == True
    elif status == 'Personal':
        mask &= df['is_personal'] == True
    elif status == 'Business':
        mask &= df['is_personal'] == False
    
    filtered = df[mask]
    
    total_debits = filtered[filtered['debit'] > 0]['debit'].sum()
    total_credits = filtered[filtered['credit'] > 0]['credit'].sum()
    total_itcs = filtered[filtered['is_personal'] == False]['itc_amount'].sum()
    needs_review_count = len(filtered[filtered['needs_review'] == True])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Transactions", len(filtered))
    with col2: st.metric("Total Debits (Out)", f"${total_debits:,.2f}")
    with col3: st.metric("Total ITCs", f"${total_itcs:,.2f}")
    with col4: st.metric("Needs Review", needs_review_count)
    
    if total_credits > 0:
        st.metric("Total Credits (In)", f"${total_credits:,.2f}")
    
    st.dataframe(
        filtered[['date', 'description', 'debit', 'credit', 'cra_category', 'itc_amount', 'is_personal', 'needs_review']], 
        use_container_width=True, height=500
    )
    
    # FIX #7: Export button for filtered view
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 Export Filtered Transactions (CSV)",
            filtered.to_csv(index=False),
            f"transactions_filtered_FY{st.session_state.fiscal_year}.csv",
            "text/csv"
        )
    with col2:
        st.download_button(
            "📥 Export ALL Transactions (CSV)",
            df.to_csv(index=False),
            f"transactions_ALL_FY{st.session_state.fiscal_year}.csv",
            "text/csv"
        )
    
    st.markdown("---")
    st.markdown("### Summary by Category")
    summary = filtered.groupby('cra_category').agg({
        'debit': 'sum', 'credit': 'sum', 'itc_amount': 'sum'
    }).round(2)
    summary.columns = ['Total Debits', 'Total Credits', 'Total ITCs']
    summary = summary.sort_values('Total Debits', ascending=False)
    st.dataframe(summary, use_container_width=True)


# ============================================================
# PAGE: GST Filing (FIX #1: 5/105 extraction, FIX #5: display)
# ============================================================
elif page == "💰 GST Filing":
    st.title(f"💰 GST/HST Return - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    # FIX #1 & #2: Use only taxable revenue with 5/105 extraction
    taxable_revenue = get_taxable_revenue(df)
    gst_collected = calc_gst_collected(taxable_revenue)
    
    # ITCs from bank transactions
    itc_eligible = df[(df['is_personal'] == False) & (df['itc_amount'] > 0)]
    bank_itc = itc_eligible['itc_amount'].sum()
    
    # Cash ITCs
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    
    # Phone ITCs
    greg_phone = st.session_state.phone_bill.get('greg', {})
    lili_phone = st.session_state.phone_bill.get('lilibeth', {})
    greg_phone_itc = (greg_phone.get('monthly', 0.0) * 12 * greg_phone.get('business_pct', 100) / 100) * 0.05 / 1.05
    lili_phone_itc = (lili_phone.get('monthly', 0.0) * 12 * lili_phone.get('business_pct', 100) / 100) * 0.05 / 1.05
    phone_itc = greg_phone_itc + lili_phone_itc
    total_itc = bank_itc + cash_itc + phone_itc
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### GST Collected")
        st.metric("Taxable Revenue (GST-inclusive)", f"${taxable_revenue:,.2f}")
        # FIX #5: Display shows correct formula
        st.metric("GST Collected (5/105 extraction)", f"${gst_collected:,.2f}")
    with col2:
        st.markdown("### Input Tax Credits")
        st.metric("Bank ITCs", f"${bank_itc:,.2f}")
        st.metric("Cash ITCs", f"${cash_itc:,.2f}")
        st.metric("Phone ITCs", f"${phone_itc:,.2f}")
        st.metric("**TOTAL ITCs**", f"${total_itc:,.2f}")
    
    st.markdown("---")
    net_gst = gst_collected - total_itc
    if net_gst > 0:
        st.error(f"## 📤 NET GST OWING: ${net_gst:,.2f}")
    else:
        st.success(f"## 📥 NET GST REFUND: ${abs(net_gst):,.2f}")
    
    st.markdown("---")
    st.markdown("### GST34 Line Summary")
    gst34_data = {
        'Line': ['101', '105', '108', '109'],
        'Description': [
            'Total sales and other revenue (before GST)',
            'GST collected or collectible',
            'Total Input Tax Credits',
            'Net tax (remit or refund)'
        ],
        'Amount': [
            f"${taxable_revenue:,.2f}",
            f"${gst_collected:,.2f}",
            f"${total_itc:,.2f}",
            f"${net_gst:,.2f}" if net_gst > 0 else f"(${abs(net_gst):,.2f})"
        ]
    }
    st.table(pd.DataFrame(gst34_data))
    
    # FIX #5: Corrected display formula
    st.markdown("### 🧮 Calculation Detail")
    st.info(f"""**GST Collected (5/105 extraction from GST-inclusive revenue):**
    ${taxable_revenue:,.2f} × 5 ÷ 105 = ${gst_collected:,.2f}
    
    **ITCs:**
    - Bank transactions: ${bank_itc:,.2f}
    - Cash expenses: ${cash_itc:.2f}
    - Greg's phone: ${greg_phone_itc:.2f}
    - Lilibeth's phone: ${lili_phone_itc:.2f}
    - **Total ITCs:** ${total_itc:.2f}
    
    **Net:** ${gst_collected:,.2f} - ${total_itc:.2f} = ${net_gst:,.2f}""")


# ============================================================
# PAGE: Shareholder Accounts (FIX #4: per-person tracking)
# ============================================================
elif page == "👥 Shareholder Accounts":
    st.title(f"👥 Shareholder Loans - FY {st.session_state.fiscal_year}")
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    st.info("**CRA Rule (ITA 15(2)):** Shareholder loans must be repaid within 1 year of fiscal year-end (Nov 30) or the balance becomes taxable personal income.")
    
    # FIX #4: Track distributions by who they went to
    dist_df = df[df['cra_category'] == 'Shareholder Distribution']
    personal_df = df[df['is_personal'] == True]
    
    # Identify Lilibeth's specific transactions
    lili_dist_out = dist_df[
        (dist_df['debit'] > 0) & 
        dist_df['description'].str.contains('Lilibeth|LILIBETH', case=False, na=False)
    ]['debit'].sum()
    
    lili_dist_in = dist_df[
        (dist_df['credit'] > 0) & 
        dist_df['description'].str.contains('Lilibeth|LILIBETH', case=False, na=False)
    ]['credit'].sum()
    
    # ATM withdrawals and unattributed distributions go to Greg (primary operator)
    total_dist_out = dist_df[dist_df['debit'] > 0]['debit'].sum()
    total_dist_in = dist_df[dist_df['credit'] > 0]['credit'].sum()
    greg_dist_out = total_dist_out - lili_dist_out
    greg_dist_in = total_dist_in - lili_dist_in
    
    total_personal = personal_df['debit'].sum()
    
    st.markdown("### 👨 Greg MacDonald (51% owner)")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Distributions Out", f"${greg_dist_out:,.2f}")
    with col2: st.metric("Repayments In", f"${greg_dist_in:,.2f}")
    with col3: st.metric("Net", f"${greg_dist_out - greg_dist_in:,.2f}")
    
    st.markdown("### 👩 Lilibeth Sejera (49% owner)")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Distributions Out", f"${lili_dist_out:,.2f}")
    with col2: st.metric("Repayments In", f"${lili_dist_in:,.2f}")
    with col3: st.metric("Net", f"${lili_dist_out - lili_dist_in:,.2f}")
    
    st.markdown("---")
    st.markdown("### Summary")
    net_distributions = total_dist_out - total_dist_in
    st.markdown(f"""
    - **Total Distributions Out:** ${total_dist_out:,.2f}
    - **Total Repayments In:** ${total_dist_in:,.2f}
    - **Net Distributions:** ${net_distributions:,.2f}
    - **Personal Expenses (corp-paid):** ${total_personal:,.2f}
    - **Total Shareholder Loan Activity:** ${net_distributions + total_personal:,.2f}
    """)
    
    st.warning("⚠️ Angela determines the final SHL balance in her working papers. These figures are for reference.")
    
    # Show all distribution transactions for review
    with st.expander("📋 All Distribution Transactions"):
        st.dataframe(
            dist_df[['date', 'description', 'debit', 'credit']].sort_values('date'),
            use_container_width=True
        )


# ============================================================
# PAGE: T5 Slips (FIX #3: editable split, FIX: duplicate removed)
# ============================================================
elif page == "📄 T5 Slips":
    st.title(f"📄 T5 Investment Income Slips - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    st.info("**CRA Requirement:** T5 slips must be filed by last day of February following the tax year")
    
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    
    st.markdown("### 💰 Dividend Information")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Distributions from Bank", f"${distributions:,.2f}")
    with col2:
        dividend_type = st.selectbox("Dividend Type", 
            ["Non-Eligible (Other than Eligible)", "Eligible"],
            help="Most CCPC dividends are Non-Eligible unless paid from GRIP")
    
    if distributions > 0:
        st.markdown("---")
        st.warning("⚠️ **Important:** Angela determines the actual dividend amounts and split. "
                   "Distributions from the bank account are NOT the same as declared dividends. "
                   "Enter the amounts Angela provides below.")
        
        # FIX #3: Editable dividend amounts instead of hardcoded 51/49
        st.markdown("### Dividend Amounts (as directed by accountant)")
        col1, col2 = st.columns(2)
        with col1:
            greg_dividend = st.number_input(
                "👨 Greg's Actual Dividend ($)", 
                min_value=0.0, 
                value=float(distributions * 0.51),
                step=100.0,
                help="Enter the amount Angela specifies for Greg's dividend"
            )
        with col2:
            lili_dividend = st.number_input(
                "👩 Lilibeth's Actual Dividend ($)", 
                min_value=0.0, 
                value=float(distributions * 0.49),
                step=100.0,
                help="Enter the amount Angela specifies for Lilibeth's dividend"
            )
        
        total_dividends = greg_dividend + lili_dividend
        if abs(total_dividends - distributions) > 1:
            st.info(f"Total dividends entered (${total_dividends:,.2f}) differs from total distributions (${distributions:,.2f}). This is normal — Angela determines the declared amount.")
        
        if "Eligible" in dividend_type:
            grossup_rate = 0.38
            tax_credit_rate = 0.150198
        else:
            grossup_rate = 0.15
            tax_credit_rate = 0.090301
        
        greg_grossup = greg_dividend * grossup_rate
        lili_grossup = lili_dividend * grossup_rate
        greg_taxable = greg_dividend + greg_grossup
        lili_taxable = lili_dividend + lili_grossup
        greg_credit = greg_taxable * tax_credit_rate
        lili_credit = lili_taxable * tax_credit_rate
        
        st.markdown("---")
        st.markdown("#### 👨 Greg MacDonald")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Actual Dividend", f"${greg_dividend:,.2f}")
        with col2: st.metric("Gross-up", f"${greg_grossup:,.2f}")
        with col3: st.metric("Taxable Amount", f"${greg_taxable:,.2f}")
        with col4: st.metric("Tax Credit", f"${greg_credit:,.2f}")
        
        st.markdown("#### 👩 Lilibeth Sejera")
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Actual Dividend", f"${lili_dividend:,.2f}")
        with col2: st.metric("Gross-up", f"${lili_grossup:,.2f}")
        with col3: st.metric("Taxable Amount", f"${lili_taxable:,.2f}")
        with col4: st.metric("Tax Credit", f"${lili_credit:,.2f}")
        
        st.markdown("---")
        st.markdown("### 📊 T5 Summary")
        summary_data = {
            'Shareholder': ['Greg MacDonald', 'Lilibeth Sejera', 'TOTAL'],
            'Actual Dividend': [f'${greg_dividend:,.2f}', f'${lili_dividend:,.2f}', f'${total_dividends:,.2f}'],
            'Taxable Amount': [f'${greg_taxable:,.2f}', f'${lili_taxable:,.2f}', f'${greg_taxable + lili_taxable:,.2f}'],
            'Tax Credit': [f'${greg_credit:,.2f}', f'${lili_credit:,.2f}', f'${greg_credit + lili_credit:,.2f}']
        }
        st.table(pd.DataFrame(summary_data))
        
        # Download T5 data
        t5_csv = pd.DataFrame([
            {'Name': 'Greg MacDonald', 'SIN': '', 'Actual_Dividend': greg_dividend, 'Grossup': greg_grossup, 
             'Taxable_Amount': greg_taxable, 'Fed_Credit': greg_credit, 'Type': dividend_type},
            {'Name': 'Lilibeth Sejera', 'SIN': '', 'Actual_Dividend': lili_dividend, 'Grossup': lili_grossup,
             'Taxable_Amount': lili_taxable, 'Fed_Credit': lili_credit, 'Type': dividend_type}
        ])
        st.download_button("📥 Download T5 Data (CSV)", t5_csv.to_csv(index=False), 
                          f"T5_Slips_FY{st.session_state.fiscal_year}.csv", "text/csv")
    else:
        st.info("No dividends paid this fiscal year. T5 slips not required.")


# ============================================================
# PAGE: Mileage Log (embeds the CRA-compliant HTML log)
# ============================================================
elif page == "🚛 Mileage Log":
    st.title(f"🚛 Mileage & Fuel Summary - FY {st.session_state.fiscal_year}")
    st.caption("Chevrolet Silverado — 100% Business Use")
    
    df = get_clean_df()
    
    # Mileage log summary
    st.markdown("### 📊 Annual Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Starting Odometer", "97,178 km")
    with col2: st.metric("Ending Odometer", "111,306 km")
    with col3: st.metric("Total KM Driven", "14,128 km")
    with col4: st.metric("Business Use", "100%")
    
    st.markdown("---")
    
    # Fuel from bank transactions
    if df is not None:
        fuel_categories = ['Fuel & Petroleum', 'Fuel']
        fuel_df = df[df['cra_category'].isin(fuel_categories) & (df['debit'] > 0)]
        total_fuel = fuel_df['debit'].sum()
        fuel_itc = fuel_df['itc_amount'].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Total Fuel (Company Card)", f"${total_fuel:,.2f}")
        with col2: st.metric("Fuel Fills", f"{len(fuel_df)}")
        with col3: st.metric("Fuel ITCs", f"${fuel_itc:,.2f}")
        
        st.markdown("---")
        st.markdown("### 📅 Monthly Fuel Breakdown")
        fuel_df = fuel_df.copy()
        fuel_df['month'] = pd.to_datetime(fuel_df['date']).dt.strftime('%Y-%m')
        monthly = fuel_df.groupby('month').agg({'debit': ['sum', 'count']}).reset_index()
        monthly.columns = ['Month', 'Fuel Spend', 'Fills']
        monthly['Avg/Fill'] = (monthly['Fuel Spend'] / monthly['Fills']).round(2)
        st.dataframe(monthly, use_container_width=True)
    
    st.markdown("---")
    st.markdown("### ⛽ Fuel Economy Note")
    st.info("""**Why fuel spend appears high relative to km:**
    
    Greg operates on oilfield lease sites (Redwater, Bruderheim, Opal, Gibbons). 
    During Alberta winter months (-25°C to -40°C), the Silverado must remain running at idle 
    for safety and operational reasons:
    
    - **Emergency egress** — immediate evacuation capability for H2S or blowout
    - **Engine protection** — extreme cold risks equipment failure if shut down
    - **Worker safety** — cab heat required during breaks
    
    Winter months (Dec-Mar) average ~$1,450/month in fuel vs. summer (May-Sep) ~$740/month. 
    The ~$710/month winter premium represents idle fuel consumption with zero odometer movement.
    
    This is standard practice across all Alberta oilfield operations and is a fully deductible business expense.
    
    **Lilibeth's personal card fuel for business trips is intentionally excluded** from these figures 
    (conservative position — company claims less than actual business fuel used).""")
    
    # Embed the full CRA-compliant mileage log HTML
    st.markdown("---")
    st.markdown("### 📋 Full CRA-Compliant Mileage Log (292 Trips)")
    
    mileage_html_path = Path(__file__).parent / "static" / "mileage_log_FY2024-2025.html"
    if mileage_html_path.exists():
        import streamlit.components.v1 as components
        with open(mileage_html_path, 'r') as f:
            html_content = f.read()
        components.html(html_content, height=800, scrolling=True)
        
        # Download button
        st.download_button(
            "📥 Download Mileage Log (HTML)",
            html_content,
            "RigBooks_CRA_Mileage_Log_FY2024-2025.html",
            "text/html"
        )
    else:
        st.warning("Mileage log HTML file not found. Upload it to `static/mileage_log_FY2024-2025.html`")


# ============================================================
# PAGE: Receipt Tracker
# ============================================================
elif page == "🧾 Receipt Tracker":
    st.title(f"🧾 Receipt Tracker - FY {st.session_state.fiscal_year}")
    st.markdown("""| Amount | Receipt? |
    |--------|----------|
    | < $30 | ❌ No |
    | $30-$150 | ⚠️ Recommended |
    | > $150 | ✅ Required |""")
    
    df = get_clean_df()
    if df is not None:
        needs_receipts = df[(df['debit'] > 150) & (df['itc_amount'] > 0)]
        st.markdown(f"### Over $150: {len(needs_receipts)} transactions")
        if len(needs_receipts) > 0:
            st.dataframe(needs_receipts[['date', 'description', 'debit', 'itc_amount']].sort_values('debit', ascending=False))
            st.warning(f"⚠️ ITCs at risk without receipts: ${needs_receipts['itc_amount'].sum():,.2f}")


# ============================================================
# PAGE: Final Summary
# ============================================================
elif page == "📋 Final Summary":
    st.title(f"📋 Final Summary - FY {st.session_state.fiscal_year}")
    df = get_clean_df()
    if df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    # FIX #1 & #2: Corrected GST calculation
    taxable_revenue = get_taxable_revenue(df)
    gst_collected = calc_gst_collected(taxable_revenue)
    
    bank_itc = df[(df['is_personal'] == False) & (df['itc_amount'] > 0)]['itc_amount'].sum()
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    greg_phone = st.session_state.phone_bill.get('greg', {})
    lili_phone = st.session_state.phone_bill.get('lilibeth', {})
    phone_itc = ((greg_phone.get('monthly', 0.0) * 12 * greg_phone.get('business_pct', 100) / 100) + 
                 (lili_phone.get('monthly', 0.0) * 12 * lili_phone.get('business_pct', 100) / 100)) * 0.05 / 1.05
    total_itc = bank_itc + cash_itc + phone_itc
    net_gst = gst_collected - total_itc
    
    st.markdown("## GST Summary")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("GST Collected", f"${gst_collected:,.2f}")
    with col2: st.metric("Total ITCs", f"${total_itc:,.2f}")
    with col3: 
        if net_gst > 0:
            st.metric("Net GST Owing", f"${net_gst:,.2f}")
        else:
            st.metric("Net GST Refund", f"${abs(net_gst):,.2f}")
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📥 All Transactions (CSV)", df.to_csv(index=False), 
                          f"transactions_FY{st.session_state.fiscal_year}.csv", "text/csv")
    with col2:
        gst_df = df[df['itc_amount'] > 0][['date', 'description', 'debit', 'cra_category', 'itc_amount']]
        st.download_button("📥 GST Working Papers (CSV)", gst_df.to_csv(index=False), 
                          f"gst_itc_FY{st.session_state.fiscal_year}.csv", "text/csv")


# ============================================================
# PAGE: Audit Guide
# ============================================================
elif page == "🛡️ Audit Guide":
    st.title("🛡️ Audit-Proof Guide")
    st.markdown("""## CRA Receipt Requirements
    | Expense | Receipt Required? |
    |---------|----------|
    | < $30 | ❌ Bank statement sufficient |
    | $30-$150 | ⚠️ Recommended |
    | > $150 | ✅ Required for ITC |
    
    ## Key Documentation
    - **Mileage log** with odometer readings (see 🚛 Mileage Log page)
    - **Bank statements** with all transactions classified
    - **Receipts** for expenses over $150
    - **Board resolution** for dividend declarations
    - **T5 slips** filed by Feb 28
    
    ## Your Data
    All fiscal years stored in `data/` folder with automatic persistence.""")
    st.success("✅ With proper documentation, you're audit-ready!")
