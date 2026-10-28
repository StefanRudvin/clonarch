import os
import tempfile

os.environ["CLONARCH_DATA_DIR"] = tempfile.mkdtemp(prefix="clonarch-test-")
os.environ["CLONARCH_HOST"] = "192.168.105.10"
os.environ["CLONARCH_PORT"] = "8787"

from fastapi.testclient import TestClient

from clonarch.main import (Account, PlaidAccountLink, PlaidConnection, Rule, SessionLocal, Transaction,
                           app, allocate, apply_rules, sync_plaid_connection)


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


def test_plaid_is_disabled_without_private_credentials(monkeypatch):
    monkeypatch.setattr("clonarch.main.plaid_configuration", lambda: None)
    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": context.headers["x-csrf-token"]}
        status = client.get("/api/v1/plaid/status").json()["data"]
        assert status["configured"] is False
        link = client.post("/api/v1/plaid/link-token", headers=headers, json={})
        assert link.status_code == 409


def test_plaid_sync_sign_dates_and_transfer_exclusion(monkeypatch):
    from decimal import Decimal
    from fastapi import HTTPException
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
            {"transaction_id": "interest-1", "account_id": "synthetic-checking", "amount": Decimal("-5.00"),
             "name": "INTEREST PAYMENT", "date": "2026-10-21", "pending": False},
        ], "modified": [], "removed": [], "next_cursor": "cursor-1", "has_more": False,
            "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE"}
        calls = []
        def fake_plaid_api(endpoint, payload):
            calls.append((endpoint, payload))
            if len(calls) == 1:
                return {"added": [], "modified": [], "removed": [], "next_cursor": "partial-cursor", "has_more": True}
            if len(calls) == 2:
                raise HTTPException(502, "Plaid request failed (TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION); check connection status")
            return response
        monkeypatch.setattr("clonarch.main.plaid_api", fake_plaid_api)
        result = sync_plaid_connection(connection, db)
        assert result["added"] == 5 and result["update_status"] == "HISTORICAL_UPDATE_COMPLETE"
        rows = db.scalars(select(Transaction).where(Transaction.source == "plaid")).all()
        purchase = next(t for t in rows if t.description == "GROCERY MARKET")
        payroll = next(t for t in rows if t.description == "ACME PAYROLL")
        payments = [t for t in rows if t.description in {"PAYMENT THANK YOU", "CHASE AUTOPAY"}]
        interest = next(t for t in rows if t.description == "INTEREST PAYMENT")
        assert interest.kind == "interest" and interest.amount_minor == 500
        assert purchase.amount_minor == -1234 and purchase.purchase_date.isoformat() == "2026-10-03"
        assert purchase.posted_date.isoformat() == "2026-10-05" and purchase.kind == "expense"
        assert payroll.amount_minor == 150025 and payroll.kind == "income"
        assert all(t.kind == "transfer" for t in payments)
        assert connection.cursor == "cursor-1"
        assert len(calls) == 3
        assert all(call[0] == "transactions/sync" for call in calls)
        assert calls[0][1]["access_token"] == "synthetic-access-token"
        assert "cursor" not in calls[0][1] and calls[1][1]["cursor"] == "partial-cursor"
        assert "cursor" not in calls[2][1], "a mutation restarts the whole update from the original cursor"


