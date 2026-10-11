# 07 · 压力矩阵：让代码自己证明（10 轮自查）

规则写完 ≠ 代码做到了。这份技能包的每条规则都是从故障反推出来的，而**反推出来的规则最容易
只写在文档里**：文档说"没测到面板要判失败"，代码里却是 `max([])` 抛异常；文档说"黑色也要画"，
代码里却用真值判断把黑色当"没有颜色"。所以需要一套**事先写好预期、事后逐项比对**的样本集。

`scripts/60_pressure_matrix.py` 就是这套东西：运行时现场生成一批**中性样本**（占位文案 +
程序生成的图片，不含任何真实项目内容），逐个跑「测量 + 门禁 + PPTX (+ 一致性校验)」，
把结果与预期比对。

> **样本是现场生成的**，不进包、不随包分发。`--list` 看清单，产物落在 `_work/_pressure/`。

## 1. 矩阵的设计：7 组轴

| 组 | 轴 | 想问的问题 |
|---|---|---|
| A | 输入形态 | 标准三栏 / 单栏 / 四栏 / 24 面板 / 零图片 / 换类名 / 空画布 |
| B | 画布与尺寸 | A0 / 90×120 / 横版 / 画布与 mm 不符 / 参数写错 |
| C | 内容与样式 | 横幅裁切 / 上下标 / 下划线 / 大小写 / nowrap / pre / 半透明 / 隐藏 / 旋转 / 圆角 / 单边边框 / 项目符号 / 缩进 / 深色配色 / 行内文本 / 重复用图 / SVG / 坏图 / 空格文件名 |
| D | **门禁假通过攻击** | 内容比画布小 / 横向溢出 / 画布外内容 / JS 报错 / 面板溢出 / 大片留白 / 没有根元素 / 选择器 0 命中 |
| E | CLI 与错误输入 | HTML 不存在 / shapes.json 截断 / `--canvas`/`--pdf-size` 写错 / 字体不存在 / `--slide-mm` 不符 |
| F | 对齐与交付 | justify / end / center 混排（不能都变右对齐） |
| G | 数据级断言 | 不该进 PPT 的文字、黑色是否真被当颜色、oklch 是否被解析 |

**预期的三种口径**（写在样本登记里，跑之前就定好）：

1. `gate: PASS` — 该过的样本必须**真**通过（不是"跳过了所以算通过"）；
2. `gate: FAIL` + `gate_must: [...]` — 该拦住的必须拦住，而且输出里要出现那句**可读的原因**；
3. `no_traceback` — 任何样本都不许抛 Python traceback（崩溃不是"失败"，是缺陷）。

另有数据级断言：`shapes_include` / `shapes_exclude`（哪段文字必须/不许出现在实测数据里）、
`black_present`（黑色填充/边框/项目符号是否被采集成颜色）。

## 2. 39 个样本

