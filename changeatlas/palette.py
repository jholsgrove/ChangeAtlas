"""palette.py — single source of colour truth for template and tests (WCAG-audited).

Values were tuned with the `dataviz` skill's accessible-palette method:
lightness/chroma bands and CVD (colour-vision-deficiency) separation were
checked with its `validate_palette.js` validator against this module's own
`bg` surface, in addition to the WCAG contrast gate in tests/test_palette.py.

Two themes ship with the report: PALETTE (dark, the original) and
LIGHT_PALETTE, identical in shape. THEMES maps theme id -> palette dict and
is what render.py injects; the template applies one at a time and the
in-report toggle switches between them. Every colour the template needs —
including the graph "chrome" the JS used to hard-code (dimmed nodes, edge
colours, badge text, highlight border) — lives here so both modes are
audited by tests/test_palette.py.

One deliberate, documented exception: `changed` and `touched` share the red
hue family by design (severity gradient within one hue — see the tier
`label`s), so their CVD separation sits below the validator's floor. That is
mitigated the way the validator's own rules require for any sub-floor pair:
secondary encoding, never colour alone — each tier also carries a distinct
`borderDashes` pattern and a always-visible text `label` (see
tests/test_palette.py::test_tiers_not_colour_alone and ::test_tier_labels_present).
"""

# Per-node-type graph colours (vis-network node fill). Same values as the
# ImpactMapper SRC port; contrast-audited against PALETTE["bg"] in
# tests/test_palette.py::test_type_colors_contrast. Kept as a module-level
# name because __main__.py builds the payload's typeStyle from it (dark is
# the payload baseline; the template re-colours per active theme).
TYPE_COLORS = {
    "repo": "#e0533d", "subsystem": "#4a9eea", "project": "#6ea8fe",
    "service": "#2db37c", "contract": "#c084fc", "driver": "#f0a020",
    "database": "#d9455f", "messaging": "#e6c34a", "feature": "#26c0c0",
    "external": "#8a949e",
}

PALETTE = {
    "bg": "#14171a",
    "panel_bg": "#1e2227",
    "text": "#e8eaed",
    "muted_text": "#b3b9c0",
    "link": "#8ab4f8",
    "tiers": {
        "changed":    {"fill": "#e0524a", "border": "#ff9086", "label": "Changed",    "borderDashes": False},
        "touched":    {"fill": "#c96a5f", "border": "#e8b2a8", "label": "Touched",    "borderDashes": [8, 4]},
        "testOnly":   {"fill": "#0f9686", "border": "#7fe0d1", "label": "Test-only",  "borderDashes": [2, 3]},
        "peripheral": {"fill": "#9a8f1a", "border": "#d9cf5e", "label": "Peripheral", "borderDashes": [12, 3, 2, 3]},
    },
    "type_colors": TYPE_COLORS,
    # Chrome (panel borders + colours previously hard-coded in template.html's JS):
    "line": "#232a31",                   # panel/table borders
    "dimmed": "#3a3f44",                 # untouched node fill — low contrast by design
    "edge_affected": "#8a5a3a",          # edge between two affected nodes
    "edge_dim": "#2a323a",               # edge touching an untouched node
    "edge_system": "#3d464f",            # edges in system view
    "badge_text": "#0b0e11",             # text on tier/type badge fills (AA-gated)
    "node_highlight_border": "#ffffff",  # selected/highlighted node outline
}

LIGHT_PALETTE = {
    "bg": "#f5f7f9",
    "panel_bg": "#ffffff",
    "text": "#1c2126",
    "muted_text": "#5a646e",
    "link": "#1a5fb4",
    "tiers": {
        "changed":    {"fill": "#c0392b", "border": "#7f1d16", "label": "Changed",    "borderDashes": False},
        "touched":    {"fill": "#a14d42", "border": "#7a352c", "label": "Touched",    "borderDashes": [8, 4]},
        "testOnly":   {"fill": "#0b6e63", "border": "#064e46", "label": "Test-only",  "borderDashes": [2, 3]},
        "peripheral": {"fill": "#6e6510", "border": "#4a440b", "label": "Peripheral", "borderDashes": [12, 3, 2, 3]},
    },
    "type_colors": {
        "repo": "#b13a28", "subsystem": "#1d6fb8", "project": "#2c5fb3",
        "service": "#177245", "contract": "#6d28d9", "driver": "#8a5a00",
        "database": "#a91b3c", "messaging": "#7a5d00", "feature": "#0f6b6b",
        "external": "#4d5761",
    },
    "line": "#dde3e8",
    "dimmed": "#c3c9cf",
    "edge_affected": "#8a5a3a",
    "edge_dim": "#d7dce1",
    "edge_system": "#8f9aa5",
    "badge_text": "#ffffff",
    "node_highlight_border": "#1c2126",
}

THEMES = {"dark": PALETTE, "light": LIGHT_PALETTE}
