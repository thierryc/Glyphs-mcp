"""Glyphs 4 development checks. The separate frozen v1 suite is unchanged."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/glyphs-mcp-development"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    with contextlib.ExitStack():
        before = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(result)
        finally:
            sys.dont_write_bytecode = before
    return result


S = module("lean_scaffold", SKILL / "scripts/scaffold.py")
DOC = module("lean_docs", SKILL / "scripts/docs.py")


def scaffold(tmp_path, kind="reporter"):
    with contextlib.redirect_stdout(io.StringIO()):
        assert S.main(["create", kind, "--name", "Test Lens", "--developer", "Qualification", "--destination", str(tmp_path)]) == 0
    return tmp_path / ("Test Lens" + S.PLUGIN_SPECS[kind]["suffix"])


@pytest.mark.parametrize("kind", S.PLUGIN_SPECS)
def test_glyphs4_templates_and_exact_loader(tmp_path, kind):
    artifact = scaffold(tmp_path, kind)
    result = S.validate_artifact(artifact, "4")
    assert result["target"] == "4" and result["runtimeTested"] is False
    assert "sdk-loader-sha256" in result["checks"]
    expected = json.loads((SKILL / "assets/SOURCE.json").read_text())["loaderSha256"][kind]
    assert hashlib.sha256((artifact / "Contents/MacOS/plugin").read_bytes()).hexdigest() == expected
    resources = artifact / "Contents/Resources"
    assert (resources / "GlyphsSDK-LICENSE.txt").read_bytes() == (SKILL / "assets/GlyphsSDK-LICENSE.txt").read_bytes()
    provenance = json.loads((resources / "GlyphsSDK-SOURCE.json").read_text())
    assert provenance["templateKind"] == kind and provenance["loaderSha256"] == expected
    assert provenance["revision"] == json.loads((SKILL / "assets/SOURCE.json").read_text())["revision"]
    assert "https://github.com/schriftgestalt/GlyphsSDK" in (resources / "plugin.py").read_text()
    assert "sdk-attribution" in result["checks"]


@pytest.mark.parametrize("target", ["3", "both", "5"])
def test_other_hosts_rejected_before_creation(tmp_path, target):
    with pytest.raises(SystemExit) as exc:
        S.main(["create", "script", "--name", "No", "--target", target, "--destination", str(tmp_path)])
    assert exc.value.code == 2 and not list(tmp_path.iterdir())


@pytest.mark.parametrize("damage", ["loader", "syntax", "principal", "permission", "license", "attribution"])
def test_native_artifact_faults_rejected(tmp_path, damage):
    bundle = scaffold(tmp_path)
    if damage == "loader":
        (bundle / "Contents/MacOS/plugin").write_bytes(b"changed executable, not run")
    elif damage == "permission":
        (bundle / "Contents/MacOS/plugin").chmod(0o644)
    elif damage == "syntax":
        (bundle / "Contents/Resources/plugin.py").write_text("bad python (\n")
    elif damage == "license":
        (bundle / "Contents/Resources/GlyphsSDK-LICENSE.txt").unlink()
    elif damage == "attribution":
        (bundle / "Contents/Resources/GlyphsSDK-SOURCE.json").write_text("{}")
    else:
        path = bundle / "Contents/Info.plist"
        plist = plistlib.loads(path.read_bytes()); plist["NSPrincipalClass"] = "Missing"
        path.write_bytes(plistlib.dumps(plist))
    with pytest.raises((S.ScaffoldError, SyntaxError)):
        S.validate_artifact(bundle, "4")


def test_preserve_existing_artifact_and_provenance_failure(tmp_path, monkeypatch):
    artifact = scaffold(tmp_path)
    source = artifact / "Contents/Resources/plugin.py"
    before = source.read_bytes()
    with contextlib.redirect_stderr(io.StringIO()):
        assert S.main(["create", "reporter", "--name", "Test Lens", "--developer", "Qualification", "--destination", str(tmp_path)]) == 2
    assert source.read_bytes() == before
    monkeypatch.setattr(S, "ASSETS_ROOT", tmp_path / "missing")
    with pytest.raises(S.ScaffoldError, match="verification failed"):
        S.validate_artifact(artifact, "4")


def test_complete_corpus_coverage_and_hashes():
    rows, manifest = DOC.load()
    assert len(rows) > 641
    for row in rows:
        DOC.read(row)
        assert row["nativeVerification"] == "not-qualified-by-documentation"
        assert row["applicationTarget"] == "4"
    for source in manifest["sourceInventory"]:
        assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
    for support in manifest["supportFiles"]:
        assert hashlib.sha256((DOC.CORPUS / "docs" / support["path"]).read_bytes()).hexdigest() == support["checksum"]
        assert support["indexed"] is False
    assert any(r["path"].endswith("_Readme_Images/showplugin.png") for r in manifest["supportFiles"])
    handbook = list((ROOT / "Documentations/Markdown").glob("*.md"))
    assert len([r for r in rows if r["sourceKind"] == "glyphs-handbook"]) == len(handbook)
    assert any(r["path"].endswith("LICENSE") for r in rows)
    assert any(r["formatVersion"] == 3 for r in rows)
    assert any(r["formatVersion"] == 4 for r in rows)


def test_generator_rejects_missing_sources_and_v1_output(tmp_path, monkeypatch):
    generator = module("lean_generator", ROOT / "src/glyphs-mcp/scripts/generate_documentation.py")
    with pytest.raises(ValueError, match="v1 documentation"):
        generator.generate_lean_documentation(generator.OUTPUT_ROOT)
    monkeypatch.setattr(generator, "HANDBOOK_ROOT", tmp_path / "missing-handbook")
    with pytest.raises(FileNotFoundError, match="Required documentation source"):
        generator.generate_lean_documentation(tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("symbol", ["GSLayer.selection", "GSFont.selection", "GSLayer.paths", "GSLayer.shapes", "GSNode.position", "ReporterPlugin.drawTextAtPoint"])
def test_qualified_api_lookup(symbol):
    result = DOC.search(symbol, 1)
    assert result["results"][0]["symbol"] == symbol
    assert result["returnedCount"] == 1


@pytest.mark.parametrize("query,expected", [
    ("Which Glyphs plugin type draws an optional Edit View overlay?", "sdk:Python Templates/Reporter/README.md"),
    ("Which native collection contains selected nodes and other selected objects?", "api-section-340"),
    ("How do path and node indices behave when paths and components are interleaved?", "api-section-339"),
    ("How can a Reporter draw a label and react to selection or layer changes?", "sdk:Python Templates/Reporter/README.md"),
])
def test_task_questions_find_relevant_evidence_in_default_bound(query, expected):
    result = DOC.search(query)
    assert expected in [r["id"] for r in result["results"]]
    assert result["returnedCount"] == 5 and not result["complete"]


def test_exact_source_paths_and_template_metadata_remain_retrievable():
    rows, _ = DOC.load()
    row = next(r for r in rows if r["path"].endswith(".xib"))
    for query in (row["title"], row["id"], row["path"], row["sourcePath"]):
        found = DOC.search(query, 1)["results"][0]
        assert found["id"] == row["id"]
        assert DOC.get(found["id"])["checksum"] == row["checksum"]


def test_search_does_not_fabricate_matches_and_is_stable():
    assert DOC.search("zzzzneverdocumented9")["results"] == []
    first = DOC.search("ReporterPlugin drawTextAtPoint")
    assert first == DOC.search("ReporterPlugin drawTextAtPoint")
    assert first["results"][0]["symbol"] == "ReporterPlugin.drawTextAtPoint"


@pytest.mark.parametrize("query", ["ReporterPlugin", "ReporterPlugin.foregroundInViewCoords",
    "ReporterPlugin.foregroundInViewCoords()", "foregroundInViewCoords", "reporterplugin.foregroundinviewcoords"])
def test_reporter_owner_and_callback_rank_the_documented_template_first(query):
    result = DOC.search(query, 3)
    guide = result["results"][0]
    assert guide["id"] == "sdk:Python Templates/Reporter/README.md"
    assert "class ____PluginClassName____(ReporterPlugin):" in DOC.read(guide)
    assert guide["symbol"] is None  # Relevance does not invent API ownership metadata.
    assert result["returnedCount"] <= 3
    assert result["complete"] == (result["returnedCount"] == result["totalCount"])


@pytest.mark.parametrize("owner,guide", [
    ("SelectTool", "sdk:Python Templates/SelectTool/README.md"),
    ("PalettePlugin", "sdk:Python Templates/Palette/README.md"),
])
def test_primary_template_owner_not_incidental_examples(owner, guide):
    assert DOC.search(owner, 1)["results"][0]["id"] == guide


def test_unrelated_or_missing_members_do_not_promote_reporter_guide():
    guide = "sdk:Python Templates/Reporter/README.md"
    for query in ("PalettePlugin.foregroundInViewCoords", "ReporterPlugin.undocumentedCallback9"):
        assert guide not in [r["id"] for r in DOC.search(query, 3)["results"]]
    for symbol in ("ReporterPlugin.drawTextAtPoint", "GSLayer.selection", "GSFont.selection", "GSNode.position"):
        assert DOC.search(symbol, 1)["results"][0]["symbol"] == symbol


@pytest.mark.parametrize("symbol", ["divideCurve", "pointOnLine", "pointOnQuadratic", "distance", "addPoints",
    "subtractPoints", "scalePoint", "removeOverlap", "subtractPaths", "intersectPaths", "GetSaveFile",
    "GetOpenFile", "GetFolder", "Message", "AskString", "PickGlyphs", "LogToConsole", "LogError"])
def test_standalone_api_functions_never_inherit_menu_item_owner(symbol):
    result = DOC.search(symbol, 1)
    assert result["results"][0]["symbol"] == symbol
    rows, _ = DOC.load()
    assert not any(row.get("symbol") == "NSMenuItem." + symbol for row in rows)


def test_api_owner_transitions_and_bound_module_function():
    generator = module("owner_generator", ROOT / "src/glyphs-mcp/scripts/generate_documentation.py")
    source = """'''.. class:: First'''
