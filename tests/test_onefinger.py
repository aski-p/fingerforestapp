import datetime as dt
import unittest
from unittest import mock

import fruit_auto
import onefinger


class FakeOneFinger:
    """새 OneFinger 응답 흉내(직원·잔고·프로젝트·내역·달력·업무일지)."""

    def __init__(self, worklog=None):
        self.employee = {"id": "900001", "employeeNo": "20160301", "name": "박근형", "organizationName": "개발팀", "positionName": "차장"}
        self.saved = []
        self.gifts = []
        self.current_worklog = worklog

    def employees(self):
        return [
            {"id": "900001", "employeeNo": "20160301", "name": "박근형", "active": True},
            {"id": "900002", "employeeNo": "20180101", "name": "장미정", "organizationName": "운영팀", "positionName": "차장", "active": True},
        ]

    def balance(self, month, gift_view=False):
        return {"giftableFruit": 7, "fruitAvailable": 9} if gift_view else {"seedAvailable": 3, "fruitAvailable": 9}

    def projects(self, at):
        return [{"id": "5001", "name": "드롭데이"}, {"id": "5002", "name": "포털", "writableAtDate": False}]

    def ledger(self, month):
        return [
            {"postedAt": "2026-11-18T05:00:00Z", "asset": "fruit", "delta": 2, "displayText": "장미정님이 열매를 보냈어요", "giftMessages": []},
            {"postedAt": "2026-11-18T06:00:00Z", "asset": "seed", "delta": -1, "displayText": "씨앗 선물", "giftMessages": [{"recipientId": "900002", "message": "고마워요"}]},
        ]

    def worklog_calendar(self, month):
        return [{"date": "2026-11-17", "state": "approved", "approvedTotal": 3}, {"date": "2026-11-18", "state": "pending", "approvedTotal": 0}]

    def worklog(self, date):
        return self.current_worklog

    def save_worklog(self, date, body):
        self.saved.append((date, body))

    def give_fruit(self, employee_id, amount, message):
        self.gifts.append((employee_id, amount, message))


class OneFingerPortTests(unittest.TestCase):
    def test_forest_login_shapes_like_the_old_api(self):
        info = fruit_auto.forest_login(FakeOneFinger())
        self.assertEqual("900001", info["resultMap"][0]["emp_id"])
        self.assertEqual("3", info["forestAuth"][0]["seedCnt"])
        self.assertEqual([{"proj_id": "5001", "proj_nm": "드롭데이"}], info["projEmp"], "only projects writable today")

    def test_balance_uses_giftable_fruit(self):
        self.assertEqual((3, 7), fruit_auto.current_seed_fruit(FakeOneFinger()))

    def test_ledger_rows_keep_the_old_history_shape(self):
        fruit_auto._EMPLOYEE_NAMES["at"] = 0.0
        rows = fruit_auto._ledger_rows(FakeOneFinger(), "202611")
        self.assertEqual("18일", rows[0]["stdDt"])  # 05:00Z = 14:00 KST on the 18th
        self.assertEqual(2, rows[0]["stdDBerryPmCnt"])
        self.assertEqual("장미정", rows[0]["tgtEmpNm"], "the sender found in the display text")
        self.assertIn("씨앗", rows[1]["tgtMsg"])
        self.assertEqual("장미정", rows[1]["tgtEmpNm"], "the recipient from the gift message")

    def test_approval_rows_from_the_calendar(self):
        rows = fruit_auto._approval_rows(FakeOneFinger(), "202611")
        self.assertEqual(1, len(rows))
        self.assertEqual("work_approval", fruit_auto.berry_history_reward_kind(rows[0]["tgtMsg"]))
        self.assertEqual(17, fruit_auto.work_approval_message_day(rows[0]["tgtMsg"]))

    def test_worklog_goes_to_the_new_forest_with_the_seed_gift(self):
        client = FakeOneFinger(worklog={"version": 2, "scheduledMinutes": 480, "items": []})
        info = fruit_auto.forest_login(client)
        state = {"worklogProjectId": "old-77", "worklogProjectName": "드롭데이", "worklogContent": "출시 준비",
                 "worklogTargetEmployeeId": "OLD-ID", "worklogTargetEmployeeName": "장미정", "worklogSeedMessage": "수고했어요"}
        result = fruit_auto._save_worklog_onefinger(client, info, state, dt.date(2026, 11, 19), 2)
        self.assertEqual("saved", result)
        date, body = client.saved[0]
        self.assertEqual("2026-11-19", date)
        self.assertEqual(2, body["expectedVersion"])
        self.assertEqual("5001", body["items"][0]["projectId"], "the old project id is found by name")
        self.assertEqual(480, body["items"][0]["minutes"])
        self.assertEqual({"recipients": [{"employeeId": "900002", "amount": 2, "message": "수고했어요"}]}, body["seedGift"], "the old target id is found by name")

    def test_worklog_never_overwrites_a_written_day(self):
        client = FakeOneFinger(worklog={"version": 3, "items": [{"id": "1"}]})
        state = {"worklogProjectId": "5001", "worklogProjectName": "드롭데이", "worklogContent": "x"}
        self.assertEqual("exists", fruit_auto._save_worklog_onefinger(client, fruit_auto.forest_login(client), state, dt.date(2026, 11, 19), 0))
        self.assertEqual([], client.saved)

    def test_fruit_gift_goes_to_fruit_gifts(self):
        client = FakeOneFinger()
        info = fruit_auto.forest_login(client)
        fruit_auto.give_all_berries(client, info, {"emp_id": "900002", "emp_nm": "장미정"}, 5, "감사")
        self.assertEqual([("900002", 5, "감사")], client.gifts)

    def test_login_form_parsing(self):
        html = '<form id="login-form" method="post" action="/login?login_challenge=abc&amp;x=1"><input type="hidden" name="csrf" value="tok&amp;en"><input name="employee_no"></form>'
        self.assertEqual({"csrf": "tok&en", "action": "/login?login_challenge=abc&x=1"}, onefinger.parse_login_form(html))
        bad = '<p id="login-error" role="alert">사번 또는 비밀번호가 일치하지 않습니다.</p>'
        self.assertEqual("invalid_credentials", onefinger.classify_login_failure(bad, 200))

    def test_sso_employee_no_falls_back_to_the_saved_number(self):
        with mock.patch.object(fruit_auto, "get_account_state", return_value={"loginEmployeeNo": "20160301"}):
            self.assertEqual("20160301", fruit_auto.sso_employee_no("hong", "forest:1"))
        self.assertEqual("20160301", fruit_auto.sso_employee_no("20160301"))


