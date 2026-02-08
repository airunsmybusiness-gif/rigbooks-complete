"""
CRA-Compliant Corporate Bookkeeping Dashboard
Cape Bretoner's Oilfield Services Ltd.
COMPLETE VERSION with all CRA rules and requirements
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
from helpers.revenue_simple import calculate_revenue

st.set_page_config(
    page_title="CRA-Ready Books - Cape Bretoner's Oilfield",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DATA_DIR = Path("data")
BASE_DATA_DIR.mkdir(exist_ok=True)

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
    "📤 Upload & Process", "💰 Revenue", "💵 Cash Expenses", "📱 Phone & Utilities",
    "📊 Transaction Review", "💰 GST Filing", "👥 Shareholder Accounts",
    "📄 T5 Slips", "🧾 Receipt Tracker", "📋 Final Summary", "🛡️ Audit Guide"
])


def load_cibc_csv(content):
    lines = content.strip().split('\n')
    data = []
    for line in lines:
        if not line.strip(): continue
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                date = pd.to_datetime(parts[0].strip()).strftime('%Y-%m-%d')
                desc = parts[1].strip()
                debit = float(parts[2].strip()) if parts[2].strip() else 0
                credit = float(parts[3].strip()) if len(parts) > 3 and parts[3].strip() else 0
                data.append({'date': date, 'description': desc, 'debit': debit, 'credit': credit})
            except: continue
    return pd.DataFrame(data)

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
        st.success(f"💾 Saved to: data/{st.session_state.fiscal_year}/corporate_df.pkl")
        
        if st.button("🔄 Process Statement", type="primary"):
            with st.spinner("Classifying transactions..."):
                classifier = TransactionClassifier()
                st.session_state.classified_df = classifier.classify_dataframe(
                    st.session_state.corporate_df, 'corporate'
                )
                save_dataframe('classified_df.pkl', st.session_state.classified_df)
            st.success("✅ Processing complete!")
            st.success(f"💾 Saved to: data/{st.session_state.fiscal_year}/classified_df.pkl")
            st.balloons()


elif page == "💰 Revenue":
    st.title(f"💰 Revenue - FY {st.session_state.fiscal_year}")
    
    if st.session_state.classified_df is None:
        st.warning("Upload and process bank statement first")
        st.stop()
    
    rev = calculate_revenue(st.session_state.classified_df)
    
    st.markdown("### Revenue Breakdown")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Wire Transfers", f"${rev['wire_total']:,.2f}")
    with col2:
        st.metric("Mobile Deposits", f"${rev['mobile_total']:,.2f}")
    with col3:
        st.metric("Branch Deposits", f"${rev['branch_total']:,.2f}")
    
    st.markdown("---")
    st.metric("**TOTAL REVENUE**", f"${rev['total']:,.2f}")
    
    with st.expander("View Transactions"):
        all_rev = pd.concat([rev['wire_transfers'], rev['mobile_deposits'], rev['branch_deposits']])
        st.dataframe(all_rev[['date', 'description', 'credit']].sort_values('date'), use_container_width=True)

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
        st.success(f"💾 Saved to: data/{st.session_state.fiscal_year}/cash_expenses.json")
    
    if st.session_state.cash_expenses:
        st.markdown("### Cash Expenses Entered")
        cash_df = pd.DataFrame(st.session_state.cash_expenses)
        st.dataframe(cash_df, use_container_width=True)
        total_cash = sum(e['amount'] for e in st.session_state.cash_expenses)
        st.metric("Total Cash Expenses", f"${total_cash:,.2f}")
        st.markdown("---")
        st.markdown("### 🧮 ITC Calculation Breakdown")
        st.info("**How ITCs are calculated:** GST = 5%, Formula: Amount × 0.05 / 1.05")
        for exp in st.session_state.cash_expenses:
            itc = exp['amount'] * 0.05 / 1.05
            st.markdown(f"**{exp['description']}** (${exp['amount']:.2f}) → ITC: ${itc:.2f}")
        total_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
        st.success(f"**Total Cash ITCs: ${total_itc:.2f}**")

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
    st.markdown("### 📊 Combined Phone Bill Totals")
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
        st.success(f"💾 Saved to: data/{st.session_state.fiscal_year}/phone_bill.json")
    
    st.markdown("---")
    st.markdown("### 🧮 Calculation Breakdown")
    st.info(f"""**Greg's Phone:**
    1. Monthly: ${greg_monthly:.2f}
    2. Annual: ${greg_monthly:.2f} × 12 = ${greg_annual:.2f}
    3. Business ({greg_pct}%): ${greg_annual:.2f} × {greg_pct}% = ${greg_deductible:.2f}
    4. ITC: ${greg_deductible:.2f} × 0.05 / 1.05 = ${greg_itc:.2f}
    
    **Lilibeth's Phone:**
    1. Monthly: ${lili_monthly:.2f}
    2. Annual: ${lili_monthly:.2f} × 12 = ${lili_annual:.2f}
    3. Business ({lili_pct}%): ${lili_annual:.2f} × {lili_pct}% = ${lili_deductible:.2f}
    4. ITC: ${lili_deductible:.2f} × 0.05 / 1.05 = ${lili_itc:.2f}
    
    **Combined Total:** ITC = ${greg_itc:.2f} + ${lili_itc:.2f} = ${total_phone_itc:.2f}""")

elif page == "📊 Transaction Review":
    st.title(f"📊 Transaction Review - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    df = st.session_state.classified_df.copy()
    col1, col2 = st.columns(2)
    with col1:
        cats = ['All'] + sorted(df['cra_category'].unique().tolist())
        cat_filter = st.selectbox("Category", cats)
    with col2:
        status = st.selectbox("Status", ['All', 'Needs Review', 'Personal', 'Business'])
    
    mask = pd.Series([True] * len(df))
    if cat_filter != 'All':
        mask &= df['cra_category'] == cat_filter
    if status == 'Needs Review':
        mask &= df['needs_review'] == True
    elif status == 'Personal':
        mask &= df['is_personal'] == True
    elif status == 'Business':
        mask &= df['is_personal'] == False
    
    filtered = df[mask]
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Transactions", len(filtered))
    with col2: st.metric("Total Debits", f"${filtered['debit'].sum():,.2f}")
    with col3: st.metric("Total ITCs", f"${filtered['itc_amount'].sum():,.2f}")
    with col4: st.metric("Needs Review", len(filtered[filtered['needs_review']]))
    st.dataframe(filtered[['date', 'description', 'debit', 'credit', 'cra_category', 'itc_amount', 'is_personal', 'needs_review']], 
                 use_container_width=True, height=500)

elif page == "💰 GST Filing":
    st.title(f"💰 GST/HST Return - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    df = st.session_state.classified_df.copy()
    calc = GSTCalculator()
    gst = calc.calculate_period(df)
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    
    greg_phone = st.session_state.phone_bill.get('greg', {})
    lili_phone = st.session_state.phone_bill.get('lilibeth', {})
    greg_phone_itc = (greg_phone.get('monthly', 0.0) * 12 * greg_phone.get('business_pct', 100) / 100) * 0.05 / 1.05
    lili_phone_itc = (lili_phone.get('monthly', 0.0) * 12 * lili_phone.get('business_pct', 100) / 100) * 0.05 / 1.05
    phone_itc = greg_phone_itc + lili_phone_itc
    total_itc = gst['total_itc'] + cash_itc + phone_itc
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### GST Collected")
        st.metric("Total Revenue", f"${gst['total_revenue']:,.2f}")
        st.metric("GST Collected (5%)", f"${gst['gst_collected']:,.2f}")
    with col2:
        st.markdown("### Input Tax Credits")
        st.metric("Bank ITCs", f"${gst['total_itc']:,.2f}")
        st.metric("Cash ITCs", f"${cash_itc:,.2f}")
        st.metric("Phone ITCs (Both)", f"${phone_itc:,.2f}")
        st.metric("**TOTAL ITCs**", f"${total_itc:,.2f}")
    
    st.markdown("---")
    net_gst = gst['gst_collected'] - total_itc
    if net_gst > 0:
        st.error(f"## 📤 NET GST OWING: ${net_gst:,.2f}")
    else:
        st.success(f"## 📥 NET GST REFUND: ${abs(net_gst):,.2f}")
    
    st.markdown("---")
    st.markdown("### 🧮 GST Calculation")
    st.info(f"""**GST Collected:** ${gst['total_revenue']:,.2f} × 0.05 = ${gst['gst_collected']:,.2f}
    
    **ITCs:**
    - Bank: ${gst['total_itc']:,.2f}
    - Cash: ${cash_itc:.2f}
    - Greg Phone: ${greg_phone_itc:.2f}
    - Lilibeth Phone: ${lili_phone_itc:.2f}
    - **Total:** ${total_itc:.2f}
    
    **Net:** ${gst['gst_collected']:,.2f} - ${total_itc:.2f} = ${net_gst:,.2f}""")

elif page == "👥 Shareholder Accounts":
    st.title(f"👥 Shareholder Loans - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    df = st.session_state.classified_df
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    personal = df[df['is_personal'] == True]['debit'].sum()
    total_loan = distributions + personal
    
    st.info("**CRA Rule:** Must repay within 1 year of Nov 30 or becomes taxable income")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 👨 Greg (51%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.51:,.2f}")
    with col2:
        st.markdown("### 👩 Lilibeth (49%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.49:,.2f}")
    
    st.markdown(f"""### Totals
    - Distributions: ${distributions:,.2f}
    - Personal: ${personal:,.2f}
    - **Total:** ${total_loan:,.2f}""")


elif page == "📄 T5 Slips":
    st.title(f"📄 T5 Investment Income Slips - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    
    st.info("**CRA Requirement:** T5 slips must be filed by last day of February following the tax year")
    
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    # Get dividend information from shareholder accounts
    df = st.session_state.classified_df
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    
    st.markdown("### 💰 Dividend Information")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Dividends Paid", f"${distributions:,.2f}")
    with col2:
        dividend_type = st.selectbox("Dividend Type", 
            ["Non-Eligible (Other than Eligible)", "Eligible"],
            help="Most CCPC dividends are Non-Eligible unless paid from GRIP")
    
    if distributions > 0:
        st.markdown("---")
        st.markdown("### 👥 T5 Slips for Shareholders")
        
        # Calculate T5 amounts
        greg_pct = 0.51
        lili_pct = 0.49
        
        greg_dividend = distributions * greg_pct
        lili_dividend = distributions * lili_pct
        
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
        
        # Greg's T5
        st.markdown("#### 👨 Greg MacDonald (51% owner)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Actual Dividend", f"${greg_dividend:,.2f}")
        with col2:
            st.metric("Gross-up", f"${greg_grossup:,.2f}")
        with col3:
            st.metric("Taxable Amount", f"${greg_taxable:,.2f}")
        with col4:
            st.metric("Tax Credit", f"${greg_credit:,.2f}")
        
        with st.expander("📋 Greg's T5 Slip Details"):
            st.markdown(f"""
            **STATEMENT OF INVESTMENT INCOME - T5**
            
            **Payer:** Cape Bretoner's Oilfield Services Ltd.  
            **Business Number:** 825303795RC0001  
            **Tax Year:** {st.session_state.fiscal_year}
            
            **Recipient:** Gregory MacDonald  
            **Ownership:** 51%  
            **SIN:** ___ ___ ___ _(enter for filing)_
            
            **Box 10 - Interest:** $0.00  
            **Box 11 - Actual Dividend:** ${greg_dividend:,.2f}  
            **Box 12 - Taxable Dividend (with gross-up):** ${greg_grossup:,.2f}  
            **Box 24 - Type:** {dividend_type}
            
            **For Personal T1 Return:**
            - Report ${greg_taxable:,.2f} on Line 12000 (Taxable Dividends)
            - Claim ${greg_credit:,.2f} as Federal Dividend Tax Credit
            
            **Calculation:**
            1. Actual dividend: ${distributions:,.2f} × 51% = ${greg_dividend:,.2f}
            2. Gross-up: ${greg_dividend:,.2f} × {grossup_rate:.0%} = ${greg_grossup:,.2f}
            3. Taxable: ${greg_dividend:,.2f} + ${greg_grossup:,.2f} = ${greg_taxable:,.2f}
            4. Credit: ${greg_taxable:,.2f} × {tax_credit_rate:.4%} = ${greg_credit:,.2f}
            """)
        
        st.markdown("---")
        
        # Lilibeth's T5
        st.markdown("#### 👩 Lilibeth Sejera (49% owner)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Actual Dividend", f"${lili_dividend:,.2f}")
        with col2:
            st.metric("Gross-up", f"${lili_grossup:,.2f}")
        with col3:
            st.metric("Taxable Amount", f"${lili_taxable:,.2f}")
        with col4:
            st.metric("Tax Credit", f"${lili_credit:,.2f}")
        
        with st.expander("📋 Lilibeth's T5 Slip Details"):
            st.markdown(f"""
            **STATEMENT OF INVESTMENT INCOME - T5**
            
            **Payer:** Cape Bretoner's Oilfield Services Ltd.  
            **Business Number:** 825303795RC0001  
            **Tax Year:** {st.session_state.fiscal_year}
            
            **Recipient:** Lilibeth Sejera  
            **Ownership:** 49%  
            **SIN:** ___ ___ ___ _(enter for filing)_
            
            **Box 10 - Interest:** $0.00  
            **Box 11 - Actual Dividend:** ${lili_dividend:,.2f}  
            **Box 12 - Taxable Dividend (with gross-up):** ${lili_grossup:,.2f}  
            **Box 24 - Type:** {dividend_type}
            
            **For Personal T1 Return:**
            - Report ${lili_taxable:,.2f} on Line 12000 (Taxable Dividends)
            - Claim ${lili_credit:,.2f} as Federal Dividend Tax Credit
            
            **Calculation:**
            1. Actual dividend: ${distributions:,.2f} × 49% = ${lili_dividend:,.2f}
            2. Gross-up: ${lili_dividend:,.2f} × {grossup_rate:.0%} = ${lili_grossup:,.2f}
            3. Taxable: ${lili_dividend:,.2f} + ${lili_grossup:,.2f} = ${lili_taxable:,.2f}
            4. Credit: ${lili_taxable:,.2f} × {tax_credit_rate:.4%} = ${lili_credit:,.2f}
            """)
        
        st.markdown("---")
        st.markdown("### 📊 T5 Summary")
        
        summary_data = {
            'Shareholder': ['Greg MacDonald', 'Lilibeth Sejera', 'TOTAL'],
            'Ownership': ['51%', '49%', '100%'],
            'Actual Dividend': [f'${greg_dividend:,.2f}', f'${lili_dividend:,.2f}', f'${distributions:,.2f}'],
            'Taxable Amount': [f'${greg_taxable:,.2f}', f'${lili_taxable:,.2f}', f'${greg_taxable + lili_taxable:,.2f}'],
            'Tax Credit': [f'${greg_credit:,.2f}', f'${lili_credit:,.2f}', f'${greg_credit + lili_credit:,.2f}']
        }
        st.table(pd.DataFrame(summary_data))
        
        st.success("✅ T5 slips ready. Print and provide to shareholders by Feb 28.")
        st.warning("⚠️ **Action Required:** File T5 Summary (T5SUM) with CRA by Feb 28 electronically or mail")
        
    else:
        st.info("No dividends paid this fiscal year. T5 slips not required.")



elif page == "📄 T5 Slips":
    st.title(f"📄 T5 Investment Income Slips - FY {st.session_state.fiscal_year}")
    st.caption(f"Period: Dec 1, {fy_start} to Nov 30, {fy_end}")
    
    st.info("**CRA Requirement:** T5 slips must be filed by last day of February following the tax year")
    
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    df = st.session_state.classified_df
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    
    st.markdown("### 💰 Dividend Information")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Dividends Paid", f"${distributions:,.2f}")
    with col2:
        dividend_type = st.selectbox("Dividend Type", 
            ["Non-Eligible (Other than Eligible)", "Eligible"],
            help="Most CCPC dividends are Non-Eligible unless paid from GRIP")
    
    if distributions > 0:
        st.markdown("---")
        st.markdown("### 👥 T5 Slips for Shareholders")
        
        greg_pct = 0.51
        lili_pct = 0.49
        greg_dividend = distributions * greg_pct
        lili_dividend = distributions * lili_pct
        
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
        
        st.markdown("#### 👨 Greg MacDonald (51% owner)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Actual Dividend", f"${greg_dividend:,.2f}")
        with col2:
            st.metric("Gross-up", f"${greg_grossup:,.2f}")
        with col3:
            st.metric("Taxable Amount", f"${greg_taxable:,.2f}")
        with col4:
            st.metric("Tax Credit", f"${greg_credit:,.2f}")
        
        with st.expander("📋 Greg's T5 Slip - Click to View"):
            st.markdown(f"""