| 轮 | 样本 | 内容 | 预期 |
|---|---|---|---|
| 1 | `A1` | 标准三栏 | PASS |
| 1 | `A7` / `D6` / `D7` | 空画布 / 选择器 0 命中 / 没有栏容器 | FAIL（有原因，不崩） |
| 1 | `D5` | `.panel` 里没有 `.panel-body` | FAIL（不崩） |
| 2 | `A2a` | 换类名、不给选择器 | FAIL，提示 `--panel` |
| 2 | `A2b` | 换类名 + 选择器覆盖 | PASS |
| 3 | `B1` / `B3` | A0 / 横版画布 | PASS |
| 3 | `B4` | 画布 px 与 `--pdf-size` mm 不符 | FAIL，指出哪个不符 |
| 3 | `B5` / `B6` | `--canvas` / `--pdf-size` 写错 | 干净报错（不是 ValueError 栈） |
| 4 | `C1` | `object-fit:cover` 横幅（4:1 → 8.5:1） | PASS + PPT 里必须真裁切 |
| 5 | `C2` | 上下标/装饰线/大小写/半透明/nowrap/pre/旋转/圆角 | PASS + 一致性校验 PASS |
| 5 | `C9` | 黑色填充/边框/项目符号 + oklch 背景 | PASS + `fill` 必须是 0（不是 -1） |
| 5 | `C10` | `opacity:0` / `visibility` / `display:none` 的文字 | PASS + 这些文字**不得**进 PPT |
| 5 | `C11` | 只用 `div > span` 写的文本行 | PASS + 这三段文字必须在 PPT 里 |
| 6 | `C3` | 单边边框/虚线/空心与原生项目符号/缩进/圆角裁切 | PASS |
| 7 | `C4` | 同一张图被引用多次 | PASS（形状名去重、按名字配对） |
| 7 | `C5` / `C6` | SVG / 坏图片文件 | 退出码 1 + 可读原因（不崩） |
| 7 | `C7` | 图片路径不存在 | 退出码 1 且**不产出** PPTX |
| 7 | `C8` | 图片文件名含空格 | PASS |
| 8 | `D1` | 内容只占画布 80% | FAIL（画布盒也要量） |
| 8 | `D2` / `D3` | 横向溢出被裁 / 画布外绝对定位内容 | FAIL |
| 8 | `D3b` | 页面有 JS 报错 | FAIL |
| 8 | `D4` | 面板内容溢出（`overflow:hidden` 包裹） | FAIL |
| 8 | `D5b` | 面板大面积留白（`--fail-loose`） | FAIL |
| 8 | `D8` | 没有 `.poster` 根元素 | FAIL，提示 `--poster` |
| 9 | `A3` / `A4` / `A5` / `A6` | 单栏 / 四栏 / 零图片 / 24 面板 | PASS |
| 10 | `E1` | HTML 路径不存在 | 干净报错 |
| 10 | `E2` | `shapes.json` 被截断 | 干净报错（不是 JSONDecodeError 栈） |
| 10 | `E3` | `--slide-mm` 与画布不符 | 告警说明会被裁切 |
| 10 | `E4` | 指定了不存在的字体 | 告警（不许静默） |
| 10 | `F1` | `justify` / `end` / `center` 混排 | PASS（justify 不能变右对齐） |

## 3. 怎么跑

```bash
python scripts/60_pressure_matrix.py --list             # 看样本
python scripts/60_pressure_matrix.py --quick            # 3 个冒烟样本（新机器第一件事）
python scripts/60_pressure_matrix.py --round 8          # 单轮
python scripts/60_pressure_matrix.py --only A1,C9,D4    # 挑几个
python scripts/60_pressure_matrix.py --all --md out.md  # 全量 + Markdown 报告
```

- 自己起浏览器（CDP，屏幕外），跑完自己关；已在跑的端口会复用。
- 给出 `LIBREOFFICE_KIT_CLI` + node 时，标了 `verify` 的样本会连 PPTX→PDF 一致性校验一起跑
  （默认 `--no-verify` 可跳过）。
- 退出码 0 = 全部符合预期；报告落在 `<work>/pressure_report.json`（含每个样本的门禁尾部输出）。
- 失败时先看 `fails` 字段：它是"预期 vs 实际"的具体差异，不是"某一步挂了"。

## 4. 本轮 10 轮自查发现并修掉的缺陷

每一轮都先跑、看结果、改代码、再跑同一批直到全绿。以下都是**跑出来**的（不是读文档看出来的）：

