"""
CRA-Compliant Corporate Bookkeeping Dashboard
Cape Bretoner's Oilfield Services Ltd.
Streamlit Cloud deployment - session state persistence
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import json

st.set_page_config(page_title="RigBooks - Cape Bretoner's", layout="wide")

# ─── Session State Initialization ───────────────────────────────────────────
MONTHS = ['Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov']

defaults = {
    'fiscal_year': "2024-2025",
    'corporate_df': None,
    'classified_df': None,
    'cash_expenses': [],
    'phone_bill': {
        'greg': {'months': {m: 0.0 for m in MONTHS}, 'business_pct': 100},
        'lilibeth': {'months': {m: 0.0 for m in MONTHS}, 'business_pct': 100}
    },
    'phone_saved': False,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

fy_start, fy_end = st.session_state.fiscal_year.split('-')

# ─── CRA Categories & Classification ────────────────────────────────────────
CRA_CATEGORIES = {
    'Fuel & Petroleum': {
        'keywords': ['SHELL', 'ESSO', 'PETRO', 'HUSKY', 'GAS BAR', 'FUEL', 'PIONEER', 'MOBIL', 'CHEVRON', 'COOP PETROLEUM', 'FLYING J', 'CARDLOCK'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Vehicle Repairs & Maintenance': {
        'keywords': ['CANADIAN TIRE', 'NAPA', 'LORDCO', 'KAL TIRE', 'OIL CHANGE', 'CARWASH', 'PARKING', 'REGISTRIES', 'MIDAS', 'JIFFY'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Meals & Entertainment (50%)': {
        'keywords': ['RESTAURANT', 'TIM HORTON', 'SUBWAY', 'MCDON', 'A&W', 'WENDYS', 'BOSTON PIZZA', 'DENNYS', 'SMITTYS', 'PIZZA', 'STARBUCKS', 'TIMS'],
        'itc': True, 'itc_pct': 0.5, 'personal': False
    },
    'Equipment & Supplies': {
        'keywords': ['OFFICE', 'STAPLES', 'HOME DEPOT', 'LOWES', 'MARKS WORK', 'AMAZON', 'PRINCESS AUTO', 'ULINE'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Professional Fees': {
        'keywords': ['ACCOUNTING', 'LEGAL', 'LAWYER', 'CPA', 'QUICKBOOKS', 'INTUIT', 'BOOKKEEP'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Insurance - Business': {
        'keywords': ['INSURANCE', 'WAWANESA', 'INTACT', 'AVIVA'],
        'itc': False, 'itc_pct': 0, 'personal': False
    },
    'Bank Charges & Interest': {
        'keywords': ['SERVICE CHARGE', 'MONTHLY FEE', 'BANK FEE', 'NSF', 'OVERDRAFT', 'INTEREST CHARGE'],
        'itc': False, 'itc_pct': 0, 'personal': False
    },
    'Telecom': {
        'keywords': ['TELUS', 'ROGERS', 'BELL', 'SHAW', 'FIDO', 'KOODO'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Utilities': {
        'keywords': ['ATCO', 'ENMAX', 'EPCOR', 'DIRECT ENERGY', 'FORTIS'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Rent': {
        'keywords': ['RENT', 'LEASE PAYMENT', 'PROPERTY MGMT'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Travel': {
        'keywords': ['HOTEL', 'MOTEL', 'INN', 'AIRBNB', 'FLIGHT', 'WESTJET', 'AIR CANADA'],
        'itc': True, 'itc_pct': 1.0, 'personal': False
    },
    'Shareholder Loan - Personal': {
        'keywords': ['NETFLIX', 'SPOTIFY', 'SKIP THE DISHES', 'DOORDASH', 'UBER EATS', 'LIQUOR', 'CANNABIS', 'LOTTERY',
                      'GROCERY', 'IGA', 'SUPERSTORE', 'SOBEYS', 'WALMART GROCERY', 'DAYCARE', 'IKEA'],
        'itc': False, 'itc_pct': 0, 'personal': True
    },
    'Shareholder Distribution': {
        'keywords': ['E-TRANSFER', 'ETRANSFER', 'INTERAC', 'TRANSFER TO', 'ATM WITHDRAWAL', 'INTERNET TRANSFER'],
        'itc': False, 'itc_pct': 0, 'personal': False
    },
    'Revenue - Oilfield Services': {
        'keywords': ['WIRE TSF', 'MOBILE DEP', 'BRANCH DEPOSIT', 'COUNTER DEPOSIT', 'DEPOSIT IN BRANCH'],
        'itc': False, 'itc_pct': 0, 'personal': False
    },
}

ALL_CATEGORY_NAMES = sorted(CRA_CATEGORIES.keys()) + ['Uncategorized']


def classify_transaction(desc, amount):
    desc_upper = desc.upper()
    for category, rules in CRA_CATEGORIES.items():
        if any(kw in desc_upper for kw in rules['keywords']):
            itc = 0.0
            if rules.get('itc') and amount > 0:
                itc = amount * 0.05 / 1.05 * rules.get('itc_pct', 1.0)
            return {
                'cra_category': category,
                'itc_amount': round(itc, 2),
                'is_personal': rules.get('personal', False),
                'needs_review': amount > 500
            }
    return {'cra_category': 'Uncategorized', 'itc_amount': 0.0, 'is_personal': False, 'needs_review': True}


def load_cibc_csv(content):
    lines = content.strip().split('\n')
    data = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                date = pd.to_datetime(parts[0].strip()).strftime('%Y-%m-%d')
                desc = parts[1].strip()
                debit = abs(float(parts[2].strip())) if parts[2].strip() else 0
                credit = abs(float(parts[3].strip())) if len(parts) > 3 and parts[3].strip() else 0
                data.append({'date': date, 'description': desc, 'debit': debit, 'credit': credit})
            except Exception:
                continue
    return pd.DataFrame(data)


def calculate_revenue(df):
    wire_mask = df['description'].str.contains('WIRE TSF', case=False, na=False) & (df['credit'] > 0)
    mobile_mask = df['description'].str.contains('MOBILE DEP', case=False, na=False) & (df['credit'] > 0)
    branch_mask = df['description'].str.contains('BRANCH|COUNTER DEPOSIT|DEPOSIT IN BRANCH', case=False, na=False) & (df['credit'] > 0)

    wire_df = df[wire_mask].drop_duplicates(subset=['date', 'credit', 'description'])
    mobile_df = df[mobile_mask].drop_duplicates(subset=['date', 'credit', 'description'])
    branch_df = df[branch_mask].drop_duplicates(subset=['date', 'credit', 'description'])

    return {
        'wire': {'df': wire_df, 'total': wire_df['credit'].sum(), 'count': len(wire_df)},
        'mobile': {'df': mobile_df, 'total': mobile_df['credit'].sum(), 'count': len(mobile_df)},
        'branch': {'df': branch_df, 'total': branch_df['credit'].sum(), 'count': len(branch_df)},
    }


def get_phone_itc():
    greg_p = st.session_state.phone_bill.get('greg', {})
    lili_p = st.session_state.phone_bill.get('lilibeth', {})
    greg_annual = sum(greg_p.get('months', {}).values())
    lili_annual = sum(lili_p.get('months', {}).values())
    greg_ded = greg_annual * greg_p.get('business_pct', 100) / 100
    lili_ded = lili_annual * lili_p.get('business_pct', 100) / 100
    greg_itc = greg_ded * 0.05 / 1.05
    lili_itc = lili_ded * 0.05 / 1.05
    return {
        'greg_annual': greg_annual, 'lili_annual': lili_annual,
        'greg_ded': greg_ded, 'lili_ded': lili_ded,
        'greg_itc': greg_itc, 'lili_itc': lili_itc,
        'total_itc': greg_itc + lili_itc,
    }


def recalc_itc_for_row(row):
    cat = row['cra_category']
    if cat in CRA_CATEGORIES:
        rules = CRA_CATEGORIES[cat]
        if rules.get('itc') and row['debit'] > 0:
            return round(row['debit'] * 0.05 / 1.05 * rules.get('itc_pct', 1.0), 2)
    return 0.0


# ─── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.title("RigBooks")
st.sidebar.markdown(f"**FY {st.session_state.fiscal_year}**")
st.sidebar.markdown(f"Dec 1, {fy_start} - Nov 30, {fy_end}")
st.sidebar.markdown("---")
st.sidebar.markdown("**Ownership**")
st.sidebar.markdown("Greg: 51% | Lilibeth: 49%")

# Status indicators
if st.session_state.classified_df is not None:
    n = len(st.session_state.classified_df)
    st.sidebar.success(f"{n} transactions loaded")
if st.session_state.cash_expenses:
    st.sidebar.info(f"{len(st.session_state.cash_expenses)} cash expenses")
if st.session_state.phone_saved:
    st.sidebar.info("Phone bills saved")

st.sidebar.markdown("---")

page = st.sidebar.radio("Navigation", [
    "Upload & Process",
    "Revenue",
    "Categorize Transactions",
    "Phone Bills",
    "Cash Expenses",
    "GST Filing",
    "Shareholders",
    "Summary",
])


# ═══════════════════════════════════════════════════════════════════════════════
#  UPLOAD & PROCESS
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Upload & Process":
    st.title(f"Upload Bank Statement - FY {st.session_state.fiscal_year}")

    if st.session_state.classified_df is not None:
        st.success(f"Statement loaded: {len(st.session_state.classified_df)} transactions")
        if st.button("Clear & Upload New"):
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
        st.success(f"Processed {len(df)} transactions - data persists in this session")
        st.rerun()

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    if st.session_state.classified_df is not None:
        df = st.session_state.classified_df
        rev = calculate_revenue(df)
        total_rev = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
        total_debits = df['debit'].sum()
        total_itc = df[df['itc_amount'] > 0]['itc_amount'].sum()
        personal = df[df['is_personal']]['debit'].sum()
        st.info(f"""**Statement Overview:**
