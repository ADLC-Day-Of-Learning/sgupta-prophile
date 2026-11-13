# Roast Profile Overlay — Design Document

## 1. Goal

Build a lightweight, installable, local-only web application that discovers Artisan `.alog` files in the launch directory and compares selected roasts in one interactive overlay chart.

The chart will support:

- Bean temperature (BT)
- Exhaust/environment temperature (ET)
- Bean-temperature rate of rise (RoR)
- Heater output
- Air/fan output
- Event pins for Charge, Turning Point, Dry End, First Crack Start, and Drop
- Checkboxes to independently show or hide each curve type and event pins
- A bean-grouped selection sidebar and a table of selected profiles with green batch weight, combined final-weight/weight-loss value, Charge and Drop bean temperatures, and Drying, Browning, and Development phase breakdowns

## 2. Initial dataset findings

### 2.1 Collection

- The full private development dataset contained 34 Artisan `.alog` files and is excluded from the Git repository.
- Three recent representative profiles are intentionally included under `sample_profiles/` for evaluation and manual comparison: `26-09-12_Baarbara_Washed_AA_batch_3.alog`, `26-09-12_Baarbara_Washed_AA_batch_4.alog`, and `26-09-12_Baarbara_Washed_AA_batch_5.alog`.
- Files were Artisan roast logs, primarily written by Artisan 4.0.2.
- All analyzed files could be parsed as Python literals.
- Files were roughly 48–96 KB and contained approximately 342–853 samples each.
- Sampling is generally every 1.5 seconds.
- Temperature mode is Celsius in all inspected profiles (`mode: "C"`).
- Some filenames are explicitly marked `glitch`; one glitch profile has no Dry End, First Crack, or Drop event. Missing data must therefore be handled without failing the whole import.

### 2.2 Relevant `.alog` structure

The `.alog` format in this collection is a Python dictionary representation, not strict JSON. The relevant fields are:

| Purpose | `.alog` field | Notes |
|---|---|---|
| Profile name | `title` | Filename will be the fallback |
| Green/final batch weight | `weight` | `[green weight, final weight, unit]` |
| Roast notes | `roastingnotes` | Optional free text |
| Cupping notes | `cuppingnotes` | Optional free text |
| Units | `mode` | `C` in the supplied set |
| Main timestamps | `timex` | Seconds from recording start |
| Exhaust/environment temperature | `temp1` | Artisan ET channel |
| Bean temperature | `temp2` | Artisan BT channel |
| Event sample indices | `timeindex` | Artisan event index array |
| Computed event details | `computed` | Includes event times and BT/ET values |
| Extra-device timestamps | `extratimex[0]` | Heater/fan device timeline |
| Heater output | `extratemp1[0]` | 0–100% in these logs |
| Air/fan output | `extratemp2[0]` | 0–100% in these logs |
| Device declaration | `devices` | Includes `+Kaleido Heater/Fan` |

The `computed` dictionary provides:

- `CHARGE_BT`, `CHARGE_ET`
- `TP_time`, `TP_BT`, `TP_ET`
- `DRY_time`, `DRY_BT`, `DRY_ET`
- `FCs_time`, `FCs_BT`, `FCs_ET`
- `DROP_time`, `DROP_BT`, `DROP_ET`

Artisan's `timeindex` order in these files is Charge, Dry End, First Crack Start, First Crack End, Second Crack Start, Second Crack End, Drop, Cool. Turning Point is instead represented by `computed.TP_*`.

### 2.3 Time alignment

The recording can contain pre-charge and post-drop samples. For comparison, each profile will be normalized so that **Charge is time zero**:

- Main and extra-device timestamps: `display time = source time - charge time`
- Curves will be clipped to Charge through Drop when Drop exists.
- If Drop is missing, data will run from Charge to the end of the recording.

This makes roast milestones line up meaningfully across profiles while preserving differing roast durations.

## 3. User experience

### 3.1 Discovery and initial state

The installable `prophile` command can be run from any directory. `GET /api/local-profiles` reads `.alog` files directly in the launch directory (non-recursively); static assets are served from the installed package, not the working directory. Discovered profiles appear in a **Beans & batches** sidebar, with no batches initially selected: both the grid and chart start empty. The file picker accepts multiple `.alog` files, and files can also be dropped anywhere on the page. Imported files are selected immediately.

