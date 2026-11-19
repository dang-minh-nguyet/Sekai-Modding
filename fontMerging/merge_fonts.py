import argparse
import logging
import math
import os
from typing import Dict, Optional, Set, Tuple

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Unicode blocks replaced from the override font (ASCII/English + Vietnamese + Latin + punctuation/currency)
OVERRIDE_RANGES = [
    (0x0020, 0x007E),  # Basic Latin (printable ASCII, excludes 0x007F DEL)
    (0x00A0, 0x00FF),  # Latin-1 Supplement
    (0x0100, 0x024F),  # Latin Extended-A & B (Ăă, Đđ, Ĩĩ, Ũũ, Ơơ, Ưư, ...)
    (0x0250, 0x02AF),  # IPA Extensions
    (0x02B0, 0x02FF),  # Spacing Modifier Letters
    (0x0300, 0x036F),  # Combining Diacritical Marks (NFD Vietnamese)
    (0x1E00, 0x1EFF),  # Latin Extended Additional (NFC Vietnamese)
    (0x2000, 0x206F),  # General Punctuation
    (0x20A0, 0x20CF),  # Currency Symbols (₫, €, ...)
]

# Full set of 134 precomposed Vietnamese accented letters for coverage checks
VIETNAMESE_CHARS = (
    "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý"
    "ĂăĐđĨĩŨũƠơƯư"
    "ẠạẢảẤấẦầẨẩẪẫẬậẮắẰằẲẳẴẵẶặ"
    "ẸẹẺẻẼẽẾếỀềỂểỄễỆệ"
    "ỈỉỊị"
    "ỌọỎỏỐốỒồỔổỖỗỘộỚớỜờỞởỠỡỢợ"
    "ỤụỦủỨứỪừỬửỮữỰự"
    "ỲỳỴỵỶỷỸỹ"
)
ASCII_PRINTABLE = "".join(chr(c) for c in range(0x0020, 0x007F))


def should_override(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in OVERRIDE_RANGES)


def get_font_type(font: TTFont) -> str:
    if "CFF2" in font:
        return "cff2"
    if "CFF " in font:
        return "cff"
    if "glyf" in font:
        return "truetype"
    raise ValueError("Font has no recognized outline format (expected glyf, CFF, or CFF2)")


def is_font_collection(path: str) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == b"ttcf"


def open_font(path: str, font_index: int = 0) -> TTFont:
    """Open a standalone font (.ttf/.otf/.woff/.woff2) or a sub-font from a collection (.ttc/.otc)."""
    if is_font_collection(path):
        coll = TTCollection(path, lazy=True)
        count = len(coll.fonts)
        names = []
        for idx, sub in enumerate(coll.fonts):
            full_name = sub["name"].getDebugName(4) or f"Font #{idx}"
            names.append(f"[{idx}] {full_name}")
        coll.close()
        if not (0 <= font_index < count):
            raise ValueError(
                f"font_index={font_index} out of range for {os.path.basename(path)} "
                f"(available: {', '.join(names)})"
            )
        logger.info(
            f"Collection detected ({os.path.basename(path)}): using {names[font_index]} "
            f"(all: {', '.join(names)})"
        )
        return TTFont(path, fontNumber=font_index)
    return TTFont(path)


def parse_axes(axes_str: Optional[str]) -> Dict[str, float]:
    """Parse comma-separated variable font axis spec like 'wght=700,wdth=100'."""
    if not axes_str:
        return {}
    result: Dict[str, float] = {}
    for item in axes_str.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid axis specification '{item}' (expected TAG=VALUE, e.g. wght=700)")
        tag, val = item.split("=", 1)
        result[tag.strip()] = float(val.strip())
    return result


