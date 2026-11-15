"""Tests for date range selector bounds, filtering, and selection synchronization."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "prophile" / "static" / "app.js"


def run_node_eval(script: str) -> dict:
    """Execute a Node.js snippet that requires app.js and returns JSON output."""
    full_script = f"""
    const app = require({json.dumps(str(APP_JS))});
    const result = (function() {{
        {script}
    }})();
    console.log(JSON.stringify(result));
    """
    proc = subprocess.run(
        ["node", "-e", full_script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


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
        app.elements.dateStart = {};
        app.elements.dateEnd = {};
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
        app.elements.dateStart = {};
        app.elements.dateEnd = {};
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

    def test_select_all_and_select_none_synchronization(self):
        script = """
        app.elements.dateStart = {};
        app.elements.dateEnd = {};
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
        app.elements.dateStart = {};
        app.elements.dateEnd = {};
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

    def test_clear_all_resets_date_bounds_and_selection(self):
        script = """
        app.elements.dateStart = {};
        app.elements.dateEnd = {};
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
