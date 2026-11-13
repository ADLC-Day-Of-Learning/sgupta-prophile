"""Integration checks for the current-directory profile discovery endpoint and CSS cascade verification."""
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from prophile.server import AppServer


def calculate_specificity(selector: str):
    """Calculate CSS specificity (a, b, c) according to CSS Selectors specs.

    a: ID selectors (#id)
    b: Class selectors (.class), attribute selectors ([attr]), pseudo-classes (:root, :hover, etc.)
       Functional pseudo-classes (:is, :not, :has) contribute the max specificity of their arguments.
       :where contributes (0, 0, 0).
    c: Type/element selectors (svg, button, div, etc.) and pseudo-elements (::before, ::after, etc.)
    """
    sel = selector.strip()
    a, b, c = 0, 0, 0

    def handle_functional_pseudo(match):
        nonlocal a, b, c
        pseudo_name = match.group(1).lower()
        content = match.group(2)
        if pseudo_name in ("not", "is", "has"):
            sub_selectors = [s.strip() for s in content.split(",") if s.strip()]
            max_spec = (0, 0, 0)
            for sub_sel in sub_selectors:
                spec = calculate_specificity(sub_sel)
                if spec > max_spec:
                    max_spec = spec
            a += max_spec[0]
            b += max_spec[1]
            c += max_spec[2]
        elif pseudo_name == "where":
            pass
        else:
            b += 1
        return ""

    sel = re.sub(r":([a-zA-Z-]+)\(([^)]*)\)", handle_functional_pseudo, sel)

    legacy_pe = r":(?:before|after|first-letter|first-line)\b"
    c += len(re.findall(legacy_pe, sel, flags=re.IGNORECASE))
    sel = re.sub(legacy_pe, "", sel, flags=re.IGNORECASE)

    double_pe = r"::[a-zA-Z-]+(?:\([^)]*\))?"
    c += len(re.findall(double_pe, sel))
    sel = re.sub(double_pe, "", sel)

    ids = re.findall(r"#[a-zA-Z0-9_-]+", sel)
    a += len(ids)
    sel = re.sub(r"#[a-zA-Z0-9_-]+", "", sel)

    attrs = re.findall(r"\[[^\]]+\]", sel)
    b += len(attrs)
    sel = re.sub(r"\[[^\]]+\]", "", sel)

    classes = re.findall(r"\.[a-zA-Z0-9_-]+", sel)
    b += len(classes)
    sel = re.sub(r"\.[a-zA-Z0-9_-]+", "", sel)

    pseudo_classes = re.findall(r":[a-zA-Z0-9_-]+", sel)
    b += len(pseudo_classes)
    sel = re.sub(r":[a-zA-Z0-9_-]+", "", sel)

    elements = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]*\b", sel)
    c += len(elements)

    return (a, b, c)


def parse_css_rules(css_text: str):
    """Parse CSS stylesheet text into a list of rule dictionaries."""
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    rules = []
    i = 0
    rule_index = 0
    while i < len(css_text):
        if css_text[i].isspace():
            i += 1
            continue
        open_brace = css_text.find("{", i)
        if open_brace == -1:
            break
        header = css_text[i:open_brace].strip()
        if header.startswith("@media"):
            depth = 1
            j = open_brace + 1
            inner_start = j
            while j < len(css_text) and depth > 0:
                if css_text[j] == "{":
                    depth += 1
                elif css_text[j] == "}":
                    depth -= 1
                j += 1
            inner_css = css_text[inner_start:j - 1]
            sub_rules = parse_css_rules(inner_css)
            rules.extend(sub_rules)
            i = j
        elif header.startswith("@"):
            depth = 1
            j = open_brace + 1
            while j < len(css_text) and depth > 0:
                if css_text[j] == "{":
                    depth += 1
                elif css_text[j] == "}":
                    depth -= 1
                j += 1
            i = j
        else:
            close_brace = css_text.find("}", open_brace)
            if close_brace == -1:
                break
            body = css_text[open_brace + 1:close_brace].strip()
            selectors = []
            cur = []
            bracket_depth = 0
            paren_depth = 0
            for ch in header:
                if ch == "[":
                    bracket_depth += 1
                elif ch == "]":
                    bracket_depth -= 1
                elif ch == "(":
                    paren_depth += 1
                elif ch == ")":
                    paren_depth -= 1
                elif ch == "," and bracket_depth == 0 and paren_depth == 0:
                    selectors.append("".join(cur).strip())
                    cur = []
                    continue
                cur.append(ch)
            if cur:
                selectors.append("".join(cur).strip())

            decls = {}
            for decl in body.split(";"):
                decl = decl.strip()
                if not decl:
                    continue
                if ":" in decl:
                    prop, val = decl.split(":", 1)
                    prop_name = prop.strip().lower()
                    val_str = val.strip()
                    important = "!important" in val_str.lower()
                    clean_val = re.sub(r"!important", "", val_str, flags=re.IGNORECASE).strip()
                    decls[prop_name] = (clean_val, important)

            for sel in selectors:
                if sel:
                    rules.append({
                        "selector": sel,
                        "declarations": decls,
                        "rule_id": rule_index,
                        "order": rule_index,
                        "specificity": calculate_specificity(sel),
                    })
            rule_index += 1
            i = close_brace + 1
    return rules


