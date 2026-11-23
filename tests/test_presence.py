import unittest
from unittest import mock

import web_server


class PresenceTests(unittest.TestCase):
    def setUp(self):
        web_server._PRESENCE.clear()
        web_server._USER_LIST.update({"at": 0.0, "users": {}})

    def tearDown(self):
        web_server._PRESENCE.clear()
        web_server._USER_LIST.update({"at": 0.0, "users": {}})

    def people(self, now, rows, accounts=None):
        with mock.patch.object(web_server, "supabase_config", return_value={"table": "profiles"}), \
             mock.patch.object(web_server, "supabase_request", return_value=rows), \
             mock.patch.object(web_server.fruit_auto, "load_all_state", return_value={"accounts": accounts or {}}):
            return web_server.social_people("1", now=now)

    def test_online_within_90_seconds_and_total_includes_offline(self):
        web_server.mark_presence("forest:1", now=1000)
        web_server.mark_presence("forest:2", now=1000)
        web_server.mark_presence("forest:3", now=850)  # 150초 전: 오프라인
        rows = [{"employee_id": "1", "name": "가"}, {"employee_id": "2", "name": "나"},
                {"employee_id": "3", "name": "다"}, {"employee_id": "forest:4", "name": "라"}]
        p = self.people(1000, rows)
        self.assertEqual(p["total"], 4)
        self.assertEqual(p["online"], 2)
        self.assertEqual([u["id"] for u in p["items"]][:2], ["1", "2"])  # 나 먼저, 그다음 접속자
        self.assertTrue(p["items"][0]["me"])
        self.assertEqual({u["id"] for u in p["items"] if not u["online"]}, {"3", "4"})

    def test_local_accounts_fill_in_and_bad_ids_are_ignored(self):
        rows = [{"employee_id": "forest:x", "name": "?"}]
        p = self.people(1000, rows, accounts={"forest:7": {"senderEmployeeId": "7", "senderEmployeeName": "사"}})
        self.assertEqual([(u["id"], u["name"]) for u in p["items"]], [("7", "사")])

    def test_old_ids_merge_by_new_directory_and_photo_moves(self):
        directory = {"12": "박승원", "13": "전수현", "14": "김동명", "15": "김동명", "16": "고성진", "1": "박근형"}
        rows = [
            {"employee_id": "900", "name": "박승원", "profile_image_path": "900/avatar.jpg", "updated_at": "2026-11-10"},
            {"employee_id": "12", "name": "박승원", "updated_at": "2026-11-22"},
            {"employee_id": "901", "name": "전수현", "profile_image_url": "https://x/901.jpg"},
            {"employee_id": "13", "name": "전수현", "profile_image_url": "https://x/13.jpg"},
            {"employee_id": "902", "name": "김동명"},            # 새 목록에 동명이인 둘: 건드리지 않음
            {"employee_id": "14", "name": "김동명"},
            {"employee_id": "903", "name": "퇴사자"},            # 새 목록에 없음: 그대로
            {"employee_id": "904", "name": "고성진"},            # 새 ID로 아직 접속 안 함(행 없음): 그대로
            {"employee_id": "forest:905", "name": "박근형", "profile_image_path": "905/a.jpg"},
            {"employee_id": "1", "name": "박근형"},
        ]
        plans = web_server.plan_old_id_merges(rows, directory)
        got = {(old, new, donor["employee_id"] if donor else None) for old, new, donor in plans}
        self.assertEqual(got, {("900", "12", "900"), ("901", "13", None), ("forest:905", "1", "forest:905")})

    def test_hide_old_ids_keeps_new_and_carries_photo(self):
        directory = {"12": "박승원", "14": "김동명", "15": "김동명"}
        users = {"12": {"name": "박승원", "photo": ""}, "900": {"name": "박승원", "photo": "p.jpg"},
                 "14": {"name": "김동명", "photo": ""}, "902": {"name": "김동명", "photo": ""}}
        out = web_server.hide_old_ids(users, directory)
        self.assertEqual(out["12"]["photo"], "p.jpg")
        self.assertNotIn("900", out)
        self.assertIn("902", out)  # 동명이인이면 그대로

    def test_mark_presence_skips_non_forest_owner(self):
        web_server.mark_presence("legacy-user", now=1)
        self.assertEqual(web_server._PRESENCE, {})


if __name__ == "__main__":
    unittest.main()