def resolve_variable_location(
    base_font: TTFont,
    override_font: TTFont,
    weight: Optional[float] = None,
    axes: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, float]]:
    """Determine axis location dict for a variable override font, or None for static fonts."""
    if "fvar" not in override_font:
        return None

    fvar_axes = {a.axisTag: a for a in override_font["fvar"].axes}
    location: Dict[str, float] = {}

    # User-specified axes take priority
    requested = dict(axes or {})
    if weight is not None and "wght" not in requested:
        requested["wght"] = weight

    # Auto-match base font's OS/2 weight when user didn't specify wght
    if "wght" in fvar_axes and "wght" not in requested and "OS/2" in base_font:
        base_weight = float(base_font["OS/2"].usWeightClass)
        axis = fvar_axes["wght"]
        clamped = max(axis.minValue, min(axis.maxValue, base_weight))
        requested["wght"] = clamped
        logger.info(
            f"Variable font detected — auto-matching base weight: "
            f"wght={clamped:g} (base={base_weight:g}, axis range={axis.minValue:g}..{axis.maxValue:g})"
        )

    for tag, val in requested.items():
        if tag not in fvar_axes:
            logger.warning(
                f"Requested axis '{tag}' not found in override font "
                f"(available: {', '.join(fvar_axes.keys())}); ignoring."
            )
            continue
        axis = fvar_axes[tag]
        clamped = max(axis.minValue, min(axis.maxValue, val))
        if clamped != val:
            logger.warning(
                f"Clamped axis '{tag}' from {val:g} to {clamped:g} "
                f"(valid range: {axis.minValue:g}..{axis.maxValue:g})"
            )
        location[tag] = clamped

    if location:
        logger.info(f"Using variable font instance: {location}")
    return location


def measure_cap_height(font: TTFont, glyphset) -> Optional[float]:
    """Measure cap height from actual 'H' or 'A' outline, falling back to OS/2.sCapHeight."""
    cmap = font.getBestCmap() or {}
    for ch in ("H", "A", "E", "I"):
        gname = cmap.get(ord(ch))
        if gname and gname in glyphset:
            bp = BoundsPen(glyphset)
            try:
                glyphset[gname].draw(bp)
                if bp.bounds and bp.bounds[3] > 0:
                    return float(bp.bounds[3])
            except Exception:
                pass
    if "OS/2" in font:
        cap = getattr(font["OS/2"], "sCapHeight", 0)
        if cap and cap > 0:
            return float(cap)
    return None


def compute_scale(
    base_font: TTFont,
    override_font: TTFont,
    override_glyphset,
    user_scale: float = 1.0,
    match_cap_height: bool = False,
) -> float:
    """Compute total coordinate/metric scale factor from override font space to base font space."""
    base_upm = base_font["head"].unitsPerEm
    override_upm = override_font["head"].unitsPerEm
    upm_scale = base_upm / override_upm

    if override_upm != base_upm:
        logger.info(
            f"Normalizing unitsPerEm: override={override_upm} -> base={base_upm} "
            f"(UPM scale={upm_scale:.6f})"
        )

    optical_scale = 1.0
    if match_cap_height:
        base_cap = measure_cap_height(base_font, base_font.getGlyphSet())
        override_cap = measure_cap_height(override_font, override_glyphset)
        if base_cap and override_cap and override_cap > 0:
            optical_scale = base_cap / (override_cap * upm_scale)
            logger.info(
                f"Matching CapHeight: base={base_cap:.1f}, override_scaled={override_cap * upm_scale:.1f} "
                f"(optical scale={optical_scale:.4f})"
            )
        else:
            logger.warning("Could not measure CapHeight for optical scaling; skipping --match-cap-height.")

    total_scale = upm_scale * optical_scale * user_scale
    if user_scale != 1.0:
        logger.info(f"Applying user scale multiplier {user_scale:g} -> total scale={total_scale:.6f}")
    return total_scale


def update_unicode_cmaps(base_font: TTFont, cp: int, glyph_name: str) -> None:
    """Add codepoint mapping ONLY to Unicode cmap subtables (never Mac Shift-JIS / legacy tables)."""
    for table in base_font["cmap"].tables:
        if table.isUnicode() and hasattr(table, "cmap") and isinstance(table.cmap, dict):
            if table.format == 4 and cp > 0xFFFF:
                continue
            table.cmap[cp] = glyph_name


