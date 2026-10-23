"""Track stock holdings and append portfolio snapshots to a CSV file."""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parent
TICKER_FILE = PROJECT_DIR / "constituents.csv"
SUMMARY_FILE = PROJECT_DIR / "portfolio_summary.csv"
POSITIONS_FILE = PROJECT_DIR / "portfolio_positions.csv"
TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.^-]{0,14}$")
POSITION_FIELDS = ["ticker", "shares", "buy_price"]
CSV_FIELDS = [
    "snapshot_at",
    "ticker",
    "company",
    "shares",
    "buy_price",
    "current_price",
    "cost_basis",
    "market_value",
    "gain_loss",
    "gain_loss_percent",
    "portfolio_cost_basis",
    "portfolio_market_value",
    "portfolio_gain_loss",
    "portfolio_gain_loss_percent",
]


@dataclass(frozen=True)
class Position:
    shares: Decimal
    buy_price: Decimal


@dataclass(frozen=True)
class HoldingSummary:
    ticker: str
    company: str
    shares: Decimal
    buy_price: Decimal
    current_price: Decimal
    cost_basis: Decimal
    market_value: Decimal
    gain_loss: Decimal
    gain_loss_percent: Decimal


def load_ticker_names(path: Path = TICKER_FILE) -> dict[str, str]:
    """Load company names from the bundled S&P 500 reference CSV."""
    if not path.is_file():
        return {}

    with path.open("r", newline="", encoding="utf-8-sig") as ticker_file:
        return {
            row["Symbol"].strip().upper(): row["Security"].strip()
            for row in csv.DictReader(ticker_file)
            if row.get("Symbol") and row.get("Security")
        }


def load_positions(path: Path = POSITIONS_FILE) -> dict[str, Position]:
    if not path.is_file():
        return {}

    positions: dict[str, Position] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as positions_file:
        for row in csv.DictReader(positions_file):
            ticker = row.get("ticker", "").strip().upper()
            try:
                shares = Decimal(row.get("shares", ""))
                buy_price = Decimal(row.get("buy_price", ""))
            except InvalidOperation as error:
                raise ValueError(f"Invalid saved position for {ticker or 'unknown ticker'}.") from error
            if (
                not TICKER_PATTERN.fullmatch(ticker)
                or not shares.is_finite()
                or shares <= 0
                or not buy_price.is_finite()
                or buy_price <= 0
            ):
                raise ValueError(f"Invalid saved position for {ticker or 'unknown ticker'}.")
            positions[ticker] = Position(shares=shares, buy_price=buy_price)
    return positions