class Element:
    def __init__(self, tag, element_id=None, classes=None, attributes=None, parent=None, is_root=False):
        self.tag = tag.lower()
        self.element_id = element_id
        self.classes = set(classes) if classes else set()
        self.attributes = dict(attributes) if attributes else {}
        self.parent = parent
        self.is_root = is_root


def parse_simple_compound(compound: str):
    tag = None
    elem_id = None
    classes = set()
    attrs = []
    pseudo_classes = set()
    s = compound.strip()

    attr_matches = re.findall(r"\[([a-zA-Z0-9_-]+)(?:([~|^$*]?=)([\"']?)(.*?)\3)?\]", s)
    for k, op, _, v in attr_matches:
        attrs.append((k, op, v))
    s = re.sub(r"\[[^\]]+\]", "", s)

    id_match = re.search(r"#([a-zA-Z0-9_-]+)", s)
    if id_match:
        elem_id = id_match.group(1)
        s = s.replace(f"#{elem_id}", "")

    class_matches = re.findall(r"\.([a-zA-Z0-9_-]+)", s)
    for c in class_matches:
        classes.add(c)
    s = re.sub(r"\.[a-zA-Z0-9_-]+", "", s)

    pseudo_matches = re.findall(r":([a-zA-Z0-9_-]+)", s)
    for p in pseudo_matches:
        pseudo_classes.add(p)
    s = re.sub(r":[a-zA-Z0-9_-]+", "", s)

    tag_match = re.search(r"^[a-zA-Z0-9_-]+", s)
    if tag_match and tag_match.group(0) != "*":
        tag = tag_match.group(0).lower()

    return {"tag": tag, "id": elem_id, "classes": classes, "attrs": attrs, "pseudo_classes": pseudo_classes}


def element_matches_compound(elem: Element, criteria: dict):
    if criteria["tag"] and elem.tag != criteria["tag"]:
        return False
    if criteria["id"] and elem.element_id != criteria["id"]:
        return False
    if criteria["classes"] and not criteria["classes"].issubset(elem.classes):
        return False
    for k, op, val in criteria["attrs"]:
        if k not in elem.attributes:
            return False
        if op:
            actual = elem.attributes[k]
            if op == "=" and actual != val:
                return False
            elif op == "^=" and not actual.startswith(val):
                return False
            elif op == "$=" and not actual.endswith(val):
                return False
            elif op == "*=" and val not in actual:
                return False
            elif op == "~=" and val not in actual.split():
                return False
    for pseudo in criteria["pseudo_classes"]:
        if pseudo == "root":
            if not elem.is_root:
                return False
        elif pseudo in ("hover", "focus", "focus-visible", "active"):
            return False
    return True


def matches_selector(elem: Element, selector: str):
    tokens = [t.strip() for t in re.split(r"(\s+|(?=[>+~])|(?<=[>+~]))", selector) if t.strip()]
    stages = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in (">", "+", "~"):
            combinator = tok
            i += 1
            compound = tokens[i]
        else:
            combinator = " "
            compound = tok
        stages.append((combinator, parse_simple_compound(compound)))
        i += 1

    combinator, target_criteria = stages[-1]
    if not element_matches_compound(elem, target_criteria):
        return False

    current_elem = elem
    for combinator, criteria in reversed(stages[:-1]):
        if combinator == ">":
            current_elem = current_elem.parent
            if not current_elem or not element_matches_compound(current_elem, criteria):
                return False
        else:
            matched = False
            current_elem = current_elem.parent
            while current_elem:
                if element_matches_compound(current_elem, criteria):
                    matched = True
                    break
                current_elem = current_elem.parent
            if not matched:
                return False
    return True