- Transactions: {len(df)}
- Total Revenue (credits): ${total_rev:,.2f}
- Total Expenses (debits): ${total_debits:,.2f}
- Total ITCs from bank: ${total_itc:,.2f}
- Personal expenses flagged: ${personal:,.2f}
- Needs review: {len(df[df['needs_review']])} transactions""")
    else:
        st.info("Upload a CSV to see the breakdown.")


# ═══════════════════════════════════════════════════════════════════════════════
#  REVENUE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Revenue":
    st.title(f"Revenue - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()

    rev = calculate_revenue(st.session_state.classified_df)
    total = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Wire Transfers", f"${rev['wire']['total']:,.2f}", f"{rev['wire']['count']} txns")
    with col2:
        st.metric("Mobile Deposits", f"${rev['mobile']['total']:,.2f}", f"{rev['mobile']['count']} txns")
    with col3:
        st.metric("Branch Deposits", f"${rev['branch']['total']:,.2f}", f"{rev['branch']['count']} txns")
    with col4:
        st.metric("TOTAL REVENUE", f"${total:,.2f}")

    # Show each type separately
    for label, key in [("Wire Transfers", 'wire'), ("Mobile Deposits", 'mobile'), ("Branch Deposits", 'branch')]:
        data = rev[key]
        if len(data['df']) > 0:
            with st.expander(f"{label} ({data['count']} transactions - ${data['total']:,.2f})"):
                st.dataframe(data['df'][['date', 'description', 'credit']].sort_values('date'), use_container_width=True)

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    gst = total * 0.05
    st.info(f"""**Revenue Calculation:**

