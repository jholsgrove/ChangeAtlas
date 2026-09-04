"""CSS selectors for the rendered report (changeatlas/template.html).

Every browser test and page object reaches the DOM through these constants,
so a renamed id in the template is a one-line fix here.
"""

SIDE_PANEL = "#side"
SIDE_TOGGLE = "#side-toggle"
GRAPH_CANVAS = "#graph canvas"
EXPORT_PNG = "#export-png"
RESET = "#reset"
LENS_ROW = "#lens-row"
LENS_BUTTON = "#lens-row button"
VIEW_BUTTON = "#view-{name}"      # format with impact | system | list
LAYOUT_OVERLAY = "#layout-overlay"
ROLL_WRAP = "#roll-wrap"
LENS_CAPTION = "#lens-caption"
LENS_NOTE = "#lens-note"
