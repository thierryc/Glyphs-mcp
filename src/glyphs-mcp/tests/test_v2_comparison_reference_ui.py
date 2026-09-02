"""Pure UI-state contracts for the compact comparison-reference Palette."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.comparison_reference_ui import (  # noqa: E402
    initial_reference_drafts,
    reference_form_presentation,
    reference_presentation,
    reference_spec_from_draft,
    unavailable_reference_presentation,
)


def _status(
    kind="last_saved",
    *,
    state="ready",
    repository=None,
    revision=None,
    commit=None,
    font_path=None,
    stale=False,
    error=None,
    origin="default",
):
    reference = {"kind": kind}
    if kind == "local_git" and repository:
        reference["repositoryPath"] = repository
    if kind == "github" and repository:
        reference["repositoryUrl"] = repository
    if revision:
        reference["revision"] = revision
    if font_path:
        reference["fontPath"] = font_path
    resolved = None
    if kind != "last_saved" or font_path:
        resolved = {
            "kind": kind,
            "repository": repository,
            "requestedRevision": revision,
            "resolvedCommit": commit,
            "fontPath": font_path,
            "cacheState": "warm" if kind == "github" else "local",
            "fetchedAt": 1_700_000_000 if kind == "github" else None,
        }
    return {
        "state": state,
        "ready": state in {"ready", "stale_cached"},
        "reference": reference,
        "resolved": resolved,
        "stale": stale,
        "error": error,
        "origin": origin,
    }


class ReferencePresentationTests(unittest.TestCase):
    def test_last_saved_is_one_line_and_never_exposes_its_path_or_git_actions(self):
        public = _status("last_saved", font_path="/private/tmp/Family.glyphs")
        presentation = reference_presentation(public)

        self.assertEqual(presentation.primary, "Last Saved")
        self.assertEqual(presentation.secondary, "")
        self.assertNotIn("/private/tmp", presentation.tooltip)
        self.assertFalse(presentation.show_refresh)
        self.assertFalse(presentation.show_copy)
        self.assertIsNone(presentation.resolved_commit)

    def test_local_and_github_references_use_compact_identity_and_plain_tooltips(self):
        local = reference_presentation(
            _status(
                "local_git",
                repository="/Users/designer/TypeFamily",
                revision="main",
                commit="0123456789abcdef",
                font_path="sources/Family.glyphs",
                origin="agent",
            )
        )
        github = reference_presentation(
            _status(
                "github",
                repository="https://github.com/owner/repository.git",
                revision="release",
                commit="abcdef0123456789",
                font_path="Family.glyphspackage",
                origin="sidebar",
            )
        )

        self.assertEqual(local.primary, "Local · TypeFamily")
        self.assertEqual(local.secondary, "main @ 01234567 · sources/Family.glyphs")
        self.assertIn("Configured by: Agent", local.tooltip)
        self.assertNotIn("{", local.tooltip)
        self.assertEqual(github.primary, "owner/repository")
        self.assertEqual(
            github.secondary, "release @ abcdef01 · Family.glyphspackage"
        )
        self.assertTrue(github.show_refresh)
        self.assertTrue(github.show_copy)

    def test_progress_stale_and_error_states_are_explicit_text(self):
        resolving = reference_presentation(
            _status(
                "github",
                state="resolving",
                repository="owner/repository",
                revision="main",
            )
        )
        stale = reference_presentation(
            _status(
                "github",
                state="stale_cached",
                repository="owner/repository",
                revision="main",
                commit="1234567890abcdef",
                stale=True,
            )
        )
        failed = reference_presentation(
            _status(
                "local_git",
                repository="/tmp/repository",
                revision="missing",
                error={"code": "revision_not_found", "message": "Revision not found"},
            )
        )

        self.assertEqual(resolving.secondary, "Resolving…")
        self.assertFalse(resolving.show_refresh)
        self.assertTrue(stale.secondary.startswith("Cached · main @ 12345678"))
        self.assertEqual(failed.secondary, "Couldn’t update reference")
        self.assertIn("Error: Revision not found", failed.tooltip)

    def test_unavailable_state_has_no_contextual_actions(self):
        presentation = unavailable_reference_presentation("No active font document")
        self.assertEqual(presentation.primary, "Reference Unavailable")
        self.assertEqual(presentation.secondary, "No active font document")
        self.assertFalse(presentation.show_refresh)
        self.assertFalse(presentation.show_copy)


class ReferenceFormTests(unittest.TestCase):
    def test_form_reveals_only_fields_for_the_selected_source(self):
        saved = reference_form_presentation("last_saved", {}, advanced=False)
        local = reference_form_presentation(
            "local_git",
            {"repository": "", "revision": "HEAD", "fontPath": ""},
            advanced=False,
        )
        github = reference_form_presentation(
            "github",
            {"repository": "owner/repository", "revision": "main", "fontPath": ""},
            advanced=True,
        )

        self.assertEqual(saved.sheet_height, 146.0)
        self.assertEqual(saved.action_title, "Use Last Saved")
        self.assertFalse(saved.show_repository)
        self.assertFalse(saved.show_advanced)
        self.assertEqual(local.sheet_height, 224.0)
        self.assertTrue(local.show_repository)
        self.assertTrue(local.show_advanced)
        self.assertFalse(local.show_font_path)
        self.assertEqual(github.sheet_height, 266.0)
        self.assertTrue(github.show_font_path)

    def test_required_fields_and_advanced_path_use_domain_validation(self):
        missing_revision = reference_form_presentation(
            "github",
            {"repository": "owner/repository", "revision": "", "fontPath": ""},
            advanced=False,
        )
        invalid_host = reference_form_presentation(
            "github",
            {
                "repository": "https://gitlab.com/owner/repository",
                "revision": "main",
                "fontPath": "",
            },
            advanced=False,
        )
        invalid_path = reference_form_presentation(
            "local_git",
            {"repository": "", "revision": "HEAD", "fontPath": "../Family.glyphs"},
            advanced=True,
        )

        self.assertFalse(missing_revision.action_enabled)
        self.assertIn("branch, tag, or commit", missing_revision.validation_message)
        self.assertFalse(invalid_host.action_enabled)
        self.assertIn("github.com", invalid_host.validation_message)
        self.assertFalse(invalid_path.action_enabled)
        self.assertIn("must not escape", invalid_path.validation_message)

    def test_drafts_preserve_each_git_source_and_local_defaults_to_head(self):
        drafts = initial_reference_drafts(
            {
                "kind": "github",
                "repositoryUrl": "owner/repository",
                "revision": "release",
                "fontPath": "sources/Family.glyphs",
            }
        )

        self.assertEqual(drafts["local_git"]["revision"], "HEAD")
        self.assertEqual(drafts["github"]["revision"], "release")
        self.assertEqual(
            reference_spec_from_draft("github", drafts["github"]),
            {
                "kind": "github",
                "revision": "release",
                "repositoryUrl": "https://github.com/owner/repository.git",
                "fontPath": "sources/Family.glyphs",
            },
        )

    def test_native_palette_source_has_no_duplicate_overlay_control(self):
        source = (
            V2_SOURCE / "glyphs_mcp_v2" / "inspector_palette.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Show Overlay", source)
        self.assertNotIn("toggleComparisonOverlay", source)
        self.assertIn("class GlyphsMCPComparisonReferencePalette", source)
        self.assertIn("REFERENCE_PALETTE_HEIGHT = 52", source)


if __name__ == "__main__":
    unittest.main()