| 轮 | 缺陷（症状） | 根因 | 修法 |
|---|---|---|---|
| 1 | 空画布/无栏容器/选择器 0 命中 → **Python traceback**，`gate_report.json` 都没写出来 | `max([])`、`content.scrollHeight`（null）、`body.children`（null） | JS 侧 null 保护 + 把命中数交给门禁；**0 命中一律判失败**并提示用哪个选择器 |
| 1 | 测不到任何东西却报 `GATE: PASS`（最坏的情况：PPTX 里没有文字也算过） | 覆盖度只是 `print`，不参与判定 | 文本/图片/面板/栏的命中数全部进判定；跳过 = 失败（`--allow-skip` 才放行） |
| 2 | 换了类名就完全用不了 | 选择器写死在 `poster_measure.js` 的 CFG 里 | 新增 `--poster/--content/--column/--panel/--panel-body/--panel-head` 覆盖；栏内面板选择器自动剥掉祖先部分（`':scope > .col > .panel'` 曾一个都匹配不到） |
| 3 | A0 / 横版画布报"栏区右边距差 223 px" | 样本用了 90×120 的固定栏宽（不是工具缺陷，是样本） | 样本按画布算栏宽与页边距；也顺带确认工具的栏区检查能抓到真正的不等边距 |
| 4–7 | 旋转过的图被报"变形 2.86%"（假失败） | `getBoundingClientRect()` 给的是**旋转后包围盒** | 生成器与验收都跳过带 transform 的图（用未变换尺寸绘制） |
| 7 | 黑色填充/黑色边框/黑色项目符号**整块消失**（深色配色会白字压白底） | `rgb()` 用 0 同时表示"黑色"和"解析失败"，下游 `if fill:` 又按真值判断 | 新增"没有颜色"哨兵 `-1`（存在性判断）；`oklch/lab/color()/color-mix` 交给 canvas 归一化成 sRGB |
| 7 | `src` 为 null（懒加载/data URI/远程地址）→ `AttributeError`；SVG、0 字节文件 → traceback | 直接对 `im["src"]` 做字符串操作与 `Image.open` | 区分"本地相对路径 / data: / http(s): / file:"；逐图 try/except，明确报"不能内嵌" |
| 7 | 图片变形只在生成器里 `print`，退出码仍是 0 | 自检不参与退出码 | 变形 → 退出码 1（`--allow-distorted-images` 才放行） |
| 7 | 验收把"实测图片"与"PPTX 图片"**按下标配对** | 任何一张图被跳过就整体错位 | 按 `FIG <文件名>`（含 `#n`）配对；配对不上/数量不符 → FAIL |
| 7 | 验收的"编号居中"**一个徽标都没测到也算 PASS** | `ok` 只在有数据的分支里被赋值 | 没有可比对的编号 = FAIL（`--no-badge-check` 显式放行） |
| 7 | `--pdf-size` 写错 → `ValueError` 栈；包不合法时又去构造一次 `ZipFile` → `BadZipFile` | 解析与打开都没包 try | 统一 `parse_size` 干净报错；包不合法只报 FAIL |
| 8 | **面板内容溢出被裁却 PASS**（59 段正文塞进固定高面板） | 只看 `.panel-body` 的 scrollHeight，而 body 已经长高了 | 增加 `.panel` 自身的 `scrollHeight − clientHeight`（`overflow:hidden` 也会报内容高） |
| 8 | 页面 JS 报错、横向越界、画布外内容都不报 | 门禁没有这些项 | 新增：JS 报错 / 越界（横向与纵向）/ `.poster` 盒是否等于画布 / 祖先 transform |
| 5 | `div > span` 写的整行文字**从 PPT 里消失**（三个门禁都发现不了） | 兜底扫描要求"直接文本子节点" | 行内子元素里的文字也算；补 `C11` 样本用 `shapes_include` 断言 |
| 5 | `opacity:0` 的文字被当成不透明写进 PPT | `parseFloat("0") || 1` → 1 | 显式判断 `isNaN`；祖先 opacity <0.02 视为隐藏 |
| 10 | `text-align:justify` 被当右对齐输出 | 除 left/center 外全落到 `else: 右对齐` | 显式分支：right/end、justify、未知（按左对齐并告警） |
| 10 | 本机没有指定字体时不告警 | 生成器不查字体 | 复用 `00_check_env` 的字体探测，缺失即告警 |
| 全部 | 测量失败时**旧的 `shapes.json` 留在原地**，下一步会拿旧数据生成 PPTX | 覆盖写之前不清理 | 测量前把旧文件改名为 `.prev` 并提示 |
| 全部 | 输出目录不存在时 `--pdf`/`--png`/`--out` 写不出来（测量白跑） | 只给 shapes/report 建目录 | 所有输出路径统一建目录 |
| 包级 | `99_selftest.py` 里 `40_verify_pptx.py` 报 `UnicodeEncodeError: 'gbk' codec can't encode '−'`（看着像版式校验失败） | Windows 中文控制台默认 GBK，脚本打印 U+2212（`−`）就崩 | 每个脚本都把 `stdout/stderr` 重设为 UTF-8（`errors="replace"`）；**矩阵与自检故意不给子进程设 `PYTHONIOENCODING`**，让这条路径成为常驻回归测试 |

