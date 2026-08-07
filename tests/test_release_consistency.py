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
EXPECTED_VERSION = "3.17.1"
ANDROID_VERSION = "3.16.0"
EXPECTED_ANDROID_SIGNER = "b2f3480a6d039ec381884e01a57e00c0ee1e31bcf1fe5d76ded97a4c2db47aec"


class ReleaseConsistencyTests(unittest.TestCase):
    def test_status_messages_remain_legible_over_illustrated_skins(self):
        css = (ROOT / "www/styles.css").read_text(encoding="utf-8")
        self.assertIn("background: rgba(15, 23, 42, 0.9);", css)
        self.assertIn("body .toast {\n  color: #ffffff;", css)
        self.assertIn(".toast:empty {\n  display: none;", css)

    def test_busy_overlay_uses_a_character_only_transparent_loading_gif(self):
        html = (ROOT / "www/index.html").read_text(encoding="utf-8")
        css = (ROOT / "www/styles.css").read_text(encoding="utf-8")
        app = (ROOT / "www/app.js").read_text(encoding="utf-8")
        gif = ROOT / "www/assets/fingerfruit-loading.gif"

        self.assertTrue(gif.is_file())
        self.assertEqual(b"GIF89a", gif.read_bytes()[:6])
        self.assertIn('id="busyOverlay"', html)
        self.assertIn(f'/assets/fingerfruit-loading.gif?v={EXPECTED_VERSION}', html)
        self.assertIn('<strong>로딩중이에요</strong>', html)
        self.assertNotIn('작업 중이에요', html)
        self.assertIn('role="status"', html)
        self.assertIn('.busy-overlay', css)
        self.assertRegex(
            css,
            r"\.busy-overlay-card\s*\{[^}]*border:\s*0;[^}]*background:\s*transparent;[^}]*box-shadow:\s*none;",
        )

        probe = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,nb_frames", "-of", "csv=p=0", str(gif),
            ],
            text=True,
        ).strip().split(",")
        width, height, frame_count = map(int, probe)
        self.assertEqual(frame_count, 8)
        self.assertLessEqual(width, 272)
        self.assertLessEqual(height, 320)

        rgba = subprocess.check_output(
            [
                "ffmpeg", "-v", "error", "-i", str(gif), "-vf", "select=eq(n\\,0)",
                "-frames:v", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "-",
            ]
        )
        self.assertEqual(len(rgba), width * height * 4)
        alpha = rgba[3::4]
        self.assertGreater(alpha.count(0), width * height // 3)
        self.assertTrue(all(alpha[index] == 0 for index in (0, width - 1, width * (height - 1), width * height - 1)))
        self.assertIn('$("busyOverlay").hidden = !busy', app)
        self.assertIn('$("busyOverlay").setAttribute("aria-hidden", String(!busy))', app)

    def test_login_id_fields_allow_text_keyboard_input(self):
        for relative_path in ("www/index.html", "www/single.html"):
            html = (ROOT / relative_path).read_text(encoding="utf-8")
            login_input = re.search(r'<input\s+[^>]*id="loginId"[^>]*>', html)
            self.assertIsNotNone(login_input, relative_path)
            markup = login_input.group(0)
            self.assertIn('type="text"', markup, relative_path)
            self.assertIn('inputmode="text"', markup, relative_path)
            self.assertNotIn('inputmode="numeric"', markup, relative_path)

    def test_nested_busy_operations_keep_overlay_visible_until_all_finish(self):
        app = (ROOT / "www/app.js").read_text(encoding="utf-8")
        self.assertIn("let busyDepth = 0;", app)
        self.assertIn("busyDepth += 1", app)
        self.assertIn("busyDepth = Math.max(0, busyDepth - 1)", app)
        self.assertIn("busy = busyDepth > 0", app)

    def test_release_notes_only_describe_current_update(self):
        self.assertEqual(
            [
                "열매선물 랭킹을 조회 목록 순서대로 1등부터 5등까지만 표시합니다.",
                "5위 밖의 사용자는 순위 대신 본인의 열매선물 갯수를 안내합니다.",
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
        self.assertIn(
            f"versionCode {release_builder.version_code(ANDROID_VERSION)}",
            (ROOT / "mobile-build/android-app/app/build.gradle").read_text(encoding="utf-8"),
        )
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
            (ROOT / f"www/downloads/fingerfruit-ios-v{EXPECTED_VERSION}.mobileconfig").read_text(encoding="utf-8"),
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

    def test_frontend_logout_preserves_valid_opted_in_credentials_and_clears_others(self):
        app = (ROOT / "www/app.js").read_text(encoding="utf-8")

        remembered_start = app.index("function clearRememberedLogin()")
        remembered_end = app.index("\n}\n", remembered_start)
        remembered_body = app[remembered_start:remembered_end]
        for key in ("rememberLoginKey", "rememberedLoginIdKey", "rememberedLoginPwKey"):
            self.assertIn(f"storeRemove({key})", remembered_body)
        self.assertIn('$("rememberLogin").checked = false', remembered_body)
        self.assertIn('$("loginId").value = ""', remembered_body)
        self.assertIn('$("loginPw").value = ""', remembered_body)

        preserve_start = app.index("function shouldPreserveRememberedLogin()")
        preserve_end = app.index("\n}\n", preserve_start)
        preserve_body = app[preserve_start:preserve_end]
        for key in ("rememberLoginKey", "rememberedLoginIdKey", "rememberedLoginPwKey"):
            self.assertIn(f"storeGet({key})", preserve_body)

        guarded_clear = "if (!shouldPreserveRememberedLogin()) clearRememberedLogin();"
        authenticated_start = app.index("function clearAuthenticatedUi()")
        authenticated_end = app.index("\n}\n", authenticated_start)
        self.assertIn(guarded_clear, app[authenticated_start:authenticated_end])

        logout_start = app.index('$("logoutBtn").addEventListener')
        logout_end = app.index("\n});", logout_start)
        logout_body = app[logout_start:logout_end]
        self.assertIn(guarded_clear, logout_body)
        self.assertNotIn("loadRememberedLogin()", logout_body)

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
