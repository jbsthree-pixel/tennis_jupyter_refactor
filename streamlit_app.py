"""Cross-platform browser app for interactive tennis match analysis."""

from __future__ import annotations

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
from tennis_jupyter.constants import PIVOT_ACE_COLUMN_DEFS, SERVE_TREND_METRICS  # noqa: E402
from tennis_jupyter.notebook import load_match_summary  # noqa: E402
from tennis_jupyter.reporting import write_excel_report  # noqa: E402
from tennis_jupyter.shared import safe_ratio  # noqa: E402


st.set_page_config(page_title="Tennis Match Summary", layout="wide")


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


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a dataframe to UTF-8 CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize the report workbook to in-memory Excel bytes."""
    buffer = io.BytesIO()
    write_excel_report(df, buffer)
    buffer.seek(0)
    return buffer.getvalue()


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
    """Render an interactive serve trend chart by match sequence."""
    if chart_df.empty or not selected_metrics:
        return None

    needed = sorted({column for _, numer, denom, _ in selected_metrics for column in [numer, denom]})
    missing = [column for column in needed if column not in chart_df.columns]
    if missing:
        return None

    plot_df = chart_df.copy()
    sort_columns = [column for column in ["Match Date", "matchId"] if column in plot_df.columns]
    if sort_columns:
        plot_df = plot_df.sort_values(sort_columns, na_position="last")
    plot_df["Match Sequence"] = range(1, len(plot_df) + 1)

    figure = go.Figure()
    if split_by_result and "Match Result" in plot_df.columns:
        for result_label, dash in [("W", "solid"), ("L", "dash")]:
            subset = plot_df[plot_df["Match Result"] == result_label].copy()
            if subset.empty:
                continue
            subset["Match Sequence"] = range(1, len(subset) + 1)
            for label, numer, denom, color in selected_metrics:
                values = safe_ratio(subset[numer], subset[denom]).tolist()
                figure.add_trace(
                    go.Scatter(
                        x=subset["Match Sequence"],
                        y=values,
                        mode="lines+markers",
                        name=f"{result_label} - {label}",
                        line={"color": color, "dash": dash},
                    )
                )
    else:
        for label, numer, denom, color in selected_metrics:
            values = safe_ratio(plot_df[numer], plot_df[denom]).tolist()
            figure.add_trace(
                go.Scatter(
                    x=plot_df["Match Sequence"],
                    y=values,
                    mode="lines+markers",
                    name=label,
                    line={"color": color},
                )
            )

    figure.update_layout(
        title=title,
        xaxis_title="Match Sequence",
        yaxis_title="Rate",
        yaxis_tickformat=".0%",
        yaxis_range=[0, 1],
        legend_title="Metric",
        height=500,
    )
    return figure


def build_games_diff_chart(chart_df: pd.DataFrame, split_by_result: bool, title: str) -> go.Figure | None:
    """Render a control chart for games won minus games lost."""
    if chart_df.empty or any(column not in chart_df.columns for column in ["Games Won", "Games Lost"]):
        return None

    def add_control_traces(figure: go.Figure, frame: pd.DataFrame, label_prefix: str = "") -> None:
        if frame.empty:
            return
        values = (
            pd.to_numeric(frame["Games Won"], errors="coerce").fillna(0)
            - pd.to_numeric(frame["Games Lost"], errors="coerce").fillna(0)
        )
        x_values = list(range(1, len(values) + 1))
        mean_value = float(values.mean())
        std_value = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        ucl = mean_value + 3 * std_value
        lcl = mean_value - 3 * std_value
        name_prefix = f"{label_prefix} " if label_prefix else ""

        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=values,
                mode="lines+markers",
                name=f"{name_prefix}Games Diff".strip(),
            )
        )
        for line_value, name, dash in [
            (mean_value, "CL", "solid"),
            (ucl, "UCL", "dash"),
            (lcl, "LCL", "dash"),
        ]:
            figure.add_trace(
                go.Scatter(
                    x=x_values,
                    y=[line_value] * len(x_values),
                    mode="lines",
                    name=f"{name_prefix}{name}".strip(),
                    line={"dash": dash},
                )
            )

    figure = go.Figure()
    plot_df = chart_df.copy()
    sort_columns = [column for column in ["Match Date", "matchId"] if column in plot_df.columns]
    if sort_columns:
        plot_df = plot_df.sort_values(sort_columns, na_position="last")

    if split_by_result and "Match Result" in plot_df.columns:
        for result_label in ["W", "L"]:
            add_control_traces(figure, plot_df[plot_df["Match Result"] == result_label], result_label)
    else:
        add_control_traces(figure, plot_df)

    if not figure.data:
        return None
    figure.update_layout(title=title, xaxis_title="Match Sequence", yaxis_title="Games Diff", height=500)
    return figure


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

    figure = make_subplots(rows=1, cols=2, subplot_titles=("First Serve Funnel", "Second Serve Funnel"))
    if split_by_result and "Match Result" in chart_df.columns:
        for result_label, color in [("W", "#D14905"), ("L", "#7E0000")]:
            subset = chart_df[chart_df["Match Result"] == result_label]
            if subset.empty:
                continue
            first_steps, second_steps = funnel_steps(subset)
            for col_index, steps in [(1, first_steps), (2, second_steps)]:
                figure.add_trace(
                    go.Bar(
                        x=percent_values(steps),
                        y=[label for label, _ in steps],
                        orientation="h",
                        name=result_label,
                        marker_color=color,
                        text=[f"{value:.0%}" for value in percent_values(steps)],
                        textposition="outside",
                    ),
                    row=1,
                    col=col_index,
                )
    else:
        first_steps, second_steps = funnel_steps(chart_df)
        for col_index, steps, color in [(1, first_steps, "#D14905"), (2, second_steps, "#7E0000")]:
            figure.add_trace(
                go.Bar(
                    x=percent_values(steps),
                    y=[label for label, _ in steps],
                    orientation="h",
                    marker_color=color,
                    text=[f"{value:.0%}" for value in percent_values(steps)],
                    textposition="outside",
                    showlegend=False,
                ),
                row=1,
                col=col_index,
            )

    if not figure.data:
        return None
    figure.update_xaxes(range=[0, 1.05], tickformat=".0%")
    figure.update_layout(title=title, barmode="group", height=500)
    return figure


def build_rate_heatmap(
    value_matrix: pd.DataFrame,
    title: str,
    x_label: str,
    y_label: str,
    zmin: float,
    zmax: float,
    colorscale: str,
    text_matrix: list[list[str]],
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
            hovertemplate="%{x}<br>%{y}<br>%{z:.1%}<extra></extra>",
        )
    )
    figure.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label, height=520)
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
        diff = (wins / total_matches) - (losses / total_matches)
        text = [
            [
                f"W={int(wins.iat[i, j])}<br>L={int(losses.iat[i, j])}<br>Total={int(match_counts.iat[i, j])}"
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        return build_rate_heatmap(diff, title, "Short Rally Share Tier", "Long Rally Share Tier", -1, 1, "RdYlGn", text)

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
    return build_rate_heatmap(win_rate, title, "Short Rally Share Tier", "Long Rally Share Tier", 0, 1, "RdYlGn", text)


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
        diff = (wins / total_sets) - (losses / total_sets)
        text = [
            [
                f"W={int(wins.iat[i, j])}<br>L={int(losses.iat[i, j])}<br>Total={int(all_sets.iat[i, j])}"
                for j in range(len(labels))
            ]
            for i in range(len(labels))
        ]
        return build_rate_heatmap(diff, title, bottom_col.replace(" Tier", ""), left_col.replace(" Tier", ""), -1, 1, "RdYlGn", text)

    share = all_sets / total_sets
    text = [
        [f"{share.iat[i, j]:.0%}<br>sets={int(all_sets.iat[i, j])}" for j in range(len(labels))]
        for i in range(len(labels))
    ]
    return build_rate_heatmap(share, title, bottom_col.replace(" Tier", ""), left_col.replace(" Tier", ""), 0, 1, "RdYlGn", text)


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
    figure.add_trace(go.Scatter(x=x_values, y=by_year["W"], mode="lines+markers", name="Wins"), secondary_y=False)
    figure.add_trace(go.Scatter(x=x_values, y=by_year["L"], mode="lines+markers", name="Losses"), secondary_y=False)
    figure.add_trace(go.Scatter(x=x_values, y=by_year["Win Rate"], mode="lines+markers", name="Win Rate"), secondary_y=True)
    figure.update_layout(title=title, height=420)
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
    figure.add_trace(go.Bar(x=x_values, y=by_year["Sets Won"], name="Sets Won"), row=1, col=1)
    figure.add_trace(go.Bar(x=x_values, y=by_year["Sets Lost"], name="Sets Lost"), row=1, col=1)
    figure.add_trace(go.Bar(x=x_values, y=by_year["Games Won"], name="Games Won"), row=2, col=1)
    figure.add_trace(go.Bar(x=x_values, y=by_year["Games Lost"], name="Games Lost"), row=2, col=1)
    figure.update_layout(title=title, barmode="group", height=520)
    return figure


st.title("Tennis Match Summary")
st.caption("Cross-platform local browser app for Windows and macOS.")

default_csv = PROJECT_ROOT / "data" / "input" / "StatsReport_TeamNames.csv"
with st.sidebar:
    st.header("Data")
    input_csv = st.text_input("Source CSV", value=str(default_csv))
    name_map = st.text_input("Name Map XLSX (optional)", value="")
    if st.button("Reload Data"):
        st.cache_data.clear()

source_path = Path(input_csv)
name_map_path = Path(name_map) if name_map.strip() else None

if not source_path.exists():
    st.error(f"Missing source CSV: {source_path}")
    st.stop()

csv_mtime = source_path.stat().st_mtime
name_map_mtime = name_map_path.stat().st_mtime if name_map_path and name_map_path.exists() else None
summary_df = load_summary_cached(str(source_path), str(name_map_path) if name_map_path else None, csv_mtime, name_map_mtime)

filter_values = available_filter_values(summary_df)
with st.sidebar:
    st.header("Filters")
    selected_player = st.selectbox("Player", filter_values["players"])
    selected_year = st.selectbox("Year", filter_values["years"])
    selected_month = st.selectbox("Month", filter_values["months"])
    selected_opp_team = st.selectbox("Opp Team", filter_values["opp_teams"])
    selected_season = st.selectbox("Season", filter_values["seasons"])
    split_charts = st.checkbox("Split Charts W/L", value=False)
    selected_metric_labels = st.multiselect(
        "Serve Trend Metrics",
        [label for label, _, _, _ in SERVE_TREND_METRICS],
        default=[label for label, _, _, _ in SERVE_TREND_METRICS],
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
    st.dataframe(pivot_df, width="stretch", hide_index=True)

with tabs[1]:
    st.subheader(f"Raw Matches: {current_scope}")
    st.dataframe(filtered_df, width="stretch", hide_index=True)

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
        st.dataframe(display_df, width="stretch", hide_index=True)
    else:
        st.info("No serve/return match stats available for the current filters.")

with tabs[3]:
    st.subheader(f"Serve Stats Trend: {current_scope}")
    selected_metrics = [
        metric for metric in SERVE_TREND_METRICS if metric[0] in selected_metric_labels
    ]
    serve_trend_fig = plot_metric_line_chart(
        filtered_df,
        selected_metrics,
        split_charts,
        f"Serve Statistics Trend by Match ({current_scope})",
    )
    if serve_trend_fig:
        st.plotly_chart(
            serve_trend_fig,
            width="stretch",
            key=chart_key("serve_trend", *base_chart_key_parts, selected_metric_labels),
        )
    else:
        st.info("No serve trend data is available for the current filters.")

with tabs[4]:
    st.subheader(f"Games Diff Control: {current_scope}")
    games_diff_fig = build_games_diff_chart(filtered_df, split_charts, f"Games Diff Control ({current_scope})")
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
    funnel_fig = build_funnel_chart(filtered_df, split_charts, f"Serve Efficiency Funnel ({current_scope})")
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
    rally_profile_fig = build_rally_profile_chart(filtered_df, split_charts, f"Rally Length Wins ({current_scope})")
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
    rally_bins_fig = build_rally_bins_chart(filtered_df, split_charts, f"Rally Bins ({current_scope})")
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
    pressure_fig = build_pressure_bins_chart(filtered_df, split_charts, f"Pressure Bins ({current_scope})")
    if pressure_fig:
        st.plotly_chart(
            pressure_fig,
            width="stretch",
            key=chart_key("pressure_bins", *base_chart_key_parts),
        )
    else:
        st.info("No pressure-bin data is available for the current filters.")

with tabs[9]:
    st.subheader("Source Row Edits")
    review_df, review_index_map, source_raw_df = load_source_review_cached(str(source_path), csv_mtime)
    edited_df = st.data_editor(
        review_df,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        column_config={
            "_review_id": st.column_config.NumberColumn("Review ID", disabled=True),
            "rows_affected": st.column_config.NumberColumn("Rows Affected", disabled=True),
            "Delete": st.column_config.CheckboxColumn("Delete"),
        },
    )
    st.caption("Edit grouped source rows directly here. Use the Delete column to remove grouped rows from the source CSV.")
    if st.button("Save Source CSV Changes", type="primary"):
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
    st.dataframe(dictionary_df, width="stretch", hide_index=True)