def prune_overridden_ligatures(base_font: TTFont, overridden_glyphs: Set[str]) -> int:
    """Remove GSUB 'liga' ligatures starting with an overridden glyph so e.g. 'fi'/'fl' don't revert to base font."""
    if "GSUB" not in base_font or not overridden_glyphs:
        return 0
    gsub = base_font["GSUB"].table
    if not gsub.FeatureList or not gsub.LookupList:
        return 0

    liga_lookups = set()
    for rec in gsub.FeatureList.FeatureRecord:
        if rec.FeatureTag == "liga":
            liga_lookups.update(rec.Feature.LookupListIndex)

    removed = 0
    for idx in liga_lookups:
        if idx >= len(gsub.LookupList.Lookup):
            continue
        lookup = gsub.LookupList.Lookup[idx]
        for subtable in lookup.SubTable:
            if hasattr(subtable, "ligatures") and isinstance(subtable.ligatures, dict):
                to_delete = [g for g in subtable.ligatures if g in overridden_glyphs]
                for g in to_delete:
                    removed += len(subtable.ligatures[g])
                    del subtable.ligatures[g]
    if removed:
        logger.info(f"Pruned {removed} base GSUB 'liga' entries conflicting with overridden glyphs.")
    return removed


def get_glyph_advance_width(override_glyphset, override_hmtx, glyph_name: str) -> float:
    glyph = override_glyphset[glyph_name]
    w = getattr(glyph, "width", None)
    if w is not None and math.isfinite(w):
        return float(w)
    if glyph_name in override_hmtx.metrics:
        return float(override_hmtx.metrics[glyph_name][0])
    return 0.0


def record_decomposed_glyph(override_glyphset, glyph_name: str) -> DecomposingRecordingPen:
    """Decompose all simple and nested composite contours into raw drawing commands."""
    rec = DecomposingRecordingPen(override_glyphset)
    override_glyphset[glyph_name].draw(rec)
    return rec