Wire Transfers ({rev['wire']['count']} txns):    ${rev['wire']['total']:>12,.2f}
Mobile Deposits ({rev['mobile']['count']} txns):  ${rev['mobile']['total']:>12,.2f}
Branch Deposits ({rev['branch']['count']} txns):  ${rev['branch']['total']:>12,.2f}
{'':─<45}
**TOTAL GROSS REVENUE:**{' '*20}${total:>12,.2f}

**GST Collected (5%):** ${total:,.2f} x 0.05 = ${gst:,.2f}""")


# ═══════════════════════════════════════════════════════════════════════════════
#  CATEGORIZE TRANSACTIONS (Business/Personal)
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Categorize Transactions":
    st.title(f"Categorize Transactions - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()

    df = st.session_state.classified_df

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        cats = ['All'] + sorted(df['cra_category'].unique().tolist())
        cat_filter = st.selectbox("Filter by Category", cats)
    with col2:
        status_filter = st.selectbox("Filter by Status", ['All', 'Needs Review', 'Personal', 'Business'])

    mask = pd.Series([True] * len(df), index=df.index)
    if cat_filter != 'All':
        mask &= df['cra_category'] == cat_filter
    if status_filter == 'Needs Review':
        mask &= df['needs_review'] == True
    elif status_filter == 'Personal':
        mask &= df['is_personal'] == True
    elif status_filter == 'Business':
        mask &= df['is_personal'] == False

    filtered = df[mask]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Shown", len(filtered))
    with col2:
        st.metric("Total Debits", f"${filtered['debit'].sum():,.2f}")
    with col3:
        st.metric("Total ITCs", f"${filtered['itc_amount'].sum():,.2f}")
    with col4:
        st.metric("Needs Review", len(filtered[filtered['needs_review']]))

    st.dataframe(
        filtered[['date', 'description', 'debit', 'credit', 'cra_category', 'itc_amount', 'is_personal', 'needs_review']],
        use_container_width=True, height=400
    )

    # Re-categorize section
    st.markdown("---")
    st.markdown("### Re-categorize a Transaction")
    st.markdown("Select a transaction by index and assign a new category. Changes save to session.")

    if len(filtered) > 0:
        idx_options = filtered.index.tolist()
        selected_idx = st.selectbox(
            "Transaction index",
            idx_options,
            format_func=lambda i: f"#{i} - {df.loc[i, 'date']} - {df.loc[i, 'description'][:50]} - ${df.loc[i, 'debit']:.2f}"
        )

        col1, col2 = st.columns(2)
        with col1:
            current_cat = df.loc[selected_idx, 'cra_category']
            new_cat = st.selectbox("New Category", ALL_CATEGORY_NAMES, index=ALL_CATEGORY_NAMES.index(current_cat) if current_cat in ALL_CATEGORY_NAMES else 0)
        with col2:
            current_personal = bool(df.loc[selected_idx, 'is_personal'])
            new_personal = st.checkbox("Mark as Personal", value=current_personal)

        if st.button("Save Category Change", type="primary"):
            st.session_state.classified_df.loc[selected_idx, 'cra_category'] = new_cat
            st.session_state.classified_df.loc[selected_idx, 'is_personal'] = new_personal
            # Recalculate ITC
            row = st.session_state.classified_df.loc[selected_idx]
            if new_personal:
                st.session_state.classified_df.loc[selected_idx, 'itc_amount'] = 0.0
            else:
                st.session_state.classified_df.loc[selected_idx, 'itc_amount'] = recalc_itc_for_row(row)
            st.session_state.classified_df.loc[selected_idx, 'needs_review'] = False
            st.success(f"Updated transaction #{selected_idx} to '{new_cat}' (Personal: {new_personal})")
            st.rerun()

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    cat_summary = df.groupby('cra_category').agg(
        count=('debit', 'count'),
        total_debit=('debit', 'sum'),
        total_itc=('itc_amount', 'sum')
    ).sort_values('total_debit', ascending=False)

    lines = ["**Expense Categories Summary:**\n"]
    lines.append(f"{'Category':<35} {'Count':>5} {'Debits':>12} {'ITC':>10}")
    lines.append("-" * 65)
    for cat, row in cat_summary.iterrows():
        lines.append(f"{cat:<35} {int(row['count']):>5} ${row['total_debit']:>10,.2f} ${row['total_itc']:>8,.2f}")
    lines.append("-" * 65)
    lines.append(f"{'TOTAL':<35} {int(cat_summary['count'].sum()):>5} ${cat_summary['total_debit'].sum():>10,.2f} ${cat_summary['total_itc'].sum():>8,.2f}")
    personal_total = df[df['is_personal']]['debit'].sum()
    lines.append(f"\n**Personal expenses (not deductible):** ${personal_total:,.2f}")
    st.text("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
#  PHONE BILLS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Phone Bills":
    st.title(f"Phone Bills - FY {st.session_state.fiscal_year}")
    st.markdown("**CRA Rule:** Business-use percentage of phone bills is deductible. Enter actual monthly amounts from bills.")

    # Greg
    st.markdown("### Greg's Phone (51% owner)")
    greg_data = st.session_state.phone_bill.get('greg', {'months': {m: 0.0 for m in MONTHS}, 'business_pct': 100})
    greg_pct = st.slider("Greg's Business Use %", 0, 100, greg_data.get('business_pct', 100), key='greg_pct')

    cols = st.columns(6)
    greg_months = {}
    for i, m in enumerate(MONTHS):
        with cols[i % 6]:
            greg_months[m] = st.number_input(
                f"{m} ({fy_start if m == 'Dec' else fy_end})",
                value=float(greg_data.get('months', {}).get(m, 0.0)),
                min_value=0.0, key=f'greg_{m}', format="%.2f"
            )

    greg_annual = sum(greg_months.values())
    greg_ded = greg_annual * greg_pct / 100
    greg_itc = greg_ded * 0.05 / 1.05

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Annual Total", f"${greg_annual:,.2f}")
    with col2:
        st.metric("Deductible", f"${greg_ded:,.2f}")
    with col3:
        st.metric("ITC", f"${greg_itc:,.2f}")

    st.markdown("---")

    # Lilibeth
    st.markdown("### Lilibeth's Phone (49% owner)")
    lili_data = st.session_state.phone_bill.get('lilibeth', {'months': {m: 0.0 for m in MONTHS}, 'business_pct': 100})
    lili_pct = st.slider("Lilibeth's Business Use %", 0, 100, lili_data.get('business_pct', 100), key='lili_pct')

    cols = st.columns(6)
    lili_months = {}
    for i, m in enumerate(MONTHS):
        with cols[i % 6]:
            lili_months[m] = st.number_input(
                f"{m} ({fy_start if m == 'Dec' else fy_end})",
                value=float(lili_data.get('months', {}).get(m, 0.0)),
                min_value=0.0, key=f'lili_{m}', format="%.2f"
            )

    lili_annual = sum(lili_months.values())
    lili_ded = lili_annual * lili_pct / 100
    lili_itc = lili_ded * 0.05 / 1.05

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Annual Total", f"${lili_annual:,.2f}")
    with col2:
        st.metric("Deductible", f"${lili_ded:,.2f}")
    with col3:
        st.metric("ITC", f"${lili_itc:,.2f}")

    st.markdown("---")

    # Combined
    total_phone_itc = greg_itc + lili_itc
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Combined Annual", f"${greg_annual + lili_annual:,.2f}")
    with col2:
        st.metric("Combined Deductible", f"${greg_ded + lili_ded:,.2f}")
    with col3:
        st.metric("Combined ITC", f"${total_phone_itc:,.2f}")

    if st.button("Save Phone Bills", type="primary"):
        st.session_state.phone_bill = {
            'greg': {'months': greg_months, 'business_pct': greg_pct},
            'lilibeth': {'months': lili_months, 'business_pct': lili_pct}
        }
        st.session_state.phone_saved = True
        st.success("Phone bills saved to session!")

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    st.info(f"""**Greg's Phone ITC:**
1. Annual total: ${greg_annual:.2f}
2. Business use ({greg_pct}%): ${greg_annual:.2f} x {greg_pct}% = ${greg_ded:.2f}
3. ITC (GST recovery): ${greg_ded:.2f} x 5% / 1.05 = ${greg_itc:.2f}

