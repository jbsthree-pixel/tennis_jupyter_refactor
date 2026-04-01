"""Reusable analytics helpers for the cross-platform browser app."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import MONTH_ORDER, RAW_FIELD_FORMULAS
from .pipeline import build_match_summary
from .shared import safe_ratio


def filter_matches(
    df: pd.DataFrame,
    player: str | list[str] | tuple[str, ...] | set[str] | None = None,
    year: int | None = None,
    month_name: str | None = None,
    opp_team: str | None = None,
    season_label: str | None = None,
) -> pd.DataFrame:
    """Filter the match-summary dataframe using app-friendly selectors."""
    filtered = with_season_columns(df)

    if isinstance(player, str):
        selected_players = [player] if player and player != "All" else []
    elif player:
        selected_players = [
            str(value)
            for value in player
            if value and str(value) != "All"
        ]
    else:
        selected_players = []

    if selected_players:
        filtered = filtered[filtered["player"].isin(selected_players)]
    if year is not None:
        filtered = filtered[filtered["Match Year"] == year]
    if month_name and month_name != "All":
        filtered = filtered[filtered["Match Month Name"] == month_name]
    if opp_team and opp_team != "All":
        normalized = filtered["opp_team"].fillna("").astype(str).str.strip()
        if opp_team == "None Listed":
            filtered = filtered[normalized == ""]
        else:
            filtered = filtered[normalized == opp_team]
    if season_label and season_label != "All":
        filtered = filtered[filtered["_Season Label"] == season_label]

    return filtered.reset_index(drop=True)


def summarize_key_insights(df: pd.DataFrame) -> dict[str, object]:
    """Return high-level metrics for the current filtered dataframe."""
    total_matches = int(df["matchId"].nunique()) if "matchId" in df.columns else len(df)
    total_players = int(df["player"].nunique()) if "player" in df.columns else 0
    wins = int((df["Match Result"] == "W").sum()) if "Match Result" in df.columns else 0
    losses = int((df["Match Result"] == "L").sum()) if "Match Result" in df.columns else 0
    win_rate = wins / (wins + losses) if (wins + losses) else 0.0
    date_min = df["Match Date"].min() if "Match Date" in df.columns and not df.empty else None
    date_max = df["Match Date"].max() if "Match Date" in df.columns and not df.empty else None

    return {
        "total_matches": total_matches,
        "total_players": total_players,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "date_range": (date_min, date_max),
    }


def season_sort_and_label(ts: pd.Timestamp) -> tuple[float, str]:
    """Map a timestamp to the app's August-to-June tennis season labels."""
    if pd.isna(ts):
        return (float("inf"), "(No Season)")

    year = int(ts.year)
    month = int(ts.month)
    if month >= 8:
        return (float(year), f"August {year} to June {year + 1}")
    if month <= 6:
        return (float(year - 1), f"August {year - 1} to June {year}")
    return (year + 0.5, f"July {year} (Outside Season)")


