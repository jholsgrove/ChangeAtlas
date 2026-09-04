"""render.py — embed the impact payload into template.html (token replacement)."""
import base64
import json
from pathlib import Path

from . import palette

# logo-{light,dark}.svg are the full lockup (globe + wordmark) on a
# 1254x1254 canvas; the sidebar shows a 36px icon, so the render crops the
# viewBox to the globe (centre 631,506, radius 321 + 12px stroke).
GLOBE_VIEWBOX = "296 171 670 670"


def _logo_data_uri(path: Path) -> str:
    svg = path.read_text(encoding="utf-8").replace('viewBox="0 0 1254 1254"',
                                                    f'viewBox="{GLOBE_VIEWBOX}"', 1)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def render(payload: dict, template_path, vis_path) -> str:
    template_path = Path(template_path)
    template = template_path.read_text(encoding="utf-8")
    vislib = Path(vis_path).read_text(encoding="utf-8")
    title = f"Release {payload['release']} — ChangeAtlas"
    # '<\/' keeps '</script>' inside string values from terminating the script block.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (template
            .replace("/*__TITLE__*/", title)
            .replace("/*__VISLIB__*/", vislib)
            .replace("/*__DATA__*/", data)
            .replace("/*__PALETTES__*/", json.dumps(palette.THEMES))
            .replace("/*__LOGO_LIGHT__*/", _logo_data_uri(template_path.parent / "logo-light.svg"))
            .replace("/*__LOGO_DARK__*/", _logo_data_uri(template_path.parent / "logo-dark.svg")))