def merge_to_cff(
    base_font: TTFont,
    override_font: TTFont,
    override_glyphset,
    override_type: str,
    override_codepoints: Set[int],
    scale: float,
    y_offset: float = 0.0,
) -> Tuple[int, int, int]:
    """Merge glyphs from ANY outline format (TrueType, CFF, CFF2) into a CFF (.otf) base font."""
    base_cmap = base_font.getBestCmap() or {}
    override_cmap = override_font.getBestCmap() or {}
    base_hmtx = base_font["hmtx"]
    override_hmtx = override_font["hmtx"]
    base_vmtx = base_font["vmtx"] if "vmtx" in base_font else None
    base_vorg = base_font["VORG"] if "VORG" in base_font else None
    base_upm = base_font["head"].unitsPerEm
    default_vert_origin = (
        base_vorg.defaultVertOriginY if base_vorg is not None else base_font["hhea"].ascent
    )

    cff = base_font["CFF "].cff
    top_dict = cff.topDictIndex[0]
    base_charstrings = top_dict.CharStrings
    global_subrs = getattr(cff, "GlobalSubrs", [])

    is_cid = hasattr(top_dict, "ROS") and hasattr(top_dict, "FDArray") and hasattr(top_dict, "FDSelect")

    glyph_order = list(base_font.getGlyphOrder())
    glyph_id_map = {name: i for i, name in enumerate(glyph_order)}

    # Detect base glyphs shared by multiple printable codepoints (e.g. '_' & U+0332,
    # '~' & U+0303, '`' & U+0300, U+2003 & Japanese full-width space U+3000).
    # Shared glyphs must NEVER be overwritten in-place; allocate a fresh slot instead.
    glyph_to_printable_cps: Dict[str, int] = {}
    for bcp, gname in base_cmap.items():
        if bcp >= 0x20:
            glyph_to_printable_cps[gname] = glyph_to_printable_cps.get(gname, 0) + 1
    shared_base_glyphs = {g for g, cnt in glyph_to_printable_cps.items() if cnt > 1}

    if is_cid:
        # Pick the proportional Latin FD index (e.g. FD of 'A', which is FD[12] on FOT-RodinNTLG)
        if 0x0041 in base_cmap and base_cmap[0x0041] in glyph_id_map:
            new_fd_idx = top_dict.FDSelect[glyph_id_map[base_cmap[0x0041]]]
        else:
            new_fd_idx = 0

        # Ensure FDSelect.gidArray covers all existing glyphs cleanly
        if len(top_dict.FDSelect.gidArray) < len(glyph_order):
            top_dict.FDSelect.gidArray.extend(
                [new_fd_idx] * (len(glyph_order) - len(top_dict.FDSelect.gidArray))
            )

        max_cid = len(glyph_order) - 1
        for name in glyph_order:
            if name.startswith("cid"):
                try:
                    max_cid = max(max_cid, int(name[3:]))
                except ValueError:
                    pass
        next_cid = max_cid + 1
    else:
        new_fd_idx = None
        next_cid = 0

    needs_transform = (abs(scale - 1.0) > 1e-9) or (abs(y_offset) > 1e-9)
    transform_matrix = (scale, 0, 0, scale, 0, y_offset)
    is_quad_source = override_type == "truetype"

    head = base_font["head"]
    bbox = [head.xMin, head.yMin, head.xMax, head.yMax]
    overridden_glyphs: Set[str] = set()
    replaced = added = skipped = 0

    for cp in sorted(override_codepoints):
        glyph_name = override_cmap.get(cp)
        if not glyph_name or glyph_name not in override_glyphset:
            skipped += 1
            continue

        # Determine target slot & its exact CFF Private dict BEFORE building the CharString.
        # Only replace in-place if the codepoint exists in base_cmap AND its glyph is not
        # shared with any other printable codepoint (prevents e.g. U+0332 clobbering '_',
        # U+0303 clobbering '~', or U+2003 clobbering Japanese full-width space U+3000).
        replace_in_place = cp in base_cmap and base_cmap[cp] not in shared_base_glyphs
        if replace_in_place:
            target_name = base_cmap[cp]
            gid = glyph_id_map[target_name]
            if is_cid:
                fd_idx = top_dict.FDSelect[gid]
                private = top_dict.FDArray[fd_idx].Private
            else:
                private = top_dict.Private
        else:
            if is_cid:
                target_name = f"cid{next_cid:05d}"
                private = top_dict.FDArray[new_fd_idx].Private
            else:
                candidate = glyph_name if glyph_name not in glyph_id_map else f"uni{cp:04X}"
                suffix = 1
                target_name = candidate
                while target_name in glyph_id_map:
                    target_name = f"{candidate}.{suffix}"
                    suffix += 1
                private = top_dict.Private

        try:
            rec = record_decomposed_glyph(override_glyphset, glyph_name)

            raw_width = get_glyph_advance_width(override_glyphset, override_hmtx, glyph_name)
            scaled_width = max(0, otRound(raw_width * scale))

            default_w = getattr(private, "defaultWidthX", 0)
            nominal_w = getattr(private, "nominalWidthX", 0)
            t2_width = None if scaled_width == default_w else (scaled_width - nominal_w)

            t2pen = T2CharStringPen(t2_width, glyphSet=None)
            if is_quad_source:
                # TrueType (quadratic, CW) -> CFF (cubic, CCW)
                dest_pen = Qu2CuPen(ReverseContourPen(t2pen), max_err=1.0, all_cubic=True)
            else:
                # CFF / CFF2 (already cubic, CCW) -> CFF
                dest_pen = t2pen

            if needs_transform:
                dest_pen = TransformPen(dest_pen, transform_matrix)

            rec.replay(dest_pen)
            charstring = t2pen.getCharString(private=private, globalSubrs=global_subrs)

            # Compute exact bounds of the compiled CFF outline
            bp = BoundsPen(None)
            charstring.draw(bp)
            bounds = bp.bounds
        except Exception as e:
            # Fallback for exotic quadratic curves if Qu2CuPen balks: exact degree elevation via BasePen
            if is_quad_source:
                try:
                    rec = record_decomposed_glyph(override_glyphset, glyph_name)
                    raw_width = get_glyph_advance_width(override_glyphset, override_hmtx, glyph_name)
                    scaled_width = max(0, otRound(raw_width * scale))
                    default_w = getattr(private, "defaultWidthX", 0)
                    nominal_w = getattr(private, "nominalWidthX", 0)
                    t2_width = None if scaled_width == default_w else (scaled_width - nominal_w)
                    t2pen = T2CharStringPen(t2_width, glyphSet=None)
                    dest_pen = ReverseContourPen(t2pen)
                    if needs_transform:
                        dest_pen = TransformPen(dest_pen, transform_matrix)
                    rec.replay(dest_pen)
                    charstring = t2pen.getCharString(private=private, globalSubrs=global_subrs)
                    bp = BoundsPen(None)
                    charstring.draw(bp)
                    bounds = bp.bounds
                except Exception as e2:
                    logger.warning(f"  Skipped U+{cp:04X} ({glyph_name}): {e2}")
                    skipped += 1
                    continue
            else:
                logger.warning(f"  Skipped U+{cp:04X} ({glyph_name}): {e}")
                skipped += 1
                continue

        scaled_lsb = otRound(bounds[0]) if bounds else 0
        if bounds:
            bbox[0] = min(bbox[0], otRound(bounds[0]))
            bbox[1] = min(bbox[1], otRound(bounds[1]))
            bbox[2] = max(bbox[2], otRound(bounds[2]))
            bbox[3] = max(bbox[3], otRound(bounds[3]))

        # Commit glyph
        if replace_in_place:
            base_charstrings[target_name] = charstring
            if base_vorg is not None and target_name in base_vorg.VOriginRecords:
                del base_vorg.VOriginRecords[target_name]
            replaced += 1
        else:
            if is_cid:
                next_cid += 1
            glyph_id_map[target_name] = len(glyph_order)
            glyph_order.append(target_name)
            if top_dict.charset is not glyph_order:
                top_dict.charset.append(target_name)
            if is_cid:
                top_dict.FDSelect.gidArray.append(new_fd_idx)

            base_charstrings.charStrings[target_name] = len(base_charstrings.charStringsIndex)
            base_charstrings.charStringsIndex.append(charstring)

            existed_in_base = cp in base_cmap
            update_unicode_cmaps(base_font, cp, target_name)
            if existed_in_base:
                replaced += 1
            else:
                added += 1

        base_hmtx.metrics[target_name] = (scaled_width, scaled_lsb)
        if base_vmtx is not None:
            tsb = otRound(default_vert_origin - bounds[3]) if bounds else 0
            base_vmtx.metrics[target_name] = (base_upm, tsb)
        overridden_glyphs.add(target_name)

    # Finalize font-wide structures once
    base_font.setGlyphOrder(glyph_order)
    if is_cid:
        top_dict.CIDCount = max(getattr(top_dict, "CIDCount", 0), next_cid)

    top_dict.FontBBox = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
    head.xMin, head.yMin, head.xMax, head.yMax = top_dict.FontBBox

    prune_overridden_ligatures(base_font, overridden_glyphs)
    return replaced, added, skipped


