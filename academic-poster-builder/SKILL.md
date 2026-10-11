---
name: academic-poster-builder
display_name: 学术墙报制备（文献 → HTML/PDF/可编辑 PPTX）
display_name_en: Academic Poster Builder (Literature → HTML/PDF/Editable PPTX)
description: "把用户给的文献与资料做成学术墙报：读文献定故事线与面板划分 → 按墙报口径改写文案 → 处理图表、引用与授权 → 写成满足版面契约的 HTML → 导出 PDF 与可编辑 PPTX，并保证 PPT 与浏览器/PDF 渲染逐元素对齐（DOM 实测 + 几何门禁 + PPT↔PDF 一致性校验）。触发词：做一张学术墙报/poster、把论文做成墙报、会议墙报排版、文献转海报、墙报 HTML、墙报转可编辑 PPT、PPT 文字错位/重叠/换行异常、PPT 与 PDF 版面对不上、PPT 留白或溢出、横幅被压扁、编号框、图注与图不符、墙报排版门禁。"
description_zh: "文献/资料 → 学术墙报的完整流程与硬规范：输入清单与合规红线 → 故事线与面板划分 → 墙报文案改写 → 图表与引用 → 生成 HTML → 几何门禁 → 导出 PDF 与可编辑 PPTX → 一致性验收；含图片裁白边与纵横比审计、object-fit 裁切、单边边框、编号居中修正、进程与备份规范。"
description_en: "Turn supplied literature and materials into an academic poster: gather inputs and clear rights, define the storyline and panels, rewrite copy for poster density, prepare figures and citations, then produce HTML, PDF and an editable, pixel-faithful PPTX (browser-measured DOM geometry, a quantified layout gate, figure trimming and aspect audit, object-fit cropping, per-side borders, and PPT-vs-PDF verification of badge centring, text placement, picture crop and package integrity)."
category: writing
version: 1.7.1
author: Yangming Hu
license: Apache-2.0（见 @references/LICENSE）
---

# 学术墙报制备（文献 → HTML / PDF / 可编辑 PPTX）

**输入**：用户给的文献与资料（论文、图、数据、会议要求）。**输出**：三种同源交付物 ——
`poster.html`（唯一真源）、`poster.pdf`（送印）、`poster.pptx`（可编辑）。
中间每一步都有**可量化的门禁**：先按 `05` 节把墙报做出来，再用 `01`–`04` 把 HTML 变成
与浏览器/PDF **逐元素对齐**的 PPTX。包内阈值来自多轮真实迭代（900×1200 mm 与 A0 两种画布、
数十个中性样本的压力矩阵），不是纸上推算。

> **包内资源**（包根 = 本 `SKILL.md` 所在目录，相对路径均以此为根）
> - `@references/05-prepare.md` —— **制备流程：文献/资料 → 墙报（从这里开始）**
> - `@references/01-workflow.md` —— 流水线、版面规格、门禁阈值（**改 HTML 前先读这个**）
> - `@references/02-pptx-conversion.md` —— HTML→PPTX 的 15 条映射规则（核心）
> - `@references/03-figures.md` —— 图片：取图、裁白边、纵横比、合并图
> - `@references/04-operations.md` —— 浏览器/进程/权限/备份 + 故障速查表
> - `@references/06-field-notes.md` —— **实战经验**：多轮返工里怎么接反馈、怎么收敛版面、怎么交付
> - `@references/07-pressure-matrix.md` —— **压力矩阵**：10 轮自查怎么做、"看起来过了其实没过"的八种形态
> - `@references/00-install.md` —— 安装、依赖、实测验证记录、**版权与合规提示**
> - `@references/LICENSE` —— **许可（LICENSE）、署名与免责声明**

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `scripts/00_check_env.py` | 环境体检（playwright / pymupdf / python-pptx / Pillow / numpy / 浏览器 / LibreOffice kit / 字体）；`--json` 供自检复用 |
| `scripts/edge_cdp.py` | 自己拉起 / 查看 / 关闭浏览器实例（CDP；**不要用 headless**） |
| `scripts/poster_measure.js` | DOM 实测 + 几何门禁（一次 evaluate 返回全部数据） |
| `scripts/10_measure_gate_export.py` | 一次会话完成：测量 + 门禁 + 导出 PDF + 预览 PNG + 每格余量 |
| `scripts/20_html2pptx.py` | 由实测 JSON 生成可编辑 PPTX（不需要浏览器）；缺图 → 退出码 1 |
| `scripts/30_figure_tools.py` | `trim` 裁图片白边 / `aspect` 纵横比审计 |
| `scripts/40_verify_pptx.py` | 验收（编号居中 / 文本落位 / 图片变形与裁切 / 包结构 / 页尺寸） |
| `scripts/50_snapshot.py` | 版本快照（`_backup/<时间戳>_<标签>/`，自动识别 html/pdf/pptx） |
| `scripts/99_selftest.py` | **自检**：新机器上一键验证整条链路（体检→起浏览器→测量门禁→PPTX→一致性校验→关浏览器） |
| `scripts/60_pressure_matrix.py` | **压力矩阵**：39 个中性样本 × 10 轮，逐项比对"该过的过、该拦的拦、不许 traceback"（`--quick` 3 个冒烟样本） |

