"""palette.py — single source of colour truth for template and tests (WCAG-audited).

Values were tuned with the `dataviz` skill's accessible-palette method:
lightness/chroma bands and CVD (colour-vision-deficiency) separation were
checked with its `validate_palette.js` validator against this module's own
`bg` surface, in addition to the WCAG contrast gate in tests/test_palette.py.

One deliberate, documented exception: `changed` and `touched` share the red
hue family by design (severity gradient within one hue — see the tier
`label`s), so their CVD separation sits below the validator's floor. That is
mitigated the way the validator's own rules require for any sub-floor pair:
secondary encoding, never colour alone — each tier also carries a distinct
`borderDashes` pattern and a always-visible text `label` (see
tests/test_palette.py::test_tiers_not_colour_alone and ::test_tier_labels_present).
"""
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
}
