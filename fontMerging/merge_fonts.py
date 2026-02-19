"""
Font Merger for PJSK Vietnamese Mod
====================================
Merges Vietnamese/Latin glyphs from source fonts into the Japanese game fonts.

Mappings:
  - Amplesoft Medium  -> overrides Latin/Vietnamese glyphs in FOT-RodinNTLG Pro EB
  - SVNBellico        -> overrides Latin/Vietnamese glyphs in FOT-RodinNTLG Pro DB

The Japanese glyphs (Hiragana, Katakana, CJK) are kept from the original game fonts.
"""

import os
import copy
import logging
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Unicode ranges for Latin + Vietnamese characters to override
OVERRIDE_RANGES = [
    (0x0020, 0x007F),  # Basic Latin (space, A-Z, a-z, digits, punctuation)
    (0x00A0, 0x00FF),  # Latin-1 Supplement (àáâãäå, etc.)
    (0x0100, 0x024F),  # Latin Extended-A & B
    (0x0250, 0x02AF),  # IPA Extensions
    (0x02B0, 0x02FF),  # Spacing Modifier Letters
    (0x0300, 0x036F),  # Combining Diacritical Marks
    (0x1E00, 0x1EFF),  # Latin Extended Additional (Vietnamese: ả, ắ, ặ, ế, ồ, etc.)
    (0x2000, 0x206F),  # General Punctuation
    (0x20A0, 0x20CF),  # Currency Symbols
]


def should_override(codepoint: int) -> bool:
    """Check if a codepoint falls within our override ranges."""
    return any(start <= codepoint <= end for start, end in OVERRIDE_RANGES)


def get_font_type(font: TTFont) -> str:
    if "glyf" in font:
        return "truetype"
    elif "CFF " in font:
        return "cff"
    raise ValueError("Font has no recognized outline format")


def merge_truetype_to_truetype(base_font, override_font, override_codepoints):
    """Merge TrueType glyphs into a TrueType base font."""
    base_cmap = base_font.getBestCmap()
    override_cmap = override_font.getBestCmap()
    base_glyf = base_font["glyf"]
    override_glyf = override_font["glyf"]
    base_hmtx = base_font["hmtx"]
    override_hmtx = override_font["hmtx"]
    
    replaced, added, skipped = 0, 0, 0
    
    # Collect all component glyphs needed (for composite glyphs)
    needed_glyphs = set()
    
    for cp in sorted(override_codepoints):
        glyph_name = override_cmap.get(cp)
        if not glyph_name or glyph_name not in override_glyf:
            skipped += 1
            continue
        needed_glyphs.add(glyph_name)
        
        # Check for composite glyph components
        glyph = override_glyf[glyph_name]
        if hasattr(glyph, 'components') and glyph.components:
            for comp in glyph.components:
                needed_glyphs.add(comp.glyphName)
    
    # Copy all needed glyphs (including component dependencies)
    for cp in sorted(override_codepoints):
        glyph_name = override_cmap.get(cp)
        if not glyph_name or glyph_name not in override_glyf:
            continue
        
        if cp in base_cmap:
            target_name = base_cmap[cp]
            replaced += 1
        else:
            target_name = glyph_name
            # Ensure glyph name is in the glyph order
            if target_name not in base_font.getGlyphOrder():
                base_font.setGlyphOrder(base_font.getGlyphOrder() + [target_name])
            for table in base_font["cmap"].tables:
                if hasattr(table, "cmap") and isinstance(table.cmap, dict):
                    table.cmap[cp] = target_name
            added += 1
        
        # Copy glyph
        base_glyf[target_name] = copy.deepcopy(override_glyf[glyph_name])
        if glyph_name in override_hmtx.metrics:
            base_hmtx.metrics[target_name] = override_hmtx.metrics[glyph_name]
    
    # Also copy component glyphs that aren't mapped to codepoints
    for comp_name in needed_glyphs:
        if comp_name in override_glyf and comp_name not in base_glyf:
            base_glyf[comp_name] = copy.deepcopy(override_glyf[comp_name])
            if comp_name in override_hmtx.metrics:
                base_hmtx.metrics[comp_name] = override_hmtx.metrics[comp_name]
            if comp_name not in base_font.getGlyphOrder():
                base_font.setGlyphOrder(base_font.getGlyphOrder() + [comp_name])
    
    return replaced, added, skipped


