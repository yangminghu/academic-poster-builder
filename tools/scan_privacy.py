# -*- coding: utf-8 -*-
"""scan_privacy.py —— 发布前隐私体检（通用规则，不含任何具体项目标识）。

本文件会随公开仓库分发，因此**绝不能把"要隐藏的字符串"写进源码** —— 那等于把要藏的东西公开。
这里只用通用规则；具体项目标识请在运行时通过环境变量传入：

    PRIVACY_DENY="样品A;批次B;某文件名" python tools/scan_privacy.py

用法：
    python tools/scan_privacy.py [路径...]        # 默认扫本仓库（跳过 .git/ 与 dist/）
    python tools/scan_privacy.py --zip <zip>      # 额外扫 zip 的原始字节（含中央目录文件名表）
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

SKIP_DIRS = {".git", "dist", "__pycache__", "node_modules", ".github"}
SKIP_EXT = {".pyc", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"}
DATA_EXT = {".txt", ".csv", ".tsv", ".xlsx", ".xls", ".mat", ".dat", ".bin"}

# 动态拼接，避免本文件被自己命中
_RULES = [
    ("手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ("邮箱", r"[\w.+-]+" + "@" + r"[\w-]+\.[\w.]{2,}"),
    ("绝对路径(Windows)", r"[A-Za-z]:" + r"[\\/](?:Users|Documents|Desktop|data|work)"),
    ("绝对路径(类 Unix)", r"/(?:home|Users|mnt|media)/[\w.-]+/"),
    ("NUL 字节", None),
]
RULES = [(n, re.compile(p) if p else None) for n, p in _RULES]


def deny_words() -> list[str]:
    return [w.strip() for w in re.split(r"[;\n]+", os.environ.get("PRIVACY_DENY", "")) if w.strip()]


def scan_bytes(rel: str, raw: bytes, hits: list[str]) -> None:
    for name, pat in RULES:
        if pat is None:
            if b"\x00" in raw:
                hits.append("%s: NUL 字节" % rel)
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for m in pat.finditer(text):
                hits.append("%s: %s → %s" % (rel, name, m.group(0)[:40]))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return
    for w in deny_words():
        if w in text:
            hits.append("%s: PRIVACY_DENY → %s" % (rel, w[:24]))


def scan_tree(root: pathlib.Path) -> list[str]:
    hits: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if p.suffix.lower() in DATA_EXT:
            hits.append("%s: 数据类文件（不应入库）" % rel)
        if p.suffix.lower() in SKIP_EXT:
            continue
        scan_bytes(rel, p.read_bytes(), hits)
    return hits


def scan_zip(path: pathlib.Path) -> list[str]:
    hits: list[str] = []
    raw = path.read_bytes()
    for w in deny_words():
        if w.encode() in raw:
            hits.append("%s: PRIVACY_DENY 出现在 zip 原始字节 → %s" % (path.name, w[:24]))
    z = zipfile.ZipFile(path)
    for info in z.infolist():
        if info.is_dir():
            continue
        if pathlib.PurePosixPath(info.filename).suffix.lower() in DATA_EXT:
            hits.append("%s: zip 内含数据类文件" % info.filename)
        scan_bytes(info.filename, z.read(info), hits)
    return hits


def main(argv: list[str] | None = None) -> int:
    here = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="发布前隐私体检")
    ap.add_argument("paths", nargs="*", default=None, help="要扫的目录（默认本仓库）")
    ap.add_argument("--zip", action="append", default=[], help="额外扫 zip 原始字节（可多次）")
    a = ap.parse_args(argv)

    targets = [pathlib.Path(p).resolve() for p in a.paths] or [here]
    hits: list[str] = []
    for t in targets:
        if t.is_dir():
            hits += scan_tree(t)
        elif t.suffix.lower() == ".zip":
            hits += scan_zip(t)
        else:
            scan_bytes(t.name, t.read_bytes(), hits)
    for z in a.zip:
        hits += scan_zip(pathlib.Path(z).resolve())

    print("== 隐私体检 ==")
    print("  扫描目标：%s" % ", ".join(str(t) for t in targets))
    print("  运行时禁词：%s" % (deny_words() or "（未设置 PRIVACY_DENY，仅用通用规则）"))
    if hits:
        for h in hits:
            print("  [命中] %s" % h)
        print("PRIVACY FAIL（%d 处）" % len(hits))
        return 1
    print("PRIVACY PASS（0 命中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
