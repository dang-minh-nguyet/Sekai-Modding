"""
build_font_bundle.py
--------------------
Build an encrypted Project Sekai `common` font AssetBundle directly from two
merged .otf/.ttf fonts (DB + EB) WITHOUT Unity Editor, using `msdf-atlas-gen`
and `UnityPy` (Unity 2022.3.62f2).

What it does:
  1. Decrypts `script/common.bak`
  2. Generates 4096x2048 Alpha8 SDF atlases & glyph metrics via `msdf-atlas-gen`
     (auto-downloads official Windows binary on first run if not found)
  3. Patches both `TMP_FontAsset` MonoBehaviours, both `Texture2D` atlases,
     and all 3 `Material`s (DB, EB, EB-Gacha) inside the bundle
  4. Packs with LZ4, re-encrypts the 128-byte header, and writes `script/common`

Usage (with uv):
  uv run script/build_font_bundle.py
"""

import argparse
import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from typing import Dict, List, Optional, Sequence

import numpy as np
from PIL import Image
import UnityPy
from UnityPy.enums import ClassIDType

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

UNITY_VERSION = "2022.3.62f2"
MAGIC = b"\x10\x00\x00\x00"
HEADER_SIZE = 128
RENDER_MODE_SDFAA = 4169

MSDF_RELEASE_URL_WIN64 = (
    "https://github.com/Chlumsky/msdf-atlas-gen/releases/download/v1.4/msdf-atlas-gen-1.4-win64.zip"
)

# Full 134 precomposed Vietnamese accented letters + printable ASCII + NBSP/₫/full-width space
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
EXTRA_DEFAULT_CHARS = (
    "".join(chr(c) for c in range(0x0020, 0x007F))
    + VIETNAMESE_CHARS
    + "\u00a0\u20ab\u3000"
)


# =============================================================================
# Bundle crypto helpers (128-byte self-inverse XOR header)
# =============================================================================