**Lilibeth's Phone ITC:**
1. Annual total: ${lili_annual:.2f}
2. Business use ({lili_pct}%): ${lili_annual:.2f} x {lili_pct}% = ${lili_ded:.2f}
3. ITC (GST recovery): ${lili_ded:.2f} x 5% / 1.05 = ${lili_itc:.2f}

**Combined Phone ITC:** ${greg_itc:.2f} + ${lili_itc:.2f} = ${total_phone_itc:.2f}""")


# ═══════════════════════════════════════════════════════════════════════════════
#  CASH EXPENSES
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Cash Expenses":
    st.title(f"Cash Expenses - FY {st.session_state.fiscal_year}")
    st.markdown("**CRA Rule:** Cash expenses under $30 don't need receipts. Keep receipts for $30+.")

    with st.form("add_cash"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            date = st.date_input("Date")
        with col2:
            amount = st.number_input("Amount ($)", min_value=0.0, step=0.01)
        with col3:
            desc = st.text_input("Description")
        with col4:
            cash_cat = st.selectbox("Category", [
                'Fuel & Petroleum', 'Vehicle Repairs & Maintenance', 'Equipment & Supplies',
                'Meals & Entertainment (50%)', 'Professional Fees', 'Travel', 'Other'
            ])
        if st.form_submit_button("Add Expense"):
            if amount > 0 and desc:
                itc_pct = 0.5 if '50%' in cash_cat else 1.0
                st.session_state.cash_expenses.append({
                    'date': str(date), 'amount': amount, 'description': desc,
                    'category': cash_cat, 'itc_pct': itc_pct
                })
                st.success(f"Added: {desc} - ${amount:.2f}")
                st.rerun()

    if st.session_state.cash_expenses:
        cash_df = pd.DataFrame(st.session_state.cash_expenses)
        st.dataframe(cash_df, use_container_width=True)

        # Delete button
        if len(st.session_state.cash_expenses) > 0:
            del_idx = st.number_input("Delete expense #", min_value=0, max_value=len(st.session_state.cash_expenses) - 1, step=1)
            if st.button("Delete Selected"):
                st.session_state.cash_expenses.pop(del_idx)
                st.rerun()

        total_cash = sum(e['amount'] for e in st.session_state.cash_expenses)
        cash_itc = sum(e['amount'] * 0.05 / 1.05 * e.get('itc_pct', 1.0) for e in st.session_state.cash_expenses)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Cash Expenses", f"${total_cash:,.2f}")
        with col2:
            st.metric("Cash ITC", f"${cash_itc:,.2f}")

        # CRA Breakdown
        st.markdown("---")
        st.markdown("### CRA Calculation Breakdown")
        lines = ["**Cash Expense ITC Calculation:**\n"]
        for e in st.session_state.cash_expenses:
            pct = e.get('itc_pct', 1.0)
            itc = e['amount'] * 0.05 / 1.05 * pct
            pct_label = f" x {pct:.0%}" if pct != 1.0 else ""
            lines.append(f"- {e['description']}: ${e['amount']:.2f} x 5/105{pct_label} = ${itc:.2f}")
        lines.append(f"\n**Total Cash ITCs:** ${cash_itc:.2f}")
        st.info("\n".join(lines))
    else:
        st.info("No cash expenses yet. Add some above.")

    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    st.info("Cash expenses are added to your total ITCs on the GST Filing tab.\nFormula: Amount x 5% / 1.05 = ITC (meals at 50%)")


# ═══════════════════════════════════════════════════════════════════════════════
#  GST FILING
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "GST Filing":
    st.title(f"GST/HST Return - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()

    df = st.session_state.classified_df
    rev = calculate_revenue(df)
    total_revenue = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
    gst_collected = total_revenue * 0.05

    # Bank ITCs (excluding personal)
    bank_itc = df[(df['itc_amount'] > 0) & (~df['is_personal'])]['itc_amount'].sum()

    # Cash ITCs
    cash_itc = sum(e['amount'] * 0.05 / 1.05 * e.get('itc_pct', 1.0) for e in st.session_state.cash_expenses)

    # Phone ITCs
    phone = get_phone_itc()
    phone_itc = phone['total_itc']

    total_itc = bank_itc + cash_itc + phone_itc
    net_gst = gst_collected - total_itc

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### GST Collected")
        st.metric("Total Revenue", f"${total_revenue:,.2f}")
        st.metric("GST Collected (5%)", f"${gst_collected:,.2f}")
    with col2:
        st.markdown("### Input Tax Credits")
        st.metric("Bank Statement ITCs", f"${bank_itc:,.2f}")
        st.metric("Cash Expense ITCs", f"${cash_itc:,.2f}")
        st.metric("Phone Bill ITCs", f"${phone_itc:,.2f}")
        st.metric("**TOTAL ITCs**", f"${total_itc:,.2f}")

    st.markdown("---")
    if net_gst > 0:
        st.error(f"## NET GST OWING: ${net_gst:,.2f}")
    else:
        st.success(f"## NET GST REFUND: ${abs(net_gst):,.2f}")

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    st.info(f"""**Line 101 - GST Collected:**
Total Revenue: ${total_revenue:,.2f}
GST (5%): ${total_revenue:,.2f} x 0.05 = ${gst_collected:,.2f}

