import tempfile
import unittest
from pathlib import Path

import social


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = social.Social(social.SqliteStore(Path(self.tmp.name) / "s.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_friend_request_accept_and_remove(self):
        self.assertEqual(self.s.request_friend("1", "가", "2", "나"), "requested")
        self.assertEqual(len(self.s.friends("2")["incoming"]), 1)
        self.assertEqual(self.s.respond_friend("2", "나", "1", True), "accepted")
        self.assertEqual([f["friend"] for f in self.s.friends("1")["friends"]], ["2"])
        self.s.remove_friend("1", "2")
        self.assertEqual(self.s.friends("2")["friends"], [])

    def test_mutual_request_becomes_friends(self):
        self.s.request_friend("1", "가", "2", "나")
        self.assertEqual(self.s.request_friend("2", "나", "1", "가"), "accepted")

    def test_dm_room_is_reused_and_unread_counts(self):
        r1 = self.s.open_room("1", "가", [{"id": "2", "name": "나"}])
        r2 = self.s.open_room("2", "나", [{"id": "1", "name": "가"}])
        self.assertEqual(r1["id"], r2["id"])
        self.s.send("1", "가", r1["id"], "안녕")
        self.s.send("1", "가", r1["id"], "점심?")
        rooms = self.s.rooms("2")
        self.assertEqual(rooms[0]["unread"], 2)
        msgs = self.s.messages("2", r1["id"])
        self.s.mark_read("2", r1["id"], msgs[-1]["id"])
        self.assertEqual(self.s.rooms("2")[0]["unread"], 0)
        self.assertEqual(self.s.messages("2", r1["id"], after=msgs[0]["id"])[0]["body"], "점심?")

    def test_group_room_and_outsider(self):
        room = self.s.open_room("1", "가", [{"id": "2", "name": "나"}, {"id": "3", "name": "다"}], title="점심팟")
        self.s.send("3", "다", room["id"], "좋아요")
        self.assertEqual(self.s.rooms("2")[0]["title"], "점심팟")
        with self.assertRaises(social.SocialError):
            self.s.messages("9", room["id"])

    def test_block_stops_dm_and_notes(self):
        self.s.block("2", "1", "가")
        with self.assertRaises(social.SocialError):
            self.s.open_room("1", "가", [{"id": "2", "name": "나"}])
        with self.assertRaises(social.SocialError):
            self.s.send_note("1", "가", "2", "나", "hi")

    def test_notes_inbox_and_read(self):
        self.s.send_note("1", "가", "2", "나", "회의 10시")
        summary = self.s.summary("2")
        self.assertEqual(summary["unreadNotes"], 1)
        note = self.s.notes("2")["inbox"][0]
        self.s.read_note("2", note["id"])
        self.assertEqual(self.s.summary("2")["unreadNotes"], 0)
        self.assertEqual(self.s.notes("1")["sent"][0]["body"], "회의 10시")

    def test_body_validation(self):
        room = self.s.open_room("1", "가", [{"id": "2", "name": "나"}])
        with self.assertRaises(social.SocialError):
            self.s.send("1", "가", room["id"], "   ")
        with self.assertRaises(social.SocialError):
            self.s.send("1", "가", room["id"], "x" * 2001)


class SupabaseFilterTests(unittest.TestCase):
    def test_filters_quote_and_null(self):
        calls = []
        store = social.SupabaseStore(lambda m, p, body=None, extra_headers=None: calls.append((m, p)) or [])
        store.select("fruit_notes", {"recipient": "2", "read_at": None, "id__gt": 5}, order="id.desc", limit=3)
        path = calls[0][1]
        self.assertIn("recipient=eq.2", path)
        self.assertIn("read_at=is.null", path)
        self.assertIn("id=gt.5", path)
        self.assertIn("order=id.desc", path)



class SocialAvailabilityTests(unittest.TestCase):
    def test_missing_tables_report_unavailable_and_are_rechecked(self):
        from unittest import mock
        import web_server
        web_server._SOCIAL = None
        calls = {"n": 0}

        def missing(method, path, **kwargs):
            calls["n"] += 1
            raise RuntimeError("Supabase 요청 실패: 404 PGRST205")

        with mock.patch.object(web_server, "supabase_config", lambda: {"url": "x", "key": "y"}), \
                mock.patch.object(web_server, "supabase_request", missing):
            for _ in range(2):
                with self.assertRaises(web_server.SocialUnavailable):
                    web_server.social_service()
        self.assertEqual(calls["n"], 2)
        self.assertIsNone(web_server._SOCIAL)


class SocialSendIdempotencyTests(unittest.TestCase):
    """같은 clientId 로 두 번 닿은 전송(재시도·연타)은 한 번만 저장·알림된다."""

    def setUp(self):
        import web_server
        self.ws = web_server
        web_server._SOCIAL_ONCE.clear()
        self.sent = []
        self.pushes = []

        class FakeSvc:
            def send(inner, me, name, room, body):
                self.sent.append((me, room, body))
                return {"id": len(self.sent), "recipients": ["2"]}

            def send_note(inner, me, name, to, to_name, body):
                self.sent.append((me, to, body))
                return {"id": len(self.sent)}

        from unittest import mock
        self.patches = [
            mock.patch.object(web_server, "social_service", lambda: FakeSvc()),
            mock.patch.object(web_server, "social_identity", lambda key: ("1", "가")),
            mock.patch.object(web_server, "social_push", lambda *a, **k: self.pushes.append(a)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.ws._SOCIAL_ONCE.clear()

    def test_send_with_same_client_id_is_stored_once(self):
        payload = {"room": 5, "body": "안녕", "clientId": "c-1"}
        first = self.ws.social_post("/api/social/send", payload, "k")
        second = self.ws.social_post("/api/social/send", dict(payload), "k")
        self.assertEqual(first, second)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.pushes), 1)

    def test_different_client_ids_and_missing_client_id_still_send(self):
        self.ws.social_post("/api/social/send", {"room": 5, "body": "a", "clientId": "c-1"}, "k")
        self.ws.social_post("/api/social/send", {"room": 5, "body": "a", "clientId": "c-2"}, "k")
        self.ws.social_post("/api/social/send", {"room": 5, "body": "a"}, "k")
        self.ws.social_post("/api/social/send", {"room": 5, "body": "a"}, "k")
        self.assertEqual(len(self.sent), 4)

    def test_concurrent_duplicates_run_the_action_once(self):
        import threading
        results = []
        threads = [threading.Thread(target=lambda: results.append(
            self.ws.social_post("/api/social/send", {"room": 5, "body": "동시", "clientId": "c-9"}, "k")))
            for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len({r["id"] for r in results}), 1)

    def test_failed_send_is_not_remembered_so_retry_works(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("일시 오류")
            return {"id": 7}

        with self.assertRaises(RuntimeError):
            self.ws.social_once(("send", "1", "5"), "c-3", flaky)
        self.assertEqual(self.ws.social_once(("send", "1", "5"), "c-3", flaky), {"id": 7})
        self.assertEqual(calls["n"], 2)

    def test_note_with_same_client_id_is_stored_once(self):
        payload = {"to": "2", "toName": "나", "body": "쪽지", "clientId": "n-1"}
        self.ws.social_post("/api/social/note", payload, "k")
        self.ws.social_post("/api/social/note", dict(payload), "k")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(len(self.pushes), 1)
