from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from server.access_host import AccessConfig, make_handler, verify_token
from http.server import ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "skills" / "yh-autoresearch-access" / "scripts" / "install_yh_autoresearch.py"
SPEC = importlib.util.spec_from_file_location("yh_installer", INSTALLER_PATH)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def make_test_bundle(path: Path) -> bytes:
    skill = b"---\nname: yh-autoresearch\ndescription: test bundle\n---\n# Test\n"
    entry = {"path": "SKILL.md", "sha256": hashlib.sha256(skill).hexdigest(), "size": len(skill)}
    manifest = json.dumps({
        "schema_version": 1,
        "name": "yh-autoresearch",
        "version": "0.4.0-test",
        "execution": "client-side-agent",
        "files": [entry],
    }).encode()
    checksums = f"{entry['sha256']}  SKILL.md\n".encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("yh-autoresearch/SKILL.md", skill)
        archive.writestr("yh-autoresearch/manifest.json", manifest)
        archive.writestr("yh-autoresearch/checksums.sha256", checksums)
    return path.read_bytes()


class AccessFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bundle_path = self.root / "bundle.zip"
        self.bundle = make_test_bundle(self.bundle_path)
        self.config = AccessConfig(
            access_code="AC19N",
            session_secret=b"test-session-secret-that-is-long-enough",
            bundle_path=self.bundle_path,
            token_ttl_seconds=60,
            secure_cookie=False,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.config))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_wrong_code_rejected(self) -> None:
        request = urllib.request.Request(
            self.base_url + "/api/activate",
            data=b'{"code":"wrong"}',
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 401)

    def test_literal_code_activation_download_and_install(self) -> None:
        data, digest = installer.activate_and_download(self.base_url, "ac-19-n")
        self.assertEqual(data, self.bundle)
        self.assertEqual(digest, hashlib.sha256(self.bundle).hexdigest())
        destination = self.root / "installed" / "yh-autoresearch"
        manifest, backup = installer.install_bundle(data, destination)
        self.assertEqual(manifest["version"], "0.4.0-test")
        self.assertIsNone(backup)
        self.assertTrue((destination / "SKILL.md").is_file())

    def test_nato_spoken_code_alias(self) -> None:
        data, _ = installer.activate_and_download(self.base_url, "Alpha Charlie 19 Nato")
        self.assertEqual(data, self.bundle)

    def test_expired_token_rejected(self) -> None:
        from server.access_host import issue_token

        token = issue_token(self.config, now=100)
        self.assertTrue(verify_token(self.config, token, now=120))
        self.assertFalse(verify_token(self.config, token, now=161))

    def test_path_traversal_bundle_rejected(self) -> None:
        path = self.root / "unsafe.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../escape.txt", "bad")
        with self.assertRaisesRegex(RuntimeError, "unsafe archive path"):
            installer.install_bundle(path.read_bytes(), self.root / "unsafe-install")

    def test_unlisted_bundle_file_rejected(self) -> None:
        path = self.root / "extra.zip"
        make_test_bundle(path)
        rewritten = self.root / "extra-rewritten.zip"
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(rewritten, "w") as target:
            for item in source.infolist():
                target.writestr(item, source.read(item.filename))
            target.writestr("yh-autoresearch/unlisted.txt", "not in manifest")
        with self.assertRaisesRegex(RuntimeError, "file set"):
            installer.install_bundle(rewritten.read_bytes(), self.root / "extra-install")

    def test_built_v4_bundle_end_to_end_when_present(self) -> None:
        real_bundle = ROOT / "dist" / "yh-autoresearch-0.4.0.zip"
        if not real_bundle.is_file():
            self.skipTest("built v4 bundle is not present")
        config = AccessConfig(
            access_code="AC19N",
            session_secret=b"real-bundle-test-secret-that-is-long-enough",
            bundle_path=real_bundle,
            token_ttl_seconds=60,
            secure_cookie=False,
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            data, digest = installer.activate_and_download(base_url, "AlphaCharlie19Nato")
            self.assertEqual(digest, hashlib.sha256(real_bundle.read_bytes()).hexdigest())
            destination = self.root / "real-install" / "yh-autoresearch"
            manifest, backup = installer.install_bundle(data, destination)
            self.assertEqual(manifest["version"], "0.4.0")
            self.assertEqual(manifest["execution"], "client-side-agent")
            self.assertIsNone(backup)
            self.assertTrue((destination / "shared" / "skills" / "frontier-autoresearch" / "SKILL.md").is_file())
            self.assertFalse((destination / ".autoresearch").exists())
            self.assertFalse((destination / "runs").exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