**Line 106/108 - Input Tax Credits (ITCs):**
- Bank Statement ITCs: ${bank_itc:,.2f}
- Cash Expense ITCs: ${cash_itc:,.2f}
- Greg Phone ITC: ${phone['greg_itc']:,.2f}
- Lilibeth Phone ITC: ${phone['lili_itc']:,.2f}
- **Total ITCs:** ${total_itc:,.2f}

**Line 109 - Net GST:**
${gst_collected:,.2f} - ${total_itc:,.2f} = ${net_gst:,.2f}

**Result:** {"Amount OWING to CRA - payment due by June 15" if net_gst > 0 else "REFUND from CRA - file to receive"}""")

    # ITC by category
    st.markdown("### ITC by Category")
    itc_by_cat = df[df['itc_amount'] > 0].groupby('cra_category')['itc_amount'].sum().sort_values(ascending=False)
    for cat, itc_val in itc_by_cat.items():
        st.markdown(f"- **{cat}:** ${itc_val:,.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SHAREHOLDERS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Shareholders":
    st.title(f"Shareholder Accounts - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()

    df = st.session_state.classified_df
    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    personal = df[df['is_personal'] == True]['debit'].sum()
    total_loan = distributions + personal

    st.info("**CRA Rule (ITA 15(2)):** Shareholder loans must be repaid within 1 year of fiscal year-end or become taxable income.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Greg (51%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.51:,.2f}")
        st.markdown(f"- Distributions: ${distributions * 0.51:,.2f}")
        st.markdown(f"- Personal expenses: ${personal * 0.51:,.2f}")
    with col2:
        st.markdown("### Lilibeth (49%)")
        st.metric("Shareholder Loan", f"${total_loan * 0.49:,.2f}")
        st.markdown(f"- Distributions: ${distributions * 0.49:,.2f}")
        st.markdown(f"- Personal expenses: ${personal * 0.49:,.2f}")

    # Show personal transactions
    if personal > 0:
        with st.expander("View Personal Transactions"):
            personal_df = df[df['is_personal'] == True][['date', 'description', 'debit', 'cra_category']]
            st.dataframe(personal_df.sort_values('date'), use_container_width=True)

    # Show distributions
    if distributions > 0:
        with st.expander("View Shareholder Distributions"):
            dist_df = df[df['cra_category'] == 'Shareholder Distribution'][['date', 'description', 'debit']]
            st.dataframe(dist_df.sort_values('date'), use_container_width=True)

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    st.info(f"""**Shareholder Loan Calculation (ITA 15(2)):**

