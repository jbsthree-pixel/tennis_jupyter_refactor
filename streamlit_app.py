"""Cross-platform browser app for interactive tennis match analysis."""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from tennis_jupyter.analytics import (  # noqa: E402
    add_match_rate_columns,
    available_filter_values,
    build_game_level_summary,
    build_player_comparison_summary,
    build_pivot_summary,
    build_serve_return_match_stats,
    filter_matches,
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
from tennis_jupyter.notebook import build_match_watch_url, load_match_summary  # noqa: E402
from tennis_jupyter.reporting import write_excel_report  # noqa: E402
from tennis_jupyter.shared import safe_ratio  # noqa: E402


BENCHMARK_LEVEL_DISPLAY_ORDER = [
    "NC State Avg",
    "All Opponent Avg",
    "Tour Avg",
    "Top 10 Avg",
]
BENCHMARK_LABEL_MIN_GAP = 0.15
BENCHMARK_LABEL_Y_BOUNDS = (0.02, 0.98)

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

OPPONENT_BENCHMARK_SPECS = [
    {
        "workbook_metric": "1st Serve In",
        "numerator": "first_serve_return_opportunity",
        "denominator": "return_point",
    },
    {
        "workbook_metric": "1st Serve Points Won",
        "numerator": ("first_serve_return_opportunity", "first_serve_return_won"),
        "denominator": "first_serve_return_opportunity",
    },
    {
        "workbook_metric": "2nd Serve Points Won",
        "numerator": ("second_serve_return_opportunity", "second_serve_return_won"),
        "denominator": ("second_serve_return_opportunity", "opp_double_fault"),
    },
    {
        "workbook_metric": "1st Serves Unreturned",
        "numerator": ("first_serve_return_opportunity", "first_serve_return_in"),
        "denominator": "first_serve_return_opportunity",
    },
    {
        "workbook_metric": "1st Serve Return Points Won",
        "numerator": ("first_serve_in", "first_serve_won"),
        "denominator": "first_serve_in",
    },
    {
        "workbook_metric": "2nd Serve Return Points Won",
        "numerator": ("second_serve_in", "second_serve_won"),
        "denominator": "second_serve_in",
    },
    {
        "workbook_metric": "Break Points Won",
        "numerator": ("break_point_faced", "break_point_saved"),
        "denominator": "break_point_faced",
    },
    {
        "workbook_metric": "Break Points Saved",
        "numerator": ("break_point_total", "break_point_won"),
        "denominator": "break_point_total",
    },
]

SUMMARY_CACHE_SCHEMA_VERSION = 2


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

        .score-state-bullets {{
            margin: -0.25rem 0 0.85rem 3.4rem;
        }}

        .score-state-bullets ul {{
            margin: 0;
            padding-left: 1.1rem;
        }}

        .score-state-bullets li {{
            color: var(--text-strong);
            font-size: 0.95rem;
            line-height: 1.45;
            margin: 0.15rem 0;
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

            .score-state-bullets {{
                margin-left: 1rem;
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

        button[data-baseweb="tab"]:nth-of-type(12) {{
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
    schema_version: int,
) -> pd.DataFrame:
    """Cache summary rebuilds until the source files change."""
    _ = csv_mtime, name_map_mtime, schema_version
    return load_match_summary(input_csv=input_csv, name_map_xlsx=name_map_xlsx)


@st.cache_data(show_spinner=False)
def load_game_summary_cached(
    input_csv: str,
    name_map_xlsx: str | None,
    csv_mtime: float,
    name_map_mtime: float | None,
    schema_version: int,
) -> pd.DataFrame:
    """Cache game-level rebuilds until the source files change."""
    _ = csv_mtime, name_map_mtime, schema_version
    return build_game_level_summary(input_csv=input_csv, name_map_xlsx=name_map_xlsx)


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
    escape: str | None = "html",
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
        styler = styler.format(formatters, escape=escape)
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


def scope_text(
    player: str | list[str],
    opp_team: str,
    season: str,
) -> str:
    """Create a compact label for the current filter state."""
    labels = []
    if isinstance(player, list):
        if player and "All" not in player:
            player_label = ", ".join(player) if len(player) <= 3 else f"{len(player)} players"
        else:
            player_label = "All"
    else:
        player_label = player

    for value in [player_label, opp_team, season]:
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


def classify_feature_strength(coefficient: float) -> str:
    """Bucket standardized coefficients into a simple usefulness label."""
    magnitude = abs(float(coefficient))
    if magnitude >= 0.5:
        return "High"
    if magnitude >= 0.2:
        return "Medium"
    return "Low"


def format_plain_language_feature_name(feature: str) -> str:
    """Translate technical feature labels into plainer language."""
    replacements = {
        "1st Serve In %": "First-serve rate",
        "1st Serve Won %": "First-serve points won",
        "2nd Serve Won %": "Second-serve points won",
        "Ace %": "Ace rate",
        "DF %": "Double-fault rate",
        "1st Serve Not Returned %": "Unreturned first serves",
        "break_point_faced": "Break points faced",
        "break_point_saved": "Break points saved",
        "game_point_faced": "Game points faced",
        "score_margin_games": "Game lead/deficit",
        "1st Return In %": "First-serve returns in play",
        "1st Return Won %": "First-serve return points won",
        "2nd Return In %": "Second-serve returns in play",
        "2nd Return Won %": "Second-serve return points won",
        "opp_double_fault": "Opponent double faults",
        "break_point_total": "Break points earned",
        "break_point_won": "Break points converted",
        "game_point_earned": "Game points earned",
        "pressure_diff": "Break-point edge",
    }
    return replacements.get(feature, feature.replace("_", " ").title())


def build_logistic_importance_chart(coef_df: pd.DataFrame, title: str) -> go.Figure | None:
    """Render standardized logistic coefficients as an importance bar chart."""
    if coef_df.empty:
        return None

    chart_df = coef_df.sort_values("Coefficient").copy()
    colors = [
        (
            COLORBLIND_SAFE_CHART_COLORS["accent_red"]
            if bucket == "Helped"
            else COLORBLIND_SAFE_CHART_COLORS["accent_gray"]
            if bucket == "Hurt"
            else COLORBLIND_SAFE_CHART_COLORS["accent_taupe"]
        )
        for bucket in chart_df["Bucket"]
    ]
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=chart_df["Coefficient"],
            y=chart_df["Plain Feature"],
            orientation="h",
            marker_color=colors,
            text=chart_df["Bucket"],
            customdata=chart_df[["Direction", "Included Games", "Strength"]].to_numpy(),
            hovertemplate=(
                "%{y}<br>"
                "Bucket: %{text}<br>"
                "Direction: %{customdata[0]}<br>"
                "Effect size: %{x:.3f}<br>"
                "Games Used: %{customdata[1]:,.0f}<br>"
                "Signal: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    apply_accessible_figure_style(figure, title=title, height=460)
    figure.update_layout(
        xaxis_title="Left = tended to hurt, Right = tended to help",
        yaxis_title="Match factor",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    figure.add_vline(x=0, line_dash="dash", line_color=COLORBLIND_SAFE_CHART_COLORS["accent_black"])
    return figure


def summarize_model_takeaways(coef_df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return one plain-language helper and one plain-language risk."""
    if coef_df.empty:
        return None, None

    positive_df = coef_df[coef_df["Coefficient"] > 0].sort_values("Coefficient", ascending=False)
    negative_df = coef_df[coef_df["Coefficient"] < 0].sort_values("Coefficient", ascending=True)

    helper = None
    risk = None
    if not positive_df.empty:
        helper_row = positive_df.iloc[0]
        helper = (
            f"Biggest helper in this sample: {helper_row['Plain Feature']} "
            f"showed a {helper_row['Strength'].lower()} positive signal."
        )
    if not negative_df.empty:
        risk_row = negative_df.iloc[0]
        risk = (
            f"Biggest warning sign in this sample: {risk_row['Plain Feature']} "
            f"showed a {risk_row['Strength'].lower()} negative signal."
        )
    return helper, risk


def categorize_feature_signal(coefficient: float, strength: str) -> str:
    """Group each factor into helped, hurt, or didn't matter much."""
    if strength == "Low":
        return "Didn't Matter Much"
    if coefficient > 0:
        return "Helped"
    if coefficient < 0:
        return "Hurt"
    return "Didn't Matter Much"


def bucket_game_score_state(score_margin_games: pd.Series) -> pd.Series:
    """Convert game lead/deficit into a plain-language score-state bucket."""
    numeric = pd.to_numeric(score_margin_games, errors="coerce").fillna(0)
    return numeric.apply(
        lambda value: (
            "Trailing by 2+"
            if value <= -2
            else "Trailing by 1"
            if value == -1
            else "Level"
            if value == 0
            else "Leading by 1"
            if value == 1
            else "Leading by 2+"
        )
    )


def bucket_set_score_state(score_margin_sets: pd.Series) -> pd.Series:
    """Convert set lead/deficit into a plain-language set-state bucket."""
    numeric = pd.to_numeric(score_margin_sets, errors="coerce").fillna(0)
    return numeric.apply(
        lambda value: (
            "Trailing in sets"
            if value < 0
            else "Level in sets"
            if value == 0
            else "Leading in sets"
        )
    )


def build_score_state_summary(
    df: pd.DataFrame,
    *,
    state_column: str,
    target_column: str,
    success_label: str,
    state_order: list[str] | None = None,
) -> pd.DataFrame:
    """Summarize hold/break rates by one score-state dimension."""
    if df.empty or state_column not in df.columns or target_column not in df.columns:
        return pd.DataFrame()

    summary_df = df[[state_column, target_column]].copy()
    summary_df[target_column] = pd.to_numeric(summary_df[target_column], errors="coerce").fillna(0)
    grouped = (
        summary_df.groupby(state_column, dropna=False)
        .agg(
            Games=(target_column, "size"),
            Successes=(target_column, "sum"),
        )
        .reset_index()
        .rename(columns={state_column: "Score State"})
    )
    grouped[success_label] = safe_ratio(grouped["Successes"], grouped["Games"])
    total_games = float(grouped["Games"].sum())
    grouped["Share of Games"] = grouped["Games"] / total_games if total_games else 0.0

    if state_order:
        grouped["_order"] = grouped["Score State"].map({label: idx for idx, label in enumerate(state_order)}).fillna(len(state_order))
        grouped = grouped.sort_values(["_order", "Score State"]).drop(columns="_order")
    else:
        grouped = grouped.sort_values("Games", ascending=False)

    return grouped.reset_index(drop=True)


def build_score_state_ratio_summary(
    df: pd.DataFrame,
    *,
    state_column: str,
    numerator_column: str,
    denominator_column: str,
    rate_label: str,
    state_order: list[str] | None = None,
) -> pd.DataFrame:
    """Summarize weighted rate performance by one score-state dimension."""
    required_columns = {state_column, numerator_column, denominator_column}
    if df.empty or not required_columns.issubset(df.columns):
        return pd.DataFrame()

    summary_df = df[[state_column, numerator_column, denominator_column]].copy()
    summary_df[numerator_column] = pd.to_numeric(summary_df[numerator_column], errors="coerce").fillna(0)
    summary_df[denominator_column] = pd.to_numeric(summary_df[denominator_column], errors="coerce").fillna(0)
    grouped = (
        summary_df.groupby(state_column, dropna=False)
        .agg(
            Games=(state_column, "size"),
            Numerator=(numerator_column, "sum"),
            Denominator=(denominator_column, "sum"),
        )
        .reset_index()
        .rename(columns={state_column: "Score State"})
    )
    grouped[rate_label] = safe_ratio(grouped["Numerator"], grouped["Denominator"])
    total_games = float(grouped["Games"].sum())
    grouped["Share of Games"] = grouped["Games"] / total_games if total_games else 0.0

    if state_order:
        grouped["_order"] = grouped["Score State"].map({label: idx for idx, label in enumerate(state_order)}).fillna(len(state_order))
        grouped = grouped.sort_values(["_order", "Score State"]).drop(columns="_order")
    else:
        grouped = grouped.sort_values("Games", ascending=False)

    return grouped.reset_index(drop=True)


def build_score_state_bar_chart(
    summary_df: pd.DataFrame,
    *,
    title: str,
    rate_column: str,
    overall_rate: float,
) -> go.Figure | None:
    """Plot a single score-state rate chart with an overall baseline."""
    if summary_df.empty or rate_column not in summary_df.columns:
        return None

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=summary_df["Score State"],
            y=summary_df[rate_column],
            marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_red"],
            customdata=summary_df[["Games", "Successes", "Share of Games"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>"
                f"{rate_column}: "
                "%{y:.1%}<br>"
                "Games: %{customdata[0]:,.0f}<br>"
                "Successful games: %{customdata[1]:,.0f}<br>"
                "Share of sample: %{customdata[2]:.1%}<extra></extra>"
            ),
        )
    )
    apply_accessible_figure_style(figure, title=title, height=420)
    figure.update_layout(
        margin=dict(l=40, r=20, t=60, b=40),
        xaxis_title="Score state",
        yaxis_title=rate_column,
        showlegend=False,
    )
    figure.update_yaxes(tickformat=".0%", range=[0, 1])
    figure.add_hline(
        y=overall_rate,
        line_dash="dash",
        line_color=COLORBLIND_SAFE_CHART_COLORS["accent_black"],
        annotation_text=f"Overall: {overall_rate:.1%}",
        annotation_position="top left",
    )
    return figure


def describe_player_group(df: pd.DataFrame, player_column: str = "player") -> tuple[str, str]:
    """Return a coaching-friendly player reference and pronoun."""
    if df.empty or player_column not in df.columns:
        return "the player", "they"

    players = sorted(
        {
            str(player).strip()
            for player in df[player_column].dropna().tolist()
            if str(player).strip()
        }
    )
    if not players:
        return "the player", "they"
    if len(players) == 1:
        return players[0], "they"
    return "these players", "they"


def build_score_state_explainer(
    summary_df: pd.DataFrame,
    *,
    rate_column: str,
    overall_rate: float,
    subject_label: str,
    subject_pronoun: str,
    context_label: str,
    view_label: str,
) -> str | None:
    """Create a concise coaching note for the score-state chart."""
    required_columns = {"Score State", "Games", rate_column}
    if summary_df.empty or not required_columns.issubset(summary_df.columns):
        return None

    explainer_df = summary_df.copy()
    explainer_df["_delta"] = pd.to_numeric(explainer_df[rate_column], errors="coerce").fillna(0) - float(overall_rate)
    explainer_df = explainer_df.sort_values(["_delta", "Games"], ascending=[False, False]).reset_index(drop=True)

    strongest_row = explainer_df.iloc[0]
    weakest_row = explainer_df.sort_values(["_delta", "Games"], ascending=[True, False]).iloc[0]

    strongest_delta = float(strongest_row["_delta"])
    weakest_delta = float(weakest_row["_delta"])
    action_label = "Hold" if view_label == "Service Games" else "Break"
    gap = float(strongest_row[rate_column]) - float(weakest_row[rate_column])

    bullets = [
        f"- {action_label} is most likely when: {strongest_row['Score State']} ({strongest_row[rate_column]:.1%})",
        f"- {action_label} is least likely when: {weakest_row['Score State']} ({weakest_row[rate_column]:.1%})",
    ]
    if abs(gap) <= 0.002:
        bullets.append(f"- There is not much difference across score states here ({gap:.1%} separates the top and bottom rates).")
    return "\n".join(bullets)


def render_score_state_explainer(explainer_text: str) -> None:
    """Render score-state bullets with a left offset that aligns to the chart area."""
    bullets = [line[2:].strip() for line in explainer_text.splitlines() if line.strip().startswith("- ")]
    if not bullets:
        return
    bullet_html = "".join(f"<li>{bullet}</li>" for bullet in bullets)
    st.markdown(
        f'<div class="score-state-bullets"><ul>{bullet_html}</ul></div>',
        unsafe_allow_html=True,
    )


def build_score_state_ratio_bar_chart(
    summary_df: pd.DataFrame,
    *,
    title: str,
    rate_column: str,
    overall_rate: float,
    numerator_label: str,
    denominator_label: str,
) -> go.Figure | None:
    """Plot a score-state rate chart with weighted numerator/denominator details."""
    required_columns = {"Score State", "Games", "Numerator", "Denominator", "Share of Games", rate_column}
    if summary_df.empty or not required_columns.issubset(summary_df.columns):
        return None

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=summary_df["Score State"],
            y=summary_df[rate_column],
            marker_color=COLORBLIND_SAFE_CHART_COLORS["accent_red"],
            customdata=summary_df[["Games", "Numerator", "Denominator", "Share of Games"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>"
                f"{rate_column}: "
                "%{y:.1%}<br>"
                "Games: %{customdata[0]:,.0f}<br>"
                f"{numerator_label}: "
                "%{customdata[1]:,.0f}<br>"
                f"{denominator_label}: "
                "%{customdata[2]:,.0f}<br>"
                "Share of sample: %{customdata[3]:.1%}<extra></extra>"
            ),
        )
    )
    apply_accessible_figure_style(figure, title=title, height=420)
    figure.update_layout(
        margin=dict(l=40, r=20, t=60, b=40),
        xaxis_title="Score state",
        yaxis_title=rate_column,
        showlegend=False,
    )
    figure.update_yaxes(tickformat=".0%", range=[0, 1])
    figure.add_hline(
        y=overall_rate,
        line_dash="dash",
        line_color=COLORBLIND_SAFE_CHART_COLORS["accent_black"],
        annotation_text=f"Overall: {overall_rate:.1%}",
        annotation_position="top left",
    )
    return figure


def format_action_change(delta: float, unit: str) -> str:
    """Describe an intervention in plain English."""
    if unit == "pct_points":
        points = abs(delta) * 100
        direction = "rises" if delta > 0 else "drops"
        return f"{direction} by {points:.0f} percentage points"
    if unit == "count":
        amount = abs(delta)
        direction = "rises" if delta > 0 else "drops"
        return f"{direction} by {amount:.0f}"
    amount = abs(delta)
    direction = "rises" if delta > 0 else "drops"
    return f"{direction} by {amount:.2f}"


def build_real_world_effects(
    df: pd.DataFrame,
    target_column: str,
    action_specs: list[dict[str, object]],
) -> pd.DataFrame:
    """Build observed effect curves from real games only."""
    if df.empty or target_column not in df.columns:
        return pd.DataFrame()

    base_rate = float(pd.to_numeric(df[target_column], errors="coerce").fillna(0).mean())
    rows: list[dict[str, object]] = []
    for spec in action_specs:
        feature = str(spec["feature"])
        if feature not in df.columns:
            continue
        feature_values = pd.to_numeric(df[feature], errors="coerce")
        if feature_values.notna().sum() == 0:
            continue
        baseline_value = float(feature_values.mean())
        direction = -1 if float(spec.get("delta", 0.01)) < 0 else 1
        for step in range(1, 6):
            delta = direction * (step / 100.0)
            threshold = baseline_value + delta
            if spec.get("bounds"):
                lower, upper = spec["bounds"]
                threshold = min(max(threshold, lower), upper)
            if delta > 0:
                comparison_mask = feature_values >= threshold
            else:
                comparison_mask = feature_values <= threshold
            comparison_df = df.loc[comparison_mask].copy()
            if len(comparison_df) < 25:
                continue
            observed_rate = float(pd.to_numeric(comparison_df[target_column], errors="coerce").fillna(0).mean())
            rows.append(
                {
                    "Feature": str(spec["headline"]),
                    "Step": step,
                    "Direction": "Higher" if delta > 0 else "Lower",
                    "Base Rate": base_rate,
                    "Observed Rate": observed_rate,
                    "Rate Change": observed_rate - base_rate,
                    "Sample Size": int(len(comparison_df)),
                }
            )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def build_real_world_effect_plot(
    effects_df: pd.DataFrame,
    title: str,
    rate_label: str,
) -> go.Figure | None:
    """Plot observed rate change for 1-5 point changes using real games only."""
    if effects_df.empty:
        return None

    figure = go.Figure()
    palette = [
        COLORBLIND_SAFE_CHART_COLORS["accent_red"],
        COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
        COLORBLIND_SAFE_CHART_COLORS["accent_rose"],
        COLORBLIND_SAFE_CHART_COLORS["accent_taupe"],
        COLORBLIND_SAFE_CHART_COLORS["accent_black"],
    ]
    for index, feature_name in enumerate(effects_df["Feature"].drop_duplicates()):
        feature_df = effects_df[effects_df["Feature"] == feature_name].sort_values("Step")
        figure.add_trace(
            go.Scatter(
                x=feature_df["Step"],
                y=feature_df["Rate Change"],
                mode="lines+markers",
                name=feature_name,
                line=dict(color=palette[index % len(palette)], width=3),
                marker=dict(size=8),
                customdata=feature_df[["Observed Rate", "Sample Size", "Direction"]].to_numpy(),
                hovertemplate=(
                    "%{fullData.name}<br>"
                    "%{customdata[2]} by %{x} percentage point(s)<br>"
                    f"{rate_label}: "
                    "%{customdata[0]:.1%}<br>"
                    "Difference vs overall: %{y:+.1%}<br>"
                    "Real games used: %{customdata[1]:,.0f}<extra></extra>"
                ),
            )
        )

    apply_accessible_figure_style(figure, title=title, height=440)
    figure.update_layout(
        xaxis_title="Change Size (percentage points)",
        yaxis_title=f"Difference vs overall {rate_label.lower()}",
        margin=dict(l=40, r=20, t=60, b=40),
        legend_title="Factor",
    )
    figure.update_xaxes(tickmode="linear", dtick=1)
    figure.update_yaxes(tickformat="+.0%")
    figure.add_hline(y=0, line_dash="dash", line_color=COLORBLIND_SAFE_CHART_COLORS["accent_black"])
    return figure


def build_outcome_probability_plot(
    chart_df: pd.DataFrame,
    *,
    metric_column: str,
    metric_label: str,
    success_column: str,
    failure_column: str,
    outcome_label: str,
    title: str,
    bin_size_pct: int,
    min_matches_per_bin: int,
) -> go.Figure | None:
    """Plot logistic-regression outcome probability plus observed-bin context."""
    required_columns = [metric_column, success_column, failure_column]
    if chart_df.empty or any(column not in chart_df.columns for column in required_columns):
        return None

    plot_df = chart_df[required_columns].copy()
    plot_df[metric_column] = pd.to_numeric(plot_df[metric_column], errors="coerce")
    plot_df[success_column] = pd.to_numeric(plot_df[success_column], errors="coerce").fillna(0.0)
    plot_df[failure_column] = pd.to_numeric(plot_df[failure_column], errors="coerce").fillna(0.0)
    plot_df = plot_df[
        plot_df[metric_column].notna()
        & ((plot_df[success_column] + plot_df[failure_column]) > 0)
    ].copy()
    if plot_df.empty:
        return None

    plot_df["Rate"] = plot_df[metric_column]
    plot_df["Rate"] = plot_df["Rate"].clip(lower=0.0, upper=1.0)
    expanded_rates: list[float] = []
    expanded_outcomes: list[int] = []
    for _, row in plot_df.iterrows():
        rate = float(row[metric_column])
        successes = int(max(0.0, float(row[success_column])))
        failures = int(max(0.0, float(row[failure_column])))
        if successes:
            expanded_rates.extend([rate] * successes)
            expanded_outcomes.extend([1] * successes)
        if failures:
            expanded_rates.extend([rate] * failures)
            expanded_outcomes.extend([0] * failures)

    if not expanded_outcomes:
        return None

    expanded_df = pd.DataFrame({"Rate": expanded_rates, "outcome": expanded_outcomes})
    class_counts = expanded_df["outcome"].value_counts()
    if len(class_counts) < 2 or class_counts.min() < 2:
        return None

    X = expanded_df[["Rate"]].to_numpy()
    y = expanded_df["outcome"].to_numpy()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model = LogisticRegression(
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    )
    model.fit(X_scaled, y)

    x_grid = np.linspace(0.0, 1.0, 201)
    x_grid_scaled = scaler.transform(x_grid.reshape(-1, 1))
    predicted_probability = model.predict_proba(x_grid_scaled)[:, 1]

    step = max(1, int(bin_size_pct))
    bin_edges = np.arange(0, 100 + step, step, dtype=float) / 100.0
    if bin_edges[-1] < 1.0:
        bin_edges = np.append(bin_edges, 1.0)
    bin_edges[-1] = 1.000001

    plot_df["Rate Bin"] = pd.cut(
        plot_df["Rate"],
        bins=bin_edges,
        include_lowest=True,
        right=False,
    )
    plot_df = plot_df[plot_df["Rate Bin"].notna()].copy()
    if plot_df.empty:
        return None

    grouped = (
        plot_df.groupby("Rate Bin", observed=False)
        .agg(
            Matches=("Rate", "size"),
            Successes=(success_column, "sum"),
            Failures=(failure_column, "sum"),
            Mean_Rate=("Rate", "mean"),
        )
        .reset_index()
    )
    if grouped.empty:
        return None
    grouped["Trials"] = grouped["Successes"] + grouped["Failures"]
    grouped["Observed Probability"] = safe_ratio(grouped["Successes"], grouped["Trials"])
    grouped["Bin Left"] = pd.Series(
        [float(interval.left) for interval in grouped["Rate Bin"]],
        index=grouped.index,
        dtype="float64",
    )
    grouped["Bin Right"] = pd.Series(
        [min(float(interval.right), 1.0) for interval in grouped["Rate Bin"]],
        index=grouped.index,
        dtype="float64",
    )
    grouped["Bin Mid"] = (grouped["Bin Left"] + grouped["Bin Right"]) / 2.0
    grouped["Bin Label"] = grouped.apply(
        lambda row: f"{row['Bin Left']:.0%}-{row['Bin Right']:.0%}",
        axis=1,
    )
    grouped = grouped[grouped["Matches"] >= max(1, int(min_matches_per_bin))].copy()
    if grouped.empty:
        return None

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=x_grid,
            y=predicted_probability,
            mode="lines",
            name=f"Predicted {outcome_label}",
            line=dict(color=COLORBLIND_SAFE_CHART_COLORS["accent_red"], width=4),
            hovertemplate=(
                metric_label
                + ": %{x:.1%}<br>"
                + "Predicted "
                + outcome_label.lower()
                + ": %{y:.1%}<extra></extra>"
            ),
        ),
    )

    apply_accessible_figure_style(figure, title=title, height=420)
    figure.update_layout(
        hovermode="closest",
        legend_title="Series",
        margin=dict(l=40, r=40, t=60, b=40),
    )
    figure.update_xaxes(
        title_text=metric_label,
        tickformat=".0%",
        range=[0, 1],
    )
    figure.update_yaxes(
        title_text=outcome_label,
        tickformat=".0%",
        range=[0, 1],
    )
    return figure


def chronological_train_test_split(
    model_df: pd.DataFrame,
    *,
    train_fraction: float = 0.70,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp | None]:
    """Split a model dataframe by whole dates using the oldest ~train_fraction for training."""
    if model_df.empty or "Match Date" not in model_df.columns:
        return pd.DataFrame(), pd.DataFrame(), None

    dated_df = model_df.copy()
    dated_df["Match Date"] = pd.to_datetime(dated_df["Match Date"], errors="coerce")
    dated_df = dated_df[dated_df["Match Date"].notna()].sort_values(
        ["Match Date", "matchId", "gameId"],
        na_position="last",
    )
    if dated_df.empty:
        return pd.DataFrame(), pd.DataFrame(), None

    by_date = (
        dated_df.groupby("Match Date", dropna=False)
        .size()
        .reset_index(name="games")
        .sort_values("Match Date")
        .reset_index(drop=True)
    )
    by_date["cum_games"] = by_date["games"].cumsum()
    target_games = max(1, int(len(dated_df) * train_fraction))
    cutoff_row = by_date[by_date["cum_games"] >= target_games].iloc[0]
    cutoff_date = pd.Timestamp(cutoff_row["Match Date"])

    train_df = dated_df[dated_df["Match Date"] < cutoff_date].copy()
    test_df = dated_df[dated_df["Match Date"] >= cutoff_date].copy()

    if train_df.empty or test_df.empty:
        split_index = max(1, min(len(dated_df) - 1, target_games))
        train_df = dated_df.iloc[:split_index].copy()
        test_df = dated_df.iloc[split_index:].copy()
        cutoff_date = (
            pd.Timestamp(test_df["Match Date"].min())
            if not test_df.empty and "Match Date" in test_df.columns
            else None
        )

    return train_df.reset_index(drop=True), test_df.reset_index(drop=True), cutoff_date


def fit_regularized_logistic_model(
    df: pd.DataFrame,
    target_column: str,
    feature_columns: list[str],
) -> dict[str, object] | None:
    """Fit a regularized binary logistic model and return metrics plus coefficients."""
    if df.empty:
        return None

    needed_columns = [target_column, *feature_columns]
    metadata_columns = [
        column
        for column in ["Match Date", "matchId", "gameId"]
        if column in df.columns
    ]
    model_df = df[needed_columns + metadata_columns].copy()
    for column in feature_columns:
        model_df[column] = pd.to_numeric(model_df[column], errors="coerce").fillna(0.0)
    model_df[target_column] = pd.to_numeric(model_df[target_column], errors="coerce").fillna(0).astype("int64")

    usable_features = [
        column
        for column in feature_columns
        if model_df[column].nunique(dropna=False) > 1
    ]
    if not usable_features:
        return None

    X = model_df[usable_features]
    y = model_df[target_column]
    class_counts = y.value_counts()
    if len(class_counts) < 2 or class_counts.min() < 2:
        return None

    train_df, test_df, cutoff_date = chronological_train_test_split(model_df)
    if train_df.empty or test_df.empty:
        return None

    X_train = train_df[usable_features]
    y_train = train_df[target_column]
    X_test = test_df[usable_features]
    y_test = test_df[target_column]
    train_class_counts = y_train.value_counts()
    test_class_counts = y_test.value_counts()
    if (
        len(train_class_counts) < 2
        or len(test_class_counts) < 2
        or train_class_counts.min() < 2
        or test_class_counts.min() < 2
    ):
        return None

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(
        l1_ratio=1.0,
        C=0.7,
        solver="saga",
        max_iter=1000,
        random_state=42,
    )
    model.fit(X_train_scaled, y_train)

    probabilities = model.predict_proba(X_test_scaled)[:, 1]
    predictions = (probabilities >= 0.5).astype("int64")

    coef_df = pd.DataFrame(
        {
            "Feature": usable_features,
            "Coefficient": model.coef_[0],
        }
    )
    coef_df["Abs Coefficient"] = coef_df["Coefficient"].abs()
    coef_df["Strength"] = coef_df["Coefficient"].apply(classify_feature_strength)
    coef_df["Plain Feature"] = coef_df["Feature"].apply(format_plain_language_feature_name)
    coef_df["Direction"] = coef_df["Coefficient"].apply(
        lambda value: "Helped more often" if value > 0 else "Hurt more often" if value < 0 else "Little signal"
    )
    coef_df["Bucket"] = coef_df.apply(
        lambda row: categorize_feature_signal(float(row["Coefficient"]), str(row["Strength"])),
        axis=1,
    )
    coef_df["Included Games"] = len(model_df)
    coef_df = coef_df.sort_values("Abs Coefficient", ascending=False).reset_index(drop=True)

    auc = roc_auc_score(y_test, probabilities) if y_test.nunique() > 1 else float("nan")
    accuracy = accuracy_score(y_test, predictions)

    return {
        "model": model,
        "scaler": scaler,
        "coef_df": coef_df,
        "features": usable_features,
        "feature_means": X.mean().to_dict(),
        "accuracy": accuracy,
        "roc_auc": auc,
        "positive_rate": float(y.mean()),
        "rows_used": int(len(model_df)),
        "train_rows": int(len(train_df)),
        "holdout_rows": int(len(test_df)),
        "train_end_date": (
            pd.to_datetime(train_df["Match Date"], errors="coerce").max().date()
            if "Match Date" in train_df.columns and not train_df.empty
            else None
        ),
        "test_start_date": (
            pd.to_datetime(test_df["Match Date"], errors="coerce").min().date()
            if "Match Date" in test_df.columns and not test_df.empty
            else None
        ),
        "cutoff_date": cutoff_date.date() if cutoff_date is not None else None,
        "evaluation_scope": "Chronological Holdout",
    }


def render_player_chart_grid(
    chart_df: pd.DataFrame,
    selected_players: list[str],
    key_prefix: str,
    build_chart,
    title_builder,
    chart_key_parts: tuple[object, ...],
    after_build=None,
) -> bool:
    """Render one chart per selected player in a two-column comparison grid."""
    rendered = False
    player_list = [player for player in selected_players if player]
    if not player_list:
        return rendered

    for row_start in range(0, len(player_list), 2):
        row_players = player_list[row_start : row_start + 2]
        columns = st.columns(len(row_players))
        for col_index, player_name in enumerate(row_players):
            player_df = chart_df[chart_df["player"] == player_name].copy()
            with columns[col_index]:
                figure = build_chart(player_df, title_builder(player_name))
                if not figure:
                    st.info(f"No data available for {player_name} in the current filters.")
                    continue
                if after_build:
                    after_build(figure, player_df, player_name)
                st.plotly_chart(
                    figure,
                    width="stretch",
                    key=chart_key(key_prefix, *chart_key_parts, player_name),
                )
                rendered = True
    return rendered


def benchmark_lookup(benchmark_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Index workbook metrics by label for quick baseline lookup."""
    lookup: dict[str, dict[str, float]] = {}
    if benchmark_df.empty:
        return lookup

    level_columns = [column for column in benchmark_df.columns if str(column) != "Metric"]
    for _, row in benchmark_df.iterrows():
        metric_name = str(row.get("Metric", "")).strip()
        if not metric_name:
            continue
        metric_lookup: dict[str, float] = {}
        for column in level_columns:
            value = row.get(column)
            if pd.isna(value):
                continue
            try:
                metric_lookup[str(column)] = float(value)
            except (TypeError, ValueError):
                continue
        lookup[metric_name] = metric_lookup
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


def _summed_series_value(
    totals: pd.DataFrame,
    column_or_difference: str | tuple[str, str],
) -> float:
    """Sum a numeric column or the positive difference between two columns."""
    if isinstance(column_or_difference, tuple):
        left, right = column_or_difference
        if left not in totals.columns or right not in totals.columns:
            return 0.0
        left_values = pd.to_numeric(totals[left], errors="coerce").fillna(0)
        right_values = pd.to_numeric(totals[right], errors="coerce").fillna(0)
        return float((left_values - right_values).sum())

    if column_or_difference not in totals.columns:
        return 0.0
    return float(pd.to_numeric(totals[column_or_difference], errors="coerce").fillna(0).sum())


def aggregate_opponent_benchmark_metrics(chart_df: pd.DataFrame) -> dict[str, float]:
    """Aggregate the opponent side of the filtered match data into workbook-comparable rates."""
    values: dict[str, float] = {}
    if chart_df.empty:
        return values

    totals = chart_df.copy()
    for spec in OPPONENT_BENCHMARK_SPECS:
        numerator = _summed_series_value(totals, spec["numerator"])
        denominator = _summed_series_value(totals, spec["denominator"])
        values[spec["workbook_metric"]] = float(numerator / denominator) if denominator else 0.0

    return values


def with_derived_benchmark_column(
    benchmark_df: pd.DataFrame,
    column_name: str,
    metric_values: dict[str, float],
) -> pd.DataFrame:
    """Append a derived baseline column aligned to workbook metrics."""
    if not metric_values:
        return benchmark_df.copy()

    if benchmark_df.empty:
        return pd.DataFrame(
            {
                "Metric": list(metric_values.keys()),
                column_name: list(metric_values.values()),
            }
        )

    benchmark_with_column = benchmark_df.copy()
    if "Metric" not in benchmark_with_column.columns:
        return benchmark_with_column

    benchmark_with_column["Metric"] = benchmark_with_column["Metric"].fillna("").astype(str).str.strip()
    benchmark_with_column[column_name] = benchmark_with_column["Metric"].map(metric_values)
    missing_metrics = [
        metric_name
        for metric_name in metric_values
        if metric_name not in set(benchmark_with_column["Metric"].tolist())
    ]
    if missing_metrics:
        benchmark_with_column = pd.concat(
            [
                benchmark_with_column,
                pd.DataFrame(
                    {
                        "Metric": missing_metrics,
                        column_name: [metric_values[metric_name] for metric_name in missing_metrics],
                    }
                ),
            ],
            ignore_index=True,
            sort=False,
    )
    return benchmark_with_column


def with_nc_state_benchmark(
    benchmark_df: pd.DataFrame,
    team_df: pd.DataFrame,
) -> pd.DataFrame:
    """Append a derived NC State baseline column using the full local summary dataset."""
    return with_derived_benchmark_column(
        benchmark_df,
        "NC State Avg",
        aggregate_benchmark_metrics(team_df),
    )


def with_all_opponent_benchmark(
    benchmark_df: pd.DataFrame,
    team_df: pd.DataFrame,
) -> pd.DataFrame:
    """Append a derived aggregate benchmark column for opponent-side performance."""
    return with_derived_benchmark_column(
        benchmark_df,
        "All Opponent Avg",
        aggregate_opponent_benchmark_metrics(team_df),
    )


def available_benchmark_levels(benchmark_df: pd.DataFrame) -> list[str]:
    """Return benchmark level labels in a stable display order."""
    if benchmark_df.empty:
        return []

    levels = [str(column) for column in benchmark_df.columns if str(column) != "Metric"]
    ordered = [level for level in BENCHMARK_LEVEL_DISPLAY_ORDER if level in levels]
    dynamic_levels = sorted(level for level in levels if level not in ordered)
    return ordered + dynamic_levels


def benchmark_line_style(level: str, level_index: int) -> dict[str, str]:
    """Provide a readable line style for both workbook and derived benchmark levels."""
    fixed_styles = {
        "NC State Avg": {"dash": "solid", "color": COLORBLIND_SAFE_CHART_COLORS["accent_red"]},
        "All Opponent Avg": {"dash": "longdash", "color": COLORBLIND_SAFE_CHART_COLORS["accent_gray"]},
        "Tour Avg": {"dash": "dot", "color": COLORBLIND_SAFE_CHART_COLORS["accent_black"]},
        "Top 10 Avg": {"dash": "dash", "color": COLORBLIND_SAFE_CHART_COLORS["accent_taupe"]},
    }
    if level in fixed_styles:
        return fixed_styles[level]

    color_cycle = [
        COLORBLIND_SAFE_CHART_COLORS["accent_red_dark"],
        COLORBLIND_SAFE_CHART_COLORS["accent_rose"],
        COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
        COLORBLIND_SAFE_CHART_COLORS["accent_black"],
        COLORBLIND_SAFE_CHART_COLORS["accent_taupe"],
    ]
    dash_cycle = ["longdash", "dashdot", "longdashdot", "dot"]
    return {
        "dash": dash_cycle[level_index % len(dash_cycle)],
        "color": color_cycle[level_index % len(color_cycle)],
    }


def season_scoped_team_df(
    summary_df: pd.DataFrame,
    season_label: str,
) -> pd.DataFrame:
    """Return the all-player dataset used to derive the NC State benchmark for a season scope."""
    if summary_df.empty:
        return summary_df.copy()

    if not season_label or season_label == "All":
        return summary_df.copy()

    season_df = with_season_columns(summary_df)
    return season_df[season_df["_Season Label"] == season_label].reset_index(drop=True)


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

    labels: list[dict[str, object]] = []
    for metric_label, _, _, _ in selected_metrics:
        workbook_metric = metric_to_workbook.get(metric_label)
        if not workbook_metric or workbook_metric not in lookup:
            continue
        for level_index, level in enumerate(selected_levels):
            baseline_value = lookup[workbook_metric].get(level)
            if baseline_value is None:
                continue
            line_style = benchmark_line_style(level, level_index)
            figure.add_hline(
                y=baseline_value,
                line_dash=line_style["dash"],
                line_color=line_style["color"],
                opacity=0.9,
            )
            labels.append(
                {
                    "metric_label": metric_label,
                    "level": level,
                    "baseline_value": baseline_value,
                    "line_style": line_style,
                }
            )

    if not labels:
        return

    label_positions = spread_benchmark_label_positions(
        [float(label["baseline_value"]) for label in labels],
        min_gap=BENCHMARK_LABEL_MIN_GAP,
        lower=BENCHMARK_LABEL_Y_BOUNDS[0],
        upper=BENCHMARK_LABEL_Y_BOUNDS[1],
    )
    for label, label_y in zip(labels, label_positions):
        baseline_value = float(label["baseline_value"])
        line_style = label["line_style"]
        if not isinstance(line_style, dict):
            continue
        line_color = str(line_style["color"])
        if abs(label_y - baseline_value) > 0.001:
            figure.add_shape(
                type="line",
                xref="paper",
                yref="y",
                x0=1.0,
                y0=baseline_value,
                x1=1.008,
                y1=label_y,
                line={"color": line_color, "width": 1},
            )
        figure.add_annotation(
            xref="paper",
            yref="y",
            x=1.01,
            y=label_y,
            text=f"{label['metric_label']} {label['level']}: {baseline_value:.1%}",
            showarrow=False,
            xanchor="left",
            yanchor="middle",
            align="left",
            font={"color": line_color, "size": 12},
            bgcolor="rgba(255, 253, 248, 0.92)",
        )


def spread_benchmark_label_positions(
    values: list[float],
    *,
    min_gap: float,
    lower: float,
    upper: float,
) -> list[float]:
    """Return y positions that preserve order while giving benchmark labels room."""
    if not values:
        return []

    indexed_values = sorted(enumerate(values), key=lambda item: item[1])
    positioned: list[tuple[int, float]] = []
    previous_y: float | None = None
    for original_index, value in indexed_values:
        y = min(max(value, lower), upper)
        if previous_y is not None and y - previous_y < min_gap:
            y = previous_y + min_gap
        positioned.append((original_index, y))
        previous_y = y

    overflow = positioned[-1][1] - upper
    if overflow > 0:
        positioned = [(index, y - overflow) for index, y in positioned]
        for reverse_index in range(len(positioned) - 2, -1, -1):
            next_y = positioned[reverse_index + 1][1]
            current_index, current_y = positioned[reverse_index]
            if next_y - current_y < min_gap:
                positioned[reverse_index] = (current_index, next_y - min_gap)

    underflow = lower - positioned[0][1]
    if underflow > 0:
        positioned = [(index, y + underflow) for index, y in positioned]

    by_original_index = {index: y for index, y in positioned}
    return [by_original_index[index] for index in range(len(values))]


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
    figure.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "title": {"text": "Metric"},
        },
        margin={"t": 120, "r": 240},
    )
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

    def apply_funnel_legend_layout(figure: go.Figure) -> None:
        for annotation in figure.layout.annotations:
            if getattr(annotation, "y", None) is not None and annotation.y > 0.9:
                annotation.y = 1.08
        figure.update_layout(
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.01,
                "xanchor": "center",
                "x": 0.5,
                "title": {"text": ""},
            },
            margin={"t": 150},
        )

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
    apply_funnel_legend_layout(figure)
    return figure


def build_funnel_comparison_chart(
    chart_df: pd.DataFrame,
    selected_players: list[str],
    split_by_result: bool,
    title: str,
) -> go.Figure | None:
    """Render overlaid serve funnels so selected players can be compared directly."""
    required = [
        "player",
        "first_serve_attempt",
        "first_serve_in",
        "first_serve_won",
        "second_serve_attempt",
        "second_serve_in",
        "second_serve_won",
    ]
    if chart_df.empty or any(column not in chart_df.columns for column in required):
        return None

    plot_df = chart_df[chart_df["player"].isin(selected_players)].copy()
    if plot_df.empty:
        return None

    player_palette = [
        COLORBLIND_SAFE_CHART_COLORS["accent_red"],
        COLORBLIND_SAFE_CHART_COLORS["accent_gray"],
        COLORBLIND_SAFE_CHART_COLORS["accent_rose"],
        COLORBLIND_SAFE_CHART_COLORS["accent_taupe"],
        COLORBLIND_SAFE_CHART_COLORS["accent_black"],
    ]
    player_colors = {
        player_name: player_palette[index % len(player_palette)]
        for index, player_name in enumerate(selected_players)
    }

    def funnel_steps(frame: pd.DataFrame):
        totals = frame[required[1:]].sum(numeric_only=True)
        return {
            "First Serve Funnel": [
                ("1st Attempts", float(totals.get("first_serve_attempt", 0))),
                ("1st In", float(totals.get("first_serve_in", 0))),
                ("1st Won", float(totals.get("first_serve_won", 0))),
            ],
            "Second Serve Funnel": [
                ("2nd Attempts", float(totals.get("second_serve_attempt", 0))),
                ("2nd In", float(totals.get("second_serve_in", 0))),
                ("2nd Won", float(totals.get("second_serve_won", 0))),
            ],
        }

    def add_player_trace(figure: go.Figure, steps, player_name: str, row: int, col: int, showlegend: bool) -> None:
        base = steps[0][1] if steps and steps[0][1] else 0.0
        percentages = [value / base if base else 0.0 for _, value in steps]
        previous = None
        step_rates = []
        for _, value in steps:
            step_rates.append((value / previous) if previous not in (None, 0.0) else 1.0)
            previous = value
        figure.add_trace(
            go.Bar(
                x=percentages,
                y=[label for label, _ in steps],
                orientation="h",
                name=player_name,
                marker_color=player_colors.get(player_name, COLORBLIND_SAFE_CHART_COLORS["accent_red"]),
                text=[f"{pct:.0%}" for pct in percentages],
                textposition="outside",
                customdata=[
                    [raw, pct, step]
                    for (_, raw), pct, step in zip(steps, percentages, step_rates)
                ],
                hovertemplate=(
                    "%{y}<br>"
                    f"Player={player_name}<br>"
                    "Share of attempts=%{customdata[1]:.0%}<br>"
                    "Raw count=%{customdata[0]:,.0f}<br>"
                    "Step conversion=%{customdata[2]:.0%}<extra></extra>"
                ),
                showlegend=showlegend,
            ),
            row=row,
            col=col,
        )

    def apply_funnel_legend_layout(figure: go.Figure) -> None:
        for annotation in figure.layout.annotations:
            if getattr(annotation, "y", None) is not None and annotation.y > 0.9:
                annotation.y = 1.08
        figure.update_layout(
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.01,
                "xanchor": "center",
                "x": 0.5,
                "title": {"text": ""},
            },
            margin={"t": 150},
        )

    if split_by_result and "Match Result" in plot_df.columns:
        result_labels = [
            label
            for label in ["W", "L"]
            if not plot_df[plot_df["Match Result"] == label].empty
        ]
        if result_labels:
            figure = make_subplots(
                rows=len(result_labels),
                cols=2,
                subplot_titles=tuple(
                    f"{result_label}: {panel_title}"
                    for result_label in result_labels
                    for panel_title in ["First Serve Funnel", "Second Serve Funnel"]
                ),
                vertical_spacing=0.18,
                horizontal_spacing=0.12,
            )
            for row_index, result_label in enumerate(result_labels, start=1):
                result_df = plot_df[plot_df["Match Result"] == result_label].copy()
                for player_name in selected_players:
                    player_df = result_df[result_df["player"] == player_name].copy()
                    if player_df.empty:
                        continue
                    player_steps = funnel_steps(player_df)
                    add_player_trace(
                        figure,
                        player_steps["First Serve Funnel"],
                        player_name,
                        row_index,
                        1,
                        showlegend=(row_index == 1),
                    )
                    add_player_trace(
                        figure,
                        player_steps["Second Serve Funnel"],
                        player_name,
                        row_index,
                        2,
                        showlegend=False,
                    )
            if not figure.data:
                return None
            for row_index in range(1, len(result_labels) + 1):
                figure.update_xaxes(range=[0, 1.05], tickformat=".0%", title_text="% of Attempts", row=row_index, col=1)
                figure.update_xaxes(range=[0, 1.05], tickformat=".0%", title_text="% of Attempts", row=row_index, col=2)
                figure.update_yaxes(
                    categoryorder="array",
                    categoryarray=["1st Won", "1st In", "1st Attempts"],
                    row=row_index,
                    col=1,
                )
                figure.update_yaxes(
                    categoryorder="array",
                    categoryarray=["2nd Won", "2nd In", "2nd Attempts"],
                    row=row_index,
                    col=2,
                )
            apply_accessible_figure_style(figure, title=title, height=420 * len(result_labels))
            figure.update_layout(barmode="group", legend_title="Player")
            apply_funnel_legend_layout(figure)
            return figure

    figure = make_subplots(rows=1, cols=2, subplot_titles=("First Serve Funnel", "Second Serve Funnel"))
    for player_name in selected_players:
        player_df = plot_df[plot_df["player"] == player_name].copy()
        if player_df.empty:
            continue
        player_steps = funnel_steps(player_df)
        add_player_trace(figure, player_steps["First Serve Funnel"], player_name, 1, 1, showlegend=True)
        add_player_trace(figure, player_steps["Second Serve Funnel"], player_name, 1, 2, showlegend=False)

    if not figure.data:
        return None
    figure.update_xaxes(range=[0, 1.05], tickformat=".0%", title_text="% of Attempts")
    figure.update_yaxes(categoryorder="array", categoryarray=["1st Won", "1st In", "1st Attempts"], row=1, col=1)
    figure.update_yaxes(categoryorder="array", categoryarray=["2nd Won", "2nd In", "2nd Attempts"], row=1, col=2)
    apply_accessible_figure_style(figure, title=title, height=500)
    figure.update_layout(barmode="group", legend_title="Player")
    apply_funnel_legend_layout(figure)
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
            marker={"symbol": "triangle-up", "size": 11},
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
            marker={"symbol": "x", "size": 11},
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
            marker={"symbol": "star", "size": 12},
        ),
        secondary_y=True,
    )
    apply_accessible_figure_style(figure, title=title, height=420)
    figure.update_layout(
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "center",
            "x": 0.5,
        }
    )
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


def build_player_comparison_chart(comparison_df: pd.DataFrame, title: str) -> go.Figure | None:
    """Render a grouped comparison chart across selected player metrics."""
    if comparison_df.empty or "Player" not in comparison_df.columns:
        return None

    metric_columns = [
        "Win Rate",
        "1st Serve In %",
        "1st Serve Won %",
        "2nd Serve Won %",
        "1st Return Won %",
        "2nd Return Won %",
        "BP Won %",
        "BP Saved %",
    ]
    available_metric_columns = [
        column for column in metric_columns if column in comparison_df.columns
    ]
    if not available_metric_columns:
        return None

    plot_df = comparison_df[["Player"] + available_metric_columns].melt(
        id_vars="Player",
        var_name="Metric",
        value_name="Rate",
    )
    metric_order = {metric: index for index, metric in enumerate(available_metric_columns)}
    plot_df["_metric_sort"] = plot_df["Metric"].map(metric_order)
    plot_df = plot_df.sort_values(["_metric_sort", "Player"]).drop(columns="_metric_sort")

    figure = go.Figure()
    for player_name in comparison_df["Player"].tolist():
        player_df = plot_df[plot_df["Player"] == player_name]
        figure.add_trace(
            go.Bar(
                x=player_df["Metric"],
                y=player_df["Rate"],
                name=player_name,
                text=[f"{value:.1%}" for value in player_df["Rate"]],
                textposition="outside",
            )
        )
    apply_accessible_figure_style(figure, title=title, height=480)
    figure.update_layout(
        barmode="group",
        legend_title="Player",
        xaxis_title="Metric",
        yaxis_title="Rate",
    )
    figure.update_yaxes(tickformat=".0%", range=[0, 1])
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

default_csv = PROJECT_ROOT / "data" / "input" / "team_singles_stats.csv.gz"
legacy_default_csv = PROJECT_ROOT / "data" / "input" / "team_singles_stats.csv"
default_benchmark_xlsx = PROJECT_ROOT / "data" / "input" / "Tour Data 2025.xlsx"
source_path = default_csv
if not source_path.exists() and legacy_default_csv.exists():
    source_path = legacy_default_csv
name_map_path = None
benchmark_path = default_benchmark_xlsx if default_benchmark_xlsx.exists() else None

if not source_path.exists():
    st.error(f"Missing source CSV: {default_csv} or {legacy_default_csv}")
    st.stop()

csv_mtime = source_path.stat().st_mtime
name_map_mtime = name_map_path.stat().st_mtime if name_map_path and name_map_path.exists() else None
summary_df = load_summary_cached(
    str(source_path),
    str(name_map_path) if name_map_path else None,
    csv_mtime,
    name_map_mtime,
    SUMMARY_CACHE_SCHEMA_VERSION,
)
game_df = load_game_summary_cached(
    str(source_path),
    str(name_map_path) if name_map_path else None,
    csv_mtime,
    name_map_mtime,
    SUMMARY_CACHE_SCHEMA_VERSION,
)
benchmark_df = pd.DataFrame()
if benchmark_path and benchmark_path.exists():
    benchmark_mtime = benchmark_path.stat().st_mtime
    benchmark_df = load_benchmark_workbook(str(benchmark_path), benchmark_mtime)
elif benchmark_path:
    st.warning(f"Tour benchmark workbook not found: {benchmark_path}")

filter_values = available_filter_values(summary_df)
with st.sidebar:
    st.header("Filters")
    all_player_options = filter_values["players"][1:]
    selected_players = st.multiselect(
        "Players",
        all_player_options,
        default=[],
        help="Leave empty to include all players, or pick any subset to compare.",
    )
    selected_opp_team = st.selectbox("Opp Team", filter_values["opp_teams"])
    selected_season = st.selectbox("Season", filter_values["seasons"])
    split_charts = st.checkbox("Split Charts W/L", value=False)
    season_benchmark_df = season_scoped_team_df(summary_df, selected_season)
    benchmark_df = with_nc_state_benchmark(
        benchmark_df,
        season_benchmark_df,
    )
    benchmark_df = with_all_opponent_benchmark(
        benchmark_df,
        season_benchmark_df,
    )
    st.header("Baselines")
    available_baseline_levels = available_benchmark_levels(benchmark_df)
    selected_baseline_levels = st.multiselect(
        "Benchmark Lines",
        available_baseline_levels,
        default=["NC State Avg"] if "NC State Avg" in available_baseline_levels else [],
        help="Overlay benchmark reference levels, including derived NC State and all-opponent averages, on supported charts.",
    )

filtered_df = filter_matches(
    summary_df,
    player=selected_players,
    opp_team=selected_opp_team,
    season_label=selected_season,
)
filtered_game_df = filter_matches(
    game_df,
    player=selected_players,
    opp_team=selected_opp_team,
    season_label=selected_season,
)
current_scope = scope_text(
    selected_players,
    selected_opp_team,
    selected_season,
)
base_chart_key_parts = (
    tuple(selected_players),
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
        "Serve Efficiency Funnel",
        "Serve Win Probability",
        "Rally Length Wins",
        "Rally Bins",
        "Pressure Bins",
        "Score-State Performance",
        "Serve / Return Score-State Rates",
    ]
)

with tabs[0]:
    st.subheader(f"Overview: {current_scope}")
    comparison_df = build_player_comparison_summary(filtered_df, player_order=selected_players)
    unique_players = comparison_df["Player"].nunique() if "Player" in comparison_df.columns else 0
    if len(selected_players) > 1 and unique_players > 1:
        st.markdown("**Player Comparison**")
        comparison_formatters = {
            column: "{:.1%}"
            for column in comparison_df.columns
            if "%" in column or column == "Win Rate"
        }
        st.dataframe(
            style_banded_rows(comparison_df, formatters=comparison_formatters),
            width="stretch",
        )
        comparison_fig = build_player_comparison_chart(
            comparison_df,
            f"Selected Player Comparison ({current_scope})",
        )
        if comparison_fig:
            st.plotly_chart(
                comparison_fig,
                width="stretch",
                key=chart_key("player_comparison", *base_chart_key_parts),
            )

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
        if "Match ID" in display_df.columns:
            display_df = display_df.copy()
            display_df["Match ID"] = display_df["Match ID"].map(build_match_watch_url)
        st.dataframe(
            style_banded_rows(display_df, formatters=percent_formatters),
            column_config={
                "Match ID": st.column_config.LinkColumn(
                    "Match ID",
                    display_text=r".*/watch/(.*)$",
                )
            }
            if "Match ID" in display_df.columns
            else None,
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
            st.caption("Filtered aggregate compared with selected benchmark baselines.")
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
    if len(selected_players) > 1 and selected_metrics:
        season_chart_df = with_season_columns(filtered_df)
        if selected_season == "All":
            available_seasons = (
                season_chart_df[["_Season Sort", "_Season Label"]]
                .drop_duplicates()
                .sort_values(["_Season Sort", "_Season Label"], na_position="last")
            )
            rendered_chart = False
            for _, season_row in available_seasons.iterrows():
                season_label = str(season_row["_Season Label"])
                season_subset = season_chart_df[season_chart_df["_Season Label"] == season_label].copy()
                st.markdown(f"**{season_label}**")
                rendered_chart = render_player_chart_grid(
                    season_subset,
                    selected_players,
                    "serve_trend_compare",
                    lambda frame, title: plot_metric_line_chart(frame, selected_metrics, split_charts, title),
                    lambda player_name: f"{player_name} Serve Trend ({season_label})",
                    (*base_chart_key_parts, season_label, tuple(selected_metric_labels)),
                    after_build=(
                        None
                        if split_charts
                        else lambda figure, frame, _player_name: add_benchmark_lines(
                            figure,
                            selected_metrics,
                            benchmark_df,
                            selected_baseline_levels,
                        )
                    ),
                ) or rendered_chart
            if not rendered_chart:
                st.info("No serve trend comparison data is available for the current filters.")
        else:
            rendered_chart = render_player_chart_grid(
                filtered_df,
                selected_players,
                "serve_trend_compare",
                lambda frame, title: plot_metric_line_chart(frame, selected_metrics, split_charts, title),
                lambda player_name: f"{player_name} Serve Trend ({current_scope})",
                (*base_chart_key_parts, tuple(selected_metric_labels)),
                after_build=(
                    None
                    if split_charts
                    else lambda figure, frame, _player_name: add_benchmark_lines(
                        figure,
                        selected_metrics,
                        benchmark_df,
                        selected_baseline_levels,
                    )
                ),
            )
            if not rendered_chart:
                st.info("No serve trend comparison data is available for the current filters.")
    elif selected_season == "All":
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
    st.subheader(f"Serve Efficiency Funnel: {current_scope}")
    funnel_title = (
        f"Serve Efficiency Funnel Split by Result ({current_scope})"
        if split_charts
        else f"Serve Efficiency Funnel ({current_scope})"
    )
    if len(selected_players) > 1:
        funnel_compare_fig = build_funnel_comparison_chart(
            filtered_df,
            selected_players,
            split_charts,
            f"Serve Efficiency Funnel Comparison ({current_scope})",
        )
        if funnel_compare_fig:
            st.plotly_chart(
                funnel_compare_fig,
                width="stretch",
                key=chart_key("serve_funnel_compare", *base_chart_key_parts),
            )
        else:
            st.info("No serve funnel comparison data is available for the current filters.")
    else:
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
    if len(selected_players) > 1:
        rendered_chart = render_player_chart_grid(
            filtered_df,
            selected_players,
            "rally_profile_compare",
            lambda frame, title: build_rally_profile_chart(frame, split_charts, title),
            lambda player_name: f"{player_name} Rally Profile vs Match Wins",
            base_chart_key_parts,
        )
        if not rendered_chart:
            st.info("No rally profile comparison data is available for the current filters.")
    else:
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
    if len(selected_players) > 1:
        rendered_chart = render_player_chart_grid(
            filtered_df,
            selected_players,
            "rally_bins_compare",
            lambda frame, title: build_rally_bins_chart(frame, split_charts, title),
            lambda player_name: f"{player_name} Rally Length Bins",
            base_chart_key_parts,
        )
        if not rendered_chart:
            st.info("No rally-bin comparison data is available for the current filters.")
    else:
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
    if len(selected_players) > 1:
        rendered_chart = render_player_chart_grid(
            filtered_df,
            selected_players,
            "pressure_bins_compare",
            lambda frame, title: build_pressure_bins_chart(frame, split_charts, title),
            lambda player_name: f"{player_name} Pressure Performance Bins",
            base_chart_key_parts,
        )
        if rendered_chart and selected_baseline_levels and not benchmark_df.empty:
            pressure_comparison_df = build_player_comparison_summary(filtered_df, player_order=selected_players)
            if not pressure_comparison_df.empty:
                pressure_comparison_df = pressure_comparison_df[["Player", "BP Won %", "BP Saved %"]]
                pressure_formatters = {
                    column: "{:.1%}"
                    for column in pressure_comparison_df.columns
                    if column != "Player"
                }
                st.caption("Break-point comparison summary for the selected players.")
                st.dataframe(
                    style_banded_rows(pressure_comparison_df, formatters=pressure_formatters),
                    width="stretch",
                )
        elif not rendered_chart:
            st.info("No pressure-bin comparison data is available for the current filters.")
    else:
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
    st.subheader(f"Score-State Performance: {current_scope}")
    score_state_views = {
        "Service Games": {
            "subset_column": "is_service_game",
            "target_column": "held_serve",
            "rate_label": "Hold Rate",
            "success_label": "Holds",
            "pressure_column": "game_point_faced",
            "pressure_hit_label": "Faced game point",
            "pressure_miss_label": "No game point faced",
            "caption": "How service-game outcomes changed based on the scoreboard and whether the game got tight.",
        },
        "Return Games": {
            "subset_column": "is_return_game",
            "target_column": "broke_serve",
            "rate_label": "Break Rate",
            "success_label": "Breaks",
            "pressure_column": "game_point_earned",
            "pressure_hit_label": "Reached game point",
            "pressure_miss_label": "No game point reached",
            "caption": "How return-game outcomes changed based on the scoreboard and whether you created a game-point chance.",
        },
    }
    selected_score_state_view = st.selectbox(
        "Score-state lens",
        list(score_state_views.keys()),
        key="score_state_view",
    )
    score_state_config = score_state_views[selected_score_state_view]
    score_state_game_df = filtered_game_df[
        filtered_game_df[score_state_config["subset_column"]] == 1
    ].copy()
    st.caption(score_state_config["caption"])

    if score_state_game_df.empty:
        st.info("No game-level rows are available for the current filters.")
    else:
        score_state_game_df["Game Score State"] = bucket_game_score_state(score_state_game_df["score_margin_games"])
        score_state_game_df["Set Score State"] = bucket_set_score_state(score_state_game_df["score_margin_sets"])
        player_group_label, player_group_pronoun = describe_player_group(score_state_game_df)
        score_state_game_df["Pressure State"] = np.where(
            pd.to_numeric(score_state_game_df[score_state_config["pressure_column"]], errors="coerce").fillna(0) > 0,
            score_state_config["pressure_hit_label"],
            score_state_config["pressure_miss_label"],
        )
        score_state_game_df["Game Type"] = np.where(
            score_state_game_df["tiebreaker"].fillna(False).astype(bool),
            "Tiebreak",
            "Standard game",
        )

        overall_rate = float(
            pd.to_numeric(score_state_game_df[score_state_config["target_column"]], errors="coerce").fillna(0).mean()
        )
        total_games = int(len(score_state_game_df))
        total_successes = int(
            pd.to_numeric(score_state_game_df[score_state_config["target_column"]], errors="coerce").fillna(0).sum()
        )
        pressure_games = int(
            (pd.to_numeric(score_state_game_df[score_state_config["pressure_column"]], errors="coerce").fillna(0) > 0).sum()
        )

        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        metric_col1.metric("Games", f"{total_games:,}")
        metric_col2.metric(score_state_config["success_label"], f"{total_successes:,}")
        metric_col3.metric(score_state_config["rate_label"], f"{overall_rate:.1%}")
        metric_col4.metric("Pressure Games", f"{pressure_games:,}")

        game_state_summary_df = build_score_state_summary(
            score_state_game_df,
            state_column="Game Score State",
            target_column=score_state_config["target_column"],
            success_label=score_state_config["rate_label"],
            state_order=["Trailing by 2+", "Trailing by 1", "Level", "Leading by 1", "Leading by 2+"],
        )
        set_state_summary_df = build_score_state_summary(
            score_state_game_df,
            state_column="Set Score State",
            target_column=score_state_config["target_column"],
            success_label=score_state_config["rate_label"],
            state_order=["Trailing in sets", "Level in sets", "Leading in sets"],
        )
        pressure_summary_df = build_score_state_summary(
            score_state_game_df,
            state_column="Pressure State",
            target_column=score_state_config["target_column"],
            success_label=score_state_config["rate_label"],
            state_order=[
                score_state_config["pressure_miss_label"],
                score_state_config["pressure_hit_label"],
            ],
        )
        game_type_summary_df = build_score_state_summary(
            score_state_game_df,
            state_column="Game Type",
            target_column=score_state_config["target_column"],
            success_label=score_state_config["rate_label"],
            state_order=["Standard game", "Tiebreak"],
        )

        chart_col1, chart_col2 = st.columns(2)
        game_state_fig = build_score_state_bar_chart(
            game_state_summary_df,
            title=f"{selected_score_state_view}: {score_state_config['rate_label']} by Game Score State",
            rate_column=score_state_config["rate_label"],
            overall_rate=overall_rate,
        )
        set_state_fig = build_score_state_bar_chart(
            set_state_summary_df,
            title=f"{selected_score_state_view}: {score_state_config['rate_label']} by Set Score State",
            rate_column=score_state_config["rate_label"],
            overall_rate=overall_rate,
        )
        if game_state_fig:
            chart_col1.plotly_chart(
                game_state_fig,
                width="stretch",
                key=chart_key("score_state_game_margin", *base_chart_key_parts, selected_score_state_view),
            )
            game_state_explainer = build_score_state_explainer(
                game_state_summary_df,
                rate_column=score_state_config["rate_label"],
                overall_rate=overall_rate,
                subject_label=player_group_label,
                subject_pronoun=player_group_pronoun,
                context_label=f"the {selected_score_state_view.lower()} chart shows that",
                view_label=selected_score_state_view,
            )
            if game_state_explainer:
                with chart_col1:
                    render_score_state_explainer(game_state_explainer)
        if set_state_fig:
            chart_col2.plotly_chart(
                set_state_fig,
                width="stretch",
                key=chart_key("score_state_set_margin", *base_chart_key_parts, selected_score_state_view),
            )
            set_state_explainer = build_score_state_explainer(
                set_state_summary_df,
                rate_column=score_state_config["rate_label"],
                overall_rate=overall_rate,
                subject_label=player_group_label,
                subject_pronoun=player_group_pronoun,
                context_label="the set-score chart shows that",
                view_label=selected_score_state_view,
            )
            if set_state_explainer:
                with chart_col2:
                    render_score_state_explainer(set_state_explainer)

        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.markdown("**Tight-Game Split**")
            st.dataframe(
                style_banded_rows(
                    pressure_summary_df,
                    formatters={
                        score_state_config["rate_label"]: "{:.1%}",
                        "Share of Games": "{:.1%}",
                    },
                ),
                width="stretch",
            )
        with detail_col2:
            st.markdown("**Tiebreak vs Standard**")
            st.dataframe(
                style_banded_rows(
                    game_type_summary_df,
                    formatters={
                        score_state_config["rate_label"]: "{:.1%}",
                        "Share of Games": "{:.1%}",
                    },
                ),
                width="stretch",
            )

        st.markdown("**Full Score-State Table**")
        combined_score_state_df = pd.concat(
            [
                game_state_summary_df.assign(Section="Game Score State"),
                set_state_summary_df.assign(Section="Set Score State"),
                pressure_summary_df.assign(Section="Tight-Game Split"),
                game_type_summary_df.assign(Section="Game Type"),
            ],
            ignore_index=True,
            sort=False,
        )[
            ["Section", "Score State", "Games", "Successes", score_state_config["rate_label"], "Share of Games"]
        ]
        st.dataframe(
            style_banded_rows(
                combined_score_state_df,
                formatters={
                    score_state_config["rate_label"]: "{:.1%}",
                    "Share of Games": "{:.1%}",
                },
            ),
            width="stretch",
        )

        score_state_download_df = score_state_game_df[
            [
                column
                for column in [
                    "matchId",
                    "gameId",
                    "player",
                    "opp",
                    "Match Date",
                    "set",
                    "game",
                    "score_margin_games",
                    "score_margin_sets",
                    "Game Score State",
                    "Set Score State",
                    "Pressure State",
                    "Game Type",
                    score_state_config["target_column"],
                ]
                if column in score_state_game_df.columns
            ]
        ]
        st.download_button(
            "Download Score-State Games CSV",
            data=to_csv_bytes(score_state_download_df),
            file_name=f"{selected_score_state_view.lower().replace(' ', '_')}_score_state_games.csv",
            mime="text/csv",
            width="stretch",
        )

with tabs[5]:
    st.subheader(f"Serve Win Probability: {current_scope}")
    st.caption(
        "Logistic-regression probability curves with observed-bin context from real match summaries."
    )

    control_col1, control_col2, control_col3 = st.columns(3)
    with control_col1:
        outcome_lens = st.selectbox(
            "Outcome lens",
            ["Match Win Probability", "Set Win Probability", "Game Win Probability"],
            key="serve_win_probability_outcome_lens",
        )
    with control_col2:
        bin_size_pct = st.slider(
            "Bin width (percentage points)",
            min_value=5,
            max_value=20,
            value=10,
            step=5,
            key="serve_win_rate_bin_width",
        )
    with control_col3:
        min_matches_per_bin = st.slider(
            "Minimum matches per bin",
            min_value=1,
            max_value=10,
            value=3,
            step=1,
            key="serve_win_rate_min_matches",
        )

    serve_bin_specs = [
        {
            "label": "1st Serve In %",
            "metric_column": "1st Serve In %",
        },
        {
            "label": "1st Serve Won %",
            "metric_column": "1st Serve Won %",
        },
        {
            "label": "2nd Serve In %",
            "metric_column": "2nd Serve In %",
        },
        {
            "label": "2nd Serve Won %",
            "metric_column": "2nd Serve Won %",
        },
    ]

    serve_rate_df = add_match_rate_columns(filtered_df)
    if outcome_lens == "Match Win Probability":
        serve_rate_df["Outcome Successes"] = (
            serve_rate_df["Match Result"].fillna("").astype(str).str.upper().eq("W").astype("float64")
        )
        serve_rate_df["Outcome Failures"] = (
            serve_rate_df["Match Result"].fillna("").astype(str).str.upper().eq("L").astype("float64")
        )
    elif outcome_lens == "Set Win Probability":
        serve_rate_df["Outcome Successes"] = pd.to_numeric(
            serve_rate_df["Sets Won"], errors="coerce"
        ).fillna(0.0)
        serve_rate_df["Outcome Failures"] = pd.to_numeric(
            serve_rate_df["Sets Lost"], errors="coerce"
        ).fillna(0.0)
    else:
        serve_rate_df["Outcome Successes"] = pd.to_numeric(
            serve_rate_df["Games Won"], errors="coerce"
        ).fillna(0.0)
        serve_rate_df["Outcome Failures"] = pd.to_numeric(
            serve_rate_df["Games Lost"], errors="coerce"
        ).fillna(0.0)

    rendered_bin_chart = False
    for row_start in range(0, len(serve_bin_specs), 2):
        row_specs = serve_bin_specs[row_start : row_start + 2]
        columns = st.columns(len(row_specs))
        for col_index, spec in enumerate(row_specs):
            with columns[col_index]:
                figure = build_outcome_probability_plot(
                    serve_rate_df,
                    metric_column=spec["metric_column"],
                    metric_label=spec["label"],
                    success_column="Outcome Successes",
                    failure_column="Outcome Failures",
                    outcome_label=outcome_lens,
                    title=f"{spec['label']} vs {outcome_lens}",
                    bin_size_pct=bin_size_pct,
                    min_matches_per_bin=min_matches_per_bin,
                )
                if figure:
                    st.plotly_chart(
                        figure,
                        width="stretch",
                        key=chart_key(
                            "serve_win_rate_bins",
                            *base_chart_key_parts,
                            spec["label"],
                            bin_size_pct,
                            min_matches_per_bin,
                        ),
                    )
                    rendered_bin_chart = True
                else:
                    st.info(
                        f"Not enough matches to build bins for {spec['label']} with the current filters."
                    )

    if rendered_bin_chart:
        st.markdown(
            "The red line is the logistic-regression probability curve for the selected outcome lens."
        )

with tabs[10]:
    st.subheader(f"Serve / Return Score-State Rates: {current_scope}")
    rate_score_state_views = {
        "1st Serve In %": {
            "subset_column": "is_service_game",
            "numerator_column": "first_serve_in",
            "denominator_column": "first_serve_attempt",
            "numerator_label": "1st serves in",
            "denominator_label": "1st serve attempts",
            "pressure_column": "game_point_faced",
            "pressure_hit_label": "Faced game point",
            "pressure_miss_label": "No game point faced",
            "caption": "How first-serve rate changed by scoreboard context during service games.",
        },
        "1st Serve Won %": {
            "subset_column": "is_service_game",
            "numerator_column": "first_serve_won",
            "denominator_column": "first_serve_in",
            "numerator_label": "1st-serve points won",
            "denominator_label": "1st serves in",
            "pressure_column": "game_point_faced",
            "pressure_hit_label": "Faced game point",
            "pressure_miss_label": "No game point faced",
            "caption": "How first-serve points won changed by scoreboard context during service games.",
        },
        "2nd Serve In %": {
            "subset_column": "is_service_game",
            "numerator_column": "second_serve_in",
            "denominator_column": "second_serve_attempt",
            "numerator_label": "2nd serves in",
            "denominator_label": "2nd serve attempts",
            "pressure_column": "game_point_faced",
            "pressure_hit_label": "Faced game point",
            "pressure_miss_label": "No game point faced",
            "caption": "How second-serve rate changed by scoreboard context during service games.",
        },
        "2nd Serve Won %": {
            "subset_column": "is_service_game",
            "numerator_column": "second_serve_won",
            "denominator_column": "second_serve_attempt",
            "numerator_label": "2nd-serve points won",
            "denominator_label": "2nd serve attempts",
            "pressure_column": "game_point_faced",
            "pressure_hit_label": "Faced game point",
            "pressure_miss_label": "No game point faced",
            "caption": "How second-serve points won changed by scoreboard context during service games.",
        },
        "1st Return In %": {
            "subset_column": "is_return_game",
            "numerator_column": "first_serve_return_in",
            "denominator_column": "first_serve_return_opportunity",
            "numerator_label": "1st-serve returns in play",
            "denominator_label": "1st-serve return chances",
            "pressure_column": "game_point_earned",
            "pressure_hit_label": "Reached game point",
            "pressure_miss_label": "No game point reached",
            "caption": "How first-serve return rate changed by scoreboard context during return games.",
        },
        "1st Return Won %": {
            "subset_column": "is_return_game",
            "numerator_column": "first_serve_return_won",
            "denominator_column": "first_serve_return_opportunity",
            "numerator_label": "1st-serve return points won",
            "denominator_label": "1st-serve return chances",
            "pressure_column": "game_point_earned",
            "pressure_hit_label": "Reached game point",
            "pressure_miss_label": "No game point reached",
            "caption": "How first-serve return points won changed by scoreboard context during return games.",
        },
        "2nd Return In %": {
            "subset_column": "is_return_game",
            "numerator_column": "second_serve_return_in",
            "denominator_column": "second_serve_return_opportunity",
            "numerator_label": "2nd-serve returns in play",
            "denominator_label": "2nd-serve return chances",
            "pressure_column": "game_point_earned",
            "pressure_hit_label": "Reached game point",
            "pressure_miss_label": "No game point reached",
            "caption": "How second-serve return rate changed by scoreboard context during return games.",
        },
        "2nd Return Won %": {
            "subset_column": "is_return_game",
            "numerator_column": "second_serve_return_won",
            "denominator_column": "second_serve_return_opportunity",
            "numerator_label": "2nd-serve return points won",
            "denominator_label": "2nd-serve return chances",
            "pressure_column": "game_point_earned",
            "pressure_hit_label": "Reached game point",
            "pressure_miss_label": "No game point reached",
            "caption": "How second-serve return points won changed by scoreboard context during return games.",
        },
    }
    selected_rate_score_state_view = st.selectbox(
        "Serve/return rate lens",
        list(rate_score_state_views.keys()),
        key="rate_score_state_view",
    )
    rate_score_state_config = rate_score_state_views[selected_rate_score_state_view]
    rate_score_state_game_df = filtered_game_df[
        filtered_game_df[rate_score_state_config["subset_column"]] == 1
    ].copy()
    st.caption(rate_score_state_config["caption"])

    if rate_score_state_game_df.empty:
        st.info("No game-level rows are available for the current filters.")
    else:
        numerator_display_label = rate_score_state_config["numerator_label"]
        denominator_display_label = rate_score_state_config["denominator_label"]
        rate_score_state_game_df["Game Score State"] = bucket_game_score_state(rate_score_state_game_df["score_margin_games"])
        rate_score_state_game_df["Set Score State"] = bucket_set_score_state(rate_score_state_game_df["score_margin_sets"])
        rate_score_state_game_df["Pressure State"] = np.where(
            pd.to_numeric(rate_score_state_game_df[rate_score_state_config["pressure_column"]], errors="coerce").fillna(0) > 0,
            rate_score_state_config["pressure_hit_label"],
            rate_score_state_config["pressure_miss_label"],
        )
        rate_score_state_game_df["Game Type"] = np.where(
            rate_score_state_game_df["tiebreaker"].fillna(False).astype(bool),
            "Tiebreak",
            "Standard game",
        )

        total_games = int(len(rate_score_state_game_df))
        total_numerator = float(
            pd.to_numeric(rate_score_state_game_df[rate_score_state_config["numerator_column"]], errors="coerce").fillna(0).sum()
        )
        total_denominator = float(
            pd.to_numeric(rate_score_state_game_df[rate_score_state_config["denominator_column"]], errors="coerce").fillna(0).sum()
        )
        overall_rate = float(safe_ratio(pd.Series([total_numerator]), pd.Series([total_denominator])).iloc[0])
        pressure_games = int(
            (pd.to_numeric(rate_score_state_game_df[rate_score_state_config["pressure_column"]], errors="coerce").fillna(0) > 0).sum()
        )

        metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
        metric_col1.metric("Games", f"{total_games:,}")
        metric_col2.metric(numerator_display_label, f"{total_numerator:,.0f}")
        metric_col3.metric(denominator_display_label, f"{total_denominator:,.0f}")
        metric_col4.metric(selected_rate_score_state_view, f"{overall_rate:.1%}")
        metric_col5.metric("Pressure Games", f"{pressure_games:,}")

        game_state_summary_df = build_score_state_ratio_summary(
            rate_score_state_game_df,
            state_column="Game Score State",
            numerator_column=rate_score_state_config["numerator_column"],
            denominator_column=rate_score_state_config["denominator_column"],
            rate_label=selected_rate_score_state_view,
            state_order=["Trailing by 2+", "Trailing by 1", "Level", "Leading by 1", "Leading by 2+"],
        )
        set_state_summary_df = build_score_state_ratio_summary(
            rate_score_state_game_df,
            state_column="Set Score State",
            numerator_column=rate_score_state_config["numerator_column"],
            denominator_column=rate_score_state_config["denominator_column"],
            rate_label=selected_rate_score_state_view,
            state_order=["Trailing in sets", "Level in sets", "Leading in sets"],
        )
        pressure_summary_df = build_score_state_ratio_summary(
            rate_score_state_game_df,
            state_column="Pressure State",
            numerator_column=rate_score_state_config["numerator_column"],
            denominator_column=rate_score_state_config["denominator_column"],
            rate_label=selected_rate_score_state_view,
            state_order=[
                rate_score_state_config["pressure_miss_label"],
                rate_score_state_config["pressure_hit_label"],
            ],
        )
        game_type_summary_df = build_score_state_ratio_summary(
            rate_score_state_game_df,
            state_column="Game Type",
            numerator_column=rate_score_state_config["numerator_column"],
            denominator_column=rate_score_state_config["denominator_column"],
            rate_label=selected_rate_score_state_view,
            state_order=["Standard game", "Tiebreak"],
        )

        chart_col1, chart_col2 = st.columns(2)
        game_state_fig = build_score_state_ratio_bar_chart(
            game_state_summary_df,
            title=f"{selected_rate_score_state_view} by Game Score State",
            rate_column=selected_rate_score_state_view,
            overall_rate=overall_rate,
            numerator_label=numerator_display_label,
            denominator_label=denominator_display_label,
        )
        set_state_fig = build_score_state_ratio_bar_chart(
            set_state_summary_df,
            title=f"{selected_rate_score_state_view} by Set Score State",
            rate_column=selected_rate_score_state_view,
            overall_rate=overall_rate,
            numerator_label=numerator_display_label,
            denominator_label=denominator_display_label,
        )
        if game_state_fig:
            chart_col1.plotly_chart(
                game_state_fig,
                width="stretch",
                key=chart_key("rate_score_state_game_margin", *base_chart_key_parts, selected_rate_score_state_view),
            )
        if set_state_fig:
            chart_col2.plotly_chart(
                set_state_fig,
                width="stretch",
                key=chart_key("rate_score_state_set_margin", *base_chart_key_parts, selected_rate_score_state_view),
            )

        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.markdown("**Tight-Game Split**")
            st.dataframe(
                style_banded_rows(
                    pressure_summary_df.rename(
                        columns={
                            "Numerator": numerator_display_label,
                            "Denominator": denominator_display_label,
                        }
                    ),
                    formatters={
                        selected_rate_score_state_view: "{:.1%}",
                        "Share of Games": "{:.1%}",
                    },
                ),
                width="stretch",
            )
        with detail_col2:
            st.markdown("**Tiebreak vs Standard**")
            st.dataframe(
                style_banded_rows(
                    game_type_summary_df.rename(
                        columns={
                            "Numerator": numerator_display_label,
                            "Denominator": denominator_display_label,
                        }
                    ),
                    formatters={
                        selected_rate_score_state_view: "{:.1%}",
                        "Share of Games": "{:.1%}",
                    },
                ),
                width="stretch",
            )

        st.markdown("**Full Score-State Table**")
        combined_rate_score_state_df = pd.concat(
            [
                game_state_summary_df.assign(Section="Game Score State"),
                set_state_summary_df.assign(Section="Set Score State"),
                pressure_summary_df.assign(Section="Tight-Game Split"),
                game_type_summary_df.assign(Section="Game Type"),
            ],
            ignore_index=True,
            sort=False,
        ).rename(
            columns={
                "Numerator": numerator_display_label,
                "Denominator": denominator_display_label,
            }
        )[
            [
                "Section",
                "Score State",
                "Games",
                numerator_display_label,
                denominator_display_label,
                selected_rate_score_state_view,
                "Share of Games",
            ]
        ]
        st.dataframe(
            style_banded_rows(
                combined_rate_score_state_df,
                formatters={
                    selected_rate_score_state_view: "{:.1%}",
                    "Share of Games": "{:.1%}",
                },
            ),
            width="stretch",
        )

        rate_score_state_download_df = rate_score_state_game_df[
            [
                column
                for column in [
                    "matchId",
                    "gameId",
                    "player",
                    "opp",
                    "Match Date",
                    "set",
                    "game",
                    "score_margin_games",
                    "score_margin_sets",
                    "Game Score State",
                    "Set Score State",
                    "Pressure State",
                    "Game Type",
                    rate_score_state_config["numerator_column"],
                    rate_score_state_config["denominator_column"],
                    selected_rate_score_state_view,
                ]
                if column in rate_score_state_game_df.columns
            ]
        ]
        st.download_button(
            "Download Serve/Return Score-State CSV",
            data=to_csv_bytes(rate_score_state_download_df),
            file_name=f"{selected_rate_score_state_view.lower().replace(' ', '_').replace('%', 'pct')}_score_state_games.csv",
            mime="text/csv",
            width="stretch",
        )

