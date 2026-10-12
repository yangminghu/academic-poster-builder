# -*- coding: utf-8 -*-
"""60_pressure_matrix.py —— 压力矩阵：把"复杂情况"批量喂给整条流水线，逐项比对预期。

为什么需要它：这份技能包的规则都是从真实故障反推出来的。规则写完不等于代码真的做到了——
**要让代码自己证明**。本脚本在运行时**现场生成**一批中性样本（占位文案 + 程序生成的图片，
不含任何真实项目内容），逐个跑「测量 + 门禁 + PPTX(+ 一致性校验)」，把结果与**事先写好的预期**
逐项比对：

  * 该过的样本必须 PASS（真通过，不是"跳过了所以算通过"）；
  * 该被拦住的样本必须 FAIL，且**要给出可读的原因**、不许抛 traceback；
  * 任何时候都不允许出现"检查没跑成却报 PASS"（空匹配/缺部件/缺文件）。

用法：

    python scripts/60_pressure_matrix.py --list
    python scripts/60_pressure_matrix.py --quick          # 3 个冒烟样本（新机器第一件事）
    python scripts/60_pressure_matrix.py --round 4        # 第 4 轮
    python scripts/60_pressure_matrix.py --all            # 全量回归
    python scripts/60_pressure_matrix.py --only A2b,C1,D6

退出码：0 = 全部符合预期；1 = 有样本与预期不符。报告写到 `<work>/pressure_report.json`，
`--md <file>` 另写一份 Markdown 表格（可直接贴进交付说明）。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# --------------------------------------------------------------------------------------
# 样本登记表
# --------------------------------------------------------------------------------------
FIXTURES: "dict[str, dict]" = {}


def register(fid, round_, desc, expect, build, steps=("gate", "pptx")):
    """登记一个样本。expect 见 classify() 的判定口径。"""
    FIXTURES[fid] = {"id": fid, "round": round_, "desc": desc, "expect": expect,
                     "build": build, "steps": steps}


# --------------------------------------------------------------------------------------
# 中性样本的 HTML/CSS 骨架（实现 01-workflow §2 的版面契约；文案全部是占位符）
# --------------------------------------------------------------------------------------
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:%(W)dpx;height:%(H)dpx}
body{font-family:"Microsoft YaHei",sans-serif;background:#fff;color:#123}
.poster{width:%(W)dpx;height:%(H)dpx;overflow:hidden;background:#fff;
        display:flex;flex-direction:column}
.titleblock{margin:14px 112px 0;height:200px;padding:18px 24px;border-radius:10px;
        background:linear-gradient(100deg,#123a55,#0a6f8f);border-bottom:3px solid #06a}
.titleblock h1{font-size:76px;line-height:1.14;color:#fff}
.titleblock .authors{font-size:26px;line-height:1.3;color:#dfe9f2}
.metrics{margin:12px 112px 0;height:142px;display:flex;gap:24px}
.metric{flex:1;background:#f4f7fb;border-radius:12px;padding:14px 18px;
        display:flex;flex-direction:column;justify-content:center}
.metric .val{font-size:47px;line-height:1.1;color:#0a6f8f}
.metric .lab{font-size:21px;line-height:1.25;color:#456}
.metric .cmp{font-size:19px;line-height:1.25;color:#789}
.content{margin:12px 112px 0;height:%(CH)dpx;display:flex;gap:24px}
.col{display:flex;flex-direction:column;gap:20px}
.panel{flex:1 1 auto;background:#fff;border:1px solid #dde5ee;border-radius:10px;
       display:flex;flex-direction:column;overflow:hidden}
.panel-head{padding:8px 20px;background:#e8f1fd;border-bottom:3px solid #06a;
       display:flex;align-items:center;gap:14px}
.panel-head .num{width:44px;height:44px;min-width:44px;border-radius:8px;background:#0a6f8f;
       color:#fff;display:flex;align-items:center;justify-content:center;font-size:24px}
.panel-head h2{font-size:35px;line-height:1.08;color:#123}
.panel-head .en{font-size:19px;line-height:1.2;color:#567;display:block}
.panel-body{padding:11px 20px 13px;display:flex;flex-direction:column;gap:9px}
li{font-size:27px;line-height:1.34;padding-left:28px;position:relative;list-style:none}
li::before{content:"";position:absolute;left:0;top:9px;width:15px;height:15px;
       border-radius:5px;background:#0a6f8f}
p{font-size:27px;line-height:1.38}
.note{font-size:24px;line-height:1.32;background:#f2f7fe;border-left:8px solid #06a;
       padding:8px 12px}
figcaption{font-size:21px;line-height:1.28;color:#345}
img{display:block}
.refs{font-size:22px;line-height:1.3}
.concl{display:flex;flex-direction:column;gap:10px}
.concl .item{display:flex;gap:10px}
.concl .item .n{width:34px;height:34px;min-width:34px;border-radius:50%%;background:#0a6f8f;
       color:#fff;display:flex;align-items:center;justify-content:center;font-size:19px}
.concl .item > div:last-child{font-size:25px;line-height:1.3}
.pnum{position:absolute}
.pnum .pn-val{font-size:26px;line-height:1.2}
.pnum .pn-cn{font-size:18px;line-height:1.2}
%(EXTRA)s
"""


def page(w, h, content_h, body, extra_css="", title="压力样本"):
    return ("<!DOCTYPE html>\n<html lang=\"zh\">\n<head><meta charset=\"utf-8\">"
            "<title>%s</title><style>%s</style></head>\n<body>\n%s\n</body></html>\n"
            % (title, CSS % {"W": w, "H": h, "CH": content_h, "EXTRA": extra_css}, body))


def write_fixture(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text, encoding="utf-8")
    return path


def asset_rel(dirs) -> str:
    """样本目录 → 资源目录的相对路径（写成 HTML 里的 src，跨平台用 /）。"""
    return os.path.relpath(dirs["assets"], dirs["fix"]).replace(os.sep, "/")


def panel(n, title, body, en="", num="default"):
    head_num = ("<div class=\"num\">%s</div>" % num) if num == "default" else num
    return ("<section class=\"panel\"><div class=\"panel-head\">%s<h2>%s%s</h2></div>"
            "<div class=\"panel-body\">%s</div></section>"
            % (head_num, title, ("<span class=\"en\">%s</span>" % en) if en else "", body))


def bullets(items):
    return "<ul>" + "".join("<li>%s</li>" % x for x in items) + "</ul>"


def note(t):
    return "<div class=\"note\">%s</div>" % t


def figure(src, w, h, caption="", fit="", radius=0, pos=""):
    st = "width:%dpx;height:%dpx" % (w, h)
    if fit:
        st += ";object-fit:%s" % fit
    if pos:
        st += ";object-position:%s" % pos
    if radius:
        st += ";border-radius:%dpx" % radius
    return ("<figure><img src=\"%s\" style=\"%s\" alt=\"\">%s</figure>"
            % (src, st, ("<figcaption>%s</figcaption>" % caption) if caption else ""))


