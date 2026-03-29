"""CLI entrypoint for the cross-platform tennis summary workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tennis_jupyter import export_outputs, load_match_summary, summarize_key_insights
from tennis_jupyter.shared import data_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for CSV input and output locations."""
    parser = argparse.ArgumentParser(
        description="Build a cross-platform tennis match summary for CLI and Jupyter use.",
    )
    parser.add_argument(
        "--input-csv",
        default=str(data_path("input", "StatsReport_TeamNames.csv")),
        help="Path to the local source CSV file.",
    )
    parser.add_argument(
        "--name-map-xlsx",
        default=None,
        help="Optional Excel file used to map raw player names to cleaned names.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory where CSV and Excel outputs will be written.",
    )
    return parser.parse_args()


def print_insights(insights: dict[str, object]) -> None:
    """Print high-signal match summary details to the console."""
    date_start, date_end = insights["date_range"]
    date_range_text = "unknown"
    if date_start is not None and date_end is not None:
        date_range_text = f"{date_start} to {date_end}"

    print(f"Total matches: {insights['total_matches']:,}")
    print(f"Players: {insights['total_players']:,}")
    print(f"Wins: {insights['wins']:,}")
    print(f"Losses: {insights['losses']:,}")
    print(f"Win rate: {insights['win_rate']:.1%}")
    print(f"Date range: {date_range_text}")


def main() -> int:
    """Run the end-to-end summary build and export flow."""
    args = parse_args()

    try:
        summary_df = load_match_summary(
            input_csv=Path(args.input_csv),
            name_map_xlsx=Path(args.name_map_xlsx) if args.name_map_xlsx else None,
        )
        csv_path, excel_path = export_outputs(summary_df, output_dir=Path(args.output_dir))
        print_insights(summarize_key_insights(summary_df))
        print(f"Wrote summary CSV to {csv_path}")
        print(f"Wrote Excel report to {excel_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Tip: put your source file at data/input/StatsReport_TeamNames.csv "
            "or pass --input-csv with a full path.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
