"""Generate engineered point-level indicator columns for tennis analytics."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "server",
    "returner",
    "pointWonBy",
    "firstServeIn",
    "outcome",
    "returnInPlay",
    "breakPoint",
    "endingPlayer",
    "rallyLength",
]


def load_concat_csv(folder: Path) -> pd.DataFrame:
    """Load and concatenate CSV files from a folder with column validation."""
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")

    files = sorted([*folder.glob("*.csv"), *folder.glob("*.csv.gz")])
    if not files:
        raise FileNotFoundError(f"No CSV or CSV.GZ files found in: {folder}")

    dataframes = [pd.read_csv(file_path) for file_path in files]
    base_columns = list(dataframes[0].columns)
    mismatches: list[str] = []

    for dataframe, file_path in zip(dataframes, files, strict=True):
        if list(dataframe.columns) != base_columns:
            mismatches.append(file_path.name)

    if mismatches:
        raise ValueError(f"Column mismatch across files: {mismatches}")

    return pd.concat(dataframes, ignore_index=True)


def validate_required_columns(df: pd.DataFrame) -> None:
    """Validate that the raw export contains the columns needed to derive stats."""
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def add_rawpoints_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered indicator columns used by the summary pipeline."""
    is_server = df["server"] == 0
    is_returner = df["returner"] == 0
    point_won = df["pointWonBy"] == 0

    first_serve_in = df["firstServeIn"].fillna(False) == True  # noqa: E712
    first_serve_miss = is_server & (~first_serve_in)

    return_in_play = df["returnInPlay"].fillna(False) == True  # noqa: E712
    break_point = df["breakPoint"].fillna(False) == True  # noqa: E712

    outcome = df["outcome"].fillna("")
    ending_player = df["endingPlayer"]
    rally_length = df["rallyLength"]

    df = df.copy()

    # Reuse the same boolean branches so every derived metric is consistent.
    df["service_point"] = is_server.astype("int64")
    df["return_point"] = is_returner.astype("int64")
    df["point_won"] = point_won.astype("int64")

    df["first_serve_attempt"] = is_server.astype("int64")
    df["first_serve_miss"] = first_serve_miss.astype("int64")
    df["second_serve_attempt"] = first_serve_miss.astype("int64")
    df["double_fault"] = (first_serve_miss & (outcome == "Fault")).astype("int64")

    df["first_serve_in"] = (is_server & first_serve_in).astype("int64")
    df["first_serve_won"] = (is_server & first_serve_in & point_won).astype("int64")

    df["second_serve_in"] = (first_serve_miss & (outcome != "Fault")).astype("int64")
    df["second_serve_won"] = (
        first_serve_miss & (outcome != "Fault") & point_won
    ).astype("int64")

    df["first_serve_return_opportunity"] = (is_returner & first_serve_in).astype("int64")
    df["first_serve_return_in"] = (
        is_returner & first_serve_in & return_in_play
    ).astype("int64")
    df["first_serve_return_won"] = (
        is_returner & first_serve_in & point_won
    ).astype("int64")
    df["first_serve_not_returned"] = (
        is_server & first_serve_in & (~return_in_play)
    ).astype("int64")

    df["second_serve_return_opportunity"] = (
        is_returner & (~first_serve_in) & (outcome != "Fault")
    ).astype("int64")
    df["second_serve_return_in"] = (
        is_returner & (~first_serve_in) & (outcome != "Fault") & return_in_play
    ).astype("int64")
    df["second_serve_return_won"] = (
        is_returner & (~first_serve_in) & (outcome != "Fault") & point_won
    ).astype("int64")
    df["opp_double_fault"] = (
        is_returner & (~first_serve_in) & (outcome == "Fault")
    ).astype("int64")

    df["winner"] = ((outcome == "Winner") & (ending_player == 0)).astype("int64")
    df["ace"] = ((outcome == "Ace") & is_server & point_won).astype("int64")
    df["unforced_error"] = (
        (outcome == "UnforcedError") & (ending_player == 0)
    ).astype("int64")
    df["forced_error"] = ((outcome == "ForcedError") & (ending_player == 0)).astype("int64")
    df["opp_ace"] = ((outcome == "Ace") & (df["server"] == 1) & (~point_won)).astype("int64")
    df["opp_unforced_error"] = (
        (outcome == "UnforcedError") & (ending_player == 2)
    ).astype("int64")
    df["opp_forced_error"] = ((outcome == "ForcedError") & (ending_player == 2)).astype("int64")
    df["total_point"] = (is_server | is_returner).astype("int64")

    df["break_point_total"] = (break_point & is_returner).astype("int64")
    df["break_point_won"] = (break_point & is_returner & point_won).astype("int64")
    df["break_point_faced"] = (break_point & is_server).astype("int64")
    df["break_point_saved"] = (break_point & is_server & point_won).astype("int64")

    df["short_rally_won"] = ((rally_length <= 4) & point_won).astype("int64")
    df["medium_rally_won"] = (
        (rally_length >= 5) & (rally_length <= 8) & point_won
    ).astype("int64")
    df["long_rally_won"] = ((rally_length >= 9) & point_won).astype("int64")

    return df


def main() -> int:
    """Allow the raw-point transformation to be run directly from the command line."""
    try:
        df = load_concat_csv(Path("./data/input"))
        validate_required_columns(df)
        df_out = add_rawpoints_columns(df)
        out_path = Path("output/Tennis_RawPoints.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df_out.to_csv(out_path, index=False)
        print(f"Wrote {len(df_out):,} rows to {out_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
