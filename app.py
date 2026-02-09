"""
CRA-Compliant Corporate Bookkeeping Dashboard
Cape Bretoner's Oilfield Services Ltd.
COMPLETE VERSION with all CRA rules and requirements
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import json

st.set_page_config(page_title="RigBooks - Cape Bretoner's", layout="wide")

# Session state initialization
if 'fiscal_year' not in st.session_state:
    st.session_state.fiscal_year = "2024-2025"
if 'corporate_df' not in st.session_state:
    st.session_state.corporate_df = None
if 'classified_df' not in st.session_state:
    st.session_state.classified_df = None
if 'cash_expenses' not in st.session_state:
    st.session_state.cash_expenses = []
if 'phone_bill' not in st.session_state:
    st.session_state.phone_bill = {
        'greg': {'months': {m: 0.0 for m in ['Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov']}, 'business_pct': 100},
        'lilibeth': {'months': {m: 0.0 for m in ['Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov']}, 'business_pct': 100}
    }

fy_start, fy_end = st.session_state.fiscal_year.split('-')
st.sidebar.title("RigBooks")
st.sidebar.markdown(f"**FY {st.session_state.fiscal_year}**")
st.sidebar.markdown(f"Dec 1, {fy_start} → Nov 30, {fy_end}")
st.sidebar.markdown("---")
st.sidebar.markdown("**Ownership**")
st.sidebar.markdown("👨 Greg: 51% | 👩 Lilibeth: 49%")

page = st.sidebar.radio("Navigation", [
    "📤 Upload & Process", "💰 Revenue", "📱 Phone Bills", 
    "💵 Cash Expenses", "💰 GST Filing", "👥 Shareholders", "📋 Summary"
])

CRA_CATEGORIES = {
    'Fuel': {'keywords': ['SHELL', 'ESSO', 'PETRO', 'HUSKY', 'GAS', 'FUEL', 'PIONEER', 'MOBIL', 'CHEVRON', 'COOP PETROLEUM'], 'itc': True},
    'Vehicle': {'keywords': ['CANADIAN TIRE', 'NAPA', 'LORDCO', 'KAL TIRE', 'OIL CHANGE', 'CARWASH', 'PARKING', 'REGISTRIES'], 'itc': True},
    'Meals': {'keywords': ['RESTAURANT', 'TIM HORTON', 'SUBWAY', 'MCDON', 'A&W', 'WENDYS', 'BOSTON PIZZA', 'DENNYS', 'SMITTYS'], 'itc': True, 'itc_pct': 0.5},
    'Supplies': {'keywords': ['OFFICE', 'STAPLES', 'WALMART', 'COSTCO', 'HOME DEPOT', 'LOWES', 'MARKS WORK', 'AMAZON'], 'itc': True},
    'Professional': {'keywords': ['ACCOUNTING', 'LEGAL', 'LAWYER', 'CPA', 'QUICKBOOKS', 'INTUIT'], 'itc': True},
    'Insurance': {'keywords': ['INSURANCE', 'WAWANESA', 'INTACT', 'AVIVA'], 'itc': False},
    'Bank Fees': {'keywords': ['SERVICE CHARGE', 'MONTHLY FEE', 'BANK FEE', 'NSF', 'OVERDRAFT'], 'itc': False},
    'Telecom': {'keywords': ['TELUS', 'ROGERS', 'BELL', 'SHAW', 'FIDO', 'KOODO'], 'itc': True},
    'Utilities': {'keywords': ['ATCO', 'ENMAX', 'EPCOR', 'DIRECT ENERGY', 'FORTIS'], 'itc': True},
    'Personal': {'keywords': ['NETFLIX', 'SPOTIFY', 'SKIP THE DISHES', 'DOORDASH', 'UBER EATS', 'LIQUOR', 'CANNABIS', 'LOTTERY'], 'itc': False, 'personal': True},
    'Shareholder Distribution': {'keywords': ['E-TRANSFER', 'ETRANSFER', 'INTERAC', 'TRANSFER TO'], 'itc': False}
}

def classify_transaction(desc, amount):
    desc_upper = desc.upper()
    for category, rules in CRA_CATEGORIES.items():
        if any(kw in desc_upper for kw in rules['keywords']):
            itc = 0.0
            if rules.get('itc', False) and amount > 0:
                pct = rules.get('itc_pct', 1.0)
                itc = amount * 0.05 / 1.05 * pct
            return {
                'cra_category': category,
                'itc_amount': round(itc, 2),
                'is_personal': rules.get('personal', False),
                'needs_review': False
            }
    return {'cra_category': 'Uncategorized', 'itc_amount': 0.0, 'is_personal': False, 'needs_review': True}

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
                debit = abs(float(parts[2].strip())) if parts[2].strip() else 0
                credit = abs(float(parts[3].strip())) if len(parts) > 3 and parts[3].strip() else 0
                data.append({'date': date, 'description': desc, 'debit': debit, 'credit': credit})
            except: continue
    return pd.DataFrame(data)

def calculate_revenue(df):
    wire_mask = df['description'].str.contains('WIRE TSF', case=False, na=False) & (df['credit'] > 0)
    mobile_mask = df['description'].str.contains('MOBILE DEP', case=False, na=False) & (df['credit'] > 0)
    branch_mask = df['description'].str.contains('BRANCH', case=False, na=False) & (df['credit'] > 0)
    
    wire_df = df[wire_mask].drop_duplicates(subset=['date', 'credit', 'description'])
    mobile_df = df[mobile_mask].drop_duplicates(subset=['date', 'credit', 'description'])
    branch_df = df[branch_mask].drop_duplicates(subset=['date', 'credit', 'description'])
    
    return {
        'wire': {'df': wire_df, 'total': wire_df['credit'].sum(), 'count': len(wire_df)},
        'mobile': {'df': mobile_df, 'total': mobile_df['credit'].sum(), 'count': len(mobile_df)},
        'branch': {'df': branch_df, 'total': branch_df['credit'].sum(), 'count': len(branch_df)}
    }

if page == "📤 Upload & Process":
    st.title(f"📤 Upload Bank Statement - FY {st.session_state.fiscal_year}")
    
    if st.session_state.classified_df is not None:
        st.success(f"✅ Statement loaded: {len(st.session_state.classified_df)} transactions")
        if st.button("🗑️ Clear & Upload New"):
            st.session_state.corporate_df = None
            st.session_state.classified_df = None
            st.rerun()
    
    uploaded = st.file_uploader("CIBC CSV Statement", type=['csv'])
    if uploaded:
        content = uploaded.getvalue().decode('utf-8', errors='replace')
        df = load_cibc_csv(content)
        
        classifications = df.apply(lambda r: classify_transaction(r['description'], r['debit']), axis=1)
        for col in ['cra_category', 'itc_amount', 'is_personal', 'needs_review']:
            df[col] = classifications.apply(lambda x: x[col])
        
        st.session_state.corporate_df = df
        st.session_state.classified_df = df
        st.success(f"✅ Processed {len(df)} transactions")
        st.rerun()

elif page == "💰 Revenue":
    st.title(f"💰 Revenue - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()
    
    rev = calculate_revenue(st.session_state.classified_df)
    total = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Wire Transfers", f"${rev['wire']['total']:,.2f}", f"{rev['wire']['count']} txns")
    with col2: st.metric("Mobile Deposits", f"${rev['mobile']['total']:,.2f}", f"{rev['mobile']['count']} txns")
    with col3: st.metric("Branch Deposits", f"${rev['branch']['total']:,.2f}", f"{rev['branch']['count']} txns")
    with col4: st.metric("TOTAL REVENUE", f"${total:,.2f}")
    
    with st.expander("View Transactions"):
        for name, data in [("Wire Transfers", rev['wire']), ("Mobile Deposits", rev['mobile']), ("Branch Deposits", rev['branch'])]:
            if len(data['df']) > 0:
                st.markdown(f"**{name}**")
                st.dataframe(data['df'][['date', 'description', 'credit']], use_container_width=True)
    
    st.markdown("---")
    st.markdown("### 🧮 CRA Calculation Breakdown")
    st.info(f"""**Revenue Calculation:**
    
