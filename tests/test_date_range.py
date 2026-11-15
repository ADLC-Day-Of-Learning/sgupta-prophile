"""Tests for date range selector bounds, filtering, and selection synchronization."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "prophile" / "static" / "app.js"


def run_node_eval(script: str) -> dict:
    """Execute a Node.js snippet that evaluates app.js in a mocked browser environment and returns JSON output."""
    node_preamble = f"""
    const fs = require('fs');
    function mockElement(tag = 'div') {{
        return {{
            tagName: tag.toUpperCase(),
            min: null,
            max: null,
            value: '',
            hidden: false,
            textContent: '',
            files: [],
            dataset: {{}},
            title: '',
            style: {{}},
            removeAttribute(attr) {{ delete this[attr]; }},
            setAttribute(attr, val) {{ this[attr] = val; }},
            addEventListener() {{}},
            querySelector() {{ return null; }},
            querySelectorAll() {{ return []; }},
            replaceChildren() {{}},
            append() {{}},
            appendChild() {{}},
            classList: {{
                add() {{}},
                remove() {{}},
                toggle() {{}},
            }},
        }};
    }}
    const mockDocument = {{
        querySelector: (sel) => mockElement(),
        querySelectorAll: () => [],
        createElement: (tag) => mockElement(tag),
        addEventListener: () => {{}},
        documentElement: {{ getAttribute: () => 'light', setAttribute: () => {{}} }},
        body: {{ getAttribute: () => 'light', setAttribute: () => {{}} }},
    }};
    global.window = global;
    global.document = mockDocument;
    global.localStorage = {{ getItem: () => null, setItem: () => {{}} }};
    global.ResizeObserver = class {{ observe() {{}} unobserve() {{}} disconnect() {{}} }};
    global.RoastOverlayChart = class {{
        constructor() {{ this.onHoverProfile = () => {{}}; }}
        setData() {{}}
        setTheme() {{}}
    }};
    global.HTMLInputElement = function() {{}};
    global.fetch = () => Promise.resolve({{ ok: true, json: () => Promise.resolve({{ directory: '.', profiles: [], errors: [] }}) }});

    function makeInput() {{
        return {{
            min: null,
            max: null,
            value: '',
            removeAttribute(name) {{ delete this[name]; }},
            setAttribute(name, val) {{ this[name] = val; }},
        }};
    }}

    const code = fs.readFileSync({json.dumps(str(APP_JS))}, 'utf8');
    eval(code);
    const app = window.prophileApp;

    // Ensure mock profiles pushed in tests have complete fields for DOM rendering
    const origPush = app.profiles.push;
    app.profiles.push = function(...items) {{
        for (const item of items) {{
            if (!item.phases) item.phases = {{ drying: null, browning: null, development: null }};
            if (!item.weights) item.weights = {{}};
            if (!item.events) item.events = [];
            if (!item.displayName) item.displayName = item.filename || 'mock';
            if (!item.color) item.color = '#000000';
            if (!item.id) item.id = 'id-' + Math.random();
        }}
        return origPush.apply(this, items);
    }};
    """
    full_script = f"""
    {node_preamble}
    const result = (function() {{
        {script}
    }})();
    console.log(JSON.stringify(result));
    """
    proc = subprocess.run(
        ["node", "-e", full_script],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Node execution failed (code {proc.returncode}):\n{proc.stderr}")
    return json.loads(proc.stdout.strip())


@unittest.skipUnless(shutil.which("node"), "Node.js is required to run JS unit tests")
class DateRangeSelectorTests(unittest.TestCase):
    def test_profile_date_extraction(self):
        script = """
        return {
            yy: app.profileDate({ filename: '26-09-12_Baarbara_Washed_AA_batch_3.alog' }),
            yyyy: app.profileDate({ filename: '2026-08-15_Baarbara_HSD_batch_5.alog' }),
            isoField: app.profileDate({ filename: 'other.alog', roastisodate: '2026-07-26' }),
            roastDateField: app.profileDate({ filename: 'other.alog', roastDate: '2026-06-10' }),
            noDate: app.profileDate({ filename: 'untitled_roast.alog' }),
        };
        """
        result = run_node_eval(script)
        self.assertEqual(result["yy"], "2026-09-12")
        self.assertEqual(result["yyyy"], "2026-08-15")
        self.assertEqual(result["isoField"], "2026-07-26")
        self.assertEqual(result["roastDateField"], "2026-06-10")
        self.assertIsNone(result["noDate"])

    def test_default_bounds_and_initial_selection(self):
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        app.profiles.push(
            { filename: '26-07-26_batch_1.alog', enabled: false },
            { filename: '26-08-15_batch_2.alog', enabled: false },
            { filename: '26-09-12_batch_3.alog', enabled: false }
        );
        app.updateDateBounds();
        app.updateDateRangeFromSelection();
        const today = app.getTodayIso();
        return {
            minStart: app.elements.dateStart.min,
            minEnd: app.elements.dateEnd.min,
            valStart: app.elements.dateStart.value,
            valEnd: app.elements.dateEnd.value,
            today: today
        };
        """
        result = run_node_eval(script)
        # Bounds default from oldest roast date (2026-07-26) through today
        self.assertEqual(result["minStart"], "2026-07-26")
        self.assertEqual(result["minEnd"], "2026-07-26")
        # Default selection has both set to today's date
        self.assertEqual(result["valStart"], result["today"])
        self.assertEqual(result["valEnd"], result["today"])

    def test_date_range_filtering_logic(self):
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const p1 = { filename: '26-07-26_batch_1.alog', enabled: false };
        const p2 = { filename: '26-08-15_batch_2.alog', enabled: false };
        const p3 = { filename: '26-09-12_batch_3.alog', enabled: false };
        app.profiles.push(p1, p2, p3);

        // Filter August only
        app.elements.dateStart.value = '2026-08-01';
        app.elements.dateEnd.value = '2026-08-31';
        app.applyDateRangeFilter();
        const augResult = [p1.enabled, p2.enabled, p3.enabled];

        // Filter July through September
        app.elements.dateStart.value = '2026-07-01';
        app.elements.dateEnd.value = '2026-09-30';
        app.applyDateRangeFilter();
        const allResult = [p1.enabled, p2.enabled, p3.enabled];

        // Inverted range (start > end) enables none
        app.elements.dateStart.value = '2026-09-30';
        app.elements.dateEnd.value = '2026-07-01';
        app.applyDateRangeFilter();
        const invertedResult = [p1.enabled, p2.enabled, p3.enabled];

        return { augResult, allResult, invertedResult };
        """
        result = run_node_eval(script)
        self.assertEqual(result["augResult"], [False, True, False])
        self.assertEqual(result["allResult"], [True, True, True])
        self.assertEqual(result["invertedResult"], [False, False, False])

    def test_date_range_filter_undated_profiles(self):
        """Verifies that undated profiles are disabled when applying date filters, even if previously enabled."""
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const p1 = { filename: '26-07-26_batch_1.alog', enabled: true };
        const pUndated = { filename: 'no_date_profile.alog', enabled: true };
        app.profiles.push(p1, pUndated);

        // Apply a range matching p1
        app.elements.dateStart.value = '2026-07-01';
        app.elements.dateEnd.value = '2026-07-31';
        app.applyDateRangeFilter();
        const filterMatchResult = { p1: p1.enabled, undated: pUndated.enabled };

        // Re-enable undated profile and apply inverted range (start > end)
        pUndated.enabled = true;
        app.elements.dateStart.value = '2026-09-30';
        app.elements.dateEnd.value = '2026-07-01';
        app.applyDateRangeFilter();
        const invertedResult = { p1: p1.enabled, undated: pUndated.enabled };

        return { filterMatchResult, invertedResult };
        """
        result = run_node_eval(script)
        self.assertEqual(result["filterMatchResult"], {"p1": True, "undated": False})
        self.assertEqual(result["invertedResult"], {"p1": False, "undated": False})

    def test_date_range_filter_cleared_inputs_evaluates_unbounded(self):
        """Verifies clearing both date inputs evaluates an unbounded range enabling dated profiles."""
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const p1 = { filename: '26-07-26_batch_1.alog', enabled: false };
        const p2 = { filename: '26-08-15_batch_2.alog', enabled: false };
        const pUndated = { filename: 'no_date.alog', enabled: true };
        app.profiles.push(p1, p2, pUndated);

        // Both inputs cleared (empty string)
        app.elements.dateStart.value = '';
        app.elements.dateEnd.value = '';
        app.applyDateRangeFilter();

        return {
            p1: p1.enabled,
            p2: p2.enabled,
            pUndated: pUndated.enabled,
        };
        """
        result = run_node_eval(script)
        self.assertTrue(result["p1"])
        self.assertTrue(result["p2"])
        self.assertFalse(result["pUndated"])

    def test_select_all_and_select_none_synchronization(self):
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const p1 = { filename: '26-07-26_batch_1.alog', enabled: false };
        const p2 = { filename: '26-08-15_batch_2.alog', enabled: false };
        const p3 = { filename: '26-09-12_batch_3.alog', enabled: false };
        app.profiles.push(p1, p2, p3);

        const today = app.getTodayIso();

        // Select all: date range updates to cover all roasts
        p1.enabled = true;
        p2.enabled = true;
        p3.enabled = true;
        app.updateDateRangeFromSelection();
        const allStart = app.elements.dateStart.value;
        const allEnd = app.elements.dateEnd.value;

        // Select none: date range resets to today's date for both inputs
        p1.enabled = false;
        p2.enabled = false;
        p3.enabled = false;
        app.updateDateRangeFromSelection();
        const noneStart = app.elements.dateStart.value;
        const noneEnd = app.elements.dateEnd.value;

        return { allStart, allEnd, noneStart, noneEnd, today };
        """
        result = run_node_eval(script)
        self.assertEqual(result["allStart"], "2026-07-26")
        self.assertEqual(result["allEnd"], "2026-09-12")
        self.assertEqual(result["noneStart"], result["today"])
        self.assertEqual(result["noneEnd"], result["today"])

    def test_arbitrary_profile_selection_and_deselection(self):
        """Verifies date range updates when an arbitrary number of profiles are selected or deselected."""
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const p1 = { filename: '26-07-26_batch_1.alog', enabled: false };
        const p2 = { filename: '26-08-15_batch_2.alog', enabled: false };
        const p3 = { filename: '26-09-12_batch_3.alog', enabled: false };
        app.profiles.push(p1, p2, p3);

        const today = app.getTodayIso();
        const trace = [];

        // 1. Initially none selected -> both today
        app.updateDateRangeFromSelection();
        trace.push({ step: 'init', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 2. Select an arbitrary single profile (p2 on 2026-08-15)
        p2.enabled = true;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'select_p2', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 3. Additionally select p3 (2026-09-12) -> range expands to [2026-08-15, 2026-09-12]
        p3.enabled = true;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'select_p3', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 4. Additionally select p1 (2026-07-26) -> range expands to [2026-07-26, 2026-09-12]
        p1.enabled = true;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'select_p1', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 5. Deselect p1 -> range narrows back to [2026-08-15, 2026-09-12]
        p1.enabled = false;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'deselect_p1', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 6. Deselect p3 -> range narrows to single profile [2026-08-15, 2026-08-15]
        p3.enabled = false;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'deselect_p3', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        // 7. Deselect p2 (0 profiles remain selected) -> resets to both today
        p2.enabled = false;
        app.updateDateRangeFromSelection();
        trace.push({ step: 'deselect_all', start: app.elements.dateStart.value, end: app.elements.dateEnd.value });

        return { trace, today };
        """
        result = run_node_eval(script)
        steps = {item["step"]: item for item in result["trace"]}
        today = result["today"]

        self.assertEqual(steps["init"]["start"], today)
        self.assertEqual(steps["init"]["end"], today)

        self.assertEqual(steps["select_p2"]["start"], "2026-08-15")
        self.assertEqual(steps["select_p2"]["end"], "2026-08-15")

        self.assertEqual(steps["select_p3"]["start"], "2026-08-15")
        self.assertEqual(steps["select_p3"]["end"], "2026-09-12")

        self.assertEqual(steps["select_p1"]["start"], "2026-07-26")
        self.assertEqual(steps["select_p1"]["end"], "2026-09-12")

        self.assertEqual(steps["deselect_p1"]["start"], "2026-08-15")
        self.assertEqual(steps["deselect_p1"]["end"], "2026-09-12")

        self.assertEqual(steps["deselect_p3"]["start"], "2026-08-15")
        self.assertEqual(steps["deselect_p3"]["end"], "2026-08-15")

        self.assertEqual(steps["deselect_all"]["start"], today)
        self.assertEqual(steps["deselect_all"]["end"], today)

    def test_update_date_range_from_selection_with_undated_profiles_only(self):
        """Verifies selecting only profiles without dates resets date inputs to today's date."""
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        const pUndated1 = { filename: 'undated1.alog', enabled: true };
        const pUndated2 = { filename: 'undated2.alog', enabled: true };
        app.profiles.push(pUndated1, pUndated2);

        // Set stale dates first
        app.elements.dateStart.value = '2025-01-01';
        app.elements.dateEnd.value = '2025-01-31';

        app.updateDateRangeFromSelection();
        const today = app.getTodayIso();

        return {
            start: app.elements.dateStart.value,
            end: app.elements.dateEnd.value,
            today: today
        };
        """
        result = run_node_eval(script)
        self.assertEqual(result["start"], result["today"])
        self.assertEqual(result["end"], result["today"])

    def test_clear_all_resets_date_bounds_and_selection(self):
        script = """
        app.elements.dateStart = makeInput();
        app.elements.dateEnd = makeInput();
        app.profiles.length = 0;
        app.profiles.push(
            { filename: '26-07-26_batch_1.alog', enabled: true, duplicateKey: 'k1' },
            { filename: '26-09-12_batch_2.alog', enabled: true, duplicateKey: 'k2' }
        );
        app.updateDateBounds();
        app.updateDateRangeFromSelection();

        // Clear all
        app.clearAll();
        const today = app.getTodayIso();
        return {
            minStart: app.elements.dateStart.min || null,
            valStart: app.elements.dateStart.value,
            valEnd: app.elements.dateEnd.value,
            today: today
        };
        """
        result = run_node_eval(script)
        self.assertIsNone(result["minStart"])
        self.assertEqual(result["valStart"], result["today"])
        self.assertEqual(result["valEnd"], result["today"])


if __name__ == "__main__":
    unittest.main()
