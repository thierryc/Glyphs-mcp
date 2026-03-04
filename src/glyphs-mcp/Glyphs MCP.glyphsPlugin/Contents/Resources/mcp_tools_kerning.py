# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import json

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _glyph_unicode_char,
    _load_andre_fuchs_relevant_pairs,
    _open_tab_on_main_thread,
    _safe_json,
    _set_kerning_pairs_on_main_thread,
)

import kerning_collision_engine
import kerning_proof_engine


@mcp.tool()
async def set_kerning_pair(
    font_index: int = 0,
    master_id: str = None,
    left: str = None,
    right: str = None,
    value: int = None,
) -> str:
    """Set kerning value for a specific pair.

    Args:
        font_index (int): Index of the font (0-based). Defaults to 0.
        master_id (str): Master ID. If None, uses the first master. Optional.
        left (str): Left glyph name or kerning group (e.g., "@MMK_L_A"). Required.
        right (str): Right glyph name or kerning group (e.g., "@MMK_R_V"). Required.
        value (int): Kerning value. Use 0 to remove kerning. Required.

    Returns:
        str: JSON-encoded result with success status.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        if not left or not right:
            return json.dumps(
                {"error": "Both left and right glyph/group names are required"}
            )

        if value is None:
            return json.dumps({"error": "Kerning value is required"})

        font = Glyphs.fonts[font_index]

        if master_id is None:
            master_id = font.masters[0].id

        # Initialize kerning dictionary if needed
        if master_id not in font.kerning:
            font.kerning[master_id] = {}

        if left not in font.kerning[master_id]:
            font.kerning[master_id][left] = {}

        if value == 0:
            # Remove kerning if it exists
            if right in font.kerning[master_id][left]:
                del font.kerning[master_id][left][right]
            message = "Removed kerning for '{}' - '{}'".format(left, right)
        else:
            # Set kerning value
            font.kerning[master_id][left][right] = value
            message = "Set kerning for '{}' - '{}' to {}".format(left, right, value)

        # Send notification
        Glyphs.showNotification("Kerning Updated", message)

        return json.dumps(
            {
                "success": True,
                "message": message,
                "kerning": {
                    "left": left,
                    "right": right,
                    "value": value,
                    "masterId": master_id,
                },
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def generate_kerning_tab(
    font_index: int = 0,
    master_id: str = None,
    relevant_limit: int = 2000,
    missing_limit: int = 1000,
    audit_limit: int = 200,
    per_line: int = 12,
    glyph_names: list = None,
    rendering: str = "hybrid",
) -> str:
    """Generate a kerning review tab and open it in Glyphs.

    The proof text includes:
      1) A worklist of missing high-relevance pairs (Andre Fuchs dataset),
         not covered by explicit kerning in the master (glyph or class).
      2) An audit section of tightest + widest existing explicit kerning pairs.

    Args:
        font_index: Index of the font (0-based). Defaults to 0.
        master_id: Master ID. If None, uses the first master.
        relevant_limit: How many dataset pairs to consider (top-N).
        missing_limit: Cap for the missing-pairs worklist (pairs, not tokens).
        audit_limit: Cap for tightest and widest explicit kerning pairs (pairs, not tokens).
        per_line: Number of tokens per line in the proof text.
        glyph_names: Optional list of glyph names to focus on (keep only pairs where left or right is in this list).
        rendering: One of "hybrid" (default), "unicode", or "glyph_names".

    Returns:
        JSON payload with the generated text and metadata.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return json.dumps(
                {
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts))
                }
            )

        font = Glyphs.fonts[font_index]
        if not font.masters:
            return json.dumps({"error": "Font has no masters"})

        if master_id is None:
            master_id = font.masters[0].id

        dataset_meta, dataset_pairs, warnings = _load_andre_fuchs_relevant_pairs()
        pair_count = int(dataset_meta.get("pairCount") or 0)
        used_top_n = min(max(int(relevant_limit or 0), 0), pair_count)

        focus = None
        if glyph_names:
            try:
                focus = set([str(n) for n in glyph_names if n])
            except Exception:
                focus = None
        if focus is not None and len(focus) == 0:
            focus = None

        # Build lookups from the font.
        unicode_to_glyphname = {}
        unicode_to_glyphname_fallback = {}
        glyphname_to_unicode = {}
        left_group_rep = {}
        right_group_rep = {}
        glyph_left_group = {}
        glyph_right_group = {}

        for glyph in font.glyphs:
            name = getattr(glyph, "name", None)
            if not name:
                continue

            ch = _glyph_unicode_char(glyph)
            if ch:
                if name not in glyphname_to_unicode:
                    glyphname_to_unicode[name] = ch

                if getattr(glyph, "export", True):
                    if ch not in unicode_to_glyphname:
                        unicode_to_glyphname[ch] = name
                else:
                    if ch not in unicode_to_glyphname_fallback:
                        unicode_to_glyphname_fallback[ch] = name

            lgrp = getattr(glyph, "leftKerningGroup", None)
            rgrp = getattr(glyph, "rightKerningGroup", None)
            glyph_left_group[name] = lgrp
            glyph_right_group[name] = rgrp

            if lgrp and lgrp not in left_group_rep:
                left_group_rep[lgrp] = name
            if rgrp and rgrp not in right_group_rep:
                right_group_rep[rgrp] = name

        for ch, name in unicode_to_glyphname_fallback.items():
            if ch not in unicode_to_glyphname:
                unicode_to_glyphname[ch] = name

        # Build explicit kerning set + numeric list for sorting.
        explicit = set()
        existing_numeric = []
        kerning = font.kerning.get(master_id, {}) or {}
        for left_key, right_dict in kerning.items():
            if not right_dict:
                continue
            for right_key, value in right_dict.items():
                explicit.add((str(left_key), str(right_key)))
                v = _coerce_numeric(value)
                if v is not None:
                    existing_numeric.append((str(left_key), str(right_key), float(v)))

        ProofGlyph = kerning_proof_engine.ProofGlyph

        def _context_chars(left_char, right_char):
            try:
                if left_char.isupper() and right_char.isupper():
                    return ("H", "O")
                if left_char.islower() and right_char.islower():
                    return ("n", "o")
            except Exception:
                pass
            return ("H", "O")

        def _context_glyph_name(ch):
            return unicode_to_glyphname.get(ch) or ch

        def _pair_tokens(left_name, left_char, right_name, right_char):
            stem_ch, round_ch = _context_chars(left_char or "", right_char or "")
            stem_name = _context_glyph_name(stem_ch)
            round_name = _context_glyph_name(round_ch)

            return [
                [
                    ProofGlyph(stem_name, stem_ch),
                    ProofGlyph(left_name, left_char),
                    ProofGlyph(right_name, right_char),
                    ProofGlyph(stem_name, stem_ch),
                ],
                [
                    ProofGlyph(round_name, round_ch),
                    ProofGlyph(left_name, left_char),
                    ProofGlyph(right_name, right_char),
                    ProofGlyph(round_name, round_ch),
                ],
            ]

        # 1) Missing relevant pairs worklist.
        missing_tokens = []
        missing_included = 0
        missing_skipped_no_glyph = 0

        missing_cap = max(int(missing_limit or 0), 0)
        if missing_cap > 0:
            for left_char, right_char in dataset_pairs[:used_top_n]:
                left_name = unicode_to_glyphname.get(left_char)
                right_name = unicode_to_glyphname.get(right_char)
                if not left_name or not right_name:
                    missing_skipped_no_glyph += 1
                    continue

                if focus is not None and (left_name not in focus and right_name not in focus):
                    continue

                left_group = glyph_left_group.get(left_name)
                right_group = glyph_right_group.get(right_name)

                candidates = [(left_name, right_name)]
                if right_group:
                    candidates.append((left_name, "@MMK_R_" + str(right_group)))
                if left_group:
                    candidates.append(("@MMK_L_" + str(left_group), right_name))
                if left_group and right_group:
                    candidates.append(("@MMK_L_" + str(left_group), "@MMK_R_" + str(right_group)))

                covered = False
                for cand in candidates:
                    if cand in explicit:
                        covered = True
                        break
                if covered:
                    continue

                missing_tokens.extend(_pair_tokens(left_name, left_char, right_name, right_char))
                missing_included += 1
                if missing_included >= missing_cap:
                    break

        # 2) Existing extremes audit (tightest + widest).
        def _rep_for_key(key, is_left):
            if key.startswith("@MMK_L_"):
                group = key[len("@MMK_L_") :]
                rep = left_group_rep.get(group)
                if rep:
                    return rep
                try:
                    if font.glyphs[group]:
                        return group
                except Exception:
                    return None
                return None

            if key.startswith("@MMK_R_"):
                group = key[len("@MMK_R_") :]
                rep = right_group_rep.get(group)
                if rep:
                    return rep
                try:
                    if font.glyphs[group]:
                        return group
                except Exception:
                    return None
                return None

            try:
                return key if font.glyphs[key] else None
            except Exception:
                return None

        def _unicode_for_name(name):
            uni = glyphname_to_unicode.get(name)
            if uni:
                return uni
            if isinstance(name, str) and len(name) == 1:
                return name
            return None

        tight_tokens = []
        wide_tokens = []
        tight_included = 0
        wide_included = 0

        audit_cap = max(int(audit_limit or 0), 0)
        tightest = sorted(existing_numeric, key=lambda t: t[2])[:audit_cap]
        widest = sorted(existing_numeric, key=lambda t: t[2], reverse=True)[:audit_cap]

        for left_key, right_key, _value in tightest:
            left_name = _rep_for_key(left_key, True)
            right_name = _rep_for_key(right_key, False)
            if not left_name or not right_name:
                continue
            tight_tokens.extend(
                _pair_tokens(
                    left_name,
                    _unicode_for_name(left_name),
                    right_name,
                    _unicode_for_name(right_name),
                )
            )
            tight_included += 1

        for left_key, right_key, _value in widest:
            left_name = _rep_for_key(left_key, True)
            right_name = _rep_for_key(right_key, False)
            if not left_name or not right_name:
                continue
            wide_tokens.extend(
                _pair_tokens(
                    left_name,
                    _unicode_for_name(left_name),
                    right_name,
                    _unicode_for_name(right_name),
                )
            )
            wide_included += 1

        sections = [
            ("MISSING RELEVANT PAIRS (Andre Fuchs)", missing_tokens),
            ("EXISTING KERNING OUTLIERS (Tightest)", tight_tokens),
            ("EXISTING KERNING OUTLIERS (Widest)", wide_tokens),
        ]

        text, engine_warnings = kerning_proof_engine.assemble_tab_text(
            sections=sections,
            rendering=rendering,
            per_line=per_line,
        )

        warnings.extend(engine_warnings)

        # Deduplicate warnings, keep the payload small.
        deduped = []
        seen = set()
        for w in warnings:
            if not w:
                continue
            if w in seen:
                continue
            seen.add(w)
            deduped.append(w)
            if len(deduped) >= 12:
                break

        opened_tab = False
        try:
            _open_tab_on_main_thread(font, text)
            opened_tab = True
        except Exception as exc:
            deduped.append("Failed to open Glyphs tab: {}".format(exc))

        return json.dumps(
            {
                "success": True,
                "fontIndex": font_index,
                "masterId": master_id,
                "openedTab": opened_tab,
                "dataset": {
                    "id": dataset_meta.get("id") or "andre_fuchs_relevant_pairs",
                    "pairCount": pair_count,
                    "usedTopN": used_top_n,
                },
                "counts": {
                    "missingRelevantIncluded": missing_included,
                    "missingRelevantSkippedNoGlyph": missing_skipped_no_glyph,
                    "existingTightIncluded": tight_included,
                    "existingWideIncluded": wide_included,
                },
                "warnings": deduped,
                "text": text,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


def _kerning_bumper_analyze(
    *,
    font,
    master_id,
    dataset_pairs,
    relevant_limit,
    include_existing,
    pair_limit,
    glyph_names,
    min_gap,
    scan_mode,
    scan_heights,
    dense_step,
    bands,
    target_gap,
    max_delta,
    explicit_pairs=None,
):
    """Compute kerning collision/gap measurements + deterministic bumper suggestions (no mutation)."""

    warnings = []

    scan_mode_norm, w = kerning_collision_engine.normalize_scan_mode(scan_mode)
    warnings.extend(w)

    scan_heights_norm, w = kerning_collision_engine.normalize_scan_heights(scan_heights)
    warnings.extend(w)

    try:
        min_gap_f = float(min_gap)
    except Exception:
        min_gap_f = 5.0
        warnings.append("Invalid min_gap; using 5.0.")

    try:
        target_gap_f = float(target_gap)
    except Exception:
        target_gap_f = min_gap_f

    try:
        dense_step_f = float(dense_step)
    except Exception:
        dense_step_f = 10.0
        warnings.append("Invalid dense_step; using 10.0.")

    if dense_step_f <= 0:
        dense_step_f = 10.0
        warnings.append("dense_step must be > 0; using 10.0.")

    try:
        bands_i = int(bands)
    except Exception:
        bands_i = 8
        warnings.append("Invalid bands; using 8.")
    if bands_i <= 0:
        bands_i = 8

    try:
        max_delta_i = int(max_delta)
    except Exception:
        max_delta_i = 200
        warnings.append("Invalid max_delta; using 200.")
    if max_delta_i < 0:
        max_delta_i = 0

    focus = set(glyph_names or []) if glyph_names else None

    glyph_maps = kerning_collision_engine.build_glyph_maps(getattr(font, "glyphs", []) or [])
    unicode_to_glyphname = glyph_maps.get("unicodeToGlyphname") or {}
    glyphname_to_unicode = glyph_maps.get("glyphnameToUnicode") or {}
    name_set = glyph_maps.get("nameSet") or set()
    id_to_name = glyph_maps.get("idToName") or {}
    left_key_group_rep = glyph_maps.get("leftKeyGroupRep") or {}
    right_key_group_rep = glyph_maps.get("rightKeyGroupRep") or {}

    kerning_master = font.kerning.get(master_id, {}) or {}

    candidate_counts = {
        "pairsCandidate": 0,
        "pairsMeasured": 0,
        "pairsSkippedNoGlyph": 0,
        "pairsSkippedNoOverlap": 0,
        "pairsSkippedNoBounds": 0,
    }

    used_top_n = min(max(int(relevant_limit or 0), 0), len(dataset_pairs or []))

    if explicit_pairs is not None:
        pairs = []
        seen = set()
        for item in explicit_pairs or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            left_name = str(item[0])
            right_name = str(item[1])
            if not left_name or not right_name:
                continue
            pair = (left_name, right_name)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(pair)

        candidate_counts["pairsCandidate"] = len(pairs)
    else:
        pairs, counts = kerning_collision_engine.build_candidate_pairs(
            dataset_pairs=dataset_pairs or [],
            unicode_to_glyphname=unicode_to_glyphname,
            relevant_limit=int(relevant_limit or 0),
            include_existing=bool(include_existing),
            kerning_master=kerning_master,
            name_set=name_set,
            id_to_name=id_to_name,
            left_key_group_rep=left_key_group_rep,
            right_key_group_rep=right_key_group_rep,
            focus=focus,
            pair_limit=int(pair_limit or 0),
        )
        candidate_counts["pairsCandidate"] = len(pairs)
        candidate_counts["pairsSkippedNoGlyph"] += int(counts.get("pairsSkippedNoGlyph") or 0)

    collisions = []
    safe_gaps = []

    # Measure.
    for left_name, right_name in pairs:
        left_glyph = font.glyphs[left_name] if left_name else None
        right_glyph = font.glyphs[right_name] if right_name else None
        if not left_glyph or not right_glyph:
            candidate_counts["pairsSkippedNoGlyph"] += 1
            continue

        try:
            left_layer = left_glyph.layers[master_id]
            right_layer = right_glyph.layers[master_id]
        except Exception:
            left_layer = None
            right_layer = None

        if not left_layer or not right_layer:
            candidate_counts["pairsSkippedNoBounds"] += 1
            continue

        lb = kerning_collision_engine.bounds_tuple(left_layer)
        rb = kerning_collision_engine.bounds_tuple(right_layer)
        if not lb or not rb:
            candidate_counts["pairsSkippedNoBounds"] += 1
            continue

        overlap = kerning_collision_engine.overlap_y_range(lb, rb)
        if not overlap:
            candidate_counts["pairsSkippedNoOverlap"] += 1
            continue

        left_id = getattr(left_glyph, "id", None)
        right_id = getattr(right_glyph, "id", None)
        left_group = getattr(left_glyph, "rightKerningGroup", None)
        right_group = getattr(right_glyph, "leftKerningGroup", None)

        left_class_key = "@MMK_L_" + str(left_group) if left_group else None
        right_class_key = "@MMK_R_" + str(right_group) if right_group else None

        kerning_value, source = kerning_collision_engine.resolve_explicit_kerning_value(
            kerning_master=kerning_master,
            left_glyph_id=str(left_id) if left_id else None,
            left_glyph_name=left_name,
            left_class_key=left_class_key,
            right_glyph_id=str(right_id) if right_id else None,
            right_glyph_name=right_name,
            right_class_key=right_class_key,
        )

        # If available, prefer Glyphs' kerningForPair() as a sanity check / fallback.
        try:
            kv = font.kerningForPair(master_id, left_name, right_name)
            kvf = _coerce_numeric(kv)
            if kvf is not None:
                kerning_value = float(kvf)
        except Exception:
            pass

        measured = kerning_collision_engine.measure_pair_min_gap(
            left_layer=left_layer,
            right_layer=right_layer,
            kerning_value=float(kerning_value),
            scan_mode=scan_mode_norm,
            scan_heights=scan_heights_norm,
            dense_step=dense_step_f,
            bands=bands_i,
            include_components=True,
            target_gap=target_gap_f,
        )

        if measured is None:
            candidate_counts["pairsSkippedNoBounds"] += 1
            continue

        candidate_counts["pairsMeasured"] += 1

        # Bumper suggestion (integer kerning exception).
        suggestion = kerning_collision_engine.compute_bumper_suggestion(
            kerning_value=float(kerning_value),
            measured_min_gap=float(measured.min_gap),
            target_gap=float(target_gap_f),
            max_delta=int(max_delta_i),
        )

        record = {
            "left": left_name,
            "right": right_name,
            "kerningValue": float(kerning_value),
            "kerningSource": {"leftKey": source.left_key, "rightKey": source.right_key},
            "minGap": float(measured.min_gap),
            "worstY": float(measured.worst_y) if measured.worst_y is not None else None,
            "bandMinGaps": list(measured.band_min_gaps or []),
            "bumperDelta": float(suggestion.bumper_delta),
            "recommendedException": int(suggestion.recommended_exception),
            "refined": bool(measured.refined),
            "sampleCount": int(measured.sample_count),
        }

        if float(measured.min_gap) < float(target_gap_f):
            collisions.append(record)
        else:
            safe_gaps.append(
                {
                    "left": left_name,
                    "right": right_name,
                    "kerningValue": float(kerning_value),
                    "minGap": float(measured.min_gap),
                }
            )

    return {
        "warnings": warnings,
        "scanMode": scan_mode_norm,
        "scanHeights": scan_heights_norm,
        "denseStep": dense_step_f,
        "bands": bands_i,
        "minGap": min_gap_f,
        "targetGap": target_gap_f,
        "maxDelta": max_delta_i,
        "usedTopN": used_top_n,
        "counts": candidate_counts,
        "collisions": collisions,
        "safeGaps": safe_gaps,
        "glyphnameToUnicode": glyphname_to_unicode,
        "unicodeToGlyphname": unicode_to_glyphname,
    }


@mcp.tool()
async def review_kerning_bumper(
    font_index: int = 0,
    master_id: str = None,
    relevant_limit: int = 2000,
    include_existing: bool = True,
    pair_limit: int = 3000,
    glyph_names: list = None,
    min_gap: float = 5.0,
    scan_mode: str = "two_pass",
    scan_heights: list = None,
    dense_step: float = 10.0,
    bands: int = 8,
    result_limit: int = 200,
    open_tab: bool = False,
    rendering: str = "hybrid",
    per_line: int = 12,
) -> str:
    """Review kerning collisions / near-misses and propose deterministic bumper values.

    This tool does not change kerning. It measures minimum outline gaps across
    the vertical overlap range for prioritized pairs, then computes the minimal
    kerning loosening required to satisfy a minimum gap constraint.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        font = Glyphs.fonts[font_index]
        if master_id is None:
            master_id = font.masters[0].id

        dataset_meta, dataset_pairs, warnings = _load_andre_fuchs_relevant_pairs()
        pair_count = len(dataset_pairs or [])
        if pair_count and pair_count < 250:
            warnings.append(
                "Andre-Fuchs dataset snapshot is small ({} pairs). Consider regenerating it with scripts/vendor_andre_fuchs_pairs.py.".format(
                    pair_count
                )
            )

        analysis = _kerning_bumper_analyze(
            font=font,
            master_id=master_id,
            dataset_pairs=dataset_pairs,
            relevant_limit=relevant_limit,
            include_existing=include_existing,
            pair_limit=pair_limit,
            glyph_names=glyph_names,
            min_gap=min_gap,
            scan_mode=scan_mode,
            scan_heights=scan_heights,
            dense_step=dense_step,
            bands=bands,
            target_gap=min_gap,
            max_delta=10**9,
            explicit_pairs=None,
        )

        warnings.extend(analysis.get("warnings") or [])

        # Sort + cap results.
        collisions = sorted(analysis.get("collisions") or [], key=lambda r: float(r.get("minGap", 0.0)))
        safe_gaps = sorted(analysis.get("safeGaps") or [], key=lambda r: float(r.get("minGap", 0.0)), reverse=True)

        cap = max(int(result_limit or 0), 0) or 200
        collisions_out = collisions[:cap]
        gaps_out = safe_gaps[:cap]

        text = None
        opened_tab = False
        if open_tab:
            ProofGlyph = kerning_proof_engine.ProofGlyph
            glyphname_to_unicode = analysis.get("glyphnameToUnicode") or {}
            unicode_to_glyphname = analysis.get("unicodeToGlyphname") or {}

            def _context_chars(lc, rc):
                try:
                    if lc and rc and str(lc).isupper() and str(rc).isupper():
                        return ("H", "O")
                    if lc and rc and str(lc).islower() and str(rc).islower():
                        return ("n", "o")
                except Exception:
                    pass
                return ("H", "O")

            def _context_glyph_name(ch):
                return unicode_to_glyphname.get(ch) or ch

            def _unicode_for_name(name):
                uni = glyphname_to_unicode.get(name)
                if uni:
                    return uni
                if isinstance(name, str) and len(name) == 1:
                    return name
                return None

            def _pair_tokens(left_name, right_name):
                lc = _unicode_for_name(left_name)
                rc = _unicode_for_name(right_name)
                stem_ch, round_ch = _context_chars(lc or "", rc or "")
                stem_name = _context_glyph_name(stem_ch)
                round_name = _context_glyph_name(round_ch)
                return [
                    [
                        ProofGlyph(stem_name, stem_ch),
                        ProofGlyph(left_name, lc),
                        ProofGlyph(right_name, rc),
                        ProofGlyph(stem_name, stem_ch),
                    ],
                    [
                        ProofGlyph(round_name, round_ch),
                        ProofGlyph(left_name, lc),
                        ProofGlyph(right_name, rc),
                        ProofGlyph(round_name, round_ch),
                    ],
                ]

            collision_tokens = []
            for r in collisions_out:
                collision_tokens.extend(_pair_tokens(r.get("left"), r.get("right")))

            gap_tokens = []
            for r in gaps_out:
                gap_tokens.extend(_pair_tokens(r.get("left"), r.get("right")))

            sections = [
                ("KERNING COLLISION GUARD (min_gap={}) — COLLISIONS / NEAR MISSES".format(analysis.get("minGap")), collision_tokens),
                ("LARGEST GAPS (by measured minGap)", gap_tokens),
            ]

            text, engine_warnings = kerning_proof_engine.assemble_tab_text(
                sections=sections,
                rendering=rendering,
                per_line=per_line,
            )
            warnings.extend(engine_warnings)

            try:
                _open_tab_on_main_thread(font, text)
                opened_tab = True
            except Exception as exc:
                warnings.append("Failed to open Glyphs tab: {}".format(exc))

        # Deduplicate warnings, keep the payload small.
        deduped = []
        seen = set()
        for w in warnings:
            if not w:
                continue
            if w in seen:
                continue
            seen.add(w)
            deduped.append(w)
            if len(deduped) >= 12:
                break

        return _safe_json(
            {
                "ok": True,
                "fontIndex": font_index,
                "masterId": master_id,
                "dataset": {"id": dataset_meta.get("id") or "andre_fuchs_relevant_pairs", "usedTopN": analysis.get("usedTopN")},
                "counts": analysis.get("counts"),
                "params": {
                    "minGap": float(analysis.get("minGap")),
                    "scanMode": analysis.get("scanMode"),
                    "scanHeights": analysis.get("scanHeights"),
                    "denseStep": float(analysis.get("denseStep")),
                    "bands": int(analysis.get("bands")),
                },
                "results": {"collisions": collisions_out, "largestGaps": gaps_out},
                "openedTab": bool(opened_tab),
                **({"text": text} if open_tab else {}),
                "warnings": deduped,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})


@mcp.tool()
async def apply_kerning_bumper(
    font_index: int = 0,
    master_id: str = None,
    relevant_limit: int = 2000,
    include_existing: bool = True,
    pair_limit: int = 3000,
    glyph_names: list = None,
    min_gap: float = 5.0,
    scan_mode: str = "two_pass",
    scan_heights: list = None,
    dense_step: float = 10.0,
    bands: int = 8,
    result_limit: int = 200,
    pairs: list = None,
    extra_gap: float = 0.0,
    max_delta: int = 200,
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Apply kerning bumper suggestions as glyph–glyph exceptions.

    Safety:
      - Refuses to mutate without confirm=true.
      - Use dry_run=true to preview.
      - Never auto-saves.
    """
    try:
        if not confirm and not dry_run:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Refusing to apply kerning without confirm=true.",
                    "hint": "Run apply_kerning_bumper(..., dry_run=true) to preview or set confirm=true to apply.",
                }
            )

        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        font = Glyphs.fonts[font_index]
        if master_id is None:
            master_id = font.masters[0].id

        dataset_meta, dataset_pairs, warnings = _load_andre_fuchs_relevant_pairs()

        try:
            target_gap = float(min_gap) + float(extra_gap or 0.0)
        except Exception:
            target_gap = float(min_gap or 5.0)
            warnings.append("Invalid extra_gap; ignored.")

        explicit_pairs = None
        if pairs is not None:
            explicit_pairs = pairs

        analysis = _kerning_bumper_analyze(
            font=font,
            master_id=master_id,
            dataset_pairs=dataset_pairs,
            relevant_limit=relevant_limit,
            include_existing=include_existing,
            pair_limit=pair_limit,
            glyph_names=glyph_names,
            min_gap=min_gap,
            scan_mode=scan_mode,
            scan_heights=scan_heights,
            dense_step=dense_step,
            bands=bands,
            target_gap=target_gap,
            max_delta=max_delta,
            explicit_pairs=explicit_pairs,
        )

        warnings.extend(analysis.get("warnings") or [])

        collisions = analysis.get("collisions") or []
        by_pair = {(r.get("left"), r.get("right")): r for r in collisions if r.get("left") and r.get("right")}

        requested = []
        if pairs is not None:
            for item in pairs or []:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                requested.append((str(item[0]), str(item[1])))
        else:
            requested = list(by_pair.keys())

        to_apply = []
        changes = []
        skipped_missing = 0
        skipped_safe = 0

        for left_name, right_name in requested:
            r = by_pair.get((left_name, right_name))
            if not r:
                skipped_missing += 1
                continue

            old_value = _coerce_numeric(r.get("kerningValue"))
            new_value = _coerce_numeric(r.get("recommendedException"))
            if old_value is None or new_value is None:
                skipped_missing += 1
                continue

            old_value_f = float(old_value)
            new_value_i = int(new_value)
            delta = float(new_value_i) - float(old_value_f)

            if delta <= 0:
                skipped_safe += 1
                continue

            to_apply.append((left_name, right_name, new_value_i))
            changes.append(
                {
                    "left": left_name,
                    "right": right_name,
                    "oldKerningValue": old_value_f,
                    "newKerningValue": new_value_i,
                    "delta": delta,
                    "minGap": r.get("minGap"),
                    "targetGap": target_gap,
                }
            )

        applied_count = 0
        if to_apply and confirm and not dry_run:
            _set_kerning_pairs_on_main_thread(font, master_id, to_apply)
            applied_count = len(to_apply)

        cap = max(int(result_limit or 0), 0) or 200
        changes_out = changes[:cap]

        # Deduplicate warnings, keep the payload small.
        deduped = []
        seen = set()
        for w in warnings:
            if not w:
                continue
            if w in seen:
                continue
            seen.add(w)
            deduped.append(w)
            if len(deduped) >= 12:
                break

        return _safe_json(
            {
                "ok": True,
                "dryRun": bool(dry_run),
                "confirmed": bool(confirm),
                "fontIndex": font_index,
                "masterId": master_id,
                "dataset": {"id": dataset_meta.get("id") or "andre_fuchs_relevant_pairs", "usedTopN": analysis.get("usedTopN")},
                "params": {
                    "minGap": float(analysis.get("minGap")),
                    "extraGap": float(extra_gap or 0.0),
                    "targetGap": float(target_gap),
                    "maxDelta": int(analysis.get("maxDelta")),
                    "scanMode": analysis.get("scanMode"),
                    "scanHeights": analysis.get("scanHeights"),
                    "denseStep": float(analysis.get("denseStep")),
                    "bands": int(analysis.get("bands")),
                },
                "counts": {
                    "pairsRequested": len(requested),
                    "pairsColliding": len(by_pair),
                    "pairsToApply": len(to_apply),
                    "pairsApplied": applied_count,
                    "pairsSkippedMissing": skipped_missing,
                    "pairsSkippedAlreadySafe": skipped_safe,
                },
                "changes": changes_out,
                "warnings": deduped,
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})
