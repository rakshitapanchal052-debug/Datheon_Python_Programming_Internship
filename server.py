"""Local web application for the stock portfolio tracker."""

from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from portfolio import (
    PROJECT_DIR,
    POSITIONS_FILE,
    SUMMARY_FILE,
    HoldingSummary,
    Position,
    add_position,
    append_snapshot,
    fetch_current_price,
    load_positions,
    load_ticker_names,
    save_positions,
)


HOST = "127.0.0.1"
PORT = 8000
STATIC_DIR = PROJECT_DIR / "static"
STATIC_FILES = {
    "/": STATIC_DIR / "index.html",
    "/styles.css": STATIC_DIR / "styles.css",
    "/app.js": STATIC_DIR / "app.js",
}
MAX_REQUEST_SIZE = 16_384


def build_portfolio(
    positions: dict[str, Position], log_snapshot: bool = False
) -> dict[str, object]:
    company_names = load_ticker_names()
    holdings: list[dict[str, str]] = []
    total_cost = Decimal("0")
    total_value = Decimal("0")

    for ticker, position in positions.items():
        current_price = fetch_current_price(ticker)
        cost_basis = position.shares * position.buy_price
        market_value = position.shares * current_price
        gain_loss = market_value - cost_basis
        gain_loss_percent = gain_loss / cost_basis * Decimal("100")
        total_cost += cost_basis
        total_value += market_value
        holdings.append(
            {
                "ticker": ticker,
                "company": company_names.get(ticker, ""),
                "shares": str(position.shares),
                "buy_price": f"{position.buy_price:.2f}",
                "current_price": f"{current_price:.2f}",
                "cost_basis": f"{cost_basis:.2f}",
                "market_value": f"{market_value:.2f}",
                "gain_loss": f"{gain_loss:.2f}",
                "gain_loss_percent": f"{gain_loss_percent:.2f}",
            }
        )

    total_gain = total_value - total_cost
    total_gain_percent = (
        total_gain / total_cost * Decimal("100") if total_cost else Decimal("0")
    )
    if holdings and log_snapshot:
        snapshot_holdings = [_holding_summary(item) for item in holdings]
        append_snapshot(
            snapshot_holdings,
            total_cost,
            total_value,
            total_gain_percent,
            SUMMARY_FILE,
        )

    return {
        "holdings": holdings,
        "totals": {
            "invested": f"{total_cost:.2f}",
            "market_value": f"{total_value:.2f}",
            "gain_loss": f"{total_gain:.2f}",
            "gain_loss_percent": f"{total_gain_percent:.2f}",
        },
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _holding_summary(item: dict[str, str]) -> HoldingSummary:
    return HoldingSummary(
        ticker=item["ticker"],
        company=item["company"],
        shares=Decimal(item["shares"]),
        buy_price=Decimal(item["buy_price"]),
        current_price=Decimal(item["current_price"]),
        cost_basis=Decimal(item["cost_basis"]),
        market_value=Decimal(item["market_value"]),
        gain_loss=Decimal(item["gain_loss"]),
        gain_loss_percent=Decimal(item["gain_loss_percent"]),
    )


class PortfolioRequestHandler(BaseHTTPRequestHandler):
    server_version = "PortfolioTracker/1.0"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/portfolio":
            self._get_portfolio()
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": "API endpoint not found."})
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/refresh":
            self._refresh_portfolio()
            return
        if path != "/api/positions":
            self._send_json(404, {"error": "API endpoint not found."})
            return

        try:
            payload = self._read_json()
            ticker = payload.get("ticker")
            if not isinstance(ticker, str):
                raise ValueError("Ticker must be text.")
            shares = Decimal(str(payload.get("shares", "")))
            buy_price = Decimal(str(payload.get("buy_price", "")))
            positions = load_positions(POSITIONS_FILE)
            updated_positions = add_position(
                positions, ticker, shares, buy_price
            )
            save_positions(updated_positions, POSITIONS_FILE)
        except (ValueError, InvalidOperation) as error:
            self._send_json(400, {"error": str(error)})
            return
        except OSError as error:
            self._send_json(500, {"error": f"Could not save the holding: {error}"})
            return

        self._send_json(201, {"message": "Holding saved."})

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        prefix = "/api/positions/"
        if not path.startswith(prefix):
            self._send_json(404, {"error": "API endpoint not found."})
            return
        ticker = unquote(path[len(prefix):]).strip().upper()
        try:
            positions = load_positions(POSITIONS_FILE)
        except ValueError as error:
            self._send_json(500, {"error": str(error)})
            return
        if ticker not in positions:
            self._send_json(404, {"error": f"{ticker} is not in the portfolio."})
            return
        del positions[ticker]
        try:
            save_positions(positions, POSITIONS_FILE)
        except OSError as error:
            self._send_json(500, {"error": f"Could not remove the holding: {error}"})
            return
        self._send_json(200, {"message": f"{ticker} removed."})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.log_date_time_string()} {format % args}")

    def _get_portfolio(self) -> None:
        try:
            data = build_portfolio(load_positions(POSITIONS_FILE))
        except (OSError, RuntimeError, ValueError) as error:
            self._send_json(502, {"error": str(error)})
            return
        self._send_json(200, data)

    def _refresh_portfolio(self) -> None:
        try:
            self._read_json()
            data = build_portfolio(
                load_positions(POSITIONS_FILE), log_snapshot=True
            )
        except (OSError, RuntimeError, ValueError) as error:
            self._send_json(502, {"error": str(error)})
            return
        self._send_json(200, data)

    def _read_json(self) -> dict[str, object]:
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ValueError("Invalid request size.") from error
        if length < 0 or length > MAX_REQUEST_SIZE:
            raise ValueError("Request body is too large or invalid.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("Request body must contain valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _serve_static(self, path: str) -> None:
        file_path = STATIC_FILES.get(path)
        if file_path is None or not file_path.is_file():
            self.send_error(404)
            return
        content_type = (
            mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        )
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PortfolioRequestHandler)
    print(f"Portfolio tracker is running at http://{HOST}:{PORT}")
    print(f"Performance snapshots are saved to {SUMMARY_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down portfolio tracker.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