## 何时用

- 用户给了文献/资料，要做一张**学术墙报**（要 HTML + PDF + 可编辑 PPT）→ 从 `@references/05-prepare.md` 起手。
- 已有 HTML 墙报，要交付 **PPT 可编辑版**，且不能比 PDF 差 → 从 `@references/01-workflow.md` 起手。
- PPT 出现：文字重叠、图注压图、编号数字空了/歪了、项目符号压字、编号被挤到独立一行、
  小节标题多出一行、留白或溢出、整版被放大裁切、**横幅被压扁/圆角变直角**。
- 需要把"每小节不留白、底部留边距、三栏底边对齐"变成**可测量**的验收条件。

## 硬规则（违反必然错版，细则见 `@references/02-pptx-conversion.md`）

1. **版式只有一份真源**：浏览器 DOM 实测坐标（`poster_measure.js`），不要目测换算。
2. **文本盒 = 内容盒**（加回 border/padding，宽度减掉），否则文字压在色条/项目符号上。
3. **每段一个文本框**：block 子元素 / `<br>` 都拆段，每段用实测字体盒定位；否则混合字号段落
   （中文标题+英文副标题）会被行距推下去压住下一行。
4. **行距用精确磅值** `line-height(px) × 0.75`（`spcPts`），不要用倍数。
5. **垂直修正**：浏览器把字体盒居中于行盒，PPT 精确行距下是底对齐 → 文本框 y 取
   `实测字体盒顶 + (首行字体盒高 − 行距)`；`line-height:normal` 时不用移。
6. **宽度余量按锚定边给**：左对齐只向右 +6 px；居中两侧对称 ±24 px；右对齐向左 +48 px。
   否则居中/右对齐文本会在 PPT 里换行或整体偏移。
7. **编号数字单独取出并双向居中**（`.num`/`.n` 这类 flex 居中小方块，`mode='hv'`）。
8. **圆角矩形** `adj = radius / min(w,h)`；`radius==0` 时用普通矩形（不是 `roundRect(adj=0)`）。
9. **图片写死 width+height**，纵横比误差 ≤0.5%；改尺寸后跑 `30_figure_tools.py aspect`。
   `object-fit:cover/contain` 的横幅**必须按 `object-position` 真的裁切/等比缩放**——
   直接按框拉伸会把横幅压扁（实测）；`border-radius` 要变圆角；`transform:rotate` 要跟着转。
10. **色值/几何一律取浏览器实测**（`background-color`、渐变第一个色停靠点、**四条边框**的
    宽度与颜色、`::before`、`border-radius`）。脚本里不写死主题色；单边边框（`.panel-head`
    下边线、`.note` 左边条）只采一条就会整条丢失。
11. **行内效果一个都不能丢**：上下标按「同一视觉行基线之差」实测偏移（`<sup>` 也要抬起来）；
    下划线/删除线写 `underline`/`strike`；`text-transform` 落到文字上；`white-space:nowrap`/`<pre>`
    置 `word_wrap=False`，`\n` 转段落内软换行、`\t` 按 4 空格近似；字号直接取浏览器算好的值。
    正文块元素尽量写进 `CFG.texts`，**没写进去的也有兜底扫描收走**；每段要带自己的文字原点
    （`<dd>`/`<ol>` 的缩进不能丢）；不可见内容不进 PPT；半透明文字按背景合成；
    被祖先 `overflow:hidden`（含圆角）裁掉的内容要么不画、要么告警，贴角子元素用 `custGeom` 逐角圆角。
12. **改完必须验收**：PPTX→PDF→位图，逐项比对文本墨迹与 DOM 位置（`40_verify_pptx.py`）；
    图片缺失必须让第 4 步失败，不要交出缺图的 PPTX。
13. **"没有颜色"与"黑色"必须分开**：实测色值为 `-1` 表示没有颜色，`0` 就是黑色。
    用真值判断（`if fill:`）会把黑色填充/边框/项目符号整块丢掉（深色配色直接错版）；
    `oklch/lab/color()/color-mix` 等色彩空间交给 canvas 归一化成 sRGB，取不到要告警。
14. **"检查没跑成"不是"通过"**：选择器 0 命中、测不到文本、导出被跳过、编号一个都没测到 ——
    一律判 FAIL 并说清用哪个参数补救（`--panel/--column/--poster`、`--allow-skip`、
    `--no-badge-check`）。**不要**让某次跳过悄悄变成 PASS。
15. **换模板/换类名不用改脚本**：选择器由 `10_measure_gate_export.py` 的
    `--poster/--content/--column/--panel/--panel-body/--panel-head` 覆盖；
    渲染进 PPT 的矩形/文本仍由 `poster_measure.js` 顶部的 `CFG` 决定（那是模板契约）。

## 工作流

