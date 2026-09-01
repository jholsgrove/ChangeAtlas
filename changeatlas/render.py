"""render.py — embed the impact payload into template.html (token replacement)."""
import base64
import json
from pathlib import Path

from . import palette


def _logo_data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


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
            .replace("/*__LOGO_LIGHT__*/", _logo_data_uri(template_path.parent / "logo-light.png"))
            .replace("/*__LOGO_DARK__*/", _logo_data_uri(template_path.parent / "logo-dark.png")))
