import os
import tempfile

os.environ["CLONARCH_DATA_DIR"] = tempfile.mkdtemp(prefix="clonarch-test-")
os.environ["CLONARCH_HOST"] = "192.168.105.10"
os.environ["CLONARCH_PORT"] = "8787"

from fastapi.testclient import TestClient

from clonarch.main import (Account, PlaidAccountLink, PlaidConnection, SessionLocal, Transaction,
                           app, allocate, sync_plaid_connection)


def test_allocation_keeps_every_cent():
    assert allocate(10_000, 3) == [3334, 3333, 3333]
    assert allocate(-10_000, 3) == [-3334, -3333, -3333]
    for amount in range(-100, 101):
        for months in range(1, 61):
            assert sum(allocate(amount, months)) == amount


def test_csv_import_is_preview_then_commit():
    from io import BytesIO

    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": context.headers["x-csrf-token"]}
        checking = next(a for a in client.get("/api/v1/accounts").json()["data"] if a["kind"] == "checking")
        before = len(client.get("/api/v1/transactions?month=2026-02").json()["data"])
        csv_bytes = b"date,amount,description\n2026-02-03,-25.50,Sample purchase\n"
        preview = client.post(f"/api/v1/imports/csv?account_id={checking['id']}",
                              headers=headers, files={"file": ("synthetic.csv", BytesIO(csv_bytes), "text/csv")})
        assert preview.status_code == 201, preview.text
        data = preview.json()["data"]
        assert data["candidate_count"] == 1 and data["error_count"] == 0
        assert data["sample"][0]["kind"] == "expense"
        assert len(client.get("/api/v1/transactions?month=2026-02").json()["data"]) == before
        committed = client.post(f"/api/v1/imports/{data['import_id']}/commit", headers=headers, json={})
        assert committed.status_code == 200 and committed.json()["data"]["created"] == 1
        duplicate = client.post(f"/api/v1/imports/csv?account_id={checking['id']}",
                                headers=headers, files={"file": ("synthetic.csv", BytesIO(csv_bytes), "text/csv")})
        assert duplicate.status_code == 409
        checking_csv = b"date,amount,description" + bytes([10]) + b"2026-02-04,2500.00,ACME PAYROLL" + bytes([10]) + b"2026-02-05,-500.00,CHASE AUTOPAY" + bytes([10])
        check_preview = client.post(f"/api/v1/imports/csv?account_id={checking['id']}",
                                    headers=headers, files={"file": ("checking.csv", BytesIO(checking_csv), "text/csv")})
        kinds = [r["kind"] for r in check_preview.json()["data"]["sample"]]
        assert kinds == ["income", "transfer"]


def test_plaid_is_disabled_without_private_credentials():
    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": context.headers["x-csrf-token"]}
        status = client.get("/api/v1/plaid/status").json()["data"]
        assert status["configured"] is False
        link = client.post("/api/v1/plaid/link-token", headers=headers, json={})
        assert link.status_code == 409


