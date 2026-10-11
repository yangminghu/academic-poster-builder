# -*- coding: utf-8 -*-
"""30_figure_tools.py —— 图片工具：裁白边 / 纵横比审计。

    python 30_figure_tools.py trim   --assets assets --margin 10 [--backup _work/pretrim] [--only a.png]
    python 30_figure_tools.py aspect --html poster.html [--shapes _work/shapes.json] [--tol 0.5]

trim：把每张图裁到「墨迹包围盒 + margin」。素材常带不对称白边（例：左 7 px / 右 99 px），
      版面上会被读成"右侧留白太多"。裁完纵横比会变，必须同步更新 HTML 的 width/height。
      保留原模式（RGBA/调色板图的 alpha 不丢）；JPEG 用 quality=95、subsampling=0 重编码。
aspect：逐张比对 HTML 里写的 w/h 与源图宽高比，误差 >tol% 报红（退出码 1）。
      只覆盖**行内 style 写死尺寸**的图；CSS 类定尺寸的图必须靠 40_verify_pptx.py 验收。
      <img> 有、但一个都审计不到时退出码 2（"此检查没有真正运行"），--allow-empty 可显式接受。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys

import numpy as np
from PIL import Image

for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TOL_INK = 245
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
# 属性值三种写法都收：双引号 / 单引号 / 不带引号（HTML 里都合法）
STYLE = re.compile(r"\bstyle\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
SRC = re.compile(r"\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
# width:964 / width:964px / WIDTH: 964.5px 都算；min-width/max-width 与百分比/em 不算
WH = re.compile(r"(?<![\w-])(width|height)\s*:\s*(\d+(?:\.\d+)?)\s*(?:px)?(?![%\w.])", re.I)


def _attr(m):
    """取属性值：正则里三种引号各占一个分组，取非 None 的那个。"""
    if not m:
        return None
    return next((g for g in m.groups() if g is not None), None)


def inline_sizes(html: str):
    """[(src, w, h)] —— 行内 style 同时写死 width/height 的图片（顺序无关）。

    先删掉 HTML 注释：模板里注释掉的示例 <figure><img …> 不该被当成待检图片。
    """
    out = []
    for tag in IMG_TAG.findall(re.sub(r"<!--.*?-->", "", html, flags=re.S)):
        style, src = _attr(STYLE.search(tag)), _attr(SRC.search(tag))
        if not style or not src:
            continue
        d = {k.lower(): float(v) for k, v in WH.findall(style)}
        if d.get("width") and d.get("height"):
            out.append((src, d["width"], d["height"]))
    return out


def cmd_trim(a) -> int:
    if a.backup:
        os.makedirs(a.backup, exist_ok=True)
    only = set(x.strip() for x in a.only.split(",")) if a.only else None
    files = []
    for root, _, names in os.walk(a.assets):
        for n in sorted(names):
            if n.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and (not only or n in only):
                files.append(os.path.join(root, n))
    changed, failed = 0, []
    for p in files:
        name = os.path.basename(p)
        try:
            with Image.open(p) as im:
                fmt = (im.format or "").upper()
                info = dict(im.info)
                w0, h0 = im.size
                ys, xs = np.where(np.asarray(im.convert("L")) < TOL_INK)
                if len(xs) == 0:
                    print("%-46s 全白，跳过" % name)
                    continue
                box = (max(0, int(xs.min()) - a.margin), max(0, int(ys.min()) - a.margin),
                       min(w0, int(xs.max()) + 1 + a.margin), min(h0, int(ys.max()) + 1 + a.margin))
                if box == (0, 0, w0, h0):
                    continue
                # 不 convert("RGB")：RGBA / 调色板图的 alpha 必须原样保留（只裁不降级）
                out = im.crop(box)
                out.load()                  # 先读进内存，源文件句柄才能安全关闭
            if a.backup:                    # 备份一定在任何写入之前
                shutil.copy2(p, os.path.join(a.backup, os.path.basename(p)))
            is_jpeg = fmt in ("JPEG", "JPG") or os.path.splitext(p)[1].lower() in (".jpg", ".jpeg")
            kw = {"quality": 95, "subsampling": 0} if is_jpeg else {}
            if is_jpeg and out.mode not in ("RGB", "L"):
                out = out.convert("RGB")     # 只有 JPEG 不支持 alpha，才在这里降级
            if info.get("icc_profile"):
                kw["icc_profile"] = info["icc_profile"]
            if is_jpeg and info.get("exif"):
                kw["exif"] = info["exif"]
            out.save(p, **kw)
            out.close()
            changed += 1
            print("%-46s %dx%d -> %dx%d  aspect %.3f -> %.3f"
                  % (name, w0, h0, box[2] - box[0], box[3] - box[1],
                     w0 / h0, (box[2] - box[0]) / (box[3] - box[1])))
        except Exception as exc:            # 一个文件坏掉不能拖垮整批
            failed.append(name)
            print("%-46s 处理失败，已跳过：%s: %s" % (name, type(exc).__name__, exc))
    print("trimmed %d/%d file(s)%s"
          % (changed, len(files), ("；失败 %d：%s" % (len(failed), ", ".join(failed))) if failed else ""))
    return 0 if not failed else 1


def cmd_aspect(a) -> int:
    html = open(a.html, encoding="utf-8").read()
    base = os.path.dirname(os.path.abspath(a.html))
    total = len(IMG_TAG.findall(re.sub(r"<!--.*?-->", "", html, flags=re.S)))
    # 优先用浏览器实测 JSON：里面有 object-fit，能正确跳过"横幅/裁切图"（裁切 ≠ 变形）
    fits = {}
    if a.shapes and os.path.isfile(a.shapes):
        for im in json.load(open(a.shapes, encoding="utf-8")).get("images", []):
            fits[im["src"]] = im.get("fit") or "fill"
    else:
        print("提示：未给 --shapes，只按 HTML 行内 style 检查；object-fit:cover 的横幅请用 --skip 排除")
    cands = inline_sizes(html)
    bad, n, skipped = [], 0, 0
    for src, w, h in cands:
        if any(s and s in src for s in a.skip) or fits.get(src) in ("cover", "contain", "scale-down"):
            skipped += 1
            continue
        path = os.path.normpath(os.path.join(base, src.replace("/", os.sep)))
        if not os.path.isfile(path):
            print("%-42s 文件缺失" % src); bad.append(src); continue
        im = Image.open(path)
        asp_src, asp_html = im.width / im.height, w / h
        diff = abs(asp_html / asp_src - 1) * 100
        n += 1
        print("%-42s %5gx%-5g html %.4f src %.4f  Δ%.2f%%%s"
              % (os.path.basename(src), w, h, asp_html, asp_src, diff,
                 "  <== 变形" if diff > a.tol else ""))
        if diff > a.tol:
            bad.append(src)
    if not n:
        print("checked 0 image(s); distorted %d; skipped %d (tol %.2f%%)" % (len(bad), skipped, a.tol))
        print("！<img> 共 %d 个，其中可审计（行内 style 同时写死 width/height）的 0 个"
              "；其余靠 CSS 类定尺寸或没写尺寸" % total)
        if bad:                             # 有可审计的图但文件缺失 → 仍然是失败
            return 1
        if total and not a.allow_empty:
            print("！此检查没有真正运行：aspect 一张图都没审计到，不能当成通过；"
                  "成品验收请改用 40_verify_pptx.py，或加 --allow-empty 明确接受空审计")
            return 2
        return 0
    print("checked %d image(s); distorted %d; skipped %d (tol %.2f%%; <img> 共 %d，可审计 %d)"
          % (n, len(bad), skipped, a.tol, total, len(cands)))
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trim")
    t.add_argument("--assets", default="assets")
    t.add_argument("--margin", type=int, default=10)
    t.add_argument("--backup", default="_work/pretrim")
    t.add_argument("--only", default=None)
    t.set_defaults(func=cmd_trim)
    s = sub.add_parser("aspect")
    s.add_argument("--html", required=True)
    s.add_argument("--tol", type=float, default=0.5)
    s.add_argument("--shapes", default=None, help="浏览器实测 JSON（可准确识别 object-fit:cover）")
    s.add_argument("--skip", default="", help="逗号分隔的路径片段，命中即跳过（如 banner）")
    s.add_argument("--allow-empty", action="store_true",
                   help="有 <img> 但一张都审计不到时也返回 0（默认返回 2：此检查没有真正运行）")
    s.set_defaults(func=cmd_aspect)
    a = ap.parse_args()
    a.skip = [x.strip() for x in (getattr(a, "skip", "") or "").split(",") if x.strip()]
    a.allow_empty = bool(getattr(a, "allow_empty", False))
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