def flip_header_inplace(header: bytearray) -> bytearray:
    assert len(header) == HEADER_SIZE
    for i in range(0, HEADER_SIZE, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header


def decrypt_bundle(path: str) -> bytes:
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic == MAGIC:
            hdr = bytearray(f.read(HEADER_SIZE))
            flip_header_inplace(hdr)
            return bytes(hdr) + f.read()
        f.seek(0)
        return f.read()


def encrypt_bundle(raw: bytes) -> bytes:
    hdr = bytearray(raw[:HEADER_SIZE])
    flip_header_inplace(hdr)
    return MAGIC + bytes(hdr) + raw[HEADER_SIZE:]


# =============================================================================
# msdf-atlas-gen discovery / auto-download & SDF atlas generation
# =============================================================================

def ensure_msdf_atlas_gen(explicit_path: Optional[str]) -> str:
    if explicit_path:
        if os.path.isfile(explicit_path):
            return explicit_path
        raise FileNotFoundError(f"msdf-atlas-gen binary not found at: {explicit_path}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cached_bin = os.path.join(script_dir, "tools", "msdf-atlas-gen.exe")

    candidates = [
        cached_bin,
        os.path.join(script_dir, "msdf-atlas-gen.exe"),
        os.path.join(script_dir, "msdf-atlas-gen"),
        shutil.which("msdf-atlas-gen") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c

    # Auto-download official Windows x64 binary on first run
    if os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64"):
        logger.info("msdf-atlas-gen not found locally — downloading official v1.4 release...")
        tools_dir = os.path.dirname(cached_bin)
        os.makedirs(tools_dir, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="msdf_dl_") as tmpdir:
            zip_path = os.path.join(tmpdir, "msdf-atlas-gen.zip")
            req = urllib.request.Request(
                MSDF_RELEASE_URL_WIN64, headers={"User-Agent": "Sekai-Modding"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(zip_path, "wb") as out:
                shutil.copyfileobj(resp, out)
            with zipfile.ZipFile(zip_path, "r") as zf:
                exe_member = next(
                    (m for m in zf.namelist() if m.lower().endswith("msdf-atlas-gen.exe")),
                    None,
                )
                if not exe_member:
                    raise RuntimeError("msdf-atlas-gen.exe not found inside downloaded zip")
                with zf.open(exe_member) as src, open(cached_bin, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        logger.info(f"Saved msdf-atlas-gen -> {cached_bin}")
        return cached_bin

    raise FileNotFoundError(
        "msdf-atlas-gen not found. Install it or pass --msdf-bin <path>.\n"
        "Releases: https://github.com/Chlumsky/msdf-atlas-gen/releases"
    )


def build_face_info(data: dict, point_size: int, orig_face_info: dict) -> dict:
    m = data["metrics"]
    size = float(data["atlas"]["size"])
    ascent = float(m.get("ascender", 0.88)) * size
    descent = float(m.get("descender", -0.12)) * size
    line_height = float(m.get("lineHeight", 2.0)) * size
    underline_y = float(m.get("underlineY", -0.1)) * size
    underline_t = max(0.5, float(m.get("underlineThickness", 0.05)) * size)

    glyphs_by_u = {g["unicode"]: g for g in data["glyphs"] if "unicode" in g}
    orig_pt = max(1, orig_face_info.get("m_PointSize", point_size))
    cap_line = orig_face_info.get("m_CapLine", ascent * 0.9) * (size / orig_pt)
    mean_line = orig_face_info.get("m_MeanLine", ascent * 0.65) * (size / orig_pt)
    tab_width = size * 0.35

    half_range = float(data["atlas"].get("distanceRange", 12)) / 2.0
    if ord("H") in glyphs_by_u and "planeBounds" in glyphs_by_u[ord("H")]:
        cap_line = glyphs_by_u[ord("H")]["planeBounds"]["top"] * size - half_range
    if ord("x") in glyphs_by_u and "planeBounds" in glyphs_by_u[ord("x")]:
        mean_line = glyphs_by_u[ord("x")]["planeBounds"]["top"] * size - half_range
    if 0x20 in glyphs_by_u:
        tab_width = float(glyphs_by_u[0x20].get("advance", 0.35)) * size

    face_info = dict(orig_face_info)
    face_info.update({
        "m_FaceIndex": 0,
        "m_PointSize": int(round(size)),
        "m_Scale": 1.0,
        "m_UnitsPerEM": 0,
        "m_LineHeight": float(line_height),
        "m_AscentLine": float(ascent),
        "m_CapLine": float(cap_line),
        "m_MeanLine": float(mean_line),
        "m_Baseline": 0.0,
        "m_DescentLine": float(descent),
        "m_SuperscriptOffset": float(ascent),
        "m_SuperscriptSize": 0.5,
        "m_SubscriptOffset": float(descent),
        "m_SubscriptSize": 0.5,
        "m_UnderlineOffset": float(underline_y),
        "m_UnderlineThickness": float(underline_t),
        "m_StrikethroughOffset": float(mean_line * 0.4),
        "m_StrikethroughThickness": float(underline_t),
        "m_TabWidth": float(tab_width),
    })
    return face_info


def generate_sdf_atlas(
    font_path: str,
    codepoints: Sequence[int],
    point_size: int,
    padding: int,
    atlas_w: int,
    atlas_h: int,
    orig_face_info: dict,
    msdf_bin: str,
) -> dict:
    """Generate a single-channel Alpha8 SDF atlas and TMP glyph/character tables via msdf-atlas-gen."""
    t0 = time.time()
    pxrange = 2 * (padding + 1)  # Matches Unity TMP _GradientScale = padding + 1

    with tempfile.TemporaryDirectory(prefix="sekai_msdf_") as tmpdir:
        charset_path = os.path.join(tmpdir, "charset.txt")
        atlas_png = os.path.join(tmpdir, "atlas.png")
        atlas_json = os.path.join(tmpdir, "atlas.json")

        uniq_cps = sorted(set(cp for cp in codepoints if cp > 0))
        with open(charset_path, "w", encoding="ascii") as f:
            f.write(", ".join(str(cp) for cp in uniq_cps))

        cmd = [
            msdf_bin,
            "-font", font_path,
            "-charset", charset_path,
            "-type", "sdf",
            "-size", str(point_size),
            "-pxrange", str(pxrange),
            "-pxpadding", "1",
            "-dimensions", str(atlas_w), str(atlas_h),
            "-yorigin", "bottom",
            "-imageout", atlas_png,
            "-json", atlas_json,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"msdf-atlas-gen failed (exit={res.returncode}):\n{res.stdout}\n{res.stderr}"
            )

        with open(atlas_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Flip PNG (top-down on disk) to Unity Texture2D bottom-up Alpha8 buffer
        img = np.array(Image.open(atlas_png).convert("L"), dtype=np.uint8)
        if img.shape != (atlas_h, atlas_w):
            raise RuntimeError(
                f"Atlas size mismatch: got {img.shape[1]}x{img.shape[0]}, expected {atlas_w}x{atlas_h}"
            )
        atlas_gl = np.ascontiguousarray(img[::-1, :])

    size = float(data["atlas"]["size"])
    face_info = build_face_info(data, point_size, orig_face_info)

    glyph_table = []
    character_table = []
    used_rects = []

    for idx, g in enumerate(sorted(data["glyphs"], key=lambda x: x["unicode"]), start=1):
        cp = int(g["unicode"])
        adv = float(g.get("advance", 0.0)) * size

        if "atlasBounds" not in g or "planeBounds" not in g:
            metrics = {
                "m_Width": 0.0,
                "m_Height": 0.0,
                "m_HorizontalBearingX": 0.0,
                "m_HorizontalBearingY": 0.0,
                "m_HorizontalAdvance": adv,
            }
            rect = {"m_X": 0, "m_Y": 0, "m_Width": 0, "m_Height": 0}
        else:
            ab = g["atlasBounds"]
            pb = g["planeBounds"]
            # Convert pixel-center bounds -> pixel edges, then shrink inward by `padding`
            # so TMP's +/- padding UV expansion aligns 1:1 with zero baseline drift.
            ax0 = int(round(ab["left"] - 0.5))
            ay0 = int(round(ab["bottom"] - 0.5))
            ax1 = int(round(ab["right"] + 0.5))
            ay1 = int(round(ab["top"] + 0.5))

            pL = pb["left"] * size - 0.5
            pB = pb["bottom"] * size - 0.5
            pR = pb["right"] * size + 0.5
            pT = pb["top"] * size + 0.5

            rect = {
                "m_X": int(ax0 + padding),
                "m_Y": int(ay0 + padding),
                "m_Width": int(max(0, (ax1 - ax0) - 2 * padding)),
                "m_Height": int(max(0, (ay1 - ay0) - 2 * padding)),
            }
            metrics = {
                "m_Width": float(max(0.0, (pR - pL) - 2 * padding)),
                "m_Height": float(max(0.0, (pT - pB) - 2 * padding)),
                "m_HorizontalBearingX": float(pL + padding),
                "m_HorizontalBearingY": float(pT - padding),
                "m_HorizontalAdvance": adv,
            }
            used_rects.append({"m_X": ax0, "m_Y": ay0, "m_Width": ax1 - ax0, "m_Height": ay1 - ay0})

        glyph_table.append({
            "m_Index": idx,
            "m_Metrics": metrics,
            "m_GlyphRect": rect,
            "m_Scale": 1.0,
            "m_AtlasIndex": 0,
            "m_ClassDefinitionType": 0,
        })
        character_table.append({
            "m_ElementType": 1,
            "m_Unicode": cp,
            "m_GlyphIndex": idx,
            "m_Scale": 1.0,
        })

    dt = time.time() - t0
    logger.info(
        f"Generated SDF atlas for '{os.path.basename(font_path)}': "
        f"{len(glyph_table)} glyphs in {dt:.2f}s"
    )

    return {
        "alpha8_bytes": atlas_gl.tobytes(),
        "face_info": face_info,
        "glyph_table": glyph_table,
        "character_table": character_table,
        "used_rects": used_rects,
        "free_rects": [],
        "atlas_w": atlas_w,
        "atlas_h": atlas_h,
        "padding": padding,
        "render_mode": RENDER_MODE_SDFAA,
    }


# =============================================================================
# UnityPy bundle patcher (common.bak -> encrypted common)
# =============================================================================

def update_material_float(mat_tt: dict, prop_name: str, value: float) -> None:
    floats = mat_tt.get("m_SavedProperties", {}).get("m_Floats", [])
    for i, entry in enumerate(floats):
        if isinstance(entry, dict) and entry.get("first") == prop_name:
            entry["second"] = float(value)
            return
        if isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[0] == prop_name:
            floats[i] = (prop_name, float(value)) if isinstance(entry, tuple) else [prop_name, float(value)]
            return


def get_material_main_tex_path_id(mat_tt: dict) -> Optional[int]:
    tex_envs = mat_tt.get("m_SavedProperties", {}).get("m_TexEnvs", [])
    for entry in tex_envs:
        k = entry.get("first") if isinstance(entry, dict) else entry[0]
        v = entry.get("second") if isinstance(entry, dict) else entry[1]
        if k == "_MainTex" and isinstance(v, dict):
            tex = v.get("m_Texture", {})
            if isinstance(tex, dict):
                return tex.get("m_PathID")
    return None


def build_bundle(
    original_bundle: str,
    db_font_path: str,
    eb_font_path: str,
    output_path: str,
    *,
    msdf_bin: Optional[str] = None,
    charset_path: Optional[str] = None,
    point_size: int = 42,
    padding: int = 5,
    atlas_w: int = 4096,
    atlas_h: int = 2048,
) -> None:
    UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION
    resolved_msdf = ensure_msdf_atlas_gen(msdf_bin)

    logger.info(f"Loading original bundle: {original_bundle} (Unity {UNITY_VERSION})")
    raw = decrypt_bundle(original_bundle)
    env = UnityPy.load(io.BytesIO(raw))

    font_objs = {}
    tex_objs = {}
    mat_objs = []
    for obj in env.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            d = obj.read()
            name = getattr(d, "m_Name", "")
            if name in ("FOT-RodinNTLGPro-DB-OnDemand", "FOT-RodinNTLGPro-EB-OnDemand"):
                font_objs[name] = obj
        elif obj.type == ClassIDType.Texture2D:
            d = obj.read()
            tex_objs[getattr(d, "m_Name", "")] = obj
        elif obj.type == ClassIDType.Material:
            mat_objs.append(obj)

    if len(font_objs) != 2:
        raise RuntimeError(f"Expected DB & EB TMP_FontAssets in bundle, found: {list(font_objs.keys())}")

    if charset_path:
        with open(charset_path, "r", encoding="utf-8") as f:
            codepoints = sorted(set(ord(ch) for ch in f.read()))
        logger.info(f"Using custom charset '{charset_path}': {len(codepoints)} unique chars")
    else:
        orig_cps = set()
        for fobj in font_objs.values():
            tt = fobj.read_typetree()
            for entry in tt.get("m_CharacterTable", []):
                orig_cps.add(int(entry["m_Unicode"]))
        orig_cps.update(ord(ch) for ch in EXTRA_DEFAULT_CHARS)
        codepoints = sorted(orig_cps)
        logger.info(
            f"Using common.bak original charset + full ASCII/Vietnamese: {len(codepoints)} unique chars"
        )

    targets = [
        ("FOT-RodinNTLGPro-DB-OnDemand", db_font_path),
        ("FOT-RodinNTLGPro-EB-OnDemand", eb_font_path),
    ]
    atlas_path_ids_updated: Dict[int, dict] = {}

    for asset_name, font_path in targets:
        font_obj = font_objs[asset_name]
        tex_name = f"{asset_name} Atlas"
        if tex_name not in tex_objs:
            raise RuntimeError(f"Texture '{tex_name}' not found in bundle")
        tex_obj = tex_objs[tex_name]

        font_tt = font_obj.read_typetree()
        built = generate_sdf_atlas(
            font_path,
            codepoints,
            point_size,
            padding,
            atlas_w,
            atlas_h,
            font_tt["m_FaceInfo"],
            resolved_msdf,
        )

        # 1. Patch Texture2D (Alpha8, bottom-up, inline image_data)
        tex_data = tex_obj.read()
        tex_data.m_Width = built["atlas_w"]
        tex_data.m_Height = built["atlas_h"]
        tex_data.m_TextureFormat = 1  # Alpha8
        tex_data.m_MipCount = 1
        tex_data.m_CompleteImageSize = len(built["alpha8_bytes"])
        tex_data.image_data = built["alpha8_bytes"]
        if hasattr(tex_data, "m_StreamData") and tex_data.m_StreamData:
            tex_data.m_StreamData.offset = 0
            tex_data.m_StreamData.size = 0
            tex_data.m_StreamData.path = ""
        tex_data.save()
        atlas_path_ids_updated[tex_obj.path_id] = built

        # 2. Patch TMP_FontAsset TypeTree in-place
        font_tt["m_FaceInfo"] = built["face_info"]
        font_tt["m_GlyphTable"] = built["glyph_table"]
        font_tt["m_CharacterTable"] = built["character_table"]
        font_tt["m_AtlasWidth"] = built["atlas_w"]
        font_tt["m_AtlasHeight"] = built["atlas_h"]
        font_tt["m_AtlasPadding"] = built["padding"]
        font_tt["m_AtlasRenderMode"] = built["render_mode"]
        font_tt["m_AtlasPopulationMode"] = 0  # Static
        font_tt["m_UsedGlyphRects"] = built["used_rects"]
        font_tt["m_FreeGlyphRects"] = built["free_rects"]
        font_tt["m_FontFeatureTable"] = {"m_GlyphPairAdjustmentRecords": []}
        font_obj.save_typetree(font_tt)

    # 3. Update ALL Materials referencing either atlas (DB, EB, EB-Gacha)
    for mat_obj in mat_objs:
        mat_tt = mat_obj.read_typetree()
        main_tex_id = get_material_main_tex_path_id(mat_tt)
        if main_tex_id in atlas_path_ids_updated:
            built = atlas_path_ids_updated[main_tex_id]
            update_material_float(mat_tt, "_TextureWidth", float(built["atlas_w"]))
            update_material_float(mat_tt, "_TextureHeight", float(built["atlas_h"]))
            update_material_float(mat_tt, "_GradientScale", float(built["padding"] + 1))
            mat_obj.save_typetree(mat_tt)
            logger.info(
                f"Updated Material '{mat_tt['m_Name']}' "
                f"(W={built['atlas_w']}, H={built['atlas_h']}, GS={built['padding'] + 1})"
            )

    # 4. Pack LZ4 & encrypt header
    logger.info("Packing LZ4 bundle & encrypting header...")
    packed = env.file.save(packer="lz4")
    encrypted = encrypt_bundle(packed)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(encrypted)

    logger.info(f"DONE! Saved encrypted bundle -> {output_path} ({len(encrypted):,} bytes)")
    logger.info("Rename this file to '4ad9182d51b21d790af3f73d72ddc193' and copy to your game's 47a2/ folder.")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)

    parser = argparse.ArgumentParser(
        description="Build encrypted Project Sekai font bundle directly without Unity Editor (msdf-atlas-gen + UnityPy)."
    )
    parser.add_argument(
        "--db",
        default=os.path.join(repo_root, "fontMerging", "FOT-RodinNTLGPro-DB-OnDemand.otf"),
        help="Path to merged DB font (default: fontMerging/FOT-RodinNTLGPro-DB-OnDemand.otf)",
    )
    parser.add_argument(
        "--eb",
        default=os.path.join(repo_root, "fontMerging", "FOT-RodinNTLGPro-EB-OnDemand.otf"),
        help="Path to merged EB font (default: fontMerging/FOT-RodinNTLGPro-EB-OnDemand.otf)",
    )
    parser.add_argument(
        "--original",
        default=os.path.join(script_dir, "common.bak"),
        help="Path to original encrypted common.bak bundle (default: script/common.bak)",
    )
    parser.add_argument(
        "--output", "-o",
        default=os.path.join(script_dir, "common"),
        help="Output encrypted bundle path (default: script/common)",
    )
    parser.add_argument(
        "--charset",
        default=None,
        help="Optional UTF-8 text file of characters (default: common.bak charset + ASCII & Vietnamese)",
    )
    parser.add_argument("--msdf-bin", default=None, help="Optional path to msdf-atlas-gen executable")
    parser.add_argument("--point-size", type=int, default=42, help="Sampling point size (default: 42)")
    parser.add_argument("--padding", type=int, default=5, help="SDF padding in pixels (default: 5)")
    parser.add_argument("--width", type=int, default=4096, help="Atlas width (default: 4096)")
    parser.add_argument("--height", type=int, default=2048, help="Atlas height (default: 2048)")
    args = parser.parse_args()

    for label, path in [("original bundle", args.original), ("DB font", args.db), ("EB font", args.eb)]:
        if not os.path.isfile(path):
            sys.exit(f"[ERROR] Missing {label}: {path}")

    build_bundle(
        original_bundle=args.original,
        db_font_path=args.db,
        eb_font_path=args.eb,
        output_path=args.output,
        msdf_bin=args.msdf_bin,
        charset_path=args.charset,
        point_size=args.point_size,
        padding=args.padding,
        atlas_w=args.width,
        atlas_h=args.height,
    )


if __name__ == "__main__":
    main()
