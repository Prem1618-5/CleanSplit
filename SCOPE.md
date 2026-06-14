# SCOPE.md - Anomaly Log And Database Schema

This file explains the data problems I found in `expenses_export.csv`, how the importer
handles them, and the relational schema behind the app. I treated this as both a product
and engineering problem: a silent guess is bad, but blocking every row is also not useful.

## Database Schema

```sql
users (
  id, name, email, password_hash, created_at
)

groups (
  id, name, created_by, usd_inr_rate, created_at
)

group_members (
  id, group_id, user_id, joined_at, left_at
)

expenses (
  id, group_id, description, amount, currency, paid_by_user_id,
  split_type, expense_date, notes, is_deleted, import_session_id,
  usd_inr_rate_used, created_at
)

expense_splits (
  id, expense_id, user_id, amount_inr, original_amount,
  share_count, percentage
)

settlements (
  id, group_id, payer_id, receiver_id, amount, currency,
  settlement_date, notes, created_at
)

import_sessions (
  id, group_id, filename, status, usd_inr_rate, created_by, created_at
)

import_rows (
  id, session_id, row_number, raw_data, parsed_data,
  status, anomalies, expense_id
)
```

Important schema choices:

- `expense_splits.amount_inr` is always stored in INR so balance reads are direct.
- `expenses.amount` keeps the original amount and `expenses.currency` keeps the original
  currency for display and audit.
- `expenses.usd_inr_rate_used` stores the conversion rate used for that import/manual
  expense, so old USD expenses are not silently recalculated later.
- `import_rows.raw_data` stores the original CSV row and `import_rows.parsed_data` stores
  the app's proposed cleaned version.
- `import_rows.anomalies` stores the exact problems and actions shown in the review UI
  and in `IMPORT_REPORT.md`.

## Import Status Policy

- `clean`: no anomaly found.
- `auto_fixed`: the importer made a low-risk correction and logs it.
- `needs_review`: a human must approve or reject before commit.
- `rejected`: the row is skipped during commit unless the reviewer changes it.
- `approved`: reviewer explicitly accepted the row.

## Anomalies Detected

The generated `IMPORT_REPORT.md` currently shows 18 anomaly types across 42 CSV rows.

### 1. `DUPLICATE_EXACT`

Rows 5 and 6 are the Marina Bites dinner entered twice with the same date, payer, and
amount. The descriptions differ only in wording/case.

Policy: mark both rows with an error. The earlier row defaults to review/approve, and the
later row defaults to reject. The reviewer can override.

### 2. `DUPLICATE_SIMILAR`

Rows 24 and 25 are both Thalassa dinner on the same date, but one says Aisha paid 2400
and the other says Rohan paid 2450.

Policy: do not guess a winner. Both rows need review because the payer and amount conflict.

### 3. `AMOUNT_COMMA`

Row 7 has amount `"1,200"`.

Policy: remove the comma and parse it as `1200`.

### 4. `AMOUNT_WHITESPACE`

Row 29 has amount `" 1450 "`.

Policy: preserve the raw value in the anomaly log, strip whitespace for parsing, and import
the amount as `1450`.

### 5. `AMOUNT_ZERO`

Row 31 is a Swiggy dinner with amount `0`.

Policy: reject by default. A zero expense does not affect balances and the note suggests it
was related to fixing a previous entry.

### 6. `AMOUNT_NEGATIVE`

Row 26 is a `-30 USD` parasailing refund.

Policy: keep it as a refund. The expense amount and split shares are stored negative so the
balance calculation reverses the original cost.

### 7. `DATE_FORMAT_EU`

Several rows use `DD/MM/YYYY` instead of ISO dates, for example `15/03/2026`.

Policy: convert to ISO format when the date is unambiguous.

### 8. `DATE_AMBIGUOUS`

Dates like `01/03/2026` and `04/05/2026` can be read more than one way.

Policy: default to `DD/MM/YYYY` because the surrounding section uses that format, and show
the alternate interpretation in the anomaly message.

### 9. `DATE_NO_YEAR`

Row 27 says `Mar 14`.

Policy: infer year `2026` from the rest of the CSV and log that assumption.

### 10. `MISSING_CURRENCY`

Row 28 has an empty currency field.

Policy: default to INR because it is a domestic groceries row and the note says the currency
was forgotten, not unknown.

### 11. `MISSING_PAID_BY`

Row 13 has no payer.

Policy: require review. The app cannot calculate who fronted the money without a payer.

### 12. `NAME_VARIANT_CASE`

The CSV contains `priya` and `rohan `.

Policy: normalise to `Priya` and `Rohan`, while keeping the original value in the report.

### 13. `NAME_VARIANT_SUFFIX`

Row 11 uses `Priya S`.

Policy: map to `Priya`, but mark as warning because a surname initial is more ambiguous
than case or whitespace.

### 14. `NON_MEMBER`

Row 23 includes `Dev's friend Kabir`.

Policy: remove Kabir from the group split because he is not a tracked group member. Any
private settlement with Dev is outside this group's balances.

### 15. `DEPARTED_MEMBER`

Row 36 includes Meera after her `2026-03-31` leave date.

Policy: remove Meera from the split. This matches Sam and Meera's fairness requirement:
membership dates must affect balances.

### 16. `PERCENTAGE_SUM`

Rows 15 and 32 have percentages adding to 110%.

Policy: normalise by dividing each percentage by the actual total. This preserves the
relative intended proportions and logs the corrected percentages.

### 17. `SETTLEMENT`

Rows 14 and 38 look like payments/settlements, not shared expenses.

Policy: require review, then import them as `settlements` instead of `expenses` when
approved. The backend supports both `Rohan paid Aisha back` and `Sam deposit share`.

### 18. `SPLIT_TYPE_CONFLICT`

Row 42 says `split_type=equal` but also includes `Aisha 1; Rohan 1; Priya 1; Sam 1`.

Policy: treat it as equal because the details are mathematically the same as an equal split.

## Split Types Supported

| Type | How it works |
|---|---|
| `equal` | Amount divided across all selected members |
| `unequal` | Explicit per-person amounts |
| `percentage` | Percentage values, normalised if they do not total 100 |
| `share` | Weighted shares such as `1:2:1:2` |

## Membership Assumptions Used For The CSV

| Member | Joined | Left |
|---|---|---|
| Aisha | 2026-02-01 | Active |
| Rohan | 2026-02-01 | Active |
| Priya | 2026-02-01 | Active |
| Meera | 2026-02-01 | 2026-03-31 |
| Dev | 2026-02-01 for trip/group import purposes | Active/guest |
| Sam | 2026-04-08 | Active |
