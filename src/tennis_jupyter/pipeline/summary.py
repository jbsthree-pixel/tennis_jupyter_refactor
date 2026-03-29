"""Build a match-level summary dataset from point-level tennis exports."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .rawpoints import add_rawpoints_columns, validate_required_columns


INDICATOR_COLUMNS = [
    "service_point",
    "return_point",
    "point_won",
    "first_serve_attempt",
    "first_serve_miss",
    "second_serve_attempt",
    "double_fault",
    "first_serve_in",
    "first_serve_won",
    "second_serve_in",
    "second_serve_won",
    "first_serve_return_opportunity",
    "first_serve_return_in",
    "first_serve_return_won",
    "first_serve_not_returned",
    "second_serve_return_opportunity",
    "second_serve_return_in",
    "second_serve_return_won",
    "opp_double_fault",
    "winner",
    "ace",
    "unforced_error",
    "break_point_total",
    "break_point_won",
    "break_point_faced",
    "break_point_saved",
    "short_rally_won",
    "medium_rally_won",
    "long_rally_won",
]


def parse_final_score(score: str | float | None) -> dict[str, int]:
    """Split a final-score string into aggregate game and set counts."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return {"Games Won": 0, "Games Lost": 0, "Sets Won": 0, "Sets Lost": 0}

    score_str = str(score).strip()
    if not score_str:
        return {"Games Won": 0, "Games Lost": 0, "Sets Won": 0, "Sets Lost": 0}

    games_won = 0
    games_lost = 0
    sets_won = 0
    sets_lost = 0

    for set_score in score_str.split("|"):
        cleaned_score = re.sub(r"\([^)]*\)", "", set_score.strip())
        match = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*", cleaned_score)
        if not match:
            continue

        player_games = int(match.group(1))
        opponent_games = int(match.group(2))
        games_won += player_games
        games_lost += opponent_games

        if player_games > opponent_games:
            sets_won += 1
        elif opponent_games > player_games:
            sets_lost += 1

    return {
        "Games Won": games_won,
        "Games Lost": games_lost,
        "Sets Won": sets_won,
        "Sets Lost": sets_lost,
    }


def _load_name_mapping(name_map_path: Path | None) -> dict[str, str]:
    """Load an optional raw-name to clean-name mapping spreadsheet."""
    if name_map_path is None or not name_map_path.exists():
        return {}

    name_map_df = pd.read_excel(name_map_path)
    required_cols = {"RawName", "CleanName", "Active"}
    missing_cols = required_cols - set(name_map_df.columns)
    if missing_cols:
        raise ValueError(
            f"{name_map_path.name} missing columns: {', '.join(sorted(missing_cols))}"
        )

    active_map = name_map_df[name_map_df["Active"] == True]  # noqa: E712
    return {
        str(row["RawName"]).strip().lower(): str(row["CleanName"]).strip()
        for _, row in active_map.iterrows()
        if pd.notna(row["RawName"]) and pd.notna(row["CleanName"])
    }


def _clean_name(value: str, mapping: dict[str, str]) -> str:
    """Normalize name formatting while allowing explicit mappings to win."""
    raw = str(value).strip()
    lowered = raw.lower()

    if lowered in mapping:
        return mapping[lowered]
    if "@" in raw:
        return raw
    return raw.title()


def build_match_summary(
    input_csv: Path | str,
    name_map_xlsx: Path | str | None = None,
) -> pd.DataFrame:
    """Load point-level data and collapse it to one row per match slice."""
    input_path = Path(input_csv)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    df = pd.read_csv(input_path, low_memory=False)
    required_base_columns = ["matchId", "player", "opp", "date", "finalScore"]
    for column in required_base_columns:
        if column not in df.columns:
            raise ValueError(f"Missing required column: {column}")

    mapping = _load_name_mapping(Path(name_map_xlsx) if name_map_xlsx else None)
    df["player"] = df["player"].apply(lambda value: _clean_name(value, mapping))
    df["opp"] = df["opp"].apply(lambda value: _clean_name(value, mapping))

    if "opp_team" not in df.columns:
        df["opp_team"] = ""
    df["opp_team"] = df["opp_team"].fillna("").astype(str).str.strip()

    missing_indicators = [column for column in INDICATOR_COLUMNS if column not in df.columns]
    if missing_indicators:
        validate_required_columns(df)
        df = add_rawpoints_columns(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["Match Date"] = df["date"].dt.date
    df["Match Year"] = df["date"].dt.year
    df["Match Month Name"] = df["date"].dt.strftime("%B")

    group_columns = [
        "matchId",
        "player",
        "opp",
        "opp_team",
        "Match Date",
        "Match Year",
        "Match Month Name",
    ]
    aggregation = {column: "sum" for column in INDICATOR_COLUMNS}
    aggregation["finalScore"] = "first"

    grouped = df.groupby(group_columns, dropna=False, as_index=False).agg(aggregation)
    parsed_score = grouped["finalScore"].apply(parse_final_score)
    parsed_df = pd.DataFrame(list(parsed_score))

    grouped = pd.concat([grouped.drop(columns=["finalScore"]), parsed_df], axis=1)
    grouped["Match Result"] = grouped.apply(
        lambda row: "W" if row["Sets Won"] > row["Sets Lost"] else "L",
        axis=1,
    )
    grouped["Match Key"] = grouped["matchId"].astype(str) + grouped["player"].astype(str)
    return grouped
