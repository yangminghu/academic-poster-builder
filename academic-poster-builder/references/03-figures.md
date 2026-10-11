# 03 · 图片：取图、裁白边、合并、核对

## 1. 从 PPT / PDF 里取图

```bash
<node> "<kit>/lib/cli.js" convert --input deck.pptx --output _work/deck.pdf
```
```python
import pymupdf
d = pymupdf.open(pdf)
pix = d[page_index].get_pixmap(dpi=300)          # 300 dpi 起步，供 90×120 cm 印刷
page = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
```
不要用浏览器渲染 PPT（慢且比例不稳）；不要只截 100–150 dpi——一张 22 cm 宽的图在 150 dpi
需要 ≈1300 px，300 dpi 需要 ≈2600 px。

**帧锚点法**（精确定位被裁的图）：① 在参考图里检测长直线（坐标框）取并集 → `ref_frame`；
② 同一页 300 dpi 渲染里同样检测 → `src_frame`（可先裁掉相邻面板）；③
`scale = src_frame_w / ref_frame_w`，两轴差 >0.8% 判失败；④ 按参考图边距映射裁剪
（`x0 = src_x0 − ref_x0×scale`）；⑤ 把越界的邻居内容（上一行标题、旁边相邻面板）涂白；
⑥ 等价性自检：裁好的图缩回参考图尺寸、高斯模糊 σ≈2.5 后逐像素比，`|Δ|>40` 的像素占比
**<1.5%** 才允许替换，否则保留用户给的原图。

## 2. 裁白边（必做）

素材常带不对称白边（实测一张合并图 左 7 px / 右 99 px），版面上会被读成"右边留白太多"。

```bash
python scripts/30_figure_tools.py trim --assets assets --margin 10 --backup _work/pretrim
```
统一裁到"墨迹包围盒 + 10 px"（灰度 <245 视为墨迹）；原图先备份；裁完纵横比会变，
**必须同步更新 HTML 的 width/height**。深色满幅的图会被判成"没有白边"，属正常结果。

## 3. 纵横比审计（每次改尺寸后）

```bash
python scripts/30_figure_tools.py aspect --html poster.html --shapes _work/shapes.json
```
输出每张图的 `html w/h` vs 源图宽高比，误差 >0.5% 报红（退出码 1）。只改 width 不改 height
是最常见的变形来源，PPT 里被拉伸得更明显。

**"一张图都没审计到"不等于通过**：图片用 CSS 类定尺寸、或 `style` 用单引号/不带单位时，
旧版会打印一句提示然后返回 0。现在会打印 `<img>` 总数 vs 可审计数，**有 `<img>` 却一张都审计不到
就返回退出码 2**（确实不需要这项检查时加 `--allow-empty`）。

**旋转过的图不参与纵横比判定**：`getBoundingClientRect()` 给的是旋转后包围盒，比例天然不等
（实测被报成"变形 2.86%"）。

**两个例外（脚本自动处理，不要手动放行）**：`object-fit: cover/contain` 的横幅（会议 banner）
显示框比例本来就不等于源图——那是**裁切/等比缩放**，由 `20_html2pptx.py` 按
`object-position` 写进 `srcRect` 做出来（实测：不做就会把横幅拉扁）；给了 `--shapes` 时
`aspect` 按实测 `object-fit` 自动跳过，没有 `--shapes` 时用 `--skip banner`。
宽度由 CSS 类指定的图 `aspect` 查不到（会提示"没有检查到任何图片"），所以**成品验收必须用
`40_verify_pptx.py`**——它读浏览器实测框，并对 cover/contain 图检查"是否真的裁切/等比"。

## 4. 合并图与多图注

```html
<figure class="cent">
  <img class="fx" style="width:964px;height:293px" src="assets/merged_ab.png" alt="...">
  <figcaption><b>Fig. 4</b>&nbsp;Left panel — …</figcaption>
  <figcaption><b>Fig. 5</b>&nbsp;Right panel — …</figcaption>
</figure>
```
一张图 + **两条图注**，图号保持原编号（避免全文重编号与交叉引用失配）。合并后纵横比通常变大、
高度减少 → 该栏出现余量，可用来放大别的图。

## 5. 剔除/替换图片的连带改动

| 动作 | 必须同步改 |
|---|---|
| 删一张图 | 图注、图号（后续全部 −1）、正文里的 "Fig. N"、图片来源说明的图号区间 |
| 换图 | 图注数字与图内标注是否一致（一定要对着图核） |
| 换合并图 | 两条图注分别对应左右/上下哪个面板 |
| 裁白边 | HTML 的 width/height（按新纵横比） |

用 `grep "Fig\. " poster.html` 逐个核，再核来源说明里的图号区间。

## 6. 图片来源说明（建议保留）

> **图片来源说明（按项目改写）**：写明每张图来自哪篇文献、哪些是课题组原始图、
> 哪些数据集未采用以及原因。评审与答辩时能省很多解释，也是授权留痕的一部分。

**图片来源的真实性也是合规问题**，见 `@references/00-install.md` 第 6 节。
