"""CSS cascade and specificity verification tests."""
import unittest
from pathlib import Path

try:
    from tests.css_utils import (
        Element,
        calculate_specificity,
        find_descending_specificity_conflicts,
        get_computed_style,
        matches_selector,
        parse_css_rules,
    )
except ImportError:
    from css_utils import (
        Element,
        calculate_specificity,
        find_descending_specificity_conflicts,
        get_computed_style,
        matches_selector,
        parse_css_rules,
    )


class StyleTests(unittest.TestCase):
    def test_theme_toggle_icon_styles_specificity(self):
        css_path = Path(__file__).resolve().parents[1] / "prophile" / "static" / "styles.css"
        css = css_path.read_text(encoding="utf-8")
        rules = parse_css_rules(css)

        # Build light-mode DOM tree
        root_light = Element("html", is_root=True)
        body_light = Element("body", parent=root_light)
        app_shell_light = Element("div", classes=["app-shell"], parent=body_light)
        hero_actions_light = Element("div", classes=["hero-actions"], parent=app_shell_light)
        toggle_btn_light = Element(
            "button", element_id="theme-toggle", classes=["theme-toggle"], parent=hero_actions_light
        )
        sun_icon_light = Element("svg", classes=["theme-icon", "theme-icon-sun"], parent=toggle_btn_light)
        moon_icon_light = Element("svg", classes=["theme-icon", "theme-icon-moon"], parent=toggle_btn_light)

        # Build dark-mode DOM tree
        root_dark = Element("html", attributes={"data-theme": "dark"}, is_root=True)
        body_dark = Element("body", parent=root_dark)
        app_shell_dark = Element("div", classes=["app-shell"], parent=body_dark)
        hero_actions_dark = Element("div", classes=["hero-actions"], parent=app_shell_dark)
        toggle_btn_dark = Element(
            "button", element_id="theme-toggle", classes=["theme-toggle"], parent=hero_actions_dark
        )
        sun_icon_dark = Element("svg", classes=["theme-icon", "theme-icon-sun"], parent=toggle_btn_dark)
        moon_icon_dark = Element("svg", classes=["theme-icon", "theme-icon-moon"], parent=toggle_btn_dark)

        # Computed display in light mode
        sun_light_style = get_computed_style(sun_icon_light, "display", rules)
        self.assertIsNotNone(sun_light_style)
        self.assertEqual(sun_light_style["value"], "none")

        moon_light_style = get_computed_style(moon_icon_light, "display", rules)
        self.assertIsNotNone(moon_light_style)
        self.assertEqual(moon_light_style["value"], "block")

        # Computed display in dark mode
        sun_dark_style = get_computed_style(sun_icon_dark, "display", rules)
        self.assertIsNotNone(sun_dark_style)
        self.assertEqual(sun_dark_style["value"], "block")

        moon_dark_style = get_computed_style(moon_icon_dark, "display", rules)
        self.assertIsNotNone(moon_dark_style)
        self.assertEqual(moon_dark_style["value"], "none")

        # Ensure no descending specificity conflicts on display for theme toggle icons
        for elem in (sun_icon_light, moon_icon_light, sun_icon_dark, moon_icon_dark):
            conflicts = find_descending_specificity_conflicts(elem, "display", rules)
            self.assertEqual(conflicts, [], f"Descending specificity conflict detected for {elem.classes}: {conflicts}")

    def test_theme_toggle_selector_specificity_dominance(self):
        css_path = Path(__file__).resolve().parents[1] / "prophile" / "static" / "styles.css"
        css = css_path.read_text(encoding="utf-8")
        rules = parse_css_rules(css)

        display_rules = {r["selector"]: r["specificity"] for r in rules if "display" in r["declarations"]}

        self.assertIn(".theme-toggle svg", display_rules)
        svg_base_specificity = display_rules[".theme-toggle svg"]

        sun_light_selectors = [s for s in display_rules if ".theme-icon-sun" in s and "dark" not in s]
        moon_light_selectors = [s for s in display_rules if ".theme-icon-moon" in s and "dark" not in s]
        self.assertTrue(sun_light_selectors)
        self.assertTrue(moon_light_selectors)

        for sel in sun_light_selectors:
            self.assertGreater(display_rules[sel], svg_base_specificity)
        for sel in moon_light_selectors:
            self.assertGreater(display_rules[sel], svg_base_specificity)

        dark_sun_selectors = [s for s in display_rules if ".theme-icon-sun" in s and "dark" in s]
        dark_moon_selectors = [s for s in display_rules if ".theme-icon-moon" in s and "dark" in s]
        self.assertTrue(dark_sun_selectors)
        self.assertTrue(dark_moon_selectors)

        for sel in dark_sun_selectors:
            for l_sel in sun_light_selectors:
                self.assertGreaterEqual(display_rules[sel], display_rules[l_sel])
        for sel in dark_moon_selectors:
            for l_sel in moon_light_selectors:
                self.assertGreaterEqual(display_rules[sel], display_rules[l_sel])

    def test_css_specificity_calculator(self):
        self.assertEqual(calculate_specificity("svg"), (0, 0, 1))
        self.assertEqual(calculate_specificity(".theme-icon-sun"), (0, 1, 0))
        self.assertEqual(calculate_specificity(".theme-toggle svg"), (0, 1, 1))
        self.assertEqual(calculate_specificity(".theme-toggle .theme-icon-sun"), (0, 2, 0))
        self.assertEqual(calculate_specificity(':root[data-theme="dark"] .theme-toggle .theme-icon-sun'), (0, 4, 0))
        self.assertEqual(calculate_specificity('[data-theme="dark"] .theme-toggle .theme-icon-sun'), (0, 3, 0))
        self.assertEqual(calculate_specificity("#theme-toggle"), (1, 0, 0))
        self.assertEqual(calculate_specificity("button:focus-visible"), (0, 1, 1))
        self.assertEqual(calculate_specificity(".line.step::before"), (0, 2, 1))

    def test_css_cascade_detects_buggy_selector_collision(self):
        buggy_css = """
        .theme-toggle svg { display: block; }
        .theme-icon-sun { display: none; }
        """
        rules = parse_css_rules(buggy_css)
        toggle = Element("button", classes=["theme-toggle"])
        sun = Element("svg", classes=["theme-icon", "theme-icon-sun"], parent=toggle)

        computed = get_computed_style(sun, "display", rules)
        self.assertEqual(computed["value"], "block")
        self.assertEqual(computed["winning_selector"], ".theme-toggle svg")

    def test_matches_selector_child_combinator_strictness(self):
        """Verifies child combinator (>) does not match non-direct descendants."""
        parent = Element("div")
        intermediate = Element("span", parent=parent)
        child = Element("p", parent=intermediate)

        # Descendant combinator should match
        self.assertTrue(matches_selector(child, "div p"))
        # Direct child combinator should not match grandchild
        self.assertFalse(matches_selector(child, "div > p"))
        # Intermediate direct child should match
        self.assertTrue(matches_selector(child, "div > span > p"))

    def test_parse_css_rules_media_order_and_rule_id(self):
        """Verifies @media rules maintain strict sequential order and distinct rule_ids."""
        css = """
        .base { color: red; }
        @media (min-width: 600px) {
            .base { color: blue; }
            .extra { color: green; }
        }
        .after { color: yellow; }
        """
        rules = parse_css_rules(css)
        self.assertEqual(len(rules), 4)

        # Check sequential order
        orders = [r["order"] for r in rules]
        self.assertEqual(orders, [0, 1, 2, 3])

        # Check distinct rule_ids across media block boundaries
        rule_ids = [r["rule_id"] for r in rules]
        self.assertEqual(rule_ids, [0, 1, 2, 3])

        # Verify cascade precedence: later media rule wins over earlier rule with equal specificity
        elem = Element("div", classes=["base"])
        computed = get_computed_style(elem, "color", rules)
        self.assertEqual(computed["value"], "blue")

    def test_specificity_attribute_with_hash_not_counted_as_id(self):
        """Verifies attribute selector containing '#' is counted as an attribute, not an ID."""
        self.assertEqual(calculate_specificity('a[href="#top"]'), (0, 1, 1))
        self.assertEqual(calculate_specificity('[data-target="#modal"]'), (0, 1, 0))