Groups are derived **only from filenames**: a leading date and trailing `_batch_N`/`_glitch` suffix are removed, underscores become spaces, and case-insensitive names share a group. Artisan `beans`/`title` metadata does not determine the group. A sidebar batch label shows the date, batch number, and optional `glitch` flag without repeating the group name. Unusual filenames fall back to a filename-derived label.

### 3.2 Sidebar and selected-profile grid

The sidebar offers batch and whole-bean checkboxes (including a partial-selection state), **Select all**, **Select none**, a per-batch × to remove a loaded profile entirely, and **Clear all**. Unselected batches remain available in the sidebar. Only selected profiles appear in the grid and chart. On narrow screens, the grid remains horizontally scrollable rather than hiding temperature or phase data; its smaller type and tighter spacing help it fit beside the sidebar.

| Column | Content |
|---|---|
| Profile | Source filename without `.alog`, underscores replaced with spaces; the name uses the profile's chart color |
| Green Weight (Density) | Green-bean batch weight and density formatted as `<weight> (<density>)` |
| Final weight | Final roasted batch weight followed by weight-loss percentage as `<final weight> (-<weight loss>%)` |
| Charge temp | Bean temperature at Charge, displayed to one decimal place in °C |
| Drop temp | Bean temperature at Drop, displayed to one decimal place in °C |
| Drying | Phase duration as `mm:ss` and percentage of total roast time |
| Browning | Phase duration as `mm:ss` and percentage of total roast time |
| Development | Phase duration as `mm:ss` and percentage of total roast time |
| Actions | × removes the batch from the comparison without deleting it from the sidebar |

Example display name: `26-08-14_Baarbara_Washed_AAA_batch_5.alog` becomes `26-08-14 Baarbara Washed AAA batch 5`.

```text
Green Weight (Density)  Final weight       Charge temp  Drop temp  Drying       Browning      Development
125.0 g (750.0 g/L)     105.0 g (-16.0%)  207.6 °C     187.7 °C   03:49 · 41%  03:40 · 39%   01:50 · 20%
```

Weight loss is derived from the Artisan `weight` field and appended in the Final weight cell. Missing values display `—`. Drying, Browning, and Development use mid-tone green, mid-tone brown, and dark brown in the grid. Duplicate imports (filename plus size) are skipped; per-file errors do not block other imports. Hovering or keyboard-focusing a row with roast or cupping notes reveals a labeled notes tooltip. Hovering a grid row emphasizes its chart curves; hovering near a curve or event pin highlights its grid row.

### 3.3 Chart interaction

The chart will provide:

- Hover/crosshair tooltip showing elapsed `mm:ss` and values for visible profiles/curves near the cursor
- A fixed time range that automatically fits all enabled profiles
- Responsive resizing for desktop and tablet-sized screens
- A profile/curve legend that explains both color and line style

## 4. Visual design

### 4.1 Profile color encoding

Each profile receives a distinct color from a coordinated, muted palette built from primary and secondary hues: blue, terracotta red, green, purple, ochre, teal, berry, orange, indigo, olive, cyan-blue, and mauve. The colors are mid-toned for visibility against the warm off-white background while avoiding highly saturated combinations that cause visual dissonance. For selections beyond the base palette, lighter and darker variants are used to retain distinct profile identities. The UI will recommend comparing no more than 6–8 profiles at once for readability.

Color identifies the **profile**. Line treatment identifies the **measurement**:

| Measurement | Style |
|---|---|
| Bean temperature | Solid, strongest stroke |
| Exhaust temperature | Long dash |
| RoR | Short dash/dot |
| Heat | Stepped line |
| Air | Stepped dotted line |

This keeps all curves from one profile visually related while using a harmonious range of primary and secondary colors to distinguish profiles.

### 4.2 Axes

