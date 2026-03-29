# Tennis Jupyter Refactor

This project is an isolated, cross-platform version of the tennis summary workflow.
It is designed to work in a browser through a local Streamlit app and still supports
Jupyter Notebook or a simple Python command-line run.

## What This Project Does

- Reads a local tennis CSV file from `data/input/`
- Builds a match-level summary dataset
- Writes output files to `output/`
- Supports a browser-based interactive app on Windows and macOS
- Supports interactive analysis in a Jupyter notebook

## Project Structure

- `src/` = Python source code
- `src/main.py` = command-line entrypoint
- `src/tennis_jupyter/` = reusable pipeline and notebook helpers
- `data/input/` = local input CSV files
- `output/` = generated CSV and Excel outputs
- `streamlit_app.py` = browser app entrypoint
- `notebooks/` = Jupyter notebooks

## Requirements

- Python 3
- Local browser such as Edge, Chrome, or Safari

## Install Dependencies

From the project root, run:

```powershell
py -3 -m pip install -r requirements.txt
```

If `py` does not work on your machine, use:

```powershell
python3 -m pip install -r requirements.txt
```

## Run The Browser App

This is the recommended way to use the project because it restores much more of
the original app-style experience in a cross-platform way.

From the project root, run:

```powershell
py -3 -m streamlit run streamlit_app.py
```

Or use the Python launcher:

```powershell
py -3 src/launch_app.py
```

What you get in the browser:

- filters for player, year, month, opponent team, and season
- raw match table
- serve / return match stats table
- multiple interactive charts
- filtered CSV and Excel downloads
- source row editing and save-back to the local CSV

## Deploy With Streamlit Community Cloud

This repository is set up so `streamlit_app.py` can be used as the app entrypoint.

1. Push this folder to a GitHub repository.
2. In Streamlit Community Cloud, create a new app from that repository.
3. Set the main file path to `streamlit_app.py`.
4. Leave the Python dependencies pointed at `requirements.txt`.
5. Deploy.

The default dataset is already referenced from:

`data/input/StatsReport_TeamNames.csv`

Important hosted-app note:

- downloads work normally on Streamlit Community Cloud
- the `Source Row Edits` tab writes changes back to the local CSV file on disk
- on hosted Streamlit environments, filesystem writes are not durable application storage, so those edits should be treated as temporary unless you add persistent storage or a sync workflow

## Run From The Command Line

This project supports a normal Python run from the repository root:

```powershell
$env:PYTHONPATH='src'
py -3 src/main.py
```

This will:

- read `data/input/StatsReport_TeamNames.csv`
- print key insights to the console
- write output files into `output/`

## Start Jupyter Notebook

From the project root, run:

```powershell
py -3 -m notebook
```

Jupyter should open in your browser automatically. If it does not, copy the local
URL shown in the terminal into your browser.

Then:

1. Open the `notebooks/` folder.
2. Open `tennis_analysis.ipynb`.
3. Run each cell with `Shift+Enter`.

## Optional: Use JupyterLab Instead

JupyterLab is a more modern interface with tabs, a file browser, and a built-in
workspace layout.

Install it with:

```powershell
py -3 -m pip install jupyterlab
```

Start it with:

```powershell
py -3 -m jupyter lab
```

## Input File

The default input file is:

`data/input/StatsReport_TeamNames.csv`

If you want to use a different CSV, run:

```powershell
$env:PYTHONPATH='src'
py -3 src/main.py --input-csv "C:\path\to\your_file.csv"
```

## Output Files

Successful runs create:

- `output/Tennis_MatchSummary.csv`
- `output/Tennis_MatchSummary_Report.xlsx`

## Beginner Notes For Jupyter

- A notebook is made of cells.
- You type Python code into a cell.
- Press `Shift+Enter` to run the current cell.
- Output appears directly below the cell.
- You can rerun cells as often as you want.

## Cross-Platform Notes

This version is intended to work on both Windows and macOS because it avoids the
original Tkinter desktop packaging dependency and uses:

- plain Python modules
- pandas-based data processing
- browser-based local app and notebook workflows

On macOS, replace `py -3` with `python3` if needed.

## Current Verified Run

The project has already been tested successfully in this directory using the local
CSV in `data/input/`.