Wire Transfers ({rev['wire']['count']} transactions):     ${rev['wire']['total']:>12,.2f}
Mobile Deposits ({rev['mobile']['count']} transactions):   ${rev['mobile']['total']:>12,.2f}
Branch Deposits ({rev['branch']['count']} transactions):   ${rev['branch']['total']:>12,.2f}
                                                ____________
**TOTAL GROSS REVENUE:**                        ${total:>12,.2f}

GST Collected (5%): ${total:,.2f} × 0.05 = ${total * 0.05:,.2f}""")

elif page == "📱 Phone Bills":
    st.title(f"📱 Phone Bills - FY {st.session_state.fiscal_year}")
    st.markdown("**CRA Rule:** Business-use percentage of phone bills is deductible. Enter actual monthly amounts from bills.")
    
    months = ['Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov']
    
    st.markdown("### 👨 Greg's Phone (51% owner)")
    greg_data = st.session_state.phone_bill.get('greg', {'months': {m: 0.0 for m in months}, 'business_pct': 100})
    greg_pct = st.slider("Greg's Business Use %", 0, 100, greg_data.get('business_pct', 100), key='greg_pct')
    cols = st.columns(6)
    greg_months = {}
    for i, m in enumerate(months):
        with cols[i % 6]:
            greg_months[m] = st.number_input(m, value=float(greg_data.get('months', {}).get(m, 0.0)), min_value=0.0, key=f'greg_{m}', format="%.2f")
    greg_annual = sum(greg_months.values())
    greg_ded = greg_annual * greg_pct / 100
    greg_itc = greg_ded * 0.05 / 1.05
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Annual", f"${greg_annual:,.2f}")
    with col2: st.metric("Deductible", f"${greg_ded:,.2f}")
    with col3: st.metric("ITC", f"${greg_itc:,.2f}")
    
    st.markdown("---")
    st.markdown("### 👩 Lilibeth's Phone (49% owner)")
    lili_data = st.session_state.phone_bill.get('lilibeth', {'months': {m: 0.0 for m in months}, 'business_pct': 100})
    lili_pct = st.slider("Lilibeth's Business Use %", 0, 100, lili_data.get('business_pct', 100), key='lili_pct')
    cols = st.columns(6)
    lili_months = {}
    for i, m in enumerate(months):
        with cols[i % 6]:
            lili_months[m] = st.number_input(m, value=float(lili_data.get('months', {}).get(m, 0.0)), min_value=0.0, key=f'lili_{m}', format="%.2f")
    lili_annual = sum(lili_months.values())
    lili_ded = lili_annual * lili_pct / 100
    lili_itc = lili_ded * 0.05 / 1.05
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Annual", f"${lili_annual:,.2f}")
    with col2: st.metric("Deductible", f"${lili_ded:,.2f}")
    with col3: st.metric("ITC", f"${lili_itc:,.2f}")
    
    st.markdown("---")
    total_itc = greg_itc + lili_itc
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Combined Annual", f"${greg_annual + lili_annual:,.2f}")
    with col2: st.metric("Combined Deductible", f"${greg_ded + lili_ded:,.2f}")
    with col3: st.metric("Combined ITC", f"${total_itc:,.2f}")
    
    if st.button("💾 Save Phone Bills", type="primary"):
        st.session_state.phone_bill = {
            'greg': {'months': greg_months, 'business_pct': greg_pct},
            'lilibeth': {'months': lili_months, 'business_pct': lili_pct}
        }
        st.success("✅ Phone bills saved!")
    
    st.markdown("---")
    st.markdown("### 🧮 CRA Calculation Breakdown")
    st.info(f"""**Greg's Phone ITC:**
