import pytest

from changeatlas.palette import LIGHT_PALETTE, PALETTE, THEMES, TYPE_COLORS


def _lum(hexcolor):
    r, g, b = (int(hexcolor[i:i+2], 16) / 255 for i in (1, 3, 5))
    def f(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

THEME_IDS = list(THEMES)


def test_themes_registry():
    assert THEMES == {"dark": PALETTE, "light": LIGHT_PALETTE}


def test_light_palette_same_shape_as_dark():
    assert set(LIGHT_PALETTE) == set(PALETTE)
    assert set(LIGHT_PALETTE["tiers"]) == set(PALETTE["tiers"])
    for name in PALETTE["tiers"]:
        assert set(LIGHT_PALETTE["tiers"][name]) == set(PALETTE["tiers"][name])
    assert set(LIGHT_PALETTE["type_colors"]) == set(PALETTE["type_colors"])


def test_dark_type_colors_backwards_compatible():
    # __main__.py builds the payload's typeStyle from module-level TYPE_COLORS;
    # the dark theme must carry the same values.
    assert PALETTE["type_colors"] == TYPE_COLORS


@pytest.mark.parametrize("theme", THEME_IDS)
def test_text_contrast_aa(theme):          # WCAG 1.4.3: 4.5:1 for text
    p = THEMES[theme]
    assert contrast(p["text"], p["bg"]) >= 4.5
    assert contrast(p["text"], p["panel_bg"]) >= 4.5
    assert contrast(p["link"], p["panel_bg"]) >= 4.5


@pytest.mark.parametrize("theme", THEME_IDS)
def test_tier_fill_contrast_aa(theme):     # WCAG 1.4.11: 3:1 for graphical objects
    p = THEMES[theme]
    for name, tier in p["tiers"].items():
        assert contrast(tier["fill"], p["bg"]) >= 3.0, (theme, name)


@pytest.mark.parametrize("theme", THEME_IDS)
def test_tiers_not_colour_alone(theme):    # WCAG 1.4.1: distinct border treatment per tier
    dashes = [repr(t["borderDashes"]) for t in THEMES[theme]["tiers"].values()]
    assert len(set(dashes)) == len(dashes)


@pytest.mark.parametrize("theme", THEME_IDS)
def test_tier_labels_present(theme):
    for tier in THEMES[theme]["tiers"].values():
        assert tier["label"]


@pytest.mark.parametrize("theme", THEME_IDS)
def test_type_colors_contrast(theme):     # WCAG 1.4.11: 3:1 for graphical objects
    p = THEMES[theme]
    for name, hexcolor in p["type_colors"].items():
        assert contrast(hexcolor, p["bg"]) >= 3.0, (theme, name)


@pytest.mark.parametrize("theme", THEME_IDS)
def test_badge_text_contrast_aa(theme):   # WCAG 1.4.3: badge text sits on tier/type fills
    p = THEMES[theme]
    for name, tier in p["tiers"].items():
        assert contrast(p["badge_text"], tier["fill"]) >= 4.5, (theme, name)
    for name, hexcolor in p["type_colors"].items():
        assert contrast(p["badge_text"], hexcolor) >= 4.5, (theme, name)


@pytest.mark.parametrize("theme", THEME_IDS)
def test_graph_chrome_colors_present(theme):
    # Colours the template JS previously hard-coded must come from the theme
    # so both modes control them.
    p = THEMES[theme]
    for key in ("line", "dimmed", "edge_affected", "edge_dim", "edge_system",
                "badge_text", "node_highlight_border",
                "bubble", "bubble_border", "bubble_peripheral"):
        assert key in p, (theme, key)


@pytest.mark.parametrize("theme", THEME_IDS)
def test_bubble_border_contrast(theme):
    # Grouped-mode bubbles: labels are drawn in the theme text colour over the
    # canvas bg (covered by test_text_contrast_aa). The peripheral bubble's
    # border is the tier border and must stay a 3:1 graphical object; the
    # plain bubble border is deliberately quiet but must remain visible.
    p = THEMES[theme]
    assert contrast(p["tiers"]["peripheral"]["border"], p["bg"]) >= 3.0
    assert contrast(p["bubble_border"], p["bg"]) >= 1.5
