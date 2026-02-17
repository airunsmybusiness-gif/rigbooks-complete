"""
GST Calculator
Aligned with CRA Form GST34 for GST/HST Return

FIXED (Feb 2026):
- Revenue calculation now properly handles wire transfers
- Added validation to prevent double-counting
- ITC calculations verified against CRA requirements
"""

import pandas as pd
from typing import Dict


class GSTCalculator:
    """
    Calculates GST collected and Input Tax Credits (ITCs) for CRA filing
    
    CRA GST34 Line References:
    - Line 101: Total sales and other revenue (before GST)
    - Line 103: Exempt supplies
    - Line 105: GST/HST collected
    - Line 106: Input Tax Credits
    - Line 109: Net tax (or Line 114 for refund)
    """
    
    GST_RATE = 0.05
    
    # Categories that represent taxable revenue (GST collected)
    TAXABLE_REVENUE_CATEGORIES = [
        'Revenue - Oilfield Services',
    ]
    
    # Categories exempt from GST collection
    EXEMPT_REVENUE_CATEGORIES = [
        'Transfer - Non-Taxable',
        'GST Refund',
    ]
    
    # ITC category groupings for CRA reporting
    ITC_GROUPS = {
        'itc_fuel': ['Fuel & Petroleum'],
        'itc_equipment': ['Equipment & Supplies', 'Vehicle Repairs & Maintenance', 'CCA - Capital Asset'],
        'itc_professional': ['Professional Fees'],
        'itc_meals': ['Meals & Entertainment (50%)'],
        'itc_other': ['Office Expenses', 'Telephone & Communications', 'Travel', 
                      'Rent - Commercial', 'Utilities', 'Other Expense', 'Subcontractor Payments'],
    }
    
    # Categories with NO ITC (GST-exempt or non-taxable)
    NO_ITC_CATEGORIES = [
        'Insurance - Business',      # Insurance is GST-exempt
        'Bank Charges & Interest',   # Financial services are exempt
        'Wages & Salaries',          # Not a taxable supply
        'Shareholder Distribution',  # Not a purchase
        'Shareholder Loan - Personal Expense',  # Personal = no ITC
        'Loan Payment - Business Vehicle',      # Principal/interest = no GST
        'Loan Payment - Personal',   # Personal = no ITC
        'GST Remittance',            # Not a purchase
        'Income Tax Installment',    # Not a purchase
        'GST Refund',                # Not a purchase
        'Transfer - Non-Taxable',    # Transfers aren't purchases
    ]
    
    def calculate_period(self, df: pd.DataFrame, start_date: str = None, end_date: str = None) -> Dict:
        """
        Calculate GST summary for a period.
        
        CRITICAL: This method now ensures no double-counting of revenue.
        
        Args:
            df: Classified transaction DataFrame
            start_date: Optional period start (YYYY-MM-DD)
            end_date: Optional period end (YYYY-MM-DD)
            
        Returns:
            Dict with:
            - total_revenue: Gross taxable revenue (GST-inclusive)
            - exempt_revenue: Revenue not subject to GST
            - gst_collected: GST on taxable supplies (extracted from inclusive amounts)
            - itc_fuel, itc_equipment, etc.: ITCs by category
            - total_itc: Sum of all ITCs
            - net_gst: GST collected minus ITCs
        """
        df = df.copy()
        
        # CRITICAL: Remove any duplicate rows first
        df = df.drop_duplicates(subset=['date', 'description', 'debit', 'credit'], keep='first')
        
        # Filter by date if provided
        if start_date:
            df = df[pd.to_datetime(df['date']) >= pd.to_datetime(start_date)]
        if end_date:
            df = df[pd.to_datetime(df['date']) <= pd.to_datetime(end_date)]
        
        # ===== REVENUE CALCULATION =====
        # Only count credits (money IN) that are categorized as taxable revenue
        revenue_mask = (
            df['cra_category'].isin(self.TAXABLE_REVENUE_CATEGORIES) & 
            (df['credit'] > 0)
        )
        total_revenue = df.loc[revenue_mask, 'credit'].sum()
        
        # Exempt revenue (transfers, refunds, etc.)
        exempt_mask = (
            df['cra_category'].isin(self.EXEMPT_REVENUE_CATEGORIES) & 
            (df['credit'] > 0)
        )
        exempt_revenue = df.loc[exempt_mask, 'credit'].sum()
        
        # ===== GST COLLECTED =====
        # Revenue received from clients is GST-inclusive
        # GST = Revenue × (5% ÷ 105%) = Revenue ÷ 21
        gst_collected = total_revenue * (self.GST_RATE / (1 + self.GST_RATE))
        
        # ===== INPUT TAX CREDITS =====
        result = {
            'total_revenue': round(total_revenue, 2),
            'exempt_revenue': round(exempt_revenue, 2),
            'gst_collected': round(gst_collected, 2),
        }
        
        total_itc = 0.0
        
        for group_name, categories in self.ITC_GROUPS.items():
            # Only business expenses (is_personal = False) qualify for ITC
            group_mask = (
                df['cra_category'].isin(categories) & 
                (df['is_personal'] == False) &
                (df['debit'] > 0)  # Must be an expense (debit)
            )
            group_itc = df.loc[group_mask, 'itc_amount'].sum()
            result[group_name] = round(group_itc, 2)
            total_itc += group_itc
        
        result['total_itc'] = round(total_itc, 2)
        result['net_gst'] = round(gst_collected - total_itc, 2)
        
        return result
    
    def calculate_revenue_breakdown(self, df: pd.DataFrame) -> Dict:
        """
        Get detailed revenue breakdown by source type.
        Useful for reconciliation and audit trail.
        
        Returns:
            Dict with wire_transfers, mobile_deposits, branch_deposits, other_revenue
        """
        df = df.copy()
        df = df.drop_duplicates(subset=['date', 'description', 'debit', 'credit'], keep='first')
        
        # Only look at credits (money in)
        credits = df[df['credit'] > 0].copy()
        
        # Wire transfers
        wire_mask = credits['description'].str.contains('WIRE TSF', case=False, na=False)
        wire_total = credits.loc[wire_mask, 'credit'].sum()
        wire_count = wire_mask.sum()
        
        # Mobile deposits
        mobile_mask = credits['description'].str.contains('MOBILE DEPOSIT', case=False, na=False)
        mobile_total = credits.loc[mobile_mask, 'credit'].sum()
        mobile_count = mobile_mask.sum()
        
        # Branch deposits
        branch_mask = credits['description'].str.contains(
            'BRANCH DEPOSIT|COUNTER DEPOSIT|DEPOSIT IN BRANCH', 
            case=False, na=False, regex=True
        )
        branch_total = credits.loc[branch_mask, 'credit'].sum()
        branch_count = branch_mask.sum()
        
        # Other revenue (not wire, mobile, or branch)
        other_mask = (
            (credits['cra_category'] == 'Revenue - Oilfield Services') &
            ~wire_mask & ~mobile_mask & ~branch_mask
        )
        other_total = credits.loc[other_mask, 'credit'].sum()
        other_count = other_mask.sum()
        
        # Total taxable revenue
        revenue_mask = credits['cra_category'] == 'Revenue - Oilfield Services'
        total_revenue = credits.loc[revenue_mask, 'credit'].sum()
        
        return {
            'wire_transfers': {'total': round(wire_total, 2), 'count': int(wire_count)},
            'mobile_deposits': {'total': round(mobile_total, 2), 'count': int(mobile_count)},
            'branch_deposits': {'total': round(branch_total, 2), 'count': int(branch_count)},
            'other_revenue': {'total': round(other_total, 2), 'count': int(other_count)},
            'total_revenue': round(total_revenue, 2),
            'total_transactions': int(revenue_mask.sum()),
        }
    
    def generate_itc_schedule(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate detailed ITC schedule for CRA working papers.
        
        Returns DataFrame with all ITC-eligible transactions for audit trail.
        """
        df = df.copy()
        df = df.drop_duplicates(subset=['date', 'description', 'debit', 'credit'], keep='first')
        
        # Only ITC-eligible expenses (not personal)
        itc_df = df[(df['itc_amount'] > 0) & (df['is_personal'] == False)].copy()
        
        itc_df['gross_amount'] = itc_df['debit']
        itc_df['net_amount'] = itc_df['debit'] - itc_df['itc_amount']
        
        return itc_df[['date', 'description', 'cra_category', 'gross_amount', 'itc_amount', 'net_amount']]
    
    def validate_itc_claims(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate ITC claims and flag potential CRA audit issues.
        
        Returns DataFrame with any problematic transactions.
        """
        df = df.copy()
        issues = []
        
        for idx, row in df.iterrows():
            # Issue 1: ITC claimed on personal expense
            if row['is_personal'] and row['itc_amount'] > 0:
                issues.append({
                    'date': row['date'],
                    'description': row['description'],
                    'issue': 'ITC claimed on personal expense - CRA will deny',
                    'amount': row['itc_amount'],
                    'severity': 'HIGH'
                })
            
            # Issue 2: ITC claimed on exempt category
            if row['cra_category'] in self.NO_ITC_CATEGORIES and row['itc_amount'] > 0:
                issues.append({
                    'date': row['date'],
                    'description': row['description'],
                    'issue': f'ITC claimed on exempt category: {row["cra_category"]}',
                    'amount': row['itc_amount'],
                    'severity': 'HIGH'
                })
            
            # Issue 3: Meals at wrong rate (should be 50%)
            if 'Meals' in str(row['cra_category']) and row['debit'] > 0:
                expected_itc = row['debit'] * (self.GST_RATE / (1 + self.GST_RATE)) * 0.5
                if abs(row['itc_amount'] - expected_itc) > 0.01:
                    issues.append({
                        'date': row['date'],
                        'description': row['description'],
                        'issue': f'Meals ITC should be 50% (${expected_itc:.2f}), claimed ${row["itc_amount"]:.2f}',
                        'amount': row['itc_amount'] - expected_itc,
                        'severity': 'MEDIUM'
                    })
            
            # Issue 4: Large expense without review flag
            if row['debit'] >= 500 and not row['needs_review']:
                if row['cra_category'] in ['Equipment & Supplies', 'Vehicle Repairs & Maintenance', 'Other Expense']:
                    issues.append({
                        'date': row['date'],
                        'description': row['description'],
                        'issue': 'Large expense - verify CCA eligibility and business purpose',
                        'amount': row['debit'],
                        'severity': 'LOW'
                    })
        
        return pd.DataFrame(issues) if issues else pd.DataFrame()
    
    def get_summary_for_display(self, df: pd.DataFrame) -> Dict:
        """
        Get all summary data needed for the app display.
        Combines period calculations with revenue breakdown.
        """
        period_data = self.calculate_period(df)
        revenue_data = self.calculate_revenue_breakdown(df)
        
        return {
            **period_data,
            'revenue_breakdown': revenue_data
        }


class QuarterlyGSTCalculator(GSTCalculator):
    """
    Handles quarterly GST filing with fiscal year awareness.
    
    Cape Bretoner's fiscal year end: November 30
    Q1: Dec 1 - Feb 28/29
    Q2: Mar 1 - May 31
    Q3: Jun 1 - Aug 31
    Q4: Sep 1 - Nov 30
    """
    
    def get_quarter_dates(self, fiscal_year: int, quarter: int) -> tuple:
        """
        Get start and end dates for a quarter.
        
        Args:
            fiscal_year: Year the fiscal year ENDS (e.g., 2025 for FY ending Nov 30, 2025)
            quarter: 1-4
            
        Returns:
            (start_date, end_date) as strings
        """
        if quarter == 1:
            # Dec 1 (prev year) to Feb 28/29
            start = f"{fiscal_year - 1}-12-01"
            # Check for leap year
            if fiscal_year % 4 == 0 and (fiscal_year % 100 != 0 or fiscal_year % 400 == 0):
                end = f"{fiscal_year}-02-29"
            else:
                end = f"{fiscal_year}-02-28"
        elif quarter == 2:
            start = f"{fiscal_year}-03-01"
            end = f"{fiscal_year}-05-31"
        elif quarter == 3:
            start = f"{fiscal_year}-06-01"
            end = f"{fiscal_year}-08-31"
        elif quarter == 4:
            start = f"{fiscal_year}-09-01"
            end = f"{fiscal_year}-11-30"
        else:
            raise ValueError("Quarter must be 1-4")
        
        return start, end
    
    def calculate_quarter(self, df: pd.DataFrame, fiscal_year: int, quarter: int) -> Dict:
        """
        Calculate GST for a specific quarter.
        
        Args:
            df: Classified transaction DataFrame
            fiscal_year: Year the fiscal year ends
            quarter: 1-4
            
        Returns:
            GST summary dict for the quarter
        """
        start_date, end_date = self.get_quarter_dates(fiscal_year, quarter)
        return self.calculate_period(df, start_date, end_date)
    
    def calculate_all_quarters(self, df: pd.DataFrame, fiscal_year: int) -> Dict:
        """
        Calculate GST for all four quarters.
        
        Returns:
            Dict with Q1, Q2, Q3, Q4, and annual_total
        """
        results = {}
        annual_revenue = 0
        annual_gst_collected = 0
        annual_itc = 0
        
        for q in range(1, 5):
            q_data = self.calculate_quarter(df, fiscal_year, q)
            results[f'Q{q}'] = q_data
            annual_revenue += q_data['total_revenue']
            annual_gst_collected += q_data['gst_collected']
            annual_itc += q_data['total_itc']
        
        results['annual_total'] = {
            'total_revenue': round(annual_revenue, 2),
            'gst_collected': round(annual_gst_collected, 2),
            'total_itc': round(annual_itc, 2),
            'net_gst': round(annual_gst_collected - annual_itc, 2)
        }
        
        return results
