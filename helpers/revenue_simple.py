"""
Revenue calculation helper for RigBooks
Cape Bretoner's Oilfield Services Ltd

FIXED: Wire transfers now counted ONCE using only "WIRE TSF" keyword
"""

import pandas as pd


def calculate_revenue(df):
    """Calculate revenue from bank transactions."""
    
    df = df.copy()
    
    # WIRE TRANSFERS - Only "WIRE TSF" keyword, no customer names
    wire_mask = (
        (df['credit'] > 0) & 
        df['description'].str.contains('WIRE TSF', case=False, na=False)
    )
    wire_df = df[wire_mask].drop_duplicates()
    wire_total = wire_df['credit'].sum()
    wire_count = len(wire_df)
    
    # MOBILE DEPOSITS
    mobile_mask = (
        (df['credit'] > 0) & 
        df['description'].str.contains('MOBILE DEPOSIT', case=False, na=False)
    )
    mobile_df = df[mobile_mask].drop_duplicates()
    mobile_total = mobile_df['credit'].sum()
    mobile_count = len(mobile_df)
    
    # BRANCH/COUNTER DEPOSITS
    branch_mask = (
        (df['credit'] > 0) & 
        (
            df['description'].str.contains('BRANCH DEPOSIT', case=False, na=False) |
            df['description'].str.contains('COUNTER DEPOSIT', case=False, na=False) |
            df['description'].str.contains('DEPOSIT IN BRANCH', case=False, na=False)
        )
    )
    branch_df = df[branch_mask].drop_duplicates()
    branch_total = branch_df['credit'].sum()
    branch_count = len(branch_df)
    
    # TOTAL
    total = wire_total + mobile_total + branch_total
    
    return {
        # Totals (numeric)
        'wire_total': wire_total,
        'mobile_total': mobile_total,
        'branch_total': branch_total,
        'total': total,
        'total_revenue': total,
        
        # Counts
        'wire_count': wire_count,
        'mobile_count': mobile_count,
        'branch_count': branch_count,
        'total_transactions': wire_count + mobile_count + branch_count,
        
        # DataFrames (for pd.concat and display)
        'wire_df': wire_df,
        'mobile_df': mobile_df,
        'branch_df': branch_df,
        'wire_transfers': wire_df,
        'mobile_deposits': mobile_df,
        'branch_deposits': branch_df,
    }