**STATEMENT OF INVESTMENT INCOME - T5**

**Payer Information:**
- Name: Cape Bretoner's Oilfield Services Ltd.
- Business Number: 825303795RC0001
- Tax Year: {st.session_state.fiscal_year}

**Recipient Information:**
- Name: Gregory MacDonald
- Ownership: 51%
- SIN: ___ ___ ___ (enter when filing)

**T5 Boxes:**
- Box 10 (Interest): $0.00
- Box 11 (Actual Dividend): ${greg_dividend:,.2f}
- Box 12 (Taxable Dividend): ${greg_grossup:,.2f}
- Box 24 (Type): {dividend_type}

**For Greg's Personal T1 Return:**
- Report ${greg_taxable:,.2f} on Line 12000 (Taxable Dividends)
- Claim ${greg_credit:,.2f} Federal Dividend Tax Credit

**Calculation Breakdown:**
1. Actual dividend: ${distributions:,.2f} × 51% = ${greg_dividend:,.2f}
2. Gross-up: ${greg_dividend:,.2f} × {grossup_rate:.0%} = ${greg_grossup:,.2f}
3. Taxable: ${greg_dividend:,.2f} + ${greg_grossup:,.2f} = ${greg_taxable:,.2f}
4. Federal credit: ${greg_taxable:,.2f} × {tax_credit_rate:.4%} = ${greg_credit:,.2f}
            """)
        
        st.markdown("---")
        st.markdown("#### 👩 Lilibeth Sejera (49% owner)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Actual Dividend", f"${lili_dividend:,.2f}")
        with col2:
            st.metric("Gross-up", f"${lili_grossup:,.2f}")
        with col3:
            st.metric("Taxable Amount", f"${lili_taxable:,.2f}")
        with col4:
            st.metric("Tax Credit", f"${lili_credit:,.2f}")
        
        with st.expander("📋 Lilibeth's T5 Slip - Click to View"):
            st.markdown(f"""