# 画布/版面默认值：90×120 cm，与模板同口径
W, H = 3402, 4536
TITLE_H, METRIC_H, MARGIN_TOP, BOTTOM = 200, 142, 12, 61
CH = H - (14 + TITLE_H + 12 + METRIC_H + MARGIN_TOP + BOTTOM)      # .content 高度 = 4095


def col_widths(n, content_w, gap=24):
    """按内容区宽度算栏宽：3 栏沿用模板比例，其余等宽（栏宽之和 + 间距 = 内容区宽）。"""
    if n <= 1:
        return [content_w]
    if n == 3:
        base = content_w - 2 * gap
        a = int(round(base * 1010.0 / 3178.0))
        return [a, base - 2 * a, a]
    base = content_w - (n - 1) * gap
    q = base // n
    out = [q] * n
    out[-1] = base - q * (n - 1)
    return out


def std_poster(cols, extra_css="", w=W, h=H, content_h=None, body_extra="",
               head_html=None, head_css_h=None, metrics=True, margin=None):
    """cols = [[panel_html, ...], ...] —— 每栏一个列表。页边距/栏宽按画布自动算。"""
    ch = CH if content_h is None else content_h
    margin = int(round(w * 112.0 / 3402)) if margin is None else margin
    ws = col_widths(len(cols), w - 2 * margin)
    colhtml = []
    for i, ps in enumerate(cols):
        colhtml.append("<div class=\"col\" style=\"width:%dpx;flex:0 0 %dpx;height:%dpx\">%s</div>"
                       % (ws[i], ws[i], ch, "".join(ps)))
    metrics_html = ("<div class=\"metrics\">"
                    + "".join("<div class=\"metric\"><div class=\"val\">[值]</div>"
                              "<div class=\"lab\">[指标名]</div><div class=\"cmp\">[对照]</div></div>"
                              for _ in range(4)) + "</div>") if metrics else ""
    head = head_html if head_html is not None else \
        ("<div class=\"titleblock\"><h1>[主标题]</h1>"
         "<div class=\"authors\">[作者1, 作者2, 通讯作者*]</div></div>")
    css = extra_css + ("\n.titleblock,.metrics,.content{margin-left:%dpx;margin-right:%dpx}"
                       % (margin, margin))
    if head_css_h:
        css += ".titleblock{height:%dpx;padding:0;background:none;border-bottom:0}" % head_css_h
    return page(w, h, ch, "<div class=\"poster\">%s%s<div class=\"content\">%s</div>%s</div>"
                % (head, metrics_html, "".join(colhtml), body_extra), css)


