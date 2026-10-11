# -*- coding: utf-8 -*-
"""10_measure_gate_export.py —— 一次浏览器会话完成：DOM 实测 + 几何门禁 + 导出 PDF/预览 PNG。

前置：`edge_cdp.py start --port 9223`（不要用 headless，见 references/04-operations.md）。

    python 10_measure_gate_export.py --html poster.html --canvas 3402x4536 \
        --pdf-size 900x1200 --pdf poster.pdf --png _work/preview.png \
        --shapes _work/shapes.json --report _work/gate_report.json \
        --cdp http://127.0.0.1:9223 --js scripts/poster_measure.js

换模板/换类名时用 `--poster/--content/--column/--panel/--panel-body/--panel-head`
覆盖选择器（不必改 poster_measure.js）。

**"检查没跑成"一律判失败**：选择器匹配 0 个面板/栏、测不到任何文本、PDF 没导出、
mm 对照被跳过……都不算 PASS。确实不需要某项时显式加 `--allow-skip`（它会打印每一处跳过）。

退出码：0 = 门禁全过；1 = 有门禁失败（仍会写出 PDF/JSON）；2 = 环境/连接/输入错误。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys


for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = pathlib.Path(__file__).resolve().parent


def parse_size(txt: str):
    """'3402x4536' → (3402.0, 4536.0)。只接受 WxH（允许大写的 X、逗号、空格）。"""
    s = str(txt).lower().replace("×", "x").replace(",", "x").replace(" ", "")
    parts = s.split("x")
    if len(parts) != 2:
        raise ValueError(txt)
    return float(parts[0]), float(parts[1])


def size_or_die(txt: str, flag: str):
    try:
        w, h = parse_size(txt)
    except Exception:
        print("! %s 要写成 WxH（例如 3402x4536 或 900x1200）；收到：%r" % (flag, txt))
        return None
    if w <= 0 or h <= 0:
        print("! %s 必须是正数；收到：%r" % (flag, txt))
        return None
    return w, h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--canvas", default="3402x4536", help="CSS 画布 px，如 3402x4536")
    ap.add_argument("--pdf-size", default=None, help="PDF 物理尺寸 mm，如 900x1200")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--png", default=None)
    ap.add_argument("--png-dpi", type=float, default=150.0)
    ap.add_argument("--shapes", default="_work/shapes.json")
    ap.add_argument("--report", default="_work/gate_report.json")
    ap.add_argument("--cdp", default="http://127.0.0.1:9223")
    ap.add_argument("--js", default=str(HERE / "poster_measure.js"))
    ap.add_argument("--tol-overflow", type=float, default=2.0)
    ap.add_argument("--tol-spread", type=float, default=2.0)
    ap.add_argument("--tol-coledge", type=float, default=2.0,
                    help="栏组左右留白之差上限 px（栏区必须与页头同一边距）")
    ap.add_argument("--tol-canvas", type=float, default=1.0,
                    help="画布盒与 --canvas 的容差 px（DOM 是整数，允许小数画布）")
    ap.add_argument("--max-gap", type=float, default=40.0)
    ap.add_argument("--loose-slack", type=float, default=40.0, help="每格余量超过此值记 loose（留白）")
    ap.add_argument("--fail-loose", action="store_true", help="留白超阈值也判失败（空模板会因此 FAIL）")
    ap.add_argument("--bottom-margin-min", type=float, default=50.0)
    ap.add_argument("--tol-mm", type=float, default=1.5)
    ap.add_argument("--allow-skip", action="store_true",
                    help="把「某项检查被跳过」当成通过（默认：跳过 = 失败）")
    # 选择器覆盖：换模板/换类名时用，不必改 poster_measure.js
    ap.add_argument("--poster", default=None)
    ap.add_argument("--content", default=None)
    ap.add_argument("--column", default=None)
    ap.add_argument("--panel", default=None)
    ap.add_argument("--panel-body", default=None)
    ap.add_argument("--panel-head", default=None)
    args = ap.parse_args()

    cw_ch = size_or_die(args.canvas, "--canvas")
    if cw_ch is None:
        return 1
    CW, CH = int(round(cw_ch[0])), int(round(cw_ch[1]))
    pdf_mm = None
    if args.pdf_size:
        pdf_mm = size_or_die(args.pdf_size, "--pdf-size")
        if pdf_mm is None:
            return 1
    html = pathlib.Path(args.html)
    if not html.is_file():
        print("! HTML 文件不存在（--html）：%s" % html.resolve())
        return 2
    js_path = pathlib.Path(args.js)
    if not js_path.is_file():
        print("! 测量脚本不存在（--js）：%s" % js_path.resolve())
        return 2
    js = js_path.read_text(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:                                     # pragma: no cover
        print("缺少 playwright：pip install playwright  (%s)" % exc)
        return 2
    for p in (args.shapes, args.report, args.pdf, args.png):
        if p:
            os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    # 上一轮的 shapes.json 先挪走：测量失败时若留着旧文件，下游会**静默**按旧数据生成 PPTX
    if os.path.isfile(args.shapes):
        try:
            os.replace(args.shapes, args.shapes + ".prev")
            print("note: 上一轮 shapes.json 已改名为 %s.prev（避免误用旧数据）"
                  % os.path.basename(args.shapes))
        except Exception as exc:
            print("note: 无法移动旧 shapes.json（%s）" % exc)

    cfg = {}
    for key, val in (("poster", args.poster), ("content", args.content), ("columns", args.column),
                     ("panels", args.panel), ("panelBody", args.panel_body),
                     ("panelHead", args.panel_head)):
        if val:
            cfg[key] = val

    page_errors, data = [], None
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(args.cdp, timeout=60000)
        except Exception as exc:
            print("无法连接浏览器 %s：%s" % (args.cdp, str(exc).splitlines()[0][:120]))
            print("先运行： python edge_cdp.py start --port %s" % args.cdp.rsplit(":", 1)[-1])
            return 2
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        for p in list(ctx.pages):                  # 清掉上一轮留下的空白页
            try:
                if p.url in ("about:blank", ""):
                    p.close()
            except Exception:
                pass
        # 每轮都用**新标签页**：复用旧标签页时 Chromium 会报
        # "Page.printToPDF: Printing is not available"（实测）。
        page = ctx.new_page()
        page.set_default_timeout(120000)
        page.on("pageerror", lambda e: page_errors.append(str(e).splitlines()[0][:200]))
        pdf_written = False
        try:
            page.set_viewport_size({"width": CW, "height": CH})
            page.goto(html.resolve().as_uri(), wait_until="load")
            page.wait_for_timeout(900)
            if cfg:
                page.evaluate("c => { window.__APB_CFG__ = c; }", cfg)
            data = page.evaluate(js)
            # 画布以 --canvas 为准（JS 的 CFG.canvas 只是缺省值），下游 20_/40_ 都读这个字段
            data["canvas"] = {"w": CW, "h": CH}
            json.dump(data, open(args.shapes, "w", encoding="utf-8"), ensure_ascii=False)
            print("measured: %d rects, %d texts, %d images, %d bullets%s"
                  % (len(data["rects"]), len(data["texts"]), len(data["images"]), len(data["bullets"]),
                     ("  (另有 %d 个 li 用原生/文字项目符号，PPT 不复现)" % data["bulletsSkipped"])
                     if data.get("bulletsSkipped") else ""))
            print("   baseline ratio (实测) = %.3f" % data.get("baselineRatio", 0))
            cdp = ctx.new_cdp_session(page)
            if args.pdf and not pdf_mm:
                print("  ! 给了 --pdf 但没有 --pdf-size：无法导出 PDF（mm 尺寸是必需的）")
            if args.pdf and pdf_mm:
                res = cdp.send("Page.printToPDF", {
                    "paperWidth": pdf_mm[0] / 25.4, "paperHeight": pdf_mm[1] / 25.4,
                    "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0,
                    "printBackground": True, "scale": 1, "preferCSSPageSize": False})
                open(args.pdf, "wb").write(base64.b64decode(res["data"]))
                pdf_written = True
                print("pdf  -> %s (%.2f MB)" % (args.pdf, os.path.getsize(args.pdf) / 2 ** 20))
            if args.png:
                cdp.send("Emulation.setDeviceMetricsOverride",
                         {"width": CW, "height": CH,
                          "deviceScaleFactor": args.png_dpi / 96.0, "mobile": False})
                page.wait_for_timeout(400)
                shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
                open(args.png, "wb").write(base64.b64decode(shot["data"]))
                cdp.send("Emulation.clearDeviceMetricsOverride")
                print("png  -> %s (%.2f MB)" % (args.png, os.path.getsize(args.png) / 2 ** 20))
        except Exception as exc:
            print("! 测量/导出失败：%s: %s" % (type(exc).__name__, str(exc).splitlines()[0][:160]))
            return 2
        finally:
            # 关本轮页面之前**先**开一个空白页，否则浏览器会因"最后一个标签页关闭"而退出；
            # 同一 CDP 实例随后可继续跑下一份墙报，不必重新 start。
            try:
                spare = ctx.new_page()
                page.close()
                spare.goto("about:blank", wait_until="load", timeout=15000)
            except Exception as exc:
                print("note: 标签页收尾时出错（不影响结果）：%s" % str(exc)[:120])

    if data is None:
        print("! 没有拿到实测数据")
        return 2

    # ------------------------------ 门禁 ------------------------------
    gate = data["gate"]
    skips = []
    ok = True

    def chk(cond, msg):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("ok" if cond else "FAIL", msg))

    def skip(msg):
        nonlocal ok
        skips.append(msg)
        print("  [skip] %s%s" % (msg, "" if args.allow_skip else "   <== 跳过即失败（--allow-skip 可放行）"))
        if not args.allow_skip:
            ok = False

    print("GATE " + "-" * 52)
    # 1) 画布
    bw, bh = gate["bodyScroll"]
    chk(abs(bw - CW) <= args.tol_canvas and abs(bh - CH) <= args.tol_canvas,
        "canvas %dx%d (requested %d x %d)" % (bw, bh, CW, CH))
    # 2) 选择器：匹配 0 个 = 检查没跑成，判失败（旧版会静默"通过"）
    s = gate.get("selectors") or {}
    print("   selectors: poster=%r×%d content=%r×%d columns=%r×%d panels=%r×%d"
          % (s.get("poster"), s.get("nPoster", 0), s.get("content"), s.get("nContent", 0),
             s.get("columns"), s.get("nColumns", 0), s.get("panels"), s.get("nPanels", 0)))
    chk(s.get("nPoster", 0) > 0,
        "poster 选择器 %r 命中 .poster（0 个 → 用 --poster 指定）" % s.get("poster"))
    chk(s.get("nPanels", 0) > 0,
        "面板选择器 %r 命中 panel（0 个 → 用 --panel/--column 指定；检查没跑成不算通过）"
        % s.get("panels"))
    chk(s.get("nColumns", 0) > 0,
        "栏选择器 %r 命中 column（0 个 → 用 --column 指定；没有栏就没法验「栏底对齐」）"
        % s.get("columns"))
    if s.get("nPanels", 0):
        chk(not gate.get("panelsNoBody"),
            "%d 个面板没有 panel-body（panel-body 选择器 %r 命中 %d 个；不对就用 --panel-body 指定）"
            % (gate.get("panelsNoBody", 0), s.get("panelBody"), s.get("nPanelBodies", 0)))
    # 3) .poster 盒就是画布（body.scroll* 被固定高度"顶住"，量不出内容比画布小）
    pb = gate.get("poster")
    if pb:
        chk(abs(pb["w"] - CW) <= args.tol_canvas and abs(pb["h"] - CH) <= args.tol_canvas,
            ".poster 盒 %.0fx%.0f = 画布 %dx%d（画布尺寸由 .poster 决定，不能用 html/body 顶）"
            % (pb["w"], pb["h"], CW, CH))
    else:
        chk(False, ".poster 盒没量到（--poster 选择器不对）")
    if gate.get("content") is None:
        chk(False, ".content 内容区没量到（--content 选择器不对）")
    # 4) 面板溢出：四种口径取最大 —— body 自身溢出 / 子元素被压扁后的内容溢出 /
    #    .panel 自己（overflow:hidden）的 scrollHeight 溢出 / body 内最后一个子元素的实际底边
    def panel_over(p):
        return max(p["overlap"], p.get("childOverflow") or 0, p.get("panelOver") or 0)

    over = [p for p in gate["panels"] if panel_over(p) > args.tol_overflow]
    chk(not over, "%d 个面板溢出 (overflow): %s" % (len(gate["panels"]),
        [(p["i"] + 1, panel_over(p), p["title"][:22]) for p in over] or "none"))
    # 5) 栏底对齐
    bots = [c["lastBottom"] for c in gate["columns"]]
    if bots:
        chk(max(bots) - min(bots) <= args.tol_spread,
            "column bottoms %s (spread %d px)" % (bots, max(bots) - min(bots)))
    else:
        chk(False, "没有量到任何栏的底边（0 个 .col 含面板）")
    # 6) 栏内最大间隙
    gaps = [max(c["gaps"]) if c["gaps"] else 0 for c in gate["columns"]]
    if gaps:
        chk(max(gaps) <= args.max_gap, "max inter-panel gaps %s px" % gaps)
    # 7) 栏区左右留白
    ce = gate.get("colEdge")
    if ce is None:
        chk(False, "栏区左右留白没法量（没有 .col / .content）")
    else:
        chk(abs(ce["left"] - ce["right"]) <= args.tol_coledge,
            "column block margins L%d / R%d px (diff %d, tol %.0f)"
            % (ce["left"], ce["right"], abs(ce["left"] - ce["right"]), args.tol_coledge))
    # 8) 画布外/栏外内容（会被 overflow:hidden 静默裁掉）
    cl = gate.get("clip") or {"n": 0, "samples": []}
    chk(cl["n"] == 0, "画布内越界内容（横向/纵向超出 .poster，会被裁掉）%d 处 %s"
        % (cl["n"], cl["samples"] or ""))
    # 9) 祖先 transform（"2× 设计再 scale(0.5)"会让 PPT 整张缩小且门禁误判）
    chk(not gate.get("ancestorTransform"),
        "祖先 transform: %s（rect 坐标已被缩放，画布/栏高却是布局尺寸 → 门禁会误判）"
        % (gate.get("ancestorTransform") or "none"))
    # 10) 文本/图片覆盖：测到的东西太少 = 选择器不匹配，不是通过
    chk(data["texts"], "文本项 %d 个（0 个 = 选择器与这份 HTML 不匹配，PPTX 里不会有文字）"
        % len(data["texts"]))
    gi = gate.get("images") or {}
    explained = gi.get("nHidden", 0) + gi.get("nClipped", 0)
    chk(len(data["images"]) + explained >= gi.get("nTags", 0),
        "图片 <img> %d 个，测到 %d 个（隐藏 %d / 被裁 %d / 无 src %d）"
        % (gi.get("nTags", 0), len(data["images"]), gi.get("nHidden", 0),
           gi.get("nClipped", 0), gi.get("nNoSrc", 0)))
    # 11) 页面 JS 报错
    chk(not page_errors, "页面有 JS 报错（脚本运行异常）：%s" % (page_errors[:2] or "none"))
    # 12) 画布 ↔ 目标 mm
    if pdf_mm:
        mm = (bw / 96 * 25.4, bh / 96 * 25.4)
        chk(abs(mm[0] - pdf_mm[0]) <= args.tol_mm and abs(mm[1] - pdf_mm[1]) <= args.tol_mm,
            "canvas %.2f x %.2f mm vs %.0f x %.0f mm" % (mm[0], mm[1], pdf_mm[0], pdf_mm[1]))
    else:
        skip("画布 mm 对照（未给 --pdf-size）")
    # 13) 底边距
    bottom = max(bots) if bots else 0
    chk(CH - bottom >= args.bottom_margin_min,
        "bottom margin %.0f px (>= %.0f)" % (CH - bottom, args.bottom_margin_min))
    # 14) PDF
    if args.pdf:
        if not pdf_mm:
            skip("PDF 导出/校验（给了 --pdf 但没给 --pdf-size）")
        elif not pdf_written:
            chk(False, "PDF 没写出来：%s" % args.pdf)
        else:
            try:
                import pymupdf
                doc = pymupdf.open(args.pdf)
                r = doc[0].rect
                w, h = r.width / 72 * 25.4, r.height / 72 * 25.4
                chk(len(doc) == 1 and abs(w - pdf_mm[0]) <= 1.0 and abs(h - pdf_mm[1]) <= 1.0,
                    "pdf: %d page(s) %.2f x %.2f mm" % (len(doc), w, h))
            except Exception as exc:
                chk(False, "pdf 校验异常：%s" % exc)

    # 每格余量（留白）：格子内所有内容（文本/图片/其他形状）的最低点 vs 格子下沿。
    # 面板盒取自**实测**（gate.panels），不是按类名猜 —— 换模板/换类名时也成立。
    panel_boxes = [p["panel"] for p in gate["panels"] if p.get("panel")]
    head_boxes = [p["head"] for p in gate["panels"] if p.get("head")]

    def is_chrome(b):
        for q in panel_boxes + head_boxes:
            if (abs(b["x"] - q["x"]) < 1.5 and abs(b["y"] - q["y"]) < 1.5
                    and abs(b["w"] - q["w"]) < 1.5 and abs(b["h"] - q["h"]) < 1.5):
                return True
        return False

    items = [t["outer"] for t in data["texts"]] + [i["box"] for i in data["images"]]
    items += [r["box"] for r in data["rects"] if not is_chrome(r["box"])]
    col_left = sorted({round(b["x"]) for b in panel_boxes})   # 同栏各面板 x 相同 → 用它判定归属
    worst, loose = 0.0, 0
    for k, p in enumerate(panel_boxes):
        inside = [x for x in items if p["x"] - 2 <= x["x"] <= p["x"] + p["w"]
                  and p["y"] - 2 <= x["y"] <= p["y"] + p["h"]]
        bottom_i = max((x["y"] + x["h"] for x in inside), default=p["y"])
        slack = p["y"] + p["h"] - bottom_i
        worst = max(worst, slack)
        loose += 1 if slack > args.loose_slack else 0
        col = (min(range(len(col_left)), key=lambda i: abs(col_left[i] - p["x"])) + 1) if col_left else 0
        print("   panel %2d col%d top %4.0f h %4.0f slack %3.0f%s"
              % (k + 1, col, p["y"], p["h"], slack, "  <== loose" if slack > args.loose_slack else ""))
    print("   worst slack %.0f px | loose panel(s) %d (阈值 %.0f px)"
          % (worst, loose, args.loose_slack))
    if args.fail_loose and loose:
        ok = False
        print("  [FAIL] %d 个面板留白超过阈值（--fail-loose 已开启）" % loose)

    json.dump({"gate": gate, "ok": ok, "worst_slack": worst, "loose": loose,
               "canvas": [CW, CH], "n_panels": len(gate["panels"]), "skips": skips,
               "page_errors": page_errors, "selectors": s,
               "baseline_ratio": data.get("baselineRatio")},
              open(args.report, "w", encoding="utf-8"), ensure_ascii=False)
    if skips:
        print("   skips: %s" % "；".join(skips))
    print("GATE: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
