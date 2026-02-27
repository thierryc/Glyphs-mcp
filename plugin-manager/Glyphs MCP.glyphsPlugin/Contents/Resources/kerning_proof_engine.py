# encoding: utf-8

"""Helpers for generating kerning proof strings.

This module is intentionally GlyphsApp-free so it can be unit-tested outside of
Glyphs. The MCP tools can import and use it from inside the plug-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class ProofGlyph:
    """A glyph reference usable for proofing.

    Attributes:
        name: Glyph name (e.g. "A", "A.sc", "adieresis").
        unicode: Optional single Unicode character that maps to this glyph in
            the current font. When provided for all glyphs in a token, the
            token can be rendered as pure Unicode for readability.
    """

    name: str
    unicode: str | None = None

    def has_unicode(self) -> bool:
        return isinstance(self.unicode, str) and len(self.unicode) == 1


def normalize_rendering_mode(rendering: str) -> Tuple[str, List[str]]:
    """Normalize a rendering mode and return (mode, warnings)."""

    warnings: List[str] = []
    mode = (rendering or "").strip().lower()
    if mode not in ("hybrid", "unicode", "glyph_names"):
        warnings.append("Invalid rendering mode '{}'; using 'hybrid'.".format(rendering))
        mode = "hybrid"
    return mode, warnings


def render_token(glyphs: Sequence[ProofGlyph], rendering: str = "hybrid") -> Tuple[str, List[str]]:
    """Render a single token without inserting spaces between glyphs.

    Rules:
      - 'glyph_names': always use '/name/name' slash-chains.
      - 'hybrid'/'unicode': use Unicode only if *all* glyphs have Unicode,
        otherwise fall back to a slash-chain.

    Returns (token, warnings).
    """

    mode, warnings = normalize_rendering_mode(rendering)

    if mode in ("hybrid", "unicode"):
        if all(g.has_unicode() for g in glyphs):
            token = "".join(g.unicode or "" for g in glyphs)
            return token, warnings
        if mode == "unicode":
            warnings.append("Some glyphs lack Unicode; used /glyphName fallback in 'unicode' mode.")

    token = "/" + "/".join(g.name for g in glyphs)
    return token, warnings


def render_tokens(tokens: Sequence[Sequence[ProofGlyph]], rendering: str = "hybrid") -> Tuple[List[str], List[str]]:
    """Render many tokens and collect warnings."""

    out: List[str] = []
    warnings: List[str] = []
    for token in tokens:
        rendered, w = render_token(token, rendering=rendering)
        out.append(rendered)
        warnings.extend(w)
    return out, warnings


def pack_tokens(tokens: Sequence[str], per_line: int = 12) -> str:
    """Pack already-rendered tokens into lines."""

    if per_line <= 0:
        per_line = 12

    lines: List[str] = []
    current: List[str] = []
    for tok in tokens:
        if tok is None:
            continue
        tok = str(tok)
        if not tok:
            continue
        current.append(tok)
        if len(current) >= per_line:
            lines.append(" ".join(current))
            current = []

    if current:
        lines.append(" ".join(current))

    return "\n".join(lines)


def assemble_tab_text(
    *,
    sections: Sequence[Tuple[str, Sequence[Sequence[ProofGlyph]]]],
    rendering: str = "hybrid",
    per_line: int = 12,
) -> Tuple[str, List[str]]:
    """Assemble a single proof string with headings and packed tokens."""

    mode, warnings = normalize_rendering_mode(rendering)
    if per_line <= 0:
        per_line = 12

    parts: List[str] = []
    for title, tokens in sections:
        title = (title or "").strip()
        if title:
            parts.append(title)
            parts.append("")

        rendered, w = render_tokens(tokens, rendering=mode)
        warnings.extend(w)
        parts.append(pack_tokens(rendered, per_line=per_line))
        parts.append("")

    text = "\n".join(parts).rstrip("\n")
    return text, warnings

