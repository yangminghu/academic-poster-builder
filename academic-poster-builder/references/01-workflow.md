# 01 · 流水线、版面规格与几何门禁

## 1. 真源与流水线

| 真源 | 内容 | 说明 |
|---|---|---|
| `poster.html` | 版式、文案、图片尺寸 | **唯一版式真源**，PDF/PPTX 都由它派生 |
| `_work/shapes.json` | 浏览器实测的每个元素坐标 | PPTX 的唯一几何来源（含实测色值/边框/字体盒/object-fit/圆角） |
| `assets/*.png` | 图片素材 | 尺寸一变就要重跑纵横比审计；**缺图会让第 4 步失败，不产出残缺 PPTX** |

永远不要手工量 PPT 坐标去改 HTML，也不要凭源码"心算"坐标去写 PPT。
**正文块元素（`li` / `p` / `.note` / `figcaption`）尽量都写进 `poster_measure.js` 的 `CFG.texts`**：
写进去的用类名/标签精确定位；没写进去的也有**兜底扫描**（`sel='auto'`）收走，不会整段消失
（`<p>` 就曾整段消失过）。

```bash
python scripts/00_check_env.py                    # 1 环境体检（必须全绿）
python scripts/edge_cdp.py start --port 9223      # 2 起浏览器（不用 headless，用完 stop）
python scripts/10_measure_gate_export.py \        # 3 测量+门禁+导出（一次会话）
  --html poster.html --canvas 3402x4536 --pdf-size 900x1200 \
  --pdf poster.pdf --png _work/preview.png \
  --shapes _work/shapes.json --report _work/gate_report.json \
  --cdp http://127.0.0.1:9223 --js scripts/poster_measure.js
python scripts/20_html2pptx.py --shapes _work/shapes.json --out poster.pptx \   # 4 生成 PPTX
  --html poster.html --font "Microsoft YaHei" --slide-mm 900x1200
<node> "<kit>/lib/cli.js" convert --input poster.pptx --output _work/pptx.pdf
python scripts/40_verify_pptx.py --pptx poster.pptx --shapes _work/shapes.json \  # 5 验收
  --html poster.html --pdf-size 900x1200 --pdf-preview _work/preview.png --pptx-pdf _work/pptx.pdf
python scripts/edge_cdp.py stop --port 9223        # 6 收尾
python scripts/50_snapshot.py --label v1
```

**换模板/换类名**：第 3 步加选择器覆盖即可，不必改 `poster_measure.js` ——
`--poster .wrap --content .grid --column .colc --panel .card --panel-body .card-body --panel-head .card-top`。
（`poster_measure.js` 顶部的 `CFG.rects/texts` 决定**哪些元素进 PPT**，那是模板契约；选择器只决定**门禁量什么**。）

要点：`--canvas` 是画布尺寸的唯一入口（会写进 `shapes.json`）；`--slide-mm` 必须等于画布 px
换算的毫米数（`px/96×25.4`，坐标按 9525 EMU/px 写死，不一致会裁右边/下边，脚本会告警）；
第 4 步**有图片缺失就退出码 1 且不写文件**（要接受缺图必须显式加 `--allow-missing-images`）；
一次会话做完全部事情，不要反反复复开关浏览器。迭代节奏：门禁不过 → 只动 HTML → 重跑第 3 步
（一轮 40–90 s，通常 2–3 轮收敛）。

**该改什么**：溢出（负 slack）先缩该栏图片宽度、再删/缩文字（1 行 ≈27–35 px）；留白（>40 px）
先放大该栏图片到栏宽、再补实质内容（`flex:1 1 auto` 会把余量平均分给该栏**每个**面板）；
栏底不齐检查 `.col` 高度是否等于 `.content` 高度；栏区边距不等看 §2 三栏。
想让留白超阈值也判失败，加 `--fail-loose`。

## 2. 版面规格（起手模板的契约）

```
CSS px = 目标毫米 × 96 / 25.4；900×1200 mm → 3402×4536 px；A0 841×1189 → 3179×4494 px
html, body { width:Wpx; height:Hpx }；.poster{ width:Wpx; height:Hpx; overflow:hidden }
```

**页头高度必须自己算平**：

```
banner(固定高) + 标题块(margin-top + 实测高) + 指标行(margin-top + 固定高)
              + content(margin-top + height) + 底部留白 = 画布高
```

标题块/指标行的高度取决于字号与行数，**不要照抄别的项目的数字**：写完用 `shapes.json` 里
`.titleblock`/`.content` 的实测值核对。**改任何一项都要重算 `.content{height}` 与
`.col{height}`，两者必须相等**；不用 banner 时把它的高度补进 `.content`。
示例（900×1200 mm，用符号代替具体的标题块高）：
`banner + (14 + 标题块实测高) + (12 + 指标行高) + (12 + content 高) + 底部留白 = 4536`，
底部留白 ≥50 px（参考 61 px）——标题块实测高去 `shapes.json` 里读，不要估算。