# --------------------------------------------------------------------------------------
# 资源：全部由程序生成（不含任何真实项目内容）
# --------------------------------------------------------------------------------------
def make_assets(d: pathlib.Path):
    from PIL import Image, ImageDraw
    d.mkdir(parents=True, exist_ok=True)

    def canvas(w, h, bg):
        im = Image.new("RGB", (w, h), bg)
        return im, ImageDraw.Draw(im)

    # 4:1 横幅（用来验证 object-fit:cover 的裁切）
    im, dr = canvas(1200, 300, (18, 58, 85))
    dr.ellipse([460, 60, 700, 300], fill=(240, 248, 255))
    dr.rectangle([0, 250, 1200, 300], fill=(10, 111, 143))
    im.save(d / "banner.png")

    # 普通图（带边框，便于墨迹检测）
    im, dr = canvas(800, 500, (255, 255, 255))
    for i in range(0, 800, 40):
        dr.line([(i, 0), (i, 500)], fill=(226, 235, 244))
    dr.rectangle([40, 40, 760, 460], outline=(10, 111, 143), width=4)
    dr.line([(40, 400), (300, 300), (560, 200), (760, 90)], fill=(200, 60, 60), width=6)
    im.save(d / "fig_wide.png")

    # 竖版图
    im, dr = canvas(600, 900, (255, 255, 255))
    dr.rectangle([30, 30, 570, 870], outline=(20, 80, 120), width=4)
    for k in range(6):
        dr.rectangle([70, 80 + k * 120, 530, 160 + k * 120], fill=(180, 210, 230))
    im.save(d / "fig_tall.png")

    # 不对称白边（左 7 / 右 99）——裁白边的靶子
    im, dr = canvas(800, 600, (255, 255, 255))
    dr.rectangle([7, 40, 701, 560], fill=(10, 111, 143))
    dr.rectangle([60, 120, 640, 480], fill=(255, 255, 255))
    im.save(d / "fig_margin.png")

    # 极小图 + 极端纵横比
    im, dr = canvas(200, 150, (255, 255, 255))
    dr.rectangle([10, 10, 190, 140], fill=(230, 120, 40))
    im.save(d / "fig_small.png")
    im, dr = canvas(1600, 120, (255, 255, 255))
    dr.rectangle([0, 20, 1600, 100], fill=(10, 111, 143))
    im.save(d / "fig_xwide.png")

    # 渐变/半透明底（测色值来源）
    im = Image.new("RGB", (700, 400), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    for x in range(700):
        dr.line([(x, 0), (x, 400)], fill=(int(240 - x * 0.2), int(246 - x * 0.1), 255))
    im.save(d / "fig_grad.png")

    # SVG（浏览器能渲染、OOXML 不能内嵌）
    (d / "vector.svg").write_text(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"400\" height=\"300\">"
        "<rect width=\"400\" height=\"300\" fill=\"#eef4fa\"/>"
        "<circle cx=\"200\" cy=\"150\" r=\"90\" fill=\"#0a6f8f\"/></svg>", encoding="utf-8")

    # 伪装成图片的坏文件（测"不要 traceback"）
    (d / "broken.png").write_bytes(b"not an image at all\n")


# --------------------------------------------------------------------------------------
# 样本定义（fid → builder）
# --------------------------------------------------------------------------------------
def _simple(fid_suffix, cols, **kw):
    return lambda dirs: write_fixture(dirs["fix"] / (fid_suffix + ".html"),
                                      std_poster(cols, **kw))


def three_col_ok(prefix="A1"):
    """一份"该过"的标准三栏墙报：每栏 2 个面板，内容明显小于面板高度。"""
    def b(dirs):
        a = asset_rel(dirs)
        cols = [
            [panel(1, "[面板一]", bullets(["[要点 %d]" % i for i in range(1, 4)])
                    + figure(a + "/fig_wide.png", 900, 563, "<b>图 1</b> [图注]")
                    + note("[本节小结]")),
             panel(4, "[面板四]", bullets(["[要点 %d]" % i for i in range(1, 5)]) + note("[小结]"))],
            [panel(2, "[面板二]", bullets(["[要点 %d]" % i for i in range(1, 6)])
                    + figure(a + "/fig_tall.png", 700, 1050, "<b>图 2</b> [图注]")
                    + note("[本节小结]")),
             panel(5, "[面板五]", bullets(["[要点 %d]" % i for i in range(1, 6)]) + note("[小结]"))],
            [panel(3, "[面板三]", bullets(["[要点 %d]" % i for i in range(1, 4)])
                    + figure(a + "/fig_small.png", 500, 375, "<b>图 3</b> [图注]")
                    + note("[本节小结]")),
             panel(6, "[面板六]",
                   "<div class=\"refs\"><div class=\"r\"><span class=\"n\">[1]</span>"
                   "<span>[文献条目占位]</span></div></div>"
                   "<div class=\"concl\">"
                   "<div class=\"item\"><div class=\"n\">1</div><div>[结论占位]</div></div>"
                   "<div class=\"item\"><div class=\"n\">2</div><div>[结论占位]</div></div></div>"
                   + note("[小结]"))],
        ]
        p = dirs["fix"] / (prefix + ".html")
        p.write_text(std_poster(cols), encoding="utf-8")
        return p
    return b


register("A1", 1, "标准三栏（该过）：该过的必须真 PASS",
         {"gate": "PASS", "pptx": 0}, three_col_ok("A1"))

register("A7", 1, "完全没有面板的空画布（该 FAIL，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["panel"], "pptx": None},
         _simple("A7", [[], [], []]))
# 上面 _simple 会用 3 个空栏 → 门禁测到 0 个面板；另外再给一个"连 .col 都没有"的样本
register("D7", 1, "没有 .col 栏容器（该 FAIL 或显式 skip，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["col"], "pptx": None},
         lambda dirs: write_fixture(
             dirs["fix"] / "D7.html",
             page(W, H, CH, "<div class=\"poster\"><div class=\"content\">"
                            + panel(1, "[面板一]", bullets(["[要点]"]))
                            + "</div></div>")))


def build_panelless_body(dirs):
    """有 .col 但 .col 里没有 .panel。"""
    p = dirs["fix"] / "D6.html"
    p.write_text(page(W, H, CH, "<div class=\"poster\"><div class=\"content\">"
                                "<div class=\"col\" style=\"width:1010px\"></div>"
                                "<div class=\"col\" style=\"width:1010px\"></div>"
                                "<div class=\"col\" style=\"width:1010px\"></div>"
                                "</div></div>"), encoding="utf-8")
    return p


register("D6", 1, "选择器匹配 0 个面板（该 FAIL：检查没跑成不能算 PASS）",
         {"gate": "FAIL", "gate_must": ["面板", "panel"], "pptx": None}, build_panelless_body)

register("D5", 1, ".panel 里没有 .panel-body（该 FAIL 或告警，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["panel"], "pptx": None},
         lambda dirs: write_fixture(
             dirs["fix"] / "D5.html",
             page(W, H, CH, "<div class=\"poster\"><div class=\"content\">"
                            "<div class=\"col\" style=\"width:1010px\">"
                            "<section class=\"panel\"><div class=\"panel-head\">"
                            "<div class=\"num\">1</div><h2>[面板一]</h2></div></div></section>"
                            "</div></div></div>")))

# ---------------- 第 2 轮：换类名 / 选择器可覆盖 ----------------
CUSTOM_CSS = """
.wrap{width:%dpx;height:%dpx;overflow:hidden;background:#fff}
.grid{display:flex;gap:24px;margin:12px 112px 0;height:%dpx}
.colc{display:flex;flex-direction:column;gap:20px}
.card{flex:1 1 auto;display:flex;flex-direction:column;background:#fff;
      border:1px solid #dde5ee;border-radius:10px;overflow:hidden}
.card-top{padding:8px 20px;background:#e8f1fd;border-bottom:3px solid #06a;font-size:35px}
.card-body{padding:11px 20px 13px;display:flex;flex-direction:column;gap:9px}
""" % (W, H, CH)

CUSTOM_ARGS = ["--poster", ".wrap", "--content", ".grid", "--column", ".colc",
               "--panel", ".card", "--panel-body", ".card-body", "--panel-head", ".card-top"]


def build_custom(dirs):
    """一份类名完全不同的墙报（.wrap/.grid/.colc/.card/.card-body）——验证选择器可覆盖。"""
    p = dirs["fix"] / "A2.html"
    cols = []
    for c, width in ((1, 1010), (2, 1110), (3, 1010)):
        cards = "".join(
            "<section class=\"card\"><div class=\"card-top\">[面板 %d]</div>"
            "<div class=\"card-body\">%s%s</div></section>"
            % (i, bullets(["[要点 %d]" % k for k in range(1, 4)]), note("[小结]"))
            for i in ((c - 1) * 2 + 1, (c - 1) * 2 + 2))
        cols.append("<div class=\"colc\" style=\"width:%dpx;flex:0 0 %dpx;height:%dpx\">%s</div>"
                    % (width, width, CH, cards))
    body = "<div class=\"wrap\"><div class=\"grid\">" + "".join(cols) + "</div></div>"
    return write_fixture(p, page(W, H, CH, body, extra_css=CUSTOM_CSS))


register("A2a", 2, "换类名、不给选择器（该 FAIL：必须说清选择器不匹配，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["选择器", "--panel"], "pptx": None}, build_custom)
register("A2b", 2, "换类名 + 选择器覆盖（该 PASS）",
         {"gate": "PASS", "pptx": None, "gate_args": CUSTOM_ARGS}, build_custom)

# ---------------- 第 3 轮：画布与尺寸 ----------------
register("B1", 3, "A0 841×1189 mm（3179×4494 px，该 PASS）",
         {"gate": "PASS", "pptx": 0, "canvas": "3179x4494", "pdf_size": "841x1189",
          "slide_mm": "841x1189"},
         _simple("B1", [[panel(1, "[面板一]", bullets(["[要点]"])), ],
                        [panel(2, "[面板二]", bullets(["[要点]"])), ],
                        [panel(3, "[面板三]", bullets(["[要点]"])), ]],
                 w=3179, h=4494, content_h=4494 - (14 + TITLE_H + 12 + METRIC_H + MARGIN_TOP + BOTTOM)))
register("B3", 3, "横版 1189×841 mm（4494×3179 px，该 PASS）",
         {"gate": "PASS", "pptx": None, "canvas": "4494x3179", "pdf_size": "1189x841"},
         _simple("B3", [[panel(1, "[面板一]", bullets(["[要点]"])), ],
                        [panel(2, "[面板二]", bullets(["[要点]"])), ],
                        [panel(3, "[面板三]", bullets(["[要点]"])), ]],
                 w=4494, h=3179, content_h=3179 - (14 + TITLE_H + 12 + METRIC_H + MARGIN_TOP + BOTTOM)))
register("B4", 3, "画布 px 与 --pdf-size mm 不符（该 FAIL，且说清哪个不符）",
         {"gate": "FAIL", "gate_must": ["mm"], "pptx": None, "pdf_size": "841x1189"},
         three_col_ok("B4"))
register("B5", 3, "--canvas 写错格式（该干净报错，不许 ValueError 栈）",
         {"gate": "FAIL", "gate_must": ["--canvas"], "pptx": None, "canvas": "3402*4536",
          "no_traceback": True}, three_col_ok("B5"))
register("B6", 3, "--pdf-size 写错格式（该干净报错，不许 ValueError 栈）",
         {"gate": "FAIL", "gate_must": ["--pdf-size"], "pptx": None, "pdf_size": "900:1200",
          "no_traceback": True}, three_col_ok("B6"))

# ---------------- 第 4 轮：图片与行内效果 ----------------
def build_cover(dirs):
    """4:1 的横幅被塞进 8.5:1 的显示框 —— 验证 object-fit:cover 真的裁切。"""
    a = asset_rel(dirs)
    head = ("<div class=\"titleblock\"><img src=\"%s/banner.png\" style=\"width:3178px;"
            "height:374px;object-fit:cover;object-position:50%% 50%%;border-radius:10px\" alt=\"\">"
            "</div>" % a)
    cols = [[panel(i, "[面板%d]" % i, bullets(["[要点]"]))] for i in range(1, 4)]
    p = dirs["fix"] / "C1.html"
    return write_fixture(p, std_poster(cols, head_html=head, head_css_h=374,
                                       content_h=H - (14 + 374 + 12 + METRIC_H + MARGIN_TOP + BOTTOM)))


register("C1", 4, "object-fit:cover 的 4:1 横幅放进 8.5:1 的框（该 PASS，且 PPT 里必须是裁切）",
         {"gate": "PASS", "pptx": 0, "verify": True}, build_cover)


def build_style_mix(dirs):
    a = asset_rel(dirs)
    css = """
.card2{background:linear-gradient(120deg,#eef4fa,#dbe9f6);border-radius:16px;padding:10px}
.rot{transform:rotate(-3deg)}
.vb{writing-mode:horizontal-tb}
.hsla{color:hsla(200,60%,30%,0.6)}
.under{text-decoration:underline}
.strike{text-decoration:line-through}
.upper{text-transform:uppercase}
.nowrap{white-space:nowrap}
.pre{white-space:pre;font-size:22px;line-height:1.3;background:#f6f8fa;padding:6px}
.sub-line{font-size:27px;line-height:1.34}
.op{opacity:0.55}
.hidden{visibility:hidden}
.gone{display:none}
.round-img{border-radius:24px}
"""
    body_cols = [
        [panel(1, "[面板一]",
               "<p class=\"sub-line\">[行内效果] H<sub>2</sub>O E=mc<sup>2</sup> "
               "<span class=\"under\">[下划线]</span> <span class=\"strike\">[删除线]</span> "
               "<span class=\"upper\">upper</span></p>"
               "<div class=\"card2\"><p class=\"hsla op\">[半透明文字在渐变底上]</p></div>"
               + figure(a + "/fig_wide.png", 820, 513, "<b>图 1</b> [图注]", radius=24)
               + note("[小结]"))],
        [panel(2, "[面板二]",
               "<p class=\"nowrap\">[不换行的一整行文字，很长很长很长很长很长很长]</p>"
               "<div class=\"pre\">[预格式]\n  第二行\t带制表符</div>"
               "<p class=\"hidden\">[隐藏文字不该出现在 PPT]</p>"
               "<p class=\"gone\">[display:none 不该出现]</p>"
               + figure(a + "/fig_tall.png", 500, 750, "<b>图 2</b> [图注]")
               + note("[小结]"))],
        [panel(3, "[面板三]",
               "<figure><img class=\"rot round-img\" src=\"%s/fig_small.png\" "
               "style=\"width:300px;height:225px;border-radius:24px;transform:rotate(-3deg)\" "
               "alt=\"\"><figcaption><b>图 3</b> [旋转+圆角]</figcaption></figure>"
               % a + note("[小结]"))],
    ]
    p = dirs["fix"] / "C2.html"
    p.write_text(std_poster(body_cols, extra_css=css), encoding="utf-8")
    return p


register("C2", 5, "上下标/下划线/删除线/大小写/半透明/隐藏/nowrap/pre/旋转/圆角 混排",
         {"gate": "PASS", "pptx": 0, "verify": True}, build_style_mix)


def build_black_theme(dirs):
    """深色配色：黑色填充 + 黑色单边边框 + 黑色项目符号 + oklch 背景。
    旧版把"解析不到颜色"和"黑色"都当 0，再用真值判断 → 这些黑色会被静默丢掉。
    注意：必须用 **CFG.rects 里的选择器**（.note / .panel-head / li::before），
    随便给个 <div> 加背景不会被画成形状——那是另一个（已知的）设计边界。"""
    css = """
.note.black{background:#000;border-left:8px solid #000;color:#fff}
.note.ok{background:oklch(0.75 0.15 60);border-left:8px solid oklch(0.75 0.15 60)}
li::before{background:#000}
"""
    body_cols = [
        [panel(1, "[面板一]", bullets(["[黑色项目符号]"])
               + "<div class=\"note black\">[黑底白字小结：fill=0、border-left=0]</div>")],
        [panel(2, "[面板二]", "<div class=\"note ok\">[oklch 背景色小结]</div>")],
        [panel(3, "[面板三]", bullets(["[要点]"]))],
    ]
    p = dirs["fix"] / "C9.html"
    return write_fixture(p, std_poster(body_cols, extra_css=css))


register("C9", 5, "深色配色（黑色填充/边框/项目符号 + oklch 颜色）：黑色不能与「没有颜色」混为一谈",
         {"gate": "PASS", "pptx": 0, "verify": True, "black_present": True}, build_black_theme)


def build_invisible(dirs):
    css = ".sr-only{opacity:0}.vis-h{visibility:hidden}.gone{display:none}"
    body_cols = [
        [panel(1, "[面板一]", "<p class=\"sr-only\">[不可见文字 opacity0]</p>"
               "<p class=\"vis-h\">[不可见文字 visibility]</p>"
               "<p class=\"gone\">[不可见文字 display]</p>"
               "<p>[可见文字]</p>" + note("[小结]"))],
        [panel(2, "[面板二]", bullets(["[要点]"]))],
        [panel(3, "[面板三]", bullets(["[要点]"]))],
    ]
    p = dirs["fix"] / "C10.html"
    return write_fixture(p, std_poster(body_cols, extra_css=css))


register("C10", 5, "opacity:0 / visibility:hidden / display:none 的文字不得进 PPTX",
         {"gate": "PASS", "pptx": 0, "verify": True,
          "shapes_exclude": ["不可见文字"], "shapes_include": ["可见文字"]}, build_invisible)


def build_inline_text(dirs):
    """文字只存在于行内子元素里（div > span），不能整行消失。"""
    body_cols = [
        [panel(1, "[面板一]",
               "<div class=\"meta\"><span>[行内文字甲]</span> <span>·</span> "
               "<span>[行内文字乙]</span></div>"
               "<div class=\"row\"><span>▸</span><span>[图标+标签行]</span></div>"
               + note("[小结]"))],
        [panel(2, "[面板二]", bullets(["[要点]"]))],
        [panel(3, "[面板三]", bullets(["[要点]"]))],
    ]
    p = dirs["fix"] / "C11.html"
    return write_fixture(p, std_poster(body_cols))


register("C11", 5, "只用行内子元素写的文本行（div>span）不能整行消失",
         {"gate": "PASS", "pptx": 0, "verify": True,
          "shapes_include": ["行内文字甲", "行内文字乙", "图标+标签行"]}, build_inline_text)

# ---------------- 第 6 轮：边框/嵌套/项目符号 ----------------
def build_borders(dirs):
    css = """
.b-top{border-top:6px solid #06a}
.b-right{border-right:6px solid #a60}
.b-bottom{border-bottom:6px solid #0a6}
.b-left{border-left:6px solid #60a}
.b-dash{border:3px dashed #06a}
.hollow li::before{content:"";background:transparent;border:3px solid #06a;width:12px;height:12px;
      border-radius:6px}
.native li{list-style:disc;margin-left:24px}
.native li::before{content:none}
.ind dd{margin-left:40px}
"""
    body_cols = [
        [panel(1, "[面板一]",
               "<div class=\"b-top\">[只有上边框]</div>"
               "<div class=\"b-right\">[只有右边框]</div>"
               "<div class=\"b-bottom\">[只有下边框]</div>"
               "<div class=\"b-left\">[只有左边框]</div>"
               "<div class=\"b-dash\">[虚线四边]</div>" + note("[小结]"))],
        [panel(2, "[面板二]",
               "<ul class=\"hollow\"><li>[空心项目符号 1]</li><li>[空心项目符号 2]</li></ul>"
               "<ul class=\"native\"><li>[原生圆点 1]</li><li>[原生圆点 2]</li></ul>"
               "<dl class=\"ind\"><dt>[术语]</dt><dd>[缩进的定义文字，不能顶到左边]</dd></dl>"
               "<ol style=\"margin-left:36px\"><li>[有序列表 1]</li><li>[有序列表 2]</li></ol>"
               + note("[小结]"))],
        [panel(3, "[面板三]",
               "<div style=\"position:relative;height:200px;background:#f6f8fa;border-radius:20px;"
               "overflow:hidden\"><div style=\"position:absolute;left:0;top:0;width:120px;"
               "height:40px;background:#0a6f8f\"></div>"
               "<div style=\"position:absolute;left:6px;top:6px;font-size:20px\">[贴角子元素]</div>"
               "</div>" + note("[小结]"))],
    ]
    p = dirs["fix"] / "C3.html"
    p.write_text(std_poster(body_cols, extra_css=css), encoding="utf-8")
    return p


register("C3", 6, "单边边框/虚线/空心与原生项目符号/缩进/圆角裁切+贴角子元素",
         {"gate": "PASS", "pptx": 0, "verify": True}, build_borders)


def build_dup_image(dirs):
    a = asset_rel(dirs)
    f = figure(a + "/fig_wide.png", 640, 400, "<b>图 1</b> [同一张图被引用两次]")
    body_cols = [[panel(1, "[面板一]", f + note("[小结]"))],
                 [panel(2, "[面板二]", f + note("[小结]"))],
                 [panel(3, "[面板三]", f + note("[小结]"))]]
    p = dirs["fix"] / "C4.html"
    p.write_text(std_poster(body_cols), encoding="utf-8")
    return p


register("C4", 7, "同一张图片被引用多次（形状名必须去重；验收要按名字配对）",
         {"gate": "PASS", "pptx": 0, "verify": True}, build_dup_image)


def build_svg(dirs):
    a = asset_rel(dirs)
    body_cols = [[panel(1, "[面板一]", figure(a + "/vector.svg", 400, 300, "<b>图 1</b> [SVG]")
                        + note("[小结]"))],
                 [panel(2, "[面板二]", bullets(["[要点]"]))],
                 [panel(3, "[面板三]", bullets(["[要点]"]))]]
    p = dirs["fix"] / "C5.html"
    p.write_text(std_poster(body_cols), encoding="utf-8")
    return p


register("C5", 7, "SVG 图片（OOXML 不能内嵌，该明确报错/跳过，不许 traceback）",
         {"gate": "PASS", "pptx": 1, "pptx_must": ["SVG", "svg"], "no_traceback": True}, build_svg)


def build_broken(dirs):
    a = asset_rel(dirs)
    body_cols = [[panel(1, "[面板一]", figure(a + "/broken.png", 400, 300, "<b>图 1</b> [坏文件]")
                        + note("[小结]"))],
                 [panel(2, "[面板二]", bullets(["[要点]"]))],
                 [panel(3, "[面板三]", bullets(["[要点]"]))]]
    p = dirs["fix"] / "C6.html"
    p.write_text(std_poster(body_cols), encoding="utf-8")
    return p


register("C6", 7, "坏图片文件（该干净失败：退出码 1 + 可读原因，不许 traceback）",
         {"gate": "PASS", "pptx": 1, "no_traceback": True}, build_broken)


def build_missing(dirs):
    body_cols = [[panel(1, "[面板一]", figure("assets/does_not_exist.png", 400, 300,
                                              "<b>图 1</b> [缺图]") + note("[小结]"))],
                 [panel(2, "[面板二]", bullets(["[要点]"]))],
                 [panel(3, "[面板三]", bullets(["[要点]"]))]]
    p = dirs["fix"] / "C7.html"
    p.write_text(std_poster(body_cols), encoding="utf-8")
    return p


register("C7", 7, "图片文件不存在（该退出码 1 且不产出 PPTX）",
         {"gate": "PASS", "pptx": 1, "pptx_must": ["图片缺失"]}, build_missing)


def build_space_name(dirs):
    from PIL import Image
    src = dirs["assets"] / "with space.png"
    Image.open(dirs["assets"] / "fig_wide.png").save(src)
    a = asset_rel(dirs)
    body_cols = [[panel(1, "[面板一]", figure(a + "/with space.png", 640, 400, "<b>图 1</b> [空格]")
                        + note("[小结]"))],
                 [panel(2, "[面板二]", bullets(["[要点]"]))],
                 [panel(3, "[面板三]", bullets(["[要点]"]))]]
    p = dirs["fix"] / "C8.html"
    p.write_text(std_poster(body_cols), encoding="utf-8")
    return p


register("C8", 7, "图片文件名含空格（该正常通过，不许找不到文件）",
         {"gate": "PASS", "pptx": 0, "verify": True}, build_space_name)

# ---------------- 第 8 轮：门禁假通过攻击 ----------------
def build_small_poster(dirs):
    """poster 元素只有画布的 80%（旧版门禁只看 body.scroll*，会误判 PASS）。"""
    p = dirs["fix"] / "D1.html"
    html = std_poster([[panel(1, "[面板一]", bullets(["[要点]"]))],
                       [panel(2, "[面板二]", bullets(["[要点]"]))],
                       [panel(3, "[面板三]", bullets(["[要点]"]))]])
    html = html.replace(".poster{width:%dpx;height:%dpx" % (W, H),
                        ".poster{width:%dpx;height:%dpx" % (int(W * 0.8), int(H * 0.8)))
    p.write_text(html, encoding="utf-8")
    return p


register("D1", 8, "内容只占画布 80%（该 FAIL：画布盒也必须量）",
         {"gate": "FAIL", "gate_must": ["poster"], "pptx": None}, build_small_poster)


def build_hclip(dirs):
    """一个 5000 px 宽的元素被 .poster 的 overflow:hidden 裁掉（该 FAIL）。"""
    p = dirs["fix"] / "D2.html"
    html = std_poster([[panel(1, "[面板一]", "<div style=\"width:5000px\">[超宽元素]</div>"
                               + note("[小结]"))],
                       [panel(2, "[面板二]", bullets(["[要点]"]))],
                       [panel(3, "[面板三]", bullets(["[要点]"]))]])
    p.write_text(html, encoding="utf-8")
    return p


register("D2", 8, "栏内元素横向溢出被裁（该 FAIL：横向裁切也要报）",
         {"gate": "FAIL", "gate_must": ["横向"], "pptx": None}, build_hclip)


def build_abs_overflow(dirs):
    """绝对定位的内容压到画布外（该 FAIL）。"""
    p = dirs["fix"] / "D3.html"
    html = std_poster([[panel(1, "[面板一]", bullets(["[要点]"]))],
                       [panel(2, "[面板二]", bullets(["[要点]"]))],
                       [panel(3, "[面板三]", bullets(["[要点]"]))]],
                      body_extra="<div style=\"position:absolute;left:0;top:4520px;width:600px;"
                                 "height:200px;background:#0a6f8f\">[画布外内容]</div>")
    html = html.replace(".poster{width", ".poster{position:relative;width", 1)
    p.write_text(html, encoding="utf-8")
    return p


register("D3", 8, "面板外/画布外的绝对定位内容（该 FAIL）",
         {"gate": "FAIL", "gate_must": ["越界", "画布"], "pptx": None}, build_abs_overflow)


def build_js_error(dirs):
    p = dirs["fix"] / "D3b.html"
    html = std_poster([[panel(1, "[面板一]", bullets(["[要点]"]))],
                       [panel(2, "[面板二]", bullets(["[要点]"]))],
                       [panel(3, "[面板三]", bullets(["[要点]"]))]])
    html = html.replace("</body>", "<script>undefinedFunctionCall();</script></body>")
    p.write_text(html, encoding="utf-8")
    return p


register("D3b", 8, "页面有 JS 报错（该 FAIL 或至少显式告警）",
         {"gate": "FAIL", "gate_must": ["JS", "脚本"], "pptx": None}, build_js_error)


def build_overflow_panel(dirs):
    """面板内容远超面板高度（该 FAIL：溢出必须抓到）。"""
    p = dirs["fix"] / "D4.html"
    long_txt = "".join("<p>[很长的正文 %d]</p>" % i for i in range(1, 160))
    html = std_poster([[panel(1, "[面板一]", long_txt)],
                       [panel(2, "[面板二]", bullets(["[要点]"]))],
                       [panel(3, "[面板三]", bullets(["[要点]"]))]])
    p.write_text(html, encoding="utf-8")
    return p


register("D4", 8, "面板内容溢出（该 FAIL：溢出必须被抓住）",
         {"gate": "FAIL", "gate_must": ["溢出", "overflow"], "pptx": None}, build_overflow_panel)


def build_loose(dirs):
    p = dirs["fix"] / "D5b.html"
    p.write_text(std_poster([[panel(1, "[面板一]", "<p>[一行字]</p>")],
                             [panel(2, "[面板二]", "<p>[一行字]</p>")],
                             [panel(3, "[面板三]", "<p>[一行字]</p>")]],
                            content_h=CH), encoding="utf-8")
    return p


register("D5b", 8, "面板大面积留白（--fail-loose 下该 FAIL）",
         {"gate": "FAIL", "gate_must": ["留白", "loose"], "pptx": None, "gate_args": ["--fail-loose"]},
         build_loose)


def build_no_poster(dirs):
    """没有 .poster 根元素（面板直接放在 body 的 .content 里）。"""
    cols = "".join("<div class=\"col\" style=\"width:1010px;height:%dpx\">%s</div>"
                   % (CH, panel(i, "[面板%d]" % i, bullets(["[要点]"]))) for i in (1, 2, 3))
    return write_fixture(dirs["fix"] / "D8.html",
                         page(W, H, CH, "<div class=\"content\">%s</div>" % cols))


register("D8", 8, "没有 .poster 根元素（该 FAIL：说清用 --poster 指定，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["--poster"], "pptx": None, "no_traceback": True},
         build_no_poster)

# ---------------- 第 9 轮：版式变体 ----------------
def build_single_col(dirs):
    a = asset_rel(dirs)
    cols = [[panel(1, "[面板一]", bullets(["[要点 1]", "[要点 2]", "[要点 3]"])
             + figure(a + "/fig_wide.png", 1800, 1125, "<b>图 1</b> [图注]")
             + note("[小结]"))]]
    return write_fixture(dirs["fix"] / "A3.html", std_poster(cols))


register("A3", 9, "单栏全宽（该 PASS）",
         {"gate": "PASS", "pptx": 0}, build_single_col)
register("A4", 9, "四栏（该 PASS）",
         {"gate": "PASS", "pptx": 0},
         _simple("A4", [[panel(1, "[面板一]", bullets(["[要点]"]))],
                        [panel(2, "[面板二]", bullets(["[要点]"]))],
                        [panel(3, "[面板三]", bullets(["[要点]"]))],
                        [panel(4, "[面板四]", bullets(["[要点]"]))]]))
register("A5", 9, "纯文字、零图片（该 PASS）",
         {"gate": "PASS", "pptx": 0},
         _simple("A5", [[panel(1, "[面板一]", bullets(["[要点 %d]" % i for i in range(1, 6)]))],
                        [panel(2, "[面板二]", bullets(["[要点 %d]" % i for i in range(1, 6)]))],
                        [panel(3, "[面板三]", bullets(["[要点 %d]" % i for i in range(1, 6)]))]]))
register("A6", 9, "24 面板（该 PASS，规模压力）",
         {"gate": "PASS", "pptx": 0},
         _simple("A6", [[panel(i, "[面板 %d]" % i, bullets(["[要点 %d]" % k for k in range(1, 4)]))
                         for i in range(1, 9)],
                        [panel(i, "[面板 %d]" % i, bullets(["[要点 %d]" % k for k in range(1, 4)]))
                         for i in range(9, 17)],
                        [panel(i, "[面板 %d]" % i, bullets(["[要点 %d]" % k for k in range(1, 4)]))
                         for i in range(17, 25)]]))

# ---------------- 第 10 轮：CLI / 错误输入 / 交付 ----------------
register("E1", 10, "HTML 路径不存在（该干净报错，不许 traceback）",
         {"gate": "FAIL", "gate_must": ["html"], "pptx": None, "no_traceback": True,
          "html_override": "_no_such_file_.html"}, three_col_ok("E1"))
register("E2", 10, "shapes.json 被截断（20_ 该干净报错，不许 JSONDecodeError 栈）",
         {"gate": "PASS", "pptx": 1, "pptx_must": ["JSON", "shapes"], "no_traceback": True,
          "corrupt_shapes": True}, three_col_ok("E2"))
register("E3", 10, "--slide-mm 与画布不符（20_ 该告警并说明会被裁切）",
         {"gate": "PASS", "pptx": 0, "pptx_must": ["裁切", "画布"], "slide_mm": "841x1189"},
         three_col_ok("E3"))
register("E4", 10, "指定了不存在的字体（该告警，不许静默）",
         {"gate": "PASS", "pptx": 0, "font": "NoSuchFont-XYZ"}, three_col_ok("E4"))


def build_align(dirs):
    """两端对齐 / 右对齐：不能都掉进"右对齐"分支（旧版 justify 会被右对齐）。"""
    css = ".just p{text-align:justify}.right p{text-align:end}.mid p{text-align:center}"
    body_cols = [
        [panel(1, "[面板一]", "<div class=\"just\"><p>[两端对齐的正文，"
               "用来验证 text-align:justify 不会被当成右对齐输出。]</p></div>"
               "<div class=\"right\"><p>[右对齐文字]</p></div>"
               "<div class=\"mid\"><p>[居中文字]</p></div>" + note("[小结]"))],
        [panel(2, "[面板二]", bullets(["[要点]"]))],
        [panel(3, "[面板三]", bullets(["[要点]"]))],
    ]
    return write_fixture(dirs["fix"] / "F1.html", std_poster(body_cols, extra_css=css))


register("F1", 10, "text-align: justify / end / center 混排（该 PASS，且 justify 不能变右对齐）",
         {"gate": "PASS", "pptx": 0, "verify": True,
          "shapes_include": ["两端对齐的正文"]}, build_align)

QUICK = ["A1", "B1", "A2b"]


# --------------------------------------------------------------------------------------
# 运行器
# --------------------------------------------------------------------------------------
def run(cmd, cwd=None):
    # **故意不设 PYTHONIOENCODING**：Windows 中文环境的控制台编码是 GBK，
    # 脚本必须自己扛住（统一把 stdout/stderr 重设成 utf-8），否则打印 "−/≈/✓" 之类字符就
    # UnicodeEncodeError 崩掉——这是实测踩过的真实故障，这里让它变成常驻回归测试。
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    env["PYTHONUTF8"] = "0"
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=cwd, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def find_kit():
    cli = os.environ.get("LIBREOFFICE_KIT_CLI")
    if cli and os.path.isfile(cli):
        return cli
    return None


def build_fixture(fid, work):
    fx = FIXTURES[fid]
    fdir = work / "fixtures" / fid
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir(parents=True)
    dirs = {"fix": fdir, "assets": work / "assets", "work": work}
    (work / "assets").mkdir(parents=True, exist_ok=True)
    if not (work / "assets" / "fig_wide.png").is_file():
        make_assets(work / "assets")
    html = fx["build"](dirs)
    return fdir, pathlib.Path(html)


def classify(fid, gate_rc, gate_out, pptx_rc, pptx_out, verify, shapes_path=None):
    """把实测与预期比对，返回 (是否符合预期, 失败原因列表, 观察)。"""
    fx, exp = FIXTURES[fid], FIXTURES[fid]["expect"]
    fails, obs = [], {}

    gate_pass = (gate_rc == 0)
    obs["gate_rc"] = gate_rc
    obs["gate"] = "PASS" if gate_pass else "FAIL"
    if exp.get("gate") == "PASS" and not gate_pass:
        fails.append("预期 GATE PASS，实际 FAIL")
    if exp.get("gate") == "FAIL" and gate_pass:
        fails.append("预期 GATE FAIL，实际 PASS（漏检/假通过）")
    for key in exp.get("gate_must", []):
        if key not in gate_out:
            fails.append("门禁输出里没有出现关键说明 %r" % key)
    if exp.get("no_traceback") and "Traceback" in gate_out:
        fails.append("门禁抛了 Python traceback")
    if "Traceback" in gate_out:
        fails.append("门禁抛了 Python traceback")

    if exp.get("pptx") is not None:
        if exp["pptx"] == 0 and pptx_rc != 0:
            fails.append("预期 20_html2pptx 退出码 0，实际 %s" % pptx_rc)
        if exp["pptx"] == 1 and pptx_rc == 0:
            fails.append("预期 20_html2pptx 退出码 1，实际 0（该失败却成功了）")
        for key in exp.get("pptx_must", []):
            if key not in pptx_out:
                fails.append("20_ 输出里没有出现关键说明 %r" % key)
    if "Traceback" in pptx_out:
        fails.append("20_html2pptx 抛了 Python traceback")
    obs["pptx_rc"] = pptx_rc
    obs["verify"] = verify
    if exp.get("verify") and verify is not None and "PASS" not in str(verify).upper():
        fails.append("预期 VERIFY PASS，实际 %s" % verify[:60])

    # 数据级断言：直接看 shapes.json —— 验证"看不见的东西确实没进 PPT"、
    # "黑色确实被当颜色采集"（这类问题在版面门禁里是看不见的）
    want_shapes = (exp.get("shapes_exclude") or exp.get("shapes_include")
                   or exp.get("black_present"))
    if want_shapes:
        sh = None
        if shapes_path and os.path.isfile(shapes_path):
            try:
                sh = json.loads(pathlib.Path(shapes_path).read_text(encoding="utf-8"))
            except Exception as exc:
                fails.append("shapes.json 读不出来：%s" % exc)
        if sh is None:
            fails.append("预期有 shapes.json 可断言，但没读到")
        else:
            blob = "".join("".join(r.get("t", "") for r in t.get("runs", []))
                           for t in sh.get("texts", []))
            for s in exp.get("shapes_exclude", []):
                if s in blob:
                    fails.append("不该进 PPT 的文字出现了：%r" % s)
            for s in exp.get("shapes_include", []):
                if s not in blob:
                    fails.append("PPT 里缺少文字：%r（整行/整段丢失）" % s)
            if exp.get("black_present"):
                rects = sh.get("rects") or []
                if not any(r.get("fill") == 0 for r in rects):
                    fails.append("黑色填充没被采集为颜色（fill 应为 0，不是 -1）")
                if not any(0 in (r.get("bc") or []) for r in rects):
                    fails.append("黑色边框没被采集为颜色")
                if not any((b.get("fill") == 0) for b in (sh.get("bullets") or [])):
                    fails.append("黑色项目符号没被采集为颜色")
                if not any((r.get("fill") or -1) > 0 for r in rects):
                    fails.append("oklch/非 rgb() 背景色没被解析成 sRGB 实色（应为 fill>0 而不是 -1）")
    return (not fails), fails, obs


def run_one(fid, work, port, to_pdf=True, kit=None, node=None, keep=False):
    fdir, html = build_fixture(fid, work)
    exp = FIXTURES[fid]["expect"]
    out = fdir / "out"
    out.mkdir(exist_ok=True)
    canvas = exp.get("canvas", "3402x4536")
    try:                                  # 不给 --pdf-size 时按画布换算，让 mm 对照也真的跑起来
        pdf_size = exp.get("pdf_size") or canvas_mm(canvas)
    except Exception:
        pdf_size = exp.get("pdf_size")
    if exp.get("html_override"):
        html = fdir / exp["html_override"]
    pdf = out / "poster.pdf"
    png = out / "preview.png"
    shapes = out / "shapes.json"
    args = [sys.executable, str(HERE / "10_measure_gate_export.py"), "--html", str(html),
            "--canvas", canvas, "--shapes", str(shapes), "--report", str(out / "gate.json"),
            "--cdp", "http://127.0.0.1:%d" % port, "--js", str(HERE / "poster_measure.js"),
            "--pdf", str(pdf), "--png", str(png)]
    if pdf_size:
        args += ["--pdf-size", pdf_size]
    args += exp.get("gate_args", [])
    gate_rc, gate_out = run(args, cwd=str(fdir))
    pptx_rc, pptx_out, verify = None, "", None
    if exp.get("pptx") is not None and (gate_rc == 0 or exp.get("pptx_force")):
        if exp.get("corrupt_shapes"):
            txt = shapes.read_text(encoding="utf-8")
            shapes.write_text(txt[: len(txt) // 2], encoding="utf-8")
        pptx = out / "poster.pptx"
        p_args = [sys.executable, str(HERE / "20_html2pptx.py"), "--shapes", str(shapes),
                  "--out", str(pptx), "--html", str(html),
                  "--font", exp.get("font", "Microsoft YaHei"),
                  "--slide-mm", exp.get("slide_mm", pdf_size or canvas_mm(canvas))]
        pptx_rc, pptx_out = run(p_args, cwd=str(fdir))
        if pptx_rc == 0 and to_pdf and kit and node and exp.get("verify"):
            vpdf = out / "pptx.pdf"
            run([node, kit, "convert", "--input", str(pptx), "--output", str(vpdf)], cwd=str(fdir))
            if vpdf.is_file():
                v_rc, v_out = run([sys.executable, str(HERE / "40_verify_pptx.py"),
                                   "--pptx", str(pptx), "--shapes", str(shapes), "--html", str(html),
                                   "--pdf-preview", str(png), "--pptx-pdf", str(vpdf),
                                   "--pdf-size", pdf_size or canvas_mm(canvas),
                                   "--work", str(out)], cwd=str(fdir))
                verify = [l for l in v_out.strip().splitlines() if l.strip()][-1]
            else:
                verify = "convert failed"
    ok, fails, obs = classify(fid, gate_rc, gate_out, pptx_rc, pptx_out, verify, shapes)
    return {"id": fid, "round": FIXTURES[fid]["round"], "desc": FIXTURES[fid]["desc"],
            "ok": ok, "fails": fails, "obs": obs,
            "gate_tail": [l for l in gate_out.strip().splitlines() if l.strip()][-14:],
            "pptx_tail": [l for l in pptx_out.strip().splitlines() if l.strip()][-6:],
            "fixture": str(fdir)}


def canvas_mm(canvas):
    w, h = (float(x) for x in canvas.lower().split("x"))
    return "%.0fx%.0f" % (w / 96 * 25.4, h / 96 * 25.4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出全部样本")
    ap.add_argument("--quick", action="store_true", help="3 个冒烟样本")
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--only", default=None, help="逗号分隔的样本 id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--port", type=int, default=9223)
    ap.add_argument("--work", default="_work/_pressure")
    ap.add_argument("--libreoffice-cli", default=None)
    ap.add_argument("--node", default=None)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--md", default=None, help="另写一份 Markdown 报告")
    ap.add_argument("--keep-browser", action="store_true")
    a = ap.parse_args()

    if a.list:
        for fid in sorted(FIXTURES, key=lambda k: (FIXTURES[k]["round"], k)):
            print("  R%-2d %-5s %s" % (FIXTURES[fid]["round"], fid, FIXTURES[fid]["desc"]))
        print("\n共 %d 个样本" % len(FIXTURES))
        return 0

    if a.quick:
        ids = QUICK
    elif a.only:
        ids = [x.strip() for x in a.only.split(",") if x.strip()]
    elif a.round is not None:
        ids = [k for k in FIXTURES if FIXTURES[k]["round"] == a.round]
    elif a.all:
        ids = list(FIXTURES)
    else:
        ap.error("给一个范围：--quick / --round N / --only a,b / --all")
    unknown = [x for x in ids if x not in FIXTURES]
    if unknown:
        print("未知样本：%s" % unknown); return 2
    ids = sorted(ids, key=lambda k: (FIXTURES[k]["round"], k))

    work = pathlib.Path(a.work).resolve()
    (work / "assets").mkdir(parents=True, exist_ok=True)
    make_assets(work / "assets")

    import edge_cdp
    node = a.node
    if not node:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("ce", str(HERE / "00_check_env.py"))
            ce = importlib.util.module_from_spec(spec); spec.loader.exec_module(ce)
            node = ce.find_node()
        except Exception:
            node = None
    kit = a.libreoffice_cli or find_kit()

    started = False
    if not edge_cdp.probe(a.port):
        ns = argparse.Namespace(port=a.port, profile=str(work / "edgeprofile"), exe=None, wait=25,
                                onscreen=False)
        started = edge_cdp.cmd_start(ns) == 0
        if not started:
            print("!! 浏览器起不来，压力矩阵无法运行"); return 2
    else:
        print("复用已在运行的 CDP 端口 %d" % a.port)

    results = []
    try:
        for fid in ids:
            print("\n=== [%s] %s" % (fid, FIXTURES[fid]["desc"]))
            r = run_one(fid, work, a.port, to_pdf=not a.no_verify, kit=kit, node=node)
            results.append(r)
            print("    gate=%s pptx_rc=%s verify=%s -> %s"
                  % (r["obs"]["gate"], r["obs"]["pptx_rc"], r["obs"]["verify"],
                     "OK" if r["ok"] else "不符合预期"))
            for f in r["fails"]:
                print("      ! %s" % f)
    finally:
        if started and not a.keep_browser:
            edge_cdp.cmd_stop(argparse.Namespace(port=a.port, profile=str(work / "edgeprofile"),
                                                 exe=None, wait=25, kill_all=False))

    n_ok = sum(1 for r in results if r["ok"])
    print("\n================ 压力矩阵（%d 个样本）================" % len(results))
    for r in results:
        print("  %-5s R%-2d %-5s %s" % (r["id"], r["round"], "OK" if r["ok"] else "FAIL",
                                        r["desc"][:46]))
    print("  %d/%d 符合预期" % (n_ok, len(results)))
    report = {"ok": n_ok == len(results), "n": len(results), "n_ok": n_ok, "results": results}
    (work / "pressure_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("  报告：%s" % (work / "pressure_report.json"))
    if a.md:
        lines = ["| 样本 | 轮 | 说明 | 结果 |", "|---|---|---|---|"]
        for r in results:
            lines.append("| `%s` | %d | %s | %s |"
                         % (r["id"], r["round"], r["desc"], "OK" if r["ok"] else "FAIL: " +
                            "；".join(r["fails"])))
        pathlib.Path(a.md).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("  Markdown：%s" % a.md)
    print("结论：%s" % ("PASS" if n_ok == len(results) else "FAIL（%d 个样本与预期不符）"
                        % (len(results) - n_ok)))
    return 0 if n_ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