def with_season_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add season label and sort columns to a dataframe."""
    out = df.copy()
    if "Match Date" in out.columns:
        ts = pd.to_datetime(out["Match Date"], errors="coerce")
    elif "date" in out.columns:
        ts = pd.to_datetime(out["date"], errors="coerce")
    else:
        ts = pd.Series([pd.NaT] * len(out))

    season_info = ts.apply(season_sort_and_label)
    out["_Season Sort"] = season_info.apply(lambda value: value[0])
    out["_Season Label"] = season_info.apply(lambda value: value[1])
    return out


def available_filter_values(df: pd.DataFrame) -> dict[str, list[str]]:
    """Return app filter choices in display order."""
    season_df = with_season_columns(df)
    years = sorted(
        [int(value) for value in season_df["Match Year"].dropna().unique().tolist()]
    )
    present_months = set(season_df["Match Month Name"].dropna().astype(str).tolist())
    months = [month for month in MONTH_ORDER if month in present_months]
    opp_teams = sorted(
        {
            str(value).strip()
            for value in season_df["opp_team"].dropna().astype(str)
            if str(value).strip()
        }
    )
    has_blank_opp = (
        season_df["opp_team"].isna().any()
        or (season_df["opp_team"].fillna("").astype(str).str.strip() == "").any()
    )
    seasons = (
        season_df[["_Season Sort", "_Season Label"]]
        .drop_duplicates()
        .sort_values(["_Season Sort", "_Season Label"], na_position="last")
    )

    return {
        "players": ["All"] + sorted(season_df["player"].dropna().astype(str).unique().tolist()),
        "years": ["All"] + [str(year) for year in years],
        "months": ["All"] + months,
        "opp_teams": ["All"] + (["None Listed"] if has_blank_opp else []) + opp_teams,
        "seasons": ["All"] + seasons["_Season Label"].astype(str).tolist(),
    }


def build_pivot_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Build an Excel-style pivot table with player totals and indented seasons."""
    calc_df = with_season_columns(df)
    if calc_df.empty:
        return pd.DataFrame()

    metric_columns = {
        "Matches": ("matchId", "nunique"),
        "Matches Won": ("Match Result", lambda values: (values == "W").sum()),
        "Matches Lost": ("Match Result", lambda values: (values == "L").sum()),
        "Sets Won": ("Sets Won", "sum"),
        "Sets Lost": ("Sets Lost", "sum"),
        "Games Won": ("Games Won", "sum"),
        "Games Lost": ("Games Lost", "sum"),
    }
    player_totals = (
        calc_df.groupby("player", dropna=False)
        .agg(**metric_columns)
        .reset_index()
        .sort_values("player")
    )
    player_totals = player_totals.rename(columns={"player": "Row Labels"})
    player_totals.insert(0, "_Row Sort", 0)
    player_totals["_Player Sort"] = player_totals["Row Labels"].astype(str)
    player_totals["_Season Sort"] = -1

    season_rows = (
        calc_df.groupby(["player", "_Season Label"], dropna=False)
        .agg(**metric_columns)
        .reset_index()
        .merge(
            calc_df[["player", "_Season Label", "_Season Sort"]].drop_duplicates(),
            on=["player", "_Season Label"],
            how="left",
        )
    )
    season_rows["Row Labels"] = "\u00A0\u00A0\u00A0\u00A0" + season_rows["_Season Label"].astype(str)
    season_rows.insert(0, "_Row Sort", 1)
    season_rows["_Player Sort"] = season_rows["player"].astype(str)

    combined = pd.concat(
        [
            player_totals,
            season_rows[
                ["_Row Sort", "_Player Sort", "_Season Sort", "Row Labels", *metric_columns]
            ],
        ],
        ignore_index=True,
        sort=False,
    )
    combined = combined.sort_values(
        ["_Player Sort", "_Row Sort", "_Season Sort", "Row Labels"],
        na_position="last",
    ).reset_index(drop=True)
    combined = combined.drop(columns=["_Row Sort", "_Player Sort", "_Season Sort"])

    numeric_columns = combined.select_dtypes(include="number").columns
    combined[numeric_columns] = combined[numeric_columns].fillna(0).astype(int)
    return combined


