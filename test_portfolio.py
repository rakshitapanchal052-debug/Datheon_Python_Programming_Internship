import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from portfolio import (
    Position,
    add_position,
    append_snapshot,
    load_positions,
    save_positions,
    summarize_holding,
)


class PortfolioTests(unittest.TestCase):
    def test_summarize_holding_calculates_return(self) -> None:
        holding = summarize_holding(
            "AAPL",
            Position(shares=Decimal("4"), buy_price=Decimal("100")),
            Decimal("125"),
            "Apple Inc.",
        )

        self.assertEqual(holding.cost_basis, Decimal("400"))
        self.assertEqual(holding.market_value, Decimal("500"))
        self.assertEqual(holding.gain_loss, Decimal("100"))
        self.assertEqual(holding.gain_loss_percent, Decimal("25"))
        self.assertEqual(holding.company, "Apple Inc.")

    def test_append_snapshot_writes_header_and_holding(self) -> None:
        holding = summarize_holding(
            "AAPL",
            Position(shares=Decimal("2"), buy_price=Decimal("100")),
            Decimal("110"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio_summary.csv"

            append_snapshot(
                [holding],
                Decimal("200"),
                Decimal("220"),
                Decimal("10"),
                path,
            )

            with path.open("r", newline="", encoding="utf-8") as summary_file:
                rows = list(csv.DictReader(summary_file))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAPL")
        self.assertEqual(rows[0]["market_value"], "220.00")
        self.assertEqual(rows[0]["portfolio_gain_loss_percent"], "10.00")
        self.assertTrue(rows[0]["snapshot_at"])

    def test_add_position_combines_existing_shares_at_weighted_cost(self) -> None:
        positions = {"AAPL": Position(Decimal("2"), Decimal("100"))}

        updated = add_position(positions, "aapl", Decimal("2"), Decimal("120"))

        self.assertEqual(updated["AAPL"].shares, Decimal("4"))
        self.assertEqual(updated["AAPL"].buy_price, Decimal("110"))
        self.assertEqual(positions["AAPL"].shares, Decimal("2"))

    def test_positions_round_trip_through_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portfolio_positions.csv"
            positions = {"MSFT": Position(Decimal("1.5"), Decimal("300.25"))}

            save_positions(positions, path)

            self.assertEqual(load_positions(path), positions)

    def test_add_position_rejects_non_positive_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "Share quantity"):
            add_position({}, "AAPL", Decimal("0"), Decimal("100"))


if __name__ == "__main__":
    unittest.main()
