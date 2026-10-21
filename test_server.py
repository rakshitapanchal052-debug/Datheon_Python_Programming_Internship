import csv
import json
import tempfile
import threading
import unittest
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class PortfolioServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.positions_path = root / "positions.csv"
        self.summary_path = root / "summary.csv"
        self.positions_patch = patch.object(server, "POSITIONS_FILE", self.positions_path)
        self.summary_patch = patch.object(server, "SUMMARY_FILE", self.summary_path)
        self.positions_patch.start()
        self.summary_patch.start()
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), server.PortfolioRequestHandler
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.positions_patch.stop()
        self.summary_patch.stop()
        self.temporary_directory.cleanup()

    def request_json(self, path: str, method: str = "GET", payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            return response.status, json.load(response)

    def test_dashboard_is_served(self) -> None:
        with urlopen(self.base_url) as response:
            page = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("Portfolio overview", page)
        self.assertIn("/app.js", page)

    def test_add_holding_then_refresh_logs_snapshot(self) -> None:
        status, response = self.request_json(
            "/api/positions",
            "POST",
            {"ticker": "aapl", "shares": "2", "buy_price": "100"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["message"], "Holding saved.")

        with patch.object(server, "fetch_current_price", return_value=Decimal("125")):
            status, portfolio = self.request_json(
                "/api/refresh", "POST", {}
            )

        self.assertEqual(status, 200)
        self.assertEqual(portfolio["holdings"][0]["ticker"], "AAPL")
        self.assertEqual(portfolio["totals"]["market_value"], "250.00")
        self.assertEqual(portfolio["totals"]["gain_loss_percent"], "25.00")
        with self.summary_path.open(newline="", encoding="utf-8") as summary_file:
            rows = list(csv.DictReader(summary_file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAPL")

    def test_invalid_holding_is_rejected(self) -> None:
        with self.assertRaises(HTTPError) as error:
            self.request_json(
                "/api/positions",
                "POST",
                {"ticker": "AAPL", "shares": "0", "buy_price": "100"},
            )

        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        self.assertFalse(self.positions_path.exists())

    def test_delete_holding_removes_saved_position(self) -> None:
        self.request_json(
            "/api/positions",
            "POST",
            {"ticker": "AAPL", "shares": "1", "buy_price": "100"},
        )

        status, response = self.request_json(
            "/api/positions/AAPL", "DELETE"
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["message"], "AAPL removed.")
        self.assertEqual(server.load_positions(self.positions_path), {})


if __name__ == "__main__":
    unittest.main()
