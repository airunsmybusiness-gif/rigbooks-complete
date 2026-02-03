"""
Report Generator
Produces CRA-compliant reports and exports
"""

import pandas as pd
from datetime import datetime
from typing import Dict, List
import io


class ReportGenerator:
    """
    Generates various reports for CRA filing and bookkeeping
    """
    
    def __init__(self, company_name: str = "Cape Bretoner's Oilfield Services Ltd.",
                 fiscal_year_end: str = "November 30"):
        self.company_name = company_name
        self.fiscal_year_end = fiscal_year_end
    
    def generate_income_statement(self, df: pd.DataFrame, 
                                   start_date: str = None, 
                                   end_date: str = None) -> str:
        """
        Generate basic income statement
        """
        df = df.copy()
        
        if start_date:
            df = df[pd.to_datetime(df['date']) >= pd.to_datetime(start_date)]
        if end_date:
            df = df[pd.to_datetime(df['date']) <= pd.to_datetime(end_date)]
        
        # Revenue
        revenue_categories = ['Revenue - Oilfield Services']
        revenue = df[df['cra_category'].isin(revenue_categories)]['credit'].sum()
        
        # Cost categories
        expense_categories = {
            'Fuel & Petroleum': 0,
            'Vehicle Repairs & Maintenance': 0,
            'Equipment & Supplies': 0,
            'Subcontractor Payments': 0,
            'Office Expenses': 0,
            'Professional Fees': 0,
            'Insurance': 0,
            'Bank Charges & Interest': 0,
            'Telephone & Communications': 0,
            'Meals & Entertainment (50%)': 0,
            'Travel': 0,
            'Rent': 0,
            'Utilities': 0,
            'Wages & Salaries': 0,
            'Other Expense': 0,
        }
        
        for cat in expense_categories:
            mask = (df['cra_category'] == cat) & (df['is_personal'] == False)
            expense_categories[cat] = df.loc[mask, 'debit'].sum()
        
        total_expenses = sum(expense_categories.values())
        net_income = revenue - total_expenses
        
        # Format report
        report = f"""
{'=' * 60}
INCOME STATEMENT
{self.company_name}
Period: {start_date or 'Beginning'} to {end_date or 'End'}
{'=' * 60}

REVENUE
-------
Oilfield Services Revenue          ${revenue:>15,.2f}
                                   ----------------
TOTAL REVENUE                      ${revenue:>15,.2f}

EXPENSES
--------
"""
        for cat, amount in expense_categories.items():
            if amount > 0:
                report += f"{cat:<35} ${amount:>15,.2f}\n"
        
        report += f"""                                   ----------------
TOTAL EXPENSES                     ${total_expenses:>15,.2f}

                                   ================
NET INCOME BEFORE TAX              ${net_income:>15,.2f}
{'=' * 60}
"""
        return report
    
    def generate_gst_working_papers(self, df: pd.DataFrame, gst_summary: Dict) -> str:
        """
        Generate GST working papers for accountant
        """
        report = f"""
{'=' * 70}
GST/HST WORKING PAPERS
{self.company_name}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'=' * 70}

PART 1: GST COLLECTED ON REVENUE
--------------------------------
Total Taxable Revenue (Line 101):    ${gst_summary['total_revenue']:>15,.2f}
Exempt Revenue (Line 103):           ${gst_summary['exempt_revenue']:>15,.2f}

GST Collected (5%):                  ${gst_summary['gst_collected']:>15,.2f}
  Calculation: ${gst_summary['total_revenue']:,.2f} × (5% ÷ 105%)

PART 2: INPUT TAX CREDITS (Line 106)
------------------------------------
"""
        
        for key, label in [
            ('itc_fuel', 'Fuel & Petroleum'),
            ('itc_equipment', 'Equipment, Repairs & CCA'),
            ('itc_professional', 'Professional Fees'),
            ('itc_meals', 'Meals & Entertainment (50%)'),
            ('itc_other', 'Other Eligible Expenses'),
        ]:
            report += f"{label:<35} ${gst_summary.get(key, 0):>15,.2f}\n"
        
        report += f"""                                    ----------------
TOTAL ITCs:                          ${gst_summary['total_itc']:>15,.2f}

PART 3: NET GST CALCULATION
---------------------------
GST Collected (Line 105):            ${gst_summary['gst_collected']:>15,.2f}
Less: ITCs (Line 108):               ${gst_summary['total_itc']:>15,.2f}
                                     ----------------
"""
        
        net = gst_summary['gst_collected'] - gst_summary['total_itc']
        if net > 0:
            report += f"NET GST OWING (Line 109):            ${net:>15,.2f}\n"
        else:
            report += f"NET GST REFUND (Line 114):           ${abs(net):>15,.2f}\n"
        
        report += f"""
{'=' * 70}
"""
        return report
    
    def generate_expense_schedule(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate expense schedule by CRA category (Schedule 125 format)
        """
        expenses = df[(df['debit'] > 0) & (df['is_personal'] == False)].copy()
        
        summary = expenses.groupby('cra_category').agg({
            'debit': ['sum', 'count'],
            'itc_amount': 'sum'
        }).reset_index()
        
        summary.columns = ['CRA Category', 'Total Amount', 'Transaction Count', 'ITC Claimed']
        summary['Net Cost'] = summary['Total Amount'] - summary['ITC Claimed']
        
        return summary.sort_values('Total Amount', ascending=False)
    
    def generate_shareholder_loan_report(self, tracker) -> str:
        """
        Generate shareholder loan account report
        """
        report = f"""
{'=' * 70}
SHAREHOLDER LOAN ACCOUNT REPORT
{self.company_name}
Fiscal Year End: {self.fiscal_year_end}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{'=' * 70}

GREG CHICKEN (49% Shareholder)
------------------------------
Opening Balance:                     ${tracker.greg_opening:>15,.2f}
Less: Withdrawals/Distributions:     ${tracker.greg_withdrawals:>15,.2f}
Less: Personal Expenses (Corp Paid): ${tracker.greg_personal:>15,.2f}
                                     ----------------
CLOSING BALANCE:                     ${tracker.greg_balance:>15,.2f}
"""
        
        if tracker.greg_balance < 0:
            report += f"""
*** WARNING: NEGATIVE BALANCE ***
Greg owes the corporation ${abs(tracker.greg_balance):,.2f}
Per ITA 15(2), this must be repaid within one year of fiscal year-end
or it will be included in his personal income.
Repayment deadline: November 30 of the following year
"""
        
        report += f"""

LILIBETH SEJERA (51% Shareholder)
---------------------------------
Opening Balance:                     ${tracker.lilibeth_opening:>15,.2f}
Less: Withdrawals/Distributions:     ${tracker.lilibeth_withdrawals:>15,.2f}
Less: Personal Expenses (Corp Paid): ${tracker.lilibeth_personal:>15,.2f}
                                     ----------------
CLOSING BALANCE:                     ${tracker.lilibeth_balance:>15,.2f}
"""
        
        if tracker.lilibeth_balance < 0:
            report += f"""
*** WARNING: NEGATIVE BALANCE ***
Lilibeth owes the corporation ${abs(tracker.lilibeth_balance):,.2f}
Per ITA 15(2), this must be repaid within one year of fiscal year-end
or it will be included in her personal income.
Repayment deadline: November 30 of the following year
"""
        
        report += f"""
{'=' * 70}
CRA COMPLIANCE NOTES:
- Shareholder loans must be tracked meticulously
- Personal expenses paid by corporation increase shareholder loan receivable
- Dividends should be formally declared by board resolution
- T5 slips required for any dividends paid
{'=' * 70}
"""
        return report
    
    def generate_transaction_export(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate full transaction export with all classifications
        """
        export_cols = [
            'date', 'description', 'debit', 'credit', 
            'cra_category', 'itc_amount', 'is_personal', 
            'needs_review', 'notes', 'account'
        ]
        
        # Only include columns that exist
        available_cols = [c for c in export_cols if c in df.columns]
        
        return df[available_cols].sort_values('date')
    
    def generate_items_for_review(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate list of items that need accountant review
        """
        review_items = df[df['needs_review'] == True].copy()
        
        # Add reason for review
        def get_review_reason(row):
            reasons = []
            if row['debit'] >= 500:
                reasons.append('Large expense - verify CCA eligibility')
            if 'Unclassified' in str(row.get('notes', '')):
                reasons.append('Could not auto-classify')
            if row.get('is_personal', False):
                reasons.append('Flagged as potential personal expense')
            if 'WALMART' in str(row.get('description', '')).upper():
                reasons.append('Mixed-use vendor - verify business purpose')
            return '; '.join(reasons) if reasons else 'General review'
        
        review_items['review_reason'] = review_items.apply(get_review_reason, axis=1)
        
        return review_items[['date', 'description', 'debit', 'credit', 
                            'cra_category', 'review_reason']]