def merge_truetype_to_cff(base_font, override_font, override_codepoints):
    """Merge TrueType glyphs into a CFF base font by converting outlines via pen.
    
    For CID-keyed fonts, new glyphs get allocated CID slots starting after the highest existing CID.
    """
    base_cmap = base_font.getBestCmap()
    override_cmap = override_font.getBestCmap()
    base_hmtx = base_font["hmtx"]
    override_hmtx = override_font["hmtx"]
    
    cff = base_font["CFF "]
    top_dict = cff.cff.topDictIndex[0]
    base_charstrings = top_dict.CharStrings
    
    # Get CFF private dict and global subrs from an existing charstring
    sample_cs = base_charstrings[list(base_charstrings.keys())[0]]
    private = sample_cs.private
    global_subrs = getattr(cff.cff, 'GlobalSubrs', [])
    
    glyphset = override_font.getGlyphSet()
    
    # Find the highest CID for allocating new slots
    max_cid = 0
    for name in base_charstrings.keys():
        if name.startswith("cid"):
            try:
                max_cid = max(max_cid, int(name[3:]))
            except ValueError:
                pass
    next_cid = max_cid + 1
    
    replaced, added, skipped = 0, 0, 0
    
    for cp in sorted(override_codepoints):
        glyph_name = override_cmap.get(cp)
        if not glyph_name or glyph_name not in glyphset:
            skipped += 1
            continue
        
        # First, try converting the glyph BEFORE modifying anything
        try:
            pen = RecordingPen()
            glyphset[glyph_name].draw(pen)
            
            width = override_hmtx.metrics[glyph_name][0] if glyph_name in override_hmtx.metrics else 0
            t2pen = T2CharStringPen(width, glyphSet=None)
            pen.replay(t2pen)
            charstring = t2pen.getCharString()
            charstring.private = private
            charstring.globalSubrs = global_subrs
        except Exception as e:
            logger.warning(f"  Failed to convert glyph U+{cp:04X} ({glyph_name}): {e}")
            skipped += 1
            continue
        
        # Conversion succeeded — now commit the glyph
        if cp in base_cmap:
            # Replace existing glyph
            target_name = base_cmap[cp]
            base_charstrings[target_name] = charstring
            if glyph_name in override_hmtx.metrics:
                base_hmtx.metrics[target_name] = override_hmtx.metrics[glyph_name]
            replaced += 1
        else:
            # Allocate new CID slot
            target_name = f"cid{next_cid:05d}"
            next_cid += 1
            
            # Add to glyph order
            glyph_order = base_font.getGlyphOrder()
            glyph_order.append(target_name)
            base_font.setGlyphOrder(glyph_order)
            
            # Add to charstrings
            base_charstrings.charStrings[target_name] = len(base_charstrings.charStrings)
            base_charstrings.charStringsIndex.append(charstring)
            
            # Add to cmap
            for table in base_font["cmap"].tables:
                if hasattr(table, "cmap") and isinstance(table.cmap, dict):
                    table.cmap[cp] = target_name
            
            # Add hmtx entry
            if glyph_name in override_hmtx.metrics:
                base_hmtx.metrics[target_name] = override_hmtx.metrics[glyph_name]
            else:
                base_hmtx.metrics[target_name] = (width, 0)
            
            added += 1
    
    return replaced, added, skipped


def merge_fonts(base_path: str, override_path: str, output_path: str):
    """
    Merge Latin/Vietnamese glyphs from override_font into base_font.
    Japanese glyphs are preserved.
    """
    logger.info(f"Loading base font: {os.path.basename(base_path)}")
    base_font = TTFont(base_path)
    
    logger.info(f"Loading override font: {os.path.basename(override_path)}")
    override_font = TTFont(override_path)
    
    base_type = get_font_type(base_font)
    override_type = get_font_type(override_font)
    logger.info(f"Base: {base_type}, Override: {override_type}")
    
    override_cmap = override_font.getBestCmap()
    override_codepoints = {cp for cp in override_cmap if should_override(cp)}
    logger.info(f"Found {len(override_codepoints)} overridable glyphs in {os.path.basename(override_path)}")
    
    if base_type == "truetype" and override_type == "truetype":
        replaced, added, skipped = merge_truetype_to_truetype(base_font, override_font, override_codepoints)
    elif base_type == "cff" and override_type == "truetype":
        replaced, added, skipped = merge_truetype_to_cff(base_font, override_font, override_codepoints)
    else:
        raise ValueError(f"Unsupported combination: base={base_type}, override={override_type}")
    
    logger.info(f"Results: {replaced} replaced, {added} added, {skipped} skipped")
    logger.info(f"Saving to: {os.path.basename(output_path)}")
    base_font.save(output_path)
    base_font.close()
    override_font.close()
    logger.info("Done!\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Merge override font into base font.")
    parser.add_argument("base", nargs="?", help="Base font path (e.g. FOT-RodinNTLG Pro EB.otf)")
    parser.add_argument("override", nargs="?", help="Override font path (e.g. MyFont.ttf)")
    parser.add_argument("output", nargs="?", help="Output font path (e.g. Merged.otf)")
    
    args = parser.parse_args()
    
    if args.base and args.override:
        # CLI Mode
        base_path = args.base
        override_path = args.override
        output_path = args.output or f"{os.path.splitext(base_path)[0]} - Merged.otf"
        
        if not os.path.exists(base_path):
            logger.error(f"Base font not found: {base_path}")
            return
        if not os.path.exists(override_path):
            logger.error(f"Override font not found: {override_path}")
            return
            
        merge_fonts(base_path, override_path, output_path)
    else:
        # Default Mode (Hardcoded List)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # EDIT THIS LIST TO ADD MORE PAIRS
        merge_pairs = [
            (
                os.path.join(script_dir, "FOT-RodinNTLG Pro EB.otf"),
                os.path.join(script_dir, "#9Slide05 SVNBellico.ttf"),
                os.path.join(script_dir, "FOT-RodinNTLG Pro EB - Merged.otf"),
            ),
            (
                os.path.join(script_dir, "FOT-RodinNTLG Pro DB.otf"),
                os.path.join(script_dir, "#9Slide03 AMPLESOFT MEDIUM.ttf"),
                os.path.join(script_dir, "FOT-RodinNTLG Pro DB - Merged.otf"),
            ),
        ]
        
        for base_path, override_path, output_path in merge_pairs:
            if not os.path.exists(base_path):
                logger.error(f"Not found: {base_path}")
                continue
            if not os.path.exists(override_path):
                logger.error(f"Not found: {override_path}")
                continue
            
            logger.info("=" * 60)
            logger.info(f"  {os.path.basename(override_path)}")
            logger.info(f"    -> {os.path.basename(base_path)}")
            logger.info("=" * 60)
            merge_fonts(base_path, override_path, output_path)


if __name__ == "__main__":
    main()