1. Annual total: ${greg_annual:.2f}
2. Business use ({greg_pct}%): ${greg_annual:.2f} × {greg_pct}% = ${greg_ded:.2f}
3. ITC (GST recovery): ${greg_ded:.2f} × 5% ÷ 1.05 = ${greg_itc:.2f}

**Lilibeth's Phone ITC:**
1. Annual total: ${lili_annual:.2f}
2. Business use ({lili_pct}%): ${lili_annual:.2f} × {lili_pct}% = ${lili_ded:.2f}
3. ITC (GST recovery): ${lili_ded:.2f} × 5% ÷ 1.05 = ${lili_itc:.2f}

**Combined Phone ITC:** ${greg_itc:.2f} + ${lili_itc:.2f} = ${total_itc:.2f}""")

elif page == "💵 Cash Expenses":
    st.title(f"💵 Cash Expenses - FY {st.session_state.fiscal_year}")
    st.markdown("**CRA Rule:** Cash expenses under $30 don't need receipts. Keep receipts for $30+.")
    
    with st.form("add_cash"):
        col1, col2, col3 = st.columns(3)
        with col1: date = st.date_input("Date")
        with col2: amount = st.number_input("Amount ($)", min_value=0.0)
        with col3: desc = st.text_input("Description")
        if st.form_submit_button("Add Expense"):
            st.session_state.cash_expenses.append({'date': str(date), 'amount': amount, 'description': desc})
            st.success("Added!")
            st.rerun()
    
    if st.session_state.cash_expenses:
        cash_df = pd.DataFrame(st.session_state.cash_expenses)
        st.dataframe(cash_df, use_container_width=True)
        total_cash = sum(e['amount'] for e in st.session_state.cash_expenses)
        cash_itc = total_cash * 0.05 / 1.05
        col1, col2 = st.columns(2)
        with col1: st.metric("Total Cash Expenses", f"${total_cash:,.2f}")
        with col2: st.metric("Cash ITC", f"${cash_itc:,.2f}")
        
        st.markdown("---")
        st.markdown("### 🧮 CRA Calculation Breakdown")
        st.info(f"""**Cash Expense ITC:**