def build_player_comparison_summary(
    df: pd.DataFrame,
    player_order: list[str] | None = None,
) -> pd.DataFrame:
    """Build one comparison row per player for side-by-side analysis."""
    if df.empty or "player" not in df.columns:
        return pd.DataFrame()

    calc_df = with_season_columns(df)
    required_defaults = [
        "first_serve_attempt",
        "first_serve_in",
        "first_serve_won",
        "second_serve_attempt",
        "second_serve_won",
        "first_serve_return_opportunity",
        "first_serve_return_won",
        "second_serve_return_opportunity",
        "second_serve_return_won",
        "break_point_total",
        "break_point_won",
        "break_point_faced",
        "break_point_saved",
    ]
    for column in required_defaults:
        if column not in calc_df.columns:
            calc_df[column] = 0

    comparison = (
        calc_df.groupby("player", dropna=False)
        .agg(
            Matches=("matchId", "nunique"),
            Wins=("Match Result", lambda values: (values == "W").sum()),
            Losses=("Match Result", lambda values: (values == "L").sum()),
            Sets_Won=("Sets Won", "sum"),
            Sets_Lost=("Sets Lost", "sum"),
            Games_Won=("Games Won", "sum"),
            Games_Lost=("Games Lost", "sum"),
            First_Serve_Attempts=("first_serve_attempt", "sum"),
            First_Serve_In=("first_serve_in", "sum"),
            First_Serve_Won=("first_serve_won", "sum"),
            Second_Serve_Attempts=("second_serve_attempt", "sum"),
            Second_Serve_Won=("second_serve_won", "sum"),
            First_Return_Opps=("first_serve_return_opportunity", "sum"),
            First_Return_Won=("first_serve_return_won", "sum"),
            Second_Return_Opps=("second_serve_return_opportunity", "sum"),
            Second_Return_Won=("second_serve_return_won", "sum"),
            Break_Points_Earned=("break_point_total", "sum"),
            Break_Points_Converted=("break_point_won", "sum"),
            Break_Points_Faced=("break_point_faced", "sum"),
            Break_Points_Saved=("break_point_saved", "sum"),
        )
        .reset_index()
        .rename(columns={"player": "Player"})
    )

    comparison["Win Rate"] = safe_ratio(comparison["Wins"], comparison["Matches"])
    comparison["1st Serve In %"] = safe_ratio(
        comparison["First_Serve_In"],
        comparison["First_Serve_Attempts"],
    )
    comparison["1st Serve Won %"] = safe_ratio(
        comparison["First_Serve_Won"],
        comparison["First_Serve_In"],
    )
    comparison["2nd Serve Won %"] = safe_ratio(
        comparison["Second_Serve_Won"],
        comparison["Second_Serve_Attempts"],
    )
    comparison["1st Return Won %"] = safe_ratio(
        comparison["First_Return_Won"],
        comparison["First_Return_Opps"],
    )
    comparison["2nd Return Won %"] = safe_ratio(
        comparison["Second_Return_Won"],
        comparison["Second_Return_Opps"],
    )
    comparison["BP Won %"] = safe_ratio(
        comparison["Break_Points_Converted"],
        comparison["Break_Points_Earned"],
    )
    comparison["BP Saved %"] = safe_ratio(
        comparison["Break_Points_Saved"],
        comparison["Break_Points_Faced"],
    )

    comparison = comparison[
        [
            "Player",
            "Matches",
            "Wins",
            "Losses",
            "Win Rate",
            "Sets_Won",
            "Sets_Lost",
            "Games_Won",
            "Games_Lost",
            "1st Serve In %",
            "1st Serve Won %",
            "2nd Serve Won %",
            "1st Return Won %",
            "2nd Return Won %",
            "BP Won %",
            "BP Saved %",
        ]
    ].rename(
        columns={
            "Sets_Won": "Sets Won",
            "Sets_Lost": "Sets Lost",
            "Games_Won": "Games Won",
            "Games_Lost": "Games Lost",
        }
    )

    if player_order:
        rank = {player: index for index, player in enumerate(player_order)}
        comparison["_player_sort"] = comparison["Player"].map(rank).fillna(len(rank))
        comparison = comparison.sort_values(["_player_sort", "Player"]).drop(columns="_player_sort")
    else:
        comparison = comparison.sort_values(
            ["Matches", "Wins", "Player"],
            ascending=[False, False, True],
        )

    numeric_columns = comparison.select_dtypes(include="number").columns
    count_columns = ["Matches", "Wins", "Losses", "Sets Won", "Sets Lost", "Games Won", "Games Lost"]
    for column in count_columns:
        if column in comparison.columns:
            comparison[column] = comparison[column].fillna(0).astype(int)
    comparison[numeric_columns.difference(count_columns)] = comparison[
        numeric_columns.difference(count_columns)
    ].fillna(0.0)
    return comparison.reset_index(drop=True)


