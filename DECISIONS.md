# DECISIONS.md - Decision Log

This is the decision log I would use in the live discussion to explain why the app behaves
the way it does. I focused on decisions that affect correctness, reviewability, or the
assignment requirements.

## D1 - SQLite As The Relational Database

Question: which database should I use?

Options considered:

- PostgreSQL: more production-ready and better for concurrent writes.
- SQLite: relational, file-based, simple to run locally, and enough for this dataset.

Decision: use SQLite through SQLAlchemy.

Reason: the assignment requires a relational DB, not necessarily a server database. For a
flatmate expense app with a small number of users, SQLite keeps setup simple and still gives
proper tables and relationships. I kept `DATABASE_URL` configurable so the backend can move
to Postgres later without rewriting the app logic.

## D2 - Stage CSV Rows Before Writing Expenses

Question: should the importer write expenses immediately?

Options considered:

- Write valid rows immediately and skip bad rows.
- Stage every row in `import_rows`, show anomalies, then commit after review.

Decision: stage first, commit later.

Reason: the assignment says a crashed import and a silent guess are both failing answers.
Meera also explicitly wants to approve anything deleted or changed. Staging makes the app's
decision visible before it affects balances.

## D3 - Store Original Currency And INR Split Amounts

Question: how should USD expenses affect balances?

Options considered:

- Convert everything to INR and only store INR.
- Store original amount/currency plus the INR amount used for balance calculation.

Decision: store both.

Reason: Priya's complaint is about the sheet pretending dollars and rupees are the same.
The app needs INR values for one balance number, but it also needs to show the original USD
amount and the rate used. That is why `expenses.usd_inr_rate_used` exists.

## D4 - Use Word-Set Similarity For Duplicates

Question: how should the importer detect duplicate descriptions?

Options considered:

- Exact string comparison after lowercasing.
- Word-set Jaccard similarity with same-date and amount checks.

Decision: use word-set similarity.

Reason: exact matching misses `Dinner at Marina Bites` vs `dinner - marina bites` and
`Dinner at Thalassa` vs `Thalassa dinner`. Word sets catch both while the date/amount/payer
conditions reduce false positives.

## D5 - Treat Negative Amount As Refund

Question: is `-30 USD` an error?

Options considered:

- Reject negative amounts.
- Treat negative amounts as refunds.

Decision: treat this row as a refund.

Reason: the description says parasailing refund. Rejecting it would make the balance less
accurate. The app stores negative split values so the balance math naturally reverses the
original charge.

## D6 - Normalise Bad Percentage Totals

Question: what should happen when percentages total 110%?

Options considered:

- Reject the row.
- Normalise the percentages and show the correction.

Decision: normalise and log it.

Reason: the relative split intent is still clear. Normalising preserves that intent while
making the row mathematically valid. The app still surfaces the anomaly so the reviewer can
reject it if they disagree.

## D7 - Import Settlements As Settlements, Not Expenses

Question: how should rows like `Rohan paid Aisha back` be stored?

Options considered:

- Import them as normal expenses.
- Skip them.
- Convert them into settlement records after review.

Decision: convert to settlements after review.

Reason: a repayment changes balances differently from a new expense. Storing it as a
settlement keeps the model honest and makes the balances explainable.

## D8 - Enforce Membership Dates During Import

Question: should someone who moved out still be included in later expenses?

Options considered:

- Preserve the CSV exactly.
- Block the row.
- Remove the inactive member and log the correction.

Decision: remove the inactive member and log it.

Reason: the product requirement says Sam should not be affected by March expenses. The same
logic applies to Meera after she moved out. The app logs the correction so it is not hidden.

## D9 - Default Ambiguous Dates To DD/MM/YYYY

Question: how should `04/05/2026` be read?

Options considered:

- MM/DD/YYYY.
- DD/MM/YYYY.
- Block as unresolvable.

Decision: default to DD/MM/YYYY and show the alternate.

Reason: the surrounding CSV section uses DD/MM/YYYY, including unambiguous dates like
`28/03/2026`. Blocking every ambiguous date would slow the import, but silently choosing
would be risky. The app chooses DD/MM and logs the alternate interpretation.

## D10 - Minimum Settlement Plan Plus Breakdown

Question: what balance view should users see?

Options considered:

- Show only all pairwise balances.
- Show a minimum settlement plan.
- Show minimum settlement plan plus per-member breakdown.

Decision: show both minimum settlement and audit breakdown.

Reason: Aisha wants a simple who-pays-whom answer. Rohan wants to trace the calculation.
The minimum settlement plan solves Aisha's use case, and the member breakdown solves
Rohan's use case.

## D11 - Check In A Generated Import Report

Question: should `IMPORT_REPORT.md` be manually written or generated?

Options considered:

- Write the report by hand from the CSV.
- Generate it from the same importer code used by the app.

Decision: generate it with `backend/generate_import_report.py`.

Reason: the assignment asks for an import report produced by the app. A generated report is
more defensible because the anomaly list comes from the parser, not from a separate manual
document that can drift from the code.
