"""render.py — embed the impact payload into template.html (token replacement)."""
import json
from pathlib import Path

from . import palette


def render(payload: dict, template_path, vis_path) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    vislib = Path(vis_path).read_text(encoding="utf-8")
    title = f"Release {payload['release']} — ChangeAtlas"
    # '<\/' keeps '</script>' inside string values from terminating the script block.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (template
            .replace("/*__TITLE__*/", title)
            .replace("/*__VISLIB__*/", vislib)
            .replace("/*__DATA__*/", data)
            .replace("/*__PALETTE__*/", json.dumps(palette.PALETTE)))
