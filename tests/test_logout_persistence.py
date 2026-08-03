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
from pathlib import Path
from unittest import TestCase, main

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


if __name__ == "__main__":
    # Suppress the default state warning that's noisy in test output
    sys.exit(main(verbosity=2) or 0)