Shareholder Distributions (e-transfers, ATM):  ${distributions:>12,.2f}
Personal Expenses (flagged as personal):       ${personal:>12,.2f}
{'':─<50}
**Total Shareholder Loan:**{' '*23}${total_loan:>12,.2f}

**Split by Ownership:**
- Greg (51%): ${total_loan:,.2f} x 51% = ${total_loan * 0.51:,.2f}
- Lilibeth (49%): ${total_loan:,.2f} x 49% = ${total_loan * 0.49:,.2f}

**Repayment Deadline:** Nov 30, {int(fy_end) + 1}
If not repaid, amount becomes taxable income under ITA 15(2).""")


# ═══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Summary":
    st.title(f"Summary - FY {st.session_state.fiscal_year}")
    if st.session_state.classified_df is None:
        st.warning("Upload a statement first")
        st.stop()

    df = st.session_state.classified_df
    rev = calculate_revenue(df)
    total_revenue = rev['wire']['total'] + rev['mobile']['total'] + rev['branch']['total']
    gst_collected = total_revenue * 0.05

    bank_itc = df[(df['itc_amount'] > 0) & (~df['is_personal'])]['itc_amount'].sum()
    cash_itc = sum(e['amount'] * 0.05 / 1.05 * e.get('itc_pct', 1.0) for e in st.session_state.cash_expenses)
    phone = get_phone_itc()
    phone_itc = phone['total_itc']
    total_itc = bank_itc + cash_itc + phone_itc
    net_gst = gst_collected - total_itc

    distributions = df[df['cra_category'] == 'Shareholder Distribution']['debit'].sum()
    personal = df[df['is_personal'] == True]['debit'].sum()
    total_loan = distributions + personal

    # Revenue
    st.markdown("### Revenue")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Wire Transfers", f"${rev['wire']['total']:,.2f}")
    with col2:
        st.metric("Mobile Deposits", f"${rev['mobile']['total']:,.2f}")
    with col3:
        st.metric("Branch Deposits", f"${rev['branch']['total']:,.2f}")
    with col4:
        st.metric("Total Revenue", f"${total_revenue:,.2f}")

    # GST
    st.markdown("### GST")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Collected", f"${gst_collected:,.2f}")
    with col2:
        st.metric("ITCs", f"${total_itc:,.2f}")
    with col3:
        st.metric("Net", f"${net_gst:,.2f}")

    # Shareholder Loans
    st.markdown("### Shareholder Loans")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Greg (51%)", f"${total_loan * 0.51:,.2f}")
    with col2:
        st.metric("Lilibeth (49%)", f"${total_loan * 0.49:,.2f}")

    # Downloads
    st.markdown("---")
    summary_text = f"""CAPE BRETONER'S OILFIELD SERVICES LTD - FY {st.session_state.fiscal_year}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