def build_serve_return_match_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Build the detailed serve and return match stats table from the original app."""
    calc_df = with_season_columns(df)
    if calc_df.empty:
        return pd.DataFrame()

    defaults = [
        "ace",
        "double_fault",
        "first_serve_attempt",
        "first_serve_in",
        "first_serve_won",
        "second_serve_attempt",
        "second_serve_in",
        "second_serve_won",
        "first_serve_return_opportunity",
        "first_serve_return_in",
        "first_serve_return_won",
        "second_serve_return_opportunity",
        "second_serve_return_in",
        "second_serve_return_won",
        "opp_double_fault",
        "first_serve_not_returned",
    ]
    ace_df = calc_df.copy()
    for column in defaults:
        if column not in ace_df.columns:
            ace_df[column] = 0

    if "opp_team" not in ace_df.columns:
        ace_df["opp_team"] = ""
    ace_df["opp_team"] = ace_df["opp_team"].fillna("").astype(str).str.strip()
    ace_df["matchId"] = ace_df["matchId"].fillna("").astype(str)
    ace_df["Match Date"] = pd.to_datetime(ace_df["Match Date"], errors="coerce")

    grouped = (
        ace_df.groupby(
            ["player", "_Season Label", "_Season Sort", "opp_team", "Match Date", "matchId"],
            dropna=False,
        )[defaults]
        .sum()
        .reset_index()
        .sort_values(
            ["player", "_Season Sort", "_Season Label", "opp_team", "Match Date", "matchId"],
            na_position="last",
        )
    )
    grouped["+/-"] = grouped["ace"] - grouped["double_fault"]
    grouped["Ace %"] = safe_ratio(grouped["ace"], grouped["first_serve_attempt"])
    grouped["DF %"] = safe_ratio(grouped["double_fault"], grouped["second_serve_attempt"])
    grouped["1SNR %"] = safe_ratio(grouped["first_serve_not_returned"], grouped["first_serve_in"])
    grouped["First Serve %"] = safe_ratio(grouped["first_serve_in"], grouped["first_serve_attempt"])
    grouped["1st Serve Win %"] = safe_ratio(grouped["first_serve_won"], grouped["first_serve_in"])
    grouped["Second Serve %"] = safe_ratio(grouped["second_serve_in"], grouped["second_serve_attempt"])
    grouped["2nd Serve Win %"] = safe_ratio(grouped["second_serve_won"], grouped["second_serve_attempt"])
    grouped["First Serve Returns %"] = safe_ratio(
        grouped["first_serve_return_in"],
        grouped["first_serve_return_opportunity"],
    )
    grouped["First Serve Returns Won %"] = safe_ratio(
        grouped["first_serve_return_won"],
        grouped["first_serve_return_opportunity"],
    )
    grouped["Second Serve Returns %"] = safe_ratio(
        grouped["second_serve_return_in"],
        grouped["second_serve_return_opportunity"],
    )
    grouped["Second Serve Returns Won %"] = safe_ratio(
        grouped["second_serve_return_won"],
        grouped["second_serve_return_opportunity"],
    )

    result = pd.DataFrame(
        {
            "Player": grouped["player"].astype(str),
            "Year": grouped["_Season Label"].astype(str),
            "Opp Team": grouped["opp_team"].replace("", "None Listed"),
            "Match Date": grouped["Match Date"].dt.strftime("%Y-%m-%d").fillna(""),
            "Match ID": grouped["matchId"].astype(str),
            "Aces": grouped["ace"].astype(int),
            "Ace %": grouped["Ace %"],
            "Double Faults": grouped["double_fault"].astype(int),
            "DF %": grouped["DF %"],
            "+/-": grouped["+/-"].astype(int),
            "1SNR": grouped["first_serve_not_returned"].astype(int),
            "1SNR %": grouped["1SNR %"],
            "First Serves": grouped["first_serve_attempt"].astype(int),
            "First Serves In": grouped["first_serve_in"].astype(int),
            "First Serve %": grouped["First Serve %"],
            "First Serve Won": grouped["first_serve_won"].astype(int),
            "1st Serve Win %": grouped["1st Serve Win %"],
            "Second Serves": grouped["second_serve_attempt"].astype(int),
            "Second Serves In": grouped["second_serve_in"].astype(int),
            "Second Serve %": grouped["Second Serve %"],
            "Second Serve Won": grouped["second_serve_won"].astype(int),
            "2nd Serve Win %": grouped["2nd Serve Win %"],
            "First Serve Returns": grouped["first_serve_return_opportunity"].astype(int),
            "First Serve Returns In": grouped["first_serve_return_in"].astype(int),
            "First Serve Returns %": grouped["First Serve Returns %"],
            "First Serve Returns Won": grouped["first_serve_return_won"].astype(int),
            "First Serve Returns Won %": grouped["First Serve Returns Won %"],
            "Second Serve Returns": grouped["second_serve_return_opportunity"].astype(int),
            "Second Serve Returns In": grouped["second_serve_return_in"].astype(int),
            "Second Serve Returns %": grouped["Second Serve Returns %"],
            "Second Serve Returns Won": grouped["second_serve_return_won"].astype(int),
            "Second Serve Returns Won %": grouped["Second Serve Returns Won %"],
            "Opp Double Faults": grouped["opp_double_fault"].astype(int),
        }
    )
    return result.reset_index(drop=True)


def build_raw_data_dictionary(df: pd.DataFrame) -> pd.DataFrame:
    """Return field descriptions for the raw matches table."""
    return pd.DataFrame(
        {
            "Field": list(df.columns),
            "How Calculated": [
                RAW_FIELD_FORMULAS.get(
                    column,
                    "Carried from grouped match-level data without an extra app formula.",
                )
                for column in df.columns
            ],
        }
    )


def load_source_review(source_csv_path: str | Path) -> tuple[pd.DataFrame, dict[int, list[int]], pd.DataFrame]:
    """Load grouped source rows for review and editing."""
    source_path = Path(source_csv_path)
    source_df = pd.read_csv(source_path, low_memory=False)
    source_columns = ["date", "player", "opp", "opp_team"]

    missing = [column for column in source_columns if column not in source_df.columns]
    if missing:
        raise ValueError(f"Missing source columns: {', '.join(missing)}")

    review_base = source_df[source_columns].copy()
    for column in source_columns:
        review_base[column] = review_base[column].fillna("").astype(str).str.strip()
    review_base["_source_index"] = review_base.index

    grouped = (
        review_base.groupby(source_columns, dropna=False, sort=False)["_source_index"]
        .agg(list)
        .reset_index(name="_source_indices")
    )
    grouped["_review_id"] = range(len(grouped))
    grouped["rows_affected"] = grouped["_source_indices"].apply(len)

    review_df = grouped[["_review_id"] + source_columns + ["rows_affected"]].copy()
    review_df["Delete"] = False
    index_map = {
        int(row["_review_id"]): list(row["_source_indices"])
        for _, row in grouped.iterrows()
    }
    return review_df, index_map, source_df


def save_source_review_changes(
    edited_review_df: pd.DataFrame,
    index_map: dict[int, list[int]],
    source_df: pd.DataFrame,
    source_csv_path: str | Path,
) -> pd.DataFrame:
    """Apply grouped row edits back to the source CSV and rebuild the summary."""
    updated_source = source_df.copy()
    delete_ids = edited_review_df.loc[edited_review_df["Delete"] == True, "_review_id"].tolist()  # noqa: E712
    delete_indices: set[int] = set()
    for review_id in delete_ids:
        delete_indices.update(index_map.get(int(review_id), []))

    if delete_indices:
        updated_source = updated_source.drop(index=list(delete_indices))

    editable_rows = edited_review_df.loc[edited_review_df["Delete"] != True].copy()  # noqa: E712
    for _, row in editable_rows.iterrows():
        review_id = int(row["_review_id"])
        for source_index in index_map.get(review_id, []):
            if source_index not in updated_source.index:
                continue
            for column in ["date", "player", "opp", "opp_team"]:
                updated_source.at[source_index, column] = row[column]

    updated_source.to_csv(source_csv_path, index=False)
    return build_match_summary(source_csv_path)
