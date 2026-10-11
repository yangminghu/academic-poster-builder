# 00 · 安装、依赖、实测验证记录与合规提示

## 1. 放到哪里

| 范围 | 路径 |
|---|---|
| 用户级（所有会话生效） | `<平台技能目录>/academic-poster-builder/`（DSH 为 `~/.dsh/skills/`，其它平台见其文档） |
| 项目级 | `<项目>/.dsh/skills/academic-poster-builder/` 或 `<项目>/.agents/skills/academic-poster-builder/` |

技能根目录只扫一层（不递归 `**/SKILL.md`）。**上传平台**：按 `{skill-name}/SKILL.md` 打包，
`SKILL.md` 必须在顶层文件夹内（不能平铺在 zip 根、也不能埋两层）；所有文本文件
**UTF-8 无 BOM + LF**，否则 frontmatter 解析失败。

## 2. 依赖

```bash
pip install playwright pymupdf python-pptx Pillow numpy
```

- **浏览器不用下载**：脚本自己拉起系统已装的 Edge / Chrome / Chromium，Playwright 只负责
  `connect_over_cdp`，不需要 `playwright install`。其它平台用 `CHROME_PATH` 或 `--exe`。
- **LibreOffice kit**（仅 PPTX→PDF）：用运行环境自带的 kit CLI（`LIBREOFFICE_KIT_CLI`，
  node 用 `LIBREOFFICE_KIT_NODE` 或 PATH）；没有也能跑完整流程，只是 `40_verify_pptx.py` 的
  页尺寸项与 `99_selftest.py` 第 4 步会**明确报 SKIP**（`--require-verify` 可把它当失败）。
- **中文字体**：模板默认 `Microsoft YaHei`；Linux/macOS 换成实际安装的字体族，
  且 `--font` 必须与浏览器字体栈第一项一致（否则断行点与 PDF 不一致）。生成 PPTX 时若本机
  没有该字体，`20_html2pptx.py` 会告警。

体检：`python scripts/00_check_env.py`（`--json` 只输出一行机器可读结果）。最短用法见 `SKILL.md`。

## 3. 实测验证记录（v1.7.0 发布前实跑）

环境：Windows / Python 3.13 / playwright / PyMuPDF 1.28 / python-pptx 1.0.2 / Pillow / numpy /
Edge 155 / LibreOffice kit（native）/ Microsoft YaHei。

**样本全部是中性样本**：包内模板 + `scripts/60_pressure_matrix.py` 现场生成的 39 个样本
（占位文案 + 程序生成的图片，不含任何真实项目内容），因此下面的数字可被任何人复现。

| 环节 | 结果 |
|---|---|
| `99_selftest.py`（包内模板，含 PPTX→PDF 一致性校验） | **PASS**：起浏览器 → 测量门禁 → PPTX → PPTX→PDF → 一致性校验，收尾残留进程 0 |
| `60_pressure_matrix.py --all`（39 个样本 × 10 轮） | **39/39 符合预期**：门禁 PASS 23 例、按预期拦下 16 例（每例都给出可读原因、**零 traceback**）；生成 PPTX 17 次成功、按预期退出码 1 **4** 次（SVG / 坏图 / 缺图 / shapes.json 截断）；**9 个样本连 PPTX→PDF 一致性校验，9/9 `VERIFY: PASS`** |
| `10_measure_gate_export.py` | 覆盖 3402×4536 / 3179×4494 / 4494×3179 三种画布；门禁新增"选择器命中数 / `.poster` 盒 / 越界 / JS 报错 / 跳过即失败"后，16 个注入缺陷 **16/16 被拦下** |
| `20_html2pptx.py` | 缺图 / 坏图 / SVG / `data:` / 远程地址 / 变形 → **退出码 1 且不写文件**；黑色填充/边框/项目符号与 `oklch` 颜色按实测输出（数据级断言） |
| `40_verify_pptx.py` | 编号居中、文本落位、图片变形与裁切、包结构、页尺寸五项；此外**没有可比对的编号 / PPTX 里缺图 / 读不出 PPTX** 都判 FAIL，不再"没跑就算过" |
| `edge_cdp.py` | 进程查询不再把查询自身算成残留；`--kill-all` 严格 opt-in（不会误杀用户自己的浏览器） |
| `30_figure_tools.py` | `aspect` 在有 `<img>` 却一张都审计不到时返回 **2**；`trim` 保留 alpha、JPEG 用 95 质量并逐文件容错 |

压力矩阵的完整设计、39 个样本清单、10 轮各自发现并修掉的缺陷见
`@references/07-pressure-matrix.md`；多轮返工的经验与交付纪律见 `@references/06-field-notes.md`。

## 4. 版本记录

**v1.7.0** —— 经验沉淀 + 10 轮压力矩阵自查驱动的一轮修正（本轮共修 20+ 处，明细见 `07`）：

