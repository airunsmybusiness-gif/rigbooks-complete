"""
Shareholder Loan Tracker
Tracks shareholder loan accounts for CRA compliance
Critical for avoiding taxable benefits under ITA 15(2)
"""

import pandas as pd
import re
from typing import List, Dict, Optional
from datetime import datetime


class ShareholderTracker:
    """
    Tracks shareholder loan accounts for:
    - Greg Chicken (49%)
    - Lilibeth Sejera (51%)
    
    CRA Rules:
    - Shareholder loans (amounts owed BY shareholder TO corporation) must be 
      repaid within one year of the corporation's fiscal year-end
    - If not repaid, the amount is included in shareholder's income
    - Personal expenses paid by corporation = additions to shareholder loan
    """
    
    def __init__(self):
        # Opening balances (can be set from prior year)
        self.greg_opening = 0.0
        self.lilibeth_opening = 0.0
        
        # Transaction tracking
        self.greg_transactions: List[Dict] = []
        self.lilibeth_transactions: List[Dict] = []
        
        # Running totals
        self.greg_withdrawals = 0.0
        self.greg_personal = 0.0
        self.lilibeth_withdrawals = 0.0
        self.lilibeth_personal = 0.0
        
        # Patterns to identify shareholder transactions
        self.GREG_TRANSFER_PATTERNS = [
            r'INTERNET TRANSFER.*TO:.*00099.*78-83439',  # Transfer to Greg's account
            r'INTERNET TRANSFER.*000000\d+.*TO:',  # Generic transfer pattern matching Greg
        ]
        
        self.LILIBETH_TRANSFER_PATTERNS = [
            r'E-TRANSFER.*Lilibeth Sejera',
            r'E-TRANSFER.*LILIBETH',
        ]
        
        # Personal expense patterns (when paid from corporate)
        self.PERSONAL_EXPENSE_PATTERNS = [
            (r'LIQUOR|WINE|CANNABIS|GREEN SOLUTION', 'Personal - Alcohol/Cannabis'),
            (r'IKEA', 'Personal - Furniture'),
            (r'LITTLE STEPS|DAYCARE', 'Personal - Childcare'),
            (r'IGA|GROCERY|SUPERMARKET|SAFEWAY', 'Personal - Groceries'),
            (r'RESTAURANT|PIZZA|BUFFET|STEAK', 'Personal - Dining (non-business)'),
            (r'VALUE VILLAGE|GOODWILL', 'Personal - Clothing'),
            (r'BARBER|SALON|NAILS', 'Personal - Grooming'),
        ]
    
    @property
    def greg_balance(self) -> float:
        """
        Greg's shareholder loan balance
        Positive = Corporation owes Greg (he's put money in or has credit)
        Negative = Greg owes corporation (he's taken more than entitled)
        """
        return self.greg_opening - self.greg_withdrawals - self.greg_personal
    
    @property
    def lilibeth_balance(self) -> float:
        """
        Lilibeth's shareholder loan balance
        """
        return self.lilibeth_opening - self.lilibeth_withdrawals - self.lilibeth_personal
    
    def process_transfers(self, corporate_df: pd.DataFrame, personal_df: pd.DataFrame, 
                          shareholder: str) -> None:
        """
        Match transfers between corporate and personal accounts
        """
        if shareholder == 'Greg':
            patterns = self.GREG_TRANSFER_PATTERNS
        else:
            patterns = self.LILIBETH_TRANSFER_PATTERNS
        
        # Find outgoing transfers from corporate
        for idx, row in corporate_df.iterrows():
            desc = row['description']
            
            for pattern in patterns:
                if re.search(pattern, desc, re.IGNORECASE):
                    amount = row.get('debit', 0) or 0
                    if amount > 0:
                        txn = {
                            'date': row['date'],
                            'description': desc,
                            'type': 'Distribution/Withdrawal',
                            'amount': amount,
                            'source': 'Corporate Account'
                        }
                        
                        if shareholder == 'Greg':
                            self.greg_transactions.append(txn)
                            self.greg_withdrawals += amount
                        else:
                            self.lilibeth_transactions.append(txn)
                            self.lilibeth_withdrawals += amount
                    break
        
        # Find ATM withdrawals (need to determine which shareholder)
        for idx, row in corporate_df.iterrows():
            desc = row['description'].upper()
            
            if 'ATM WITHDRAWAL' in desc or 'ABM WITHDRAWAL' in desc:
                amount = row.get('debit', 0) or 0
                if amount > 0:
                    # Default to Greg as primary operator unless we can determine otherwise
                    # In practice, this should be reviewed
                    txn = {
                        'date': row['date'],
                        'description': row['description'],
                        'type': 'Cash Withdrawal (ATM)',
                        'amount': amount,
                        'source': 'Corporate Account',
                        'note': 'Review: Assign to correct shareholder'
                    }
                    self.greg_transactions.append(txn)
                    self.greg_withdrawals += amount
    
    def process_personal_expenses(self, corporate_df: pd.DataFrame) -> None:
        """
        Identify personal expenses paid from corporate account
        These should be added to shareholder loan (they owe the corp)
        """
        for idx, row in corporate_df.iterrows():
            desc = row['description']
            debit = row.get('debit', 0) or 0
            
            if debit == 0:
                continue
            
            for pattern, category in self.PERSONAL_EXPENSE_PATTERNS:
                if re.search(pattern, desc, re.IGNORECASE):
                    # For now, split between shareholders by ownership ratio
                    # In practice, should be assigned to specific shareholder
                    greg_portion = debit * 0.49
                    lili_portion = debit * 0.51
                    
                    self.greg_transactions.append({
                        'date': row['date'],
                        'description': desc,
                        'type': f'Personal Expense - {category}',
                        'amount': greg_portion,
                        'source': 'Corporate Account',
                        'note': 'Allocated by ownership % - verify assignment'
                    })
                    self.greg_personal += greg_portion
                    
                    self.lilibeth_transactions.append({
                        'date': row['date'],
                        'description': desc,
                        'type': f'Personal Expense - {category}',
                        'amount': lili_portion,
                        'source': 'Corporate Account',
                        'note': 'Allocated by ownership % - verify assignment'
                    })
                    self.lilibeth_personal += lili_portion
                    
                    break
    
    def set_opening_balances(self, greg: float, lilibeth: float) -> None:
        """
        Set opening balances from prior year
        """
        self.greg_opening = greg
        self.lilibeth_opening = lilibeth
    
    def add_shareholder_contribution(self, shareholder: str, amount: float, 
                                     date: str, description: str) -> None:
        """
        Record when shareholder puts money INTO the corporation
        This increases their loan balance (corp owes them more)
        """
        txn = {
            'date': date,
            'description': description,
            'type': 'Shareholder Contribution',
            'amount': -amount,  # Negative because it reduces what they owe
            'source': 'Manual Entry'
        }
        
        if shareholder == 'Greg':
            self.greg_transactions.append(txn)
            self.greg_withdrawals -= amount  # Reduces net withdrawals
        else:
            self.lilibeth_transactions.append(txn)
            self.lilibeth_withdrawals -= amount
    
    def record_dividend(self, shareholder: str, amount: float, 
                        date: str, resolution_date: str) -> None:
        """
        Record dividend declaration
        Dividends reduce shareholder loan but create T5 reporting requirement
        """
        txn = {
            'date': date,
            'description': f'Dividend per resolution dated {resolution_date}',
            'type': 'Dividend',
            'amount': amount,
            'source': 'Manual Entry',
            'note': 'Creates T5 reporting requirement'
        }
        
        if shareholder == 'Greg':
            self.greg_transactions.append(txn)
        else:
            self.lilibeth_transactions.append(txn)
    
    def generate_year_end_report(self, fiscal_year_end: str) -> Dict:
        """
        Generate year-end shareholder loan summary
        """
        return {
            'fiscal_year_end': fiscal_year_end,
            'greg': {
                'opening_balance': self.greg_opening,
                'withdrawals': self.greg_withdrawals,
                'personal_expenses': self.greg_personal,
                'closing_balance': self.greg_balance,
                'transactions': self.greg_transactions,
                'status': 'OK' if self.greg_balance >= 0 else 'OWING - Taxable Benefit Risk'
            },
            'lilibeth': {
                'opening_balance': self.lilibeth_opening,
                'withdrawals': self.lilibeth_withdrawals,
                'personal_expenses': self.lilibeth_personal,
                'closing_balance': self.lilibeth_balance,
                'transactions': self.lilibeth_transactions,
                'status': 'OK' if self.lilibeth_balance >= 0 else 'OWING - Taxable Benefit Risk'
            }
        }
    
    def check_taxable_benefit_risk(self) -> List[Dict]:
        """
        Check for potential taxable benefit issues under ITA 15(2)
        """
        issues = []
        
        if self.greg_balance < 0:
            issues.append({
                'shareholder': 'Greg Chicken',
                'amount_owing': abs(self.greg_balance),
                'issue': 'Shareholder owes corporation money at year-end',
                'consequence': 'If not repaid within one year of fiscal year-end, '
                               'amount will be included in personal income',
                'deadline': 'November 30 of following year'
            })
        
        if self.lilibeth_balance < 0:
            issues.append({
                'shareholder': 'Lilibeth Sejera',
                'amount_owing': abs(self.lilibeth_balance),
                'issue': 'Shareholder owes corporation money at year-end',
                'consequence': 'If not repaid within one year of fiscal year-end, '
                               'amount will be included in personal income',
                'deadline': 'November 30 of following year'
            })
        
        return issues


