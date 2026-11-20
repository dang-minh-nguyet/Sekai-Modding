"""
story_mod.py
------------
All-in-one Project Sekai story modding tool (Main Story & Event Story)
for JP and EN — powered by `sssekai` and `UnityPy` (no Unity Editor required).

Workflow:
  1. Choose region (JP / EN) and story (Main Story unit or Event Story by ID/name)
  2. Choose chapter(s) to extract
  3. Automatically fetches the original encrypted AssetBundle via `sssekai`
     and extracts all translatable text (TalkData + Telop / PlaceInfo /
     FullScreenText / SimpleSelectable) into a clean, editable `.txt` file
  4. Translator edits text in the `.txt` file
  5. Patch translated `.txt` file(s) back into the bundle, pack LZ4, re-encrypt,
     and output to `story/output/<region>/<cacheDir>/<cacheFile>` with Android
     installation instructions.

Usage:
  Interactive menu:
    uv run story/story_mod.py

  CLI shortcuts:
    uv run story/story_mod.py list [--region jp|en] [--type main|event] [--search KEYWORD]
    uv run story/story_mod.py extract [--region jp|en] --main leo --chapter 1
    uv run story/story_mod.py extract [--region jp|en] --event 210 --chapter 1
    uv run story/story_mod.py patch <file.txt or folder>
"""

import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import sys
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import UnityPy
from UnityPy.enums import ClassIDType
from sssekai.abcache import AbCache, AbCacheConfig
from sssekai.crypto.AssetBundle import SEKAI_AB_MAGIC, decrypt_header_inplace
from sssekai.unity import sssekai_get_unity_version

# Suppress noisy UnityPy fallback version warnings (bundles have stripped version headers)
warnings.filterwarnings("ignore", message="No valid Unity version found.*")
UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()

# Ensure UTF-8 I/O on Windows terminals (for Japanese & Vietnamese text)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# =============================================================================
# Constants & Region Config
# =============================================================================

STORY_DIR = Path(__file__).resolve().parent
CACHE_DIR = STORY_DIR / "cache"
WORK_DIR = STORY_DIR / "work"
OUTPUT_DIR = STORY_DIR / "output"

MASTER_DB_REPOS = {
    "jp": "https://raw.githubusercontent.com/Sekai-World/sekai-master-db-diff/main",
    "en": "https://raw.githubusercontent.com/Sekai-World/sekai-master-db-en-diff/main",
}

ANDROID_PACKAGES = {
    "jp": "com.sega.pjsekai",
    "en": "com.sega.ColorfulStage.en",
}

# Main Story groups (maps internal unit/episodeGroup IDs to friendly display names)
@dataclass(frozen=True)
class MainStoryGroup:
    key: str
    display_name: str
    unit: str
    episode_group_id: Optional[int]  # None = all episodes in chapter; int = filter piapro sub-group
    aliases: Tuple[str, ...]


MAIN_STORY_GROUPS: List[MainStoryGroup] = [
    MainStoryGroup("leo", "Leo/need", "light_sound", None, ("leo", "leoneed", "l/n", "ln", "light_sound")),
    MainStoryGroup("mmj", "MORE MORE JUMP!", "idol", None, ("mmj", "idol")),
    MainStoryGroup("vbs", "Vivid BAD SQUAD", "street", None, ("vbs", "street")),
    MainStoryGroup("wxs", "Wonderlands×Showtime", "theme_park", None, ("wxs", "wds", "theme_park")),
    MainStoryGroup("n25", "25-ji, Nightcord de.", "school_refusal", None, ("n25", "niigo", "25ji", "school_refusal")),
    MainStoryGroup("vs-leo", "VIRTUAL SINGER — Leo/need (School SEKAI)", "piapro", 1, ("vs-leo", "vsleo")),
    MainStoryGroup("vs-mmj", "VIRTUAL SINGER — MORE MORE JUMP! (Stage SEKAI)", "piapro", 2, ("vs-mmj", "vsmmj")),
    MainStoryGroup("vs-vbs", "VIRTUAL SINGER — Vivid BAD SQUAD (Street SEKAI)", "piapro", 3, ("vs-vbs", "vsstreet")),
    MainStoryGroup("vs-wxs", "VIRTUAL SINGER — Wonderlands×Showtime (Wonderland SEKAI)", "piapro", 4, ("vs-wxs", "vswonder")),
    MainStoryGroup("vs-n25", "VIRTUAL SINGER — 25-ji, Nightcord de. (Empty SEKAI)", "piapro", 5, ("vs-n25", "vsnightcode")),
]

# All SpecialEffectType values that carry player-visible text in `StringVal`
TEXT_EFFECT_TYPES: Dict[int, str] = {
    8: "TELOP",        # Telop banner (location / time transition)
    18: "PLACE",       # PlaceInfo header
    23: "CHOICE",      # SimpleSelectable choice text
    24: "FULLSCREEN",  # FullScreenText white narration (used in main stories)
}