Total cash expenses: ${total_cash:.2f}
ITC (GST recovery): ${total_cash:.2f} × 5% ÷ 1.05 = ${cash_itc:.2f}""")

elif page == "💰 GST Filing":
    st.title(f"💰 GST/HST Return - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()
    
    df = st.session_state.classified_df
    rev = calculate_revenue(df)
    total_revenue = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
    gst_collected = total_revenue * 0.05
    
    bank_itc = df[df['itc_amount'] > 0]['itc_amount'].sum()
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    
    greg_p = st.session_state.phone_bill.get('greg', {})
    lili_p = st.session_state.phone_bill.get('lilibeth', {})
    greg_annual = sum(greg_p.get('months', {}).values())
    lili_annual = sum(lili_p.get('months', {}).values())
    greg_itc = greg_annual * greg_p.get('business_pct', 100) / 100 * 0.05 / 1.05
    lili_itc = lili_annual * lili_p.get('business_pct', 100) / 100 * 0.05 / 1.05
    phone_itc = greg_itc + lili_itc
    
    total_itc = bank_itc + cash_itc + phone_itc
    net_gst = gst_collected - total_itc
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### GST Collected")
        st.metric("Total Revenue", f"${total_revenue:,.2f}")
        st.metric("GST Collected (5%)", f"${gst_collected:,.2f}")
    with col2:
        st.markdown("### Input Tax Credits")
        st.metric("Bank ITCs", f"${bank_itc:,.2f}")
        st.metric("Cash ITCs", f"${cash_itc:,.2f}")
        st.metric("Phone ITCs", f"${phone_itc:,.2f}")
        st.metric("**TOTAL ITCs**", f"${total_itc:,.2f}")
    
    st.markdown("---")
    if net_gst > 0:
        st.error(f"## 📤 NET GST OWING: ${net_gst:,.2f}")
    else:
        st.success(f"## 📥 NET GST REFUND: ${abs(net_gst):,.2f}")
    
    st.markdown("---")
    st.markdown("### 🧮 CRA Calculation Breakdown")
    st.info(f"""**GST Collected:**
Total Revenue: ${total_revenue:,.2f}
GST (5%): ${total_revenue:,.2f} × 0.05 = ${gst_collected:,.2f}

**Input Tax Credits (ITCs):**
- Bank Statement ITCs: ${bank_itc:,.2f}
- Cash Expense ITCs: ${cash_itc:,.2f}
- Greg Phone ITC: ${greg_itc:,.2f}
- Lilibeth Phone ITC: ${lili_itc:,.2f}
- **Total ITCs:** ${total_itc:,.2f}

