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
