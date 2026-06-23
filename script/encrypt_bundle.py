"""
encrypt_bundle.py
-----------------
Drag and drop a DECRYPTED Unity asset bundle onto this script (or pass the
path as the first argument) to produce a re-encrypted copy next to the original.

The XOR transform is its own inverse, so the same bit-flip operation both
encrypts and decrypts the 128-byte header.

Output format:
  [4-byte magic: 10 00 00 00] [128-byte XOR'd header] [remaining data ...]

Output: <original_filename>.encrypted
"""

import os
import sys


MAGIC = b"\x10\x00\x00\x00"
HEADER_SIZE = 128


def encrypt_header(header: bytearray) -> bytearray:
    """Flip bits on the first 5 bytes of every 8-byte block (same as decrypt)."""
    assert len(header) == HEADER_SIZE, f"Header must be exactly {HEADER_SIZE} bytes."
    for i in range(0, HEADER_SIZE, 8):
        for j in range(5):
            header[i + j] = ~header[i + j] & 0xFF
    return header


def encrypt_file(src_path: str) -> None:
    if not os.path.isfile(src_path):
        print(f"[ERROR] File not found: {src_path}")
        return

    with open(src_path, "rb") as f:
        data = f.read()

    # Guard: refuse to double-encrypt an already-encrypted file.
    if data[:4] == MAGIC:
        print(f"[SKIP]  File already appears encrypted (magic bytes present): {src_path}")
        return

    if len(data) < HEADER_SIZE:
        print(f"[ERROR] File too short to encrypt (need at least {HEADER_SIZE} bytes): {src_path}")
        return

    header = bytearray(data[:HEADER_SIZE])
    rest = data[HEADER_SIZE:]

    encrypted_header = encrypt_header(header)

    out_path = src_path + ".encrypted"
    with open(out_path, "wb") as f:
        f.write(MAGIC)
        f.write(encrypted_header)
        f.write(rest)

    print(f"[OK]    Encrypted → {out_path}")


def main():
    paths = sys.argv[1:]
    if not paths:
        print("Usage: drag and drop one or more decrypted bundle files onto this script.")
        input("Press Enter to exit...")
        return

    for path in paths:
        encrypt_file(path)

    input("\nDone. Press Enter to exit...")


if __name__ == "__main__":
    main()