**三栏**：`Σ栏宽 + Σ栏间距 = 画布宽 − 2×页边距`，且栏区左右留白之差 ≤2 px（门禁第 5 项逐像素查）。
页边距由栏宽反推：`(3402 − 3178)/2 = 112 px`；页头三块（标题块/指标行/content）必须同值，
否则右栏会比页头缩进一条（实测踩过 48 px = 12.7 mm）。

```css
.content{ margin:12px 112px 0; display:flex; gap:24px; }
.col{ width:1010px; flex:0 0 1010px; height:<content>; display:flex; flex-direction:column; gap:20px; }
.col.center{ width:1110px; flex:0 0 1110px; }
```

**面板**：`.panel` 的 flex-basis 是内容高，`flex-grow:1` 把该栏剩余空间**平均**分给各面板；
内容超出时按各自 basis 比例收缩 → 负 slack（文字被裁）。所以"某一格多 20 px"会摊到整栏。
`.panel-head{padding:8px 20px}`（每减 2 px，全栏省 4 px/面板）、`.panel-body{padding:11px 20px 13px; gap:9px}`。
**内容区可用宽度**：左/右栏 `1010−6−40 = 964 px`，中栏 `1110−6−40 = 1064 px`（写图幅上限用）。

**图片**：`<img class="fx" style="width:830px;height:319px" src="assets/x.png" alt="...">`
— width/height 必须同时写且与源图纵横比一致（≤0.5%）；`h = w / aspect`，改宽度同步改高度。
`object-fit:cover/contain` 的横幅按 `object-position` 在 PPTX 里做裁切/等比缩放（见
`@references/02-pptx-conversion.md` 规则 12）。合并图用"一图两图注"（图号沿用）。

| 用途 | 字号 / 行高 |
|---|---|
| 大标题 h1 | 76 / 1.14；英文副标题 33 / 1.22 |
| 面板标题 h2 | 35 / 1.08；英文 19 |
| 正文 li / p | 27 / 1.34–1.38 |
| 图注 figcaption | 21 / 1.28 |
| note（每节小结） | 24 / 1.32 |
| 指标卡 数值/标签 | 47 / 21 |

行高写**数字倍数**（PPT 侧要按 `font-size × 倍数` 换算精确磅值）；写 `normal` 也可以
（脚本跳过精确行距），但同一段落内不要混。

**留白与边距**：每格底部余量 0–40 px（`panel.bottom − 内容最低点`，DOM 实测不是看图）；
底边距 ≥50 px（参考 61 px）；左右边距 ≥80 px（参考 112 px）；栏内间距 20 px、面板内元素间距
9 px 是最后 20–40 px 的微调旋钮。

**常见陷阱**：改页头后忘记同步 `.col` 高度（整版下方空一条）；给面板写死 `height`（flex 失效、
栏底不齐）；图片只改 width（变形，PPT 里被拉伸更明显）；`li` 项目符号不用 `::before`（PPT 不复现）；
单边边框（`.panel-head` 下边线、`.note` 左边条）只采一条就不会被画出来。

## 3. 几何门禁（阈值 + 怎么测）

所有指标来自同一次浏览器会话（`10_measure_gate_export.py`），原始数据在 `gate_report.json`。

