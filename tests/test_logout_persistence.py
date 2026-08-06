"""
Test: UI settings survive logout (remove_account_state path).

This test simulates the API logout flow and verifies that all UI settings
(theme, font, skin, giftMessage, deliveryCycle, pushEnabled, etc.) are
preserved across logout/login cycles.
"""

import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path
from unittest import TestCase, main, mock

# Setup paths before importing fruit_auto
TEST_DIR = tempfile.mkdtemp()
STATE_PATH = Path(TEST_DIR) / "state.json"
SECRETS_PATH = Path(TEST_DIR) / "secrets.json"

# Mock the module-level paths in fruit_auto
import fruit_auto as fa

_original_state_path = fa.STATE_PATH
_original_secrets_path = fa.SECRETS_PATH

fa.STATE_PATH = STATE_PATH
fa.SECRETS_PATH = SECRETS_PATH


class TestLogoutPersistence(TestCase):
    """Verify UI settings persist across logout."""

    def setUp(self):
        """Create a fresh state and secrets for each test."""
        # Restore temp paths BEFORE any file operations (tearDown restores
        # them to the original — we must re-apply).
        fa.STATE_PATH = STATE_PATH
        fa.SECRETS_PATH = SECRETS_PATH
        STATE_PATH.unlink(missing_ok=True)
        SECRETS_PATH.unlink(missing_ok=True)
        # Write a minimal initial state
        fa.save_json(STATE_PATH, fa.DEFAULT_STATE.copy())
        fa.save_json(SECRETS_PATH, {"accounts": {}, "sessions": {}})

    def tearDown(self):
        """Restore original paths."""
        STATE_PATH.unlink(missing_ok=True)
        SECRETS_PATH.unlink(missing_ok=True)
        fa.STATE_PATH = _original_state_path
        fa.SECRETS_PATH = _original_secrets_path

    def _create_test_account(self, owner_key="test_user"):
        """Create a test account with UI settings in secrets."""
        secrets = {
            "accounts": {
                owner_key: {
                    "pms_id": "test@example.com",
                    "pms_password": "secret123",
                    "ownerKey": owner_key,
                    # UI settings
                    "theme": "dark",
                    "font": "inter",
                    "skin": "forest",
                    "giftMessage": "수고했어!",
                    "sendBerryCount": 3,
                    "sendAllBerries": True,
                    "businessHoursOnly": False,
                    "pushEnabled": True,
                    "deliveryCycle": "mon-fri",
                    "deliveryCycleIndex": 0,
                    "deliveryCycleCompletedCount": 5,
                }
            },
            "sessions": {},
            "webPushSubscriptions": {owner_key: []},
        }
        fa.save_json(SECRETS_PATH, secrets)
        # Create account state in state.json (simulating login)
        account = secrets["accounts"][owner_key].copy()
        fa.save_account_state(owner_key, account)
        return account

    def test_remove_account_state_preserves_ui_settings(self):
        """remove_account_state() must preserve UI settings from the account."""
        self._create_test_account()

        # Call remove_account_state (this is the logout path)
        result = fa.remove_account_state("test_user")
        state_post = fa.load_json(STATE_PATH, fa.DEFAULT_STATE)

        # All UI settings should be in the returned state
        self.assertEqual(result.get("theme"), "dark", "theme should be preserved")
        self.assertEqual(result.get("font"), "inter", "font should be preserved")
        self.assertEqual(result.get("skin"), "forest", "skin should be preserved")
        self.assertEqual(result.get("giftMessage"), "수고했어!", "giftMessage should be preserved")
        self.assertEqual(result.get("sendBerryCount"), 3, "sendBerryCount should be preserved")
        self.assertEqual(result.get("sendAllBerries"), True, "sendAllBerries should be preserved")
        self.assertEqual(result.get("businessHoursOnly"), False, "businessHoursOnly should be preserved")
        self.assertEqual(result.get("pushEnabled"), True, "pushEnabled should be preserved")
        self.assertEqual(result.get("deliveryCycle"), "mon-fri", "deliveryCycle should be preserved")

        # state.json should also have these values mirrored at top level
        state = fa.load_json(STATE_PATH, fa.DEFAULT_STATE)
        self.assertEqual(state.get("theme"), "dark", "state.json theme should be preserved")
        self.assertEqual(state.get("font"), "inter", "state.json font should be preserved")
        self.assertEqual(state.get("giftMessage"), "수고했어!", "state.json giftMessage should be preserved")

        # The account should be removed
        self.assertIsNone(state.get("accounts", {}).get("test_user"), "account should be removed")
        self.assertEqual(state.get("activeOwnerKey"), None, "activeOwnerKey should be None")

    def test_multiple_logout_preserves_settings(self):
        """Settings should survive multiple consecutive logout/login cycles."""
        self._create_test_account()

        for i in range(3):
            # Logout removes the account
            result = fa.remove_account_state("test_user")

            # Verify settings survived
            self.assertEqual(result.get("theme"), "dark",
                           f"theme survived logout #{i+1}")
            self.assertEqual(result.get("giftMessage"), "수고했어!",
                           f"giftMessage survived logout #{i+1}")

            # Simulate re-login by recreating the account with same settings
            account = {
                "pms_id": "test@example.com",
                "pms_password": "secret123",
                "ownerKey": "test_user",
                "theme": "dark",
                "font": "inter",
                "skin": "forest",
                "giftMessage": "수고했어!",
                "sendBerryCount": 3,
                "sendAllBerries": True,
                "businessHoursOnly": False,
                "pushEnabled": True,
            }
            secrets = fa.load_json(SECRETS_PATH, {})
            secrets["accounts"]["test_user"] = account
            fa.save_json(SECRETS_PATH, secrets)
            fa.save_account_state("test_user", account)

    def test_logout_resets_operational_fields(self):
        """Operational fields should be reset, not preserved."""
        self._create_test_account()

        # Set some operational fields
        state = fa.load_json(STATE_PATH, fa.DEFAULT_STATE)
        state["enabled"] = True
        state["status"] = "running"
        state["lastResult"] = "success"
        state["loginSavedAt"] = "2024-01-01T00:00:00"
        fa.save_json(STATE_PATH, state)

        result = fa.remove_account_state("test_user")

        # Operational fields should be reset
        self.assertEqual(result.get("enabled"), False, "enabled should be reset")
        self.assertEqual(result.get("status"), "off", "status should be reset")
        self.assertEqual(result.get("lastResult"), "logged_out", "lastResult should be reset")
        self.assertEqual(result.get("loginSavedAt"), None, "loginSavedAt should be reset")

        # But UI settings should survive
        self.assertEqual(result.get("theme"), "dark", "theme should survive")
        self.assertEqual(result.get("giftMessage"), "수고했어!", "giftMessage should survive")

    def test_ui_settings_in_accounts_dict_preserved(self):
        """Settings stored in the accounts dict must be preserved too."""
        # Use save_account_state to create the account properly (ensures mirror logic runs)
        account = {
            "pms_id": "test@example.com",
            "pms_password": "secret123",
            "ownerKey": "test_user",
            "theme": "dark",
            "font": "roboto",
            "skin": "night",
            "giftMessage": "고마워!",
        }
        fa.save_account_state("test_user", account)

        result = fa.remove_account_state("test_user")

        self.assertEqual(result.get("theme"), "dark", "theme from account dict preserved")
        self.assertEqual(result.get("font"), "roboto", "font from account dict preserved")
        self.assertEqual(result.get("skin"), "night", "skin from account dict preserved")
        self.assertEqual(result.get("giftMessage"), "고마워!", "giftMessage from account dict preserved")

    def test_empty_account_logout(self):
        """Logout with no account should not crash."""
        result = fa.remove_account_state("nonexistent_user")
        self.assertIsInstance(result, dict, "Should return a dict even for nonexistent users")
        self.assertEqual(result.get("enabled"), False)
        self.assertEqual(result.get("status"), "off")

    def test_relogin_restores_persisted_account_settings_from_supabase(self):
        """A fresh login must hydrate settings instead of relying on local state."""
        owner_key = "forest:1001"
        persisted = {
            "theme": "dark",
            "giftMessage": "수고했어!",
            "targetEmployeeId": "2002",
            "targetEmployeeName": "테스트 대상",
            "targetCycle": [{"emp_id": "2002", "emp_nm": "테스트 대상"}],
            "sendBerryCount": 3,
            "sendAllBerries": True,
            "businessHoursOnly": True,
            "runIntervalMinutes": 90,
            "pushEnabled": False,
            "worklogScheduleDays": [1, 3, 5],
            "worklogScheduleTime": "10:15",
            "worklogProjectId": "project-7",
            "worklogContent": "주간 보고",
        }

        with mock.patch.object(fa, "_load_state_from_supabase", return_value=persisted) as load_remote:
            restored = fa.get_account_state(owner_key, hydrate_remote=True)

        load_remote.assert_called_once_with(owner_key)
        for key, value in persisted.items():
            self.assertEqual(restored.get(key), value, f"{key} should be restored after relogin")
        self.assertFalse(restored["enabled"], "automation must not restart just because settings were restored")

    def test_fresh_remote_round_trip_restores_only_the_authenticated_owner(self):
        rows = {}

        def fake_request(method, path, body=None, extra_headers=None):
            if method == "POST":
                rows[str(body["employee_id"])] = dict(body)
                return [body]
            query = urllib.parse.urlparse(path).query
            employee_filter = urllib.parse.parse_qs(query).get("employee_id", [""])[0]
            employee_id = urllib.parse.unquote(employee_filter.removeprefix("eq."))
            return [rows[employee_id]] if employee_id in rows else []

        first_owner = "forest:1001"
        second_owner = "forest:2002"
        with mock.patch.object(fa, "_supabase_config", return_value={
            "url": "https://example.supabase.co",
            "key": "test-service-key",
            "table": "profiles",
        }), mock.patch.object(fa, "_supabase_request", side_effect=fake_request):
            fa._save_state_to_supabase(first_owner, {"accounts": {first_owner: {
                "theme": "dark",
                "giftMessage": "첫 번째 계정",
                "pms_password": "must-not-persist",
                "enabled": True,
            }}})
            fa._save_state_to_supabase(second_owner, {"accounts": {second_owner: {
                "theme": "light",
                "giftMessage": "두 번째 계정",
                "pms_password": "must-not-persist-either",
            }}})

            fa.save_json(fa.STATE_PATH, fa.DEFAULT_STATE)
            first = fa.get_account_state(first_owner, hydrate_remote=True)
            second = fa.get_account_state(second_owner, hydrate_remote=True)

        self.assertEqual(first["theme"], "dark")
        self.assertEqual(first["giftMessage"], "첫 번째 계정")
        self.assertEqual(second["theme"], "light")
        self.assertEqual(second["giftMessage"], "두 번째 계정")
        self.assertFalse(first["enabled"])
        self.assertNotIn("pms_password", rows["1001"]["state"])
        self.assertNotIn("pms_password", rows["2002"]["state"])

    def test_supabase_state_snapshot_uses_employee_id_and_excludes_runtime_and_secrets(self):
        owner_key = "forest:1001"
        account = {
            "ownerKey": owner_key,
            "senderEmployeeId": "1001",
            "senderEmployeeName": "테스트 사용자",
            "targetEmployeeId": "2002",
            "giftMessage": "고마워!",
            "worklogScheduleTime": "10:15",
            "theme": "dark",
            "enabled": True,
            "lastAttemptAt": "2026-08-06T00:00:00+00:00",
            "pms_id": "private-id",
            "pms_password": "private-password",
        }
        state = {"accounts": {owner_key: account}}
        calls = []

        with mock.patch.object(fa, "_supabase_config", return_value={"table": "profiles", "key": "service-key"}), mock.patch.object(
            fa, "_supabase_request", side_effect=lambda method, path, **kwargs: calls.append((method, path, kwargs)) or []
        ):
            self.assertTrue(fa._save_state_to_supabase(owner_key, state))

        body = calls[0][2]["body"]
        self.assertEqual(body["employee_id"], "1001")
        self.assertEqual(body["state"]["targetEmployeeId"], "2002")
        self.assertEqual(body["state"]["worklogScheduleTime"], "10:15")
        self.assertEqual(body["state"]["theme"], "dark")
        self.assertNotIn("enabled", body["state"])
        self.assertNotIn("lastAttemptAt", body["state"])
        self.assertNotIn("pms_id", body["state"])
        self.assertNotIn("pms_password", body["state"])

    def test_supabase_row_identity_comes_only_from_owner_key(self):
        owner_key = "forest:1001"
        state = {"accounts": {owner_key: {
            "senderEmployeeId": "9999",
            "senderEmployeeName": "테스트 사용자",
            "theme": "dark",
        }}}
        calls = []
        with mock.patch.object(fa, "_supabase_config", return_value={"table": "profiles", "key": "service-key"}), mock.patch.object(
            fa, "_supabase_request", side_effect=lambda method, path, **kwargs: calls.append((method, path, kwargs)) or []
        ):
            self.assertTrue(fa._save_state_to_supabase(owner_key, state))
        self.assertEqual(calls[0][2]["body"]["employee_id"], "1001")

    def test_logout_never_copies_unexpected_credentials_into_state(self):
        owner_key = "forest:1001"
        account = {
            "ownerKey": owner_key,
            "theme": "dark",
            "pms_id": "private-id",
            "pms_password": "private-password",
            "access_token": "private-token",
        }
        fa.save_account_state(owner_key, account)
        logged_out = fa.remove_account_state(owner_key)
        on_disk = json.loads(fa.STATE_PATH.read_text())
        for key in ("pms_id", "pms_password", "access_token"):
            self.assertNotIn(key, logged_out)
            self.assertNotIn(key, on_disk)

    def test_remote_hydration_failure_falls_back_to_local_state(self):
        owner_key = "forest:1001"
        fa.save_account_state(owner_key, {"ownerKey": owner_key, "theme": "local-dark"})
        with mock.patch.object(fa, "_load_state_from_supabase", side_effect=OSError("offline")):
            restored = fa.get_account_state(owner_key, hydrate_remote=True)
        self.assertEqual(restored["theme"], "local-dark")

    def test_profile_settings_rows_are_not_misread_as_login_credentials(self):
        rows = [{"employee_id": "1001", "state": {
            "theme": "dark",
            "giftMessage": "고마워!",
            "pms_id": "legacy-private-id",
            "pms_password": "legacy-private-password",
        }}]
        with mock.patch.object(fa, "_supabase_config", return_value={"table": "profiles", "key": "service-key"}), mock.patch.object(
            fa, "_supabase_request", return_value=rows
        ):
            self.assertIsNone(fa._load_secrets_from_supabase())


if __name__ == "__main__":
    # Suppress the default state warning that's noisy in test output
    sys.exit(main(verbosity=2) or 0)
