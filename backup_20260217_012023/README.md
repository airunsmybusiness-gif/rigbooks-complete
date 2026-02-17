# RigBooks - CRA-Compliant Corporate Tax & Accounting System

Cape Bretoner's Oilfield Services Ltd.

## Features
✅ Multi-year fiscal period tracking (2024-2025, 2025-2026, etc.)
✅ Bank statement upload & automatic transaction classification
✅ Cash expense tracking with CRA receipt rules
✅ Dual phone bill deductions (Greg 51%, Lilibeth 49%)
✅ GST/HST filing with transparent ITC calculations
✅ T5 slip generation for shareholders
✅ Shareholder loan tracking
✅ Audit-proof documentation
✅ Complete data persistence

## Data Storage
All data saved in `data/[fiscal-year]/` folders:
- Bank statements (corporate_df.pkl)
- Classified transactions (classified_df.pkl)
- Cash expenses (cash_expenses.json)
- Phone bills (phone_bill.json)

## CRA Compliance
- Receipt tracking by amount ($30, $150 thresholds)
- Transparent GST calculations
- T5 slip generation with gross-up and tax credits
- Shareholder loan tracking for CRA deadlines
