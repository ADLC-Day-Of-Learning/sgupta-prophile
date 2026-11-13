# Agent Instructions

## Build and Test Commands

- Run test suite: `python3 -m unittest discover -s tests`
- Note that no external dependencies or build steps are required (Python standard library only).

## Documentation Currency

- `design_doc.md` is living documentation.
- Any change modifying profile table columns, data formats, or backend endpoints must update Section 3.2 ('Sidebar and selected-profile grid') column tables and example rows.

## HTML Integration Test Conventions

- Integration checks in `tests/test_server.py` test server-rendered static templates using substring matching on GET `/`.
- When asserting the removal or replacement of markup elements, assert against complete opening tags including attributes (e.g. `<th scope="col">...</th>`) rather than bare tags (`<th>...</th>`) to prevent vacuous negative assertions.
