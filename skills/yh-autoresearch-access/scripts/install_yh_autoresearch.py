"""Activate, download, verify, and install the YH Autoresearch client-side skill."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_destination(agent: str) -> Path:
    if agent == "codex":
        base = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        return base / "skills" / "yh-autoresearch"
    if agent == "claude":
        return Path.home() / ".claude" / "skills" / "yh-autoresearch"
    return Path.cwd() / ".agents" / "skills" / "yh-autoresearch"


def activate_and_download(base_url: str, code: str, timeout: int = 60) -> tuple[bytes, str]:
    base = base_url.rstrip("/")
    body = json.dumps({"code": code}).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/api/activate",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            activation = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("activation failed") from None
        raise RuntimeError(f"activation host returned HTTP {exc.code}") from None
    token = str(activation.get("token", ""))
    expected_hash = str(activation.get("bundle_sha256", "")).lower()
    if not token or len(expected_hash) != 64:
        raise RuntimeError("activation response is incomplete")
    download = urllib.request.Request(
        urllib.parse.urljoin(base + "/", str(activation.get("bundle_url", "/api/bundle")).lstrip("/")),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/zip"},
    )
    with urllib.request.urlopen(download, timeout=timeout) as response:
        data = response.read()
        header_hash = response.headers.get("X-YH-Bundle-SHA256", "").lower()
    actual = sha256_bytes(data)
    if actual != expected_hash or (header_hash and header_hash != actual):
        raise RuntimeError("bundle checksum mismatch")
    return data, actual


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise RuntimeError("bundle is empty")
    for member in members:
        path = Path(member.filename)
        mode = member.external_attr >> 16
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "yh-autoresearch":
            raise RuntimeError(f"unsafe archive path: {member.filename}")
        if stat.S_ISLNK(mode):
            raise RuntimeError(f"symbolic links are not allowed: {member.filename}")
    return members


def verify_tree(root: Path) -> dict[str, object]:
    manifest_path = root / "manifest.json"
    skill_path = root / "SKILL.md"
    if not manifest_path.is_file() or not skill_path.is_file():
        raise RuntimeError("bundle is missing SKILL.md or manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "yh-autoresearch" or manifest.get("execution") != "client-side-agent":
        raise RuntimeError("bundle manifest identity is invalid")
    entries = manifest.get("files", [])
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("bundle manifest has no files")
    expected_files = {"manifest.json", "checksums.sha256"}
    for entry in entries:
        relative = Path(str(entry.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("manifest contains an unsafe path")
        expected_files.add(relative.as_posix())
        path = root / relative
        if not path.is_file() or path.stat().st_size != int(entry.get("size", -1)):
            raise RuntimeError(f"manifest size mismatch: {relative.as_posix()}")
        if sha256_file(path) != entry.get("sha256"):
            raise RuntimeError(f"manifest checksum mismatch: {relative.as_posix()}")
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise RuntimeError("bundle file set does not match the manifest")
    return manifest


def install_bundle(data: bytes, destination: Path) -> tuple[dict[str, object], Path | None]:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yh-ar-install-") as temp_dir:
        archive_path = Path(temp_dir) / "bundle.zip"
        archive_path.write_bytes(data)
        extract_root = Path(temp_dir) / "extract"
        extract_root.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_members(archive)
            archive.extractall(extract_root, members=members)
        candidate = extract_root / "yh-autoresearch"
        manifest = verify_tree(candidate)
        backup: Path | None = None
        if destination.exists():
            backup = destination.with_name(f"{destination.name}.backup-{int(time.time())}")
            if backup.exists():
                raise RuntimeError(f"backup destination already exists: {backup}")
            destination.replace(backup)
        try:
            shutil.move(str(candidate), str(destination))
        except Exception:
            if backup and backup.exists() and not destination.exists():
                backup.replace(destination)
            raise
    return manifest, backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("YH_AUTORESEARCH_ACCESS_URL", ""))
    parser.add_argument("--agent", choices=["codex", "claude", "generic"], default="codex")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or YH_AUTORESEARCH_ACCESS_URL is required")
    code = os.environ.get("YH_AUTORESEARCH_CODE") or getpass.getpass("YH Autoresearch access code: ")
    data, archive_hash = activate_and_download(args.base_url, code)
    destination = args.destination or default_destination(args.agent)
    manifest, backup = install_bundle(data, destination)
    print(json.dumps({
        "installed": True,
        "version": manifest.get("version"),
        "destination": str(destination.resolve()),
        "bundle_sha256": archive_hash,
        "backup": str(backup) if backup else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