- Bottom: elapsed time from Charge, formatted `mm:ss`
- Left: temperature in the source unit (°C for the supplied profiles)
- Right: RoR in °C/min, fixed at 0 on the bottom and the maximum visible-profile RoR on the top
- Far left: heater/air control scale titled `AIR / HEAT %`; numeric tick labels omit repeated percent symbols

Subtle horizontal grid lines and restrained labels will keep a multi-profile chart readable. The chart uses approximately 68% of the available browser viewport height, capped at 760 px on larger screens and reduced responsively on narrow screens. This is taller than the initial version while preserving space for browser chrome and surrounding controls.

### 4.3 Event pins

Pins will be drawn at event time and BT value. Each pin uses the profile's assigned palette color and a stable abbreviation/shape:

- `CHG` — Charge
- `TP` — Turning Point
- `DE` — Dry End
- `FC` — First Crack Start
- `DROP` — Drop

Hovering a pin will show event name, elapsed time, BT, and ET. Missing events are simply omitted. Event labels will use basic collision avoidance (alternating vertical offsets) to reduce overlap.

### 4.4 Curve visibility controls

These controls are separate from the profile-selection checkboxes in the sidebar. A checkbox group above the chart contains:

- Bean temp
- Exhaust temp
- RoR
- Heat
- Air
- Event pins

Changes apply immediately without reparsing files. At least one measurement may remain visible; event pins are independently optional.

## 5. Data processing

### 5.1 Safe parsing

The local Python server will parse uploads with `ast.literal_eval`, which supports the supplied Python-literal format without executing file contents. It will never use `eval`.

Validation will enforce:

- Top-level value must be a dictionary.
- `timex`, `temp1`, and `temp2` must be arrays.
- Required arrays must have usable numeric samples.
- Parallel arrays are clipped to their shortest valid length.
- Non-numeric and non-finite samples are discarded or represented as gaps.
- Uploads must have an `.alog` filename and remain below a conservative size limit (5 MB).

### 5.2 Normalized API result

The backend will return only fields needed by the browser. The table's profile label will deliberately be derived from `filename`, rather than the internal Artisan `title`, so its naming consistently follows the selected file.

```json
{
  "id": "client-generated-id",
  "filename": "profile.alog",
  "displayName": "profile",
  "title": "Internal Artisan roast title",
  "bean": "Filename-derived bean group",
  "unit": "C",
  "notes": {
    "roast": "Roast operator notes",
    "cupping": "Cupping observations"
  },
  "weights": {
    "green": 125.0,
    "final": 105.0,
    "lossPercent": 16.0,
    "unit": "g"
  },
  "phases": {
    "total": 559.5,
    "drying": {"seconds": 229.5, "percent": 41.0},
    "browning": {"seconds": 220.5, "percent": 39.4},
    "development": {"seconds": 109.5, "percent": 19.6}
  },
  "series": {
    "bt": [[0.0, 194.4]],
    "et": [[0.0, 184.5]],
    "ror": [[0.0, null]],
    "heat": [[0.0, 75.0]],
    "air": [[0.0, 30.0]]
  },
  "events": [
    {"key": "charge", "time": 0.0, "bt": 194.4, "et": 184.5},
    {"key": "drop", "time": 559.5, "bt": 203.1, "et": 198.8}
  ],
  "warnings": []
}
```

The server will not retain uploads after responding. Profiles whose filenames end in `glitch.alog` (case-insensitive) suppress non-fatal parser warnings; invalid files still report errors.

### 5.3 Batch weight extraction and calculation

The structured Artisan `weight` value is interpreted as `[green weight, final roasted weight, unit]`. If a weight is absent there, `computed.weightin` and `computed.weightout` are used as fallbacks. Weight values retain their source unit and are displayed to one decimal place.

```text
weight loss percent = (green weight - final weight) / green weight × 100
```

The calculated percentage is used when both weights are valid. `computed.weight_loss` is the fallback when the percentage cannot be derived. Missing or invalid values display an em dash (`—`) without preventing the profile from loading.

### 5.4 Phase-time and percentage calculation

The phase table follows the standard three-phase roast model documented by Artisan: Drying ends at Dry End/yellow, Browning (also called the Maillard phase) runs from Dry End to First Crack Start, and Development runs from First Crack Start to Drop.

