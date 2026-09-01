"""Export-to-Obsidian button: the report builds a vault (folder of markdown
notes) client-side and downloads it as a store-only zip — no dependencies, so
the report stays self-contained. We cannot execute the template's JS here (no
browser); as with test_template_a11y.py these are string-level gates on the
shipped source.
"""
from pathlib import Path
from changeatlas import render

PKG = Path(__file__).resolve().parent.parent / "changeatlas"
VIS = Path(__file__).resolve().parent.parent / "vendor" / "vis-network.min.js"


def _render():
    payload = {"release": "1.0", "generated": "2026-08-31",
               "nodes": [{"id": "a", "title": "A", "type": "service", "repo": "r", "summary": "s", "tags": []}],
               "edges": [], "typeStyle": {}, "edgeLabel": {},
               "impact": {"changed": ["a"], "touched": [], "testOnly": [], "peripheral": []},
               "details": {"a": {"stories": [], "prs": [], "prodFiles": 3, "testFiles": 0}}}
    return render.render(payload, PKG / "template.html", VIS)


def test_export_button_present():
    html = _render()
    assert 'id="export-obsidian"' in html
    assert "Export to Obsidian" in html


def test_zip_writer_is_store_only_and_dependency_free():
    html = _render()
    assert "function makeZip" in html
    assert "function crc32" in html
    # The three zip record signatures: local file header, central directory
    # entry, end-of-central-directory.
    for sig in ("0x04034b50", "0x02014b50", "0x06054b50"):
        assert sig in html, sig


def test_vault_notes_structure():
    html = _render()
    assert "function buildVaultFiles" in html
    # One note per component under Components/, plus a release index note.
    assert "'Components/'" in html
    assert "'Release '" in html
    # Notes link to each other with wikilinks and carry tier tags.
    assert "function wikiLink" in html
    assert "function sanitizeName" in html


def test_vault_filenames_are_safe_and_unique():
    html = _render()
    # Windows-illegal and Obsidian-link-breaking characters are stripped...
    assert 'replace(/[\\\\/:*?"<>|#^\\[\\]]/g' in html
    # ...and colliding titles get a numeric suffix rather than overwriting.
    assert "while (used.has(" in html


def test_vault_graph_preset_uses_tier_palette():
    html = _render()
    # .obsidian/graph.json colour groups mirror the impact tiers so the
    # vault's graph view opens looking like the impact map.
    assert "'.obsidian/graph.json'" in html
    assert "colorGroups" in html


def test_export_is_view_aware():
    # Exporting from System view produces a system vault: notes tagged by
    # component type (no release overlay), a type-grouped index note, and a
    # distinct zip name so the two exports don't overwrite each other.
    html = _render()
    assert "function systemIndexNote" in html
    assert "'System map" in html
    assert "'-system'" in html
    # System notes carry a type tag instead of a tier tag...
    assert "'  - ' + sanitizeName(n.type)" in html
    # ...and release details (stories/PRs) are omitted, same as the in-app
    # System view panel.
    assert "system ? null : DATA.details[n.id]" in html


def test_system_graph_preset_uses_type_palette():
    html = _render()
    # System-vault colour groups are built per component type from the
    # theme's per-type colours (impact vaults keep the tier groups).
    assert "function graphPreset(system)" in html
    assert "'tag:#' + sanitizeName(t)" in html


def test_story_and_pr_urls_go_through_safeurl():
    html = _render()
    # Same discipline as showNode/buildListView: exported links must be
    # http(s) or become inert.
    assert "](' + safeUrl(" in html