| # | 指标 | 阈值 | 怎么测 | 不合格先改什么 |
|---|---|---|---|---|
| 1 | 画布尺寸 | `body.scrollWidth/Height` == `--canvas`（±1 px） | `getBoundingClientRect` / `scrollWidth` | 内容超宽/超高（找溢出的元素） |
| 2 | **选择器命中** | 面板数 >0、栏数 >0、`.poster`/`.content` 各 1、`.panel-body` 不缺 | `gate.selectors` | 用 `--panel/--column/--poster/--content/--panel-body` 指定 |
| 3 | **`.poster` 盒 = 画布** | 盒宽高 == `--canvas`（±1 px） | `.poster` 的 rect | `body.scroll*` 会被固定高度"顶住"，量不出内容比画布小 |
| 4 | 面板溢出 | `max(body 溢出, 子元素内容溢出, **panel 自身溢出**) ≤ 2 px` | 每个 `.panel`/`.panel-body` | 缩该栏图片宽度 or 删 1 行文字 |
| 5 | 栏底对齐 | `max−min(lastPanelBottom) ≤ 2 px` | 每栏最后一个面板的 bottom | `.col` 高度 ≠ `.content` 高度 |
| 6 | 栏内最大间隙 | `≤ 40 px`（正常 = 设计 gap） | 相邻面板 top−bottom | 面板高度被写死 |
| 7 | 栏区左右留白 | 左右之差 `≤ 2 px` | 栏组 x 与 `.content` 内容盒之比 | `Σ栏宽+Σ间距` 没填满内容区 |
| 8 | **越界内容** | 0 处 | `.poster` 内所有元素 rect 是否超出 `.poster` 盒 | 横向/纵向溢出会被 `overflow:hidden` 静默裁掉 |
| 9 | **祖先 transform** | 必须为 none | 逐级看 `.poster` 及其祖先 | `scale()` 之后 rect 全是缩放后坐标，栏高/画布却是布局尺寸 |
| 10 | **文本/图片覆盖** | 文本项 >0；测到图片数 + 隐藏数 + 被裁数 ≥ `<img>` 数 | `data.texts`、`gate.images` | 选择器不匹配 / 图被隐藏 |
| 11 | **页面 JS 报错** | 0 条 | `pageerror` 事件 | 先修页内脚本 |
| 12 | 画布 ↔ 目标 mm | `±1.5 mm` | `px / 96 × 25.4` | 画布尺寸算错 |
| 13 | 每格余量（留白） | **0–40 px**（>40 记 loose） | `panel.bottom − max(子元素 bottom)` | 放大该栏图片 / 补文字 |
| 14 | 底边距 | `≥ 50 px` | 画布底 − 最下排面板 bottom | 减 `.content` 高度 |
| 15 | PDF | 1 页，目标尺寸 ±1 mm | 导出后读 PDF `rect` | printToPDF 参数 |

`GATE: PASS ⇔ 1–15 全部通过`。三点口径要记牢：

- **"检查没跑成" = 失败**：跳过（缺 `--pdf-size`、没导出 PDF）默认判 FAIL；
  确实不需要时用 `--allow-skip`，它会把每一处跳过打印出来。
- 第 13 项默认只警告（有些面板本来就短一截），成品验收加 `--fail-loose`；
  第 7 项用 `--tol-coledge` 调阈值。
- 第 2/3/8/9/10/11 项是新版补上的——它们对应的都是"**门禁报 PASS，但内容其实错了/根本没测**"
  这一类假通过（见 `@references/07-pressure-matrix.md` 第 5 节）。

一次通过应该长这样：画布 `3402×4536`、面板零溢出、栏底三值相等（差 0）、间隙 = 设计 gap、
栏区 `L0/R0`、画布 900.11×1200.15 mm、PDF 单页 900.26×1200.15 mm。
换台机器先跑 `scripts/99_selftest.py`，再跑 `scripts/60_pressure_matrix.py --quick`。

## 4. PPT 侧验收（`40_verify_pptx.py`）

| 指标 | 阈值 | 说明 |
|---|---|---|
| 编号数字居中 | 中心偏差 **≤1 px** | PPT 渲染图 vs HTML 预览图，比较徽标内白色数字的墨迹中心 |
| 文本落位 | 中位 ≤2 px，**最大 ≤10 px** | 每个文本项在两图中的墨迹顶边差 |
| 图片 | 普通图变形 ≤0.5%；cover **必须真的裁切**；contain 必须等比 | 读实测 `object-fit` + PPTX 里的 `srcRect` / 图片帧 |
| 包结构 | 无问题 | 内建检查：ZIP 完整性 + 必备部件 + 全部 XML/rels 可解析 + 内部关系目标存在 |
| PPTX→PDF 页尺寸 | 目标 ±1 mm，单页 | 读 PDF `rect`，与 `--pdf-size` 或画布 mm 对照 |

**"没有可比对的对象"也是失败**：没有编号徽标可比对 → FAIL（`--no-badge-check` 显式放行）；
PPTX 里的图片对象少于实测图片数 → FAIL（`--allow-missing-pictures` 显式放行）；
读不出 PPTX 里的图片 → FAIL。图片按对象名（`FIG <文件名>`，重复加 `#n`）配对，不按序号。

**常见"看起来过了其实没过"**：用像素统计代替 DOM 测量判留白（面板底色/边框会被算成墨迹，
结论完全反）；用绝对亮度阈值判墨迹（标题条 `#E8F1FD`、note 底色 `#F2F7FE` 接近白会被算成墨迹）
——要用**窗口内背景中位数**做基准、差异 >40 才算墨迹（`ink_box` 即如此，深色底上的白字也能测）；
窗口开太大（把相邻元素的墨迹算进来，窗口就用元素框本身，上下 ±2 px）；
只看缩略图（1–3 px 错位看不见，关键区域要 1:1 裁图对照）；
只验一个版本（HTML 与 PPTX 是两条产物链，必须分别验证再互验）；
只看"变形 0"就放心（cover 图会被明确豁免，必须另外查是否真的裁切）。