同时修掉的运维问题（同一轮自检里暴露的）：`edge_cdp.py` 的进程查询**把查询自己的 shell 也匹配
进来**（于是"残留永远不为 0"，`--kill-all` 会被误触发去杀用户自己的浏览器）；`99_selftest.py`
被自己创建的 `_work` 目录判 FAIL；转换器退出码被忽略导致旧 PDF 冒充新结果；
`99_selftest` 缺 kit 时跳过校验却报"全绿"；`30_figure_tools.py` 在"一张图都没审计到"时返回 0；
`50_snapshot.py` 同分钟快照互相覆盖；`trim` 压平 alpha 并以默认质量重压 JPEG。

## 5. 八种"看起来过了其实没过"

自检时要专门攻击这八种形态（`D` 组样本就是它们）：

1. **选择器 0 命中**：面板/栏/文本一个都没测到，却因为"没有失败项"而 PASS。
2. **跳过当通过**：`[skip]` 只打印不参与判定（缺 `--pdf-size`、没 `--pdf`）。
3. **验证对象不对**：拿 HTML 实测数据当"PPTX 已正确"的证据（没读 PPTX 里的图片对象）。
4. **黑色 = 没有颜色**：用 0 兼表两种含义，再用真值判断 → 整块黑色被丢掉。
5. **压平后无溢出**：父元素 `overflow:hidden` 把 `scrollHeight` 压平，溢出消失在统计里。
6. **旋转/裁切被当变形**：包围盒比例 ≠ 源图比例，于是报假失败（`--allow-*` 反而会被滥用）。
7. **看不见的东西进 PPT**：`opacity:0`、被圆角裁掉、`display:none` 之后的文字照样输出。
8. **条件式赋值**：`ok` 只在"有数据"的分支里被写 → 没数据等于没失败。

## 6. 加新样本

在 `scripts/60_pressure_matrix.py` 里注册即可（`build` 收到 `dirs`，返回 HTML 路径）：

```python
register("C12", 5, "说明：这份样本要证明什么",
         {"gate": "FAIL", "gate_must": ["原因关键字"], "no_traceback": True},
         build_my_fixture)
```

想断言"实测数据里必须/不许出现某段文字"，加 `shapes_include` / `shapes_exclude`；
想验证颜色是否真的被采集，加 `black_present`。**先写预期，再看结果**——倒过来写就是在给
现有行为背书，起不到自查作用。

## 7. 已知未覆盖（照实写清楚）

- **输入侧**（文献 → 提纲 → 文案）只能靠人判断，矩阵覆盖不到；`@references/05-prepare.md` 的
  清单是那里的检查表。
- 只测了 Windows + Edge；macOS/Linux 的浏览器与字体差异需要各自跑一遍 `--quick`。
- 没有覆盖真实的 Word/LaTeX 输入、多语言混排的断行、超大文件（>200 张图）的性能。
- 一致性校验的阈值（编号 ≤1 px、文本落位中位 ≤2 px / 最大 ≤10 px）是渲染器差异与真错版之间的
  经验分界；换渲染器（PowerPoint 本体）后应重新标定。