REVENUE:
  Wire Transfers: ${rev['wire']['total']:,.2f} ({rev['wire']['count']} txns)
  Mobile Deposits: ${rev['mobile']['total']:,.2f} ({rev['mobile']['count']} txns)
  Branch Deposits: ${rev['branch']['total']:,.2f} ({rev['branch']['count']} txns)
  TOTAL: ${total_revenue:,.2f}

GST:
  Collected: ${gst_collected:,.2f}
  Bank ITCs: ${bank_itc:,.2f}
  Cash ITCs: ${cash_itc:,.2f}
  Phone ITCs: ${phone_itc:,.2f}
  Total ITCs: ${total_itc:,.2f}
  NET GST {"OWING" if net_gst > 0 else "REFUND"}: ${abs(net_gst):,.2f}

SHAREHOLDER LOANS:
  Greg (51%): ${total_loan * 0.51:,.2f}
  Lilibeth (49%): ${total_loan * 0.49:,.2f}
  Total: ${total_loan:,.2f}

PHONE BILLS:
  Greg: ${phone['greg_annual']:,.2f} annual, ${phone['greg_ded']:,.2f} deductible, ${phone['greg_itc']:,.2f} ITC
  Lilibeth: ${phone['lili_annual']:,.2f} annual, ${phone['lili_ded']:,.2f} deductible, ${phone['lili_itc']:,.2f} ITC

