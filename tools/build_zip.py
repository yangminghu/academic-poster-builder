# -*- coding: utf-8 -*-
"""build_zip.py —— 确定性打包：同样的输入必得同样的字节。

固定条目顺序、固定时间戳、固定权限位、不写目录条目、全部 deflate。
这样 CI 里可以"打包两次比对字节"来证明产物可复现，Release 附件也因此稳定。

用法：
    python tools/build_zip.py                          # 打包 academic-poster-builder/ → dist/
    python tools/build_zip.py --pkg <目录> --out <zip>
    python tools/build_zip.py --reproducible           # 打两次并比对（CI 用）
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys
import tempfile
import zipfile

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

# zip 内固定时间戳（1980-01-01 00:00:00，DOS 时间最小值）
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
FIXED_ATTR = (0o644 << 16)  # 普通文件
TOP_ORDER = ["SKILL.md", "references", "scripts", "templates"]


def package_version(pkg: pathlib.Path) -> str:
    text = (pkg / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*([\d.]+)\s*$", text, re.M)
    if not m:
        raise SystemExit("SKILL.md 里找不到 version 字段")
    return m.group(1)


def ordered_files(pkg: pathlib.Path) -> list[pathlib.Path]:
    files = [p for p in pkg.rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.suffix != ".pyc" and not p.name.startswith(".")]
    def key(p: pathlib.Path):
        rel = p.relative_to(pkg).as_posix()
        top = rel.split("/")[0]
        rank = TOP_ORDER.index(top) if top in TOP_ORDER else len(TOP_ORDER)
        return (rank, rel)
    return sorted(files, key=key)


def build(pkg: pathlib.Path, out: pathlib.Path) -> tuple[int, str]:
    files = ordered_files(pkg)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            rel = f.relative_to(pkg).as_posix()
            zi = zipfile.ZipInfo("%s/%s" % (pkg.name, rel), date_time=FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = FIXED_ATTR
            zi.create_system = 0
            if not rel.isascii():
                zi.flag_bits |= 0x800
            z.writestr(zi, f.read_bytes())
    data = out.read_bytes()
    return len(files), hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    here = pathlib.Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="确定性打包技能包")
    ap.add_argument("--pkg", default=None, help="包目录（默认 <仓库>/academic-poster-builder）")
    ap.add_argument("--out", default=None, help="输出 zip（默认 dist/<包名>-v<版本>.zip）")
    ap.add_argument("--reproducible", action="store_true", help="打两次并比对字节")
    a = ap.parse_args(argv)

    pkg = pathlib.Path(a.pkg).resolve() if a.pkg else here / "academic-poster-builder"
    if not (pkg / "SKILL.md").is_file():
        raise SystemExit("找不到包目录：%s" % pkg)
    ver = package_version(pkg)
    out = pathlib.Path(a.out).resolve() if a.out else here / "dist" / ("%s-v%s.zip" % (pkg.name, ver))

    n, sha = build(pkg, out)
    print("打包：%s" % out)
    print("  包名 %s | 版本 %s | 条目 %d | 字节 %d" % (pkg.name, ver, n, out.stat().st_size))
    print("  sha256 %s" % sha)

    if a.reproducible:
        with tempfile.TemporaryDirectory() as td:
            again = pathlib.Path(td) / "again.zip"
            _, sha2 = build(pkg, again)
            same = sha == sha2
            print("  可复现：%s（第二次 %s）" % ("是" if same else "否", sha2[:16]))
            if not same:
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
