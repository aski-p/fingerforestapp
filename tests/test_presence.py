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

    def test_alias_maps_old_ids_by_new_directory_name(self):
        directory = {"12": "박승원", "13": "전수현", "14": "김동명", "15": "김동명"}
        named = [("20190012", "박승원"), ("forest:20190013", "전수현"), ("20190014", "김동명"), ("20180001", "퇴사자"), ("12", "박승원")]
        self.assertEqual(web_server.build_alias(directory, named), {"20190012": "12", "20190013": "13"})

    def test_friend_rows_move_to_new_ids_and_mutual_requests_become_friends(self):
        import tempfile, social
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        try:
            s = social.Social(social.SqliteStore(Path(tmp.name) / "s.db"))
            s.request_friend("1", "박근형", "20190002", "장미정")   # 나는 장미정의 옛 ID에 신청
            s.request_friend("2", "장미정", "1", "박근형")          # 장미정(새 ID)은 나에게 신청
            s.request_friend("1", "박근형", "20190003", "김혜주")   # 김혜주 옛 ID: 한쪽 신청만
            web_server._ALIAS["map"] = {"20190002": "2", "20190003": "3"}
            web_server.migrate_friend_rows(s.store, web_server._ALIAS["map"])
            self.assertEqual([f["friend"] for f in s.friends("1")["friends"]], ["2"])
            self.assertEqual([f["friend"] for f in s.friends("2")["friends"]], ["1"])
            self.assertEqual([f["friend"] for f in s.friends("1")["outgoing"]], ["3"])
            self.assertEqual([f["friend"] for f in s.friends("3")["incoming"]], ["1"])
            self.assertEqual(s.store.select("fruit_friends", {"owner": "20190002"}), [])
        finally:
            web_server._ALIAS["map"] = {}
            tmp.cleanup()

    def test_people_list_joins_alias_into_new_id_with_old_photo(self):
        users = {"2": {"name": "장미정", "photo": ""}, "20190002": {"name": "장미정", "photo": "old.jpg"}}
        out = web_server.drop_aliases(users, {"20190002": "2"})
        self.assertEqual(out, {"2": {"name": "장미정", "photo": "old.jpg"}})

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
