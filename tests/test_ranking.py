import unittest
from unittest import mock

import fruit_auto


class FakeRankingClient:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def post_json(self, url, payload):
        self.requests.append((url, payload))
        return self.rows


class GiftRankingTests(unittest.TestCase):
    def test_gift_ranking_uses_matching_employee_row_for_my_summary(self):
        client = FakeRankingClient(
            [
                {"empId": "777", "empNm": "허종섭", "rnk": 1, "sumBerry": 320},
                {"empId": "123", "empNm": "박근형", "rnk": 5, "sumBerry": 125},
            ]
        )
        login_result = (client, {}, {}, {}, "123", "박근형")

        with mock.patch.object(fruit_auto, "require_owner", return_value="forest:123"), mock.patch.object(
            fruit_auto, "account_login", return_value=login_result
        ):
            result = fruit_auto.forest_ranking(kind="gift", month="202607", owner_key="forest:123")

        self.assertEqual({"rank": 5, "name": "박근형", "count": 125}, result["my"])
        self.assertEqual(
            {"rank": 5, "name": "박근형", "count": 125},
            next(item for item in result["items"] if item["name"] == "박근형"),
        )
        self.assertEqual({"empId": "", "stdMt": "202607"}, client.requests[0][1])


if __name__ == "__main__":
    unittest.main()
