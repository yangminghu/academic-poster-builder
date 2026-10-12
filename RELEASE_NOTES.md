面向 **DeepSeek Harness** 的学术墙报制备技能包：把用户给的**文献与资料**做成学术墙报，输出
**HTML / PDF / 可编辑 PPTX** 三种同源交付物，并保证 PPTX 与浏览器/PDF 渲染**逐元素对齐**。

> 不是"HTML 转 PPT"的格式转换器，而是**从文献到成稿**的完整流程：读文献定故事线与面板 →
> 按墙报口径改写文案 → 处理图表、引用与授权 → 写成满足版面契约的 HTML → 导出并验收。

## 本版变更（v1.8.0）

打包与发布**自动化** —— 打 tag 即自动校验并出 Release，不再手工拖文件：

| # | 变更 |
|---|---|
| 1 | 新增 `scripts/check_package.py`：把技能包规范变成**可执行门禁**（根目录结构 / frontmatter 必填项 / `@references` 引用落地 / 许可自洽 / 编码 / 隐私 / zip 容器规范），带 **13 项负向测试** |
| 2 | `99_selftest.py` 第 0 步改为调用该门禁（单一真源），自检由 18 步合并为 **13 步** |
| 3 | 新增 `tools/build_zip.py`：**确定性打包**（固定顺序/时间戳/权限位）—— 同输入必得同字节，可复现 |
| 4 | 新增 `tools/scan_privacy.py`：发布前隐私体检（只用通用规则，具体标识经 `PRIVACY_DENY` 运行时传入） |
| 5 | 新增 `.github/workflows/ci.yml`：push/PR 自动跑 8 道校验；**打 tag 自动创建/更新 Release 并挂 zip** |

## 内容（22 个文件）

- **SKILL.md** —— 15 条硬规则 + 工作流 + 交付物 + 已知边界
- **references/**（9 份）—— 制备流程、流水线、CSS→OOXML 映射、图片工具、运维与故障速查、
  实战经验、压力矩阵、安装与实测记录、许可（Apache-2.0 摘要 + 全文）
- **scripts/**（11 个）—— 环境体检、测量+门禁+导出、生成 PPTX、图片裁白边/纵横比、
  一致性验收、版本快照、压力矩阵、**打包门禁**、自检、CDP 浏览器管理、DOM 实测脚本
- **templates/poster_template.html** —— 起手模板（骨架，无示例数据）

## 能力

- **15 项几何门禁**：画布尺寸、选择器命中、`.poster` 盒、面板溢出（含被 flex 压扁的子元素）、
  栏底对齐、栏内间隙、栏区左右留白、越界内容、祖先 transform、文本/图片覆盖、页面 JS 报错、
  画布↔目标 mm、每格余量、底边距、PDF 页数与尺寸
- **"没跑成"不许算"通过"**：选择器 0 命中、测不到文本、检查被跳过、编号无可比对项，一律 FAIL
- **PPT↔PDF 一致性验收**：编号居中、文本落位、图片变形与裁切、包结构、页尺寸
- **压力矩阵**：39 个**中性样本**（运行时现场生成、不进包）× 10 轮，逐项比对
  "该过的过、该拦的拦、不许 traceback"，含门禁假通过攻击与 CLI 错误输入
- **行内与样式**：上下标、下划线/删除线、大小写变换、`nowrap`/`pre`、半透明合成、隐藏元素、
  旋转、逐角圆角裁切、单边/虚线边框、`object-fit` 裁切、深色配色、`oklch/lab` 归一化
- 浏览器默认**屏幕外启动**（不打扰使用者）；缺图 → 退出码 1 且不产出残缺 PPTX

## 安装

把 `academic-poster-builder/` 整个目录放进 DSH 扫描的 skill 目录
（项目级 `.dsh/skills/` 或用户级 `<dshHome>/skills/`；**以 DSH 官方文档为准**）。
`SKILL.md` 是通用格式，也可用于其他支持 SKILL.md 的 agent。

## 运行环境

DSH 自带 Python 已包含全部依赖（playwright / PyMuPDF / python-pptx / Pillow / numpy），
**无需安装任何包**；PPTX→PDF 用 DSH 随附的 LibreOffice Kit。浏览器**不要用 headless**。

## 自检与门禁

```bash
python scripts/check_package.py            # 打包门禁（离线，不需要浏览器）
python scripts/check_package.py --selftest # 门禁自身的 13 项负向测试
python scripts/99_selftest.py              # 全链路自检（13 步：门禁 → 体检 → 浏览器 → 门禁导出 → PPTX → 一致性校验）
python scripts/60_pressure_matrix.py --quick   # 3 个冒烟样本
python scripts/60_pressure_matrix.py --all     # 全量 39 个样本 × 10 轮
```

## 许可

**Apache License 2.0** —— 可自由使用、修改、分发（含商业与闭源分发），须保留版权与许可声明、标注改动。
见 [LICENSE](https://github.com/yangminghu/academic-poster-builder/blob/main/LICENSE) 与
[NOTICE](https://github.com/yangminghu/academic-poster-builder/blob/main/NOTICE)。

Copyright 2026 Yangming Hu。

本仓库与发布附件均**不含任何用户数据、论文原文、图片素材或个人信息**；
本仓库与 DeepSeek、Anthropic 及其他任何组织**无隶属、赞助或背书关系**。
