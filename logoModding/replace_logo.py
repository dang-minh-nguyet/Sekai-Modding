"""
replace_logo.py
---------------
All-in-one pipeline:
  1. Decrypt  426774ceaca2c93196cdb9e2c551d1ff
  2. Inspect  the Texture2D inside to get W x H
  3. Resize   alt.png (and alt.webp if present) to that resolution,
              transparent background, aspect-ratio preserving letterbox
  4. Replace  the texture inside the bundle  (set_image API)
  5. Encrypt  -> output: 426774ceaca2c93196cdb9e2c551d1ff.modded

Run from the logoModding/ directory:
    python replace_logo.py
"""

import io
import os
import sys

# ── third-party ──────────────────────────────────────────────────────────────
try:
    import UnityPy
    from UnityPy.enums import ClassIDType
except ImportError:
    sys.exit("[ERROR] UnityPy not found.  Run:  pip install UnityPy")

try:
    from PIL import Image
except ImportError:
    sys.exit("[ERROR] Pillow not found.  Run:  pip install Pillow")

# ── constants ─────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
BUNDLE_NAME = "426774ceaca2c93196cdb9e2c551d1ff"
BUNDLE_PATH = os.path.join(SCRIPT_DIR, BUNDLE_NAME)
ALT_PNG     = os.path.join(SCRIPT_DIR, "alt.png")
ALT_WEBP    = os.path.join(SCRIPT_DIR, "alt.webp")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, BUNDLE_NAME + ".modded")

MAGIC       = b"\x10\x00\x00\x00"
HEADER_SIZE = 128


# =============================================================================
# Crypto helpers  (self-inverse XOR; same as decrypt_bundle.py / encrypt_bundle.py)
# =============================================================================

def _flip_header(header: bytearray) -> bytearray:
    """Flip bits on the first 5 bytes of every 8-byte block."""
    assert len(header) == HEADER_SIZE
    for i in range(0, HEADER_SIZE, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header


def decrypt_to_bytes(path: str) -> bytes:
    """Read an encrypted bundle and return raw decrypted bytes."""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            print("[INFO] No magic bytes - treating file as already decrypted.")
            f.seek(0)
            return f.read()
        header = bytearray(f.read(HEADER_SIZE))
        rest   = f.read()
    _flip_header(header)
    return bytes(header) + rest


def encrypt_bytes(raw: bytes) -> bytes:
    """Wrap raw bundle bytes with the 4-byte magic + XOR'd header."""
    header = bytearray(raw[:HEADER_SIZE])
    _flip_header(header)
    return MAGIC + bytes(header) + raw[HEADER_SIZE:]


# =============================================================================
# Image helpers
# =============================================================================

def letterbox(src: Image.Image, w: int, h: int) -> Image.Image:
    """
    Scale *src* to fit inside (w, h) preserving aspect ratio.
    Result is centred on a fully-transparent RGBA canvas of size (w, h).
    """
    src = src.convert("RGBA")
    src.thumbnail((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = (w - src.width)  // 2
    y = (h - src.height) // 2
    canvas.paste(src, (x, y), src)
    return canvas


# =============================================================================
# Main pipeline
# =============================================================================

def main():
    # ── 1. Decrypt ────────────────────────────────────────────────────────────
    print("[1/5] Decrypting bundle ...")
    raw = decrypt_to_bytes(BUNDLE_PATH)
    print(f"      Bundle size after decrypt: {len(raw):,} bytes")

    # ── 2. Load with UnityPy & find the Texture2D ─────────────────────────────
    print("[2/5] Loading bundle with UnityPy ...")
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.31f1"
    env = UnityPy.load(io.BytesIO(raw))

    texture_objs = []
    for obj in env.objects:
        if obj.type == ClassIDType.Texture2D:
            try:
                data = obj.read()
                texture_objs.append((data.m_Name, data.m_Width, data.m_Height, obj))
            except Exception as e:
                print(f"      [WARN] Could not read a Texture2D: {e}")

    if not texture_objs:
        sys.exit("[ERROR] No Texture2D assets found in this bundle.")

    for name, w, h, _ in texture_objs:
        fmt = texture_objs[0][3].read().m_TextureFormat
        print(f"      Texture2D  '{name}'  {w} x {h}  format={fmt}")

    # Use first texture (the bundle only contains one)
    target_name, tex_w, tex_h, target_obj = texture_objs[0]
    print(f"      -> Will replace '{target_name}' ({tex_w} x {tex_h})")

    # ── 3. Resize source images ───────────────────────────────────────────────
    print("[3/5] Resizing source images ...")

    sources = []
    if os.path.exists(ALT_PNG):
        sources.append(("PNG", ALT_PNG))
    if os.path.exists(ALT_WEBP):
        sources.append(("WEBP", ALT_WEBP))

    if not sources:
        sys.exit(f"[ERROR] Neither alt.png nor alt.webp found in {SCRIPT_DIR}")

    resized = {}
    for label, path in sources:
        src = Image.open(path)
        print(f"      {label}  original: {src.width} x {src.height}")
        img = letterbox(src, tex_w, tex_h)
        resized[label] = img
        # Save a preview for inspection
        preview = os.path.join(SCRIPT_DIR, f"alt_preview_{label.lower()}.png")
        img.save(preview, format="PNG")
        print(f"      {label}  resized : {img.width} x {img.height}  (preview -> {preview})")

    # Prefer WEBP source for highest quality injection (same resize logic)
    inject_img = resized.get("WEBP", resized.get("PNG"))
    label_used = "WEBP" if "WEBP" in resized else "PNG"
    print(f"      Using {label_used} source for bundle injection.")

    # ── 4. Replace the texture ────────────────────────────────────────────────
    print("[4/5] Injecting new image into bundle ...")
    tex_data = target_obj.read()

    # Clear external StreamData so Unity reads inline pixel data
    if hasattr(tex_data, "m_StreamData") and tex_data.m_StreamData:
        tex_data.m_StreamData.offset = 0
        tex_data.m_StreamData.size   = 0
        tex_data.m_StreamData.path   = ""

    # set_image() encodes the PIL image to the texture's original format
    tex_data.set_image(inject_img)
    tex_data.save()
    print(f"      Texture '{target_name}' replaced.")

    # ── 5. Pack & encrypt ─────────────────────────────────────────────────────
    print("[5/5] Packing (LZ4) and encrypting ...")
    packed    = env.file.save(packer="lz4")
    encrypted = encrypt_bytes(packed)

    with open(OUTPUT_PATH, "wb") as f:
        f.write(encrypted)

    print(f"\n[DONE]  Output -> {OUTPUT_PATH}")
    print(f"        Rename to  {BUNDLE_NAME}  and drop into the game's 47a2/ folder.")


if __name__ == "__main__":
    main()
