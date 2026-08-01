"""A local StreamLine device that enforces the firmware's digest challenge.

Home Assistant's aiohttp mocker replaces the session's request path, so a
client middleware never runs against it and no mocked call can show whether
the integration answers a challenge. These tests serve real responses over a
loopback port instead, so the RFC 7616 exchange the firmware requires is
proven rather than assumed.

The rules mirror ``firmware/streamline/src/auth.rs``: one ``admin`` account in
realm ``streamline``, SHA-256 with ``qop=auth``, a response hash bound to the
request's method and URI, and a nonce count that must strictly increase.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from aiohttp import web
from aiohttp.test_utils import TestServer

from .device_payloads import error_response

if TYPE_CHECKING:
    from types import TracebackType

USERNAME = "admin"
REALM = "streamline"
ALGORITHM = "SHA-256"
QOP = "auth"

_FIELD = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|([^\s,]+))')


@dataclass(frozen=True)
class _Route:
    """What one registered operation answers with."""

    payload: dict[str, Any]
    authenticated: bool
    status: int


class Verdict(Enum):
    """The firmware's three outcomes for one authenticated request."""

    AUTHORIZED = "authorized"
    DENIED = "denied"
    # The key was not disproven: the nonce is unknown or its count was
    # reused, so the client should retry against a fresh challenge.
    STALE = "stale"


class DigestDevice:
    """Serve device payloads, gating the authenticated ones behind a digest."""

    def __init__(self, admin_key: str) -> None:
        self._admin_key = admin_key
        self._routes: dict[tuple[str, str], _Route] = {}
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._serve)
        self._server = TestServer(app)
        self._nonce = "0" * 32
        self._highest_count = 0
        self.served_requests: list[tuple[str, str]] = []
        self.authenticated_paths: list[str] = []

    @property
    def url(self) -> str:
        """Return the device root URL, once the device is serving."""
        return str(self._server.make_url("")).rstrip("/")

    def route(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any],
        authenticated: bool,
        status: int = 200,
    ) -> None:
        """Serve one device operation, with or without the digest gate."""
        self._routes[method.upper(), path] = _Route(payload, authenticated, status)

    async def _serve(self, request: web.Request) -> web.Response:
        route = self._routes.get((request.method, request.path))
        if route is None:
            raise web.HTTPNotFound
        if route.authenticated:
            verdict = self._verdict(request)
            if verdict is not Verdict.AUTHORIZED:
                return self._challenge(stale=verdict is Verdict.STALE)
            self.authenticated_paths.append(request.path)
        self.served_requests.append((request.method, request.path))
        return web.json_response(route.payload, status=route.status)

    def expire_nonce(self) -> None:
        """Retire the live nonce, as an hour or a fifth client would."""
        self._nonce = f"{int(self._nonce, 16) + 1:032x}"
        self._highest_count = 0

    async def __aenter__(self) -> DigestDevice:
        await self._server.start_server()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._server.close()

    def _challenge(self, *, stale: bool) -> web.Response:
        header = (
            f'Digest realm="{REALM}", qop="{QOP}", algorithm={ALGORITHM}, nonce="{self._nonce}"'
        )
        return web.json_response(
            error_response("invalid admin key"),
            status=401,
            headers={"WWW-Authenticate": header + (", stale=true" if stale else "")},
        )

    def _verdict(self, request: web.Request) -> Verdict:
        """Accept only a fresh, correctly bound proof of the admin key."""
        header = request.headers.get("Authorization", "")
        if not header.startswith("Digest "):
            return Verdict.DENIED
        fields = {
            match[1]: match[2] if match[2] is not None else match[3]
            for match in _FIELD.finditer(header.removeprefix("Digest "))
        }
        if (
            not {"nc", "cnonce", "response"} <= fields.keys()
            or fields.get("username") != USERNAME
            or fields.get("realm") != REALM
            or fields.get("uri") != request.path_qs
            or fields.get("qop") != QOP
            or fields.get("algorithm", ALGORITHM) != ALGORITHM
        ):
            return Verdict.DENIED
        count = int(fields["nc"], 16)
        if fields.get("nonce") != self._nonce or count <= self._highest_count:
            return Verdict.STALE
        expected = _response_hash(
            self._admin_key, request.method, request.path_qs, self._nonce, fields
        )
        if expected != fields["response"]:
            return Verdict.DENIED
        self._highest_count = count
        return Verdict.AUTHORIZED


def _response_hash(
    admin_key: str, method: str, uri: str, nonce: str, fields: dict[str, str]
) -> str:
    ha1 = _sha256(f"{USERNAME}:{REALM}:{admin_key}")
    ha2 = _sha256(f"{method}:{uri}")
    return _sha256(f"{ha1}:{nonce}:{fields['nc']}:{fields['cnonce']}:{QOP}:{ha2}")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
