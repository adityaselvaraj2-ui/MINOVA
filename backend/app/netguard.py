from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any

logger = logging.getLogger("minetrace.netguard")

_original_connect = socket.socket.connect
_original_getaddrinfo = socket.getaddrinfo
_active = False

LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1", "localhost"})


class ExternalNetworkBlockedError(OSError):
    pass


ExternalNetworkBlocked = ExternalNetworkBlockedError


def _is_loopback(host: str) -> bool:
    if host in LOOPBACK_ADDRS:
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_loopback
    except ValueError:
        return False


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    af_unix = getattr(socket, "AF_UNIX", None)
    if af_unix is not None and self.family == af_unix:
        return _original_connect(self, address)

    host = address[0] if isinstance(address, tuple) else str(address)

    if not _is_loopback(str(host)):
        msg = f"ExternalNetworkBlocked: connection to {host} denied by netguard"
        logger.warning(msg)
        raise ExternalNetworkBlockedError(msg)

    return _original_connect(self, address)


def _guarded_getaddrinfo(
    host: Any,
    port: Any,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0,
) -> list:
    host_str = str(host) if host is not None else ""
    if host_str and not _is_loopback(host_str):
        msg = f"ExternalNetworkBlocked: DNS lookup for {host_str} denied by netguard"
        logger.warning(msg)
        raise ExternalNetworkBlockedError(msg)

    return _original_getaddrinfo(host, port, family, type, proto, flags)


def activate() -> None:
    global _active
    if _active:
        return

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    socket.socket.connect = _guarded_connect  # type: ignore[assignment]
    socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
    _active = True
    logger.info("Netguard activated: only loopback connections allowed")


def deactivate() -> None:
    global _active
    if not _active:
        return
    socket.socket.connect = _original_connect  # type: ignore[assignment]
    socket.getaddrinfo = _original_getaddrinfo  # type: ignore[assignment]
    _active = False
    logger.info("Netguard deactivated")


def is_active() -> bool:
    return _active
