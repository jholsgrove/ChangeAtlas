from changeatlas.palette import PALETTE, TYPE_COLORS

def _lum(hexcolor):
    r, g, b = (int(hexcolor[i:i+2], 16) / 255 for i in (1, 3, 5))
    def f(c): return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def test_text_contrast_aa():          # WCAG 1.4.3: 4.5:1 for text
    assert contrast(PALETTE["text"], PALETTE["bg"]) >= 4.5
    assert contrast(PALETTE["text"], PALETTE["panel_bg"]) >= 4.5
    assert contrast(PALETTE["link"], PALETTE["panel_bg"]) >= 4.5

def test_tier_fill_contrast_aa():     # WCAG 1.4.11: 3:1 for graphical objects
    for name, tier in PALETTE["tiers"].items():
        assert contrast(tier["fill"], PALETTE["bg"]) >= 3.0, name

def test_tiers_not_colour_alone():    # WCAG 1.4.1: distinct border treatment per tier
    dashes = [repr(t["borderDashes"]) for t in PALETTE["tiers"].values()]
    assert len(set(dashes)) == len(dashes)

def test_tier_labels_present():
    for tier in PALETTE["tiers"].values():
        assert tier["label"]

def test_type_colors_contrast():     # WCAG 1.4.11: 3:1 for graphical objects
    for name, hexcolor in TYPE_COLORS.items():
        assert contrast(hexcolor, PALETTE["bg"]) >= 3.0, name
