# Roast Profile Overlay

A lightweight localhost web app for comparing multiple Artisan `.alog` coffee-roast profiles on a shared chart. It overlays bean temperature, exhaust temperature, rate of rise, heater output, and air output; marks roast milestones; and summarizes batch weights, weight loss, Charge/Drop temperatures, and roast-phase timing.

## Requirements

- Python 3.9 or newer
- A modern browser

There are no third-party runtime dependencies.

## Install and run from any folder

From the project checkout, install without `sudo` in a virtual environment. On macOS, upgrade the environment's pip first: the pip bundled with Python 3.9 may build an unusable `UNKNOWN` package from this project's `pyproject.toml`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Keep the environment active to run `prophile` from another folder. Alternatively, use the full path to `.venv/bin/prophile`.

Then change to **any folder containing `.alog` files** and run:

```bash
cd /path/to/roasts
prophile
```

Open `http://127.0.0.1:8000` in a browser. Use `prophile --port 8080` for another port; stop with `Ctrl+C`. The command reads `.alog` files directly in the directory where it was launched (non-recursive); it does not modify them. Only this local browser can access the server. For development without installing, run `python3 /path/to/prophile/server.py` from the roast directory.

## Use

1. On opening the page, profiles in the launch directory appear in the **Beans & batches** sidebar, grouped solely by filename (date prefix and trailing batch number/`glitch` suffix removed; Artisan metadata is ignored). **Nothing is selected initially**, so the grid and chart are empty.
2. Tick a batch, tick a bean group, or use **Select all** to add profiles to both the grid and chart. Untick them or use **Select none** to remove them from the comparison without deleting them from the sidebar. Use the **From** and **To** date range inputs (between the action buttons and batch checkboxes) to filter profiles by roast date: adjusting the date range selects all roasts falling within the specified bounds, while selection actions automatically synchronize the date range inputs.
3. Use **Choose .alog files** or drop files anywhere on the page to add more profiles (these are selected on import). Use × in the grid to remove a batch from the comparison (it remains in the sidebar); use × in the sidebar to remove it entirely, or **Clear all** to remove everything from the current page. Reload to rediscover files in the launch directory.
4. Hover over a selected grid row to emphasize its chart curves, or hover near a curve/event pin to highlight its corresponding grid row. Rows with notes show the roast and cupping notes on hover/focus.
5. Use chart checkboxes to show or hide Bean temp, Exhaust temp, RoR, Heat, Air, or Event pins. Hover over the chart for values at an elapsed time.

The chart automatically fits selected profiles. Profiles are aligned to Charge at `00:00` and ordinarily end at Drop. Files with missing events remain chartable and show unavailable phase values where needed.

## Sample profiles

Three `.alog` examples are bundled in `sample_profiles/`:

- `26-09-12_Baarbara_Washed_AA_batch_3.alog`
- `26-09-12_Baarbara_Washed_AA_batch_4.alog`
- `26-09-12_Baarbara_Washed_AA_batch_5.alog`

Run `prophile` from `sample_profiles/`, then select the bean group to try the multi-profile table and overlay chart. The full private development profile collection remains excluded from Git.

## Features

- Launch-directory `.alog` discovery, bean-grouped filters, multi-file selection and drag-and-drop
- Date range selector controls with From and To date bounds and automatic selection synchronization
- Coordinated, muted primary and secondary colors applied directly to profile names and their chart curves
- Distinct line styles for BT, ET, RoR, heater, and air
- Dynamic RoR scale from 0 to the maximum RoR across enabled profiles
- Far-left `AIR / HEAT %` control axis with uncluttered numeric tick labels
- Taller responsive chart bounded to the available viewport
- Charge, Turning Point, Dry End, First Crack Start, and Drop pins
- Per-profile and per-measurement visibility controls
- Green batch weight and combined final weight/weight loss in the format `105.0 g (-16.0%)`
- Table-row tooltips for optional roast notes and cupping notes
- Charge and Drop bean temperatures in the profile table
- Drying, Browning, and Development time/percentage table, denoted by mid-tone green, mid-tone brown, and dark brown
- Crosshair tooltips and responsive Canvas rendering
- Partial support for incomplete profiles through non-blocking warnings; non-fatal warnings are suppressed for `*glitch.alog` (invalid files still show errors)
- Safe parsing with Python `ast.literal_eval`

## Supported `.alog` fields

The parser uses these Artisan fields:

| Data | Field |
|---|---|
| Unit | `mode` |
| Profile metadata | `title` |
| Roast and cupping notes | `roastingnotes`, `cuppingnotes` |
| Green/final batch weight and unit | `weight` |
| Computed weight fallbacks | `computed.weightin`, `computed.weightout`, `computed.weight_loss` |
| Main timestamps | `timex` |
| Exhaust/environment temperature | `temp1` |
| Bean temperature | `temp2` |
| Milestone indices | `timeindex` |
| Computed milestone details | `computed` |
| Extra device declaration | `devices`, `extradevices` |
| Heater/fan timestamps | `extratimex` |
| Heater output | `extratemp1` |
| Air/fan output | `extratemp2` |

The `weight` field is read as green weight, final roasted weight, and source unit. Weight loss is calculated as `(green weight - final weight) / green weight × 100`; computed weight fields are used as fallbacks when needed. The table combines final weight and loss as `<final weight> (-<weight loss>%)`, with values displayed to one decimal place. Unavailable values appear as an em dash.

RoR is calculated from BT with a centered 30-second least-squares window. Phase timing is derived from event boundaries:

- Drying: Charge to Dry End
- Browning: Dry End to First Crack Start
- Development: First Crack Start to Drop
- Percentage: phase duration divided by Charge-to-Drop time

Charge and Drop table temperatures use the corresponding normalized event BT values and are shown to one decimal place in °C; unavailable values appear as an em dash. Fahrenheit profiles are normalized to Celsius. Heater/air extraction looks for an extra device labeled `Heater/Fan` and falls back to the first extra channel for compatibility with the supplied Kaleido logs.

## Test

Run the standard-library test suite from the project root:

```bash
python3 -m unittest discover -s tests -v
```

Tests parse all three bundled sample profiles and use synthetic fixtures covering representative, incomplete, mismatched, unsafe, and Fahrenheit inputs, filename grouping and glitch warnings. Server tests exercise launch-directory discovery and static delivery. The full private roast-profile collection is not required by the test suite.