EFFECT_TAG_TO_TYPE: Dict[str, int] = {v: k for k, v in TEXT_EFFECT_TYPES.items()}
ALL_BLOCK_TAGS = ("TALK",) + tuple(TEXT_EFFECT_TYPES.values())
BLOCK_HEADER_RE = re.compile(r"^\[(" + "|".join(ALL_BLOCK_TAGS) + r") #(\d+)\]\s*$")


# =============================================================================
# Crypto & Cache Path Helpers
# =============================================================================

def bundle_cache_path(bundle_name: str) -> Tuple[str, str]:
    """Compute Project Sekai's (cacheDirectoryName, cacheFileName) from bundleName."""
    parent = posixpath.dirname(bundle_name)
    cache_dir = hashlib.md5(parent.encode("utf-8")).hexdigest()[:4]
    cache_file = hashlib.md5(bundle_name.encode("utf-8")).hexdigest()
    return cache_dir, cache_file


def decrypt_bundle_bytes(data: bytes) -> bytes:
    """Decrypt a Project Sekai encrypted AssetBundle (or pass through if already raw)."""
    if data[:4] == SEKAI_AB_MAGIC:
        hdr = bytearray(data[4:132])
        decrypt_header_inplace(hdr)
        return bytes(hdr) + data[132:]
    return data


def encrypt_bundle_bytes(raw: bytes) -> bytes:
    """Encrypt a raw Unity AssetBundle with the 4-byte magic + 128-byte XOR'd header."""
    if raw[:4] == SEKAI_AB_MAGIC:
        return raw
    hdr = bytearray(raw[:128])
    decrypt_header_inplace(hdr)
    return SEKAI_AB_MAGIC + bytes(hdr) + raw[128:]


# =============================================================================
# Metadata & sssekai Downloader
# =============================================================================