def get_computed_style(elem: Element, prop_name: str, rules: list[dict]):
    matching_decls = []
    for rule in rules:
        if prop_name in rule["declarations"]:
            if matches_selector(elem, rule["selector"]):
                val, important = rule["declarations"][prop_name]
                matching_decls.append((important, rule["specificity"], rule["order"], val, rule["selector"]))
    if not matching_decls:
        return None
    matching_decls.sort(key=lambda x: (x[0], x[1], x[2]))
    winning = matching_decls[-1]
    return {
        "value": winning[3],
        "important": winning[0],
        "specificity": winning[1],
        "winning_selector": winning[4],
        "all_matches": matching_decls,
    }


def find_descending_specificity_conflicts(elem: Element, prop_name: str, rules: list[dict]):
    matches = []
    for rule in rules:
        if prop_name in rule["declarations"]:
            if matches_selector(elem, rule["selector"]):
                val, important = rule["declarations"][prop_name]
                matches.append((
                    rule.get("rule_id", rule["order"]),
                    rule["order"],
                    rule["specificity"],
                    important,
                    rule["selector"],
                    val,
                ))
    conflicts = []
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            r1 = matches[i]
            r2 = matches[j]
            # Ignore selectors from the same rule block
            if r1[0] == r2[0]:
                continue
            # A later rule with lower specificity attempting to set a conflicting value
            if r2[2] < r1[2] and not r2[3] and r2[5] != r1[5]:
                conflicts.append((r1, r2))
    return conflicts


class ServerTests(unittest.TestCase):
    def test_local_profiles_and_static_assets_from_other_directory(self):
        sample = next((Path(__file__).resolve().parents[1] / "sample_profiles").glob("*.alog"))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / sample.name).write_bytes(sample.read_bytes())
            (directory / "bad.alog").write_text("not a roast")
            (directory / "other.txt").write_text("ignored")
            server = AppServer(("127.0.0.1", 0), directory.resolve())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/api/local-profiles") as response:
                    data = json.load(response)
                self.assertEqual(data["directory"], str(directory.resolve()))
                self.assertEqual(len(data["profiles"]), 1)
                self.assertEqual(data["profiles"][0]["bean"], "Baarbara Washed AA")
                self.assertEqual(len(data["errors"]), 1)
                with urlopen(base + "/") as response:
                    body = response.read()
                    self.assertIn(b"Beans &amp; batches", body)
                    self.assertIn(b'id="theme-toggle"', body)
                    self.assertIn(b'class="theme-toggle"', body)
                    self.assertIn(b"Green Weight (Density)", body)
                    self.assertNotIn(b'<th scope="col">Green weight</th>', body)
                    self.assertNotIn(b'<th scope="col">Density</th>', body)
                with urlopen(base + "/styles.css") as response:
                    css = response.read().decode("utf-8")
                    self.assertIn('data-theme="dark"', css)
                    self.assertIn("--ink", css)
                    self.assertIn("--paper", css)
                    self.assertIn(".theme-toggle .theme-icon-sun { display: none; }", css)
                    self.assertIn(".theme-toggle .theme-icon-moon { display: block; }", css)
                with urlopen(base + "/app.js") as response:
                    js = response.read().decode("utf-8")
                    self.assertIn("themeToggle", js)
                    self.assertIn("setTheme", js)
                    self.assertIn("greenWeightDensityText", js)
                with urlopen(base + "/chart.js") as response:
                    chart_js = response.read().decode("utf-8")
                    self.assertIn("isDarkMode", chart_js)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_profiles_table_combined_header(self):
        sample = next((Path(__file__).resolve().parents[1] / "sample_profiles").glob("*.alog"))
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / sample.name).write_bytes(sample.read_bytes())
            server = AppServer(("127.0.0.1", 0), directory.resolve())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                with urlopen(base + "/") as response:
                    html = response.read().decode("utf-8")
                    self.assertIn("Green Weight (Density)", html)
                    self.assertNotIn('<th scope="col">Green weight</th>', html)
                    self.assertNotIn('<th scope="col">Density</th>', html)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

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
