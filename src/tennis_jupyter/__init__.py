"""Cross-platform tennis analysis package for CLI and Jupyter workflows."""

from .notebook import (
    export_outputs,
    filter_matches,
    load_match_summary,
    plot_serve_trends,
    summarize_key_insights,
)
from .reporting import write_excel_report

__all__ = [
    "export_outputs",
    "filter_matches",
    "load_match_summary",
    "plot_serve_trends",
    "summarize_key_insights",
    "write_excel_report",
]
