"""Small code-gated release host for the client-side YH Autoresearch bundle.

The host distributes bytes only. It never executes research or stores user research state.
Put it behind HTTPS for any non-loopback deployment.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


AUDIENCE = "yh-autoresearch-bundle"
COOKIE_NAME = "yh_ar_access"
PHONETIC_TOKENS = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliett": "J",
    "juliet": "J", "kilo": "K", "lima": "L", "mike": "M", "november": "N",
    "nato": "N", "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R",
    "sierra": "S", "tango": "T", "uniform": "U", "victor": "V", "whiskey": "W",
    "xray": "X", "yankee": "Y", "zulu": "Z", "zero": "0", "one": "1",
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9",
}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def normalize_code(value: str) -> str:
    """Normalize the short internal-beta code without logging it."""
    compact = "".join(ch for ch in value.lower() if ch.isalnum())
    decoded: list[str] = []
    offset = 0
    tokens = sorted(PHONETIC_TOKENS, key=len, reverse=True)
    while offset < len(compact):
        if compact[offset].isdigit():
            decoded.append(compact[offset])
            offset += 1
            continue
        token = next((word for word in tokens if compact.startswith(word, offset)), None)
        if token is None:
            return compact.upper()
        decoded.append(PHONETIC_TOKENS[token])
        offset += len(token)
    return "".join(decoded)


@dataclass(frozen=True)
class AccessConfig:
    access_code: str
    session_secret: bytes
    bundle_path: Path
    token_ttl_seconds: int = 900
    secure_cookie: bool = True
    public_prefix: str = ""

    @classmethod
    def from_env(cls) -> "AccessConfig":
        access_code = os.environ.get("YH_ACCESS_CODE", "")
        secret = os.environ.get("YH_SESSION_SECRET", "").encode("utf-8")
        bundle = os.environ.get("YH_BUNDLE_PATH", "")
        if not normalize_code(access_code):
            raise RuntimeError("YH_ACCESS_CODE is required")
        if len(secret) < 32:
            raise RuntimeError("YH_SESSION_SECRET must contain at least 32 characters")
        if not bundle:
            raise RuntimeError("YH_BUNDLE_PATH is required")
        bundle_path = Path(bundle).expanduser().resolve()
        if not bundle_path.is_file() or bundle_path.suffix.lower() != ".zip":
            raise RuntimeError("YH_BUNDLE_PATH must be an existing ZIP file")
        return cls(
            access_code=normalize_code(access_code),
            session_secret=secret,
            bundle_path=bundle_path,
            token_ttl_seconds=int(os.environ.get("YH_TOKEN_TTL_SECONDS", "900")),
            secure_cookie=os.environ.get("YH_SECURE_COOKIE", "1") != "0",
            public_prefix=normalize_prefix(os.environ.get("YH_PUBLIC_PREFIX", "")),
        )

    @property
    def bundle_sha256(self) -> str:
        digest = hashlib.sha256()
        with self.bundle_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()


def normalize_prefix(value: str) -> str:
    compact = "/" + value.strip().strip("/") if value.strip().strip("/") else ""
    if ".." in compact or "//" in compact:
        raise RuntimeError("YH_PUBLIC_PREFIX is invalid")
    return compact


def issue_token(config: AccessConfig, now: int | None = None) -> str:
    current = int(time.time() if now is None else now)
    payload = {
        "aud": AUDIENCE,
        "exp": current + config.token_ttl_seconds,
        "iat": current,
        "nonce": secrets.token_hex(12),
    }
    encoded = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _b64url(hmac.new(config.session_secret, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_token(config: AccessConfig, token: str, now: int | None = None) -> bool:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = _b64url(hmac.new(config.session_secret, encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected):
            return False
        payload = json.loads(_b64url_decode(encoded))
        current = int(time.time() if now is None else now)
        return payload.get("aud") == AUDIENCE and int(payload.get("exp", 0)) >= current
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return False


def make_handler(config: AccessConfig) -> type[BaseHTTPRequestHandler]:
    class AccessHandler(BaseHTTPRequestHandler):
        server_version = "YHAccess/0.1"

        def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if length is not None:
                self.send_header("Content-Length", str(length))

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _html(self, status: int, body: str, cookie: str | None = None) -> None:
            data = body.encode("utf-8")
            self._headers(status, "text/html; charset=utf-8", len(data))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> bytes:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length < 0 or length > 8192:
                return b""
            return self.rfile.read(length)

        def _presented_token(self) -> str:
            authorization = self.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                return authorization[7:].strip()
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookies.get(COOKIE_NAME)
            return morsel.value if morsel else ""

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._json(HTTPStatus.OK, {"ok": True, "service": "yh-autoresearch-access"})
                return
            if self.path == "/":
                action = html.escape(config.public_prefix + "/activate", quote=True)
                page = f"""<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>YH Autoresearch Internal Beta</title>
