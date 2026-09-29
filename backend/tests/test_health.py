from __future__ import annotations

import pytest


def test_health_returns_ok(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "MineTrace"
    assert data["version"] == "0.1.0"
    assert "database" in data
    assert "ollama" in data
    assert "netguard_active" in data


def test_health_db_status(client):
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert data["database"]["status"] == "ok"


def test_netguard_blocks_external():
    import socket

    from app.netguard import ExternalNetworkBlockedError, activate, is_active

    activate()
    assert is_active()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(ExternalNetworkBlockedError):
        s.connect(("8.8.8.8", 53))
    s.close()


def test_netguard_allows_loopback():
    import socket

    from app.netguard import ExternalNetworkBlockedError, activate

    activate()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(0.5)
        s.connect(("127.0.0.1", 1))
    except ExternalNetworkBlockedError:
        pytest.fail("Loopback should be allowed")
    except (ConnectionRefusedError, TimeoutError, OSError):
        pass
    finally:
        s.close()
