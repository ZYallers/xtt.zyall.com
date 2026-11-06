#!/usr/bin/env python3
"""把若干 PNG 打成一个多尺寸 ICO（Vista+ 支持条目内直接内嵌 PNG）。

用法：build_ico.py <输出.ico> <16.png> <32.png> ...
尺寸从每个 PNG 的 IHDR 读取，不依赖 Pillow。
"""
import struct
import sys


def png_size(data: bytes) -> int:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    w, h = struct.unpack(">II", data[16:24])
    assert w == h and 0 < w <= 256, f"只支持正方形、边长 1~256 的 PNG，拿到 {w}x{h}"
    return w


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    dst, srcs = sys.argv[1], sys.argv[2:]

    blobs = []
    for path in srcs:
        data = open(path, "rb").read()
        size = png_size(data)
        print(f"  {path}: {size}x{size} bitdepth={data[24]} colortype={data[25]} {len(data)}B")
        blobs.append((size, data))
    blobs.sort(key=lambda b: b[0])

    out = bytearray(struct.pack("<HHH", 0, 1, len(blobs)))   # reserved/type/count
    offset = 6 + 16 * len(blobs)
    for size, data in blobs:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in blobs:
        out += data

    with open(dst, "wb") as fh:
        fh.write(out)
    print(f"→ {dst}  {len(out)} bytes")


if __name__ == "__main__":
    main()
