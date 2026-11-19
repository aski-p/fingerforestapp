import unittest
from unittest import mock

import fruit_auto


class FakeRankingClient:
    """새 OneFinger GET /rankings 흉내: 예전 행(empId·empNm·sumBerry)을 {top, me}로 바꿔 돌려준다."""

    def __init__(self, rows, me_id="123"):
        self.rows = rows
        self.me_id = me_id
        self.requests = []

    def rankings(self, kind, month=None, year=None):
        self.requests.append((kind, month, year))
        top = [
            {"employee": {"id": r["empId"], "name": r["empNm"]}, "rank": r.get("rnk") or 99, "value": r["sumBerry"], "level": None}
            for r in self.rows
        ]
        me = next((t for t in top if t["employee"]["id"] == self.me_id), None)
        return {"top": top, "me": me, "calculatedAt": "2026-07-31T00:00:00Z"}


class GiftRankingTests(unittest.TestCase):
    def run_gift_ranking(self, rows, employee_id="123", employee_name="박근형"):
        client = FakeRankingClient(rows)
        login_result = (client, {}, {}, {}, employee_id, employee_name)
        with mock.patch.object(fruit_auto, "require_owner", return_value=f"forest:{employee_id}"), mock.patch.object(
            fruit_auto, "account_login", return_value=login_result
        ):
            result = fruit_auto.forest_ranking(
                kind="gift", month="202607", owner_key=f"forest:{employee_id}"
            )
        return result, client

    def test_gift_ranking_derives_rank_from_response_order_not_api_rank(self):
        result, client = self.run_gift_ranking(
            [
                {"empId": "777", "empNm": "허종섭", "rnk": 99, "sumBerry": 320},
                {"empId": "123", "empNm": "박근형", "rnk": 99, "sumBerry": 125},
                {"empId": "456", "empNm": "김준", "rnk": 99, "sumBerry": 100},
            ]
        )

        self.assertEqual({"rank": 2, "name": "박근형", "count": 125}, result["my"])
        self.assertEqual([1, 2, 3], [item["rank"] for item in result["items"]])
        self.assertEqual(("gift", "2026-07", "2026"), client.requests[0])

    def test_gift_ranking_assigns_no_rank_below_fifth_place(self):
        rows = [
            {"empId": str(index), "empNm": f"직원{index}", "sumBerry": 100 - index}
            for index in range(1, 7)
        ]
        rows[-1] = {"empId": "123", "empNm": "박근형", "sumBerry": 42}

        result, _client = self.run_gift_ranking(rows)

        self.assertEqual({"rank": 0, "name": "박근형", "count": 42}, result["my"])
        self.assertEqual([1, 2, 3, 4, 5, 0], [item["rank"] for item in result["items"]])


if __name__ == "__main__":
    unittest.main()
