# every.hackspain

Synthetic treasury dataset for the **HackSpain X-Ray Track**.

## What's in this repo

This repository contains a **sample dataset** under `data_summary/` — small CSV extracts (about 10 rows per table) so you can inspect schemas, relationships, and column formats without downloading gigabytes of data.

| File | Sample rows | Full dataset rows |
|---|---:|---:|
| `groups.csv` | 33 | 250 |
| `companies.csv` | 10 | 1,286 |
| `banking_products.csv` | 10 | 5,987 |
| `debt_products.csv` | 10 | 2,239 |
| `balances.csv` | 10 | 7,997 |
| `debt_schedule_config.csv` | 10 | 88 |
| `invoices.csv` | 13 | 898,889 |
| `transactions.csv` | 10 | 2,630,949 |

See [`data_summary/data_dictionary.md`](data_summary/data_dictionary.md) for column definitions and entity relationships.

## Why the full dataset is not here

The complete dataset lives locally in `data/` (~615 MB). Two files exceed [GitHub's 100 MB file limit](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files):

- `transactions.csv` — ~450 MB
- `invoices.csv` — ~165 MB

For that reason, `data/` is listed in `.gitignore` and is **not** pushed to this repository.

## Getting the full dataset

Contact the HackSpain organizers or your track lead to obtain the full `data/` folder. Once you have it, place it at the repo root:

```
every.hackspain/
├── data/           ← full dataset (local only, gitignored)
├── data_summary/   ← sample extracts (in git)
└── README.md
```

## Dataset overview

- **1,286 companies** across **250 business groups**
- **24 months** of financial history (2024-09-01 → 2026-09-01)
- Synthetic data generated from the statistical distribution of real SME treasury patterns
- Stable IDs across all files (`company_id`, `group_id`, `product_id`, `counterparty_id`)
