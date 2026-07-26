from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest import mock

import build_fingerfruit_release as release_builder
import web_server


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "3.16.2"
ANDROID_VERSION = "3.16.0"
EXPECTED_ANDROID_SIGNER = "b2f3480a6d039ec381884e01a57e00c0ee1e31bcf1fe5d76ded97a4c2db47aec"


class ReleaseConsistencyTests(unittest.TestCase):
    def test_release_notes_only_describe_current_update(self):
        self.assertEqual(
            [
                "업무시간에만 자동전송을 켜면 주말과 공휴일에는 보내지 않고 다음 업무일로 연기합니다.",
                "열매선물 랭킹에서 내 순위와 선물한 열매 수가 0으로 표시되던 문제를 수정했습니다.",
            ],
            web_server.RELEASE_NOTES,
        )

    def test_canonical_sources_use_expected_platform_versions(self):
        checks = {
            "web_server.py": f'APP_VERSION = "{EXPECTED_VERSION}"',
            "www/app.js": f'const appVersion = "{EXPECTED_VERSION}"',
            "www/index.html": f"v{EXPECTED_VERSION} 정식버전",
            "www/install.html": f"v{EXPECTED_VERSION} 정식버전",
            "mobile-build/android-app/app/build.gradle": f'versionName "{ANDROID_VERSION}"',
            "mobile-build/android-app/app/src/main/java/com/openclaw/fruitauto/MainActivity.java": f'APP_VERSION = "{ANDROID_VERSION}"',
        }
        for relative, expected in checks.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(expected, text, relative)
        self.assertIn("versionCode 31600", (ROOT / "mobile-build/android-app/app/build.gradle").read_text(encoding="utf-8"))
        for relative in ("www/app.js", "www/index.html", "www/sw.js", "www/styles.css"):
            self.assertNotIn("3.16.1", (ROOT / relative).read_text(encoding="utf-8"), relative)

    def test_app_info_and_install_page_reference_existing_platform_artifacts(self):
        info = web_server.app_info(None)
        self.assertEqual(info["latestVersion"], EXPECTED_VERSION)
        self.assertEqual(info["iosVersion"], EXPECTED_VERSION)
        self.assertEqual(info["androidVersion"], ANDROID_VERSION)
        self.assertTrue(info["iosProfileUrl"].endswith(f"fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig"))
        self.assertTrue(info["androidApkUrl"].endswith(f"fingerfruit-android-v{ANDROID_VERSION}.apk"))
        install = (ROOT / "www" / "install.html").read_text(encoding="utf-8")
        self.assertIn(f"fingerfruit-android-v{ANDROID_VERSION}.apk", install)
        self.assertIn(f"Android APK v{ANDROID_VERSION}", install)
        self.assertIn(f"fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig", install)

    def test_release_artifacts_exist_and_embed_platform_versions(self):
        apk = ROOT / "www" / "downloads" / f"fingerfruit-android-v{ANDROID_VERSION}.apk"
        ios = ROOT / "www" / "downloads" / f"fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig"
        self.assertTrue(apk.is_file())
        self.assertTrue(ios.is_file())
        self.assertIn(f"v={EXPECTED_VERSION}", ios.read_text(encoding="utf-8"))
        with zipfile.ZipFile(apk) as archive:
            manifest = archive.read("AndroidManifest.xml")
        self.assertIn(ANDROID_VERSION.encode("utf-16le"), manifest)

    def test_ios_profiles_have_no_trailing_whitespace(self):
        for path in (
            ROOT / f"www/downloads/fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig",
            ROOT / "fruit-auto-ios.mobileconfig",
        ):
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, [line.rstrip() for line in lines], path)

    def test_convenience_artifacts_match_advertised_downloads(self):
        self.assertEqual(
            (ROOT / "fruit-auto-android.apk").read_bytes(),
            (ROOT / f"www/downloads/fingerfruit-android-v{ANDROID_VERSION}.apk").read_bytes(),
        )
        self.assertEqual(
            (ROOT / "fruit-auto-ios.mobileconfig").read_bytes(),
            (ROOT / f"www/downloads/fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig").read_bytes(),
        )

    def test_public_clients_do_not_embed_shared_bearer_token(self):
        android_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "mobile-build/android-app/app/src/main/java").rglob("*.java")
        )
        public_clients = [
            android_sources,
            (ROOT / "www/downloads/fingerfruit-ios-v3.16.2.mobileconfig").read_text(encoding="utf-8"),
            (ROOT / "fruit-auto-ios.mobileconfig").read_text(encoding="utf-8"),
            (ROOT / "www/app.js").read_text(encoding="utf-8"),
            (ROOT / "www/single.html").read_text(encoding="utf-8"),
        ]
        server = (ROOT / "web_server.py").read_text(encoding="utf-8")
        for source in public_clients:
            self.assertNotIn("X-Fruit-Token", source)
            self.assertNotRegex(source, r"[?&](?:amp;)?token=")
            self.assertNotIn("FRUIT_TOKEN", source)
        self.assertNotIn("FRUIT_AUTO_WEB_TOKEN", server)
        self.assertNotIn("def require_auth", server)
        self.assertNotIn("X-Fruit-Token", server)

    def test_frontend_invalidates_all_authenticated_request_gates(self):
        app = (ROOT / "www/app.js").read_text(encoding="utf-8")
        clear_start = app.index("function clearSessionStorage()")
        clear_end = app.index("\n}\n", clear_start)
        clear_body = app[clear_start:clear_end]
        self.assertIn("sessionEpoch += 1", clear_body)
        self.assertIn("refreshRequestGate.clear()", clear_body)
        self.assertIn("notificationRequestGate.clear()", clear_body)
        self.assertIn("worklogProjectLoader.clear()", clear_body)
        self.assertIn("requestEpoch !== sessionEpoch", app)
        self.assertIn("recoveringSession = null", clear_body)
        self.assertIn("if (requestEpoch === sessionEpoch)", app)

    def test_android_artifact_retains_update_compatible_signer(self):
        apksigner = Path(
            shutil.which("apksigner")
            or "/opt/data/cache/fingerforest-android/sdk/build-tools/35.0.0/apksigner"
        )
        apk = ROOT / "www" / "downloads" / f"fingerfruit-android-v{ANDROID_VERSION}.apk"
        if not apksigner.is_file():
            self.skipTest("apksigner is unavailable")
        result = subprocess.run(
            [str(apksigner), "verify", "--print-certs", str(apk)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(EXPECTED_ANDROID_SIGNER, result.stdout)

    def test_release_builder_updates_styles(self):
        source = (ROOT / "build_fingerfruit_release.py").read_text(encoding="utf-8")
        update_block = re.search(r"def update_versions\(.*?\n\n", source, re.S)
        self.assertIsNotNone(update_block)
        self.assertIn('WWW / "styles.css"', update_block.group(0))

    def test_cleanup_preserves_split_platform_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            www = root / "www"
            public_downloads = www / "downloads"
            mobile_downloads = root / "mobile-build" / "downloads"
            public_downloads.mkdir(parents=True)
            mobile_downloads.mkdir(parents=True)
            for downloads in (public_downloads, mobile_downloads):
                for name in (
                    "fingerfruit-android-v3.16.0.apk",
                    "fingerfruit-android-v3.15.6.apk",
                    "fingerfruit-ios-v3.16.1.mobileconfig",
                    "fingerfruit-ios-v3.16.0.mobileconfig",
                ):
                    (downloads / name).write_bytes(b"artifact")
            with mock.patch.object(release_builder, "ROOT", root), mock.patch.object(
                release_builder, "WWW", www
            ):
                release_builder.clean_old_downloads("3.16.1", "3.16.0")
            for downloads in (public_downloads, mobile_downloads):
                self.assertTrue((downloads / "fingerfruit-android-v3.16.0.apk").exists())
                self.assertTrue((downloads / "fingerfruit-ios-v3.16.1.mobileconfig").exists())
                self.assertFalse((downloads / "fingerfruit-android-v3.15.6.apk").exists())
                self.assertFalse((downloads / "fingerfruit-ios-v3.16.0.mobileconfig").exists())

    def test_android_signer_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "app.apk"
            apk.write_bytes(b"not-used-by-fake-signer")
            apksigner = root / "apksigner"
            apksigner.write_text(
                "#!/bin/sh\necho 'Signer #1 certificate SHA-256 digest: deadbeef'\n",
                encoding="utf-8",
            )
            apksigner.chmod(0o700)
            with self.assertRaisesRegex(RuntimeError, "signer"):
                release_builder.verify_android_signer(apk, apksigner=apksigner)

    def test_android_signer_spoofed_certificate_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "app.apk"
            apk.write_bytes(b"not-used-by-fake-signer")
            apksigner = root / "apksigner"
            apksigner.write_text(
                "#!/bin/sh\n"
                "echo 'Signer #1 certificate SHA-256 digest: deadbeef'\n"
                f"echo 'Signer #1 certificate DN: CN={EXPECTED_ANDROID_SIGNER}'\n",
                encoding="utf-8",
            )
            apksigner.chmod(0o700)
            with self.assertRaisesRegex(RuntimeError, "signer"):
                release_builder.verify_android_signer(apk, apksigner=apksigner)

    def test_android_extra_signer_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "app.apk"
            apk.write_bytes(b"not-used-by-fake-signer")
            apksigner = root / "apksigner"
            apksigner.write_text(
                "#!/bin/sh\n"
                f"echo 'Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}'\n"
                "echo 'Signer #2 certificate SHA-256 digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n",
                encoding="utf-8",
            )
            apksigner.chmod(0o700)
            with self.assertRaisesRegex(RuntimeError, "signer"):
                release_builder.verify_android_signer(apk, apksigner=apksigner)

    def test_android_signer_rejects_unaccounted_and_noncanonical_records(self):
        cases = [
            f"Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}\nSigner #2 certificate DN: CN=Other\n",
            f"Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}\nSigner #2 certificate SHA-256 digest: not-hex\n",
            f"Signer #1 certificate SHA-256 digest: :{EXPECTED_ANDROID_SIGNER}:\n",
            f"Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER[:2]}::{EXPECTED_ANDROID_SIGNER[2:]}\n",
            f"Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}\nprefix Signer #2 certificate DN: CN=Other\n",
            f" Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}\n",
            f"\tSigner #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}\n",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apk = root / "app.apk"
            apk.write_bytes(b"not-used-by-fake-signer")
            apksigner = root / "apksigner"
            for index, output in enumerate(cases):
                apksigner.write_text(
                    "#!/bin/sh\nprintf '%b' " + repr(output) + "\n",
                    encoding="utf-8",
                )
                apksigner.chmod(0o700)
                with self.subTest(case=index), self.assertRaisesRegex(RuntimeError, "signer"):
                    release_builder.verify_android_signer(apk, apksigner=apksigner)

    def test_android_signer_verifier_supplies_java_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            java = java_home / "bin" / "java"
            java.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            java.chmod(0o700)
            apk = root / "app.apk"
            apk.write_bytes(b"not-used-by-fake-signer")
            apksigner = root / "apksigner"
            apksigner.write_text(
                "#!/bin/sh\n"
                "test -x \"$JAVA_HOME/bin/java\" || exit 127\n"
                f"echo 'Signer #1 certificate SHA-256 digest: {EXPECTED_ANDROID_SIGNER}'\n",
                encoding="utf-8",
            )
            apksigner.chmod(0o700)
            with mock.patch.dict(os.environ, {"JAVA_HOME": "", "PATH": "/usr/bin:/bin"}), mock.patch.object(
                release_builder, "JAVA_HOME", java_home
            ):
                release_builder.verify_android_signer(apk, apksigner=apksigner)

    def test_build_android_creates_download_directory_after_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            android = root / "mobile-build" / "android-app"
            apk = android / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
            apk.parent.mkdir(parents=True)
            apk.write_bytes(b"verified-apk")
            www = root / "www"
            (www / "downloads").mkdir(parents=True)
            java_home = root / "jdk"
            (java_home / "bin").mkdir(parents=True)
            with mock.patch.object(release_builder, "ROOT", root), mock.patch.object(
                release_builder, "WWW", www
            ), mock.patch.object(release_builder, "ANDROID", android), mock.patch.object(
                release_builder, "JAVA_HOME", java_home
            ), mock.patch.object(release_builder, "GRADLE", root / "gradle"), mock.patch.object(
                release_builder, "run"
            ), mock.patch.object(release_builder, "verify_android_signer") as verify:
                release_builder.build_android("3.16.1")
            verify.assert_called_once_with(apk)
            self.assertEqual(
                (root / "mobile-build" / "downloads" / "fingerfruit-android-v3.16.1.apk").read_bytes(),
                b"verified-apk",
            )

    def test_copy_ios_creates_mobile_download_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            www = root / "www"
            source = www / "downloads" / "fingerfruit-ios-v3.16.1.mobileconfig"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"ios-profile")
            with mock.patch.object(release_builder, "ROOT", root), mock.patch.object(
                release_builder, "WWW", www
            ):
                release_builder.copy_ios("3.16.1")
            self.assertEqual(
                (root / "mobile-build" / "downloads" / source.name).read_bytes(),
                b"ios-profile",
            )

    def test_default_release_preserves_android_version_without_building(self):
        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(
            release_builder, "current_version", return_value="3.16.1"
        ), mock.patch.object(release_builder, "next_version", return_value="3.16.2"), mock.patch.object(
            release_builder, "current_android_version", return_value="3.16.0"
        ), mock.patch.object(release_builder, "update_versions"), mock.patch.object(
            release_builder, "rebuild_ios_profile"
        ), mock.patch.object(release_builder, "copy_ios"), mock.patch.object(
            release_builder, "clean_old_downloads"
        ) as clean, mock.patch.object(release_builder, "build_android") as build:
            os.environ.pop("FINGERFRUIT_BUILD_ANDROID", None)
            release_builder.main()
        build.assert_not_called()
        clean.assert_called_once_with("3.16.2", "3.16.0")


if __name__ == "__main__":
    unittest.main()
