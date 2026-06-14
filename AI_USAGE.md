# AI_USAGE.md - AI Usage Log

I used AI as a development assistant, but I stayed responsible for the design decisions and
final code. The most useful role for AI was producing first drafts quickly; the risky part
was that some drafts looked correct while missing integration details.

## Tools Used

- ChatGPT/Codex: repository editing, debugging, command-line verification, and documentation
  cleanup.
- Claude-style prompting: architecture and importer first drafts.

I am not claiming the AI wrote a finished product. I used it closer to a pair programmer:
ask for a draft, run it, inspect the result, then change what was wrong.

## Key Prompts

### 1. Product And Architecture Prompt

> Build a shared expenses app for the flatmate CSV assignment. The app needs login,
> groups with membership dates, expenses, split types from the CSV, settlements, USD to
> INR conversion, balances, and an importer that stages anomalies before commit.
> Use FastAPI, SQLite, SQLAlchemy, React, and TypeScript.

### 2. Importer Prompt

> Write an importer for the provided expenses CSV. It must detect duplicate rows, amount
> formatting issues, zero and negative amounts, DD/MM dates, ambiguous dates, missing
> payer/currency, name variants, non-members, departed members, settlements, percentage
> totals that do not equal 100, and split-type conflicts. Return raw data, parsed data,
> status, and anomaly objects for each row.

### 3. Balance Prompt

> Implement group balance calculation from expense splits and settlements. Return a
> minimum transaction settlement plan and a per-member breakdown showing each expense's
> paid amount, share amount, and net effect.

### 4. UI Prompt

> Build an import review page where each CSV row shows original data, parsed data,
> anomaly badges, approve/reject actions, and a commit button that only appears after
> all review rows have been decided.

### 5. Documentation Prompt

> Draft README.md, SCOPE.md, DECISIONS.md, IMPORT_REPORT.md, and AI_USAGE.md for the
> assignment. Make sure the anomaly policy and database schema are explained in a way
> I can defend in a live review.

## Where AI Was Wrong And What I Changed

### Case 1 - JWT `sub` Was Generated As An Integer

AI-generated code used:

```python
token = create_access_token({"sub": user.id})
```

Problem: `python-jose` expects the JWT subject to be a string. Authenticated endpoints
returned 401 even though login appeared to work.

How I caught it: I ran the backend flow and decoded the token error. The failure was not in
the route permissions; it was in token validation.

Fix:

```python
token = create_access_token({"sub": str(user.id)})
user_id = int(payload.get("sub"))
```

### Case 2 - Duplicate Detection Missed Real Duplicate Dinners

AI-generated logic compared normalised strings exactly. That missed:

- `Dinner at Marina Bites`
- `dinner - marina bites`

It also missed:

- `Dinner at Thalassa`
- `Thalassa dinner`

How I caught it: I generated the import report and saw that duplicate anomaly counts were
zero even though the CSV clearly had duplicate-looking rows.

Fix: I changed duplicate detection to word-set Jaccard similarity with same-date and
amount/payer checks.

### Case 3 - Amount Whitespace Was Documented But Not Actually Detected

The docs said the app detected `" 1450 "`, but an earlier parser version stripped all CSV
fields before calling the amount parser.

How I caught it: I regenerated `IMPORT_REPORT.md` and checked whether `AMOUNT_WHITESPACE`
appeared. It did not.

Fix: I changed `parse_csv` to preserve raw CSV values and let each parser record anomalies
before normalising.

### Case 4 - Settlement Import Only Handled One Sentence Pattern

The first settlement commit code handled `Rohan paid Aisha back`, but not `Sam deposit share`
because that row does not follow the same text pattern.

How I caught it: the smoke test committed only one settlement even though the report found
two settlement rows.

Fix: I added a fallback for settlement rows with exactly one `split_with` receiver. The
smoke test now expects two settlements.

### Case 5 - Test Dependency Was Missing

The backend smoke test used FastAPI's `TestClient`, but `httpx` was not in
`backend/requirements.txt`.

How I caught it: running `python smoke_check.py` failed before hitting app code.

Fix: I added `httpx==0.27.2` to backend requirements and reran the smoke test.

## What I Did Not Let AI Decide Alone

- Whether negative amounts should be rejected or treated as refunds.
- Whether settlement-looking rows should become settlements.
- Whether departed members should be removed from later splits.
- Whether ambiguous dates should default to DD/MM/YYYY.
- Which files should be included in the final repository.

Those are product decisions, not just coding decisions, so I documented them in
`DECISIONS.md`.