```bash
# 0) 自检：确认这台机器整条链路能跑通（含包内模板全流程）
python scripts/99_selftest.py

# 0.1) 压力矩阵（可选但推荐，尤其换机器/改过脚本之后）：3 个冒烟样本
python scripts/60_pressure_matrix.py --quick
#      全量 39 个样本（10 轮）：python scripts/60_pressure_matrix.py --all

# 0.5) 制备（有文献/资料时先做这一步）：收输入 → 故事线与面板 → 文案改写 → 图表与引用
#      照 @references/05-prepare.md §0–§4 走，产出提纲后再写 HTML

# 1) 起手：复制模板，改画布尺寸/字体/文案
cp templates/poster_template.html ./poster.html

# 2) 环境体检
python scripts/00_check_env.py

# 3) 起浏览器（不用 headless；窗口默认在屏幕外，不打扰你；用完必须 stop）
#    同一端口已在跑会自动复用，不会新开窗口；要看着调试加 --onscreen
python scripts/edge_cdp.py start --port 9223

# 4) 测量 + 门禁 + 导出（一次会话）；门禁不过 → 只改 HTML → 重跑本步
python scripts/10_measure_gate_export.py \
  --html poster.html --canvas 3402x4536 --pdf-size 900x1200 \
  --pdf poster.pdf --png _work/preview.png \
  --shapes _work/shapes.json --report _work/gate_report.json \
  --cdp http://127.0.0.1:9223 --js scripts/poster_measure.js
#    换模板/换类名：加 --poster .wrap --content .grid --column .colc --panel .card \
#      --panel-body .card-body --panel-head .card-top（不必改 poster_measure.js）
#    想让"留白超阈值"也判失败：加 --fail-loose；确实不需要某项检查：加 --allow-skip

# 5) 生成可编辑 PPTX（不启浏览器）；有图片缺失会退出码 1 且不写文件
python scripts/20_html2pptx.py --shapes _work/shapes.json --out poster.pptx \
  --html poster.html --font "Microsoft YaHei" --slide-mm 900x1200

# 6) 验收（PPTX→PDF 用 LibreOffice kit，然后逐项比对）
python scripts/40_verify_pptx.py --pptx poster.pptx --shapes _work/shapes.json \
  --html poster.html --pdf-size 900x1200 \
  --pdf-preview _work/preview.png --pptx-pdf _work/pptx.pdf

# 7) 关浏览器 + 快照
python scripts/edge_cdp.py stop --port 9223
python scripts/50_snapshot.py --label v1
```

**门禁不过时改什么**（阈值与测法见 `@references/01-workflow.md`）：

| 症状 | 先改什么 |
|---|---|
| 溢出（slack 为负） | 先缩该栏图片宽度（等比），其次删/缩文字（1 行 ≈ 27–35 px） |
| 留白（slack > 40 px） | 把该栏图片放大到栏宽，其次补一句实质内容（不要灌水） |
| 三栏底边不齐 | `.col` 高度必须等于 `.content` 高度（改页头后同步） |
| 栏区左右留白不等 | 栏宽之和没填满内容区（`Σ栏宽+Σ间距 = 画布宽 − 2×页边距`） |

## 交付物

| 文件 | 说明 |
|---|---|
| `poster.html` | 版式唯一真源（可继续迭代） |
| `poster.pdf` | 打印版（单页、无页边距、背景开、尺寸按会议要求） |
| `poster.pptx` | 可编辑版（文本框 + 图片 + 形状；编号/图注/小结都可改字） |
| `_work/shapes.json` | 当前 PPTX 所依据的实测数据 |
| `_work/gate_report.json` | 门禁原始数据（可复现） |
| `_backup/<时间戳>_<标签>/` | 每轮快照 |

## 已知边界

- 文本落位阈值取 10 px：LibreOffice 与 PowerPoint 对"精确行距首行基线"的处理最多差约 8 px，
  属可接受的渲染器差异 → 不要把两行文字排到只差 10 px 的位置上。
- macOS / Linux：浏览器路径与字体族按环境替换（`CHROME_PATH`、`--font`），中文字体缺失时
  断行点会与 PDF 不一致。
- `PPTX→PDF` 依赖 LibreOffice kit；缺失时 `40_verify_pptx.py` 的页尺寸项与
  `99_selftest.py` 第 4 步自动跳过。
- **接单/收费本身不违法**，风险在素材授权与经营合规：见 `@references/00-install.md` 第 6 节。
- 门禁默认**把"跳过"判失败**（缺 `--pdf-size`、没导出 PDF 等）；确实不需要时用 `--allow-skip`，
  它会把每一处跳过打印出来。`40_verify_pptx.py` 同理：没有可比对的编号徽标时用 `--no-badge-check`。
- 故障现象与修法见 `@references/04-operations.md`；安装与实测数据见 `@references/00-install.md`；
  多轮返工的经验与交付纪律见 `@references/06-field-notes.md`；
  自查方法与"看起来过了其实没过"的八种形态见 `@references/07-pressure-matrix.md`。
