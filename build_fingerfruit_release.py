#!/usr/bin/env python3
import base64
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WWW = ROOT / "www"
ANDROID = ROOT / "mobile-build" / "android-app"
LOCAL_MOBILE_BUILD = ROOT / "mobile-build"
STATE_MOBILE_BUILD = ROOT.parent / "state" / "fruit-auto" / "mobile-build"
EXPECTED_ANDROID_SIGNER_SHA256 = "19657138bba6fb9186d885c42eab5142710b147401e49abb2bbc0f12d01b50e7"
GRADLE = Path(os.environ.get("GRADLE_HOME") or LOCAL_MOBILE_BUILD / "gradle") / "bin" / "gradle"
JAVA_HOME = Path(os.environ.get("JAVA_HOME") or LOCAL_MOBILE_BUILD / "jdk21")
if not GRADLE.exists():
    GRADLE = STATE_MOBILE_BUILD / "gradle" / "bin" / "gradle"
if not (JAVA_HOME / "bin" / "java").exists():
    JAVA_HOME = STATE_MOBILE_BUILD / "jdk21"


def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.write_text(text, encoding="utf-8")


def strip_trailing_whitespace(text):
    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(line.rstrip() for line in text.splitlines()) + trailing_newline


def current_version():
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', read(ROOT / "web_server.py"))
    if not match:
        raise RuntimeError("APP_VERSION not found")
    return match.group(1)


def current_android_version():
    match = re.search(r'ANDROID_APP_VERSION\s*=\s*"([^"]+)"', read(ROOT / "web_server.py"))
    if not match:
        raise RuntimeError("ANDROID_APP_VERSION not found")
    return match.group(1)


def next_version(version):
    parts = [int(part) for part in version.split(".")]
    if len(parts) == 2:
        parts.append(0)
    parts[-1] += 1
    if parts[-1] >= 10:
        parts[-1] = 0
        parts[-2] += 1
    return ".".join(str(part) for part in parts)


def version_code(version):
    major, minor, patch = [int(part) for part in version.split(".")]
    return major * 10000 + minor * 100 + patch


def replace_version(path, old, new):
    text = read(path).replace(old, new)
    text = re.sub(r"v\d+\.\d+\.\d+ 정식버전 · by aski", f"v{new} 정식버전 · by aski", text)
    text = re.sub(
        r"(?:app-touch-icon|app-icon-192)\.png\?v=\d+\.\d+\.\d+",
        lambda match: match.group(0).split("?")[0] + f"?v={new}",
        text,
    )
    text = re.sub(
        r"(?:styles\.css|app\.js)\?v=\d+\.\d+\.\d+",
        lambda match: match.group(0).split("?")[0] + f"?v={new}",
        text,
    )
    write(path, text)


def profile_url_for_version(match, version):
    url = re.sub(r"([?&](?:amp;)?v=)\d+\.\d+\.\d+", "", match.group(2))
    separator = "&amp;" if "?" in url else "?"
    return f"{match.group(1)}{url}{separator}v={version}{match.group(3)}"


def update_versions(old, new):
    files = [
        ROOT / "web_server.py",
        WWW / "index.html",
        WWW / "install.html",
        WWW / "app.js",
        WWW / "sw.js",
        WWW / "styles.css",
    ]
    for path in files:
        replace_version(path, old, new)


def update_android_source_version(new):
    main_activity = ANDROID / "app" / "src" / "main" / "java" / "com" / "openclaw" / "fruitauto" / "MainActivity.java"
    main_text = re.sub(r'APP_VERSION\s*=\s*"[^"]+"', f'APP_VERSION = "{new}"', read(main_activity))
    write(main_activity, main_text)
    gradle_path = ANDROID / "app" / "build.gradle"
    gradle_text = re.sub(r"versionCode\s+\d+", f"versionCode {version_code(new)}", read(gradle_path))
    gradle_text = re.sub(r'versionName\s+"[^"]+"', f'versionName "{new}"', gradle_text)
    write(gradle_path, gradle_text)


def update_android_release_references(old, new):
    server_path = ROOT / "web_server.py"
    server_text = re.sub(
        r'ANDROID_APP_VERSION\s*=\s*"[^"]+"',
        f'ANDROID_APP_VERSION = "{new}"',
        read(server_path),
        count=1,
    )
    write(server_path, server_text)
    install_path = WWW / "install.html"
    install_text = read(install_path)
    install_text = install_text.replace(f"fingerfruit-android-v{old}.apk", f"fingerfruit-android-v{new}.apk")
    install_text = install_text.replace(f"Android APK v{old}", f"Android APK v{new}")
    write(install_path, install_text)


def rebuild_ios_profile(old, new):
    downloads = WWW / "downloads"
    template = downloads / f"fingerfruit-ios-v{old}.mobileconfig"
    if not template.exists():
        candidates = sorted(downloads.glob("fingerfruit-ios-v*.mobileconfig"))
        if not candidates:
            return
        template = candidates[-1]
    text = read(template)
    icon_data = base64.b64encode((WWW / "icons" / "app-icon-192.png").read_bytes()).decode("ascii")
    icon_data = "\n".join("\t\t\t" + line for line in textwrap.wrap(icon_data, 64))
    text = re.sub(
        r"(<key>Icon</key>\s*<data>\s*).*?(\s*</data>)",
        r"\1\n" + icon_data + r"\2",
        text,
        count=1,
        flags=re.S,
    )
    text = text.replace(old, new)
    text = re.sub(
        r"(<key>URL</key>\s*<string>)([^<]*)(</string>)",
        lambda match: profile_url_for_version(match, new),
        text,
        count=1,
        flags=re.S,
    )
    text = strip_trailing_whitespace(text)
    (downloads / f"fingerfruit-ios-v{new}.mobileconfig").write_text(text, encoding="utf-8")


