"""Cross-platform browser app for interactive tennis match analysis."""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from tennis_jupyter.analytics import (  # noqa: E402
    available_filter_values,
    build_pivot_summary,
    build_raw_data_dictionary,
    build_serve_return_match_stats,
    filter_matches,
    load_source_review,
    save_source_review_changes,
    summarize_key_insights,
    with_season_columns,
)
from tennis_jupyter.constants import (  # noqa: E402
    COLORBLIND_SAFE_CHART_COLORS,
    COLORBLIND_SAFE_DIVERGING_SCALE,
    COLORBLIND_SAFE_SEQUENTIAL_SCALE,
    PIVOT_ACE_COLUMN_DEFS,
    SERVE_TREND_METRICS,
)
from tennis_jupyter.notebook import load_match_summary  # noqa: E402
from tennis_jupyter.reporting import write_excel_report  # noqa: E402
from tennis_jupyter.shared import safe_ratio  # noqa: E402


BENCHMARK_LEVEL_COLUMNS = {
    "Tour Avg": "Tour Avg",
    "Top 10 Avg": "Top 10 Avg",
}

BENCHMARK_SPECS = [
    {
        "workbook_metric": "1st Serve In",
        "app_label": "1st Serve In %",
        "table_column": "First Serve %",
        "numerator": "first_serve_in",
        "denominator": "first_serve_attempt",
    },
    {
        "workbook_metric": "1st Serve Points Won",
        "app_label": "1st Serve Won %",
        "table_column": "1st Serve Win %",
        "numerator": "first_serve_won",
        "denominator": "first_serve_in",
    },
    {
        "workbook_metric": "2nd Serve Points Won",
        "app_label": "2nd Serve Won %",
        "table_column": "2nd Serve Win %",
        "numerator": "second_serve_won",
        "denominator": "second_serve_attempt",
    },
    {
        "workbook_metric": "1st Serves Unreturned",
        "app_label": None,
        "table_column": "1SNR %",
        "numerator": "first_serve_not_returned",
        "denominator": "first_serve_in",
    },
    {
        "workbook_metric": "1st Serve Return Points Won",
        "app_label": None,
        "table_column": "First Serve Returns Won %",
        "numerator": "first_serve_return_won",
        "denominator": "first_serve_return_opportunity",
    },
    {
        "workbook_metric": "2nd Serve Return Points Won",
        "app_label": None,
        "table_column": "Second Serve Returns Won %",
        "numerator": "second_serve_return_won",
        "denominator": "second_serve_return_opportunity",
    },
    {
        "workbook_metric": "Break Points Won",
        "app_label": None,
        "table_column": None,
        "numerator": "break_point_won",
        "denominator": "break_point_total",
    },
    {
        "workbook_metric": "Break Points Saved",
        "app_label": None,
        "table_column": None,
        "numerator": "break_point_saved",
        "denominator": "break_point_faced",
    },
]


st.set_page_config(page_title="Tennis Match Summary", layout="wide")