def merge_to_truetype(
    base_font: TTFont,
    override_font: TTFont,
    override_glyphset,
    override_type: str,
    override_codepoints: Set[int],
    scale: float,
    y_offset: float = 0.0,
) -> Tuple[int, int, int]:
    """Merge glyphs from ANY outline format (TrueType, CFF, CFF2) into a TrueType (.ttf) base font."""
    base_cmap = base_font.getBestCmap() or {}
    override_cmap = override_font.getBestCmap() or {}
    base_glyf = base_font["glyf"]
    base_hmtx = base_font["hmtx"]
    override_hmtx = override_font["hmtx"]
    base_vmtx = base_font["vmtx"] if "vmtx" in base_font else None
    base_upm = base_font["head"].unitsPerEm
    default_vert_origin = base_font["hhea"].ascent

    glyph_order = list(base_font.getGlyphOrder())
    glyph_set_names = set(glyph_order)

    glyph_to_printable_cps: Dict[str, int] = {}
    for bcp, gname in base_cmap.items():
        if bcp >= 0x20:
            glyph_to_printable_cps[gname] = glyph_to_printable_cps.get(gname, 0) + 1
    shared_base_glyphs = {g for g, cnt in glyph_to_printable_cps.items() if cnt > 1}

    needs_transform = (abs(scale - 1.0) > 1e-9) or (abs(y_offset) > 1e-9)
    transform_matrix = (scale, 0, 0, scale, 0, y_offset)
    is_cubic_source = override_type in ("cff", "cff2")

    overridden_glyphs: Set[str] = set()
    replaced = added = skipped = 0

    for cp in sorted(override_codepoints):
        glyph_name = override_cmap.get(cp)
        if not glyph_name or glyph_name not in override_glyphset:
            skipped += 1
            continue

        try:
            rec = record_decomposed_glyph(override_glyphset, glyph_name)
            raw_width = get_glyph_advance_width(override_glyphset, override_hmtx, glyph_name)
            scaled_width = max(0, otRound(raw_width * scale))

            ttpen = TTGlyphPen(None)
            if is_cubic_source:
                # CFF/CFF2 (cubic, CCW) -> TrueType (quadratic, CW)
                dest_pen = Cu2QuPen(ttpen, max_err=1.0, reverse_direction=True)
            else:
                dest_pen = ttpen

            if needs_transform:
                dest_pen = TransformPen(dest_pen, transform_matrix)

            rec.replay(dest_pen)
            glyph = ttpen.glyph()
            glyph.recalcBounds(base_glyf)
        except Exception as e:
            logger.warning(f"  Skipped U+{cp:04X} ({glyph_name}): {e}")
            skipped += 1
            continue

        replace_in_place = cp in base_cmap and base_cmap[cp] not in shared_base_glyphs
        if replace_in_place:
            target_name = base_cmap[cp]
            replaced += 1
        else:
            candidate = glyph_name if glyph_name not in glyph_set_names else f"uni{cp:04X}"
            suffix = 1
            target_name = candidate
            while target_name in glyph_set_names:
                target_name = f"{candidate}.{suffix}"
                suffix += 1
            glyph_order.append(target_name)
            glyph_set_names.add(target_name)
            existed_in_base = cp in base_cmap
            update_unicode_cmaps(base_font, cp, target_name)
            if existed_in_base:
                replaced += 1
            else:
                added += 1

        base_glyf[target_name] = glyph
        scaled_lsb = glyph.xMin if glyph.numberOfContours > 0 else 0
        base_hmtx.metrics[target_name] = (scaled_width, scaled_lsb)
        if base_vmtx is not None:
            tsb = otRound(default_vert_origin - glyph.yMax) if glyph.numberOfContours > 0 else 0
            base_vmtx.metrics[target_name] = (base_upm, tsb)
        overridden_glyphs.add(target_name)

    base_font.setGlyphOrder(glyph_order)
    prune_overridden_ligatures(base_font, overridden_glyphs)
    return replaced, added, skipped


