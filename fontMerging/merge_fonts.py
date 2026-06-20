import argparse
import copy
import logging
import os
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OVERRIDE_RANGES = [
    (0x0020, 0x007F), (0x00A0, 0x00FF), (0x0100, 0x024F),
    (0x0250, 0x02AF), (0x02B0, 0x02FF), (0x0300, 0x036F),
    (0x1E00, 0x1EFF), (0x2000, 0x206F), (0x20A0, 0x20CF),
]

def should_override(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in OVERRIDE_RANGES)

def get_font_type(font: TTFont) -> str:
    if "glyf" in font: return "truetype"
    if "CFF " in font: return "cff"
    raise ValueError("Font has no recognized outline format")

def merge_truetype_to_truetype(base_font: TTFont, override_font: TTFont, override_codepoints: set) -> tuple:
    base_cmap, override_cmap = base_font.getBestCmap(), override_font.getBestCmap()
    base_glyf, override_glyf = base_font["glyf"], override_font["glyf"]
    base_hmtx, override_hmtx = base_font["hmtx"], override_font["hmtx"]
    
    valid_cps = {cp: name for cp in sorted(override_codepoints) if (name := override_cmap.get(cp)) in override_glyf}
    needed_glyphs = set(valid_cps.values())
    needed_glyphs.update(
        comp.glyphName
        for name in list(needed_glyphs)
        if hasattr(glyph := override_glyf[name], 'components') and glyph.components
        for comp in glyph.components
    )
    
    replaced = added = 0
    for cp, glyph_name in valid_cps.items():
        if cp in base_cmap:
            target_name = base_cmap[cp]
            replaced += 1
        else:
            target_name = glyph_name
            if target_name not in base_font.getGlyphOrder():
                base_font.setGlyphOrder(base_font.getGlyphOrder() + [target_name])
            for table in base_font["cmap"].tables:
                if hasattr(table, "cmap") and isinstance(table.cmap, dict):
                    table.cmap[cp] = target_name
            added += 1
        
        base_glyf[target_name] = copy.deepcopy(override_glyf[glyph_name])
        if glyph_name in override_hmtx.metrics:
            base_hmtx.metrics[target_name] = override_hmtx.metrics[glyph_name]
            
    for comp_name in needed_glyphs - set(base_glyf.keys()):
        base_glyf[comp_name] = copy.deepcopy(override_glyf.get(comp_name))
        if comp_name in override_hmtx.metrics:
            base_hmtx.metrics[comp_name] = override_hmtx.metrics[comp_name]
        if comp_name not in base_font.getGlyphOrder():
            base_font.setGlyphOrder(base_font.getGlyphOrder() + [comp_name])
            
    return replaced, added, len(override_codepoints) - len(valid_cps)

def merge_truetype_to_cff(base_font: TTFont, override_font: TTFont, override_codepoints: set) -> tuple:
    base_cmap, override_cmap = base_font.getBestCmap(), override_font.getBestCmap()
    base_hmtx, override_hmtx = base_font["hmtx"], override_font["hmtx"]
    base_charstrings = base_font["CFF "].cff.topDictIndex[0].CharStrings
    private = next(iter(base_charstrings.values())).private
    global_subrs = getattr(base_font["CFF "].cff, 'GlobalSubrs', [])
    glyphset = override_font.getGlyphSet()
    
    next_cid = max((int(name[3:]) for name in base_charstrings if name.startswith("cid") and name[3:].isdigit()), default=0) + 1
    replaced = added = skipped = 0
    
    for cp in sorted(override_codepoints):
        if not (glyph_name := override_cmap.get(cp)) or glyph_name not in glyphset:
            skipped += 1
            continue
        try:
            pen = RecordingPen()
            glyphset[glyph_name].draw(pen)
            width = override_hmtx.metrics[glyph_name][0] if glyph_name in override_hmtx.metrics else 0
            t2pen = T2CharStringPen(width, glyphSet=None)
            pen.replay(t2pen)
            charstring = t2pen.getCharString()
            charstring.private, charstring.globalSubrs = private, global_subrs
        except Exception as e:
            logger.warning(f"  Failed to convert glyph U+{cp:04X} ({glyph_name}): {e}")
            skipped += 1
            continue
            
        if cp in base_cmap:
            target_name = base_cmap[cp]
            replaced += 1
        else:
            target_name = f"cid{next_cid:05d}"
            next_cid += 1
            base_font.setGlyphOrder(base_font.getGlyphOrder() + [target_name])
            base_charstrings.charStrings[target_name] = len(base_charstrings.charStrings)
            base_charstrings.charStringsIndex.append(charstring)
            for table in base_font["cmap"].tables:
                if hasattr(table, "cmap") and isinstance(table.cmap, dict):
                    table.cmap[cp] = target_name
            added += 1
            
        base_charstrings[target_name] = charstring
        base_hmtx.metrics[target_name] = override_hmtx.metrics.get(glyph_name, (width, 0))
        
    return replaced, added, skipped

def merge_fonts(base_path: str, override_path: str, output_path: str):
    base_font, override_font = TTFont(base_path), TTFont(override_path)
    base_type, override_type = get_font_type(base_font), get_font_type(override_font)
    override_codepoints = {cp for cp in override_font.getBestCmap() if should_override(cp)}
    
    if base_type == "truetype" and override_type == "truetype":
        merge_truetype_to_truetype(base_font, override_font, override_codepoints)
    elif base_type == "cff" and override_type == "truetype":
        merge_truetype_to_cff(base_font, override_font, override_codepoints)
    else:
        raise ValueError(f"Unsupported combination: base={base_type}, override={override_type}")
        
    base_font.save(output_path)
    base_font.close()
    override_font.close()

def main():
    parser = argparse.ArgumentParser(description="Merge override font into base font.")
    parser.add_argument("base", nargs="?", help="Base font path (e.g. FOT-RodinNTLG Pro EB.otf)")
    parser.add_argument("override", nargs="?", help="Override font path (e.g. MyFont.ttf)")
    parser.add_argument("output", nargs="?", help="Output font path (e.g. Merged.otf)")
    args = parser.parse_args()
    
    if args.base and args.override:
        output_path = args.output or f"{os.path.splitext(args.base)[0]} - Merged.otf"
        if os.path.exists(args.base) and os.path.exists(args.override):
            merge_fonts(args.base, args.override, output_path)
        else:
            logger.error("Base or override font not found.")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        merge_pairs = [
            (os.path.join(script_dir, "FOT-RodinNTLG Pro EB.otf"), os.path.join(script_dir, "YourFont1.ttf"), os.path.join(script_dir, "FOT-RodinNTLGPro-EB-OnDemand.otf")),
            (os.path.join(script_dir, "FOT-RodinNTLG Pro DB.otf"), os.path.join(script_dir, "YourFont2.ttf"), os.path.join(script_dir, "FOT-RodinNTLGPro-DB-OnDemand.otf")),
        ]
        for base, override, out in merge_pairs:
            if os.path.exists(base) and os.path.exists(override):
                merge_fonts(base, override, out)
            else:
                logger.error(f"Missing file(s) for pair: {base} / {override}")

if __name__ == "__main__":
    main()