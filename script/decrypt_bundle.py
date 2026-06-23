"""
decrypt_bundle.py
-----------------
Drag and drop an encrypted Unity asset bundle onto this script (or pass the
path as the first argument) to produce a decrypted copy next to the original.

Encrypted format expected:
  [4-byte magic: 10 00 00 00] [128-byte XOR'd header] [remaining data ...]

Output: <original_filename>.decrypted
"""

import os
import sys


MAGIC = b"\x10\x00\x00\x00"
HEADER_SIZE = 128


def decrypt_header(header: bytearray) -> bytearray:
    """Flip bits on the first 5 bytes of every 8-byte block."""
    assert len(header) == HEADER_SIZE, f"Header must be exactly {HEADER_SIZE} bytes."
    for i in range(0, HEADER_SIZE, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header


def decrypt_file(src_path: str) -> None:
    if not os.path.isfile(src_path):
        print(f"[ERROR] File not found: {src_path}")
        return

    with open(src_path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            print(f"[SKIP]  Not an encrypted bundle (bad magic): {src_path}")
            return

        header_raw = bytearray(f.read(HEADER_SIZE))
        if len(header_raw) < HEADER_SIZE:
            print(f"[ERROR] File too short to contain a full header: {src_path}")
            return

        rest = f.read()

    decrypted_header = decrypt_header(header_raw)

    out_path = src_path + ".decrypted"
    with open(out_path, "wb") as f:
        f.write(decrypted_header)
        f.write(rest)

    print(f"[OK]    Decrypted → {out_path}")


def main():
    paths = sys.argv[1:]
    if not paths:
        print("Usage: drag and drop one or more encrypted bundle files onto this script.")
        input("Press Enter to exit...")
        return

    for path in paths:
        decrypt_file(path)

    input("\nDone. Press Enter to exit...")


if __name__ == "__main__":
    main()
