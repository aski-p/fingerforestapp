import datetime as dt
import multiprocessing
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import fruit_auto
import web_server


class SessionWriteThrottleTests(unittest.TestCase):
    def test_fresh_session_validation_does_not_rewrite_secrets(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        owner_key = "forest:employee-1"
        session = {
            "version": fruit_auto.SESSION_SCHEMA_VERSION,
            "ownerKey": owner_key,
            "createdAt": now.isoformat(),
            "refreshedAt": now.isoformat(),
            "expiresAt": (now + dt.timedelta(seconds=fruit_auto.SESSION_TTL_SECONDS)).isoformat(),
        }
        secrets = {
            "accounts": {owner_key: {"pms_id": "id", "pms_password": "password"}},
            "sessions": {"session-token": session},
        }

        with mock.patch.object(fruit_auto, "load_secrets", return_value=secrets), mock.patch.object(
            fruit_auto, "save_secrets"
        ) as save_secrets:
            result = fruit_auto.owner_from_session("session-token", "device-1")

        self.assertEqual(result, owner_key)
        save_secrets.assert_not_called()

    def test_issue_session_persists_pruned_expired_sessions_after_active_session(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        owner_key = "forest:employee-1"
        active = {
            "version": fruit_auto.SESSION_SCHEMA_VERSION,
            "ownerKey": owner_key,
            "createdAt": now.isoformat(),
            "refreshedAt": now.isoformat(),
            "expiresAt": (now + dt.timedelta(seconds=fruit_auto.SESSION_TTL_SECONDS)).isoformat(),
        }
        expired = {**active, "expiresAt": (now - dt.timedelta(seconds=1)).isoformat()}
        secrets = {
            "accounts": {owner_key: {"pms_id": "id", "pms_password": "password"}},
            "sessions": {"active-token": active, "expired-token": expired},
        }
        with mock.patch.object(fruit_auto, "require_owner", return_value=owner_key), mock.patch.object(
            fruit_auto, "load_secrets", return_value=secrets
        ), mock.patch.object(fruit_auto, "save_secrets") as save_secrets:
            result = fruit_auto.issue_session(owner_key=owner_key)
        self.assertEqual(result["sessionToken"], "active-token")
        self.assertNotIn("expired-token", secrets["sessions"])
        save_secrets.assert_called_once_with(secrets)

    def test_unknown_session_token_does_not_rewrite_secrets(self):
        secrets = {"accounts": {}, "sessions": {}}
        with mock.patch.object(fruit_auto, "load_secrets", return_value=secrets), mock.patch.object(
            fruit_auto, "save_secrets"
        ) as save_secrets:
            self.assertIsNone(fruit_auto.owner_from_session("unknown-token"))
        save_secrets.assert_not_called()

    def test_issue_session_revalidates_owner_inside_transaction(self):
        owner_key = "forest:deleted"
        secrets = {"accounts": {}, "sessions": {}}
        with mock.patch.object(fruit_auto, "require_owner", return_value=owner_key), mock.patch.object(
            fruit_auto, "load_secrets", return_value=secrets
        ), mock.patch.object(fruit_auto, "save_secrets") as save_secrets:
            with self.assertRaises(fruit_auto.FruitAutoError):
                fruit_auto.issue_session(owner_key=owner_key)
        self.assertEqual(secrets["sessions"], {})
        save_secrets.assert_not_called()


class SecretsTransactionTests(unittest.TestCase):
    def test_stale_push_cleanup_only_removes_exact_subscription_snapshot(self):
        owner_key = "forest:owner"
        stale_snapshot = {
            "endpoint": "https://push.example/shared",
            "deviceId": "device-1",
            "updatedAt": "2026-07-16T00:00:00Z",
        }
        refreshed = {**stale_snapshot, "updatedAt": "2026-07-16T00:01:00Z"}
        unchanged = {
            "endpoint": "https://push.example/unchanged",
            "deviceId": "device-2",
            "updatedAt": "2026-07-16T00:00:00Z",
        }
        secrets = {
            "accounts": {owner_key: {}},
            "sessions": {},
            "webPushSubscriptions": {owner_key: [refreshed, unchanged]},
        }
        with mock.patch.object(
            fruit_auto, "mutate_secrets", side_effect=lambda mutator: mutator(secrets)
        ):
            fruit_auto.remove_stale_web_push_subscriptions(
                [(owner_key, stale_snapshot), (owner_key, unchanged)]
            )
        self.assertEqual(secrets["webPushSubscriptions"][owner_key], [refreshed])

    def test_push_subscription_revalidates_owner_inside_transaction(self):
        owner_key = "forest:deleted"
        secrets = {"accounts": {}, "sessions": {}}
        with mock.patch.object(fruit_auto, "require_owner", return_value=owner_key), mock.patch.object(
            fruit_auto, "mutate_secrets", side_effect=lambda mutator: mutator(secrets)
        ):
            with self.assertRaises(fruit_auto.FruitAutoError):
                fruit_auto.save_web_push_subscription(
                    owner_key,
                    {"endpoint": "https://push.example/deleted", "deviceId": "device-1"},
                )
        self.assertNotIn(owner_key, secrets.get("webPushSubscriptions", {}))

    def test_mutate_secrets_serializes_concurrent_read_modify_write(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "SECRETS_PATH", Path(directory) / "secrets.json"
        ):
            fruit_auto.save_secrets({"accounts": {}, "sessions": {}, "counter": 0})

            def increment(secrets):
                current = secrets.get("counter", 0)
                time.sleep(0.002)
                secrets["counter"] = current + 1

            threads = [threading.Thread(target=fruit_auto.mutate_secrets, args=(increment,)) for _ in range(20)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(fruit_auto.load_secrets()["counter"], 20)

    def test_mutate_secrets_serializes_across_processes(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "SECRETS_PATH", Path(directory) / "secrets.json"
        ):
            fruit_auto.save_secrets({"accounts": {}, "sessions": {}, "counter": 0})

            def increment(secrets):
                current = secrets.get("counter", 0)
                time.sleep(0.02)
                secrets["counter"] = current + 1

            context = multiprocessing.get_context("fork")
            processes = [context.Process(target=fruit_auto.mutate_secrets, args=(increment,)) for _ in range(12)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(5)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(fruit_auto.load_secrets()["counter"], 12)

    def test_web_push_writer_cannot_overwrite_concurrent_account_update(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "SECRETS_PATH", Path(directory) / "secrets.json"
        ):
            owner_key = "forest:owner"
            fruit_auto.save_secrets({
                "accounts": {owner_key: {"pms_id": "id", "pms_password": "password"}},
                "sessions": {},
            })
            context = multiprocessing.get_context("fork")
            snapshot_loaded = context.Event()
            resume_writer = context.Event()
            original_load = fruit_auto.load_secrets
            load_count = 0

            def coordinated_load():
                nonlocal load_count
                secrets = original_load()
                if multiprocessing.current_process().name == "push-writer":
                    load_count += 1
                    if load_count == 2:
                        snapshot_loaded.set()
                        resume_writer.wait(5)
                return secrets

            def add_account(secrets):
                secrets.setdefault("accounts", {})["forest:new"] = {
                    "pms_id": "new",
                    "pms_password": "password",
                }
                secrets.setdefault("sessions", {})["new-session"] = {
                    "version": fruit_auto.SESSION_SCHEMA_VERSION,
                    "ownerKey": "forest:new",
                }

            with mock.patch.object(fruit_auto, "load_secrets", side_effect=coordinated_load):
                writer = context.Process(
                    name="push-writer",
                    target=fruit_auto.save_web_push_subscription,
                    args=(owner_key, {"endpoint": "https://push.example/1", "deviceId": "device-1"}),
                )
                writer.start()
                self.assertTrue(snapshot_loaded.wait(5))
                updater = context.Process(target=fruit_auto.mutate_secrets, args=(add_account,))
                updater.start()
                time.sleep(0.1)
                resume_writer.set()
                writer.join(5)
                updater.join(5)
                self.assertEqual(writer.exitcode, 0)
                self.assertEqual(updater.exitcode, 0)
            final = original_load()
            self.assertIn("forest:new", final["accounts"])
            self.assertIn("new-session", final["sessions"])
            self.assertEqual(len(final["webPushSubscriptions"][owner_key]), 1)


class AccountStateIsolationTests(unittest.TestCase):
    def test_full_logout_revokes_all_owner_sessions_and_preserves_other_owner(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "SECRETS_PATH", Path(directory) / "secrets.json"
        ), mock.patch.object(fruit_auto, "STATE_PATH", Path(directory) / "state.json"):
            fruit_auto.save_secrets(
                {
                    "accounts": {"forest:a": {"pms_id": "a"}, "forest:b": {"pms_id": "b"}},
                    "sessions": {
                        "a-1": fruit_auto.new_session_record("forest:a"),
                        "a-2": fruit_auto.new_session_record("forest:a"),
                        "b-1": fruit_auto.new_session_record("forest:b"),
                    },
                    "webPushSubscriptions": {
                        "forest:a": [{"endpoint": "https://push.example/a"}],
                        "forest:b": [{"endpoint": "https://push.example/b"}],
                    },
                }
            )
            account_a = {"ownerKey": "forest:a", "status": "on", "enabled": True, "loginUser": "A"}
            account_b = {"ownerKey": "forest:b", "status": "off", "enabled": False, "loginUser": "B"}
            fruit_auto.save_json(
                fruit_auto.STATE_PATH,
                {"accounts": {"forest:a": account_a, "forest:b": account_b}, "activeOwnerKey": "forest:a"},
            )
            fruit_auto.logout("forest:a", session_token="a-1")
            secrets = fruit_auto.load_secrets()
            state = fruit_auto.load_all_state()
            self.assertEqual(secrets["accounts"], {"forest:b": {"pms_id": "b"}})
            self.assertEqual(set(secrets["sessions"]), {"b-1"})
            self.assertEqual(
                secrets["webPushSubscriptions"],
                {"forest:b": [{"endpoint": "https://push.example/b"}]},
            )
            self.assertEqual(state["accounts"], {"forest:b": account_b})
            self.assertEqual(state["activeOwnerKey"], "forest:b")

    def test_unsubscribe_revalidates_owner_without_creating_orphan_key(self):
        secrets = {"accounts": {}, "sessions": {}}
        with mock.patch.object(fruit_auto, "require_owner", return_value="forest:deleted"), mock.patch.object(
            fruit_auto, "mutate_secrets", side_effect=lambda mutator: mutator(secrets)
        ):
            with self.assertRaises(fruit_auto.FruitAutoError):
                fruit_auto.remove_web_push_subscription("forest:deleted", "https://push.example/old")
        self.assertNotIn("webPushSubscriptions", secrets)

    def test_login_and_logout_serialize_secret_and_state_updates(self):
        owner_key = "forest:a"
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "SECRETS_PATH", Path(directory) / "secrets.json"
        ), mock.patch.object(fruit_auto, "STATE_PATH", Path(directory) / "state.json"):
            fruit_auto.save_secrets(
                {"accounts": {owner_key: {"pms_id": "old"}}, "sessions": {"old": fruit_auto.new_session_record(owner_key)}}
            )
            fruit_auto.save_json(
                fruit_auto.STATE_PATH,
                {"accounts": {owner_key: {"ownerKey": owner_key, "loginUser": "Old"}}, "activeOwnerKey": owner_key},
            )
            state_write_started = threading.Event()
            allow_state_write = threading.Event()
            original_save_account_state = fruit_auto.save_account_state
            errors = []

            def delayed_save_account_state(key, account):
                if threading.current_thread().name == "login-writer":
                    state_write_started.set()
                    allow_state_write.wait(5)
                return original_save_account_state(key, account)

            def login_writer():
                try:
                    fruit_auto.save_credentials("new-id", "new-password")
                except Exception as exc:
                    errors.append(exc)

            def logout_writer():
                try:
                    fruit_auto.logout(owner_key, session_token="old")
                except Exception as exc:
                    errors.append(exc)

            with mock.patch.object(
                fruit_auto, "pms_login", return_value=("pms-token", {"SESS_USERID": "u", "SESS_USERNAME": "New", "SESS_EMPNO": "1"})
            ), mock.patch.object(
                fruit_auto, "forest_login", return_value={"resultMap": [{}]}
            ), mock.patch.object(
                fruit_auto, "employee_identity", return_value=(owner_key, "1", "New")
            ), mock.patch.object(
                fruit_auto, "store_worklog_project_cache"
            ), mock.patch.object(fruit_auto, "save_account_state", side_effect=delayed_save_account_state):
                login_thread = threading.Thread(target=login_writer, name="login-writer")
                logout_thread = threading.Thread(target=logout_writer, name="logout-writer")
                login_thread.start()
                self.assertTrue(state_write_started.wait(5))
                logout_thread.start()
                time.sleep(0.05)
                self.assertTrue(logout_thread.is_alive())
                allow_state_write.set()
                login_thread.join(5)
                logout_thread.join(5)

            self.assertFalse(errors)
            self.assertNotIn(owner_key, fruit_auto.load_secrets().get("accounts", {}))
            self.assertNotIn(owner_key, fruit_auto.load_all_state().get("accounts", {}))

    def test_remove_account_state_preserves_other_accounts(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fruit_auto, "STATE_PATH", Path(directory) / "state.json"
        ):
            for active_owner in ("forest:a", "forest:b"):
                with self.subTest(active_owner=active_owner):
                    account_a = {"ownerKey": "forest:a", "status": "on", "enabled": True}
                    account_b = {"ownerKey": "forest:b", "status": "off", "enabled": False, "loginUser": "B"}
                    fruit_auto.save_json(
                        fruit_auto.STATE_PATH,
                        {
                            "accounts": {"forest:a": account_a, "forest:b": account_b},
                            "activeOwnerKey": active_owner,
                            "status": "on" if active_owner == "forest:a" else "off",
                            "loginUser": "A" if active_owner == "forest:a" else "B",
                        },
                    )
                    fruit_auto.remove_account_state("forest:a")
                    state = fruit_auto.load_all_state()
                    self.assertEqual(state["accounts"], {"forest:b": account_b})
                    self.assertEqual(state["activeOwnerKey"], "forest:b")
                    self.assertEqual(state["loginUser"], "B")


class ProfileLookupCacheTests(unittest.TestCase):
    def setUp(self):
        web_server.clear_profile_photo_cache()

    def tearDown(self):
        web_server.clear_profile_photo_cache()

    def test_identical_profile_lookup_uses_ttl_cache(self):
        rows = [
            {
                "employee_id": "employee-1",
                "name": "사용자",
                "profile_image_url": "https://cdn.example/avatar.png",
                "profile_image_path": "",
                "updated_at": "2026-07-16T00:00:00Z",
            }
        ]
        with mock.patch.object(
            web_server,
            "supabase_config",
            return_value={"url": "https://example.supabase.co", "key": "test", "bucket": "profiles", "table": "profiles"},
        ), mock.patch.object(web_server, "supabase_request", return_value=rows) as request:
            first = web_server.list_profile_photos(["employee-1"])
            second = web_server.list_profile_photos(["employee-1"])

        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)


class WorklogProjectCacheTests(unittest.TestCase):
    def setUp(self):
        fruit_auto.clear_worklog_project_cache()

    def tearDown(self):
        fruit_auto.clear_worklog_project_cache()

    def test_identical_project_lookup_avoids_reauthentication(self):
        employee_info = {
            "projEmp": [{"proj_id": "P1", "proj_nm": "프로젝트 1"}],
            "projInner": [{"proj_id": "P2", "proj_nm": "프로젝트 2"}],
        }
        login_result = (object(), employee_info, {}, {}, "employee-1", "사용자")
        with mock.patch.object(fruit_auto, "require_owner", return_value="forest:employee-1"), mock.patch.object(
            fruit_auto, "account_login", return_value=login_result
        ) as account_login:
            first = fruit_auto.list_worklog_projects(owner_key="forest:employee-1")
            second = fruit_auto.list_worklog_projects(owner_key="forest:employee-1")

        self.assertEqual(first, second)
        self.assertEqual(account_login.call_count, 1)

    def test_login_employee_info_can_seed_project_cache(self):
        owner_key = "forest:employee-1"
        employee_info = {
            "projEmp": [{"proj_id": "P1", "proj_nm": "프로젝트 1"}],
            "projInner": [],
        }
        fruit_auto.store_worklog_project_cache(
            owner_key,
            fruit_auto.worklog_projects_from_employee_info(employee_info),
        )
        with mock.patch.object(fruit_auto, "require_owner", return_value=owner_key), mock.patch.object(
            fruit_auto, "account_login"
        ) as account_login:
            projects = fruit_auto.list_worklog_projects(owner_key=owner_key)
        self.assertEqual(projects, [{"id": "P1", "name": "프로젝트 1", "source": "projEmp"}])
        account_login.assert_not_called()


class StaticCachePolicyTests(unittest.TestCase):
    def test_versioned_assets_are_immutable_but_html_is_not(self):
        immutable = "public, max-age=31536000, immutable"
        no_store = "no-store, no-cache, max-age=0, must-revalidate"
        self.assertEqual(web_server.static_cache_control("/app.js", "v=3.16.1"), immutable)
        self.assertEqual(web_server.static_cache_control("/styles.css", "v=3.16.1"), immutable)
        self.assertEqual(web_server.static_cache_control("/request_coordinator.js", "v=3.16.1"), immutable)
        self.assertEqual(web_server.static_cache_control("/app.js", "v=0.0.0"), no_store)
        self.assertEqual(web_server.static_cache_control("/app.js", "v=999.999.999"), no_store)
        self.assertEqual(web_server.static_cache_control("/app.js", ""), no_store)
        self.assertEqual(web_server.static_cache_control("/", ""), no_store)
        self.assertEqual(web_server.static_cache_control("/install.html", ""), no_store)


class FrontendRequestPolicyTests(unittest.TestCase):
    def test_frontend_avoids_redundant_saved_login_and_android_no_cache(self):
        root = Path(__file__).resolve().parents[1]
        app_source = (root / "www" / "app.js").read_text(encoding="utf-8")
        android_source = (
            root
            / "mobile-build"
            / "android-app"
            / "app"
            / "src"
            / "main"
            / "java"
            / "com"
            / "openclaw"
            / "fruitauto"
            / "MainActivity.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn('api("/api/saved-login")', app_source)
        self.assertIn("WebSettings.LOAD_DEFAULT", android_source)
        self.assertNotIn("WebSettings.LOAD_NO_CACHE", android_source)


if __name__ == "__main__":
    unittest.main()
