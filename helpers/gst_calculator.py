"""
GST Calculator
Aligned with CRA Form GST34 for GST/HST Return
"""

import pandas as pd
from typing import Dict


class GSTCalculator:
    """
    Calculates GST collected and Input Tax Credits (ITCs) for CRA filing
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
    
    # ITC category groupings for reporting
    ITC_GROUPS = {
        'itc_fuel': ['Fuel & Petroleum'],
        'itc_equipment': ['Equipment & Supplies', 'Vehicle Repairs & Maintenance', 'CCA - Capital Asset'],
        'itc_professional': ['Professional Fees'],
        'itc_meals': ['Meals & Entertainment (50%)'],
        'itc_other': ['Office Expenses', 'Telephone & Communications', 'Travel', 'Rent - Commercial', 'Utilities', 'Other Expense', 'Subcontractor Payments'],
    }
    
    # Categories with NO ITC
    NO_ITC_CATEGORIES = [
        'Insurance - Business',
        'Bank Charges & Interest',
        'Wages & Salaries',
        'Shareholder Distribution',
        'Shareholder Loan - Personal Expense',
        'Loan Payment - Business Vehicle',
        'Loan Payment - Personal',
        'GST Remittance',
        'Income Tax Installment',
        'GST Refund',
        'Transfer - Non-Taxable',
    ]
    
    def calculate_period(self, df: pd.DataFrame, start_date: str = None, end_date: str = None) -> Dict:
        """
        Calculate GST summary for a period
        
        Returns dict with:
        - total_revenue: Gross taxable revenue
        - exempt_revenue: Revenue not subject to GST
        - gst_collected: GST on taxable supplies (5%)
        - itc_fuel, itc_equipment, etc.: ITCs by category
        - total_itc: Sum of all ITCs
        """
        df = df.copy()
        
        # Filter by date if provided
        if start_date:
            df = df[pd.to_datetime(df['date']) >= pd.to_datetime(start_date)]
        if end_date:
            df = df[pd.to_datetime(df['date']) <= pd.to_datetime(end_date)]
        
        # Calculate revenue
        revenue_mask = df['cra_category'].isin(self.TAXABLE_REVENUE_CATEGORIES) & (df['credit'] > 0)
        total_revenue = df.loc[revenue_mask, 'credit'].sum()
        
        # Exempt revenue
        exempt_mask = df['cra_category'].isin(self.EXEMPT_REVENUE_CATEGORIES) & (df['credit'] > 0)
        exempt_revenue = df.loc[exempt_mask, 'credit'].sum()
        
        # GST collected on taxable revenue
        # Revenue is typically GST-inclusive when received from clients
        # GST = Revenue * (5% / 105%) = Revenue / 21
        gst_collected = total_revenue * (self.GST_RATE / (1 + self.GST_RATE))
        
        # Calculate ITCs by group
        result = {
            'total_revenue': round(total_revenue, 2),
            'exempt_revenue': round(exempt_revenue, 2),
            'gst_collected': round(gst_collected, 2),
        }
        
        total_itc = 0.0
        
        for group_name, categories in self.ITC_GROUPS.items():
            group_mask = df['cra_category'].isin(categories) & (df['is_personal'] == False)
            group_itc = df.loc[group_mask, 'itc_amount'].sum()
            result[group_name] = round(group_itc, 2)
            total_itc += group_itc
        
        result['total_itc'] = round(total_itc, 2)
        result['net_gst'] = round(gst_collected - total_itc, 2)
        
        return result
    
    def generate_itc_schedule(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate detailed ITC schedule for working papers
        """
        # Only ITC-eligible expenses
        itc_df = df[(df['itc_amount'] > 0) & (df['is_personal'] == False)].copy()
        
        itc_df['gross_amount'] = itc_df['debit']
        itc_df['net_amount'] = itc_df['debit'] - itc_df['itc_amount']
        
        return itc_df[['date', 'description', 'cra_category', 'gross_amount', 'itc_amount', 'net_amount']]
    
    def validate_itc_claims(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate ITC claims and flag potential issues
        """
        issues = []
        
        for idx, row in df.iterrows():
            # Check for ITC on personal expenses
            if row['is_personal'] and row['itc_amount'] > 0:
                issues.append({
                    'date': row['date'],
                    'description': row['description'],
                    'issue': 'ITC claimed on personal expense',
                    'amount': row['itc_amount']
                })
            
            # Check for ITC on exempt categories
            if row['cra_category'] in self.NO_ITC_CATEGORIES and row['itc_amount'] > 0:
                issues.append({
                    'date': row['date'],
                    'description': row['description'],
                    'issue': f'ITC claimed on exempt category: {row["cra_category"]}',
                    'amount': row['itc_amount']
                })
            
            # Check for meals at 100% instead of 50%
            if 'Meals' in row['cra_category']:
                expected_itc = row['debit'] * (self.GST_RATE / (1 + self.GST_RATE)) * 0.5
                if abs(row['itc_amount'] - expected_itc) > 0.01:
                    issues.append({
                        'date': row['date'],
                        'description': row['description'],
                        'issue': 'Meals ITC should be 50%',
                        'amount': row['itc_amount'] - expected_itc
                    })
        
        return pd.DataFrame(issues) if issues else pd.DataFrame()


class QuarterlyGSTCalculator(GSTCalculator):
    """
    Handles quarterly GST filing with fiscal year awareness
    Fiscal year end: November 30
    Q1: Dec 1 - Feb 28/29
    Q2: Mar 1 - May 31
    Q3: Jun 1 - Aug 31
    Q4: Sep 1 - Nov 30
    """
    
    def get_quarter_dates(self, fiscal_year: int, quarter: int) -> tuple:
        """
        Get start and end dates for a quarter
        fiscal_year is the year the fiscal year ENDS (e.g., 2025 for FY ending Nov 30, 2025)
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
        Calculate GST for a specific quarter
        """
        start_date, end_date = self.get_quarter_dates(fiscal_year, quarter)
        return self.calculate_period(df, start_date, end_date)
