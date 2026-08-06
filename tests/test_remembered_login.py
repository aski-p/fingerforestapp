import json
import re
import subprocess
from pathlib import Path
from unittest import TestCase, main


APP_JS = Path(__file__).resolve().parents[1] / "www" / "app.js"


def extract_function(source: str, name: str) -> str:
    match = re.search(rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", source)
    if not match:
        raise AssertionError(f"function {name} not found")
    start = match.start()
    brace = source.find("{", match.start())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"function {name} is incomplete")


def extract_block_after(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"block marker not found: {marker}")
    brace = source.find("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"block is incomplete: {marker}")


def extract_event_handler_body(source: str, marker: str) -> str:
    block = extract_block_after(source, marker)
    brace = block.find("{")
    return block[brace + 1:-1]


class TestRememberedLogin(TestCase):
    def test_preserves_only_explicitly_checked_complete_credentials(self):
        source = APP_JS.read_text(encoding="utf-8")
        helper = extract_function(source, "shouldPreserveRememberedLogin")
        script = f"""
const rememberLoginKey = "remember";
const rememberedLoginIdKey = "id";
const rememberedLoginPwKey = "pw";
let values = {{}};
function storeGet(key) {{ return values[key] || ""; }}
{helper}
const cases = [
  [{{ remember: "1", id: "user", pw: "secret" }}, true],
  [{{ remember: "0", id: "user", pw: "secret" }}, false],
  [{{ remember: "1", id: "", pw: "secret" }}, false],
  [{{ remember: "1", id: "user", pw: "" }}, false],
];
for (const [input, expected] of cases) {{
  values = input;
  if (shouldPreserveRememberedLogin() !== expected) {{
    throw new Error(JSON.stringify({{ input, expected }}));
  }}
}}
"""
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_logout_paths_clear_credentials_only_without_valid_remember_opt_in(self):
        source = APP_JS.read_text(encoding="utf-8")
        auth_cleanup = extract_function(source, "clearAuthenticatedUi")
        explicit_logout = extract_block_after(
            source,
            '$("logoutBtn").addEventListener("click", async () =>',
        )
        expected_guard = "if (!shouldPreserveRememberedLogin()) clearRememberedLogin();"
        self.assertIn(expected_guard, auth_cleanup)
        self.assertIn(expected_guard, explicit_logout)

    def test_security_migration_preserves_opted_in_credentials_but_clears_sessions(self):
        source = APP_JS.read_text(encoding="utf-8")
        helper = extract_function(source, "shouldPreserveRememberedLogin")
        migration = extract_function(source, "runSecurityMigration")
        script = f"""
const securityMigrationKey = "migration";
const fruitSessionKey = "session";
const fruitOwnerKey = "owner";
const cachedStateKey = "cache";
const rememberLoginKey = "remember";
const rememberedLoginIdKey = "id";
const rememberedLoginPwKey = "pw";
const loggedOutKey = "loggedOut";
let values = {{}};
let nativeRemoved = [];
function storeGet(key) {{ return values[key] || ""; }}
function storeSet(key, value) {{ values[key] = String(value); }}
function storeRemove(key) {{ delete values[key]; }}
const window = {{ FruitAndroid: {{
  saveSession(value) {{ values.nativeSession = value; }},
  removeLocal(key) {{ nativeRemoved.push(key); }},
}} }};
{helper}
{migration}
values = {{
  session: "token", owner: "owner-1", cache: "cached",
  remember: "1", id: "user", pw: "secret",
}};
runSecurityMigration();
if (values.remember !== "1" || values.id !== "user" || values.pw !== "secret") {{
  throw new Error("opted-in credentials were removed");
}}
if (values.session || values.owner || values.cache) throw new Error("session state survived migration");
if (nativeRemoved.includes("remember") || nativeRemoved.includes("id") || nativeRemoved.includes("pw")) {{
  throw new Error("native opted-in credentials were removed");
}}
values = {{ id: "stale-user", pw: "stale-secret" }};
nativeRemoved = [];
runSecurityMigration();
if (values.id || values.pw) throw new Error("non-opted-in credentials survived migration");
if (!nativeRemoved.includes("id") || !nativeRemoved.includes("pw")) {{
  throw new Error("native non-opted-in credentials survived migration");
}}
"""
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_logout_always_clears_local_and_native_session_even_when_api_fails(self):
        source = APP_JS.read_text(encoding="utf-8")
        handler = extract_event_handler_body(
            source,
            '$("logoutBtn").addEventListener("click", async () =>',
        )
        script = f"""
let apiError = null;
let preserveRememberedLogin = true;
let clearSessionCalls = 0;
let clearRememberCalls = 0;
let rendered = null;
let busy = [];
let messages = [];
let fields = {{ results: {{ innerHTML: "x" }}, searchInput: {{ value: "x" }} }};
function $(id) {{ return fields[id]; }}
async function api() {{
  if (apiError) throw apiError;
  return {{ loggedIn: false }};
}}
function clearSessionStorage() {{ clearSessionCalls += 1; }}
function clearAuthenticatedUi() {{ clearSessionStorage(); }}
function shouldPreserveRememberedLogin() {{ return preserveRememberedLogin; }}
function clearRememberedLogin() {{ clearRememberCalls += 1; }}
const sessionKey = "fruitSession";
const sessionStorage = {{ removeItem() {{}} }};
function renderState(value) {{ rendered = value; }}
function closeHistoryModal() {{}}
function toast(value) {{ messages.push(value); }}
function setBusy(value) {{ busy.push(value); }}
async function logoutHandler() {{
{handler}
}}
for (const preserve of [true, false]) {{
  preserveRememberedLogin = preserve;
  for (const error of [null, new Error("로그인 세션 만료"), new Error("network unavailable")]) {{
    apiError = error;
    clearSessionCalls = 0;
    clearRememberCalls = 0;
    rendered = null;
    busy = [];
    messages = [];
    await logoutHandler();
    if (clearSessionCalls !== 1) throw new Error(`session not cleared for ${{preserve}}/${{error}}`);
    const expectedRememberClears = preserve ? 0 : 1;
    if (clearRememberCalls !== expectedRememberClears) {{
      throw new Error(`wrong credential cleanup for ${{preserve}}/${{error}}`);
    }}
    if (busy.join(",") !== "true,false") throw new Error(`busy not settled for ${{preserve}}/${{error}}`);
  }}
}}
"""
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    main()