st.markdown(
    f"""
    <style>
        :root {{
            --accent-red: {COLORBLIND_SAFE_CHART_COLORS["accent_red"]};
            --accent-red-dark: {COLORBLIND_SAFE_CHART_COLORS["accent_red_dark"]};
            --accent-gray: {COLORBLIND_SAFE_CHART_COLORS["accent_gray"]};
            --surface-neutral: {COLORBLIND_SAFE_CHART_COLORS["surface_neutral"]};
            --text-strong: #1f1f1f;
        }}

        .stApp {{
            background: linear-gradient(180deg, #fffdf8 0%, var(--surface-neutral) 100%);
            color: var(--text-strong);
        }}

        .nc-state-banner {{
            align-items: center;
            background: linear-gradient(135deg, #cc0000 0%, #990000 55%, #1f1f1f 100%);
            border: 1px solid rgba(31, 31, 31, 0.15);
            border-radius: 18px;
            color: #ffffff;
            display: flex;
            gap: 1rem;
            margin: 0 0 1.25rem 0;
            overflow: hidden;
            padding: 1.1rem 1.4rem;
            position: relative;
        }}

        .nc-state-banner::after {{
            background: linear-gradient(90deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0));
            content: "";
            inset: 0;
            pointer-events: none;
            position: absolute;
        }}

        .nc-state-banner__eyebrow {{
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            margin-bottom: 0.35rem;
            position: relative;
            text-transform: uppercase;
            z-index: 1;
        }}

        .nc-state-banner__title {{
            font-size: 2rem;
            font-weight: 800;
            line-height: 1.05;
            margin: 0;
            position: relative;
            z-index: 1;
        }}

        .nc-state-banner__subtitle {{
            font-size: 1rem;
            margin-top: 0.45rem;
            max-width: 52rem;
            opacity: 0.95;
            position: relative;
            z-index: 1;
        }}

        .nc-state-banner__logo {{
            background: rgba(255, 255, 255, 0.92);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18);
            flex: 0 0 auto;
            padding: 0.45rem;
            position: relative;
            width: 92px;
            z-index: 1;
        }}

        .nc-state-banner__logo img {{
            display: block;
            height: auto;
            width: 100%;
        }}

        .nc-state-banner__content {{
            min-width: 0;
            position: relative;
            z-index: 1;
        }}

        @media (max-width: 640px) {{
            .nc-state-banner {{
                align-items: flex-start;
                flex-direction: column;
            }}

            .nc-state-banner__logo {{
                width: 72px;
            }}

            .nc-state-banner__title {{
                font-size: 1.65rem;
            }}
        }}

        .stButton > button,
        .stDownloadButton > button,
        button[kind="primary"] {{
            background: var(--accent-red);
            border: 1px solid var(--accent-red);
            color: #ffffff;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        button[kind="primary"]:hover {{
            background: var(--accent-red-dark);
            border-color: var(--accent-red-dark);
            color: #ffffff;
        }}

        [data-baseweb="tab-list"] button[aria-selected="true"] {{
            color: var(--accent-red);
            border-bottom-color: var(--accent-red);
        }}

        button[data-baseweb="tab"]:nth-of-type(10) {{
            cursor: not-allowed;
            opacity: 0.5;
            pointer-events: none;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_summary_cached(
    input_csv: str,
    name_map_xlsx: str | None,
    csv_mtime: float,
    name_map_mtime: float | None,
) -> pd.DataFrame:
    """Cache summary rebuilds until the source files change."""
    _ = csv_mtime, name_map_mtime
    return load_match_summary(input_csv=input_csv, name_map_xlsx=name_map_xlsx)


@st.cache_data(show_spinner=False)
def load_source_review_cached(source_csv: str, csv_mtime: float):
    """Cache grouped source rows for editing until the source file changes."""
    _ = csv_mtime
    return load_source_review(source_csv)


@st.cache_data(show_spinner=False)
def load_benchmark_workbook(benchmark_xlsx: str, benchmark_mtime: float) -> pd.DataFrame:
    """Load the tour benchmark workbook into a normalized dataframe."""
    _ = benchmark_mtime
    benchmark_df = pd.read_excel(benchmark_xlsx)
    benchmark_df = benchmark_df.rename(columns={benchmark_df.columns[0]: "Metric"})
    benchmark_df["Metric"] = benchmark_df["Metric"].fillna("").astype(str).str.strip()
    benchmark_df = benchmark_df[benchmark_df["Metric"] != ""].copy()
    return benchmark_df


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a dataframe to UTF-8 CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize the report workbook to in-memory Excel bytes."""
    buffer = io.BytesIO()
    write_excel_report(df, buffer)
    buffer.seek(0)
    return buffer.getvalue()


def style_banded_rows(
    df: pd.DataFrame,
    hide_index: bool = True,
    formatters: dict[str, str | callable] | None = None,
) -> pd.io.formats.style.Styler:
    """Apply alternating row shading to read-only dataframes."""
    band_color = "rgba(204, 0, 0, 0.08)"
    base_color = "rgba(255, 255, 255, 0.9)"

    styler = df.style.apply(
        lambda row: [
            f"background-color: {band_color if row.name % 2 else base_color}"
            for _ in row
        ],
        axis=1,
    )
    if formatters:
        styler = styler.format(formatters)
    if hide_index:
        styler = styler.hide(axis="index")
    return styler


def image_to_data_uri(path: Path) -> str | None:
    """Convert a local image file into an embeddable data URI."""
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    image_type = path.suffix.lower().lstrip(".") or "png"
    return f"data:image/{image_type};base64,{encoded}"


def scope_text(player: str, year: str, month_name: str, opp_team: str, season: str) -> str:
    """Create a compact label for the current filter state."""
    labels = []
    for value in [player, year, month_name, opp_team, season]:
        if value and value != "All":
            labels.append(value)
    return " | ".join(labels) if labels else "Current Filters"


def chart_key(name: str, *parts: object) -> str:
    """Build a stable chart key that changes when filters or chart options change."""
    serialized = [name]
    for part in parts:
        if isinstance(part, (list, tuple, set)):
            serialized.append(",".join(str(item) for item in part))
        else:
            serialized.append(str(part))
    return "::".join(serialized)


def benchmark_lookup(benchmark_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Index workbook metrics by label for quick baseline lookup."""
    lookup: dict[str, dict[str, float]] = {}
    if benchmark_df.empty:
        return lookup

    for _, row in benchmark_df.iterrows():
        metric_name = str(row.get("Metric", "")).strip()
        if not metric_name:
            continue
        lookup[metric_name] = {
            level_name: float(row[column])
            for level_name, column in BENCHMARK_LEVEL_COLUMNS.items()
            if column in benchmark_df.columns and pd.notna(row.get(column))
        }
    return lookup


def aggregate_benchmark_metrics(chart_df: pd.DataFrame) -> dict[str, float]:
    """Aggregate filtered match data into workbook-comparable rates."""
    values: dict[str, float] = {}
    if chart_df.empty:
        return values

    totals = chart_df.copy()
    for spec in BENCHMARK_SPECS:
        if spec["numerator"] not in totals.columns or spec["denominator"] not in totals.columns:
            continue
        numerator = pd.to_numeric(totals[spec["numerator"]], errors="coerce").fillna(0).sum()
        denominator = pd.to_numeric(totals[spec["denominator"]], errors="coerce").fillna(0).sum()
        values[spec["workbook_metric"]] = float(numerator / denominator) if denominator else 0.0

    return values


def build_benchmark_snapshot(
    chart_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    selected_levels: list[str],
) -> pd.DataFrame:
    """Compare the filtered aggregate rates against selected benchmark baselines."""
    if chart_df.empty or benchmark_df.empty or not selected_levels:
        return pd.DataFrame()

    lookup = benchmark_lookup(benchmark_df)
    current_values = aggregate_benchmark_metrics(chart_df)
    rows: list[dict[str, object]] = []
    for spec in BENCHMARK_SPECS:
        metric_name = spec["workbook_metric"]
        if metric_name not in lookup or metric_name not in current_values:
            continue

        row: dict[str, object] = {
            "Metric": metric_name,
            "Current": current_values[metric_name],
        }
        for level in selected_levels:
            if level not in lookup[metric_name]:
                continue
            row[level] = lookup[metric_name][level]
            row[f"vs {level}"] = current_values[metric_name] - lookup[metric_name][level]
        rows.append(row)

    return pd.DataFrame(rows)


def add_benchmark_lines(
    figure: go.Figure,
    selected_metrics: list[tuple[str, str, str, str]],
    benchmark_df: pd.DataFrame,
    selected_levels: list[str],
) -> None:
    """Overlay workbook benchmark lines for selected serve trend metrics."""
    if benchmark_df.empty or not selected_levels:
        return

    lookup = benchmark_lookup(benchmark_df)
    metric_to_workbook = {
        spec["app_label"]: spec["workbook_metric"]
        for spec in BENCHMARK_SPECS
        if spec["app_label"]
    }
    line_styles = {
        "Tour Avg": {"dash": "dot", "color": COLORBLIND_SAFE_CHART_COLORS["accent_black"]},
        "Top 10 Avg": {"dash": "dash", "color": COLORBLIND_SAFE_CHART_COLORS["accent_taupe"]},
    }

    for metric_label, _, _, _ in selected_metrics:
        workbook_metric = metric_to_workbook.get(metric_label)
        if not workbook_metric or workbook_metric not in lookup:
            continue
        for level in selected_levels:
            baseline_value = lookup[workbook_metric].get(level)
            if baseline_value is None:
                continue
            figure.add_hline(
                y=baseline_value,
                line_dash=line_styles[level]["dash"],
                line_color=line_styles[level]["color"],
                opacity=0.9,
                annotation_text=f"{metric_label} {level}: {baseline_value:.1%}",
                annotation_position="top left",
            )


def tier_from_quantiles(series: pd.Series) -> pd.Categorical:
    """Bucket continuous values into low, mid, high tiers."""
    labels = ["Low", "Mid", "High"]
    numeric = pd.to_numeric(series, errors="coerce")
    q1 = float(numeric.quantile(1 / 3))
    q2 = float(numeric.quantile(2 / 3))
    if pd.isna(q1) or pd.isna(q2) or q1 >= q2:
        return pd.cut(numeric, bins=[-0.001, 1 / 3, 2 / 3, 1.001], labels=labels)
    return pd.cut(
        numeric,
        bins=[-0.001, q1, q2, 1.001],
        labels=labels,
        include_lowest=True,
    )


def fixed_tier(series: pd.Series) -> pd.Categorical:
    """Bucket rates into low, mid, high tiers with stable cutoffs."""
    return pd.cut(series, bins=[-0.001, 0.35, 0.55, 1.001], labels=["Low", "Mid", "High"])


def plot_metric_line_chart(chart_df: pd.DataFrame, selected_metrics: list[tuple[str, str, str, str]], split_by_result: bool, title: str) -> go.Figure | None:
    """Render an interactive serve trend chart by match order with date context."""
    if chart_df.empty or not selected_metrics:
        return None

    needed = sorted({column for _, numer, denom, _ in selected_metrics for column in [numer, denom]})
    missing = [column for column in needed if column not in chart_df.columns]
    if missing:
        return None

    plot_df = chart_df.copy()
    if "Match Date" in plot_df.columns:
        plot_df["Match Date"] = pd.to_datetime(plot_df["Match Date"], errors="coerce")
    sort_columns = [column for column in ["Match Date", "matchId"] if column in plot_df.columns]
    if sort_columns:
        plot_df = plot_df.sort_values(sort_columns, na_position="last")
    plot_df = plot_df.reset_index(drop=True)
    plot_df["Match Sequence"] = range(1, len(plot_df) + 1)
    use_match_date = "Match Date" in plot_df.columns and plot_df["Match Date"].notna().any()

    def build_customdata(frame: pd.DataFrame) -> list[list[str]]:
        date_text = (
            frame["Match Date"].dt.strftime("%Y-%m-%d").fillna("Unknown")
            if "Match Date" in frame.columns
            else pd.Series(["Unknown"] * len(frame), index=frame.index)
        )
        opponent_text = (
            frame["opp"].fillna("").astype(str)
            if "opp" in frame.columns
            else pd.Series([""] * len(frame), index=frame.index)
        )
        result_text = (
            frame["Match Result"].fillna("").astype(str)
            if "Match Result" in frame.columns
            else pd.Series([""] * len(frame), index=frame.index)
        )
        return [
            [date_text.loc[idx], opponent_text.loc[idx], result_text.loc[idx]]
            for idx in frame.index
        ]

    hover_template = (
        "Match Order: %{x}<br>"
        "Rate: %{y:.1%}<br>"
        "Match Date: %{customdata[0]}"
        "<br>Opponent: %{customdata[1]}"
        "<br>Result: %{customdata[2]}"
        "<extra>%{fullData.name}</extra>"
    )
    marker_symbols = {
        "1st Serve In %": "circle",
        "1st Serve Won %": "square",
        "2nd Serve In %": "diamond",
        "2nd Serve Won %": "triangle-up",
        "Double Fault %": "x",
    }

    top_tickvals: list[int] = []
    top_ticktext: list[str] = []
    if use_match_date:
        max_ticks = min(6, len(plot_df))
        step = max(1, (len(plot_df) + max_ticks - 1) // max_ticks)
        tick_rows = plot_df.iloc[::step].copy()
        if tick_rows.empty or tick_rows.iloc[-1]["Match Sequence"] != plot_df.iloc[-1]["Match Sequence"]:
            tick_rows = pd.concat([tick_rows, plot_df.tail(1)], ignore_index=True)
        tick_rows = tick_rows.drop_duplicates(subset=["Match Sequence"])
        tick_rows = tick_rows[tick_rows["Match Date"].notna()]
        top_tickvals = tick_rows["Match Sequence"].astype(int).tolist()
        top_ticktext = [
            f"{match_date.strftime('%b')} {match_date.day}"
            for match_date in tick_rows["Match Date"]
        ]

    if split_by_result and "Match Result" in plot_df.columns:
        subsets: list[tuple[str, pd.DataFrame]] = []
        for result_label in ["W", "L"]:
            subset = plot_df[plot_df["Match Result"] == result_label].copy()
            if subset.empty:
                continue
            subset = subset.reset_index(drop=True)
            subset["Match Sequence"] = range(1, len(subset) + 1)
            subsets.append((result_label, subset))

        if not subsets:
            return None

        figure = make_subplots(
            rows=len(subsets),
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.22,
            subplot_titles=tuple(f"{result_label}: Serve Statistics Trend" for result_label, _ in subsets),
        )
        for row_index, (result_label, subset) in enumerate(subsets, start=1):
            for label, numer, denom, color in selected_metrics:
                values = safe_ratio(subset[numer], subset[denom]).tolist()
                figure.add_trace(
                    go.Scatter(
                        x=subset["Match Sequence"],
                        y=values,
                        mode="lines+markers",
                        name=label,
                        line={"color": color},
                        marker={"symbol": marker_symbols.get(label, "circle"), "size": 9},
                        customdata=build_customdata(subset),
                        hovertemplate=hover_template,
                        showlegend=(row_index == 1),
                    ),
                    row=row_index,
                    col=1,
                )
            figure.update_xaxes(
                title_text="Match Order (chronological)",
                tickmode="linear",
                dtick=1 if len(subset) <= 15 else max(1, len(subset) // 8),
                row=row_index,
                col=1,
            )
            figure.update_yaxes(
                title_text="Rate",
                tickformat=".0%",
                range=[0, 1],
                row=row_index,
                col=1,
            )
    else:
        figure = go.Figure()
        for label, numer, denom, color in selected_metrics:
            values = safe_ratio(plot_df[numer], plot_df[denom]).tolist()
            figure.add_trace(
                go.Scatter(
                    x=plot_df["Match Sequence"],
                    y=values,
                    mode="lines+markers",
                    name=label,
                    line={"color": color},
                    marker={"symbol": marker_symbols.get(label, "circle"), "size": 9},
                    customdata=build_customdata(plot_df),
                    hovertemplate=hover_template,
                )
                )

    display_title = (
        title.replace("Serve Statistics Trend by Date", "Serve Statistics Trend by Match Split W/L")
        if split_by_result and "Match Result" in plot_df.columns
        else title
    )
    apply_accessible_figure_style(figure, title=display_title, height=860 if split_by_result and "Match Result" in plot_df.columns else 500)
    if not (split_by_result and "Match Result" in plot_df.columns):
        figure.update_xaxes(
            title_text="Match Order (chronological)",
            tickmode="linear",
            dtick=1 if len(plot_df) <= 15 else max(1, len(plot_df) // 8),
        )
    if top_tickvals and top_ticktext and not (split_by_result and "Match Result" in plot_df.columns):
        figure.update_layout(
            xaxis2={
                "overlaying": "x",
                "side": "top",
                "tickmode": "array",
                "tickvals": top_tickvals,
                "ticktext": top_ticktext,
                "title": {"text": "Match Date"},
                "showgrid": False,
            }
        )
    if not (split_by_result and "Match Result" in plot_df.columns):
        figure.update_yaxes(title_text="Rate", tickformat=".0%", range=[0, 1])
    return figure


def apply_accessible_figure_style(figure: go.Figure, *, title: str, height: int) -> None:
    """Apply a colorblind-safer visual baseline to all Plotly figures."""
    figure.update_layout(
        title=title,
        height=height,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFDF8",
        font={"color": "#1f1f1f"},
        colorway=[
            COLORBLIND_SAFE_CHART_COLORS["accent_red"],
            COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
            COLORBLIND_SAFE_CHART_COLORS["accent_rose"],
            COLORBLIND_SAFE_CHART_COLORS["accent_taupe"],
            COLORBLIND_SAFE_CHART_COLORS["accent_black"],
        ],
        legend_title="Metric",
    )


def build_games_diff_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render a control chart for games won minus games lost."""
    if chart_df.empty or any(column not in chart_df.columns for column in ["Games Won", "Games Lost"]):
        return None

    def add_control_traces(
        figure: go.Figure,
        frame: pd.DataFrame,
        *,
        row: int = 1,
        col: int = 1,
        show_legend: bool = True,
        use_subplots: bool = False,
    ) -> bool:
        if frame.empty:
            return False
        values = (
            pd.to_numeric(frame["Games Won"], errors="coerce").fillna(0)
            - pd.to_numeric(frame["Games Lost"], errors="coerce").fillna(0)
        )
        x_values = list(range(1, len(values) + 1))
        mean_value = float(values.mean())
        std_value = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        ucl = mean_value + 3 * std_value
        lcl = mean_value - 3 * std_value
        marker_colors = [
            COLORBLIND_SAFE_CHART_COLORS["accent_gray"]
            if value > ucl or value < lcl
            else COLORBLIND_SAFE_CHART_COLORS["accent_red"]
            for value in values
        ]

        def add_trace(trace: go.BaseTraceType) -> None:
            if use_subplots:
                figure.add_trace(trace, row=row, col=col)
            else:
                figure.add_trace(trace)

        add_trace(
            go.Scatter(
                x=x_values,
                y=values,
                mode="lines",
                name="Games Diff",
                line={"color": "#808080", "width": 1.2},
                hovertemplate="Match Sequence=%{x}<br>Games Diff=%{y:.0f}<extra></extra>",
                showlegend=False,
            )
        )
        add_trace(
            go.Scatter(
                x=x_values,
                y=values,
                mode="markers",
                name="Games Diff",
                marker={"color": marker_colors, "size": 8},
                hovertemplate="Match Sequence=%{x}<br>Games Diff=%{y:.0f}<extra></extra>",
                showlegend=False,
            )
        )
        for line_value, name, dash in [
            (mean_value, "CL", "solid"),
            (ucl, "UCL", "dash"),
            (lcl, "LCL", "dash"),
        ]:
            line_color = {
                "CL": COLORBLIND_SAFE_CHART_COLORS["accent_black"],
                "UCL": COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
                "LCL": COLORBLIND_SAFE_CHART_COLORS["accent_taupe"],
            }[name]
            add_trace(
                go.Scatter(
                    x=x_values,
                    y=[line_value] * len(x_values),
                    mode="lines",
                    name=f"{name} {line_value:.2f}",
                    line={"dash": dash, "color": line_color},
                    hoverinfo="skip",
                    showlegend=show_legend,
                )
            )
        add_trace(
            go.Scatter(
                x=x_values,
                y=[0] * len(x_values),
                mode="lines",
                name="Zero",
                line={"dash": "dot", "color": "#4D4D4D", "width": 1.0},
                hoverinfo="skip",
                showlegend=False,
            )
        )
        return True

    plot_df = chart_df.copy()
    sort_columns = [column for column in ["Match Date", "matchId"] if column in plot_df.columns]
    if sort_columns:
        plot_df = plot_df.sort_values(sort_columns, na_position="last")

    if split_by_result and "Match Result" in plot_df.columns:
        subsets = [(label, plot_df[plot_df["Match Result"] == label].copy()) for label in ["W", "L"]]
        subsets = [(label, frame) for label, frame in subsets if not frame.empty]
        if len(subsets) >= 2:
            figure = make_subplots(
                rows=2,
                cols=1,
                shared_xaxes=False,
                subplot_titles=tuple(f"{label}: Games Differential Control" for label, _ in subsets[:2]),
                vertical_spacing=0.18,
            )
            for row_index, (_label, frame) in enumerate(subsets[:2], start=1):
                add_control_traces(figure, frame, row=row_index, col=1, show_legend=(row_index == 1), use_subplots=True)
                figure.update_xaxes(title_text="Match Sequence", row=row_index, col=1)
                figure.update_yaxes(title_text="Games Won - Games Lost", row=row_index, col=1)
            apply_accessible_figure_style(figure, title=title, height=860)
            return figure
        elif subsets:
            figure = go.Figure()
            add_control_traces(figure, subsets[0][1], use_subplots=False)
            apply_accessible_figure_style(figure, title=title, height=500)
            figure.update_xaxes(title_text="Match Sequence")
            figure.update_yaxes(title_text="Games Won - Games Lost")
            return figure
    else:
        figure = go.Figure()
        add_control_traces(figure, plot_df, use_subplots=False)
        if not figure.data:
            return None
        apply_accessible_figure_style(figure, title=title, height=500)
        figure.update_xaxes(title_text="Match Sequence")
        figure.update_yaxes(title_text="Games Won - Games Lost")
        return figure
    return None


def build_funnel_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render first and second serve funnel charts."""
    required = [
        "first_serve_attempt",
        "first_serve_in",
        "first_serve_won",
        "second_serve_attempt",
        "second_serve_in",
        "second_serve_won",
    ]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    def funnel_steps(frame: pd.DataFrame):
        totals = frame[required].sum(numeric_only=True)
        first = [
            ("1st Attempts", float(totals.get("first_serve_attempt", 0))),
            ("1st In", float(totals.get("first_serve_in", 0))),
            ("1st Won", float(totals.get("first_serve_won", 0))),
        ]
        second = [
            ("2nd Attempts", float(totals.get("second_serve_attempt", 0))),
            ("2nd In", float(totals.get("second_serve_in", 0))),
            ("2nd Won", float(totals.get("second_serve_won", 0))),
        ]
        return first, second

    def percent_values(steps):
        base = steps[0][1] if steps and steps[0][1] else 0.0
        return [value / base if base else 0.0 for _, value in steps]

    def step_values(steps):
        step_rates = []
        previous = None
        for _, value in steps:
            step_rates.append((value / previous) if previous not in (None, 0.0) else 1.0)
            previous = value
        return step_rates

    figure = make_subplots(rows=1, cols=2, subplot_titles=("First Serve Funnel", "Second Serve Funnel"))
    if split_by_result and "Match Result" in chart_df.columns:
        subsets = {label: chart_df[chart_df["Match Result"] == label] for label in ["W", "L"]}
        if not subsets["W"].empty and not subsets["L"].empty:
            w_first, w_second = funnel_steps(subsets["W"])
            l_first, l_second = funnel_steps(subsets["L"])
            for col_index, steps_w, steps_l, panel_title in [
                (1, w_first, l_first, "First Serve Funnel (W vs L)"),
                (2, w_second, l_second, "Second Serve Funnel (W vs L)"),
            ]:
                pct_w = percent_values(steps_w)
                pct_l = percent_values(steps_l)
                labels = [label for label, _ in steps_w]
                figure.add_trace(
                    go.Bar(
                        x=pct_w,
                        y=labels,
                        orientation="h",
                        name="W",
                        marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_red"],
                        text=[f"{pct:.0%} ({int(raw):,})" for (_, raw), pct in zip(steps_w, pct_w)],
                        textposition="outside",
                        customdata=[[raw, pct] for (_, raw), pct in zip(steps_w, pct_w)],
                        hovertemplate=(
                            "%{y}<br>"
                            "Result=W<br>"
                            "Share of attempts=%{customdata[1]:.0%}<br>"
                            "Raw count=%{customdata[0]:,.0f}<extra></extra>"
                        ),
                        showlegend=(col_index == 1),
                    ),
                    row=1,
                    col=col_index,
                )
                figure.add_trace(
                    go.Bar(
                        x=pct_l,
                        y=labels,
                        orientation="h",
                        name="L",
                        marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
                        text=[f"{pct:.0%} ({int(raw):,})" for (_, raw), pct in zip(steps_l, pct_l)],
                        textposition="outside",
                        customdata=[[raw, pct] for (_, raw), pct in zip(steps_l, pct_l)],
                        hovertemplate=(
                            "%{y}<br>"
                            "Result=L<br>"
                            "Share of attempts=%{customdata[1]:.0%}<br>"
                            "Raw count=%{customdata[0]:,.0f}<extra></extra>"
                        ),
                        showlegend=(col_index == 1),
                    ),
                    row=1,
                    col=col_index,
                )
                figure.layout.annotations[col_index - 1].update(text=panel_title)
        else:
            split_by_result = False
    if not split_by_result or "Match Result" not in chart_df.columns:
        first_steps, second_steps = funnel_steps(chart_df)
        for col_index, steps, color in [
            (1, first_steps, COLORBLIND_SAFE_CHART_COLORS["accent_red"]),
            (2, second_steps, COLORBLIND_SAFE_CHART_COLORS["accent_gray"]),
        ]:
            percentages = percent_values(steps)
            step_rates = step_values(steps)
            figure.add_trace(
                go.Bar(
                    x=percentages,
                    y=[label for label, _ in steps],
                    orientation="h",
                    marker_color=color,
                    text=[
                        f"{pct:.0%} ({int(raw):,})" if idx == 0 else f"{pct:.0%} ({step:.0%} step)"
                        for idx, ((_, raw), pct, step) in enumerate(zip(steps, percentages, step_rates))
                    ],
                    textposition="outside",
                    customdata=[[raw, pct, step] for (_, raw), pct, step in zip(steps, percentages, step_rates)],
                    hovertemplate=(
                        "%{y}<br>"
                        "Share of attempts=%{customdata[1]:.0%}<br>"
                        "Raw count=%{customdata[0]:,.0f}<br>"
                        "Step conversion=%{customdata[2]:.0%}<extra></extra>"
                    ),
                    showlegend=False,
                ),
                row=1,
                col=col_index,
            )

    if not figure.data:
        return None
    figure.update_xaxes(range=[0, 1.05], tickformat=".0%", title_text="% of Attempts")
    figure.update_yaxes(categoryorder="array", categoryarray=["1st Won", "1st In", "1st Attempts"], row=1, col=1)
    figure.update_yaxes(categoryorder="array", categoryarray=["2nd Won", "2nd In", "2nd Attempts"], row=1, col=2)
    apply_accessible_figure_style(figure, title=title, height=500)
    figure.update_layout(barmode="group", legend_title="Result")
    return figure


def build_rate_heatmap(
    value_matrix: pd.DataFrame,
    title: str,
    x_label: str,
    y_label: str,
    zmin: float,
    zmax: float,
    colorscale: list[list[float | str]],
    text_matrix: list[list[str]],
    hover_matrix: list[list[str]] | None = None,
    colorbar_title: str | None = None,
) -> go.Figure:
    """Render a labeled heatmap."""
    figure = go.Figure(
        data=go.Heatmap(
            z=value_matrix.values.astype(float),
            x=value_matrix.columns.tolist(),
            y=value_matrix.index.tolist(),
            colorscale=colorscale,
            zmin=zmin,
            zmax=zmax,
            text=text_matrix,
            texttemplate="%{text}",
            customdata=hover_matrix,
            hovertemplate="%{customdata}<extra></extra>" if hover_matrix else "%{x}<br>%{y}<br>%{z:.1%}<extra></extra>",
            colorbar={"title": colorbar_title} if colorbar_title else None,
        )
    )
    apply_accessible_figure_style(figure, title=title, height=520)
    figure.update_xaxes(title_text=x_label)
    figure.update_yaxes(title_text=y_label)
    return figure


def build_rally_profile_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render rally profile win-rate heatmap."""
    required = ["short_rally_won", "medium_rally_won", "long_rally_won", "Match Result"]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    plot_df = chart_df.copy()
    total_rally_wins = (
        pd.to_numeric(plot_df["short_rally_won"], errors="coerce").fillna(0)
        + pd.to_numeric(plot_df["medium_rally_won"], errors="coerce").fillna(0)
        + pd.to_numeric(plot_df["long_rally_won"], errors="coerce").fillna(0)
    )
    plot_df = plot_df[total_rally_wins > 0].copy()
    if plot_df.empty:
        return None

    plot_df["Short Share"] = safe_ratio(plot_df["short_rally_won"], total_rally_wins.loc[plot_df.index])
    plot_df["Long Share"] = safe_ratio(plot_df["long_rally_won"], total_rally_wins.loc[plot_df.index])
    plot_df["Short Tier"] = tier_from_quantiles(plot_df["Short Share"])
    plot_df["Long Tier"] = tier_from_quantiles(plot_df["Long Share"])
    plot_df["is_win"] = (plot_df["Match Result"] == "W").astype("int64")
    plot_df = plot_df.dropna(subset=["Short Tier", "Long Tier"])
    if plot_df.empty:
        return None

    labels = ["Low", "Mid", "High"]
    if split_by_result:
        match_counts = (
            plot_df.pivot_table(index="Long Tier", columns="Short Tier", values="matchId", aggfunc="count", observed=False)
            .reindex(index=labels, columns=labels)
            .fillna(0)
        )
        wins = (
            plot_df[plot_df["Match Result"] == "W"]
            .pivot_table(index="Long Tier", columns="Short Tier", values="matchId", aggfunc="count", observed=False)
            .reindex(index=labels, columns=labels)
            .fillna(0)
        )
        losses = (
            plot_df[plot_df["Match Result"] == "L"]
            .pivot_table(index="Long Tier", columns="Short Tier", values="matchId", aggfunc="count", observed=False)
            .reindex(index=labels, columns=labels)
            .fillna(0)
        )
        total_matches = max(float(match_counts.values.sum()), 1.0)
        win_share = wins / total_matches
        loss_share = losses / total_matches
        diff = win_share - loss_share
        max_abs = max(float(abs(diff.values).max()), 0.01)
        text = [
            [
                (
                    f"W matches={int(wins.iat[i, j])} ({float(win_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"L matches={int(losses.iat[i, j])} ({float(loss_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"win rate in profile="
                    f"{((float(wins.iat[i, j]) / float(match_counts.iat[i, j])) if float(match_counts.iat[i, j]) > 0 else 0.0):.0%} "
                    f"(n={int(match_counts.iat[i, j])})"
                )
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        hover = [
            [
                (
                    f"Short Rally Share Tier: {labels[j]}<br>"
                    f"Long Rally Share Tier: {labels[i]}<br>"
                    f"W matches={int(wins.iat[i, j])} ({float(win_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"L matches={int(losses.iat[i, j])} ({float(loss_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"Win rate in profile={(float(wins.iat[i, j]) / float(match_counts.iat[i, j])):.0%}<br>"
                    f"Total matches in cell={int(match_counts.iat[i, j])}"
                    if float(match_counts.iat[i, j]) > 0
                    else (
                        f"Short Rally Share Tier: {labels[j]}<br>"
                        f"Long Rally Share Tier: {labels[i]}<br>"
                        "No matches in this profile"
                    )
                )
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        return build_rate_heatmap(
            diff,
            title,
            "Short Rally Share Tier (<=4 shots share)",
            "Long Rally Share Tier (>=9 shots share)",
            -max_abs,
            max_abs,
            COLORBLIND_SAFE_DIVERGING_SCALE,
            text,
            hover,
            "W match share - L match share",
        )

    win_rate = (
        plot_df.pivot_table(index="Long Tier", columns="Short Tier", values="is_win", aggfunc="mean", observed=False)
        .reindex(index=labels, columns=labels)
        .fillna(0)
    )
    match_counts = (
        plot_df.pivot_table(index="Long Tier", columns="Short Tier", values="matchId", aggfunc="count", observed=False)
        .reindex(index=labels, columns=labels)
        .fillna(0)
    )
    text = [
        [f"{win_rate.iat[i, j]:.0%}<br>matches={int(match_counts.iat[i, j])}" for j in range(len(labels))]
        for i in range(len(labels))
    ]
    return build_rate_heatmap(
        win_rate,
        title,
        "Short Rally Share Tier",
        "Long Rally Share Tier",
        0,
        1,
        COLORBLIND_SAFE_SEQUENTIAL_SCALE,
        text,
    )


def build_set_share_heatmap(chart_df: pd.DataFrame, split_by_result: bool, title: str, left_col: str, bottom_col: str) -> go.Figure | None:
    """Render the pressure and rally bin heatmaps based on set share."""
    plot_df = chart_df.copy()
    plot_df["set_total"] = (
        pd.to_numeric(plot_df["Sets Won"], errors="coerce").fillna(0)
        + pd.to_numeric(plot_df["Sets Lost"], errors="coerce").fillna(0)
    )
    plot_df = plot_df[plot_df["set_total"] > 0].copy()
    if plot_df.empty:
        return None

    labels = ["Low", "Mid", "High"]
    all_sets = (
        plot_df.pivot_table(index=left_col, columns=bottom_col, values="set_total", aggfunc="sum", observed=False)
        .reindex(index=labels, columns=labels)
        .fillna(0)
    )
    total_sets = max(float(all_sets.values.sum()), 1.0)

    if split_by_result:
        wins = (
            plot_df[plot_df["Match Result"] == "W"]
            .pivot_table(index=left_col, columns=bottom_col, values="set_total", aggfunc="sum", observed=False)
            .reindex(index=labels, columns=labels)
            .fillna(0)
        )
        losses = (
            plot_df[plot_df["Match Result"] == "L"]
            .pivot_table(index=left_col, columns=bottom_col, values="set_total", aggfunc="sum", observed=False)
            .reindex(index=labels, columns=labels)
            .fillna(0)
        )
        win_share = wins / total_sets
        loss_share = losses / total_sets
        diff = win_share - loss_share
        max_abs = max(float(abs(diff.values).max()), 0.01)
        text = [
            [
                (
                    f"win sets={int(wins.iat[i, j])} ({float(win_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"loss sets={int(losses.iat[i, j])} ({float(loss_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"total sets in cell={int(all_sets.iat[i, j])}"
                )
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        hover = [
            [
                (
                    f"{bottom_col.replace(' Tier', '')}: {labels[j]}<br>"
                    f"{left_col.replace(' Tier', '')}: {labels[i]}<br>"
                    f"W sets={int(wins.iat[i, j])} ({float(win_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"L sets={int(losses.iat[i, j])} ({float(loss_share.iat[i, j]):.0%} of all filtered)<br>"
                    f"Total sets in cell={int(all_sets.iat[i, j])}"
                )
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        return build_rate_heatmap(
            diff,
            title,
            bottom_col.replace(" Tier", ""),
            left_col.replace(" Tier", ""),
            -max_abs,
            max_abs,
            COLORBLIND_SAFE_DIVERGING_SCALE,
            text,
            hover,
            "W share of all filtered sets - L share of all filtered sets",
        )

    share = all_sets / total_sets
    text = [
        [f"{share.iat[i, j]:.0%}<br>sets={int(all_sets.iat[i, j])}" for j in range(len(labels))]
        for i in range(len(labels))
    ]
    return build_rate_heatmap(
        share,
        title,
        bottom_col.replace(" Tier", ""),
        left_col.replace(" Tier", ""),
        0,
        1,
        COLORBLIND_SAFE_SEQUENTIAL_SCALE,
        text,
    )


def build_pressure_bins_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render the break-point pressure heatmap."""
    required = [
        "break_point_total",
        "break_point_won",
        "break_point_faced",
        "break_point_saved",
        "Match Result",
        "Sets Won",
        "Sets Lost",
    ]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    plot_df = chart_df.copy()
    plot_df["BP Won %"] = safe_ratio(plot_df["break_point_won"], plot_df["break_point_total"])
    plot_df["BP Saved %"] = safe_ratio(plot_df["break_point_saved"], plot_df["break_point_faced"])
    plot_df["BP Won Tier"] = fixed_tier(plot_df["BP Won %"])
    plot_df["BP Saved Tier"] = fixed_tier(plot_df["BP Saved %"])
    plot_df = plot_df.dropna(subset=["BP Won Tier", "BP Saved Tier"])
    if plot_df.empty:
        return None

    return build_set_share_heatmap(plot_df, split_by_result, title, "BP Saved Tier", "BP Won Tier")


def build_rally_bins_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render the rally-share set distribution heatmap."""
    required = ["short_rally_won", "medium_rally_won", "long_rally_won", "Match Result", "Sets Won", "Sets Lost"]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    plot_df = chart_df.copy()
    total_rally_wins = (
        pd.to_numeric(plot_df["short_rally_won"], errors="coerce").fillna(0)
        + pd.to_numeric(plot_df["medium_rally_won"], errors="coerce").fillna(0)
        + pd.to_numeric(plot_df["long_rally_won"], errors="coerce").fillna(0)
    )
    plot_df = plot_df[total_rally_wins > 0].copy()
    if plot_df.empty:
        return None

    plot_df["Short Share"] = safe_ratio(plot_df["short_rally_won"], total_rally_wins.loc[plot_df.index])
    plot_df["Long Share"] = safe_ratio(plot_df["long_rally_won"], total_rally_wins.loc[plot_df.index])
    plot_df["Short Tier"] = tier_from_quantiles(plot_df["Short Share"])
    plot_df["Long Tier"] = tier_from_quantiles(plot_df["Long Share"])
    plot_df = plot_df.dropna(subset=["Short Tier", "Long Tier"])
    if plot_df.empty:
        return None

    return build_set_share_heatmap(plot_df, split_by_result, title, "Long Tier", "Short Tier")


def build_win_loss_chart(chart_df: pd.DataFrame, title: str) -> go.Figure | None:
    """Render yearly wins, losses, and win rate."""
    if chart_df.empty or "Match Year" not in chart_df.columns or "Match Result" not in chart_df.columns:
        return None

    by_year = (
        chart_df.groupby(["Match Year", "Match Result"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .sort_values("Match Year")
    )
    for column in ["W", "L"]:
        if column not in by_year.columns:
            by_year[column] = 0
    by_year["Total"] = by_year["W"] + by_year["L"]
    by_year["Win Rate"] = safe_ratio(by_year["W"], by_year["Total"])

    figure = make_subplots(specs=[[{"secondary_y": True}]])
    x_values = by_year["Match Year"].astype(str).tolist()
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=by_year["W"],
            mode="lines+markers",
            name="Wins",
            line={"color": COLORBLIND_SAFE_CHART_COLORS["accent_red"]},
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=by_year["L"],
            mode="lines+markers",
            name="Losses",
            line={"color": COLORBLIND_SAFE_CHART_COLORS["accent_gray"]},
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=by_year["Win Rate"],
            mode="lines+markers",
            name="Win Rate",
            line={"color": COLORBLIND_SAFE_CHART_COLORS["accent_black"]},
        ),
        secondary_y=True,
    )
    apply_accessible_figure_style(figure, title=title, height=420)
    figure.update_yaxes(title_text="Matches", secondary_y=False)
    figure.update_yaxes(title_text="Win Rate", tickformat=".0%", range=[0, 1], secondary_y=True)
    return figure


def build_sets_games_chart(chart_df: pd.DataFrame, title: str) -> go.Figure | None:
    """Render sets and games won/lost by year."""
    required = ["Match Year", "Sets Won", "Sets Lost", "Games Won", "Games Lost"]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    by_year = (
        chart_df.groupby("Match Year", dropna=False)[["Sets Won", "Sets Lost", "Games Won", "Games Lost"]]
        .sum()
        .reset_index()
        .sort_values("Match Year")
    )

    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Sets", "Games"))
    x_values = by_year["Match Year"].astype(str).tolist()
    figure.add_trace(
        go.Bar(x=x_values, y=by_year["Sets Won"], name="Sets Won", marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_red"]),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Bar(x=x_values, y=by_year["Sets Lost"], name="Sets Lost", marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_gray"]),
        row=1,
        col=1,
    )
    figure.add_trace(
        go.Bar(x=x_values, y=by_year["Games Won"], name="Games Won", marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_rose"]),
        row=2,
        col=1,
    )
    figure.add_trace(
        go.Bar(x=x_values, y=by_year["Games Lost"], name="Games Lost", marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_black"]),
        row=2,
        col=1,
    )
    apply_accessible_figure_style(figure, title=title, height=520)
    figure.update_layout(barmode="group", legend_title="Metric")
    return figure


banner_logo_path = PROJECT_ROOT / "assets" / "ncstate-circle-blk-kowolf.png"
banner_logo_uri = image_to_data_uri(banner_logo_path)
banner_logo_html = (
    f'<div class="nc-state-banner__logo"><img src="{banner_logo_uri}" alt="NC State logo" /></div>'
    if banner_logo_uri
    else ""
)

st.markdown(
    f"""
    <section class="nc-state-banner">
        {banner_logo_html}
        <div class="nc-state-banner__content">
            <div class="nc-state-banner__eyebrow">NC State Women's Tennis</div>
            <h1 class="nc-state-banner__title">Tennis Match Summary</h1>
            <div class="nc-state-banner__subtitle">
                Match analytics and reporting for local review, seasonal trends, and opponent scouting.
            </div>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)
st.caption("Cross-platform local browser app for Windows and macOS.")

default_csv = PROJECT_ROOT / "data" / "input" / "StatsReport_TeamNames.csv"
default_benchmark_xlsx = PROJECT_ROOT / "data" / "input" / "Tour Data 2025.xlsx"
with st.sidebar:
    st.header("Data")
    input_csv = st.text_input("Source CSV", value=str(default_csv), disabled=True)
    name_map = st.text_input("Name Map XLSX (optional)", value="", disabled=True)
    benchmark_xlsx = st.text_input(
        "Tour Benchmark XLSX (optional)",
        value=str(default_benchmark_xlsx) if default_benchmark_xlsx.exists() else "",
        disabled=True,
    )
    if st.button("Reload Data"):
        st.cache_data.clear()

source_path = Path(input_csv)
name_map_path = Path(name_map) if name_map.strip() else None
benchmark_path = Path(benchmark_xlsx) if benchmark_xlsx.strip() else None

if not source_path.exists():
    st.error(f"Missing source CSV: {source_path}")
    st.stop()

csv_mtime = source_path.stat().st_mtime
name_map_mtime = name_map_path.stat().st_mtime if name_map_path and name_map_path.exists() else None
summary_df = load_summary_cached(str(source_path), str(name_map_path) if name_map_path else None, csv_mtime, name_map_mtime)
benchmark_df = pd.DataFrame()
if benchmark_path and benchmark_path.exists():
    benchmark_mtime = benchmark_path.stat().st_mtime
    benchmark_df = load_benchmark_workbook(str(benchmark_path), benchmark_mtime)
elif benchmark_path:
    st.warning(f"Tour benchmark workbook not found: {benchmark_path}")

filter_values = available_filter_values(summary_df)
with st.sidebar:
    st.header("Filters")
    selected_player = st.selectbox("Player", filter_values["players"])
    selected_year = st.selectbox("Year", filter_values["years"])
    selected_month = st.selectbox("Month", filter_values["months"])
    selected_opp_team = st.selectbox("Opp Team", filter_values["opp_teams"])
    selected_season = st.selectbox("Season", filter_values["seasons"])
    split_charts = st.checkbox("Split Charts W/L", value=False)
    st.header("Baselines")
    available_baseline_levels = [
        level
        for level, column in BENCHMARK_LEVEL_COLUMNS.items()
        if not benchmark_df.empty and column in benchmark_df.columns
    ]
    selected_baseline_levels = st.multiselect(
        "Benchmark Lines",
        available_baseline_levels,
        default=["Tour Avg"] if "Tour Avg" in available_baseline_levels else [],
        help="Overlay tour reference levels from the benchmark workbook on supported charts.",
    )

filtered_df = filter_matches(
    summary_df,
    player=selected_player,
    year=None if selected_year == "All" else int(selected_year),
    month_name=selected_month,
    opp_team=selected_opp_team,
    season_label=selected_season,
)
current_scope = scope_text(selected_player, selected_year, selected_month, selected_opp_team, selected_season)
base_chart_key_parts = (
    selected_player,
    selected_year,
    selected_month,
    selected_opp_team,
    selected_season,
    split_charts,
    tuple(selected_baseline_levels),
    len(filtered_df),
)
insights = summarize_key_insights(filtered_df)

metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
metric_col1.metric("Matches", f"{insights['total_matches']:,}")
metric_col2.metric("Players", f"{insights['total_players']:,}")
metric_col3.metric("Wins", f"{insights['wins']:,}")
metric_col4.metric("Win Rate", f"{insights['win_rate']:.1%}")

download_col1, download_col2 = st.columns(2)
download_col1.download_button(
    "Download Filtered CSV",
    data=to_csv_bytes(filtered_df),
    file_name="Tennis_MatchSummary.csv",
    mime="text/csv",
    width="stretch",
)
download_col2.download_button(
    "Download Filtered Excel Report",
    data=to_excel_bytes(filtered_df),
    file_name="Tennis_MatchSummary_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="stretch",
)

tabs = st.tabs(
    [
        "Overview",
        "Raw Matches",
        "Serve / Return Match Stats",
        "Serve Stats Trend",
        "Games Diff Control",
        "Serve Efficiency Funnel",
        "Rally Length Wins",
        "Rally Bins",
        "Pressure Bins",
        "Source Row Edits",
        "Raw Data Dictionary",
    ]
)

with tabs[0]:
    st.subheader(f"Overview: {current_scope}")
    overview_col1, overview_col2 = st.columns(2)
    win_loss_fig = build_win_loss_chart(filtered_df, f"Win/Loss Trend ({current_scope})")
    sets_games_fig = build_sets_games_chart(filtered_df, f"Sets & Games by Year ({current_scope})")
    if win_loss_fig:
        overview_col1.plotly_chart(
            win_loss_fig,
            width="stretch",
            key=chart_key("win_loss", *base_chart_key_parts),
        )
    if sets_games_fig:
        overview_col2.plotly_chart(
            sets_games_fig,
            width="stretch",
            key=chart_key("sets_games", *base_chart_key_parts),
        )

    pivot_df = build_pivot_summary(filtered_df)
    st.markdown("**Pivot Summary**")
    st.dataframe(style_banded_rows(pivot_df), width="stretch")

with tabs[1]:
    st.subheader(f"Raw Matches: {current_scope}")
    st.dataframe(style_banded_rows(filtered_df), width="stretch")

with tabs[2]:
    st.subheader(f"Serve / Return Match Stats: {current_scope}")
    ace_df = build_serve_return_match_stats(filtered_df)
    default_columns = [column for column, _ in PIVOT_ACE_COLUMN_DEFS]
    selected_columns = st.multiselect(
        "Visible Columns",
        default_columns,
        default=default_columns,
        key="ace_columns",
    )
    if not ace_df.empty:
        display_df = ace_df[["Player"] + selected_columns]
        percent_formatters = {
            column: "{:.1%}"
            for column in display_df.columns
            if "%" in column
        }
        st.dataframe(
            style_banded_rows(display_df, formatters=percent_formatters),
            width="stretch",
        )
        benchmark_snapshot_df = build_benchmark_snapshot(
            filtered_df,
            benchmark_df,
            selected_baseline_levels,
        )
        if not benchmark_snapshot_df.empty:
            benchmark_formatters = {
                column: "{:.1%}"
                for column in benchmark_snapshot_df.columns
                if column != "Metric"
            }
            st.caption("Filtered aggregate compared with selected tour baselines.")
            st.dataframe(
                style_banded_rows(benchmark_snapshot_df, formatters=benchmark_formatters),
                width="stretch",
            )
    else:
        st.info("No serve/return match stats available for the current filters.")

with tabs[3]:
    st.subheader(f"Serve Stats Trend: {current_scope}")
    all_serve_trend_metric_labels = [label for label, _, _, _ in SERVE_TREND_METRICS]
    if "serve_trend_metrics" not in st.session_state:
        st.session_state["serve_trend_metrics"] = all_serve_trend_metric_labels
    reset_col, metrics_col = st.columns([0.7, 8], gap="small")
    with reset_col:
        st.markdown("<div style='height: 1.9rem;'></div>", unsafe_allow_html=True)
        if st.button("Reset", key="reset_serve_trend_metrics"):
            st.session_state["serve_trend_metrics"] = all_serve_trend_metric_labels
    with metrics_col:
        selected_metric_labels = st.multiselect(
            "Serve Trend Metrics",
            all_serve_trend_metric_labels,
            key="serve_trend_metrics",
        )
    selected_metrics = [
        metric for metric in SERVE_TREND_METRICS if metric[0] in selected_metric_labels
    ]
    if selected_season == "All":
        season_chart_df = with_season_columns(filtered_df)
        available_seasons = (
            season_chart_df[["_Season Sort", "_Season Label"]]
            .drop_duplicates()
            .sort_values(["_Season Sort", "_Season Label"], na_position="last")
        )
        rendered_chart = False
        for _, season_row in available_seasons.iterrows():
            season_label = str(season_row["_Season Label"])
            season_subset = season_chart_df[season_chart_df["_Season Label"] == season_label].copy()
            serve_trend_fig = plot_metric_line_chart(
                season_subset,
                selected_metrics,
                split_charts,
                f"Serve Statistics Trend by Date ({season_label})",
            )
            if not serve_trend_fig:
                continue
            rendered_chart = True
            if not split_charts:
                add_benchmark_lines(
                    serve_trend_fig,
                    selected_metrics,
                    benchmark_df,
                    selected_baseline_levels,
                )
            st.markdown(f"**{season_label}**")
            st.plotly_chart(
                serve_trend_fig,
                width="stretch",
                key=chart_key(
                    "serve_trend",
                    *base_chart_key_parts,
                    season_label,
                    selected_metric_labels,
                ),
            )
        if not rendered_chart:
            st.info("No serve trend data is available for the current filters.")
    else:
        serve_trend_fig = plot_metric_line_chart(
            filtered_df,
            selected_metrics,
            split_charts,
            f"Serve Statistics Trend by Date ({current_scope})",
        )
        if serve_trend_fig:
            if not split_charts:
                add_benchmark_lines(
                    serve_trend_fig,
                    selected_metrics,
                    benchmark_df,
                    selected_baseline_levels,
                )
            st.plotly_chart(
                serve_trend_fig,
                width="stretch",
                key=chart_key(
                    "serve_trend",
                    *base_chart_key_parts,
                    selected_metric_labels,
                ),
            )
        else:
            st.info("No serve trend data is available for the current filters.")

with tabs[4]:
    st.subheader(f"Games Diff Control: {current_scope}")
    games_diff_title = (
        f"Games Differential Control Chart Split by Result ({current_scope})"
        if split_charts
        else f"Games Differential Control ({current_scope})"
    )
    games_diff_fig = build_games_diff_chart(filtered_df, split_charts, games_diff_title)
    if games_diff_fig:
        st.plotly_chart(
            games_diff_fig,
            width="stretch",
            key=chart_key("games_diff", *base_chart_key_parts),
        )
    else:
        st.info("No games-diff data is available for the current filters.")

with tabs[5]:
    st.subheader(f"Serve Efficiency Funnel: {current_scope}")
    funnel_title = (
        f"Serve Efficiency Funnel Split by Result ({current_scope})"
        if split_charts
        else f"Serve Efficiency Funnel ({current_scope})"
    )
    funnel_fig = build_funnel_chart(filtered_df, split_charts, funnel_title)
    if funnel_fig:
        st.plotly_chart(
            funnel_fig,
            width="stretch",
            key=chart_key("serve_funnel", *base_chart_key_parts),
        )
    else:
        st.info("No serve funnel data is available for the current filters.")

with tabs[6]:
    st.subheader(f"Rally Length Wins: {current_scope}")
    rally_profile_title = (
        f"Rally Profile vs Match Wins (split W/L) ({current_scope})"
        if split_charts
        else f"Rally Profile vs Match Wins (win rate by bin) ({current_scope})"
    )
    rally_profile_fig = build_rally_profile_chart(filtered_df, split_charts, rally_profile_title)
    if rally_profile_fig:
        st.plotly_chart(
            rally_profile_fig,
            width="stretch",
            key=chart_key("rally_profile", *base_chart_key_parts),
        )
    else:
        st.info("No rally profile data is available for the current filters.")

with tabs[7]:
    st.subheader(f"Rally Bins: {current_scope}")
    rally_bins_title = (
        f"Rally Bins Split W/L (each % = sets in cell / all currently filtered sets) ({current_scope})"
        if split_charts
        else f"Rally Length Bins (% of Total Sets) ({current_scope})"
    )
    rally_bins_fig = build_rally_bins_chart(filtered_df, split_charts, rally_bins_title)
    if rally_bins_fig:
        st.plotly_chart(
            rally_bins_fig,
            width="stretch",
            key=chart_key("rally_bins", *base_chart_key_parts),
        )
    else:
        st.info("No rally-bin data is available for the current filters.")

with tabs[8]:
    st.subheader(f"Pressure Bins: {current_scope}")
    pressure_title = (
        f"Pressure Bins Split W/L (each % = sets in cell / all currently filtered sets) ({current_scope})"
        if split_charts
        else f"Pressure Performance Bins (% of Total Sets) ({current_scope})"
    )
    pressure_fig = build_pressure_bins_chart(filtered_df, split_charts, pressure_title)
    if pressure_fig:
        st.plotly_chart(
            pressure_fig,
            width="stretch",
            key=chart_key("pressure_bins", *base_chart_key_parts),
        )
        if selected_baseline_levels and not benchmark_df.empty:
            pressure_snapshot_df = build_benchmark_snapshot(
                filtered_df,
                benchmark_df,
                selected_baseline_levels,
            )
            if not pressure_snapshot_df.empty and "Metric" in pressure_snapshot_df.columns:
                pressure_snapshot_df = pressure_snapshot_df[
                    pressure_snapshot_df["Metric"].isin(["Break Points Won", "Break Points Saved"])
                ]
            if not pressure_snapshot_df.empty:
                pressure_formatters = {
                    column: "{:.1%}"
                    for column in pressure_snapshot_df.columns
                    if column != "Metric"
                }
                st.caption("Pressure baseline values are summarized below the chart.")
                st.dataframe(
                    style_banded_rows(pressure_snapshot_df, formatters=pressure_formatters),
                    width="stretch",
                )
    else:
        st.info("No pressure-bin data is available for the current filters.")

with tabs[9]:
    st.subheader("Source Row Edits")
    review_df, review_index_map, source_raw_df = load_source_review_cached(str(source_path), csv_mtime)
    st.caption("This tab is temporarily visible but disabled.")
    edited_df = st.data_editor(
        review_df,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=True,
        column_config={
            "_review_id": st.column_config.NumberColumn("Review ID", disabled=True),
            "rows_affected": st.column_config.NumberColumn("Rows Affected", disabled=True),
            "Delete": st.column_config.CheckboxColumn("Delete"),
        },
    )
    st.caption("Edit grouped source rows directly here. Use the Delete column to remove grouped rows from the source CSV.")
    if st.button("Save Source CSV Changes", type="primary", disabled=True):
        updated_summary = save_source_review_changes(
            edited_df,
            review_index_map,
            source_raw_df,
            str(source_path),
        )
        st.cache_data.clear()
        st.success(f"Saved changes to {source_path.name} and rebuilt the summary ({len(updated_summary):,} rows).")
        st.rerun()

with tabs[10]:
    st.subheader("Raw Data Dictionary")
    dictionary_df = build_raw_data_dictionary(filtered_df if not filtered_df.empty else summary_df)
    st.dataframe(style_banded_rows(dictionary_df), width="stretch")