if __name__ == "__main__":
    unittest.main()


class OneFingerRequestTests(unittest.TestCase):
    def _capture(self, method, path):
        client = onefinger.OneFingerClient()
        client.employee = {"id": "900001"}
        seen = {}

        class Res:
            status = 200

            def read(self):
                return b'{"data": {}}'

        def fake_open(req, timeout=None):
            seen["url"] = req.full_url
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            return Res()

        client._open = fake_open
        client.session_info = lambda: {"authenticated": True, "csrf": "tok"}
        client.api(method, path, body={} if method != "GET" else None)
        return seen

    def test_forest_calls_go_to_the_forest_api(self):
        seen = self._capture("GET", "/me")
        self.assertTrue(seen["url"].endswith("/api/v1/forest/me"), seen["url"])

    def test_writes_send_origin_and_csrf(self):
        seen = self._capture("POST", "/fruit-gifts")
        self.assertEqual(seen["headers"]["origin"], onefinger.ONEFINGER_URL)
        self.assertEqual(seen["headers"]["x-csrf-token"], "tok")
        self.assertEqual(seen["headers"]["x-forest-expected-employee-id"], "900001")


class OneFingerSessionReuseTests(unittest.TestCase):
    def setUp(self):
        fruit_auto.forget_onefinger_sessions()

    def tearDown(self):
        fruit_auto.forget_onefinger_sessions()

    def test_second_login_reuses_the_live_session(self):
        calls = {"login": 0}

        def fake_login(self, employee_no, password):
            calls["login"] += 1
            self.employee = {"id": "900001", "employeeNo": employee_no, "name": "테스트"}
            return self.employee

        with mock.patch.object(onefinger.OneFingerClient, "login", fake_login), \
                mock.patch.object(onefinger.OneFingerClient, "session_info", lambda self: {"authenticated": True, "csrf": "t"}):
            fruit_auto.pms_login(fruit_auto.Client(), "12345678", "pw")
            _token, dataset = fruit_auto.pms_login(fruit_auto.Client(), "12345678", "pw")
        self.assertEqual(calls["login"], 1)
        self.assertEqual(dataset["SESS_EMPNO"], "12345678")

    def test_expired_session_logs_in_again(self):
        calls = {"login": 0}

        def fake_login(self, employee_no, password):
            calls["login"] += 1
            self.employee = {"id": "900001", "employeeNo": employee_no, "name": "테스트"}
            return self.employee

        with mock.patch.object(onefinger.OneFingerClient, "login", fake_login), \
                mock.patch.object(onefinger.OneFingerClient, "session_info", lambda self: {"authenticated": False}):
            fruit_auto.pms_login(fruit_auto.Client(), "12345678", "pw")
            fruit_auto.pms_login(fruit_auto.Client(), "12345678", "pw")
        self.assertEqual(calls["login"], 2)
