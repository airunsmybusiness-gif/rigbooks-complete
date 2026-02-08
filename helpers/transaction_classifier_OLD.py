"""
Transaction Classifier
CRA-compliant categorization with ITC eligibility determination
Customized for Cape Bretoner's Oilfield Services Ltd.

BUSINESS CONTEXT:
- Oilfield services company in Alberta
- Owners: Lilibeth (51%), Greg (49%)
- Greg contracts for Long Run/PricewaterhouseCoopers
- Lilibeth works full-time at Rick's Oilfield Hauling (T4 income)
- Business vehicle: Chevy Silverado (TD loan)
- Personal vehicles: Mazda (Scotia loan)
- REDWATER RENT = Business expense (where they live for work)
- Peace River house = Owned personally, mortgage from Greg's personal account
- Childcare (Little Steps) = Personal

EXCLUDE FROM ALL CALCULATIONS:
- 1695784 Alberta Ltd payments to Lilibeth = Friend's utility contribution for Peace River house
  (Nothing to do with business)
"""

import pandas as pd
import re
from typing import Dict, Tuple, Optional


class TransactionClassifier:
    """
    Classifies bank transactions into CRA categories with ITC eligibility
    """
    
    # GST Rate
    GST_RATE = 0.05
    
    # Category definitions with ITC eligibility
    CATEGORIES = {
        'Revenue - Oilfield Services': {'itc_eligible': False, 'itc_rate': 0},
        'Fuel & Petroleum': {'itc_eligible': True, 'itc_rate': 1.0},
        'Vehicle Repairs & Maintenance': {'itc_eligible': True, 'itc_rate': 1.0},
        'Equipment & Supplies': {'itc_eligible': True, 'itc_rate': 1.0},
        'Subcontractor Payments': {'itc_eligible': True, 'itc_rate': 1.0},
        'Office Expenses': {'itc_eligible': True, 'itc_rate': 1.0},
        'Professional Fees': {'itc_eligible': True, 'itc_rate': 1.0},
        'Insurance - Business': {'itc_eligible': False, 'itc_rate': 0},
        'Bank Charges & Interest': {'itc_eligible': False, 'itc_rate': 0},
        'Telephone & Communications': {'itc_eligible': True, 'itc_rate': 1.0},
        'Meals & Entertainment (50%)': {'itc_eligible': True, 'itc_rate': 0.5},
        'Travel': {'itc_eligible': True, 'itc_rate': 1.0},
        'Rent - Commercial': {'itc_eligible': True, 'itc_rate': 1.0},
        'Utilities': {'itc_eligible': True, 'itc_rate': 1.0},
        'Wages & Salaries': {'itc_eligible': False, 'itc_rate': 0},
        'Shareholder Distribution': {'itc_eligible': False, 'itc_rate': 0},
        'Shareholder Loan - Personal Expense': {'itc_eligible': False, 'itc_rate': 0},
        'Loan Payment - Business Vehicle': {'itc_eligible': False, 'itc_rate': 0},
        'Loan Payment - Personal': {'itc_eligible': False, 'itc_rate': 0},
        'GST Remittance': {'itc_eligible': False, 'itc_rate': 0},
        'Income Tax Installment': {'itc_eligible': False, 'itc_rate': 0},
        'GST Refund': {'itc_eligible': False, 'itc_rate': 0},
        'Transfer - Non-Taxable': {'itc_eligible': False, 'itc_rate': 0},
        'CCA - Capital Asset': {'itc_eligible': True, 'itc_rate': 1.0},
        'Other Expense': {'itc_eligible': True, 'itc_rate': 1.0},
    }
    
    CLASSIFICATION_RULES = [
        # ===== REVENUE =====
        (r'WIRE TSF.*PRICEWATERHOUSE|LONG RUN|CONTRACTOR INV', 'Revenue - Oilfield Services', False, False),
        (r'WIRE TSF.*EXPLORATION', 'Revenue - Oilfield Services', False, False),
        (r'MOBILE DEPOSIT', 'Revenue - Oilfield Services', False, True),
        (r'E-TRANSFER.*Paula Gour', 'Revenue - Oilfield Services', False, False),
        (r'E-TRANSFER.*Angela Henderson', 'Revenue - Oilfield Services', False, False),
        
        # ===== SHAREHOLDER DISTRIBUTIONS =====
        (r'INTERNET TRANSFER.*TO:.*00099.*78-83439', 'Shareholder Distribution', False, False),
        (r'E-TRANSFER.*Lilibeth Sejera', 'Shareholder Distribution', False, False),
        (r'ATM WITHDRAWAL|ABM WITHDRAWAL', 'Shareholder Distribution', False, False),
        (r'BRANCH.*WITHDRAWAL', 'Shareholder Distribution', False, False),
        
        # ===== LOANS =====
        (r'TD ON-LINE LOANS|LOAN PAYMENT.*TD', 'Loan Payment - Business Vehicle', False, False),
        (r'LOAN PAYMENT.*SCOTIA BANK|SCOTIA BANK.*LOAN', 'Loan Payment - Personal', True, False),
        
        # ===== REDWATER RENT - Business expense (where Greg & Lilibeth live for work) =====
        (r'rent@realtyfocus|rent@realtyexecutives|REALTYFOCUS', 'Rent - Commercial', False, False),
        
        # ===== BANK FEES =====
        (r'ACCOUNT FEE|SERVICE CHARGE|MONTHLY.*FEE|OVERDRAFT.*FEE|NSF|OVER LIMIT', 'Bank Charges & Interest', False, False),
        (r'OVERDRAFT INTEREST|INTEREST CHARGE', 'Bank Charges & Interest', False, False),
        
        # ===== GOVERNMENT =====
        (r'DEBIT MEMO.*GOVERNMENT|GPFS.*GOVERNMENT', 'GST Remittance', False, False),
        
        # ===== INSURANCE =====
        (r'MANULIFE', 'Insurance - Business', False, False),
        
        # ===== TELEPHONE =====
        (r'KOODO|TELUS|BELL|ROGERS|FIDO', 'Telephone & Communications', False, False),
        
        # ===== FUEL =====
        (r'PETRO-CANADA|PETRO CANADA|SHELL|ESSO|CHEVRON|CENTEX|MOBIL|DOMO GAS', 'Fuel & Petroleum', False, False),
        (r'FAS GA|FGP\d+', 'Fuel & Petroleum', False, False),
        (r'CO-OP.*BRIN|NC CO-OP|CIRCLE K', 'Fuel & Petroleum', False, False),
        (r'REDWATER ESSO|BRUDERHEIM ESSO', 'Fuel & Petroleum', False, False),
        
        # ===== VEHICLE REPAIRS =====
        (r'OK TIRE|NAPA|PART SOURCE|JIFFY LUBE', 'Vehicle Repairs & Maintenance', False, False),
        (r'CANADIAN TIRE', 'Vehicle Repairs & Maintenance', False, True),
        (r'REDWATER REGIST|REGISTRY', 'Vehicle Repairs & Maintenance', False, False),
        
        # ===== EQUIPMENT =====
        (r'PRINCESS AUTO', 'Equipment & Supplies', False, False),
        (r'HOME HARDWARE|WESTLOCK HOME|REDWATER HOME', 'Equipment & Supplies', False, False),
        (r'COSTCO BUSINESS', 'Equipment & Supplies', False, False),
        
        # ===== PROFESSIONAL FEES =====
        (r'NOTARY|LAWYER|LEGAL|ACCOUNTANT|CPA|BOOKKEEP', 'Professional Fees', False, False),
        (r'EDMONTON NOTARY', 'Professional Fees', False, False),
        (r'WORKERS COMP|WCB', 'Professional Fees', False, False),
        
        # ===== MEALS (50% ITC) =====
        (r'TIM HORTONS', 'Meals & Entertainment (50%)', False, False),
        (r'A&W |MCDONALD|WENDY|SUBWAY', 'Meals & Entertainment (50%)', False, False),
        (r'ACHTI.*STEAK|RAINBOW RESTAUR|UPTOWN PIZZA', 'Meals & Entertainment (50%)', False, False),
        (r'JOEY|DQ GRILL', 'Meals & Entertainment (50%)', False, False),
        
        # ===== PERSONAL - Shareholder Loan =====
        (r'LIQUOR|WINE RACK|BEER STORE', 'Shareholder Loan - Personal Expense', True, False),
        (r'CANNABIS|GREEN SOLUTION|KURVE CANNABIS|PLANTLIFE|THC|CANNA CABANA', 'Shareholder Loan - Personal Expense', True, False),
        (r'IKEA', 'Shareholder Loan - Personal Expense', True, False),
        (r'LITTLE STEPS|DAYCARE|CHILD CARE', 'Shareholder Loan - Personal Expense', True, False),
        (r'IGA|REDWATER IGA|GROCERY|SUPERMARKET|SAFEWAY|SUPERSTORE|T&T SUPERMARKET', 'Shareholder Loan - Personal Expense', True, False),
        (r'HOLDEN COLONY', 'Shareholder Loan - Personal Expense', True, False),
        (r'WALMART', 'Shareholder Loan - Personal Expense', True, True),
        (r'DOLLARAMA', 'Shareholder Loan - Personal Expense', True, True),
        (r'VALUE VILLAGE|GOODWILL|URBAN PLANET', 'Shareholder Loan - Personal Expense', True, False),
        (r'RED APPLE', 'Shareholder Loan - Personal Expense', True, False),
        (r'BARBER|SALON|NAILS|BROW BAR', 'Shareholder Loan - Personal Expense', True, False),
        (r'MANILA GRILL|JOLLIBEE|SEAFOOD CITY|KOKORIKO|PHO|GIGA.*PINOY', 'Shareholder Loan - Personal Expense', True, False),
        (r'BUFFET ROYALE|YANG MING|KHAN RESTAURANT', 'Shareholder Loan - Personal Expense', True, False),
        (r'AMAZON|TEMU|IHERB|ETSY', 'Shareholder Loan - Personal Expense', True, True),
        (r'SNOW VALLEY|KICKS SALOO|VENUE', 'Shareholder Loan - Personal Expense', True, False),
        
        # ===== TRANSFERS =====
        (r'E-TRANSFER|INTERNET TRANSFER', 'Transfer - Non-Taxable', False, True),
        (r'DEPOSIT', 'Transfer - Non-Taxable', False, True),
    ]
    
    def __init__(self):
        pass
    
    def classify_transaction(self, description: str, debit: float, credit: float) -> Dict:
        description_upper = description.upper()
        
        # Special handling for GOVERNMENT CANADA
        if 'GOVERNMENT CANADA' in description_upper:
            if credit > 0:
                return {
                    'cra_category': 'GST Refund',
                    'is_personal': False,
                    'needs_review': False,
                    'itc_amount': 0.0,
                    'notes': 'Government credit - GST refund or carbon rebate'
                }
            else:
                return {
                    'cra_category': 'Income Tax Installment',
                    'is_personal': False,
                    'needs_review': False,
                    'itc_amount': 0.0,
                    'notes': 'Tax installment'
                }
        
        for pattern, category, is_personal, needs_review in self.CLASSIFICATION_RULES:
            if re.search(pattern, description_upper, re.IGNORECASE):
                cat_info = self.CATEGORIES.get(category, {'itc_eligible': False, 'itc_rate': 0})
                
                itc_amount = 0.0
                if cat_info['itc_eligible'] and debit > 0 and not is_personal:
                    gst_in_purchase = debit * (self.GST_RATE / (1 + self.GST_RATE))
                    itc_amount = gst_in_purchase * cat_info['itc_rate']
                
                if debit >= 500 and category in ['Equipment & Supplies', 'Vehicle Repairs & Maintenance']:
                    needs_review = True
                
                return {
                    'cra_category': category,
                    'is_personal': is_personal,
                    'needs_review': needs_review,
                    'itc_amount': round(itc_amount, 2),
                    'notes': ''
                }
        
        if credit > 0:
            return {
                'cra_category': 'Revenue - Oilfield Services',
                'is_personal': False,
                'needs_review': True,
                'itc_amount': 0.0,
                'notes': 'Unclassified credit - review'
            }
        else:
            return {
                'cra_category': 'Other Expense',
                'is_personal': False,
                'needs_review': True,
                'itc_amount': round(debit * (self.GST_RATE / (1 + self.GST_RATE)), 2),
                'notes': 'Unclassified - review'
            }
    
    def classify_dataframe(self, df: pd.DataFrame, account_type: str = "corporate") -> pd.DataFrame:
        df = df.drop_duplicates(subset=["date", "description", "debit", "credit"], keep="first")
        df = df.copy()
        df['cra_category'] = ''
        df['is_personal'] = False
        df['needs_review'] = False
        df['itc_amount'] = 0.0
        df['notes'] = ''
        
        for idx, row in df.iterrows():
            result = self.classify_transaction(
                row['description'],
                row.get('debit', 0) or 0,
                row.get('credit', 0) or 0
            )
            df.at[idx, 'cra_category'] = result['cra_category']
            df.at[idx, 'is_personal'] = result['is_personal']
            df.at[idx, 'needs_review'] = result['needs_review']
            df.at[idx, 'itc_amount'] = result['itc_amount']
            df.at[idx, 'notes'] = result['notes']
        
        return df


class PersonalAccountClassifier:
    BUSINESS_PATTERNS = [
        (r'PETRO-CANADA|ESSO|SHELL|CHEVRON|FAS GA|FGP\d+', 'Fuel - Potential Business'),
        (r'NAPA|PART SOURCE|OK TIRE|JIFFY', 'Vehicle - Potential Business'),
        (r'HOME HARDWARE|PRINCESS AUTO', 'Supplies - Potential Business'),
    ]
    
    def identify_business_expenses(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['potential_business'] = False
        df['business_category'] = ''
        
        for idx, row in df.iterrows():
            desc = row['description'].upper()
            for pattern, category in self.BUSINESS_PATTERNS:
                if re.search(pattern, desc, re.IGNORECASE):
                    df.at[idx, 'potential_business'] = True
                    df.at[idx, 'business_category'] = category
                    break
        return df
