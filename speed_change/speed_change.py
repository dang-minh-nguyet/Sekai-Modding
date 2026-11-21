#!/usr/bin/env python3
"""Project Sekai dialogue text speed patcher (CLI).

Automatically downloads the latest JP/EN XAPK from APKPure (cached locally),
patches the TalkWindow prefab wordInterval (default 60ms/char) to any user-specified
value in milliseconds, zipaligns & signs all split APKs via uber-apk-signer,
and repacks a ready-to-install signed .xapk file.
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import UnityPy

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
TOOLS_DIR = BASE_DIR / "tools"
WORK_DIR = BASE_DIR / "work"
OUTPUT_DIR = BASE_DIR / "output"

REGIONS = {
    "jp": {
        "package": "com.sega.pjsekai",
        "url": "https://d.apkpure.net/b/XAPK/com.sega.pjsekai?version=latest",
        "label": "JP (com.sega.pjsekai)",
    },
    "en": {
        "package": "com.sega.ColorfulStage.en",
        "url": "https://d.apkpure.net/b/XAPK/com.sega.ColorfulStage.en?version=latest",
        "label": "EN (com.sega.ColorfulStage.en)",
    },
}

UBER_SIGNER_VERSION = "1.3.0"
UBER_SIGNER_JAR = TOOLS_DIR / f"uber-apk-signer-{UBER_SIGNER_VERSION}.jar"
UBER_SIGNER_URL = (
    f"https://github.com/patrickfav/uber-apk-signer/releases/download/"
    f"v{UBER_SIGNER_VERSION}/uber-apk-signer-{UBER_SIGNER_VERSION}.jar"
)

# TalkWindow MonoBehaviour serialized layout constants (verified on JP & EN)
TALK_WINDOW_MONO_SIZE = 204
OFFSET_WORD_INTERVAL = 0x84       # float wordInterval (default: 0.06s = 60ms)
OFFSET_AUTO_NEXT_DELAY = 0xC8     # float autoTextNextPageDelay (default: 2.0s)
DEFAULT_SPEED_MS = 60.0

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def format_speed_tag(ms: float) -> str:
    """Format speed value cleanly for filenames (e.g., 35.0 -> '35', 32.5 -> '32.5')."""
    if ms == int(ms):
        return str(int(ms))
    return f"{ms:g}"


def check_java() -> str:
    """Verify Java runtime is installed and return path to java executable."""
    java_path = shutil.which("java")
    if not java_path:
        print(
            "[LỖI] Không tìm thấy Java (JRE/JDK) trên máy.\n"
            "Java là bắt buộc để chạy uber-apk-signer ký số file APK.\n\n"
            "Cài nhanh trên Windows bằng PowerShell:\n"
            "    winget install EclipseAdoptium.Temurin.21.JRE\n\n"
            "Sau khi cài xong, mở lại PowerShell và chạy lại lệnh này.",
            file=sys.stderr,
        )
        sys.exit(1)
    return java_path


def ensure_uber_signer() -> Path:
    """Download uber-apk-signer jar if not already cached in tools/."""
    if UBER_SIGNER_JAR.exists() and UBER_SIGNER_JAR.stat().st_size > 1_000_000:
        return UBER_SIGNER_JAR

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = UBER_SIGNER_JAR.with_suffix(".jar.part")
    print(f"[1/5] Đang tải uber-apk-signer v{UBER_SIGNER_VERSION}...")
    req = urllib.request.Request(UBER_SIGNER_URL, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req) as resp, open(tmp_path, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp_path.replace(UBER_SIGNER_JAR)
    print(f"      Đã lưu: {UBER_SIGNER_JAR}")
    return UBER_SIGNER_JAR


def download_xapk(region: str, force_refresh: bool = False) -> Path:
    """Download latest XAPK from APKPure if not cached locally."""
    info = REGIONS[region]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    xapk_path = CACHE_DIR / f"{info['package']}.xapk"

    if xapk_path.exists() and not force_refresh:
        if zipfile.is_zipfile(xapk_path) and xapk_path.stat().st_size > 50 * 1024 * 1024:
            size_mb = xapk_path.stat().st_size / (1024 * 1024)
            print(f"[2/5] Dùng lại XAPK đã tải sẵn: {xapk_path.name} ({size_mb:.1f} MB)")
            print("      (Thêm --refresh nếu game vừa update phiên bản mới)")
            return xapk_path
        print("[!] File XAPK trong cache bị lỗi/chưa tải xong, sẽ tải lại...")

    url = info["url"]
    tmp_path = xapk_path.with_suffix(".xapk.part")
    print(f"[2/5] Đang tải XAPK bản {info['label']} từ APKPure...")

    with requests.get(url, headers=HTTP_HEADERS, stream=True, allow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        t0 = time.time()
        last_print = 0.0

        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_print >= 0.5 or (total and downloaded >= total):
                    elapsed = max(now - t0, 0.01)
                    speed_mbs = downloaded / (1024 * 1024) / elapsed
                    if total:
                        pct = downloaded / total * 100
                        msg = (
                            f"\r      {downloaded / (1024*1024):6.1f} / "
                            f"{total / (1024*1024):.1f} MB ({pct:5.1f}%) - {speed_mbs:5.1f} MB/s"
                        )
                    else:
                        msg = f"\r      {downloaded / (1024*1024):6.1f} MB - {speed_mbs:5.1f} MB/s"
                    print(msg, end="", flush=True)
                    last_print = now

    print()
    if not zipfile.is_zipfile(tmp_path):
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("File tải về không phải định dạng XAPK/ZIP hợp lệ.")

    tmp_path.replace(xapk_path)
    print(f"      Tải xong: {xapk_path}")
    return xapk_path


def find_talk_window_script_pid(extract_dir: Path) -> Optional[int]:
    """Locate the exact MonoScript PathID of Sekai.TalkWindow in globalgamemanagers.assets."""
    for apk_file in sorted(extract_dir.glob("*.apk")):
        with zipfile.ZipFile(apk_file, "r") as zf:
            names = zf.namelist()
            raw: Optional[bytes] = None
            if "assets/bin/Data/globalgamemanagers.assets" in names:
                raw = zf.read("assets/bin/Data/globalgamemanagers.assets")
            else:
                splits = sorted(
                    (n for n in names if n.startswith("assets/bin/Data/globalgamemanagers.assets.split")),
                    key=lambda s: int(s.rsplit("split", 1)[1]),
                )
                if splits:
                    raw = b"".join(zf.read(s) for s in splits)
            if not raw:
                continue
            env = UnityPy.load(raw)
            for obj in env.objects:
                if obj.type.name == "MonoScript":
                    try:
                        d = obj.read()
                        if getattr(d, "m_ClassName", "") == "TalkWindow" and getattr(d, "m_Namespace", "") == "Sekai":
                            return obj.path_id
                    except Exception:
                        pass
    return None


def find_talk_window_patches(
    asset_bytes: bytes,
    talk_window_script_pid: Optional[int] = None,
) -> List[Tuple[int, float, float, str]]:
    """Inspect a Unity asset file and locate all Sekai.TalkWindow MonoBehaviour speed offsets.

    Matches both scenario TalkWindow prefabs and Live2D TalkWindow prefabs
    (e.g. UIPartsLive2DTalkWindow, UIPartsLive2DAndTalkWindowViewer,
    ScreenLayerCharacterArchiveLive2DVoicePlayer).

    Returns list of (absolute_wordInterval_offset, current_wordInterval, current_autoDelay, go_name).
    """
    # Fast pre-filter before invoking UnityPy
    if talk_window_script_pid is not None:
        if struct.pack("<q", talk_window_script_pid) not in asset_bytes:
            return []
    else:
        if b"TalkWindow" not in asset_bytes:
            return []

    try:
        env = UnityPy.load(asset_bytes)
    except Exception:
        return []

    ggma_fids: set[int] = set()
    if talk_window_script_pid is not None:
        for sf in env.files.values():
            for idx, ext in enumerate(getattr(sf, "externals", []), start=1):
                if getattr(ext, "path", "").lower() == "globalgamemanagers.assets":
                    ggma_fids.add(idx)
        if not ggma_fids:
            return []

    go_names: Dict[int, str] = {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            try:
                go_names[obj.path_id] = obj.read().m_Name
            except Exception:
                pass

    results: List[Tuple[int, float, float, str]] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) != TALK_WINDOW_MONO_SIZE:
            continue
        _go_fid, go_pid = struct.unpack_from("<Iq", raw, 0)
        script_fid, script_pid = struct.unpack_from("<Iq", raw, 16)
        go_name = go_names.get(go_pid, "")

        if talk_window_script_pid is not None:
            if script_fid not in ggma_fids or script_pid != talk_window_script_pid:
                continue
        else:
            if "TalkWindow" not in go_name:
                continue

        word_interval = struct.unpack_from("<f", raw, OFFSET_WORD_INTERVAL)[0]
        auto_delay = struct.unpack_from("<f", raw, OFFSET_AUTO_NEXT_DELAY)[0]
        # Sanity-check float ranges
        if 0.0 <= word_interval <= 2.0 and 0.0 <= auto_delay <= 60.0:
            results.append((obj.byte_start + OFFSET_WORD_INTERVAL, word_interval, auto_delay, go_name or "TalkWindow"))
    return results


def patch_apk_inplace_stored(apk_path: Path, replacements: Dict[str, bytes]) -> bool:
    """Patch ZIP_STORED entries directly in-place and update Local + Central Directory CRC-32.

    Returns True on success, False if ZIP64 or non-stored entry requires full rebuild.
    """
    with zipfile.ZipFile(apk_path, "r") as zf:
        entry_meta: Dict[str, Tuple[int, int]] = {}
        for name, new_data in replacements.items():
            info = zf.getinfo(name)
            if info.compress_type != zipfile.ZIP_STORED or info.file_size != len(new_data):
                return False
            entry_meta[name] = (info.header_offset, info.file_size)

    file_size = apk_path.stat().st_size
    with open(apk_path, "r+b") as f:
        # Locate End of Central Directory (EOCD)
        search_len = min(file_size, 65557)
        f.seek(file_size - search_len)
        tail = f.read(search_len)
        eocd_rel = tail.rfind(b"PK\x05\x06")
        if eocd_rel == -1:
            return False
        cd_size, cd_offset = struct.unpack_from("<II", tail, eocd_rel + 12)
        if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            return False

        # Patch payload & Local File Header CRC-32 for each entry
        new_crcs: Dict[str, int] = {}
        for name, new_data in replacements.items():
            header_offset, usize = entry_meta[name]
            f.seek(header_offset)
            lh = f.read(30)
            if lh[:4] != b"PK\x03\x04":
                return False
            fn_len, extra_len = struct.unpack_from("<HH", lh, 26)
            data_offset = header_offset + 30 + fn_len + extra_len

            new_crc = zlib.crc32(new_data) & 0xFFFFFFFF
            new_crcs[name] = new_crc

            # Write patched payload
            f.seek(data_offset)
            f.write(new_data)

            # Update Local File Header CRC-32 (offset 14)
            f.seek(header_offset + 14)
            f.write(struct.pack("<I", new_crc))

        # Walk Central Directory and update CRC-32 for modified entries
        f.seek(cd_offset)
        cd_buf = f.read(cd_size)
        pos = 0
        updated = 0
        while pos < len(cd_buf) and cd_buf[pos : pos + 4] == b"PK\x01\x02":
            fn_len, extra_len, comment_len = struct.unpack_from("<HHH", cd_buf, pos + 28)
            fn = cd_buf[pos + 46 : pos + 46 + fn_len].decode("utf-8", errors="ignore")
            if fn in new_crcs:
                f.seek(cd_offset + pos + 16)
                f.write(struct.pack("<I", new_crcs[fn]))
                updated += 1
            pos += 46 + fn_len + extra_len + comment_len

        if updated != len(new_crcs):
            return False

    return True


def patch_apk_rebuild(apk_path: Path, replacements: Dict[str, bytes]) -> None:
    """Rebuild an APK while preserving original compression types for all entries."""
    tmp_apk = apk_path.with_suffix(".apk.tmp")
    with zipfile.ZipFile(apk_path, "r") as zin, zipfile.ZipFile(tmp_apk, "w") as zout:
        for item in zin.infolist():
            if item.filename in replacements:
                data = replacements[item.filename]
            else:
                data = zin.read(item.filename)
            new_info = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            new_info.compress_type = item.compress_type
            new_info.external_attr = item.external_attr
            zout.writestr(new_info, data)
    tmp_apk.replace(apk_path)


def patch_single_apk(
    apk_path: Path,
    speed_sec: float,
    auto_delay_sec: Optional[float] = None,
    talk_window_script_pid: Optional[int] = None,
) -> int:
    """Scan an APK for TalkWindow assets and patch wordInterval (and optional autoDelay).

    Returns number of TalkWindow MonoBehaviour instances patched.
    """
    replacements: Dict[str, bytes] = {}
    patched_count = 0

    with zipfile.ZipFile(apk_path, "r") as zf:
        candidates = [n for n in zf.namelist() if n.startswith("assets/bin/Data/")]
        for entry_name in candidates:
            raw = zf.read(entry_name)
            hits = find_talk_window_patches(raw, talk_window_script_pid=talk_window_script_pid)
            if not hits:
                continue

            buf = bytearray(raw)
            for abs_wi_off, old_wi, old_delay, go_name in hits:
                buf[abs_wi_off : abs_wi_off + 4] = struct.pack("<f", speed_sec)
                delay_note = ""
                if auto_delay_sec is not None:
                    abs_delay_off = abs_wi_off - OFFSET_WORD_INTERVAL + OFFSET_AUTO_NEXT_DELAY
                    buf[abs_delay_off : abs_delay_off + 4] = struct.pack("<f", auto_delay_sec)
                    delay_note = f", autoDelay: {old_delay:.2f}s -> {auto_delay_sec:.2f}s"
                print(
                    f"      Patch {apk_path.name} :: {Path(entry_name).name} ({go_name}) "
                    f"@ {hex(abs_wi_off)}: {old_wi*1000:.1f}ms -> {speed_sec*1000:.1f}ms{delay_note}"
                )
                patched_count += 1
            replacements[entry_name] = bytes(buf)

    if replacements:
        if not patch_apk_inplace_stored(apk_path, replacements):
            patch_apk_rebuild(apk_path, replacements)

    return patched_count


def sign_apks(
    java_path: str,
    signer_jar: Path,
    apks_dir: Path,
    signed_dir: Path,
    keystore: Optional[str] = None,
    ks_alias: Optional[str] = None,
    ks_pass: Optional[str] = None,
    ks_key_pass: Optional[str] = None,
) -> Dict[str, Path]:
    """Zipalign and sign all APKs in apks_dir with the same key via uber-apk-signer."""
    signed_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        java_path,
        "-jar",
        str(signer_jar),
        "--apks",
        str(apks_dir),
        "--out",
        str(signed_dir),
        "--allowResign",
    ]
    if keystore:
        cmd.extend(["--ks", keystore])
        if ks_alias:
            cmd.extend(["--ksAlias", ks_alias])
        if ks_pass:
            cmd.extend(["--ksPass", ks_pass])
        if ks_key_pass:
            cmd.extend(["--ksKeyPass", ks_key_pass])

    print("[4/5] Đang zipalign & ký số toàn bộ split APK bằng uber-apk-signer...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        raise RuntimeError(f"uber-apk-signer thất bại (mã lỗi {res.returncode}).")

    # Map original APK filename -> signed APK path
    orig_apks = [p for p in apks_dir.iterdir() if p.suffix.lower() == ".apk"]
    signed_apks = [p for p in signed_dir.iterdir() if p.suffix.lower() == ".apk"]
    mapping: Dict[str, Path] = {}

    for orig in orig_apks:
        prefix = f"{orig.stem}-aligned-"
        matches = [s for s in signed_apks if s.name.startswith(prefix)]
        if not matches:
            matches = [s for s in signed_apks if s.stem.startswith(orig.stem)]
        if not matches:
            raise RuntimeError(f"Không tìm thấy file đã ký tương ứng với {orig.name}")
        mapping[orig.name] = matches[0]

    print(f"      Đã ký & xác thực xong {len(mapping)} APK (v1/v2/v3 + zipalign).")
    return mapping


def build_signed_xapk(
    extract_dir: Path,
    signed_map: Dict[str, Path],
    output_xapk: Path,
) -> None:
    """Repackage manifest, non-APK files, and signed APKs into a single .xapk."""
    output_xapk.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_xapk.with_suffix(".xapk.part")

    print(f"[5/5] Đang đóng gói XAPK -> {output_xapk.name}...")
    with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_STORED) as zf:
        for root, _dirs, files in os.walk(extract_dir):
            for fn in sorted(files):
                full_path = Path(root) / fn
                rel_path = full_path.relative_to(extract_dir).as_posix()
                if rel_path in signed_map:
                    zf.write(signed_map[rel_path], rel_path)
                else:
                    zf.write(full_path, rel_path)

    tmp_out.replace(output_xapk)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Đổi tốc độ chạy chữ hội thoại (TalkWindow.wordInterval) cho Project Sekai.\n"
            "Mặc định gốc của game là 60ms/ký tự (0.06s). Số càng nhỏ chữ chạy càng nhanh."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ví dụ:\n"
            "  uv run speed_change/speed_change.py 35              # JP, 35ms/ký tự\n"
            "  uv run speed_change/speed_change.py 30 --region en  # EN, 30ms/ký tự\n"
            "  uv run speed_change/speed_change.py 40 --refresh    # Tải lại XAPK mới nhất\n"
        ),
    )
    parser.add_argument(
        "speed_ms",
        type=float,
        help="Tốc độ chạy chữ mong muốn tính bằng mili-giây/ký tự (gốc: 60, gợi ý: 30-45).",
    )
    parser.add_argument(
        "--region",
        choices=list(REGIONS.keys()),
        default="jp",
        help="Server game: jp (mặc định) hoặc en.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Đường dẫn tới file .xapk có sẵn trên máy (bỏ qua bước tự tải).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Đường dẫn file .xapk đầu ra (mặc định: speed_change/output/<pkg>_<ms>ms_signed.xapk).",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Buộc tải lại XAPK bản mới nhất từ APKPure thay vì dùng cache.",
    )
    parser.add_argument(
        "--auto-delay",
        type=float,
        default=None,
        help="Tùy chọn: đổi thêm thời gian chờ sang câu tiếp theo ở chế độ Auto (giây, gốc: 2.0).",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Giữ lại thư mục tạm speed_change/work/ sau khi đóng gói.",
    )
    parser.add_argument("--keystore", default=None, help="Đường dẫn keystore riêng (tùy chọn).")
    parser.add_argument("--ks-alias", default=None, help="Alias của keystore riêng.")
    parser.add_argument("--ks-pass", default=None, help="Mật khẩu keystore riêng.")
    parser.add_argument("--ks-key-pass", default=None, help="Mật khẩu key riêng.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.speed_ms < 0:
        print("[LỖI] Tốc độ (speed_ms) không được là số âm.", file=sys.stderr)
        sys.exit(1)
    if args.speed_ms == 0:
        print("[CẢNH BÁO] speed_ms = 0 có thể hiển thị chữ tức thì hoặc gây khựng lip-sync.")
    elif args.speed_ms > 200:
        print(f"[CẢNH BÁO] {args.speed_ms:g}ms khá chậm so với mặc định gốc (60ms).")

    if args.auto_delay is not None and args.auto_delay < 0:
        print("[LỖI] --auto-delay không được âm.", file=sys.stderr)
        sys.exit(1)

    t_start = time.time()
    java_path = check_java()
    signer_jar = ensure_uber_signer()

    # Step 2: Obtain XAPK
    if args.input:
        xapk_src = args.input.resolve()
        if not xapk_src.exists():
            print(f"[LỖI] Không tìm thấy file input: {xapk_src}", file=sys.stderr)
            sys.exit(1)
        print(f"[2/5] Sử dụng XAPK chỉ định: {xapk_src}")
        pkg_name = xapk_src.stem
    else:
        xapk_src = download_xapk(args.region, force_refresh=args.refresh)
        pkg_name = REGIONS[args.region]["package"]

    speed_tag = format_speed_tag(args.speed_ms)
    output_xapk = (
        args.output.resolve()
        if args.output
        else OUTPUT_DIR / f"{pkg_name}_{speed_tag}ms_signed.xapk"
    )

    # Prepare clean work directory
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    extract_dir = WORK_DIR / "extracted"
    signed_dir = WORK_DIR / "signed"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 3: Extract XAPK & patch TalkWindow prefabs
        print(f"[3/5] Đang giải nén & patch TalkWindow.wordInterval -> {speed_tag}ms ({args.speed_ms / 1000:.4f}s)...")
        with zipfile.ZipFile(xapk_src, "r") as zf:
            zf.extractall(extract_dir)

        tw_script_pid = find_talk_window_script_pid(extract_dir)
        speed_sec = args.speed_ms / 1000.0
        total_patched = 0
        for apk_file in sorted(extract_dir.glob("*.apk")):
            total_patched += patch_single_apk(
                apk_file,
                speed_sec,
                args.auto_delay,
                talk_window_script_pid=tw_script_pid,
            )

        if total_patched == 0:
            raise RuntimeError(
                "Không tìm thấy TalkWindow prefab nào trong XAPK! "
                "Có thể cấu trúc asset của game đã thay đổi."
            )
        print(f"      Tổng cộng đã patch {total_patched} prefab TalkWindow.")

        # Step 4: Zipalign & sign all split APKs
        signed_map = sign_apks(
            java_path=java_path,
            signer_jar=signer_jar,
            apks_dir=extract_dir,
            signed_dir=signed_dir,
            keystore=args.keystore,
            ks_alias=args.ks_alias,
            ks_pass=args.ks_pass,
            ks_key_pass=args.ks_key_pass,
        )

        # Step 5: Repack XAPK
        build_signed_xapk(extract_dir, signed_map, output_xapk)
    finally:
        if not args.keep_work and WORK_DIR.exists():
            shutil.rmtree(WORK_DIR, ignore_errors=True)

    elapsed = time.time() - t_start
    size_mb = output_xapk.stat().st_size / (1024 * 1024)
    ratio = (DEFAULT_SPEED_MS / args.speed_ms) if args.speed_ms > 0 else float("inf")
    ratio_str = f"nhanh gấp {ratio:.2f}x" if ratio >= 1 else f"chậm hơn {1/ratio:.2f}x"

    print("\n" + "=" * 60)
    print("HOÀN TẤT!")
    print(f"  Tốc độ cũ : {DEFAULT_SPEED_MS:g}ms/ký tự (mặc định gốc)")
    print(f"  Tốc độ mới: {speed_tag}ms/ký tự ({ratio_str})")
    print(f"  File XAPK : {output_xapk}")
    print(f"  Dung lượng: {size_mb:.1f} MB | Thời gian xử lý: {elapsed:.1f}s")
    print("=" * 60)
    print(
        "\nCách cài trên Android:\n"
        "  - Chuyển file .xapk trên sang điện thoại và cài bằng SAI (Split APKs Installer)\n"
        "    hoặc XAPK Installer.\n"
        "  - Lần đầu chuyển từ bản gốc (CH Play/QooApp): cần gỡ bản gốc trước (nhớ liên kết\n"
        "    tài khoản trước khi gỡ!), trừ khi máy có Root + Core Patch.\n"
        "  - Những lần đổi tốc độ sau trên cùng máy tính này: cài đè trực tiếp không cần gỡ!"
    )


if __name__ == "__main__":
    main()
