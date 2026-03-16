"""Webhook receive and deviceName tests."""
from unittest.mock import patch
from app.models import RawMessage


@patch("app.routers.webhook._process_in_background")
def test_webhook_creates_message(mock_bg, client, db):
    """Webhook should create a raw message and return message_id."""
    r = client.post("/api/webhook", json={
        "type": "NOTIFICATION",
        "source": "com.test",
        "sourceName": "테스트앱",
        "content": "테스트 메시지 10,000원",
        "timestamp": 1710568800000,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "message_id" in data


@patch("app.routers.webhook._process_in_background")
def test_webhook_stores_device_name(mock_bg, client, db):
    """deviceName should be stored in raw_messages."""
    r = client.post("/api/webhook", json={
        "type": "NOTIFICATION",
        "source": "com.hanacard",
        "sourceName": "하나카드",
        "deviceName": "꾸폰",
        "content": "하나카드 승인 15,000원",
        "timestamp": 1710568800000,
    })
    msg_id = r.json()["message_id"]
    msg = db.query(RawMessage).get(msg_id)
    assert msg.device_name == "꾸폰"


@patch("app.routers.webhook._process_in_background")
def test_webhook_empty_device_name(mock_bg, client, db):
    """Missing deviceName should default to empty string."""
    r = client.post("/api/webhook", json={
        "type": "NOTIFICATION",
        "source": "com.test",
        "sourceName": "테스트",
        "content": "테스트",
        "timestamp": 1710568800000,
    })
    msg_id = r.json()["message_id"]
    msg = db.query(RawMessage).get(msg_id)
    assert msg.device_name == ""


@patch("app.routers.webhook._process_in_background")
def test_webhook_message_status_pending(mock_bg, client, db):
    """New webhook message should have status 'pending'."""
    r = client.post("/api/webhook", json={
        "type": "SMS",
        "source": "com.bank",
        "sourceName": "은행",
        "content": "입금 500,000원",
        "timestamp": 1710568800000,
    })
    msg_id = r.json()["message_id"]
    msg = db.query(RawMessage).get(msg_id)
    assert msg.status == "pending"