CASH EXPENSES: {len(st.session_state.cash_expenses)} entries, ${sum(e['amount'] for e in st.session_state.cash_expenses):,.2f} total
"""
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("Download Summary", summary_text, f"summary_FY{st.session_state.fiscal_year}.txt")
    with col2:
        st.download_button("Download Transactions CSV", df.to_csv(index=False), f"transactions_FY{st.session_state.fiscal_year}.csv")

    # CRA Breakdown
    st.markdown("---")
    st.markdown("### CRA Calculation Breakdown")
    st.info(f"""**Complete Tax Summary:**

**Revenue:** ${total_revenue:,.2f}
  - Wire: ${rev['wire']['total']:,.2f} | Mobile: ${rev['mobile']['total']:,.2f} | Branch: ${rev['branch']['total']:,.2f}

**GST Collected:** ${total_revenue:,.2f} x 5% = ${gst_collected:,.2f}

**ITCs:**
  - Bank: ${bank_itc:,.2f}
  - Cash: ${cash_itc:,.2f}
  - Phone: ${phone_itc:,.2f} (Greg ${phone['greg_itc']:,.2f} + Lilibeth ${phone['lili_itc']:,.2f})
  - Total: ${total_itc:,.2f}

**Net GST:** ${gst_collected:,.2f} - ${total_itc:,.2f} = ${net_gst:,.2f}
  {"OWING to CRA" if net_gst > 0 else "REFUND from CRA"}

**Shareholder Loans:** ${total_loan:,.2f}
  - Greg (51%): ${total_loan * 0.51:,.2f}
  - Lilibeth (49%): ${total_loan * 0.49:,.2f}
  - Repayment deadline: Nov 30, {int(fy_end) + 1}""")
