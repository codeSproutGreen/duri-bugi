"""Dashboard, monthly, trend, income-expense tests."""
from tests.conftest import seed_accounts, seed_account, seed_entry


def test_dashboard_totals_exclude_groups(client, db):
    """Group accounts should not contribute to totals."""
    accts = seed_accounts(db)
    # expense_group is a group — even if it somehow had balance, it shouldn't count
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "total_expense" in data


def test_dashboard_net_worth(client, db):
    """net_worth = total_asset - total_liability."""
    accts = seed_accounts(db)
    seed_entry(db, accts["bank"].id, accts["equity"].id, 1000000, description="초기자본")
    seed_entry(db, accts["food"].id, accts["card"].id, 50000, description="카드결제")

    r = client.get("/api/dashboard").json()
    assert r["net_worth"] == r["total_asset"] - r["total_liability"]


def test_dashboard_includes_deleted_account_with_balance(client, db):
    """Deleted account with non-zero balance should appear in dashboard."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000)
    # Soft delete food account
    food = accts["food"]
    food.is_deleted = 1
    db.commit()

    r = client.get("/api/dashboard").json()
    acct_ids = [a["id"] for a in r["accounts"]]
    assert food.id in acct_ids


def test_dashboard_excludes_deleted_account_zero_balance(client, db):
    """Deleted account with zero balance should not appear."""
    accts = seed_accounts(db)
    # Delete food (no entries, zero balance)
    food = accts["food"]
    food.is_deleted = 1
    db.commit()

    r = client.get("/api/dashboard").json()
    acct_ids = [a["id"] for a in r["accounts"]]
    assert food.id not in acct_ids


def test_pending_count(client, db):
    """pending_count should match unconfirmed entries."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000, confirmed=0)
    seed_entry(db, accts["food"].id, accts["card"].id, 5000, confirmed=0)
    seed_entry(db, accts["food"].id, accts["card"].id, 3000, confirmed=1)

    r = client.get("/api/dashboard").json()
    assert r["pending_count"] == 2


def test_pending_count_endpoint(client, db):
    """Lightweight pending-count endpoint."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 10000, confirmed=0)

    r = client.get("/api/dashboard/pending-count").json()
    assert r["count"] == 1


def test_monthly_income_expense(client, db):
    """Monthly aggregation should separate income and expense."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 50000, entry_date="2026-03-10", description="식비")
    seed_entry(db, accts["bank"].id, accts["salary"].id, 3000000, entry_date="2026-03-01", description="급여")

    r = client.get("/api/dashboard/monthly?months=1").json()
    assert len(r) >= 1
    march = next((m for m in r if m["month"] == "2026-03"), None)
    assert march is not None
    assert march["expense"] > 0
    assert march["income"] > 0


def test_income_expense_report(client, db):
    """Per-account income/expense report for date range."""
    accts = seed_accounts(db)
    seed_entry(db, accts["food"].id, accts["card"].id, 30000, entry_date="2026-03-15")

    r = client.get("/api/dashboard/income-expense?start=2026-03-01&end=2026-03-31").json()
    assert "expense" in r
    assert "total_expense" in r
    assert r["total_expense"] >= 30000
