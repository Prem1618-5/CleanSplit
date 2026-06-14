import os
import json
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./smoke_cleansplit.db"
os.environ["SECRET_KEY"] = "smoke-secret"

db_path = Path("smoke_cleansplit.db")
if db_path.exists():
    db_path.unlink()

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def assert_ok(resp, label):
    if resp.status_code >= 400:
        raise AssertionError(f"{label}: {resp.status_code} {resp.text}")
    return resp.json()


def register(name):
    return assert_ok(
        client.post(
            "/api/auth/register",
            data={"name": name, "email": f"{name.lower()}@example.com", "password": "password123"},
        ),
        f"register {name}",
    )


users = {name: register(name) for name in ["Aisha", "Rohan", "Priya", "Meera", "Sam", "Dev"]}
headers = {"Authorization": f"Bearer {users['Aisha']['access_token']}"}

group = assert_ok(
    client.post("/api/groups", data={"name": "Flat 4B", "usd_inr_rate": "85"}, headers=headers),
    "create group",
)
group_id = group["id"]

for name in ["Rohan", "Priya", "Meera", "Sam", "Dev"]:
    joined = "2026-04-08" if name == "Sam" else "2026-02-01"
    assert_ok(
        client.post(
            f"/api/groups/{group_id}/members",
            data={"user_email": f"{name.lower()}@example.com", "joined_at": joined},
            headers=headers,
        ),
        f"add member {name}",
    )

meera_id = users["Meera"]["user"]["id"]
assert_ok(
    client.patch(f"/api/groups/{group_id}/members/{meera_id}", data={"left_at": "2026-03-31"}, headers=headers),
    "mark Meera left",
)

expense = assert_ok(
    client.post(
        f"/api/groups/{group_id}/expenses",
        data={
            "description": "Smoke groceries",
            "amount": "1200",
            "currency": "INR",
            "paid_by_user_id": str(users["Aisha"]["user"]["id"]),
            "split_type": "equal",
            "expense_date": "2026-04-20",
            "split_members": json.dumps({
                users["Aisha"]["user"]["id"]: 1,
                users["Rohan"]["user"]["id"]: 1,
                users["Priya"]["user"]["id"]: 1,
                users["Sam"]["user"]["id"]: 1,
            }),
        },
        headers=headers,
    ),
    "create expense",
)

csv_path = Path(__file__).resolve().parents[3] / "Assignment Files" / "expenses_export.csv"
with csv_path.open("rb") as fh:
    upload = assert_ok(
        client.post(
            "/api/import/upload",
            data={"group_id": str(group_id), "usd_inr_rate": "85"},
            files={"file": ("expenses_export.csv", fh, "text/csv")},
            headers=headers,
        ),
        "upload csv",
    )

session_id = upload["session_id"]
rows_resp = assert_ok(client.get(f"/api/import/{session_id}/rows", headers=headers), "get import rows")
rows = rows_resp["rows"]
anomaly_types = {
    anomaly["type"]
    for row in rows
    for anomaly in row["anomalies"]
}
expected_anomalies = {
    "AMOUNT_WHITESPACE",
    "DUPLICATE_EXACT",
    "DUPLICATE_SIMILAR",
    "NAME_VARIANT_SUFFIX",
    "SETTLEMENT",
}
missing_anomalies = expected_anomalies - anomaly_types
if missing_anomalies:
    raise AssertionError(f"missing expected anomalies: {sorted(missing_anomalies)}")

report_download = client.get(f"/api/import/{session_id}/report.md", headers=headers)
if report_download.status_code != 200 or "## Row-Level Actions" not in report_download.text:
    raise AssertionError("downloadable import report was not generated")

pending = [r for r in rows if r["status"] == "needs_review"]

for row in pending:
    assert_ok(
        client.patch(
            f"/api/import/{session_id}/rows/{row['id']}",
            data={"new_status": "approved"},
            headers=headers,
        ),
        f"approve row {row['row_number']}",
    )

commit = assert_ok(client.post(f"/api/import/{session_id}/commit", headers=headers), "commit import")
if commit["settlements_created"] != 2:
    raise AssertionError(f"expected 2 settlements, got {commit['settlements_created']}")
balances = assert_ok(client.get(f"/api/groups/{group_id}/balances", headers=headers), "balances")
breakdown = assert_ok(
    client.get(f"/api/groups/{group_id}/balances/{users['Rohan']['user']['id']}", headers=headers),
    "Rohan breakdown",
)

print({
    "manual_expense_id": expense["id"],
    "import_session": session_id,
    "uploaded_rows": len(rows),
    "approved_review_rows": len(pending),
    "anomaly_types": sorted(anomaly_types),
    "commit": commit,
    "balance_members": list(balances["members"].keys()),
    "settlement_transactions": len(balances["transactions"]),
    "rohan_breakdown_rows": len(breakdown["breakdown"]),
})
