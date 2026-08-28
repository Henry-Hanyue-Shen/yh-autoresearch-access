"""Build a deterministic, single-root YH Autoresearch skill ZIP from v4 source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".autoresearch",
    ".claude",
    ".codex",
    "__pycache__",
    ".pytest_cache",
    "runs",
    "loop_runs",
    "checkpoints",
    "evaluators",
    "runner_runs",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def include_path(relative: Path) -> bool:
    return not any(part in EXCLUDED_PARTS for part in relative.parts) and relative.suffix.lower() not in EXCLUDED_SUFFIXES


def build_bundle(source: Path, output: Path, version: str, source_release_sha256: str) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    required = [source / "START_HERE.md", source / "AGENTS.md", source / "shared" / "skills" / "frontier-autoresearch" / "SKILL.md"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"source is not a YH Autoresearch v4 tree; missing: {missing}")

    template = Path(__file__).resolve().parents[1] / "bundle" / "SKILL.md"
    if not template.is_file():
        raise RuntimeError("bundle/SKILL.md is missing")

    with tempfile.TemporaryDirectory(prefix="yh-ar-bundle-") as temp_dir:
        root = Path(temp_dir) / "yh-autoresearch"
        root.mkdir()
        for path in sorted(source.rglob("*"), key=lambda item: item.as_posix().lower()):
            relative = path.relative_to(source)
            if not include_path(relative) or path.is_dir():
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        shutil.copy2(template, root / "SKILL.md")

        files: list[dict[str, object]] = []
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
            if path.is_file() and path.name not in {"manifest.json", "checksums.sha256"}:
                relative = path.relative_to(root).as_posix()
                files.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})

        manifest = {
            "schema_version": 1,
            "name": "yh-autoresearch",
            "version": version,
            "execution": "client-side-agent",
            "source_release_sha256": source_release_sha256.lower(),
            "files": files,
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        checksum_lines = [f"{entry['sha256']}  {entry['path']}" for entry in files]
        checksum_lines.append(f"{sha256_file(root / 'manifest.json')}  manifest.json")
        (root / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
                if not path.is_file():
                    continue
                arcname = (Path("yh-autoresearch") / path.relative_to(root)).as_posix()
                info = zipfile.ZipInfo(arcname, date_time=(2026, 8, 24, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())

    result = {
        "output": str(output),
        "sha256": sha256_file(output),
        "size": output.stat().st_size,
        "file_count": len(manifest["files"]) + 2,
        "version": version,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="0.4.0")
    parser.add_argument("--source-release-sha256", required=True)
    args = parser.parse_args()
    result = build_bundle(args.source, args.output, args.version, args.source_release_sha256)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
