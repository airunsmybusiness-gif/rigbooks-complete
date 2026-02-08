"""Simple revenue calculator - no complex logic"""

def calculate_revenue(df):
    """
    Calculate revenue from bank statement
    Returns: dict with wire_transfers, mobile_deposits, branch_deposits, total
    """
    
    # Wire transfers (Long Run/PWC)
    wire_mask = (df['credit'] > 0) & df['description'].str.contains('WIRE TSF', case=False, na=False)
    wire_df = df[wire_mask].copy()
    wire_total = wire_df['credit'].sum()
    
    # Mobile deposits
    mobile_mask = (df['credit'] > 0) & df['description'].str.contains('MOBILE DEPOSIT', case=False, na=False)
    mobile_df = df[mobile_mask].copy()
    mobile_total = mobile_df['credit'].sum()
    
    # Branch deposits
    branch_mask = (df['credit'] > 0) & df['description'].str.contains('DEPOSIT.*BANKING CENTRE', case=False, na=False, regex=True)
    branch_df = df[branch_mask].copy()
    branch_total = branch_df['credit'].sum()
    
    return {
        'wire_transfers': wire_df,
        'wire_total': wire_total,
        'mobile_deposits': mobile_df,
        'mobile_total': mobile_total,
        'branch_deposits': branch_df,
        'branch_total': branch_total,
        'total': wire_total + mobile_total + branch_total
    }
