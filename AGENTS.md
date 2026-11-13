# Agent Instructions

## Build and Test Commands

- Run test suite: `python3 -m unittest discover -s tests`
- Note that no external dependencies or build steps are required (Python standard library only).

## Documentation Currency

- `design_doc.md` is living documentation.
- Any change modifying profile table columns must update Section 3.2 ('Sidebar and selected-profile grid') column tables and example rows.
- Any change modifying data formats or backend endpoints must update Section 5.2 ('Normalized API result') and/or Section 6.3 ('Local API').

## HTML Integration Test Conventions

- Integration checks in `tests/test_server.py` test server-rendered static templates using substring matching on GET `/`.
- When asserting the removal or replacement of markup elements, assert against complete opening tags including attributes (e.g. `<th scope="col">...</th>`) rather than bare tags (`<th>...</th>`) to prevent vacuous negative assertions.

## CSS and Styling Test Conventions

- Stylesheet cascade precedence, selector specificity dominance, and computed element display states are tested in `tests/test_styles.py` using standard-library helpers from `tests/css_utils.py`.
- Do not add raw substring assertions on `styles.css` in `tests/test_server.py` to verify visual or display styles. Server integration checks in `test_server.py` should only verify HTTP static asset availability (status 200, Content-Type, and baseline CSS custom properties), delegating all selector specificity and cascade validation to `tests/test_styles.py`.