def bound(self): pass
First.bound = bound
'''.. function:: bound()
.. class:: Second'''
'''.. attribute:: selection'''
def plain(): pass
'''.. function:: plain()'''
'''.. function:: uncertain()'''
"""
    symbols = [row[2] for row in generator._lean_api_sections(source)]
    assert symbols == [None, "First.bound", "Second.selection", "plain", None]
    assert DOC.search("GSFont.removeKerningForPair", 1)["results"][0]["symbol"] == "GSFont.removeKerningForPair"
    assert DOC.search("GSLayer.removeOverlap", 1)["results"][0]["symbol"] == "GSLayer.removeOverlap"


@pytest.mark.parametrize("damage", ["changed", "missing", "extra"])
def test_all_pinned_sdk_sources_are_required(tmp_path, monkeypatch, damage):
    generator = module("pin_generator", ROOT / "src/glyphs-mcp/scripts/generate_documentation.py")
    shutil.copytree(ROOT / "GlyphsSDK", tmp_path / "SDK")
    monkeypatch.setattr(generator, "SDK_ROOT", tmp_path / "SDK")
    changed = generator.SDK_ROOT / "ObjectWrapper/GlyphsApp/plugins.py"
    if damage == "changed":
        changed.write_text("# changed pinned input\n" + changed.read_text())
    elif damage == "missing":
        changed.unlink()
    else:
        (generator.SDK_ROOT / "undocumented.py").write_text("# extra input")
    with pytest.raises(ValueError, match="Pinned SDK sources changed"):
        generator.generate_lean_documentation(tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("case", ["manifest-missing", "manifest-type", "index-mismatch", "row-missing", "row-type"])
def test_missing_or_inconsistent_provenance_is_update_required(tmp_path, case):
    corpus = tmp_path / "corpus"
    shutil.copytree(DOC.CORPUS, corpus)
    manifest = json.loads((corpus / "manifest.json").read_text())
    index = json.loads((corpus / "index.json").read_text())
    row = next(r for r in index["documents"] if r["sourceKind"] == "glyphs-python-api")
    if case == "manifest-missing":
        del manifest["sourceRevision"]
    elif case == "manifest-type":
        manifest["sourceRevision"] = []
    elif case == "index-mismatch":
        index["sourceRevision"] = "a" * 40
    elif case == "row-missing":
        del row["sourceRevision"]
    else:
        row["sourcePath"] = []
    raw = json.dumps(index).encode(); (corpus / "index.json").write_bytes(raw)
    manifest["indexSha256"] = hashlib.sha256(raw).hexdigest()
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    for call in (lambda: DOC.search("GSLayer.selection", corpus=corpus), lambda: DOC.get("api-section-340", corpus=corpus)):
        with pytest.raises(DOC.DocsError) as error:
            call()
        assert error.value.code == "update_required"


def test_retrieval_bounds_unicode_and_complete_flags():
    result = DOC.search("Glyphs", 900)
    assert result["returnedCount"] == 20 < result["totalCount"] and not result["complete"]
    doc_id = "sdk:ObjectWrapper/GlyphsApp/__init__.py"
    first = DOC.get(doc_id)
    assert first["returnedChars"] == 4000 and first["nextOffset"] == 4000 and first["truncated"]
    assert not first["complete"]
    large = DOC.get(doc_id, max_chars=90000)
    assert large["returnedChars"] == 12000
    tail = DOC.get(doc_id, offset=first["totalChars"] - 3)
    assert tail["returnedChars"] == 3 and not tail["complete"] and not tail["truncated"] and tail["nextOffset"] is None
    small = DOC.get("api-section-340")
    assert small["complete"] and len(small["content"]) == small["totalChars"]


@pytest.mark.parametrize("case", ["index", "manifest", "page", "missing", "escape"])
def test_corrupt_corpus_is_update_required(tmp_path, case):
    shutil.copytree(DOC.CORPUS, tmp_path / "corpus")
    corpus = tmp_path / "corpus"
    rows, _ = DOC.load(corpus)
    row = next(r for r in rows if r["id"] == "api-section-340")
    if case in ("index", "manifest"):
        (corpus / (case + ".json")).write_text("[]")
    elif case == "page":
        (corpus / "docs" / row["path"]).write_text("corrupted")
    elif case == "missing":
        (corpus / "docs" / row["path"]).unlink()
    else:
        path = corpus / "docs" / row["path"]
        path.unlink(); outside = tmp_path / "outside"; outside.write_text("unrelated")
        path.symlink_to(outside)
    with pytest.raises(DOC.DocsError) as exc:
        DOC.get("api-section-340", corpus=corpus)
    assert exc.value.code == "update_required"


def test_invalid_requests_are_not_font_discovery_errors():
    for call in (lambda: DOC.search(""), lambda: DOC.get("api-section-340", -1), lambda: DOC.get("api-section-340", 999999)):
        with pytest.raises(DOC.DocsError) as exc:
            call()
        assert exc.value.code == "invalid_request"
    with pytest.raises(DOC.DocsError) as exc:
        DOC.get("../../outside")
    assert exc.value.code == "document_not_found" and "not a font" in str(exc.value)


def test_installed_copy_is_offline_and_repository_independent(tmp_path):
    dest = tmp_path / "installed"
    shutil.copytree(SKILL, dest)
    for args in (["search", "GSLayer.selection", "--limit", "1"], ["get", "api-section-340"]):
        result = subprocess.run([sys.executable, "-I", str(dest / "scripts/docs.py"), *args], cwd=tmp_path,
                                capture_output=True, text=True, check=True)
        assert json.loads(result.stdout)["ok"]
    source = (dest / "scripts/docs.py").read_text()
    assert not any(s in source for s in ("import GlyphsApp", "import requests", "import socket", "urllib.request"))


def test_entry_metadata_starter_and_private_boundaries():
    text = (SKILL / "SKILL.md").read_text()
    assert text.index("Glyphs may be") < text.index("For MCP access")
    assert "--target 4" in text and "scripts/scaffold.py" in text
    meta = yaml.safe_load((SKILL / "agents/openai.yaml").read_text())
    assert meta["interface"]["display_name"] == "Glyphs Vibe Coding"
    assert "$glyphs-mcp-development" in meta["interface"]["default_prompt"]
    assert "policy" not in meta
    assert 25 <= len(meta["interface"]["short_description"]) <= 64
    assert "bridge, sidecar and skills updated together" in text
    entry = (ROOT / "skills/glyphs/SKILL.md").read_text()
    assert entry.index("$glyphs-mcp-development") < entry.index("connection-session.md")
    connection = (ROOT / "skills/glyphs/references/connection-session.md").read_text()
    assert "Inspect the tool catalog" in connection
    assert yaml.safe_load((ROOT / "skills/glyphs/agents/openai.yaml").read_text())["policy"]["allow_implicit_invocation"] is False
    starter = ROOT / "macos-installer/GlyphsMCPInstaller"
    template = (starter / "Resources/Starter/AGENTS.md").read_text().strip()
    assert template in (starter / "Core/StarterProjectCreator.swift").read_text()