| # | 变更 |
|---|---|
| 1 | 新增 `references/06-field-notes.md`：接反馈/收敛版面/交付纪律/自我怀疑清单 |
| 2 | 新增 `references/07-pressure-matrix.md` + `scripts/60_pressure_matrix.py`：39 个中性样本 × 10 轮，逐项比对"该过的过、该拦的拦、不许 traceback" |
| 3 | **门禁不再"没跑就算过"**：选择器 0 命中、测不到文本、检查被跳过、编号无可比对项，一律 FAIL（`--allow-skip` / `--no-badge-check` 显式放行） |
| 4 | **新增门禁项**：`.poster` 盒是否等于画布、横向/纵向越界内容、页面 JS 报错、祖先 `transform`、`.panel-body` 缺失、图片 `<img>` 数与测到数是否吻合 |
| 5 | **溢出判定补全**：面板自身 `scrollHeight − clientHeight`（`overflow:hidden` 会把 body 的 scrollHeight 压平，实测漏检 59 段正文的溢出） |
| 6 | **"没有颜色"与"黑色"分离**（`-1` vs `0`）：黑色填充/边框/项目符号不再被静默丢掉；`oklch/lab/color()/color-mix` 经 canvas 归一化成 sRGB，取不到则告警 |
| 7 | **选择器可覆盖**：`--poster/--content/--column/--panel/--panel-body/--panel-head`，换模板不用改脚本 |
| 8 | 图片路径区分本地相对 / `data:` / `http(s):` / `file:`；坏图、SVG、0 字节文件逐图容错；图片变形改为**退出码 1** |
| 9 | 验收按对象名配对图片（不再按下标）；旋转过的图不再被误判"变形" |
| 10 | 运维修正：`edge_cdp.py` 进程查询不再自匹配（残留计数、`--kill-all` 误触发）；`99_selftest.py` 不再被自己的 `_work` 判失败、转换器退出码参与判定、跳过后不再报"全绿"；`50_snapshot.py` 同分钟快照不再互相覆盖；`trim` 保留 alpha |
| 11 | 文档同步：规则 13/14/15（颜色存在性、跳过即失败、选择器覆盖）、故障表新增 8 行、经验与压力矩阵两节新增 |
| 12 | **Windows 中文控制台编码**：所有脚本把 `stdout/stderr` 重设为 UTF-8（`errors="replace"`）—— 否则打印 `−/≈` 这类字符会 `UnicodeEncodeError` 崩掉（实测出现在一致性校验里，看着像版式失败）；`99_selftest.py` 与 `60_pressure_matrix.py` 故意**不**给子进程设 `PYTHONIOENCODING`，让这条路径始终被测到 |

**v1.7.1** —— 许可与署名（元数据，不改版式规则）：

| # | 变更 |
|---|---|
| 1 | 许可由"专有（保留所有权利）"改为 **Apache License 2.0**（宽松开源：允许商用、修改、闭源再分发） |
| 2 | `references/LICENSE` 重写为"中文摘要（授权 / 条件 / 免责 / 专利 / 原创性声明）+ 许可证全文" |
| 3 | 署名统一为 **Yangming Hu**（frontmatter `author` 由 `HYM` 改为 `Yangming Hu`；版权行同步） |
| 4 | `SKILL.md` 的 `license:` 字段与 `00-install.md` 第 6 节同步；`99_selftest.py` 的许可断言改为校验
Apache-2.0 标识 + 署名，并**禁止回退**（出现"专有许可"即 FAIL） |

**v1.6.0** —— 技能定位修正：从"HTML→PPTX"扩成"**文献/资料 → 学术墙报（HTML/PDF/可编辑 PPTX）**"：

| # | 变更 |
|---|---|
| 1 | 技能改名 **`academic-poster-builder`**（zip 根目录同步改名；`name` 字段与根目录名一致，自检含该断言） |
| 2 | frontmatter 的 `display_name` / `description` / `description_zh` / `description_en` 改为"输入文献资料 → 制备墙报 → 输出 HTML/PDF/可编辑 PPTX"口径 |
| 3 | 新增 **`references/05-prepare.md`**：制备流程（输入清单与合规红线 / 故事线与面板划分 / 墙报文案改写口径 / 从文献取图与引用 / 三种交付物 / 交付前清单） |
| 4 | `SKILL.md` 标题、引言、资源清单、何时用、工作流（新增第 0.5 步"制备"）同步；交付物表已含三种文件 |

**v1.5.x** —— 许可与署名完善：`references/许可与署名.md` 改名 **`references/LICENSE`**（ASCII 文件名）；
新增专有许可（保留全部权利）+ 授权范围 + 原创性声明 + 免责声明；frontmatter 新增 `license:` 字段；
`99_selftest.py` 新增第 0 步「包结构与许可」守卫（根目录只允许 `SKILL.md`/`references/`/`scripts/`/`templates/`，
**全包不得出现手机号或邮箱**）。

**v1.5.0** —— 首轮 10 轮压力矩阵自查驱动的一轮修正（`CFG.texts` 之外的兜底扫描、
`<dd>/<ol>` 缩进、`<li>` 重复输出、`<pre>` 换行、圆角裁切与逐角圆角、文本框重名、
`--pdf-size`/`--slide-mm` 解析报错、浏览器窗口默认在屏幕外等 11 项）。