def check_coverage(font: TTFont, override_cmap: Dict[int, str]) -> Tuple[int, int]:
    """Check and log ASCII & Vietnamese coverage of the override font."""
    missing_ascii = [c for c in ASCII_PRINTABLE if ord(c) not in override_cmap]
    missing_viet = [c for c in VIETNAMESE_CHARS if ord(c) not in override_cmap]

    if missing_ascii:
        logger.warning(
            f"Override font is missing {len(missing_ascii)} printable ASCII char(s): "
            f"{''.join(missing_ascii[:20])}"
        )
    if missing_viet:
        sample = "".join(missing_viet[:20]) + ("..." if len(missing_viet) > 20 else "")
        logger.warning(
            f"Override font is missing {len(missing_viet)}/{len(VIETNAMESE_CHARS)} Vietnamese char(s): {sample}"
        )
    elif not missing_ascii:
        logger.info(
            f"Coverage OK: all {len(ASCII_PRINTABLE)} ASCII + all {len(VIETNAMESE_CHARS)} Vietnamese chars present."
        )
    return len(missing_ascii), len(missing_viet)


def verify_merged_font(path: str) -> None:
    """Reload saved font and strictly verify table integrity, CFF FDSelect/widths, vmtx, and cmap."""
    font = TTFont(path)
    try:
        glyph_order = font.getGlyphOrder()
        num_glyphs = len(glyph_order)
        assert font["maxp"].numGlyphs == num_glyphs, (
            f"maxp.numGlyphs ({font['maxp'].numGlyphs}) != glyphOrder ({num_glyphs})"
        )
        assert len(font["hmtx"].metrics) == num_glyphs, (
            f"hmtx count ({len(font['hmtx'].metrics)}) != glyphOrder ({num_glyphs})"
        )
        if "vmtx" in font:
            assert len(font["vmtx"].metrics) == num_glyphs, (
                f"vmtx count ({len(font['vmtx'].metrics)}) != glyphOrder ({num_glyphs})"
            )

        # Ensure legacy non-Unicode cmaps weren't polluted with Vietnamese Unicode codepoints
        for table in font["cmap"].tables:
            if not table.isUnicode() and hasattr(table, "cmap"):
                for test_cp in (0x0110, 0x1EA0, 0x1EA4):
                    assert test_cp not in table.cmap, (
                        f"Non-Unicode cmap (plat={table.platformID}, enc={table.platEncID}) "
                        f"contains leaked Unicode codepoint U+{test_cp:04X}"
                    )

        if "CFF " in font:
            td = font["CFF "].cff.topDictIndex[0]
            assert len(td.charset) == num_glyphs, f"CFF charset ({len(td.charset)}) != {num_glyphs}"
            assert len(td.CharStrings) == num_glyphs, f"CFF CharStrings ({len(td.CharStrings)}) != {num_glyphs}"
            if hasattr(td, "FDSelect"):
                assert len(td.FDSelect.gidArray) == num_glyphs, (
                    f"CFF FDSelect ({len(td.FDSelect.gidArray)}) != {num_glyphs}"
                )
                assert all(
                    fd is not None and 0 <= fd < len(td.FDArray) for fd in td.FDSelect.gidArray
                ), "CFF FDSelect contains invalid or None FD index"
                if hasattr(td, "CIDCount"):
                    max_cid = max(
                        (int(g[3:]) for g in glyph_order if g.startswith("cid") and g[3:].isdigit()),
                        default=0,
                    )
                    assert td.CIDCount > max_cid, f"CFF CIDCount ({td.CIDCount}) <= max CID ({max_cid})"

        # Spot-draw sample glyphs across ASCII, Vietnamese, and Japanese to confirm CharStrings & widths match hmtx
        gs = font.getGlyphSet()
        cmap = font.getBestCmap() or {}
        combining_pairs = {"_": 0x0332, "~": 0x0303, "`": 0x0300}
        for ch in "Aa0 _~`ĐđƠơƯưẠạẤấỆệỘộỨứỲỳあ亜":
            g = cmap.get(ord(ch))
            if not g:
                continue
            bp = BoundsPen(gs)
            gs[g].draw(bp)
            hmtx_w = font["hmtx"].metrics[g][0]
            if ch in combining_pairs:
                comb_g = cmap.get(combining_pairs[ch])
                assert comb_g != g, (
                    f"Printable ASCII {ch!r} ({g}) shares glyph with combining mark U+{combining_pairs[ch]:04X}!"
                )
                if hmtx_w == 0:
                    logger.warning(
                        f"Printable ASCII {ch!r} ({g}) has zero advance width in override font."
                    )
            if "CFF " in font:
                cs = font["CFF "].cff.topDictIndex[0].CharStrings[g]
                cs.decompile()
                assert cs.width == hmtx_w, (
                    f"Width mismatch for {ch!r} ({g}): CFF cs.width={cs.width} != hmtx={hmtx_w}"
                )
        logger.info(f"Verification PASSED: {os.path.basename(path)} ({num_glyphs} glyphs)")
    finally:
        font.close()