The values will be derived from event times, even though most supplied logs also contain `computed.dryphasetime`, `computed.midphasetime`, and `computed.finishphasetime`. Deriving the values gives consistent behavior and satisfies future logs that omit Artisan's computed summary.

With Charge normalized to time zero:

```text
total roast time = Drop - Charge
Drying time      = Dry End - Charge
Browning time    = First Crack Start - Dry End
Development time = Drop - First Crack Start
phase percent    = phase time / total roast time × 100
```

Percentages will be displayed to the nearest whole percent in the compact table; normalized API values retain one decimal place. Durations will be formatted as `mm:ss`. The three percentages may visually total 99% or 101% due to independent display rounding.

A phase cell displays an em dash (`—`) if either boundary needed for that phase is missing or invalid. Percentages are omitted if Drop is missing because total roast time cannot be established reliably. The profile still remains selectable and chartable.

References used for the phase definitions and calculation:

- [Artisan documentation — Roast Phases](https://artisan-scope.org/docs/phases/)
- [Artisan — Development Time Ratio](https://artisan-roasterscope.blogspot.com/2020/05/displaying-development-time-ratio-in.html)

The percentages are descriptive measurements, not quality targets; the app will not mark any percentage as good or bad.

### 5.5 RoR calculation

The files do not serialize the full RoR curve, so BT RoR will be derived from `temp2`.

To avoid amplifying sensor noise, each point will use a local least-squares slope over an approximately 30-second centered window:

- slope unit is converted from °C/second to °C/minute
- windows with insufficient samples become gaps
- no extrapolation beyond available data

The window will be a named constant and documented in code so it can be tuned later. This produces a more useful comparison than a noisy point-to-point derivative.

The RoR axis starts at 0 and ends at the highest non-negative RoR value across all enabled profiles. The range is recalculated when profiles are enabled, disabled, added, or removed. Negative RoR samples fall outside the displayed RoR scale.

### 5.6 Heater and air extraction

For this dataset, the first extra device is declared as `+Kaleido Heater/Fan`:

- Heater: `extratemp1[0]`
- Air/fan: `extratemp2[0]`
- Time: `extratimex[0]`

The parser will first identify an extra device whose device label contains `Heater/Fan` (case-insensitive), then fall back to index 0 for compatibility with these logs. If no valid channel exists, that profile will load with a warning and without the missing curves.

### 5.7 Mixed temperature units

The supplied set is entirely Celsius. If a future selection mixes Celsius and Fahrenheit profiles, the backend will normalize Fahrenheit profiles to Celsius and include an import warning. The chart will therefore never combine incompatible temperature scales.

## 6. Technical architecture

### 6.1 Stack

To keep the app lightweight and easy to run:

- **Backend:** Python 3 standard library only
- **Frontend:** semantic HTML, modern vanilla JavaScript, and CSS
- **Chart:** custom HTML Canvas renderer with a small DOM overlay for controls/tooltips
- **Runtime dependencies:** none (installation uses a Python build backend)
- **Network binding:** `127.0.0.1` only

No framework, database, cloud service, or CDN is required; installation uses pip.

### 6.2 Project layout and responsibilities

```text
pyproject.toml                 # build configuration and `prophile` CLI entry point
server.py, roast_parser.py     # source-checkout entry point and compatibility import
prophile/
  server.py                   # localhost static server, local discovery, upload API
  roast_parser.py             # safe parser, events, phases, and RoR
  static/
    index.html                # sidebar, grid, and chart markup
    app.js                    # imports, selection, filters, grid state
    chart.js                  # canvas chart and coordinated hover
    styles.css                # responsive styling
sample_profiles/              # three bundled `.alog` examples
tests/                        # parser and server integration tests
README.md, design_doc.md
```

### 6.3 Local API

- `GET /api/local-profiles`: reads `.alog` files in the directory captured at startup, returning normalized profiles, per-file errors, and the directory path. Files outside the directory (including symlink targets) are excluded. Profiles are initially unselected in the browser.
- `POST /api/parse`: accepts raw `.alog` bytes with a URL-encoded `X-Filename` header and returns a normalized profile or a structured error. Each picker/drop import is independent; uploads are not saved.

### 6.4 Install and run

Install from the checkout in a virtual environment (no `sudo`): `python3 -m venv .venv`, activate it, upgrade pip, then `python -m pip install .`. Upgrading pip is important with Apple's bundled Python 3.9/pip 21, which may otherwise build an unusable `UNKNOWN` wheel. Run `prophile [--port PORT]` from the roast directory and open `http://127.0.0.1:8000` by default. For source-checkout use without installation, run `python3 /path/to/checkout/server.py` from the roast directory. The server binds only to `127.0.0.1`.

## 7. Accessibility and responsiveness

- Every checkbox and action has a visible label or accessible name and keyboard focus state.
- Rows containing roast or cupping notes can be focused to reveal the same labeled notes tooltip provided on mouseover.
- File selection works without drag-and-drop.
- Colors are not the only encoding: filenames, line styles, and event labels remain present.
- Controls wrap cleanly on narrow screens.
- Canvas receives an accessible text summary listing loaded profiles and visible metrics.
- Reduced-motion preferences will be respected; the chart does not require animation.

## 8. Error handling

The UI will distinguish:

- Unsupported extension
- File too large
- Invalid or malformed `.alog`
- Missing main temperature arrays
- Missing optional heater/air channel
- Missing roast milestones
- Duplicate selection
- Server/network failure

Warnings are non-blocking when a useful partial profile can still be charted. Non-fatal warnings from `*glitch.alog` files are suppressed, but parse errors remain visible.

## 9. Testing and acceptance criteria

### 9.1 Automated parser tests

Using Python's built-in `unittest`:

- Parse all three bundled profiles from `sample_profiles/`.
- Parse a representative synthetic `.alog` fixture.
- Correctly map `temp1` to ET and `temp2` to BT.
- Correctly map the Kaleido heater/fan extra device.
- Align Charge to `00:00`.
- Extract optional roast notes and cupping notes without treating missing notes as errors.
- Extract green and final batch weights and calculate weight-loss percentage.
- Return Charge and Drop bean temperatures from normalized event data.
- Calculate Drying, Browning, and Development durations and percentages from event boundaries.
- Return unavailable phase values safely when an event boundary is missing.
- Clip ordinary profiles at Drop.
- Retain usable data when Drop or other events are absent.
- Generate finite, plausible RoR values from a known linear fixture.
- Reject executable/malformed input safely.
- Handle mismatched array lengths and missing optional channels.

### 9.2 End-to-end acceptance

1. The installed `prophile` command runs from any directory; `python3 server.py` works from a source checkout without runtime dependencies. The server binds to localhost and does not persist uploads.
2. On load, all valid `.alog` files directly in the launch directory appear in filename-derived bean groups in the sidebar; grid and chart remain empty until a batch is selected.
3. Group and batch checkboxes and Select all/none control both grid and chart; imports via multi-file picker or page-wide drop are selected automatically. Grid × deselects a batch; sidebar × removes it entirely; Clear all removes all loaded profiles.
4. The grid shows filename-derived names, green/final weights, Charge/Drop temperatures, and Drying/Browning/Development values or `—` for missing values. Notes remain available on hover and keyboard focus.
5. Hovering grid rows emphasizes their chart curves; hovering a chart curve or pin highlights the matching grid row. Colors identify profiles; line styles identify BT, ET, RoR, heat, and air. Curve/event controls, axes, tooltip, and responsive chart work with multiple selections.
6. Missing events do not prevent plotting. `*glitch.alog` suppresses non-fatal warnings, not errors. Invalid profiles cannot prevent valid ones from loading.
7. Tests cover parsing, filename grouping, glitch warning suppression, and launch-directory discovery/static delivery; README documents installation, usage, and tests.

## 10. Deliberate non-goals for the first version

- Editing or writing `.alog` files
- Saving comparisons between browser sessions
- Exporting chart images or CSV
- Cloud sync or remote access
- Reproducing every Artisan calculation or annotation
- User-configurable RoR smoothing
- Comparing metadata beyond what is shown in chart tooltips

These can be added later without changing the normalized profile model.