**v1.4.0** —— 复杂情况压力矩阵（7 份样本）驱动的一轮修正：上标不抬起、下划线/删除线丢失、
`white-space:nowrap` 仍换行、`text-transform` 不生效、半透明文字变实色、`visibility:hidden` 照样输出、
空心项目符号丢失、同一图片多次引用重名、`transform: rotate` 静默错位、`box-shadow`/虚线边框静默丢失。

**v1.3.x** —— `object-fit:cover` 的 `srcRect` 裁切与 `contain/scale-down` 等比摆位；
四条边框都采都画（单边边框不再丢线）；图片圆角；缺图 → 退出码 1 且不写文件；
行数审计按"视觉行"聚合后交叉验证。**v1.2.0** 起色值与项目符号几何改由浏览器实测。

**v1.1.0 / v1.0.x** —— `50_snapshot.py` 默认自动识别 `*.html/*.pdf/*.pptx`；新增 `99_selftest.py`；
每轮新开标签页并留一张空白页（同一 CDP 实例可连跑多份墙报）；首个可分发版本。

### 可复现性（"能不能一模一样"）

| 检查 | 结果 |
|---|---|
| 同一 `shapes.json` 连续生成两次 | 部件逐字节相同；整文件 MD5 不同（差异只在 zip 条目时间戳） |
| 同一 HTML 两次测量 | 几何/文本/图片/边框/项目符号/门禁全部字段一致 |
| `60_pressure_matrix.py --all` 连跑 | 39 个样本结论稳定（同一份代码、同一台机器） |

**注意**：这里的"一模一样"指**同一份 HTML + 同一份素材**下的可复现性。要与某一份**历史 PPTX
文件**逐字节相同，需要那份原文件 + 原素材一起比对——缺其一无法验证。

## 5. 已知边界

- 文本落位阈值 10 px：LibreOffice 与 PowerPoint 对"精确行距首行基线"的处理最多差约 8 px，
  属可接受的渲染器差异 → 不要把两行文字排到只差 10 px 的位置上。
- macOS / Linux：浏览器路径与字体族按环境替换；建议先 `60_pressure_matrix.py --quick` 复测。
- PPTX→PDF 的页尺寸项依赖 LibreOffice kit。
- 不用 headless：实测 headless Edge 会挂死并残留进程，故 `edge_cdp.py` 采用
  "自己拉起最小化窗口 + CDP + 进程树清理"（见 `@references/04-operations.md`）。
- `30_figure_tools.py aspect` 只覆盖行内 style 写死尺寸的图；CSS 类定尺寸的图靠
  `40_verify_pptx.py` 验收（现在会有明确提示，不再"审计 0 张也算通过"）。
- PPTX 里图片按 `srcRect` 裁切、形状按几何绘制：**都与浏览器渲染一致，但不是"从浏览器截图"**，
  所以字体度量仍由 LibreOffice/PowerPoint 决定（±1–2% 字宽差）。
- 压力矩阵覆盖的是"工具链在各种输入下是否可靠"；**输入侧的内容质量**（故事线、文案口径）
  不在自动检查范围内，见 `@references/05-prepare.md` 与 `@references/06-field-notes.md`。

## 6. 版权与合规提示（不是法律意见）

用本技能**接单/收费本身不违法**——它是工具，产出物是你自己的排版工作。风险几乎都来自
"你放进去的素材"和"你的经营方式"，请逐项确认：

| 项目 | 风险 | 建议 |
|---|---|---|
| 论文插图（他人或自己已发表） | 期刊/出版社通常保留**图片版权**（即使你是作者，也常需 permission） | 用**自己课题组未发表原图**；必须用已发表图时走 RightsLink/期刊 permission，海报上标注来源 |
| 会议 banner / 会标 / logo | 商标权 + 组织方版权，商用尤其敏感 | 会议投稿海报属合理使用场景也要按其征稿要求；**接商业单**不要自带他人会标 |
| 字体 | `Microsoft YaHei` 等随 Windows 授权，**字体文件**不可随包分发；PPTX 只写字体名通常没问题 | 用于印刷/商用前确认字体授权；需要分发就换开源字体（思源黑体/Noto） |
| 图片素材网站 | 免费图库常有"禁止商用/需署名"条款 | 保存授权截图与来源链接 |
| 未发表数据 | 保密义务、个人数据（合作者姓名/单位） | 接单先签 NDA/授权书，交付后按约删除原始数据 |
| 收费经营 | 在中国境内持续经营性收费涉及工商登记与开票（经营性收入 vs 劳务报酬） | 偶发劳务按劳务报酬申报；常态化经营办理个体/公司登记并开票 |
| 本技能包自身 | **Apache License 2.0**（宽松开源：允许商用、修改、闭源再分发），条款见 `@references/LICENSE` | 分发/修改/商用都可以，但**须保留版权与许可声明、标注改动**；不提供担保 |

一句话：**工具无罪，素材和授权才是风险点**。做付费墙报时，最该做的是把"每张图/每个 logo 的
来源和授权"留痕（`@references/03-figures.md` 的图片来源说明正好可以用上）。

> 以上为一般性信息，不构成法律意见；具体到你的经营模式与所在地，请咨询律师或专业机构。
