#!/usr/bin/env python3
import base64
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WWW = ROOT / "www"
ANDROID = ROOT / "mobile-build" / "android-app"
GRADLE = ROOT / "mobile-build" / "gradle" / "bin" / "gradle"
JAVA_HOME = ROOT / "mobile-build" / "jdk21"


def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.write_text(text, encoding="utf-8")


def current_version():
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', read(ROOT / "web_server.py"))
    if not match:
        raise RuntimeError("APP_VERSION not found")
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
    write(path, text)


def update_versions(old, new):
    files = [
        ROOT / "web_server.py",
        WWW / "index.html",
        WWW / "install.html",
        WWW / "app.js",
        WWW / "sw.js",
        ANDROID / "app" / "src" / "main" / "java" / "com" / "openclaw" / "fruitauto" / "MainActivity.java",
    ]
    for path in files:
        replace_version(path, old, new)
    gradle_path = ANDROID / "app" / "build.gradle"
    gradle_text = read(gradle_path)
    gradle_text = re.sub(r"versionCode\s+\d+", f"versionCode {version_code(new)}", gradle_text)
    gradle_text = re.sub(r'versionName\s+"[^"]+"', f'versionName "{new}"', gradle_text)
    write(gradle_path, gradle_text)


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
    (downloads / f"fingerfruit-ios-v{new}.mobileconfig").write_text(text, encoding="utf-8")


def clean_old_downloads(new):
    downloads = WWW / "downloads"
    downloads.mkdir(exist_ok=True)
    for path in downloads.glob("fingerfruit-android-v*.apk"):
        if f"-v{new}." not in path.name:
            path.unlink()
    for path in downloads.glob("fingerfruit-ios-v*.mobileconfig"):
        if f"-v{new}." not in path.name:
            path.unlink()
    mobile_downloads = ROOT / "mobile-build" / "downloads"
    mobile_downloads.mkdir(exist_ok=True)
    for path in mobile_downloads.glob("fingerfruit-android-v*.apk"):
        if f"-v{new}." not in path.name:
            path.unlink()
    for path in mobile_downloads.glob("fingerfruit-ios-v*.mobileconfig"):
        if f"-v{new}." not in path.name:
            path.unlink()


def run(cmd, cwd=None, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def build_android(new):
    env = dict(**__import__("os").environ)
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"] = f"{JAVA_HOME / 'bin'}:{env.get('PATH', '')}"
    env["GRADLE_USER_HOME"] = str(ROOT / "mobile-build" / ".gradle-home")
    run([str(GRADLE), "--no-daemon", ":app:assembleRelease"], cwd=ANDROID, env=env)
    apk = ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if not apk.exists():
        raise RuntimeError("release APK not found")
    versioned = ROOT / "mobile-build" / "downloads" / f"fingerfruit-android-v{new}.apk"
    shutil.copy2(apk, versioned)
    shutil.copy2(versioned, WWW / "downloads" / versioned.name)
    shutil.copy2(versioned, ROOT / "fruit-auto-android.apk")


def copy_ios(new):
    src = WWW / "downloads" / f"fingerfruit-ios-v{new}.mobileconfig"
    dst = ROOT / "mobile-build" / "downloads" / src.name
    shutil.copy2(src, dst)
    shutil.copy2(src, ROOT / "fruit-auto-ios.mobileconfig")


def main():
    old = current_version()
    new = next_version(old)
    print(f"Building fingerfruit {old} -> {new}")
    update_versions(old, new)
    rebuild_ios_profile(old, new)
    clean_old_downloads(new)
    build_android(new)
    copy_ios(new)
    print(json.dumps({"oldVersion": old, "newVersion": new}, ensure_ascii=False))


if __name__ == "__main__":
    main()