def test_correction_review_creates_reusable_income_rule():
    from datetime import date
    from sqlalchemy import select

    description = "HubSpot-OSV PAYROLL617 PPD ID: 00002238"
    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": context.headers["x-csrf-token"]}
        checking = next(a for a in client.get("/api/v1/accounts").json()["data"] if a["kind"] == "checking")
        added = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": checking["id"], "amount_minor": 250000, "purchase_date": "2026-10-15",
            "posted_date": "2026-10-15", "description": description, "kind": "income"})
        assert added.status_code == 201, added.text
        tx_id = added.json()["data"]["id"]
        other_category = next(c for c in client.get("/api/v1/categories").json()["data"] if c["name"] == "Other")
        marked = client.patch(f"/api/v1/transactions/{tx_id}", headers=headers, json={"kind": "income"})
        assert marked.status_code == 200
        candidates = client.get("/api/v1/rules/suggestions").json()["data"]
        candidate = next(x for x in candidates if x["transaction_id"] == tx_id)
        assert candidate["kind"] == "income"
        assert r"payroll\d+" in candidate["suggested_pattern"]
        created = client.post(f"/api/v1/rules/suggestions/{tx_id}/create", headers=headers, json={
            "name": "HubSpot payroll", "pattern": candidate["suggested_pattern"],
            "category_id": other_category["id"], "spend_type": "exceptional", "kind": "income"})
        assert created.status_code == 201, created.text
        assert created.json()["data"]["kind"] == "income"
        assert created.json()["data"]["category_id"] == other_category["id"]
        assert created.json()["data"]["spend_type"] == "exceptional"
        assert all(x["transaction_id"] != tx_id for x in client.get("/api/v1/rules/suggestions").json()["data"])
        with SessionLocal() as db:
            rule = db.scalar(select(Rule).where(Rule.name == "HubSpot payroll"))
            assert rule and rule.kind == "income" and rule.category_id == other_category["id"]
            assert rule.spend_type == "exceptional"
            source = db.get(Transaction, tx_id)
            assert source and source.kind == "income" and source.category_id == other_category["id"]
            assert source.spend_type == "exceptional" and source.rule_locked is False
            future = Transaction(account_id=checking["id"], amount_minor=190000, purchase_date=date(2026, 11, 15),
                                 description="HubSpot-OSV PAYROLL618 PPD ID: 00009999", merchant="HubSpot",
                                 kind="expense", status="posted")
            db.add(future)
            db.flush()
            apply_rules(future, db)
            assert future.kind == "income", "description rule should match even when merchant_name exists"
            assert future.category_id == other_category["id"] and future.spend_type == "exceptional"


def test_rules_can_be_edited_and_deleted():
    from datetime import date

    with TestClient(app, base_url="http://192.168.105.10:8787") as client:
        context = client.get("/api/v1/context")
        headers = {"Origin": "http://192.168.105.10:8787", "X-CSRF-Token": context.headers["x-csrf-token"]}
        category = next(c for c in client.get("/api/v1/categories").json()["data"] if c["name"] == "Other")
        created = client.post("/api/v1/rules", headers=headers, json={
            "name": "Old rule", "pattern": "^old merchant$", "spend_type": "regular"})
        assert created.status_code == 201, created.text
        rule_id = created.json()["data"]["id"]
        edited = client.patch(f"/api/v1/rules/{rule_id}", headers=headers, json={
            "name": "Amazon case-insensitive", "pattern": "^Amazon$", "category_id": category["id"],
            "spend_type": "exceptional", "kind": "interest", "priority": 25, "enabled": True})
        assert edited.status_code == 200, edited.text
        assert edited.json()["data"]["category_id"] == category["id"]
        assert edited.json()["data"]["kind"] == "interest"
        assert edited.json()["data"]["enabled"] is True
        with SessionLocal() as db:
            future = Transaction(account_id=next(a["id"] for a in client.get("/api/v1/accounts").json()["data"] if a["kind"] == "checking"),
                                 amount_minor=-500, purchase_date=date(2026, 11, 1), description="amazon",
                                 kind="expense", status="posted")
            db.add(future)
            db.flush()
            apply_rules(future, db)
            assert future.category_id == category["id"], "Amazon regex should match lowercase transaction text"
        assert client.patch(f"/api/v1/rules/{rule_id}", headers=headers, json={"pattern": "("}).status_code == 422
        deleted = client.delete(f"/api/v1/rules/{rule_id}", headers=headers)
        assert deleted.status_code == 200 and deleted.json()["data"]["deleted"]
        assert all(r["id"] != rule_id for r in client.get("/api/v1/rules").json()["data"])


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
        interest = client.post("/api/v1/transactions", headers=headers, json={
            "account_id": checking["id"], "amount_minor": 250, "purchase_date": "2026-01-31",
            "posted_date": "2026-01-31", "description": "BANK INTEREST", "kind": "interest"
        })
        assert interest.status_code == 201, interest.text
        allocation = client.put(f"/api/v1/transactions/{purchase.json()['data']['id']}/allocation",
                                headers=headers, json={"start_month": "2026-01", "end_month_exclusive": "2027-01"})
        assert allocation.status_code == 200, allocation.text
        report = client.get("/api/v1/reports/monthly?month=2026-01&basis=normalized").json()["data"]
        assert report["actual"]["regular_minor"] == 120_000
        assert report["normalized"]["regular_minor"] == 10_000
        assert report["actual"]["income_minor"] == 600_000, "interest is distinct from reported income"
        assert report["actual"]["recorded_surplus_minor"] == 480_000
        assert client.post("/api/v1/rules/apply", json={}).status_code == 403
