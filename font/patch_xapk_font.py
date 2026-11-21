#!/usr/bin/env python3
"""Patch merged DB/EB fonts directly into a Project Sekai XAPK (JP / EN).

Unlike `build_font_bundle.py` (which outputs an encrypted `font/common` bundle
to copy into Android/data/.../47a2/), this script patches the built-in font
assets directly inside `UnityDataAssetPack.apk` and outputs a zipaligned,
signed `.xapk` ready to install via SAI — no Shizuku / Root / Android/data
access required on Android 11+.

What it patches inside UnityDataAssetPack.apk (discovered dynamically via
globalgamemanagers ResourceManager — works for JP, EN, and future updates):
  1. `font/fot-rodinntlgpro-db` & `eb` (Unity Font):
     Replaces embedded OTF `m_FontData` with your merged DB/EB fonts so
     `SDF_Dynamic` fallback renders any missing glyph using your font.
  2. `font/fot-rodinntlgpro-db-builtin` & `eb-builtin` (TMP_FontAsset + 1024x1024 Atlas):
     Rebuilds the built-in startup/title SDF atlases with original 400 chars
     + full ASCII + full Vietnamese.
  3. `font/fot-rodinntlgpro-db sdf_base` & `eb sdf_base` (+ all ~36 preset Materials):
     Bakes full printable ASCII + all 134 Vietnamese accented characters into
     the primary `SDF_Base` atlases (1024x1024) and updates `_TextureWidth`,
     `_TextureHeight`, and `_GradientScale` on every preset Material referencing
     them (scenario, outline, gacha, difficulty, etc.). Because TMP checks
     `SDF_Base` before `font/common`, all Latin & Vietnamese text across the
     entire game renders with your custom font while Japanese Kanji/Kana
     continue falling back seamlessly to `font/common` and `SDF_Dynamic`.

Optional: pass `--speed-ms 35` (and `--auto-delay 1.0`) to combine Font Mod +
Speed Change into a single signed `.xapk` in one run.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import shutil
import sys
import time
import warnings
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import UnityPy
from UnityPy.enums import ClassIDType

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

FONT_DIR = Path(__file__).resolve().parent
ROOT_DIR = FONT_DIR.parent
SPEED_DIR = ROOT_DIR / "speed_change"
OUTPUT_DIR = FONT_DIR / "output"
WORK_DIR = FONT_DIR / "work"

# Import shared helpers from build_font_bundle.py & speed_change.py
sys.path.insert(0, str(FONT_DIR))
sys.path.insert(0, str(SPEED_DIR))

import build_font_bundle as bfb  # noqa: E402
import speed_change as sc  # noqa: E402

warnings.filterwarnings("ignore", message="No valid Unity version found.*")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_tmp_fontasset_typetree(common_bak_path: Path):
    """Extract the Unity 2022.3 TMP_FontAsset TypeTreeNode from font/assets/common.bak."""
    UnityPy.config.FALLBACK_UNITY_VERSION = bfb.UNITY_VERSION
    raw = bfb.decrypt_bundle(str(common_bak_path))
    env = UnityPy.load(io.BytesIO(raw))
    for obj in env.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            d = obj.read()
            if getattr(d, "m_Name", "") in ("FOT-RodinNTLGPro-DB-OnDemand", "FOT-RodinNTLGPro-EB-OnDemand"):
                return obj.serialized_type.nodes
    raise RuntimeError(f"Không tìm thấy TMP_FontAsset TypeTree trong {common_bak_path}")


def read_resource_manager_map(extract_dir: Path) -> Dict[str, List[Tuple[str, int]]]:
    """Read ResourceManager m_Container from globalgamemanagers -> {res_path: [(filename, path_id), ...]}."""
    for apk_file in sorted(extract_dir.glob("*.apk")):
        with zipfile.ZipFile(apk_file, "r") as zf:
            if "assets/bin/Data/globalgamemanagers" not in zf.namelist():
                continue
            ggm_bytes = zf.read("assets/bin/Data/globalgamemanagers")
            env = UnityPy.load(ggm_bytes)
            sf = next(iter(env.files.values()))
            externals = [e.path for e in getattr(sf, "externals", [])]
            res_map: Dict[str, List[Tuple[str, int]]] = {}
            for obj in env.objects:
                if obj.type.name == "ResourceManager":
                    tree = obj.read_typetree()
                    for item in tree.get("m_Container", []):
                        path = item["first"] if isinstance(item, dict) else item[0]
                        pptr = item["second"] if isinstance(item, dict) else item[1]
                        fid = pptr["m_FileID"]
                        pid = pptr["m_PathID"]
                        fname = "globalgamemanagers" if fid == 0 else externals[fid - 1]
                        res_map.setdefault(path, []).append((fname, pid))
                    return res_map
    raise RuntimeError("Không tìm thấy globalgamemanagers / ResourceManager trong XAPK.")


def patch_embedded_font_asset(asset_bytes: bytes, font_file_path: Path) -> bytes:
    """Replace Font.m_FontData inside a serialized Unity Font asset file."""
    font_bytes = font_file_path.read_bytes()
    env = UnityPy.load(asset_bytes)
    patched = False
    for obj in env.objects:
        if obj.type == ClassIDType.Font:
            d = obj.read()
            d.m_FontData = font_bytes
            d.save()
            patched = True
            logger.info(f"  Patched embedded Font '{d.m_Name}' ({len(font_bytes):,} bytes)")
    if not patched:
        raise RuntimeError("Không tìm thấy object Font trong asset mục tiêu.")
    sf = next(iter(env.files.values()))
    return sf.save()


def patch_tmp_asset_file(
    asset_bytes: bytes,
    font_file_path: Path,
    codepoints: Sequence[int],
    *,
    tmp_nodes,
    msdf_bin: str,
    point_size: int,
    padding: int,
    atlas_w: int,
    atlas_h: int,
    keep_existing_chars: bool = False,
) -> Tuple[bytes, dict]:
    """Rebuild Texture2D + TMP_FontAsset + internal Material in a serialized TMP font file."""
    env = UnityPy.load(asset_bytes)
    font_obj = None
    tex_obj = None
    mat_objs = []

    for obj in env.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            font_obj = obj
        elif obj.type == ClassIDType.Texture2D:
            tex_obj = obj
        elif obj.type == ClassIDType.Material:
            mat_objs.append(obj)

    if not font_obj or not tex_obj:
        raise RuntimeError("Asset TMP_FontAsset thiếu MonoBehaviour hoặc Texture2D.")

    font_tt = font_obj.read_typetree(nodes=tmp_nodes)

    target_cps = set(cp for cp in codepoints if cp >= 0x20)
    if keep_existing_chars:
        for entry in font_tt.get("m_CharacterTable", []):
            cp = int(entry["m_Unicode"])
            if cp >= 0x20:
                target_cps.add(cp)
    sorted_cps = sorted(target_cps)

    built = bfb.generate_sdf_atlas(
        str(font_file_path),
        sorted_cps,
        point_size,
        padding,
        atlas_w,
        atlas_h,
        font_tt["m_FaceInfo"],
        msdf_bin,
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

    # 2. Patch TMP_FontAsset MonoBehaviour using borrowed TypeTree nodes
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
    font_obj.save_typetree(font_tt, nodes=tmp_nodes)

    # 3. Patch internal Material(s)
    for mat_obj in mat_objs:
        mat_tt = mat_obj.read_typetree()
        bfb.update_material_float(mat_tt, "_TextureWidth", float(built["atlas_w"]))
        bfb.update_material_float(mat_tt, "_TextureHeight", float(built["atlas_h"]))
        bfb.update_material_float(mat_tt, "_GradientScale", float(built["padding"] + 1))
        mat_obj.save_typetree(mat_tt)

    sf = next(iter(env.files.values()))
    logger.info(
        f"  Patched TMP '{font_tt['m_Name']}' "
        f"({len(built['glyph_table'])} glyphs, {atlas_w}x{atlas_h}, pt={point_size}, pad={padding})"
    )
    return sf.save(), built


def find_data_apk(extract_dir: Path, sample_hash: str) -> Path:
    """Locate the split APK containing assets/bin/Data/<sample_hash>."""
    target = f"assets/bin/Data/{sample_hash}"
    for apk_file in sorted(extract_dir.glob("*.apk")):
        with zipfile.ZipFile(apk_file, "r") as zf:
            if target in zf.namelist():
                return apk_file
    raise RuntimeError(f"Không tìm thấy {target} trong bất kỳ split APK nào.")


def patch_external_sdf_materials(
    zf: zipfile.ZipFile,
    atlas_specs: Dict[str, dict],
) -> Dict[str, bytes]:
    """Update _TextureWidth / _TextureHeight / _GradientScale on all Materials referencing SDF_Base atlases."""
    replacements: Dict[str, bytes] = {}
    target_bytes = {h.encode("ascii"): h for h in atlas_specs}

    for entry_name in zf.namelist():
        if not entry_name.startswith("assets/bin/Data/"):
            continue
        fname = Path(entry_name).name
        if fname in atlas_specs:
            continue  # Internal material already updated when rebuilding SDF_Base
        raw = zf.read(entry_name)
        if not any(tb in raw for tb in target_bytes):
            continue
        try:
            env = UnityPy.load(raw)
        except Exception:
            continue

        sf = next(iter(env.files.values()))
        fexts = [e.path for e in getattr(sf, "externals", [])]
        modified = False

        for obj in env.objects:
            if obj.type != ClassIDType.Material:
                continue
            mat_tt = obj.read_typetree()
            tex_envs = mat_tt.get("m_SavedProperties", {}).get("m_TexEnvs", [])
            ref_hash = None
            for entry in tex_envs:
                k = entry.get("first") if isinstance(entry, dict) else entry[0]
                v = entry.get("second") if isinstance(entry, dict) else entry[1]
                if k == "_MainTex" and isinstance(v, dict):
                    tex = v.get("m_Texture", {})
                    fid = tex.get("m_FileID", 0)
                    if fid > 0 and fid - 1 < len(fexts) and fexts[fid - 1] in atlas_specs:
                        ref_hash = fexts[fid - 1]
                        break
            if ref_hash:
                built = atlas_specs[ref_hash]
                bfb.update_material_float(mat_tt, "_TextureWidth", float(built["atlas_w"]))
                bfb.update_material_float(mat_tt, "_TextureHeight", float(built["atlas_h"]))
                bfb.update_material_float(mat_tt, "_GradientScale", float(built["padding"] + 1))
                obj.save_typetree(mat_tt)
                modified = True

        if modified:
            replacements[entry_name] = sf.save()

    return replacements


def patch_fonts_in_xapk(
    extract_dir: Path,
    db_font: Path,
    eb_font: Path,
    *,
    common_bak: Path,
    msdf_bin: str,
    base_codepoints: Sequence[int],
    base_point_size: int = 42,
    builtin_point_size: int = 36,
    padding: int = 5,
    atlas_size: int = 1024,
    patch_sdf_base: bool = True,
) -> Path:
    """Patch embedded Font OTFs, Builtin atlases, and SDF_Base (+ preset materials) in-place."""
    res_map = read_resource_manager_map(extract_dir)

    def get_hash(res_key: str) -> str:
        entries = res_map.get(res_key)
        if not entries:
            raise RuntimeError(f"Không tìm thấy resource '{res_key}' trong globalgamemanagers.")
        return entries[0][0]

    db_font_hash = get_hash("font/fot-rodinntlgpro-db")
    eb_font_hash = get_hash("font/fot-rodinntlgpro-eb")
    db_builtin_hash = get_hash("font/fot-rodinntlgpro-db-builtin")
    eb_builtin_hash = get_hash("font/fot-rodinntlgpro-eb-builtin")
    db_base_hash = get_hash("font/fot-rodinntlgpro-db sdf_base")
    eb_base_hash = get_hash("font/fot-rodinntlgpro-eb sdf_base")

    data_apk = find_data_apk(extract_dir, db_font_hash)
    tmp_nodes = load_tmp_fontasset_typetree(common_bak)

    replacements: Dict[str, bytes] = {}
    base_atlas_specs: Dict[str, dict] = {}

    with zipfile.ZipFile(data_apk, "r") as zf:
        # 1. Embedded OTF Font assets (powers SDF_Dynamic)
        for label, fhash, fpath in [
            ("DB", db_font_hash, db_font),
            ("EB", eb_font_hash, eb_font),
        ]:
            entry = f"assets/bin/Data/{fhash}"
            replacements[entry] = patch_embedded_font_asset(zf.read(entry), fpath)

        # 2. Builtin TMP_FontAssets (original 400 chars + ASCII + Vietnamese)
        for label, fhash, fpath in [
            ("DB-Builtin", db_builtin_hash, db_font),
            ("EB-Builtin", eb_builtin_hash, eb_font),
        ]:
            entry = f"assets/bin/Data/{fhash}"
            patched_bytes, _built = patch_tmp_asset_file(
                zf.read(entry),
                fpath,
                base_codepoints,
                tmp_nodes=tmp_nodes,
                msdf_bin=msdf_bin,
                point_size=builtin_point_size,
                padding=padding,
                atlas_w=atlas_size,
                atlas_h=atlas_size,
                keep_existing_chars=True,
            )
            replacements[entry] = patched_bytes

        # 3. SDF_Base primary TMP_FontAssets + all external preset Materials
        if patch_sdf_base:
            for label, fhash, fpath in [
                ("DB SDF_Base", db_base_hash, db_font),
                ("EB SDF_Base", eb_base_hash, eb_font),
            ]:
                entry = f"assets/bin/Data/{fhash}"
                patched_bytes, built = patch_tmp_asset_file(
                    zf.read(entry),
                    fpath,
                    base_codepoints,
                    tmp_nodes=tmp_nodes,
                    msdf_bin=msdf_bin,
                    point_size=base_point_size,
                    padding=padding,
                    atlas_w=atlas_size,
                    atlas_h=atlas_size,
                    keep_existing_chars=True,
                )
                replacements[entry] = patched_bytes
                base_atlas_specs[fhash] = built

            mat_replacements = patch_external_sdf_materials(zf, base_atlas_specs)
            logger.info(
                f"  Updated {len(mat_replacements)} external preset Materials referencing DB/EB SDF_Base."
            )
            replacements.update(mat_replacements)

    logger.info(f"  Rebuilding {data_apk.name} ({len(replacements)} modified Unity assets)...")
    sc.patch_apk_rebuild(data_apk, replacements)
    return data_apk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch font tiếng Việt/Latin trực tiếp vào file XAPK của Project Sekai (JP/EN)\n"
            "mà không cần chép file vào Android/data (không cần Shizuku/Root)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ví dụ:\n"
            "  # Sau khi đã gộp font bằng font/merge_fonts.py:\n"
            "  uv run font/patch_xapk_font.py\n"
            "  uv run font/patch_xapk_font.py --region en\n"
            "  # Kết hợp mod font + đổi tốc độ chữ 35ms vào chung 1 file XAPK:\n"
            "  uv run font/patch_xapk_font.py --speed-ms 35\n"
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=OUTPUT_DIR / "FOT-RodinNTLGPro-DB-OnDemand.otf",
        help="File font DB đã gộp (mặc định: font/output/FOT-RodinNTLGPro-DB-OnDemand.otf).",
    )
    parser.add_argument(
        "--eb",
        type=Path,
        default=OUTPUT_DIR / "FOT-RodinNTLGPro-EB-OnDemand.otf",
        help="File font EB đã gộp (mặc định: font/output/FOT-RodinNTLGPro-EB-OnDemand.otf).",
    )
    parser.add_argument(
        "--region",
        choices=list(sc.REGIONS.keys()),
        default="jp",
        help="Server game: jp (mặc định) hoặc en.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Đường dẫn file .xapk có sẵn trên máy (bỏ qua bước tải từ APKPure).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Đường dẫn file .xapk đầu ra (mặc định: font/output/<pkg>_font_signed.xapk).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Buộc tải lại XAPK bản mới nhất từ APKPure.",
    )
    parser.add_argument(
        "--charset",
        type=Path,
        default=None,
        help="File .txt chứa bảng ký tự cho SDF_Base (mặc định: toàn bộ ASCII + 134 ký tự tiếng Việt).",
    )
    parser.add_argument(
        "--no-sdf-base",
        action="store_true",
        help="Chỉ patch OTF nhúng + Builtin atlas (bỏ qua SDF_Base; dùng nếu bạn muốn font/common ưu tiên cho ASCII).",
    )
    parser.add_argument(
        "--speed-ms",
        type=float,
        default=None,
        help="Tùy chọn: kết hợp patch luôn tốc độ chạy chữ hội thoại (ms/ký tự, VD: 35).",
    )
    parser.add_argument(
        "--auto-delay",
        type=float,
        default=None,
        help="Tùy chọn (đi kèm --speed-ms): đổi thời gian chờ Auto sang câu tiếp theo (giây, gốc: 2.0).",
    )
    parser.add_argument(
        "--point-size",
        type=int,
        default=42,
        help="Kích thước lấy mẫu SDF cho SDF_Base (mặc định: 42).",
    )
    parser.add_argument(
        "--builtin-point-size",
        type=int,
        default=36,
        help="Kích thước lấy mẫu SDF cho Builtin atlas (mặc định: 36).",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=5,
        help="Độ rộng vùng biên SDF (mặc định: 5, khớp _GradientScale=6 của game).",
    )
    parser.add_argument(
        "--msdf-bin",
        default=None,
        help="Đường dẫn thủ công tới msdf-atlas-gen.",
    )
    parser.add_argument(
        "--original",
        type=Path,
        default=FONT_DIR / "assets" / "common.bak",
        help="File common.bak dùng để lấy TypeTree TMP_FontAsset (mặc định: font/assets/common.bak).",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Giữ lại thư mục tạm font/work/ sau khi đóng gói.",
    )
    parser.add_argument("--keystore", default=None, help="Đường dẫn keystore riêng (tùy chọn).")
    parser.add_argument("--ks-alias", default=None, help="Alias của keystore riêng.")
    parser.add_argument("--ks-pass", default=None, help="Mật khẩu keystore riêng.")
    parser.add_argument("--ks-key-pass", default=None, help="Mật khẩu key riêng.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    for label, p in [("DB font", args.db), ("EB font", args.eb), ("common.bak", args.original)]:
        if not p.is_file():
            sys.exit(
                f"[LỖI] Không tìm thấy {label}: {p}\n"
                "Hãy chạy `font/merge_fonts.py` trước hoặc truyền --db / --eb."
            )

    if args.speed_ms is not None and args.speed_ms < 0:
        sys.exit("[LỖI] --speed-ms không được âm.")
    if args.auto_delay is not None and args.auto_delay < 0:
        sys.exit("[LỖI] --auto-delay không được âm.")

    t_start = time.time()
    java_path = sc.check_java()
    signer_jar = sc.ensure_uber_signer()
    msdf_bin = bfb.ensure_msdf_atlas_gen(args.msdf_bin)

    # Resolve charset for SDF_Base + Builtin extra glyphs
    if args.charset:
        base_codepoints = sorted(set(ord(ch) for ch in args.charset.read_text(encoding="utf-8-sig") if ord(ch) >= 0x20))
        logger.info(f"Dùng bảng ký tự tùy chỉnh '{args.charset}': {len(base_codepoints)} ký tự")
    else:
        base_codepoints = sorted(set(ord(ch) for ch in bfb.EXTRA_DEFAULT_CHARS if ord(ch) >= 0x20))
        logger.info(f"Dùng bảng ký tự mặc định (ASCII + 134 chữ tiếng Việt): {len(base_codepoints)} ký tự")

    # Obtain XAPK (shares cache with speed_change/cache/)
    if args.input:
        xapk_src = args.input.resolve()
        if not xapk_src.is_file():
            sys.exit(f"[LỖI] Không tìm thấy file input: {xapk_src}")
        print(f"[2/5] Sử dụng XAPK chỉ định: {xapk_src}")
        pkg_name = xapk_src.stem
    else:
        xapk_src = sc.download_xapk(args.region, force_refresh=args.refresh)
        pkg_name = sc.REGIONS[args.region]["package"]

    suffix = "font"
    if args.speed_ms is not None:
        suffix += f"_{sc.format_speed_tag(args.speed_ms)}ms"
    output_xapk = (
        args.output.resolve()
        if args.output
        else OUTPUT_DIR / f"{pkg_name}_{suffix}_signed.xapk"
    )

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    extract_dir = WORK_DIR / "extracted"
    signed_dir = WORK_DIR / "signed"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("[3/5] Đang giải nén & patch Font trực tiếp vào XAPK...")
        with zipfile.ZipFile(xapk_src, "r") as zf:
            zf.extractall(extract_dir)

        patch_fonts_in_xapk(
            extract_dir=extract_dir,
            db_font=args.db.resolve(),
            eb_font=args.eb.resolve(),
            common_bak=args.original.resolve(),
            msdf_bin=msdf_bin,
            base_codepoints=base_codepoints,
            base_point_size=args.point_size,
            builtin_point_size=args.builtin_point_size,
            padding=args.padding,
            patch_sdf_base=not args.no_sdf_base,
        )

        # Optional combined speed change patch
        if args.speed_ms is not None:
            print(f"[3b/5] Kết hợp patch TalkWindow.wordInterval -> {sc.format_speed_tag(args.speed_ms)}ms...")
            tw_script_pid = sc.find_talk_window_script_pid(extract_dir)
            speed_sec = args.speed_ms / 1000.0
            total_tw = 0
            for apk_file in sorted(extract_dir.glob("*.apk")):
                total_tw += sc.patch_single_apk(
                    apk_file,
                    speed_sec,
                    args.auto_delay,
                    talk_window_script_pid=tw_script_pid,
                )
            print(f"       Tổng cộng đã patch {total_tw} prefab TalkWindow.")

        signed_map = sc.sign_apks(
            java_path=java_path,
            signer_jar=signer_jar,
            apks_dir=extract_dir,
            signed_dir=signed_dir,
            keystore=args.keystore,
            ks_alias=args.ks_alias,
            ks_pass=args.ks_pass,
            ks_key_pass=args.ks_key_pass,
        )

        sc.build_signed_xapk(extract_dir, signed_map, output_xapk)
    finally:
        if not args.keep_work and WORK_DIR.exists():
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    elapsed = time.time() - t_start
    size_mb = output_xapk.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print("HOÀN TẤT MOD FONT XAPK!")
    print(f"  DB Font   : {args.db}")
    print(f"  EB Font   : {args.eb}")
    if args.speed_ms is not None:
        print(f"  Speed Mod : {sc.format_speed_tag(args.speed_ms)}ms/ký tự")
    print(f"  File XAPK : {output_xapk}")
    print(f"  Dung lượng: {size_mb:.1f} MB | Thời gian xử lý: {elapsed:.1f}s")
    print("=" * 60)
    print(
        "\nCách cài trên Android:\n"
        "  - Cài file .xapk trên bằng SAI (Split APKs Installer) hoặc XAPK Installer.\n"
        "  - Không cần truy cập Android/data hay Shizuku/Root để mod font!\n"
        "  - Lần đầu chuyển từ bản gốc (CH Play/QooApp): cần gỡ bản gốc trước (nhớ liên kết\n"
        "    tài khoản trước khi gỡ!), trừ khi máy có Root + Core Patch.\n"
        "  - Dùng chung debug keystore với speed_change.py nên cài đè qua lại thoải mái!"
    )


if __name__ == "__main__":
    main()