**Net GST Calculation:**
${gst_collected:,.2f} - ${total_itc:,.2f} = ${net_gst:,.2f}

{"Amount OWING to CRA" if net_gst > 0 else "REFUND from CRA"}""")

elif page == "👥 Shareholders":
    st.title(f"👥 Shareholder Accounts - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()
    
    df = st.session_state.classified_df
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    personal = df[df['is_personal'] == True]['debit'].sum()
    total_loan = distributions + personal
    
    st.info("**CRA Rule:** Shareholder loans must be repaid within 1 year of fiscal year-end or become taxable income.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 👨 Greg (51%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.51:,.2f}")
    with col2:
        st.markdown("### 👩 Lilibeth (49%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.49:,.2f}")
    
    st.markdown("---")
    st.markdown("### 🧮 CRA Calculation Breakdown")
    st.info(f"""**Shareholder Loan Calculation:**
    
Shareholder Distributions (e-transfers, etc.): ${distributions:,.2f}
Personal Expenses (flagged as personal):       ${personal:,.2f}
                                               ____________
**Total Shareholder Loan:**                    ${total_loan:,.2f}

**Split by Ownership:**
- Greg (51%): ${total_loan:,.2f} × 51% = ${total_loan * 0.51:,.2f}
- Lilibeth (49%): ${total_loan:,.2f} × 49% = ${total_loan * 0.49:,.2f}

**Repayment Deadline:** Nov 30, {fy_end} + 1 year = Nov 30, {int(fy_end)+1}""")

elif page == "📋 Summary":
    st.title(f"📋 Final Summary - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()
    
    df = st.session_state.classified_df
    rev = calculate_revenue(df)
    total_revenue = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
    gst_collected = total_revenue * 0.05
    
    bank_itc = df[df['itc_amount'] > 0]['itc_amount'].sum()
    cash_itc = sum(e['amount'] * 0.05 / 1.05 for e in st.session_state.cash_expenses)
    greg_p = st.session_state.phone_bill.get('greg', {})
    lili_p = st.session_state.phone_bill.get('lilibeth', {})
    phone_itc = (sum(greg_p.get('months', {}).values()) * greg_p.get('business_pct', 100) / 100 + 
                 sum(lili_p.get('months', {}).values()) * lili_p.get('business_pct', 100) / 100) * 0.05 / 1.05
    total_itc = bank_itc + cash_itc + phone_itc
    net_gst = gst_collected - total_itc
    
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    personal = df[df['is_personal'] == True]['debit'].sum()
    total_loan = distributions + personal
    
    st.markdown("### Revenue")
    st.metric("Total Revenue", f"${total_revenue:,.2f}")
    
    st.markdown("### GST")
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Collected", f"${gst_collected:,.2f}")
    with col2: st.metric("ITCs", f"${total_itc:,.2f}")
    with col3: st.metric("Net", f"${net_gst:,.2f}")
    
    st.markdown("### Shareholder Loans")
    col1, col2 = st.columns(2)
    with col1: st.metric("Greg (51%)", f"${total_loan * 0.51:,.2f}")
    with col2: st.metric("Lilibeth (49%)", f"${total_loan * 0.49:,.2f}")
    
    st.markdown("---")
    summary_text = f"""CAPE BRETONER'S OILFIELD SERVICES LTD - FY {st.session_state.fiscal_year}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

REVENUE: ${total_revenue:,.2f}
GST COLLECTED: ${gst_collected:,.2f}
TOTAL ITCs: ${total_itc:,.2f}
NET GST {"OWING" if net_gst > 0 else "REFUND"}: ${abs(net_gst):,.2f}

SHAREHOLDER LOANS:
- Greg (51%): ${total_loan * 0.51:,.2f}
- Lilibeth (49%): ${total_loan * 0.49:,.2f}
"""
    st.download_button("📥 Download Summary", summary_text, f"summary_FY{st.session_state.fiscal_year}.txt")
    
    st.download_button("📥 Download All Transactions", df.to_csv(index=False), f"transactions_FY{st.session_state.fiscal_year}.csv")