class DividendTracker:
    """
    Tracks dividend declarations and payments for T5 preparation
    """
    
    def __init__(self):
        self.dividends: List[Dict] = []
    
    def declare_dividend(self, total_amount: float, declaration_date: str,
                         payment_date: str, dividend_type: str = 'non-eligible') -> Dict:
        """
        Record a dividend declaration
        
        Args:
            total_amount: Total dividend amount
            declaration_date: Date of board resolution
            payment_date: Date dividend was/will be paid
            dividend_type: 'eligible' or 'non-eligible'
        """
        # Split by ownership
        greg_amount = total_amount * 0.49
        lili_amount = total_amount * 0.51
        
        dividend = {
            'declaration_date': declaration_date,
            'payment_date': payment_date,
            'type': dividend_type,
            'total_amount': total_amount,
            'greg_amount': greg_amount,
            'lilibeth_amount': lili_amount,
            'greg_t5_taxable': self._calculate_t5_taxable(greg_amount, dividend_type),
            'lilibeth_t5_taxable': self._calculate_t5_taxable(lili_amount, dividend_type),
        }
        
        self.dividends.append(dividend)
        return dividend
    
    def _calculate_t5_taxable(self, amount: float, dividend_type: str) -> float:
        """
        Calculate taxable amount for T5 (with gross-up)
        Eligible dividends: 38% gross-up
        Non-eligible dividends: 15% gross-up
        """
        if dividend_type == 'eligible':
            return amount * 1.38
        else:
            return amount * 1.15
    
    def generate_t5_data(self) -> List[Dict]:
        """
        Generate T5 slip data for each shareholder
        """
        t5_slips = []
        
        # Aggregate by shareholder
        greg_total = sum(d['greg_amount'] for d in self.dividends)
        greg_taxable = sum(d['greg_t5_taxable'] for d in self.dividends)
        
        lili_total = sum(d['lilibeth_amount'] for d in self.dividends)
        lili_taxable = sum(d['lilibeth_t5_taxable'] for d in self.dividends)
        
        if greg_total > 0:
            t5_slips.append({
                'recipient': 'Greg Chicken',
                'sin': '[SIN REQUIRED]',
                'actual_dividends': greg_total,
                'taxable_dividends': greg_taxable,
                'dividend_tax_credit': greg_taxable * 0.150198,  # Approximate
            })
        
        if lili_total > 0:
            t5_slips.append({
                'recipient': 'Lilibeth Sejera',
                'sin': '[SIN REQUIRED]',
                'actual_dividends': lili_total,
                'taxable_dividends': lili_taxable,
                'dividend_tax_credit': lili_taxable * 0.150198,
            })
        
        return t5_slips