**STATEMENT OF INVESTMENT INCOME - T5**

**Payer Information:**
- Name: Cape Bretoner's Oilfield Services Ltd.
- Business Number: 825303795RC0001
- Tax Year: {st.session_state.fiscal_year}

**Recipient Information:**
- Name: Lilibeth Sejera
- Ownership: 49%
- SIN: ___ ___ ___ (enter when filing)

**T5 Boxes:**
- Box 10 (Interest): $0.00
- Box 11 (Actual Dividend): ${lili_dividend:,.2f}
- Box 12 (Taxable Dividend): ${lili_grossup:,.2f}
- Box 24 (Type): {dividend_type}

**For Lilibeth's Personal T1 Return:**
- Report ${lili_taxable:,.2f} on Line 12000 (Taxable Dividends)
- Claim ${lili_credit:,.2f} Federal Dividend Tax Credit

**Calculation Breakdown:**
1. Actual dividend: ${distributions:,.2f} × 49% = ${lili_dividend:,.2f}
2. Gross-up: ${lili_dividend:,.2f} × {grossup_rate:.0%} = ${lili_grossup:,.2f}
3. Taxable: ${lili_dividend:,.2f} + ${lili_grossup:,.2f} = ${lili_taxable:,.2f}
4. Federal credit: ${lili_taxable:,.2f} × {tax_credit_rate:.4%} = ${lili_credit:,.2f}
            """)
        
        st.markdown("---")
        st.markdown("### 📊 T5 Summary (T5SUM)")
        summary_data = {
            'Shareholder': ['Greg MacDonald', 'Lilibeth Sejera', '**TOTAL**'],
            'Ownership': ['51%', '49%', '100%'],
            'Actual Dividend': [f'${greg_dividend:,.2f}', f'${lili_dividend:,.2f}', f'${distributions:,.2f}'],
            'Taxable Amount': [f'${greg_taxable:,.2f}', f'${lili_taxable:,.2f}', f'${greg_taxable + lili_taxable:,.2f}'],
            'Tax Credit': [f'${greg_credit:,.2f}', f'${lili_credit:,.2f}', f'${greg_credit + lili_credit:,.2f}']
        }
        st.table(pd.DataFrame(summary_data))
        
        st.success("✅ T5 slips calculated. Provide to shareholders for their personal tax returns.")
        st.warning("⚠️ **CRA Filing Deadline:** File T5 Summary electronically by February 28")
        
        st.markdown("---")
        st.markdown("### 📥 Download T5 Data")
        t5_csv = pd.DataFrame([
            {'Name': 'Greg MacDonald', 'SIN': '', 'Actual_Dividend': greg_dividend, 'Grossup': greg_grossup, 
             'Taxable_Amount': greg_taxable, 'Fed_Credit': greg_credit},
            {'Name': 'Lilibeth Sejera', 'SIN': '', 'Actual_Dividend': lili_dividend, 'Grossup': lili_grossup,
             'Taxable_Amount': lili_taxable, 'Fed_Credit': lili_credit}
        ])
        st.download_button("📥 Download T5 Data (CSV)", t5_csv.to_csv(index=False), 
                          f"T5_Slips_FY{st.session_state.fiscal_year}.csv", "text/csv")
    else:
        st.info("No dividends paid this fiscal year. T5 slips not required.")

elif page == "🧾 Receipt Tracker":
    st.title(f"🧾 Receipt Tracker - FY {st.session_state.fiscal_year}")
    st.markdown("""| Amount | Receipt? |
    |--------|----------|
    | < $30 | ❌ No |
    | $30-$150 | ⚠️ Recommended |
    | > $150 | ✅ Required |""")
    
    if st.session_state.classified_df is not None:
        df = st.session_state.classified_df
        needs_receipts = df[(df['debit'] > 150) & (df['itc_amount'] > 0)]
        st.markdown(f"### Over $150: {len(needs_receipts)} transactions")
        if len(needs_receipts) > 0:
            st.dataframe(needs_receipts[['date', 'description', 'debit', 'itc_amount']].sort_values('debit', ascending=False))
            st.warning(f"⚠️ ITCs at risk: ${needs_receipts['itc_amount'].sum():,.2f}")

elif page == "📋 Final Summary":
    st.title(f"📋 Final Summary - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Please upload and process a statement first.")
        st.stop()
    
    df = st.session_state.classified_df
    calc = GSTCalculator()
    gst = calc.calculate_period(df)
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    
    greg_phone = st.session_state.phone_bill.get('greg', {})
    lili_phone = st.session_state.phone_bill.get('lilibeth', {})
    phone_itc = ((greg_phone.get('monthly', 0.0) * 12 * greg_phone.get('business_pct', 100) / 100) + 
                 (lili_phone.get('monthly', 0.0) * 12 * lili_phone.get('business_pct', 100) / 100)) * 0.05 / 1.05
    
    total_itc = gst['total_itc'] + cash_itc + phone_itc
    net_gst = gst['gst_collected'] - total_itc
    
    st.markdown("## GST Summary")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Collected", f"${gst['gst_collected']:,.2f}")
    with col2: st.metric("ITCs", f"${total_itc:,.2f}")
    with col3: st.metric("Net", f"${net_gst:,.2f}" if net_gst > 0 else f"${abs(net_gst):,.2f} Refund")
    
    st.info(f"💾 All data saved in: `data/{st.session_state.fiscal_year}/`")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📥 All Transactions", df.to_csv(index=False), 
                          f"transactions_FY{st.session_state.fiscal_year}.csv", "text/csv")
    with col2:
        gst_df = df[df['itc_amount'] > 0][['date', 'description', 'debit', 'cra_category', 'itc_amount']]
        st.download_button("📥 GST Papers", gst_df.to_csv(index=False), 
                          f"gst_itc_FY{st.session_state.fiscal_year}.csv", "text/csv")

elif page == "🛡️ Audit Guide":
    st.title("🛡️ Audit-Proof Guide")
    st.markdown("""## CRA Requirements
    | Expense | Receipt? |
    |---------|----------|
    | < $30 | ❌ No |
    | $30-$150 | ⚠️ Recommended |
    | > $150 | ✅ Required |
    
    ## Your Data
    All fiscal years stored permanently in `data/` folder. Data persists forever - no backups needed.""")
    st.success("✅ With proper documentation, you're audit-ready!")
