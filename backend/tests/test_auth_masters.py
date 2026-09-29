from __future__ import annotations

from app.db.models import Role, Subsidiary, User
from app.security import hash_password


def _seed_minimal(db):
    """Create minimal data for auth tests."""
    if db.query(Role).count() > 0:
        return
    role = Role(code="FOREMAN", rank=1, label="Foreman", can_enter=True, can_approve=False)
    db.add(role)
    sub = Subsidiary(code="NCL", name="Northern Coalfields Limited")
    db.add(sub)
    db.flush()
    user = User(
        username="testuser",
        full_name="Test User",
        password_hash=hash_password("testpass"),
        role_code="FOREMAN",
    )
    db.add(user)
    db.commit()


def test_login_success(client):
    from app.db.session import get_session_factory

    session = get_session_factory()()
    _seed_minimal(session)
    session.close()

    resp = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == "testuser"
    assert data["role_code"] == "FOREMAN"


def test_login_wrong_password(client):
    resp = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "wrong"})
    assert resp.status_code == 401


def test_me_endpoint(client):
    login = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    token = login.json()["access_token"]

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["can_enter"] is True


def test_masters_requires_auth(client):
    resp = client.get("/api/v1/masters/subsidiaries")
    assert resp.status_code == 401


def test_masters_subsidiaries(client):
    login = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    token = login.json()["access_token"]

    resp = client.get(
        "/api/v1/masters/subsidiaries", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["code"] == "NCL"


def test_masters_roles(client):
    login = client.post("/api/v1/auth/login", json={"username": "testuser", "password": "testpass"})
    token = login.json()["access_token"]

    resp = client.get("/api/v1/masters/roles", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