def fetch_json_url(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Sekai-Modding"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_master_json(region: str, filename: str, refresh: bool = False) -> object:
    meta_dir = CACHE_DIR / f"meta_{region}"
    meta_dir.mkdir(parents=True, exist_ok=True)
    local_path = meta_dir / filename

    if not refresh and local_path.is_file():
        return json.loads(local_path.read_text(encoding="utf-8"))

    url = f"{MASTER_DB_REPOS[region]}/{filename}"
    print(f"  [Fetch] {filename} ({region.upper()})...")
    data = fetch_json_url(url)
    local_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def refresh_metadata(region: str) -> None:
    for fname in ("versions.json", "unitStories.json", "eventStories.json", "events.json"):
        load_master_json(region, fname, refresh=True)
    print(f"[OK] Đã cập nhật metadata mới nhất cho bản {region.upper()}.")


_AB_CLIENT_CACHE: Dict[str, AbCache] = {}


def get_ab_client(region: str, refresh_version: bool = False) -> AbCache:
    if not refresh_version and region in _AB_CLIENT_CACHE:
        return _AB_CLIENT_CACHE[region]

    ver = load_master_json(region, "versions.json", refresh=refresh_version)
    cfg = AbCacheConfig(
        app_region=region,
        app_version=ver["appVersion"],
        app_platform="android",
        app_hash=ver["appHash"],
        asset_version=ver["assetVersion"],
        asset_hash=ver["assetHash"],
    )
    client = AbCache(cfg)
    if region == "jp":
        client.update_signatures()
    client._update_gameversion_data()
    _AB_CLIENT_CACHE[region] = client
    return client


def ensure_bundle_downloaded(region: str, bundle_name: str, force: bool = False) -> Path:
    """Download and cache the original encrypted AssetBundle via sssekai."""
    cache_dir, cache_file = bundle_cache_path(bundle_name)
    local_path = CACHE_DIR / "bundles" / region / cache_dir / cache_file
    if not force and local_path.is_file() and local_path.stat().st_size > 132:
        print(f"  [Cache] Dùng bundle gốc đã tải: {local_path.relative_to(STORY_DIR.parent)}")
        return local_path

    print(f"  [Download] Đang tải bundle `{bundle_name}` ({region.upper()}) qua sssekai...")
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            client = get_ab_client(region, refresh_version=(attempt == 1))
            url = client.SEKAI_AB_ENDPOINT + client.SEKAI_AB_BASE_PATH + bundle_name
            resp = client.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.content
            if len(data) <= 132:
                raise RuntimeError(f"Bundle trả về quá nhỏ ({len(data)} bytes)")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(data)
            print(f"  [OK] Đã tải {len(data):,} bytes -> {local_path.relative_to(STORY_DIR.parent)}")
            return local_path
        except Exception as e:
            last_err = e
            if attempt == 0:
                print(f"  [Retry] Lỗi tải ({e}), đang làm mới versions.json và thử lại...")
                _AB_CLIENT_CACHE.pop(region, None)
    raise RuntimeError(f"Không tải được bundle `{bundle_name}` ({region.upper()}): {last_err}")


# =============================================================================
# Story Catalog (Main Story + Event Story)
# =============================================================================

@dataclass
class EpisodeEntry:
    display_no: int
    label: str
    title: str
    scenario_id: str


@dataclass
class StoryEntry:
    kind: str           # "main" | "event"
    region: str
    story_key: str      # e.g. "main_leo" or "event_210_event_addcolor_2026"
    display_title: str
    bundle_name: str
    episodes: List[EpisodeEntry]


def get_main_story(region: str, group: MainStoryGroup) -> StoryEntry:
    unit_stories = load_master_json(region, "unitStories.json")
    unit_obj = next((u for u in unit_stories if u.get("unit") == group.unit), None)
    if not unit_obj:
        raise ValueError(f"Không tìm thấy unit '{group.unit}' trong unitStories.json ({region})")

    chapter = unit_obj["chapters"][0]
    bundle_name = f"scenario/unitstory/{chapter['assetbundleName']}"

    raw_eps = chapter.get("episodes", [])
    if group.episode_group_id is not None:
        raw_eps = [ep for ep in raw_eps if ep.get("unitStoryEpisodeGroupId") == group.episode_group_id]

    episodes = [
        EpisodeEntry(
            display_no=idx,
            label=ep.get("episodeNoLabel") or f"Ep {ep.get('episodeNo', idx)}",
            title=ep.get("title", ""),
            scenario_id=ep["scenarioId"],
        )
        for idx, ep in enumerate(raw_eps, start=1)
    ]

    return StoryEntry(
        kind="main",
        region=region,
        story_key="main_virtual_singer" if group.unit == "piapro" else f"main_{group.key}",
        display_title=f"Main Story — {group.display_name}",
        bundle_name=bundle_name,
        episodes=episodes,
    )


def list_event_stories(region: str) -> List[Tuple[int, str, str, dict]]:
    """Return list of (event_id, event_name, assetbundle_name, raw_event_story) sorted by event_id."""
    event_stories = load_master_json(region, "eventStories.json")
    events = load_master_json(region, "events.json")
    name_by_id = {e["id"]: e.get("name", "") for e in events}

    items = []
    for es in event_stories:
        ev_id = int(es["eventId"])
        ab = es["assetbundleName"]
        name = name_by_id.get(ev_id, ab)
        items.append((ev_id, name, ab, es))
    items.sort(key=lambda x: x[0])
    return items


def get_event_story(region: str, event_id: int) -> StoryEntry:
    items = list_event_stories(region)
    match = next((it for it in items if it[0] == event_id), None)
    if not match:
        raise ValueError(f"Không tìm thấy Event Story ID={event_id} trên bản {region.upper()}.")
    ev_id, ev_name, ab, es = match
    bundle_name = f"event_story/{ab}/scenario"

    episodes = [
        EpisodeEntry(
            display_no=int(ep.get("episodeNo", idx)),
            label=f"Ch.{ep.get('episodeNo', idx)}",
            title=ep.get("title", ""),
            scenario_id=ep["scenarioId"],
        )
        for idx, ep in enumerate(es.get("eventStoryEpisodes", []), start=1)
    ]

    return StoryEntry(
        kind="event",
        region=region,
        story_key=f"event_{ev_id:03d}_{ab}",
        display_title=f"Event #{ev_id}: {ev_name}",
        bundle_name=bundle_name,
        episodes=episodes,
    )


# =============================================================================
# Scenario Extraction & Editable Text Format
# =============================================================================

def load_bundle_scenarios(bundle_path: Path) -> Tuple[UnityPy.Environment, Dict[str, object]]:
    """Load an encrypted/raw bundle and return (env, {scenario_id: MonoBehaviour_obj})."""
    raw = decrypt_bundle_bytes(bundle_path.read_bytes())
    env = UnityPy.load(io.BytesIO(raw))
    scenarios: Dict[str, object] = {}
    for obj in env.objects:
        if obj.type == ClassIDType.MonoBehaviour:
            tt = obj.read_typetree()
            name = tt.get("m_Name") or tt.get("ScenarioId")
            if name and "Snippets" in tt and "TalkData" in tt:
                scenarios[name] = obj
                sid = tt.get("ScenarioId")
                if sid and sid not in scenarios:
                    scenarios[sid] = obj
    return env, scenarios


def extract_scenario_blocks(tt: dict) -> List[dict]:
    """Walk Snippets in playback order and collect all translatable Talk & SpecialEffect blocks."""
    talk_data = tt.get("TalkData", [])
    effect_data = tt.get("SpecialEffectData", [])
    snippets = tt.get("Snippets", [])

    blocks: List[dict] = []
    seen_talk = set()
    seen_effect = set()

    for snippet in snippets:
        action = snippet.get("Action")
        ref = snippet.get("ReferenceIndex", -1)

        if action == 1 and 0 <= ref < len(talk_data):
            if ref in seen_talk:
                continue
            seen_talk.add(ref)
            entry = talk_data[ref]
            blocks.append({
                "tag": "TALK",
                "ref": ref,
                "speaker": entry.get("WindowDisplayName", ""),
                "text": entry.get("Body", ""),
            })
        elif action == 6 and 0 <= ref < len(effect_data):
            if ref in seen_effect:
                continue
            effect = effect_data[ref]
            etype = effect.get("EffectType")
            if etype in TEXT_EFFECT_TYPES:
                seen_effect.add(ref)
                blocks.append({
                    "tag": TEXT_EFFECT_TYPES[etype],
                    "ref": ref,
                    "effect_type": etype,
                    "text": effect.get("StringVal", ""),
                })

    # Safety net: catch any TalkData or text SpecialEffectData not referenced in Snippets
    for ref, entry in enumerate(talk_data):
        if ref not in seen_talk and (entry.get("Body") or entry.get("WindowDisplayName")):
            blocks.append({
                "tag": "TALK",
                "ref": ref,
                "speaker": entry.get("WindowDisplayName", ""),
                "text": entry.get("Body", ""),
            })
    for ref, effect in enumerate(effect_data):
        etype = effect.get("EffectType")
        if ref not in seen_effect and etype in TEXT_EFFECT_TYPES and effect.get("StringVal"):
            blocks.append({
                "tag": TEXT_EFFECT_TYPES[etype],
                "ref": ref,
                "effect_type": etype,
                "text": effect.get("StringVal", ""),
            })

    return blocks


def format_editable_script(
    story: StoryEntry,
    episode: EpisodeEntry,
    blocks: List[dict],
) -> str:
    cache_dir, cache_file = bundle_cache_path(story.bundle_name)
    lines = [
        "# ============================================================================",
        "# Sekai-Modding Story Script",
        f"# Region   : {story.region}",
        f"# Story    : {story.display_title}",
        f"# Bundle   : {story.bundle_name}",
        f"# Scenario : {episode.scenario_id}",
        f"# Episode  : {episode.label} — {episode.title}",
        f"# CacheDir : {cache_dir}",
        f"# CacheFile: {cache_file}",
        "# ----------------------------------------------------------------------------",
        "# HƯỚNG DẪN DỊCH:",
        "# - Chỉ sửa phần nội dung bên dưới các thẻ [TALK #...], [TELOP #...],",
        "#   [PLACE #...], [FULLSCREEN #...], [CHOICE #...].",
        "# - KHÔNG sửa hoặc xóa các dòng bắt đầu bằng `#` hay `[...]`.",
        "# - Với [TALK #...]: dòng `Speaker:` là tên nhân vật (sửa hoặc giữ nguyên),",
        "#   các dòng phía dưới là lời thoại (được phép xuống dòng tự do).",
        "# ============================================================================",
        "",
    ]

    for blk in blocks:
        lines.append(f"[{blk['tag']} #{blk['ref']}]")
        if blk["tag"] == "TALK":
            speaker = blk.get("speaker", "")
            lines.append(f"Speaker: {speaker}" if speaker else "Speaker:")
        lines.append(blk.get("text", ""))
        lines.append("")

    return "\n".join(lines)


def parse_editable_script(txt_path: Path) -> Tuple[Dict[str, str], List[dict]]:
    """Parse an edited `.txt` story script back into (metadata, blocks)."""
    content = txt_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")

    meta: Dict[str, str] = {}
    blocks: List[dict] = []
    cur_tag: Optional[str] = None
    cur_ref: Optional[int] = None
    cur_lines: List[str] = []
    cur_start_line = 0

    def flush_block():
        nonlocal cur_tag, cur_ref, cur_lines
        if cur_tag is None:
            return
        # Trim trailing separator blank line(s) added between blocks
        while cur_lines and cur_lines[-1] == "":
            cur_lines.pop()

        if cur_tag == "TALK":
            if not cur_lines or not cur_lines[0].startswith("Speaker:"):
                raise ValueError(
                    f"{txt_path.name}:{cur_start_line}: Thiếu dòng `Speaker:` ngay sau [{cur_tag} #{cur_ref}]"
                )
            speaker = cur_lines[0][len("Speaker:"):].strip()
            body = "\n".join(cur_lines[1:])
            blocks.append({"tag": "TALK", "ref": cur_ref, "speaker": speaker, "text": body})
        else:
            body = "\n".join(cur_lines)
            blocks.append({"tag": cur_tag, "ref": cur_ref, "text": body})

        cur_tag = None
        cur_ref = None
        cur_lines = []

    for lineno, line in enumerate(lines, start=1):
        # Header metadata lines (only before first block)
        if cur_tag is None and line.startswith("#"):
            m_meta = re.match(r"^#\s*([A-Za-z]+)\s*:\s*(.*)$", line)
            if m_meta:
                meta[m_meta.group(1)] = m_meta.group(2).strip()
            continue

        m_hdr = BLOCK_HEADER_RE.match(line)
        if m_hdr:
            flush_block()
            cur_tag = m_hdr.group(1)
            cur_ref = int(m_hdr.group(2))
            cur_start_line = lineno
            cur_lines = []
            continue

        if cur_tag is not None:
            cur_lines.append(line)

    flush_block()

    for required in ("Region", "Bundle", "Scenario"):
        if required not in meta:
            raise ValueError(f"{txt_path.name}: Thiếu metadata `# {required}: ...` ở đầu file.")

    return meta, blocks


# =============================================================================
# Core Actions: Extract & Patch
# =============================================================================

def extract_episodes(
    story: StoryEntry,
    episodes: Sequence[EpisodeEntry],
    *,
    force_download: bool = False,
    overwrite: bool = False,
) -> List[Path]:
    bundle_path = ensure_bundle_downloaded(story.region, story.bundle_name, force=force_download)
    _, scenarios = load_bundle_scenarios(bundle_path)

    out_dir = WORK_DIR / story.region / story.story_key
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for ep in episodes:
        obj = scenarios.get(ep.scenario_id)
        if obj is None:
            print(f"  [WARN] Không tìm thấy scenario `{ep.scenario_id}` trong bundle (bỏ qua).")
            continue

        tt = obj.read_typetree()
        blocks = extract_scenario_blocks(tt)
        script_text = format_editable_script(story, ep, blocks)

        out_file = out_dir / f"{ep.display_no:02d}_{ep.scenario_id}.txt"
        if out_file.exists() and not overwrite:
            # Backup or warn rather than silently destroying user's translation
            backup = out_file.with_suffix(".orig.txt")
            print(f"  [SKIP] Đã tồn tại {out_file.relative_to(STORY_DIR.parent)} (dùng --overwrite để ghi đè).")
            if not backup.exists():
                backup.write_text(script_text, encoding="utf-8")
            written.append(out_file)
            continue

        out_file.write_text(script_text, encoding="utf-8")
        talk_cnt = sum(1 for b in blocks if b["tag"] == "TALK")
        fx_cnt = len(blocks) - talk_cnt
        print(
            f"  [OK] {out_file.relative_to(STORY_DIR.parent)} "
            f"({talk_cnt} thoại, {fx_cnt} effect text)"
        )
        written.append(out_file)

    return written


def patch_from_paths(target_path: Path, output_override: Optional[Path] = None) -> Path:
    """Patch one `.txt` file or all `.txt` files in a folder into an encrypted AssetBundle."""
    if target_path.is_dir():
        txt_files = sorted(
            p for p in target_path.glob("*.txt") if not p.name.endswith(".orig.txt")
        )
        if not txt_files:
            raise FileNotFoundError(f"Không tìm thấy file .txt nào trong thư mục: {target_path}")
    elif target_path.is_file():
        txt_files = [target_path]
    else:
        raise FileNotFoundError(f"Không tìm thấy đường dẫn: {target_path}")

    parsed = []
    for p in txt_files:
        meta, blocks = parse_editable_script(p)
        parsed.append((p, meta, blocks))

    # Ensure all files target the same region + bundle
    region = parsed[0][1]["Region"].lower()
    bundle_name = parsed[0][1]["Bundle"]
    for p, meta, _ in parsed[1:]:
        if meta["Region"].lower() != region or meta["Bundle"] != bundle_name:
            raise ValueError(
                f"File {p.name} thuộc bundle `{meta['Bundle']}` ({meta['Region']}), "
                f"khác với `{bundle_name}` ({region}). Hãy patch từng bundle riêng!"
            )

    bundle_path = ensure_bundle_downloaded(region, bundle_name)
    env, scenarios = load_bundle_scenarios(bundle_path)

    total_changed = 0
    for p, meta, blocks in parsed:
        scenario_id = meta["Scenario"]
        obj = scenarios.get(scenario_id)
        if obj is None:
            raise RuntimeError(f"Không tìm thấy `{scenario_id}` trong bundle `{bundle_name}`")

        tt = obj.read_typetree()
        talk_data = tt.get("TalkData", [])
        effect_data = tt.get("SpecialEffectData", [])
        changed = 0

        for blk in blocks:
            ref = blk["ref"]
            if blk["tag"] == "TALK":
                if not (0 <= ref < len(talk_data)):
                    raise IndexError(f"{p.name}: [TALK #{ref}] vượt quá số câu thoại ({len(talk_data)})")
                entry = talk_data[ref]
                if entry.get("WindowDisplayName", "") != blk["speaker"]:
                    entry["WindowDisplayName"] = blk["speaker"]
                    changed += 1
                if entry.get("Body", "") != blk["text"]:
                    entry["Body"] = blk["text"]
                    changed += 1
            else:
                if not (0 <= ref < len(effect_data)):
                    raise IndexError(
                        f"{p.name}: [{blk['tag']} #{ref}] vượt quá SpecialEffectData ({len(effect_data)})"
                    )
                effect = effect_data[ref]
                expected_type = EFFECT_TAG_TO_TYPE[blk["tag"]]
                if effect.get("EffectType") != expected_type:
                    raise ValueError(
                        f"{p.name}: [{blk['tag']} #{ref}] lệch EffectType "
                        f"(file={expected_type}, bundle={effect.get('EffectType')})"
                    )
                if effect.get("StringVal", "") != blk["text"]:
                    effect["StringVal"] = blk["text"]
                    changed += 1

        obj.save_typetree(tt)
        total_changed += changed
        print(f"  [Patch] {p.name} ({scenario_id}): {changed} mục đã thay đổi")

    print("  [Pack] Đang nén LZ4 và mã hóa header...")
    packed = env.file.save(packer="lz4")
    encrypted = encrypt_bundle_bytes(packed)

    cache_dir, cache_file = bundle_cache_path(bundle_name)
    out_path = output_override or (OUTPUT_DIR / region / cache_dir / cache_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(encrypted)

    pkg = ANDROID_PACKAGES.get(region, "<package>")
    print()
    print("=" * 72)
    print(f"  [DONE] Đã đóng gói & mã hóa thành công! ({len(encrypted):,} bytes, {total_changed} mục sửa)")
    print(f"  File kết quả : {out_path}")
    print("-" * 72)
    print("  HƯỚNG DẪN CHÉP VÀO ANDROID:")
    print(f"  1. Vào thư mục game ({region.upper()}):")
    print(f"       Android/data/{pkg}/files/data/{cache_dir}/")
    print(f"  2. Sao lưu file gốc (nếu đã có) rồi chép đè file:")
    print(f"       {cache_file}")
    print(f"     vào đúng thư mục `{cache_dir}/` ở trên (tạo thư mục `{cache_dir}` nếu chưa có).")
    print("  3. Lưu ý: Nên tải sẵn story đó trong game trước (hoặc chép sẵn trước khi mở đọc).")
    print("=" * 72)

    return out_path


# =============================================================================
# Helpers for Selection Parsing & Interactive UI
# =============================================================================

def parse_chapter_selection(spec: str, episodes: Sequence[EpisodeEntry]) -> List[EpisodeEntry]:
    spec = spec.strip().lower()
    if spec in ("all", "a", "*"):
        return list(episodes)

    by_no = {ep.display_no: ep for ep in episodes}
    by_sid = {ep.scenario_id.lower(): ep for ep in episodes}
    selected: List[EpisodeEntry] = []
    seen = set()

    for token in re.split(r"[,\s]+", spec):
        if not token:
            continue
        if token in by_sid:
            ep = by_sid[token]
            if ep.scenario_id not in seen:
                seen.add(ep.scenario_id)
                selected.append(ep)
            continue
        m_range = re.match(r"^(\d+)-(\d+)$", token)
        if m_range:
            a, b = int(m_range.group(1)), int(m_range.group(2))
            for n in range(min(a, b), max(a, b) + 1):
                if n in by_no and by_no[n].scenario_id not in seen:
                    seen.add(by_no[n].scenario_id)
                    selected.append(by_no[n])
            continue
        if token.isdigit():
            n = int(token)
            if n in by_no:
                ep = by_no[n]
                if ep.scenario_id not in seen:
                    seen.add(ep.scenario_id)
                    selected.append(ep)
                continue
        raise ValueError(f"Không hiểu lựa chọn chapter: '{token}'")

    if not selected:
        raise ValueError("Chưa chọn chapter nào hợp lệ.")
    return selected


def resolve_main_group(query: str) -> MainStoryGroup:
    q = query.strip().lower()
    if q.isdigit():
        idx = int(q)
        if 1 <= idx <= len(MAIN_STORY_GROUPS):
            return MAIN_STORY_GROUPS[idx - 1]
    for g in MAIN_STORY_GROUPS:
        if q == g.key or q in g.aliases or q in g.display_name.lower():
            return g
    raise ValueError(
        f"Không tìm thấy nhóm Main Story '{query}'. "
        f"Các key hợp lệ: {', '.join(g.key for g in MAIN_STORY_GROUPS)}"
    )


def interactive_pick_story(region: str) -> Optional[StoryEntry]:
    print("\nChọn loại story:")
    print("  [1] Main Story (Unit Story + Virtual Singer)")
    print("  [2] Event Story")
    print("  [0] Quay lại")
    choice = input("Chọn (1/2/0): ").strip()

    if choice == "0" or not choice:
        return None

    if choice == "1":
        print(f"\n--- Main Story ({region.upper()}) ---")
        for i, g in enumerate(MAIN_STORY_GROUPS, start=1):
            print(f"  [{i:2d}] {g.display_name}")
        raw = input("Chọn nhóm (1-10): ").strip()
        if not raw or raw == "0":
            return None
        group = resolve_main_group(raw)
        return get_main_story(region, group)

    if choice == "2":
        items = list_event_stories(region)
        print(f"\n--- Event Story ({region.upper()} — tổng {len(items)} event) ---")
        print("15 event mới nhất:")
        for ev_id, ev_name, ab, _ in items[-15:]:
            print(f"  {ev_id:3d}: {ev_name}  ({ab})")

        while True:
            q = input("\nNhập ID event (VD: 210), từ khóa tìm kiếm, 'all' xem hết, hoặc '0' quay lại: ").strip()
            if not q or q == "0":
                return None
            if q.lower() == "all":
                for ev_id, ev_name, ab, _ in items:
                    print(f"  {ev_id:3d}: {ev_name}  ({ab})")
                continue
            if q.isdigit():
                return get_event_story(region, int(q))
            # Keyword search
            ql = q.lower()
            matches = [it for it in items if ql in it[1].lower() or ql in it[2].lower()]
            if not matches:
                print(f"  Không tìm thấy event nào khớp '{q}'. Thử từ khóa khác hoặc nhập ID.")
                continue
            if len(matches) == 1:
                ev_id, ev_name, ab, _ = matches[0]
                print(f"  -> Chọn: {ev_id}: {ev_name} ({ab})")
                return get_event_story(region, ev_id)
            print(f"  Tìm thấy {len(matches)} event:")
            for ev_id, ev_name, ab, _ in matches[:30]:
                print(f"    {ev_id:3d}: {ev_name}  ({ab})")
            if len(matches) > 30:
                print(f"    ... (còn {len(matches) - 30} kết quả nữa, hãy gõ cụ thể hơn)")

    print("Lựa chọn không hợp lệ.")
    return None


def interactive_extract(region: str) -> None:
    story = interactive_pick_story(region)
    if story is None:
        return

    cache_dir, cache_file = bundle_cache_path(story.bundle_name)
    print(f"\n=== {story.display_title} ({region.upper()}) ===")
    print(f"  Bundle : {story.bundle_name}")
    print(f"  Android: files/data/{cache_dir}/{cache_file}")
    print("\nDanh sách chapter:")
    for ep in story.episodes:
        print(f"  [{ep.display_no:2d}] {ep.label} — {ep.title}  ({ep.scenario_id})")

    sel_raw = input("\nChọn chapter (VD: 1, hoặc 1-4, hoặc 1,3, hoặc all): ").strip()
    if not sel_raw:
        return
    selected = parse_chapter_selection(sel_raw, story.episodes)
    written = extract_episodes(story, selected)
    if written:
        print("\nĐã xuất xong! Hãy mở file .txt ở trên để dịch, sau đó quay lại chọn [2] Patch.")


def interactive_patch(region: str) -> None:
    reg_work = WORK_DIR / region
    folders = []
    if reg_work.is_dir():
        for d in sorted(reg_work.iterdir()):
            if d.is_dir():
                txts = [p for p in d.glob("*.txt") if not p.name.endswith(".orig.txt")]
                if txts:
                    folders.append((d, txts))

    print(f"\n--- Patch bản dịch ({region.upper()}) ---")
    if folders:
        for idx, (d, txts) in enumerate(folders, start=1):
            print(f"  [{idx:2d}] {d.name}  ({len(txts)} chapter .txt)")
        print("  Hoặc nhập trực tiếp đường dẫn tới file .txt / thư mục.")
    else:
        print(f"  Chưa có thư mục nào trong {reg_work.relative_to(STORY_DIR.parent)}.")
        print("  Hãy nhập đường dẫn tới file .txt / thư mục (hoặc Enter để quay lại).")

    raw = input("Chọn số hoặc nhập đường dẫn: ").strip().strip('"')
    if not raw or raw == "0":
        return

    if raw.isdigit() and 1 <= int(raw) <= len(folders):
        target = folders[int(raw) - 1][0]
    else:
        target = Path(raw)

    patch_from_paths(target)


def interactive_lookup(region: str) -> None:
    story = interactive_pick_story(region)
    if story is None:
        return
    cache_dir, cache_file = bundle_cache_path(story.bundle_name)
    pkg = ANDROID_PACKAGES[region]
    print(f"\n=== Thông tin hash: {story.display_title} ({region.upper()}) ===")
    print(f"  Bundle name : {story.bundle_name}")
    print(f"  Cache dir   : {cache_dir}")
    print(f"  Cache file  : {cache_file}")
    print(f"  Android path: Android/data/{pkg}/files/data/{cache_dir}/{cache_file}")


def run_interactive() -> None:
    print("=" * 60)
    print("  Sekai-Modding — Story Modding Tool (Main & Event Story)")
    print("=" * 60)
    reg_in = input("Chọn server game ([1] JP (mặc định) / [2] EN): ").strip().lower()
    region = "en" if reg_in in ("2", "en") else "jp"

    while True:
        print(f"\n--- Menu chính (Server: {region.upper()}) ---")
        print("  [1] Tải & Extract story ra file .txt để dịch")
        print("  [2] Patch file .txt đã dịch -> bundle mã hóa")
        print("  [3] Tra cứu hash & thư mục Android của story")
        print("  [4] Làm mới danh sách event / version mới nhất")
        print("  [5] Đổi server (JP <-> EN)")
        print("  [0] Thoát")

        cmd = input("Chọn (1/2/3/4/5/0): ").strip()
        try:
            if cmd == "0":
                break
            elif cmd == "1":
                interactive_extract(region)
            elif cmd == "2":
                interactive_patch(region)
            elif cmd == "3":
                interactive_lookup(region)
            elif cmd == "4":
                refresh_metadata(region)
            elif cmd == "5":
                region = "en" if region == "jp" else "jp"
                print(f"Đã chuyển sang server: {region.upper()}")
            else:
                print("Vui lòng chọn từ 0 đến 5.")
        except Exception as e:
            print(f"\n[ERROR] {e}")


# =============================================================================
# CLI Entrypoint
# =============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project Sekai Main & Event Story modding tool (download via sssekai, extract, patch, encrypt)."
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", help="Liệt kê Main Story / Event Story và đường dẫn hash")
    p_list.add_argument("--region", choices=("jp", "en"), default="jp")
    p_list.add_argument("--type", choices=("main", "event"), default="event")
    p_list.add_argument("--search", default="", help="Từ khóa lọc tên / assetbundleName event")
    p_list.add_argument("--refresh", action="store_true", help="Tải lại metadata mới nhất từ GitHub")

    # extract
    p_ext = sub.add_parser("extract", help="Tải bundle qua sssekai và extract chapter ra file .txt để dịch")
    p_ext.add_argument("--region", choices=("jp", "en"), default="jp")
    grp = p_ext.add_mutually_exclusive_group(required=True)
    grp.add_argument("--main", help="Nhóm Main Story (VD: leo, mmj, vbs, wxs, n25, vs-leo, vs-mmj, vs-vbs, vs-wxs, vs-n25)")
    grp.add_argument("--event", type=int, help="ID của Event Story (VD: 210)")
    p_ext.add_argument("--chapter", default="all", help="Số tập cần extract (VD: 1, 1-4, 1,3, hoặc all)")
    p_ext.add_argument("--overwrite", action="store_true", help="Ghi đè nếu file .txt đã tồn tại")
    p_ext.add_argument("--force-download", action="store_true", help="Bỏ qua cache và tải lại bundle gốc")

    # patch
    p_pat = sub.add_parser("patch", help="Patch 1 file .txt hoặc cả thư mục .txt đã dịch -> bundle mã hóa")
    p_pat.add_argument("target", help="Đường dẫn file .txt hoặc thư mục chứa các file .txt của cùng 1 story")
    p_pat.add_argument("--output", "-o", default=None, help="Đường dẫn file xuất tùy chỉnh (mặc định: story/output/<region>/<dir>/<file>)")

    # refresh
    p_ref = sub.add_parser("refresh", help="Cập nhật metadata (versions, unitStories, eventStories, events)")
    p_ref.add_argument("--region", choices=("jp", "en"), default="jp")

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.command:
        run_interactive()
        return

    if args.command == "refresh":
        refresh_metadata(args.region)
        return

    if args.command == "list":
        if args.refresh:
            refresh_metadata(args.region)
        if args.type == "main":
            for i, g in enumerate(MAIN_STORY_GROUPS, start=1):
                st = get_main_story(args.region, g)
                cdir, cfile = bundle_cache_path(st.bundle_name)
                print(
                    f"[{i:2d}] {g.key:6s} | {g.display_name:55s} | "
                    f"{len(st.episodes):2d} eps | {cdir}/{cfile}"
                )
        else:
            items = list_event_stories(args.region)
            ql = args.search.lower().strip()
            for ev_id, ev_name, ab, es in items:
                if ql and ql not in ev_name.lower() and ql not in ab.lower() and ql != str(ev_id):
                    continue
                cdir, cfile = bundle_cache_path(f"event_story/{ab}/scenario")
                eps = len(es.get("eventStoryEpisodes", []))
                print(f"{ev_id:3d}: {ev_name}  ({ab}, {eps} eps) -> {cdir}/{cfile}")
        return

    if args.command == "extract":
        if args.main:
            story = get_main_story(args.region, resolve_main_group(args.main))
        else:
            story = get_event_story(args.region, args.event)

        cdir, cfile = bundle_cache_path(story.bundle_name)
        print(f"=== {story.display_title} ({args.region.upper()}) ===")
        print(f"  Bundle : {story.bundle_name}")
        print(f"  Android: files/data/{cdir}/{cfile}")
        selected = parse_chapter_selection(args.chapter, story.episodes)
        extract_episodes(
            story,
            selected,
            force_download=args.force_download,
            overwrite=args.overwrite,
        )
        return

    if args.command == "patch":
        out = Path(args.output) if args.output else None
        patch_from_paths(Path(args.target), output_override=out)
        return


if __name__ == "__main__":
    main()
