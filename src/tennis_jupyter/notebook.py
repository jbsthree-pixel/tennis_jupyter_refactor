"""Notebook-friendly helpers for loading, filtering, plotting, and exporting data."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .analytics import filter_matches, summarize_key_insights
from .pipeline import build_match_summary
from .reporting import write_excel_report
from .shared import output_path, safe_ratio


def load_match_summary(
    input_csv: str | Path,
    name_map_xlsx: str | Path | None = None,
) -> pd.DataFrame:
    """Load the local CSV into the match-summary dataset used in notebooks."""
    return build_match_summary(input_csv=input_csv, name_map_xlsx=name_map_xlsx)


def plot_serve_trends(df: pd.DataFrame, player: str | None = None) -> None:
    """Plot year-level serve metrics for the whole dataset or a single player."""
    plot_df = filter_matches(df, player=player) if player else df.copy()
    if plot_df.empty:
        raise ValueError("No rows available for the requested serve trend plot.")

    yearly = (
        plot_df.groupby("Match Year", dropna=False)[
            [
                "first_serve_attempt",
                "first_serve_in",
                "first_serve_won",
                "second_serve_attempt",
                "second_serve_won",
                "double_fault",
            ]
        ]
        .sum()
        .reset_index()
        .sort_values("Match Year")
    )

    yearly["1st Serve In %"] = safe_ratio(
        yearly["first_serve_in"],
        yearly["first_serve_attempt"],
    )
    yearly["1st Serve Won %"] = safe_ratio(
        yearly["first_serve_won"],
        yearly["first_serve_in"],
    )
    yearly["2nd Serve Won %"] = safe_ratio(
        yearly["second_serve_won"],
        yearly["second_serve_attempt"],
    )
    yearly["Double Fault %"] = safe_ratio(
        yearly["double_fault"],
        yearly["second_serve_attempt"],
    )

    ax = yearly.plot(
        x="Match Year",
        y=["1st Serve In %", "1st Serve Won %", "2nd Serve Won %", "Double Fault %"],
        marker="o",
        figsize=(10, 5),
        title="Serve Trends by Year" if player is None else f"Serve Trends by Year: {player}",
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()


def export_outputs(
    df: pd.DataFrame,
    output_dir: str | Path | None = None,
    csv_name: str = "Tennis_MatchSummary.csv",
    excel_name: str = "Tennis_MatchSummary_Report.xlsx",
) -> tuple[Path, Path]:
    """Write CSV and Excel outputs for the current summary dataframe."""
    target_dir = Path(output_dir) if output_dir else output_path()
    target_dir.mkdir(parents=True, exist_ok=True)

    csv_path = target_dir / csv_name
    excel_path = target_dir / excel_name

    df.to_csv(csv_path, index=False)
    write_excel_report(df, excel_path)
    return csv_path, excel_path