def merge_fonts(
    base_path: str,
    override_path: str,
    output_path: str,
    *,
    font_index: int = 0,
    weight: Optional[float] = None,
    axes: Optional[Dict[str, float]] = None,
    scale: float = 1.0,
    match_cap_height: bool = False,
    y_offset: float = 0.0,
    verify: bool = False,
) -> Tuple[int, int, int]:
    base_font = TTFont(base_path)
    override_font = open_font(override_path, font_index=font_index)
    try:
        base_type = get_font_type(base_font)
        override_type = get_font_type(override_font)
        logger.info(
            f"Merging '{os.path.basename(override_path)}' ({override_type}) -> "
            f"'{os.path.basename(base_path)}' ({base_type})"
        )

        location = resolve_variable_location(base_font, override_font, weight=weight, axes=axes)
        override_glyphset = (
            override_font.getGlyphSet(location=location, normalized=False)
            if location is not None
            else override_font.getGlyphSet()
        )

        override_cmap = override_font.getBestCmap() or {}
        override_codepoints = {cp for cp in override_cmap if should_override(cp)}
        check_coverage(override_font, override_cmap)

        total_scale = compute_scale(
            base_font,
            override_font,
            override_glyphset,
            user_scale=scale,
            match_cap_height=match_cap_height,
        )

        if base_type == "cff":
            replaced, added, skipped = merge_to_cff(
                base_font,
                override_font,
                override_glyphset,
                override_type,
                override_codepoints,
                scale=total_scale,
                y_offset=y_offset,
            )
        elif base_type == "truetype":
            replaced, added, skipped = merge_to_truetype(
                base_font,
                override_font,
                override_glyphset,
                override_type,
                override_codepoints,
                scale=total_scale,
                y_offset=y_offset,
            )
        else:
            raise ValueError(f"Unsupported base font format: {base_type} (expected cff or truetype)")

        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        base_font.save(output_path)
        logger.info(
            f"Saved '{output_path}' — replaced={replaced}, added={added}, skipped={skipped}"
        )
    finally:
        base_font.close()
        override_font.close()

    if verify:
        verify_merged_font(output_path)

    return replaced, added, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Merge English/Vietnamese/Latin glyphs from an override font into a base font."
    )
    parser.add_argument("base", nargs="?", help="Base font path (e.g. FOT-RodinNTLG Pro EB.otf)")
    parser.add_argument("override", nargs="?", help="Override font path (.ttf, .otf, .ttc, .otc, variable font)")
    parser.add_argument("output", nargs="?", help="Output font path (e.g. FOT-RodinNTLGPro-EB-OnDemand.otf)")
    parser.add_argument("--font-index", type=int, default=0, help="Sub-font index for .ttc/.otc collections (default: 0)")
    parser.add_argument("--weight", type=float, default=None, help="Variable font wght axis value (default: auto-match base weight)")
    parser.add_argument("--axes", type=str, default=None, help="Variable font axes, e.g. 'wght=700,wdth=100'")
    parser.add_argument("--scale", type=float, default=1.0, help="Extra optical scale multiplier on top of UPM normalization (default: 1.0)")
    parser.add_argument("--match-cap-height", action="store_true", help="Auto-scale override font so CapHeight matches the base font")
    parser.add_argument("--y-offset", type=float, default=0.0, help="Vertical baseline offset in base font units (default: 0)")
    parser.add_argument("--verify", action="store_true", help="Reload and strictly verify the output font after saving")
    args = parser.parse_args()

    axes_dict = parse_axes(args.axes)

    if args.base and args.override:
        output_path = args.output or f"{os.path.splitext(args.base)[0]} - Merged.otf"
        if os.path.exists(args.base) and os.path.exists(args.override):
            merge_fonts(
                args.base,
                args.override,
                output_path,
                font_index=args.font_index,
                weight=args.weight,
                axes=axes_dict,
                scale=args.scale,
                match_cap_height=args.match_cap_height,
                y_offset=args.y_offset,
                verify=args.verify,
            )
        else:
            logger.error("Base or override font not found.")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        merge_pairs = [
            (
                os.path.join(script_dir, "FOT-RodinNTLG Pro EB.otf"),
                os.path.join(script_dir, "YourFont1.ttf"),
                os.path.join(script_dir, "FOT-RodinNTLGPro-EB-OnDemand.otf"),
            ),
            (
                os.path.join(script_dir, "FOT-RodinNTLG Pro DB.otf"),
                os.path.join(script_dir, "YourFont2.ttf"),
                os.path.join(script_dir, "FOT-RodinNTLGPro-DB-OnDemand.otf"),
            ),
        ]
        for base, override, out in merge_pairs:
            if os.path.exists(base) and os.path.exists(override):
                merge_fonts(
                    base,
                    override,
                    out,
                    font_index=args.font_index,
                    weight=args.weight,
                    axes=axes_dict,
                    scale=args.scale,
                    match_cap_height=args.match_cap_height,
                    y_offset=args.y_offset,
                    verify=args.verify,
                )
            else:
                logger.error(f"Missing file(s) for pair: {base} / {override}")


if __name__ == "__main__":
    main()
