"""
Shareholder Loan Tracker
Tracks individual shareholder loan balances for CRA compliance (ITA 15(2))

Cape Bretoner's Oilfield Services Ltd.
Greg MacDonald (51%) | Lilibeth Sejera (49%)
"""

import pandas as pd
from typing import Dict, Optional


class ShareholderTracker:
    """
    Tracks shareholder loan accounts per individual.
    
    CRA Rule (ITA 15(2)): Shareholder loans must be repaid within
    one year of the corporation's fiscal year-end (Nov 30) or the
    outstanding balance becomes taxable personal income.
    """
    
    def __init__(self):
        self.greg_opening = 0.0
        self.greg_withdrawals = 0.0
        self.greg_personal = 0.0
        self.greg_repayments = 0.0
        self.greg_balance = 0.0
        
        self.lilibeth_opening = 0.0
        self.lilibeth_withdrawals = 0.0
        self.lilibeth_personal = 0.0
        self.lilibeth_repayments = 0.0
        self.lilibeth_balance = 0.0
    
    def calculate_from_transactions(self, df: pd.DataFrame) -> Dict:
        """
        Calculate shareholder loan balances from classified transactions.
        
        Tracks per-person instead of splitting everything 51/49.
        Lilibeth's e-transfers are identified by name in description.
        Unattributed transactions (ATM, etc.) default to Greg as primary operator.
        """
        df = df.copy()
        df = df.drop_duplicates(subset=['date', 'description', 'debit', 'credit'], keep='first')
        
        dist_df = df[df['cra_category'] == 'Shareholder Distribution']
        personal_df = df[df['is_personal'] == True]
        
        # Lilibeth's distributions OUT
        lili_out_mask = (
            (dist_df['debit'] > 0) & 
            dist_df['description'].str.contains('Lilibeth|LILIBETH', case=False, na=False)
        )
        self.lilibeth_withdrawals = dist_df.loc[lili_out_mask, 'debit'].sum()
        
        # Lilibeth's repayments IN
        lili_in_mask = (
            (dist_df['credit'] > 0) & 
            dist_df['description'].str.contains('Lilibeth|LILIBETH', case=False, na=False)
        )
        self.lilibeth_repayments = dist_df.loc[lili_in_mask, 'credit'].sum()
        
        # Greg gets everything else (ATM, unattributed, etc.)
        total_dist_out = dist_df[dist_df['debit'] > 0]['debit'].sum()
        total_dist_in = dist_df[dist_df['credit'] > 0]['credit'].sum()
        self.greg_withdrawals = total_dist_out - self.lilibeth_withdrawals
        self.greg_repayments = total_dist_in - self.lilibeth_repayments
        
        # Personal expenses — attribute to both proportionally for now
        # (Angela determines the actual split)
        self.greg_personal = personal_df['debit'].sum() * 0.51
        self.lilibeth_personal = personal_df['debit'].sum() * 0.49
        
        # Calculate balances (negative = owes corp)
        self.greg_balance = self.greg_opening - self.greg_withdrawals - self.greg_personal + self.greg_repayments
        self.lilibeth_balance = self.lilibeth_opening - self.lilibeth_withdrawals - self.lilibeth_personal + self.lilibeth_repayments
        
        return {
            'greg': {
                'opening': self.greg_opening,
                'withdrawals': self.greg_withdrawals,
                'personal': self.greg_personal,
                'repayments': self.greg_repayments,
                'balance': self.greg_balance,
            },
            'lilibeth': {
                'opening': self.lilibeth_opening,
                'withdrawals': self.lilibeth_withdrawals,
                'personal': self.lilibeth_personal,
                'repayments': self.lilibeth_repayments,
                'balance': self.lilibeth_balance,
            },
            'total': {
                'net_distributions': (total_dist_out - total_dist_in),
                'personal_expenses': personal_df['debit'].sum(),
                'total_activity': (total_dist_out - total_dist_in) + personal_df['debit'].sum(),
            }
        }