def test_plaid_sync_sign_dates_and_transfer_exclusion(monkeypatch):
    from decimal import Decimal
    from cryptography.fernet import Fernet
    from sqlalchemy import select

    key = Fernet.generate_key()
    fernet = Fernet(key)
    monkeypatch.setattr("clonarch.main.plaid_configuration", lambda: ({"environment": "production"}, fernet))
    with SessionLocal() as db:
        card = Account(name="Synthetic Plaid Card", owner="Household", kind="credit_card")
        checking = Account(name="Synthetic Plaid Checking", owner="Owner", kind="checking")
        db.add_all([card, checking])
        db.flush()
        connection = PlaidConnection(item_id="synthetic-item", access_token_encrypted=fernet.encrypt(b"synthetic-access-token").decode())
        db.add(connection)
        db.flush()
        db.add_all([
            PlaidAccountLink(connection_id=connection.id, external_account_id="synthetic-card", account_id=card.id, mask="1234"),
            PlaidAccountLink(connection_id=connection.id, external_account_id="synthetic-checking", account_id=checking.id, mask="5678"),
        ])
        db.commit()
        response = {"added": [
            {"transaction_id": "purchase-1", "account_id": "synthetic-card", "amount": Decimal("12.34"),
             "name": "GROCERY MARKET", "merchant_name": "Grocery Market", "date": "2026-10-05",
             "authorized_date": "2026-10-03", "pending": False},
            {"transaction_id": "payroll-1", "account_id": "synthetic-checking", "amount": Decimal("-1500.25"),
             "name": "ACME PAYROLL", "date": "2026-10-15", "pending": False},
            {"transaction_id": "card-payment-1", "account_id": "synthetic-card", "amount": Decimal("-100.00"),
             "name": "PAYMENT THANK YOU", "date": "2026-10-20", "pending": False},
            {"transaction_id": "checking-payment-1", "account_id": "synthetic-checking", "amount": Decimal("100.00"),
             "name": "CHASE AUTOPAY", "date": "2026-10-20", "pending": False},
        ], "modified": [], "removed": [], "next_cursor": "cursor-1", "has_more": False,
            "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE"}
        calls = []
        def fake_plaid_api(endpoint, payload):
            calls.append((endpoint, payload))
            return response
        monkeypatch.setattr("clonarch.main.plaid_api", fake_plaid_api)
        result = sync_plaid_connection(connection, db)
        assert result["added"] == 4 and result["update_status"] == "HISTORICAL_UPDATE_COMPLETE"
        rows = db.scalars(select(Transaction).where(Transaction.source == "plaid")).all()
        purchase = next(t for t in rows if t.description == "GROCERY MARKET")
        payroll = next(t for t in rows if t.description == "ACME PAYROLL")
        payments = [t for t in rows if "PAYMENT" in t.description or "AUTOPAY" in t.description]
        assert purchase.amount_minor == -1234 and purchase.purchase_date.isoformat() == "2026-10-03"
        assert purchase.posted_date.isoformat() == "2026-10-05" and purchase.kind == "expense"
        assert payroll.amount_minor == 150025 and payroll.kind == "income"
        assert all(t.kind == "transfer" for t in payments)
        assert connection.cursor == "cursor-1"
        assert calls[0][0] == "transactions/sync"
        assert calls[0][1]["access_token"] == "synthetic-access-token"


def test_monthly_ledger_and_csrf():
    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        assert context.status_code == 200
        csrf = context.headers["x-csrf-token"]
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": csrf}
        accounts = client.get("/api/v1/accounts").json()["data"]
        categories = client.get("/api/v1/categories").json()["data"]
        checking = next(a for a in accounts if a["kind"] == "checking")
        groceries = next(c for c in categories if c["name"] == "Groceries")
        purchase = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": checking["id"], "amount_minor": -120_000,
            "purchase_date": "2026-01-12", "description": "Annual premium",
            "kind": "expense", "category_id": groceries["id"], "spend_type": "regular"
        })
        assert purchase.status_code == 201, purchase.text
        paycheck = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": checking["id"], "amount_minor": 600_000,
            "purchase_date": "2026-01-15", "posted_date": "2026-01-15",
            "description": "Payroll", "kind": "income"
        })
        assert paycheck.status_code == 201, paycheck.text
        allocation = client.put(f"/api/v1/transactions/{purchase.json()['data']['id']}/allocation",
                                headers=headers, json={"start_month": "2026-01", "end_month_exclusive": "2027-01"})
        assert allocation.status_code == 200, allocation.text
        report = client.get("/api/v1/reports/monthly?month=2026-01&basis=normalized").json()["data"]
        assert report["actual"]["regular_minor"] == 120_000
        assert report["normalized"]["regular_minor"] == 10_000
        assert report["actual"]["income_minor"] == 600_000
        assert report["actual"]["recorded_surplus_minor"] == 480_000
        assert client.post("/api/v1/rules/apply", json={}).status_code == 403
