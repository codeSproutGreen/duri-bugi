"""Journal entry CRUD, balance validation, confirm/reject tests."""
from tests.conftest import seed_accounts, seed_entry, seed_raw_message
from app.models import CategoryRule, RawMessage


# ── Balance validation ──

def test_create_entry_balanced_ok(client, db):
    """Balanced entry should succeed."""
    accts = seed_accounts(db)
    r = client.post("/api/entries", json={
        "entry_date": "2026-03-16",
        "description": "테스트",
        "lines": [
            {"account_id": accts["food"].id, "debit": 10000, "credit": 0},
            {"account_id": accts["card"].id, "debit": 0, "credit": 10000},
        ],
    })
    assert r.status_code == 200
    assert r.json()["is_confirmed"] == 1  # manual entries auto-confirmed


def test_create_entry_unbalanced_rejected(client, db):
    """Unbalanced entry (debit != credit) should be rejected."""
    accts = seed_accounts(db)
    r = client.post("/api/entries", json={
        "entry_date": "2026-03-16",
        "description": "불일치",
        "lines": [
            {"account_id": accts["food"].id, "debit": 10000, "credit": 0},
            {"account_id": accts["card"].id, "debit": 0, "credit": 5000},
        ],
    })
    assert r.status_code == 400


def test_create_entry_zero_rejected(client, db):
    """Zero amount entry should be rejected."""
    accts = seed_accounts(db)
    r = client.post("/api/entries", json={
        "entry_date": "2026-03-16",
        "description": "제로",
        "lines": [
            {"account_id": accts["food"].id, "debit": 0, "credit": 0},
            {"account_id": accts["card"].id, "debit": 0, "credit": 0},
        ],
    })
    assert r.status_code == 400


# ── Group account blocking ──

def test_create_entry_with_group_account_rejected(client, db):
    """Group accounts cannot be used in journal entries."""
    accts = seed_accounts(db)
    r = client.post("/api/entries", json={
        "entry_date": "2026-03-16",
        "description": "그룹테스트",
        "lines": [
            {"account_id": accts["expense_group"].id, "debit": 5000, "credit": 0},
            {"account_id": accts["card"].id, "debit": 0, "credit": 5000},
        ],
    })
    assert r.status_code == 400


# ── Confirmed filter ──

def test_list_entries_confirmed_filter(client, db):
    """Filter entries by confirmed status."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000, confirmed=1, description="확인됨")
    seed_entry(db, accts["food"].id, accts["card"].id, 5000, confirmed=0, description="미확인")

    confirmed = client.get("/api/entries?confirmed=1").json()
    pending = client.get("/api/entries?confirmed=0").json()

    assert all(e["is_confirmed"] == 1 for e in confirmed)
    assert all(e["is_confirmed"] == 0 for e in pending)
    assert len(confirmed) == 1
    assert len(pending) == 1


# ── Confirm / Reject flow ──

def test_confirm_entry(client, db):
    """Confirming an entry sets is_confirmed=1."""
    accts = seed_accounts(db)
    entry = seed_entry(db, accts["food"].id, accts["card"].id, 8000, confirmed=0)
    r = client.post(f"/api/entries/{entry.id}/confirm")
    assert r.status_code == 200
    db.refresh(entry)
    assert entry.is_confirmed == 1


def test_confirm_creates_category_rule(client, db):
    """Confirming an entry should create a category rule."""
    accts = seed_accounts(db)
    entry = seed_entry(db, accts["food"].id, accts["card"].id, 8000, confirmed=0, description="스타벅스")
    client.post(f"/api/entries/{entry.id}/confirm")
    rule = db.query(CategoryRule).filter(CategoryRule.merchant_pattern == "스타벅스").first()
    assert rule is not None
    assert rule.debit_account_id == accts["food"].id
    assert rule.credit_account_id == accts["card"].id


def test_reject_entry_deletes_and_updates_message(client, db):
    """Rejecting an entry should delete it and set message status to rejected."""
    accts = seed_accounts(db)
    msg = seed_raw_message(db, content="테스트 결제")
    entry = seed_entry(db, accts["food"].id, accts["card"].id, 5000, confirmed=0)
    entry.raw_message_id = msg.id
    db.commit()

    r = client.post(f"/api/entries/{entry.id}/reject")
    assert r.status_code == 200
    db.refresh(msg)
    assert msg.status == "rejected"
    # Entry should be deleted
    assert db.query(type(entry)).get(entry.id) is None


def test_delete_entry_resets_message_to_pending(client, db):
    """Deleting an entry should reset linked message status to pending."""
    accts = seed_accounts(db)
    msg = seed_raw_message(db, content="테스트")
    msg.status = "parsed"
    db.commit()
    entry = seed_entry(db, accts["food"].id, accts["card"].id, 5000, confirmed=1)
    entry.raw_message_id = msg.id
    db.commit()

    r = client.delete(f"/api/entries/{entry.id}")
    assert r.status_code == 200
    db.refresh(msg)
    assert msg.status == "pending"


# ── Update entry ──

def test_update_entry_replaces_lines(client, db):
    """Updating lines should replace old lines."""
    accts = seed_accounts(db)
    entry = seed_entry(db, accts["food"].id, accts["card"].id, 10000, confirmed=1)
    r = client.put(f"/api/entries/{entry.id}", json={
        "lines": [
            {"account_id": accts["misc_expense"].id, "debit": 20000, "credit": 0},
            {"account_id": accts["card"].id, "debit": 0, "credit": 20000},
        ],
    })
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert len(lines) == 2
    assert lines[0]["account_id"] == accts["misc_expense"].id
    assert lines[0]["debit"] == 20000


# ── Search ──

def test_list_entries_search(client, db):
    """Search filter should match description."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000, description="스타벅스")
    seed_entry(db, accts["food"].id, accts["card"].id, 5000, description="맥도날드")

    r = client.get("/api/entries?search=스타벅스").json()
    assert len(r) == 1
    assert r[0]["description"] == "스타벅스"
