# academic-poster-builder

**学术墙报制备（文献 → HTML / PDF / 可编辑 PPTX）** —— 面向 [DeepSeek Harness](https://github.com/deepseek-ai)
的技能包：把用户给的**文献与资料**做成学术墙报，并保证 PPTX 与浏览器/PDF 渲染**逐元素对齐**。

> 不是"HTML 转 PPT"的格式转换器，而是**从文献到成稿**的完整流程：读文献定故事线与面板 →
> 按墙报口径改写文案 → 处理图表、引用与授权 → 写成满足版面契约的 HTML → 导出三种交付物。

## 输入与输出

| | |
|---|---|
| **输入** | 论文/资料、图、数据、会议要求（画布尺寸、编号规则）、署名与基金信息、语言 |
| **输出** | `poster.html`（唯一真源）· `poster.pdf`（送印，按画布 mm 单页）· `poster.pptx`（可编辑：文本框 + 图片 + 形状，非贴图） |

## 内容

```
academic-poster-builder/
├── SKILL.md                      # 主文档：硬规则 + 工作流 + 交付物
├── references/
│   ├── 05-prepare.md             # 制备：输入清单 / 故事线与面板 / 文案改写 / 图表引用 / 合规红线
│   ├── 01-workflow.md            # 流水线、版面规格、几何门禁（15 项阈值）
│   ├── 02-pptx-conversion.md     # CSS → OOXML 映射规则（核心）
│   ├── 03-figures.md             # 取图、裁白边、纵横比、合并图
│   ├── 04-operations.md          # 浏览器/进程/权限/备份 + 故障速查表
│   ├── 06-field-notes.md         # 接反馈、收敛版面、交付纪律、自我怀疑清单
│   ├── 07-pressure-matrix.md     # 压力矩阵：39 个中性样本 × 10 轮自查
│   ├── 00-install.md             # 安装、依赖、实测验证记录、合规提示
│   └── LICENSE                   # 许可与署名（Apache-2.0 摘要 + 全文）
├── scripts/                      # 00 体检 / 10 测量门禁导出 / 20 生成 PPTX / 30 图片工具 /
│                                 # 40 验收 / 50 快照 / 60 压力矩阵 / check_package 打包门禁 /
│                                 # 99 自检 / edge_cdp / poster_measure.js
└── templates/poster_template.html # 起手模板（骨架，无示例数据）
```

## 仓库结构

```
academic-poster-builder/          ← 仓库根
├── README.md / LICENSE / NOTICE / RELEASE_NOTES.md
├── .gitattributes                ← 强制 LF（本包硬性要求）
├── .gitignore                    ← 挡住 *.zip / *.txt / *.xlsx / *.pdf / 图片 / __pycache__
├── .github/workflows/ci.yml      ← CI：校验 + 打 tag 自动发布
├── tools/
│   ├── build_zip.py              ← 确定性打包（同输入必得同字节）
│   └── scan_privacy.py           ← 发布前隐私体检（只用通用规则）
└── academic-poster-builder/      ← 技能包本体（根结构 = SKILL.md + references/ + scripts/ + templates/）
```

## 校验与发布（自动化）

推 `main` / 提 PR 时 CI 自动跑 8 道：LF 换行 → Python 语法 → 打包两次比对（可复现）→
包门禁（目录 + zip）→ 门禁自身 13 项负向测试 → 隐私体检 → 压力矩阵样本登记冒烟 → 环境体检。

**发布不再手工**：改完包 → 把 `SKILL.md` 的 `version` 与本次发布号对齐 → 打 tag 并推送：

```bash
git tag -a v1.8.0 -m "学术墙报制备 v1.8.0"
git push origin v1.8.0
```

CI 会先校验（tag 必须与包内 `version` 一致），通过后**自动创建或更新 Release**，
把确定性打包出的 zip 挂成附件，并清理过期附件。Release 描述取自 [RELEASE_NOTES.md](RELEASE_NOTES.md)。
也可在 Actions 页手动触发工作流（填一个已存在的 tag）补发或重发 Release。

> 发布作业需要 `GITHUB_TOKEN` 的写权限（仓库默认通常已有）。若报 403：
> Settings → Actions → General → Workflow permissions → 勾 "Read and write permissions"。

## 安装

把 `academic-poster-builder/` 整个目录放进 DSH 扫描的 skill 目录
（项目级 `.dsh/skills/` 或用户级 `<dshHome>/skills/`；**以 DSH 官方文档为准**）。
`SKILL.md` 是通用格式，也可用于其他支持 SKILL.md 的 agent。

## 运行环境

**在 DeepSeek Harness 中运行（推荐）**：DSH 自带 Python 已包含全部依赖
（playwright / PyMuPDF / python-pptx / Pillow / numpy），**无需安装任何包** ——
先调用 `load_workspace_dependencies` 取 Python 路径，再执行 `scripts/` 下的脚本。
PPTX→PDF 用 DSH 随附的 LibreOffice Kit（`LIBREOFFICE_KIT_CLI` / `LIBREOFFICE_KIT_NODE`）。

**在其他环境中运行**：`pip install playwright pymupdf python-pptx Pillow numpy`，
并自备 Edge/Chrome 与 LibreOffice。浏览器**不要用 headless**（本机实测会挂）。

## 用法（三步）

```bash
# 0) 自检：确认这台机器整条链路能跑通
python scripts/99_selftest.py

# 1) 制备：照 references/05-prepare.md 收输入、定面板、改文案，写成 poster.html

# 2) 测量 + 门禁 + 导出（一次会话；门禁不过只改 HTML 再重跑）
python scripts/10_measure_gate_export.py --html poster.html --canvas 3402x4536 \
    --pdf-size 900x1200 --pdf poster.pdf --png _work/preview.png \
    --shapes _work/shapes.json --report _work/gate.json --js scripts/poster_measure.js

# 3) 生成可编辑 PPTX + 验收
python scripts/20_html2pptx.py --shapes _work/shapes.json --out poster.pptx \
    --html poster.html --slide-mm 900x1200
python scripts/40_verify_pptx.py --pptx poster.pptx --shapes _work/shapes.json \
    --html poster.html --pdf-size 900x1200 --pdf-preview _work/preview.png \
    --pptx-pdf _work/poster_pptx.pdf --work _work
```

浏览器默认**在屏幕外启动**（不打扰用户）；同端口已在跑会自动复用。
压力矩阵自查：`python scripts/60_pressure_matrix.py`。

## 本仓库不含任何用户数据

仓库与发布附件里**没有任何实测数据、论文原文、图片素材或个人信息**；
技能包只有 `.md` / `.py` / `.js` / `.html` 文本与模板。`.gitignore` 已挡住
`*.zip` / `*.txt` / `*.xlsx` / `*.pdf` / 图片，避免误提交。

## 许可

**Apache License 2.0** —— 可自由使用、修改、分发（含商业与闭源分发），
但须保留版权与许可声明、标注改动。见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。

Copyright 2026 Yangming Hu.

> 本仓库与 DeepSeek、Anthropic 及其他任何组织**无隶属、赞助或背书关系**；
> 运行环境与安装位置的描述以各官方文档为准。
