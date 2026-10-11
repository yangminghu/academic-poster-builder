# -*- coding: utf-8 -*-
"""50_snapshot.py —— 每个交付版本留一份快照（用户明确要求保留历史备份）。

    python 50_snapshot.py --dir . --label v7_final [--keep poster.html,poster.pdf,poster.pptx]

生成 `_backup/<yyyyMMdd_HHmmss>_<label>/`，并写 `_backup/README.txt` 说明备份策略。
同一秒内同名快照会自动加 `_2`/`_3` 后缀：**既有快照永不覆盖**（历史就是要留着）。
不给 --keep 时自动收集该目录下的 *.html/*.pdf/*.pptx（文件名任意，不写死 poster.*）。
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys

for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

README = """backup policy
=============
_backup/<timestamp>_<label>/   每次改动前/后的 html|pdf|pptx 全量副本
_work/pretrim/                 图片裁白边前的原始素材
_work/shapes.json              当前 PPTX 所依据的浏览器实测数据
每个交付版本都要有快照；回退时直接取对应目录里的文件。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--label", default="snapshot")
    ap.add_argument("--keep", default=None, help="文件名（逗号分隔）；缺省自动收集 *.html/*.pdf/*.pptx")
    ap.add_argument("--backup-root", default="_backup")
    args = ap.parse_args()

    root = os.path.join(args.dir, args.backup_root)
    # 秒级时间戳 + 冲突后缀：同一分钟内连拍两次也不会互相覆盖（分钟级曾直接吞掉前一份）
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(root, "%s_%s" % (stamp, args.label))
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(root, "%s_%s_%d" % (stamp, args.label, n))
        n += 1
    os.makedirs(dest)                      # 不用 exist_ok：绝不落进已有目录
    with open(os.path.join(root, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(README)

    if args.keep:
        names = [x.strip() for x in args.keep.split(",") if x.strip()]
    else:
        names = sorted(f for f in os.listdir(args.dir)
                       if os.path.isfile(os.path.join(args.dir, f))
                       and f.lower().endswith((".html", ".pdf", ".pptx")))
        if not names:
            print("目录里没有 *.html / *.pdf / *.pptx 可快照；用 --keep 指定文件名")
            return 1
        print("自动识别到：%s" % ", ".join(names))

    copied = []
    for name in names:
        src = os.path.join(args.dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, os.path.basename(name)))
            copied.append("%s (%.2f MB)" % (os.path.basename(name), os.path.getsize(src) / 2 ** 20))
    print("snapshot -> %s" % dest)
    for c in copied:
        print("   " + c)
    if not copied:
        print("   (没有找到任何文件；用 --keep 指定文件名)")
        return 1
    print("history: %d snapshot(s)"
          % len([d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