<style>body{font:16px system-ui;max-width:34rem;margin:10vh auto;padding:1.2rem;color:#17202a}input,button{font:inherit;padding:.8rem;margin:.35rem 0;width:100%;box-sizing:border-box}button{background:#17202a;color:white;border:0;border-radius:.4rem}small{color:#59636e}</style>
<h1>YH Autoresearch</h1><p>Activate the client-side internal beta skill.</p>
<form method=\"post\" action=\"{action}\"><label>Access code<input name=\"code\" autocomplete=\"one-time-code\" required maxlength=\"64\"></label><button>Activate and download</button></form>
<small>The host distributes the skill only. Research stays in your agent workspace.</small></html>"""
                self._html(HTTPStatus.OK, page)
                return
            if self.path in {"/download", "/api/bundle"}:
                if not verify_token(config, self._presented_token()):
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "activation_required"})
                    return
                stat = config.bundle_path.stat()
                self._headers(HTTPStatus.OK, "application/zip", stat.st_size)
                self.send_header("Content-Disposition", f'attachment; filename="{html.escape(config.bundle_path.name)}"')
                self.send_header("X-YH-Bundle-SHA256", config.bundle_sha256)
                self.end_headers()
                with config.bundle_path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        self.wfile.write(block)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path not in {"/activate", "/api/activate"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            body = self._read_body()
            content_type = self.headers.get("Content-Type", "")
            supplied = ""
            try:
                if content_type.startswith("application/json"):
                    supplied = str(json.loads(body or b"{}").get("code", ""))
                else:
                    supplied = parse_qs(body.decode("utf-8")).get("code", [""])[0]
            except (json.JSONDecodeError, UnicodeDecodeError):
                supplied = ""
            valid = hmac.compare_digest(normalize_code(supplied), config.access_code)
            if not valid:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_access_code"})
                return
            token = issue_token(config)
            if self.path == "/api/activate" or content_type.startswith("application/json"):
                self._json(
                    HTTPStatus.OK,
                    {
                        "token": token,
                        "expires_in": config.token_ttl_seconds,
                        "bundle_url": config.public_prefix + "/api/bundle",
                        "bundle_sha256": config.bundle_sha256,
                    },
                )
                return
            cookie_path = config.public_prefix + "/" if config.public_prefix else "/"
            cookie = f"{COOKIE_NAME}={token}; Path={cookie_path}; HttpOnly; SameSite=Strict; Max-Age={config.token_ttl_seconds}"
            if config.secure_cookie:
                cookie += "; Secure"
            download_url = html.escape(config.public_prefix + "/download", quote=True)
            page = f"<!doctype html><meta charset=\"utf-8\"><title>Activated</title><p>Activation accepted.</p><p><a href=\"{download_url}\">Download YH Autoresearch</a></p>"
            self._html(HTTPStatus.OK, page, cookie=cookie)

        def log_message(self, format: str, *args: object) -> None:
            # Standard access log; request bodies and authorization headers are never logged.
            super().log_message(format, *args)

    return AccessHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a code-gated YH Autoresearch bundle")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    config = AccessConfig.from_env()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(config))
    print(f"YH Autoresearch access host listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
