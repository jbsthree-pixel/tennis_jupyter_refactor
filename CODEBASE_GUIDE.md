# Codebase Guide

This repository contains a local tennis analytics workflow for NC State women's
tennis. It started as a notebook-style analysis and has been refactored into a
small reusable Python package plus Streamlit browser apps.

The project is meant to support three ways of working:

- a local Streamlit app for interactive review
- a command-line run that creates CSV and Excel outputs
- notebook helpers for exploratory analysis

There is also an experimental "wide" Streamlit app for a newer browser export
format.

## Quick Start

Install dependencies from the repository root:

```powershell
py -3 -m pip install -r requirements.txt
```

Run the main Streamlit app:

```powershell
py -3 -m streamlit run streamlit_app.py
```

Or run it through the launcher:

```powershell
py -3 src/launch_app.py
```

Run the command-line summary export:

```powershell
$env:PYTHONPATH='src'
py -3 src/main.py
```

Run the experimental wide-data app:

```powershell
py -3 src/launch_app_wide.py
```

## Repository Layout

```text
.
|-- README.md
|-- CODEBASE_GUIDE.md
|-- requirements.txt
|-- streamlit_app.py
|-- streamlit_app_wide.py
|-- assets/
|-- data/
|   `-- input/
|-- notebooks/
|-- output/
`-- src/
    |-- launch_app.py
    |-- launch_app_wide.py
    |-- main.py
    `-- tennis_jupyter/
        |-- analytics.py
        |-- constants.py
        |-- notebook.py
        |-- reporting.py
        |-- shared.py
        |-- wide_analytics.py
        |-- wide_loader.py
        `-- pipeline/
            |-- rawpoints.py
            `-- summary.py
```

Important files:

- `streamlit_app.py` is the main interactive app for point-level match data.
- `streamlit_app_wide.py` is an experimental app for `browser_match_stats_wide`
  style exports.
- `src/main.py` is the command-line entrypoint.
- `src/tennis_jupyter/` is the reusable package used by the apps, CLI, and
  notebook.
- `data/input/` holds local source files.
- `output/` holds generated reports and logs. It is ignored by Git.
- `assets/` contains NC State images used by the Streamlit app banner.

## Data Inputs

The main app currently looks for:

- `data/input/team_singles_stats.csv.gz`
- fallback: `data/input/team_singles_stats.csv`

The CLI default documented in `README.md` is:

- `data/input/StatsReport_TeamNames.csv`

The wide app looks for:

- `data/input/browser_match_stats_wide.csv`

The main app also reads benchmark data when present:

- `data/input/Tour Data 2025.xlsx`

The important distinction is that the main pipeline expects point-level rows,
while the wide pipeline expects one browser-exported match row with separate
`player_0` and `player_1` metric columns.

## Main Data Flow

The stable path is:

1. Load a point-level CSV.
2. Validate that required point columns exist.
3. Add engineered indicator columns if the source file does not already have
   them.
4. Group point rows into match-level rows.
5. Add date, season, result, score, serve, return, rally, and pressure metrics.
6. Feed the summary into Streamlit, notebook helpers, or Excel export.

In code, the core flow is:

```text
src/main.py
  -> tennis_jupyter.notebook.load_match_summary()
    -> tennis_jupyter.pipeline.summary.build_match_summary()
      -> tennis_jupyter.pipeline.rawpoints.validate_required_columns()
      -> tennis_jupyter.pipeline.rawpoints.add_rawpoints_columns()
  -> tennis_jupyter.notebook.export_outputs()
    -> tennis_jupyter.reporting.write_excel_report()
