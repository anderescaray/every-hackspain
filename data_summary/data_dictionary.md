# HackSpain X-Ray Track — Data Dictionary

This is a **synthetic dataset**: 1,286 companies across 250 business groups, with 24 months
of financial history (**2024-09-01 to 2026-09-01**). It was generated from the statistical
distribution of real SME treasury data (bank accounts, financing, transactions, invoices), so
volumes, seasonality, counterparty patterns and financing terms behave like the real thing.
No row corresponds to an actual company, bank account or person.

All IDs (`company_id`, `group_id`, `product_id`, `counterparty_id`) are stable within the
dataset: the same entity always has the same ID in every file.

## groups.csv (250 rows)
One row per business group. A group can be a holding with several subsidiaries, so group
size ranges from 1 to 24 companies (median 2).

| column | description |
|---|---|
| group_id | Group ID |
| erp | ERP system used by the group, if any (e.g. `businesscentral`, `netsuite`, `sap`) |
| n_companies_in_sample | Number of companies from this group included in the dataset (1-24) |

## companies.csv (1,286 rows)
| column | description |
|---|---|
| company_id | Company ID — the primary key used across every other file |
| group_id | Parent group ID |
| country | ISO country code, when known (often missing) |
| currency | Company currency |
| erp | ERP system, if any |
| created_at | When the company was onboarded onto the platform |

## banking_products.csv (5,987 rows) / debt_products.csv (2,239 rows)
Bank accounts and financing facilities. Split by `type`:
- **banking_products**: checking, card, investment, tpv, saving, expensesPlatform
- **debt_products**: loan, leasing, lineofcredit, mortgage, renting, factoring, confirming, guarantee

| column | description |
|---|---|
| product_id | Product/account ID |
| company_id | Owning company |
| label | Human-readable label, e.g. `LOAN_01`, `CHECKING_02` |
| type | Product type (see above) |
| bank_name | Bank name (e.g. "BBVA", "Banco Santander"). `Other (customer-defined)` for products that are not linked to a bank connection (intercompany loans, shareholder loans, prepaid cards, "other" accounts) |
| service | Bank service code; `custom` for the customer-defined products above |
| currency | Product currency |
| created_at | When the product was connected |
| granted / outstanding / liquidity | *(debt_products only)* `granted` = original facility amount, `outstanding` = current balance owed, `liquidity` = available amount when reported |

## debt_schedule_config.csv (87 rows)
Loan terms for the debt products that have a formal amortization schedule (mostly `loan`
and `leasing`). One row per debt product.

| column | description |
|---|---|
| product_id, company_id | Keys |
| settlement_product_id | Settlement bank account (a `product_id`) |
| amortization_type, interest_calc_method, amortising_frequency, interest_type | Loan terms (e.g. `constant quote`, `30/360`, `monthly`, `fixed`/`variable`) |
| granted_balance | Original principal |
| outstanding_balance | Remaining principal as of extraction |
| total_periods | Total number of installments in the schedule |
| next_payment_date, last_payment_date | Loan-level dates |
| annual_interest_rate_or_spread | Current/latest rate |

## transactions.csv (2,556,437 rows)
Bank transactions, 2024-09-01 to 2026-09-01.

| column | description |
|---|---|
| transaction_id | Transaction ID |
| company_id, product_id | Keys (product = which bank account) |
| date, value_date | Booking / value date |
| amount | Amount (negative = outgoing, positive = incoming) |
| exchange_rate | Exchange rate applied to the transaction |
| status | `booked`, `pending`, etc. |
| accounting_status | Reconciliation status, when available |
| category | Auto-assigned category (e.g. `utility`, `tax`, `collection`) |
| description | Bank transaction narrative. Names, identifiers and rare words are replaced by placeholders (see *Placeholders* below) |
| counterparty_id | Counterparty (same counterparty ⇒ same ID everywhere). Blank when the transaction has no resolved counterparty |

## invoices.csv (897,894 rows)
ERP-sourced invoices (synced in from the company's ERP).

| column | description |
|---|---|
| operation_id | Invoice/document ID |
| company_id | Key |
| document_type | e.g. `invoice`, `credit_note` |
| issuance_date, due_date, payment_date | Invoice lifecycle dates |
| amount, pending_amount | Amounts (pending_amount = 0 once fully paid) |
| status | e.g. `paid`, `pending` |
| currency | Invoice currency |
| accounting_currency | Accounting currency of the invoice |
| exchange_rate | Exchange rate applied to the invoice |
| concept | Free-text invoice line/concept (e.g. `"Factura FC2024-00819. [X] Suscripción"`). Same placeholders as `transactions.description` |
| counterparty_id | Supplier/customer — same ID space as transactions.csv's `counterparty_id` |

## balances.csv (7,996 rows)
Balances as of 2026-09-01, one row per product.

| column | description |
|---|---|
| product_id, company_id | Keys |
| date | Always 2026-09-01 (or the closest prior day with a recorded snapshot) |
| balance | Ledger balance on that date |
| available, granted, liquidity, countable | Balance breakdowns, when populated by the bank/provider (often null depending on account type) |

## Placeholders
The free-text fields (`transactions.description`, `invoices.concept`) contain these tokens
in place of the original text:

| token | stands for |
|---|---|
| `COUNTERPARTY_xxxxx` | A counterparty (same ID as in `counterparty_id`) |
| `[COMPANY]` | A company name |
| `[PERSON]`, `[NAME]` | A person or payer/payee name |
| `[IBAN]`, `[ACCOUNT]`, `[CARD]` | Bank account or card identifiers |
| `[TAXID]`, `[EMAIL]`, `[PHONE]`, `[URL]`, `[ADDRESS]` | Other identifiers |
| `[REF]`, `[NUM]` | Long alphanumeric references / long digit sequences |
| `[X]` | Any other uncommon word |
