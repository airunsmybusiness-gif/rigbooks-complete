"""T5 Generator for Cape Bretoner's Oilfield"""
import pandas as pd

class T5Generator:
    def __init__(self):
        self.payer_name = "CAPE BRETONER'S OILFIELD SERVICES LTD."
        self.business_number = "825303795RC0001"
    
    def generate_t5(self, total_dividends):
        greg_amt = total_dividends * 0.51
        lili_amt = total_dividends * 0.49
        
        greg_grossup = greg_amt * 0.38
        lili_grossup = lili_amt * 0.38
        
        data = [
            {'name': 'Gregory MacDonald', 'ownership': '51%', 'actual_dividend': greg_amt, 
             'grossup': greg_grossup, 'taxable': greg_amt + greg_grossup},
            {'name': 'Lilibeth Sejera', 'ownership': '49%', 'actual_dividend': lili_amt,
             'grossup': lili_grossup, 'taxable': lili_amt + lili_grossup}
        ]
        return pd.DataFrame(data)