```

The Streamlit app follows the same summary path but adds cached loaders,
filters, charts, benchmark overlays, source-row editing, and downloads.

## Core Package Modules

### `tennis_jupyter.pipeline.rawpoints`

This module converts raw point rows into indicator columns.

Required raw columns:

- `server`
- `returner`
- `pointWonBy`
- `firstServeIn`
- `outcome`
- `returnInPlay`
- `breakPoint`
- `endingPlayer`
- `rallyLength`

The key function is `add_rawpoints_columns(df)`. It adds countable integer
columns such as `service_point`, `return_point`, `first_serve_in`,
`double_fault`, `ace`, `break_point_won`, and rally-length win buckets.

These columns are deliberately simple 0/1 indicators, which makes later
aggregation predictable: match-level metrics are mostly sums of these fields.

### `tennis_jupyter.pipeline.summary`

This module builds the match-level dataset.

Important behavior:

- Requires `matchId`, `player`, `opp`, `date`, and `finalScore`.
- Optionally applies a name mapping workbook with `RawName`, `CleanName`, and
  `Active` columns.
- Derives `opp_team` from `matchName` when the source does not provide one.
- Parses `finalScore` into `Games Won`, `Games Lost`, `Sets Won`, and
  `Sets Lost`.
- Creates `Match Result` from sets won versus sets lost.
- Groups by match, player, opponent, opponent team, date, year, and month.

If a source CSV already contains the indicator columns, the module uses them.
If not, it validates the raw point columns and derives the indicators.

### `tennis_jupyter.analytics`

This module contains reusable calculations for the main app.

The most important functions are:

- `add_match_rate_columns()` for percentage columns such as first-serve-in rate
  and return-win rate.
- `filter_matches()` for player, year, month, opponent team, opponent school,
  and season filters.
- `with_season_columns()` for August-to-June tennis season labels.
- `available_filter_values()` for Streamlit selector options.
- `build_pivot_summary()` for Excel-style player and season rollups.
- `build_player_comparison_summary()` for side-by-side player comparison.
- `build_serve_return_match_stats()` for the detailed serve/return table.
- `build_game_level_summary()` for one row per game, used by score-state and
  modeling views.
- `load_source_review()` and `save_source_review_changes()` for grouped source
  row editing from the app.

This is the best place to add reusable app calculations. If a calculation is
used in both Streamlit and notebooks, it belongs here instead of directly inside
`streamlit_app.py`.

### `tennis_jupyter.reporting`

This module writes the Excel report.

It builds:

- raw match summary sheet
- year/result pivot
- year games/sets pivot
- player overview pivot
- serve/return pivot
- chart sheet

The report uses `pandas.ExcelWriter` with `openpyxl`, then formats tables,
percentage columns, widths, and charts.

### `tennis_jupyter.notebook`

This module provides notebook-friendly wrappers:

- `load_match_summary()`
- `plot_serve_trends()`
- `export_outputs()`
- match-watch URL formatting helpers

The CLI imports from this module because it exposes a compact public surface.

### `tennis_jupyter.shared`

Small shared helpers live here:

- `project_root()`
- `data_path()`
- `output_path()`
- `safe_ratio()`

Use `safe_ratio()` instead of direct division for percentage metrics. It keeps
zero-denominator cases numeric and avoids scattered divide-by-zero handling.

### `tennis_jupyter.constants`

This module centralizes:

- month ordering
- chart colors
- serve trend metric definitions
- serve/return table column definitions
- raw-field formula descriptions

If a label, color, or table column definition is shared across app and helpers,
it should usually move here.

## Main Streamlit App

`streamlit_app.py` is large because it contains the full UI and many chart
builders. It imports reusable calculations from `tennis_jupyter.analytics`, but
much of the visualization and modeling code still lives inline.

High-level app behavior:

1. Configure page and CSS.
2. Load the default point-level CSV.
3. Build cached match-level and game-level summaries.
4. Optionally load the tour benchmark workbook.
5. Create sidebar filters for players, opponent team, season, win/loss split,
   and benchmark lines.
6. Build filtered match and game dataframes.
7. Render headline metrics, downloads, and tabbed analysis views.

Major tabs include:

- Overview
- Raw Matches
- Serve / Return Match Stats
- Serve Stats Trend
- Serve Efficiency Funnel
- Serve Win Probability
- Rally Length Wins
- Rally Bins
- Pressure Bins
- Score-State Performance
- Serve / Return Score-State Rates

The app uses:

- Streamlit for UI
- Plotly for charts
- scikit-learn logistic regression for probability-style modeling
- pandas for transformations

Because the file is very large, a good improvement path is to move pure
calculation functions into `tennis_jupyter.analytics` and chart construction
functions into a dedicated module such as `tennis_jupyter.charts`.

## Wide Data Path

The wide path is experimental and separate from the main point-level pipeline.

`tennis_jupyter.wide_loader`:

- loads `browser_match_stats_wide.csv`
- normalizes each wide row into a `player_0` perspective
- maps wide metric columns into display names such as `Aces`,
  `1st Serve In %`, and `Service Games Won %`

`tennis_jupyter.wide_analytics`:

- adds date and season labels
- builds filter values
- filters normalized wide rows
- summarizes key metrics
- builds player comparison and pivot summaries

`streamlit_app_wide.py`:

- renders a Streamlit interface for the normalized wide data
- includes raw wide rows, schema notes, serve trend charts, funnels, rally
  profile views, and downloads

One important limitation: `normalize_browser_match_stats_wide()` currently
projects only the `player_0` perspective. If users need both players represented
as rows, this is one of the first places to improve.

## CLI Entrypoint

`src/main.py` is intentionally small.

It accepts:

- `--input-csv`
- `--name-map-xlsx`
- `--output-dir`

It prints high-level insights and writes:

- `output/Tennis_MatchSummary.csv`
- `output/Tennis_MatchSummary_Report.xlsx`

This is a good smoke-test path when changing pipeline code because it exercises
loading, summarizing, and Excel export without needing the Streamlit UI.

## Notebook Workflow

The notebook in `notebooks/tennis_analysis.ipynb` should use the public helpers
from `tennis_jupyter.notebook` and `tennis_jupyter.analytics`.

For notebook work, set `PYTHONPATH` to `src` or start Jupyter from an environment
where the package can be imported.

Typical notebook flow:

```python
from tennis_jupyter.notebook import load_match_summary, plot_serve_trends

