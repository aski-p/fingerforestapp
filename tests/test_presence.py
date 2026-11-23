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

    def test_same_name_old_id_merges_into_new_id_and_photo_moves(self):
        old = "2026-11-10T00:00:00+00:00"
        new = "2026-11-22T00:00:00+00:00"
        rows = [
            {"employee_id": "900", "name": "박승원", "updated_at": old, "profile_image_path": "900/avatar.jpg"},
            {"employee_id": "12", "name": "박승원", "updated_at": new},
            {"employee_id": "901", "name": "전수현", "updated_at": old},
            {"employee_id": "13", "name": "전수현", "updated_at": new, "profile_image_url": "https://x/13.jpg"},
            {"employee_id": "14", "name": "김동명", "updated_at": new},
            {"employee_id": "15", "name": "김동명", "updated_at": new},  # 둘 다 새 ID: 동명이인일 수 있어 그대로
            {"employee_id": "902", "name": "옛사람", "updated_at": old},  # 아직 옛 ID뿐: 그대로
        ]
        people, moves = web_server.merge_profile_rows(rows)
        self.assertEqual(sorted(p["id"] for p in people), ["12", "13", "14", "15", "902"])
        self.assertEqual([(eid, d["employee_id"]) for eid, d in moves], [("12", "900")])

    def test_mark_presence_skips_non_forest_owner(self):
        web_server.mark_presence("legacy-user", now=1)
        self.assertEqual(web_server._PRESENCE, {})


if __name__ == "__main__":
    unittest.main()
