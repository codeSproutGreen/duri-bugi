"""Account CRUD, code generation, soft delete, group logic tests."""
from tests.conftest import seed_account, seed_accounts, seed_entry


# ── Duplicate name check ──

def test_create_same_name_different_type_ok(client, db):
    """Same account name in different types should be allowed."""
    seed_accounts(db)
    # "테스트" in expense
    r1 = client.post("/api/accounts", json={"code": "", "name": "테스트", "type": "expense"})
    assert r1.status_code == 200
    # "테스트" in income — should succeed
    r2 = client.post("/api/accounts", json={"code": "", "name": "테스트", "type": "income"})
    assert r2.status_code == 200


# ── Code generation ──

def test_auto_generate_code(client, db):
    """Account with empty code should get auto-generated code."""
    seed_accounts(db)
    r = client.post("/api/accounts", json={"code": "", "name": "새계정", "type": "expense"})
    assert r.status_code == 200
    assert r.json()["code"] != ""


def test_next_code_skips_deleted(client, db):
    """Deleted account codes should not be reused."""
    acct = seed_account(db, "5001", "삭제될계정", "expense")
    db.commit()
    # Soft delete
    client.delete(f"/api/accounts/{acct.id}")
    # Next code should skip 5001
    r = client.get("/api/accounts/next-code?type=expense")
    assert r.status_code == 200
    assert int(r.json()["code"]) > 5001


def test_create_duplicate_code_rejected(client, db):
    """Duplicate account code should be rejected."""
    seed_account(db, "1001", "기존계정", "asset")
    db.commit()
    r = client.post("/api/accounts", json={"code": "1001", "name": "새계정", "type": "asset"})
    assert r.status_code == 400


# ── Soft delete ──

def test_delete_account_soft(client, db):
    """Deleted account should not appear in account list."""
    accts = seed_accounts(db)
    acct_id = accts["food"].id
    r = client.delete(f"/api/accounts/{acct_id}")
    assert r.status_code == 200
    # Should not appear in list
    r = client.get("/api/accounts")
    all_ids = [a["id"] for a in r.json().get("expense", [])]
    assert acct_id not in all_ids


def test_delete_account_with_transactions_allowed(client, db):
    """Account with transactions should still be deletable (soft delete)."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000)
    r = client.delete(f"/api/accounts/{accts['food'].id}")
    assert r.status_code == 200


def test_delete_account_with_children_blocked(client, db):
    """Account with active children should not be deletable."""
    accts = seed_accounts(db)
    parent = accts["expense_group"]
    seed_account(db, "5010", "하위계정", "expense", parent_id=parent.id)
    db.commit()
    r = client.delete(f"/api/accounts/{parent.id}")
    assert r.status_code == 400


# ── Group accounts ──

def test_create_child_auto_promotes_parent_to_group(client, db):
    """Adding a child to a non-group account should auto-set parent as group."""
    accts = seed_accounts(db)
    parent = accts["food"]  # not a group
    r = client.post("/api/accounts", json={
        "code": "", "name": "간식", "type": "expense", "parent_id": parent.id,
    })
    assert r.status_code == 200
    # Refresh parent
    db.refresh(parent)
    assert parent.is_group == 1


# ── Reorder ──

def test_reorder_accounts(client, db):
    """Reorder should update sort_order."""
    a1 = seed_account(db, "5001", "A", "expense", is_group=0)
    a2 = seed_account(db, "5002", "B", "expense", is_group=0)
    db.commit()
    r = client.put("/api/accounts/reorder", json=[
        {"id": a2.id, "sort_order": 0, "parent_id": None},
        {"id": a1.id, "sort_order": 1, "parent_id": None},
    ])
    assert r.status_code == 200
    db.refresh(a1)
    db.refresh(a2)
    assert a2.sort_order == 0
    assert a1.sort_order == 1


# ── Update ──

def test_update_account(client, db):
    """Update account name."""
    accts = seed_accounts(db)
    r = client.put(f"/api/accounts/{accts['food'].id}", json={"name": "음식비"})
    assert r.status_code == 200
    assert r.json()["name"] == "음식비"


def test_update_deleted_account_404(client, db):
    """Updating a deleted account should return 404."""
    acct = seed_account(db, "9001", "삭제됨", "expense", is_deleted=1)
    db.commit()
    # is_deleted=1 but is_active defaults to 1, set is_active=0 too
    acct.is_active = 0
    db.commit()
    r = client.put(f"/api/accounts/{acct.id}", json={"name": "변경"})
    assert r.status_code == 404