df = load_match_summary("data/input/StatsReport_TeamNames.csv")
plot_serve_trends(df)
```

## Generated Outputs

Generated artifacts belong in `output/`.

The `.gitignore` excludes:

- `output/`
- `__pycache__/`
- `*.py[cod]`
- `.ipynb_checkpoints/`

If you add new generated exports, logs, or local-only analysis files, keep them
under `output/` or update `.gitignore` accordingly.

## How To Make Changes Safely

For pipeline changes:

1. Start with `src/tennis_jupyter/pipeline/rawpoints.py` or
   `src/tennis_jupyter/pipeline/summary.py`.
2. Keep indicator columns as numeric 0/1 values when possible.
3. Use `safe_ratio()` for derived rates.
4. Run the CLI after changes.
5. Open the Streamlit app and verify the affected tabs.

For app calculations:

1. Put reusable dataframe transformations in `analytics.py`.
2. Keep Streamlit-specific rendering in `streamlit_app.py`.
3. Prefer small pure functions that accept and return dataframes.
4. Avoid duplicating the same metric formula in multiple places.

For chart changes:

1. Check whether the chart uses match-level or game-level data.
2. Check whether filters should apply before or after aggregation.
3. Keep chart keys stable by including active filter state.
4. Use the shared color constants when possible.

For wide-data changes:

1. Update `WIDE_METRIC_SPECS` in `wide_loader.py` when the input schema changes.
2. Add normalized columns there first.
3. Add summaries in `wide_analytics.py`.
4. Render them in `streamlit_app_wide.py`.

## Current Improvement Opportunities

The most valuable next improvements are:

- Add automated tests for `parse_final_score()`, `add_rawpoints_columns()`,
  `build_match_summary()`, and the filtering helpers.
- Split `streamlit_app.py` into smaller modules for chart builders, modeling
  helpers, benchmark logic, and UI rendering.
- Consolidate duplicated helpers between `analytics.py`, `wide_analytics.py`,
  `streamlit_app.py`, and `streamlit_app_wide.py`.
- Make the default input file behavior consistent between `README.md`,
  `src/main.py`, and `streamlit_app.py`.
- Decide whether the wide-data app should emit one row per player per match
  instead of only the `player_0` perspective.
- Add a small fixture dataset for tests so future contributors can validate
  behavior without relying on private/local data files.
- Consider packaging the source directory with `pyproject.toml` so callers do
  not need to set `PYTHONPATH` manually.

## Mental Model For New Contributors

Think of the codebase in layers:

```text
raw tennis export
  -> point/game/match transformations
  -> reusable analytics summaries
  -> reports, notebook helpers, and Streamlit UI
```

The lower layers should know nothing about Streamlit. The Streamlit files should
orchestrate user inputs, caching, downloads, and chart rendering. When improving
the project, try to move durable tennis/statistics logic downward into the
package and leave the app files focused on presentation.