def clean_old_downloads(ios_version, android_version):
    downloads = WWW / "downloads"
    downloads.mkdir(exist_ok=True)
    for path in downloads.glob("fingerfruit-android-v*.apk"):
        if f"-v{android_version}." not in path.name:
            path.unlink()
    for path in downloads.glob("fingerfruit-ios-v*.mobileconfig"):
        if f"-v{ios_version}." not in path.name:
            path.unlink()
    mobile_downloads = ROOT / "mobile-build" / "downloads"
    mobile_downloads.mkdir(exist_ok=True)
    for path in mobile_downloads.glob("fingerfruit-android-v*.apk"):
        if f"-v{android_version}." not in path.name:
            path.unlink()
    for path in mobile_downloads.glob("fingerfruit-ios-v*.mobileconfig"):
        if f"-v{ios_version}." not in path.name:
            path.unlink()


def run(cmd, cwd=None, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def find_apksigner():
    configured = os.environ.get("APKSIGNER")
    if configured:
        return Path(configured)
    found = shutil.which("apksigner")
    if found:
        return Path(found)
    sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if sdk_root:
        candidates = sorted((Path(sdk_root) / "build-tools").glob("*/apksigner"), reverse=True)
        if candidates:
            return candidates[0]
    raise RuntimeError("apksigner is required to verify the Android release signer")


def verify_android_signer(apk, apksigner=None):
    apksigner = Path(apksigner) if apksigner else find_apksigner()
    env = dict(os.environ)
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"] = f"{JAVA_HOME / 'bin'}:{env.get('PATH', '')}"
    result = subprocess.run(
        [str(apksigner), "verify", "--print-certs", str(apk)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    output = result.stdout + result.stderr
    output_lines = output.splitlines()
    signer_lines = [line for line in output_lines if "Signer #" in line]
    if any(not line.startswith("Signer #") for line in signer_lines):
        raise RuntimeError("Android release signer output is malformed")
    signer_indices = set()
    for line in signer_lines:
        signer_match = re.match(r"^Signer #(\d+)\s", line)
        if not signer_match:
            raise RuntimeError("Android release signer output is malformed")
        signer_indices.add(signer_match.group(1))
    digest_prefix = "Signer #1 certificate SHA-256 digest:"
    digest_records = [line for line in signer_lines if "certificate SHA-256 digest:" in line]
    if signer_indices != {"1"} or len(digest_records) != 1 or not digest_records[0].startswith(digest_prefix):
        raise RuntimeError("Android release signer set does not match the authorized update-compatible signer")
    digest = digest_records[0][len(digest_prefix):].strip()
    plain_digest = re.fullmatch(r"[0-9a-fA-F]{64}", digest)
    colon_digest = re.fullmatch(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){31}", digest)
    if not plain_digest and not colon_digest:
        raise RuntimeError("Android release signer digest format is not canonical")
    normalized_digest = digest.replace(":", "").lower()
    if normalized_digest != EXPECTED_ANDROID_SIGNER_SHA256:
        raise RuntimeError("Android release signer set does not match the authorized update-compatible signer")


def build_android(new):
    env = dict(os.environ)
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"] = f"{JAVA_HOME / 'bin'}:{env.get('PATH', '')}"
    env["GRADLE_USER_HOME"] = str(ROOT / "mobile-build" / ".gradle-home")
    run([str(GRADLE), "--no-daemon", ":app:assembleRelease"], cwd=ANDROID, env=env)
    apk = ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if not apk.exists():
        raise RuntimeError("release APK not found")
    verify_android_signer(apk)
    versioned = ROOT / "mobile-build" / "downloads" / f"fingerfruit-android-v{new}.apk"
    versioned.parent.mkdir(parents=True, exist_ok=True)
    (WWW / "downloads").mkdir(parents=True, exist_ok=True)
    shutil.copy2(apk, versioned)
    shutil.copy2(versioned, WWW / "downloads" / versioned.name)
    shutil.copy2(versioned, ROOT / "fruit-auto-android.apk")


def copy_ios(new):
    src = WWW / "downloads" / f"fingerfruit-ios-v{new}.mobileconfig"
    dst = ROOT / "mobile-build" / "downloads" / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    shutil.copy2(src, ROOT / "fruit-auto-ios.mobileconfig")


def main():
    old = current_version()
    new = next_version(old)
    android_version = current_android_version()
    print(f"Building fingerfruit {old} -> {new} (Android {android_version})")
    update_versions(old, new)
    rebuild_ios_profile(old, new)
    if os.environ.get("FINGERFRUIT_BUILD_ANDROID") == "1":
        update_android_source_version(new)
        build_android(new)
        update_android_release_references(android_version, new)
        android_version = new
    copy_ios(new)
    clean_old_downloads(new, android_version)
    print(json.dumps({"oldVersion": old, "newVersion": new, "androidVersion": android_version}, ensure_ascii=False))


if __name__ == "__main__":
    main()
