"""Generate a binary AndroidManifest.xml without aapt (pure Python).

Supports the small subset needed for a WebView launcher: namespace, elements,
plain and android-namespaced string/int/bool attributes. No compiled resources
are needed because the label is a plain string, not an @resource reference.

Booleans MUST use TYPE_INT_BOOLEAN — encoding them as strings makes Android's
package parser throw INSTALL_PARSE_FAILED_MANIFEST_MALFORMED ("problem while
parsing the package"). <uses-sdk> is also required on modern Android.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

RES_STRING_POOL_TYPE = 0x0001
RES_XML_TYPE = 0x0003
RES_XML_START_NAMESPACE_TYPE = 0x0100
RES_XML_END_NAMESPACE_TYPE = 0x0101
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103

TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_BOOLEAN = 0x12
NO_ENTRY = 0xFFFFFFFF
ANDROID_NS = "http://schemas.android.com/apk/res/android"


class StringPool:
    def __init__(self) -> None:
        self.strings: list[str] = []
        self.index: dict[str, int] = {}

    def add(self, s: str) -> int:
        if s not in self.index:
            self.index[s] = len(self.strings)
            self.strings.append(s)
        return self.index[s]

    def build(self) -> bytes:
        offsets, data = [], bytearray()

        def enc_len(n: int) -> bytes:
            # Android UTF-8 string pool uses 1-byte lengths below 0x80.
            return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])

        for s in self.strings:
            offsets.append(len(data))
            b = s.encode("utf-8")
            # Order: utf16 length, utf8 byte length, bytes, NUL terminator.
            data += enc_len(len(s)) + enc_len(len(b)) + b + b"\x00"
        while len(data) % 4:
            data += b"\x00"
        header_size = 28
        chunk_size = header_size + 4 * len(self.strings) + len(data)
        out = struct.pack("<HHIIIIII", RES_STRING_POOL_TYPE, header_size, chunk_size,
                          len(self.strings), 0, 0x100, header_size + 4 * len(self.strings), 0)
        for off in offsets:
            out += struct.pack("<I", off)
        return out + bytes(data)


def _chunk(ctype: int, body: bytes) -> bytes:
    # ResXMLTree_node header = ResChunk_header (8) + lineNumber (4) + comment (4).
    return struct.pack("<HHIII", ctype, 16, 16 + len(body), 1, NO_ENTRY) + body


def _typed(value: str | int | bool, pool: StringPool) -> bytes:
    # bool must be checked before int (bool is a subclass of int in Python).
    if isinstance(value, bool):
        return struct.pack("<HBBI", 8, 0, TYPE_INT_BOOLEAN, 0xFFFFFFFF if value else 0)
    if isinstance(value, int):
        return struct.pack("<HBBI", 8, 0, TYPE_INT_DEC, value)
    idx = pool.add(value)
    return struct.pack("<HBBI", 8, 0, TYPE_STRING, idx)


def start_element(pool: StringPool, tag: str,
                  android_attrs: list[tuple[str, str | int | bool]],
                  plain_attrs: list[tuple[str, str]] | None = None) -> bytes:
    name_i = pool.add(tag)
    ab = b""
    for k, v in plain_attrs or []:
        ki, vi = pool.add(k), pool.add(v)
        ab += struct.pack("<III", NO_ENTRY, ki, vi) + _typed(v, pool)
    for k, v in android_attrs:
        ni = pool.add(k)
        raw = pool.add(v) if isinstance(v, str) else NO_ENTRY
        ab += struct.pack("<III", pool.add(ANDROID_NS), ni, raw) + _typed(v, pool)
    ext = struct.pack("<IIHHHHHH", NO_ENTRY, name_i, 20, 20,
                      len(android_attrs) + len(plain_attrs or []), 0, 0, 0)
    return _chunk(RES_XML_START_ELEMENT_TYPE, ext + ab)


def end_element(pool: StringPool, tag: str) -> bytes:
    return _chunk(RES_XML_END_ELEMENT_TYPE, struct.pack("<II", NO_ENTRY, pool.add(tag)))


def build(package: str, label: str) -> bytes:
    pool = StringPool()
    pool.add("android")
    pool.add(ANDROID_NS)

    body = _chunk(RES_XML_START_NAMESPACE_TYPE,
                  struct.pack("<II", pool.add("android"), pool.add(ANDROID_NS)))

    def elem(tag, android_attrs, plain_attrs=None):
        return start_element(pool, tag, android_attrs, plain_attrs)

    body += elem("manifest", [("versionCode", 1), ("versionName", "1.0")],
                 [("package", package)])
    # Required on modern Android — without it some installers reject the package.
    body += elem("uses-sdk", [("minSdkVersion", 21), ("targetSdkVersion", 35)])
    body += end_element(pool, "uses-sdk")
    body += elem("uses-permission", [("name", "android.permission.INTERNET")])
    body += end_element(pool, "uses-permission")
    body += elem("uses-permission", [("name", "android.permission.ACCESS_NETWORK_STATE")])
    body += end_element(pool, "uses-permission")
    body += elem("application", [("label", label), ("allowBackup", True),
                                 ("usesCleartextTraffic", True), ("hasCode", True)])
    body += elem("activity", [("name", "com.v2dstudio.app.MainActivity"), ("exported", True)])
    body += elem("intent-filter", [])
    body += elem("action", [("name", "android.intent.action.MAIN")])
    body += end_element(pool, "action")
    body += elem("category", [("name", "android.intent.category.LAUNCHER")])
    body += end_element(pool, "category")
    body += end_element(pool, "intent-filter")
    body += end_element(pool, "activity")
    body += end_element(pool, "application")
    body += end_element(pool, "manifest")
    body += _chunk(RES_XML_END_NAMESPACE_TYPE,
                   struct.pack("<II", pool.add("android"), pool.add(ANDROID_NS)))

    sp = pool.build()
    header = struct.pack("<HHI", RES_XML_TYPE, 8, 8 + len(sp) + len(body))
    return header + sp + body


if __name__ == "__main__":
    out = Path(sys.argv[1])
    package = sys.argv[2] if len(sys.argv) > 2 else "com.v2dstudio.app"
    label = sys.argv[3] if len(sys.argv) > 3 else "V2D Studio"
    out.write_bytes(build(package, label))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
