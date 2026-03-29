"""Shared constants used across the browser app and notebook helpers."""

from __future__ import annotations


MONTH_ORDER = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

COLORBLIND_SAFE_CHART_COLORS = {
    "accent_red": "#CC0000",
    "accent_red_dark": "#990000",
    "accent_gray": "#6E6E6E",
    "accent_black": "#1F1F1F",
    "accent_rose": "#C75C5C",
    "accent_taupe": "#9A8F87",
    "surface_neutral": "#F7F4F2",
}

COLORBLIND_SAFE_DIVERGING_SCALE = [
    [0.0, "#6E6E6E"],
    [0.5, "#F7F4F2"],
    [1.0, "#CC0000"],
]

COLORBLIND_SAFE_SEQUENTIAL_SCALE = [
    [0.0, "#F7F4F2"],
    [0.35, "#E0C8C8"],
    [0.7, "#C75C5C"],
    [1.0, "#990000"],
]


SERVE_TREND_METRICS = [
    ("1st Serve In %", "first_serve_in", "first_serve_attempt", COLORBLIND_SAFE_CHART_COLORS["accent_red"]),
    ("1st Serve Won %", "first_serve_won", "first_serve_in", COLORBLIND_SAFE_CHART_COLORS["accent_red_dark"]),
    ("2nd Serve In %", "second_serve_in", "second_serve_attempt", COLORBLIND_SAFE_CHART_COLORS["accent_rose"]),
    ("2nd Serve Won %", "second_serve_won", "second_serve_attempt", COLORBLIND_SAFE_CHART_COLORS["accent_gray"]),
    ("Double Fault %", "double_fault", "second_serve_attempt", COLORBLIND_SAFE_CHART_COLORS["accent_black"]),
]


PIVOT_ACE_COLUMN_DEFS = [
    ("Year", "Season"),
    ("Opp Team", "Opp Team"),
    ("Match Date", "Match Date"),
    ("Match ID", "Match ID"),
    ("Aces", "Aces"),
    ("Ace %", "Ace %"),
    ("Double Faults", "Double Faults"),
    ("DF %", "DF %"),
    ("+/-", "+/-"),
    ("1SNR", "1SNR"),
    ("1SNR %", "1SNR %"),
    ("First Serves", "First Serves"),
    ("First Serves In", "First Serves In"),
    ("First Serve %", "First Serves In %"),
    ("First Serve Won", "First Serve Won"),
    ("1st Serve Win %", "First Serves Won %"),
    ("Second Serves", "Second Serves"),
    ("Second Serves In", "Second Serves In"),
    ("Second Serve %", "Second Serves In %"),
    ("Second Serve Won", "Second Serve Won"),
    ("2nd Serve Win %", "Second Serves Won %"),
    ("First Serve Returns", "First Serves Return"),
    ("First Serve Returns In", "First Serves Return In"),
    ("First Serve Returns %", "First Serves Returns %"),
    ("First Serve Returns Won", "First Serves Return Won"),
    ("First Serve Returns Won %", "First Serves Return Won %"),
    ("Second Serve Returns", "Second Serves Return"),
    ("Second Serve Returns In", "Second Serves Return In"),
    ("Second Serve Returns %", "Second Serve Returns In %"),
    ("Second Serve Returns Won", "Second Serve Returns Won"),
    ("Second Serve Returns Won %", "Second Serve Returns Won %"),
    ("Opp Double Faults", "Opp Double Faults"),
]


RAW_FIELD_FORMULAS = {
    "matchId": "Source match identifier grouped into match-level rows.",
    "player": "Player name after optional cleaning and name mapping.",
    "opp": "Opponent name after optional cleaning and name mapping.",
    "opp_team": "Opponent team from source data, blank when not listed.",
    "Match Date": "Parsed from the source date field.",
    "Match Year": "Year extracted from Match Date.",
    "Match Month Name": "Month name extracted from Match Date.",
    "service_point": "Count of points where server == 0.",
    "return_point": "Count of points where returner == 0.",
    "point_won": "Count of points where pointWonBy == 0.",
    "first_serve_attempt": "Count of service points.",
    "first_serve_miss": "Count where server == 0 and firstServeIn is false.",
    "second_serve_attempt": "Count of first-serve misses.",
    "double_fault": "Count where first serve missed and outcome == Fault.",
    "first_serve_in": "Count where server == 0 and firstServeIn is true.",
    "first_serve_won": "Count where first serve was in and the point was won.",
    "second_serve_in": "Count where second serve landed in play.",
    "second_serve_won": "Count where second serve landed in play and point was won.",
    "first_serve_return_opportunity": "Count of returns faced against opponent first serves in.",
    "first_serve_return_in": "Count where opponent first serve was returned in play.",
    "first_serve_return_won": "Count where opponent first serve was won on return.",
    "first_serve_not_returned": "Count where first serve landed in and was not returned.",
    "second_serve_return_opportunity": "Count of returns faced against opponent second serves.",
    "second_serve_return_in": "Count where opponent second serve was returned in play.",
    "second_serve_return_won": "Count where opponent second serve was won on return.",
    "opp_double_fault": "Count of opponent double faults while returning.",
    "winner": "Count where outcome == Winner and endingPlayer == 0.",
    "ace": "Count where outcome == Ace, server == 0, and point was won.",
    "unforced_error": "Count where outcome == UnforcedError and endingPlayer == 0.",
    "break_point_total": "Count of break points earned while returning.",
    "break_point_won": "Count of break points converted while returning.",
    "break_point_faced": "Count of break points faced while serving.",
    "break_point_saved": "Count of break points saved while serving.",
    "short_rally_won": "Count of points won where rallyLength <= 4.",
    "medium_rally_won": "Count of points won where rallyLength is between 5 and 8.",
    "long_rally_won": "Count of points won where rallyLength >= 9.",
    "Games Won": "Games won across all parsed set scores.",
    "Games Lost": "Games lost across all parsed set scores.",
    "Sets Won": "Sets where player games exceeded opponent games.",
    "Sets Lost": "Sets where opponent games exceeded player games.",
    "Match Result": "W when Sets Won > Sets Lost, otherwise L.",
    "Match Key": "Concatenation of matchId and player.",
}