def save_positions(
    positions: dict[str, Position], path: Path = POSITIONS_FILE
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as positions_file:
        writer = csv.DictWriter(positions_file, fieldnames=POSITION_FIELDS)
        writer.writeheader()
        for ticker, position in positions.items():
            writer.writerow(
                {
                    "ticker": ticker,
                    "shares": str(position.shares),
                    "buy_price": str(position.buy_price),
                }
            )


def add_position(
    positions: dict[str, Position],
    ticker: str,
    shares: Decimal,
    buy_price: Decimal,
) -> dict[str, Position]:
    ticker = ticker.strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError("Enter a valid stock ticker.")
    if not shares.is_finite() or shares <= 0:
        raise ValueError("Share quantity must be greater than zero.")
    if not buy_price.is_finite() or buy_price <= 0:
        raise ValueError("Buy price must be greater than zero.")

    updated = positions.copy()
    previous = updated.get(ticker)
    if previous:
        total_shares = previous.shares + shares
        buy_price = (
            previous.shares * previous.buy_price + shares * buy_price
        ) / total_shares
        shares = total_shares
    updated[ticker] = Position(shares=shares, buy_price=buy_price)
    return updated


def prompt_positive_decimal(prompt: str) -> Decimal:
    while True:
        value = input(prompt).strip()
        try:
            number = Decimal(value)
        except InvalidOperation:
            print("Enter a valid number.")
            continue
        if not number.is_finite() or number <= 0:
            print("Enter a number greater than zero.")
            continue
        return number


def collect_positions() -> dict[str, Position]:
    """Read positions, combining repeated tickers at weighted-average cost."""
    positions: dict[str, Position] = {}
    print("Enter each holding. Leave the ticker blank when you are done.")

    while True:
        ticker = input("Ticker: ").strip().upper()
        if not ticker:
            return positions
        if not TICKER_PATTERN.fullmatch(ticker):
            print("Ticker may contain letters, numbers, '.', '-', or '^'.")
            continue

        buy_price = prompt_positive_decimal(f"{ticker} buy price per share: ")
        shares = prompt_positive_decimal(f"{ticker} share quantity: ")
        previous = positions.get(ticker)
        if previous is not None:
            total_shares = previous.shares + shares
            buy_price = (
                previous.shares * previous.buy_price + shares * buy_price
            ) / total_shares
            shares = total_shares
        positions[ticker] = Position(shares=shares, buy_price=buy_price)


def fetch_current_price(ticker: str) -> Decimal:
    """Fetch the latest available regular-market price from Yahoo Finance."""
    yahoo_ticker = ticker.replace(".", "-")
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(yahoo_ticker, safe='')}?range=1d&interval=1m"
    )
    request = Request(url, headers={"User-Agent": "StockPortfolioTracker/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not retrieve a quote for {ticker}: {error}") from error

    chart = payload.get("chart", {})
    if chart.get("error"):
        message = chart["error"].get("description", "quote provider returned an error")
        raise RuntimeError(f"Could not retrieve a quote for {ticker}: {message}")
    results = chart.get("result")
    if not results:
        raise RuntimeError(f"No quote data was returned for {ticker}.")

    market_price = results[0].get("meta", {}).get("regularMarketPrice")
    if not isinstance(market_price, (int, float)) or market_price <= 0:
        raise RuntimeError(f"No valid current market price was returned for {ticker}.")
    return Decimal(str(market_price))


def summarize_holding(
    ticker: str,
    position: Position,
    current_price: Decimal,
    company: str = "",
) -> HoldingSummary:
    cost_basis = position.shares * position.buy_price
    market_value = position.shares * current_price
    gain_loss = market_value - cost_basis
    gain_loss_percent = gain_loss / cost_basis * Decimal("100")
    return HoldingSummary(
        ticker=ticker,
        company=company,
        shares=position.shares,
        buy_price=position.buy_price,
        current_price=current_price,
        cost_basis=cost_basis,
        market_value=market_value,
        gain_loss=gain_loss,
        gain_loss_percent=gain_loss_percent,
    )


def format_money(value: Decimal) -> str:
    return f"${value:,.2f}"


def print_summary(holdings: list[HoldingSummary]) -> tuple[Decimal, Decimal, Decimal]:
    total_cost = sum((holding.cost_basis for holding in holdings), Decimal("0"))
    total_value = sum((holding.market_value for holding in holdings), Decimal("0"))
    total_gain = total_value - total_cost
    total_gain_percent = total_gain / total_cost * Decimal("100")

    print()
    print(
        f"{'Ticker':<10}{'Shares':>12}{'Buy Price':>14}"
        f"{'Current':>14}{'Market Value':>17}{'Gain/Loss':>17}{'Return':>12}"
    )
    print("-" * 96)
    for holding in holdings:
        print(
            f"{holding.ticker:<10}{holding.shares:>12,.4f}"
            f"{format_money(holding.buy_price):>14}"
            f"{format_money(holding.current_price):>14}"
            f"{format_money(holding.market_value):>17}"
            f"{format_money(holding.gain_loss):>17}"
            f"{holding.gain_loss_percent:>11.2f}%"
        )
    print("-" * 96)
    print(f"Total invested: {format_money(total_cost)}")
    print(f"Current value:  {format_money(total_value)}")
    print(f"Total gain/loss:{format_money(total_gain):>14} ({total_gain_percent:.2f}%)")
    return total_cost, total_value, total_gain_percent


def append_snapshot(
    holdings: list[HoldingSummary],
    total_cost: Decimal,
    total_value: Decimal,
    total_gain_percent: Decimal,
    path: Path = SUMMARY_FILE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    snapshot_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    total_gain = total_value - total_cost

    with path.open("a", newline="", encoding="utf-8") as summary_file:
        writer = csv.DictWriter(summary_file, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for holding in holdings:
            writer.writerow(
                {
                    "snapshot_at": snapshot_at,
                    "ticker": holding.ticker,
                    "company": holding.company,
                    "shares": str(holding.shares),
                    "buy_price": f"{holding.buy_price:.2f}",
                    "current_price": f"{holding.current_price:.2f}",
                    "cost_basis": f"{holding.cost_basis:.2f}",
                    "market_value": f"{holding.market_value:.2f}",
                    "gain_loss": f"{holding.gain_loss:.2f}",
                    "gain_loss_percent": f"{holding.gain_loss_percent:.2f}",
                    "portfolio_cost_basis": f"{total_cost:.2f}",
                    "portfolio_market_value": f"{total_value:.2f}",
                    "portfolio_gain_loss": f"{total_gain:.2f}",
                    "portfolio_gain_loss_percent": f"{total_gain_percent:.2f}",
                }
            )


def main() -> int:
    print("Stock Portfolio Performance Tracker")
    positions = collect_positions()
    if not positions:
        print("No holdings entered. Nothing was written to the CSV file.")
        return 0

    company_names = load_ticker_names()
    holdings: list[HoldingSummary] = []
    try:
        for ticker, position in positions.items():
            current_price = fetch_current_price(ticker)
            holdings.append(
                summarize_holding(
                    ticker,
                    position,
                    current_price,
                    company_names.get(ticker, ""),
                )
            )
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    total_cost, total_value, total_gain_percent = print_summary(holdings)
    append_snapshot(holdings, total_cost, total_value, total_gain_percent)
    print(f"\nSnapshot appended to {SUMMARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
