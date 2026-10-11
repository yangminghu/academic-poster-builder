/* poster_measure.js —— 一次 evaluate 返回「元素实测 + 几何门禁」的全部数据。
 *
 * 用法：data = page.evaluate(open("scripts/poster_measure.js").read())
 *       10_measure_gate_export.py 会用它，并用 --canvas 覆盖 canvas 字段。
 *
 * 换主题/换模板时**只改下面 CFG**：rects 画成形状的元素，texts 变可编辑文本框
 * （mode: '' 普通 | 'hv' 双向居中），panels/columns 用于门禁。
 * 坐标取 DOM 实测；颜色/边框/圆角/object-fit/装饰/变换全部取计算样式，脚本里不写死主题色。
 */
() => {
  const CFG = {
    canvas: { w: 3402, h: 4536 },      // 缺省值；10_measure_gate_export.py 会用 --canvas 覆盖
    rects: ['.titleblock', '.metric', '.panel', '.panel-head', '.panel-head .num',
            '.note', '.concl .item .n', '.pnum'],
    // 正文块元素都在这里；**不在里面的也不会丢**：最后有一遍兜底扫描（sel='auto'）
    texts: [['h1', ''], ['.authors', ''], ['.affil', ''],
            ['.panel-head .num', 'hv'], ['.panel-head h2', ''],
            ['.metric .lab', ''], ['.metric .val', ''], ['.metric .cmp', ''],
            ['li', ''], ['p', ''], ['figcaption', ''], ['.note', ''],
            ['.refs .r .n', ''], ['.refs .r > span:not(.n)', ''],
            ['.concl .item .n', 'hv'], ['.concl .item > div:last-child', ''],
            ['.pnum .pn-val', ''], ['.pnum .pn-cn', '']],
    panels: '.col > .panel',
    panelBody: '.panel-body',
    panelHead: '.panel-head',
    columns: '.col',
    content: '.content',
    poster: '.poster'
  };
  /* CFG 可被外部覆盖（10_measure_gate_export.py 的 --poster/--content/--column/--panel/--panel-body）：
     换模板/换类名时不必改这个文件。 */
  if (typeof window !== 'undefined' && window.__APB_CFG__) {
    for (const k of Object.keys(window.__APB_CFG__)) if (window.__APB_CFG__[k]) CFG[k] = window.__APB_CFG__[k];
  }
  const ASC_FALLBACK = 0.8;   // 字体盒内 baseline 比例：实测不到时的缺省值
  /* 颜色解析：**必须区分"没有颜色"与"黑色"**。
     旧版把"解析失败"和 rgb(0,0,0) 都返回 0，于是黑色填充/黑色边框/黑色项目符号被静默丢掉
     （深色配色的墙报会整块变透明、白字压白底）。
     除 rgba()/rgb()/#hex 之外，计算值还可能是 oklch()/lab()/lch()/color()/color-mix() ——
     交给 canvas 归一化（浏览器会把任意合法 CSS 颜色转成 sRGB）。取不到返回 ok:false。 */
  const _cv = document.createElement('canvas');
  _cv.width = _cv.height = 1;
  const _cx = _cv.getContext && _cv.getContext('2d');
  const _colCache = new Map();
  const hexToRgb = h => {
    h = h.replace('#', '');
    if (h.length === 3 || h.length === 4) h = h.split('').map(c => c + c).join('');
    const n = parseInt(h.slice(0, 6), 16);
    if (isNaN(n)) return null;
    const a = h.length >= 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
    return {ok: true, rgb: n, a: a};
  };
  const numOrPct = v => {
    const f = parseFloat(v);
    if (isNaN(f)) return NaN;
    return String(v).trim().endsWith('%') ? Math.round(f * 2.55) : f;
  };
  const parseRgbText = s => {
    const m = String(s).match(/^rgba?\(([^)]+)\)$/);
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(x => x.length);
    const n = p.slice(0, 3).map(numOrPct);
    if (n.length < 3 || n.some(v => isNaN(v))) return null;
    return {ok: true, rgb: ((n[0] & 255) << 16) + ((n[1] & 255) << 8) + (n[2] & 255),
            a: p[3] === undefined ? 1 : (isNaN(parseFloat(p[3])) ? 0 : parseFloat(p[3]))};
  };
  const parseCol = c => {
    const key = String(c == null ? '' : c).trim();
    if (_colCache.has(key)) return _colCache.get(key);
    let out = {ok: false, rgb: 0, a: 0};
    const s = key.toLowerCase();
    if (s && s !== 'transparent' && s !== 'none' && s !== 'currentcolor' && s !== 'inherit') {
      if (s.charAt(0) === '#') {
        out = hexToRgb(s) || out;
      } else {
        out = parseRgbText(s) || out;
        if (!out.ok && _cx) {                 // oklch/lab/color()/color-mix … → canvas 归一化
          _cx.fillStyle = '#010203';          // 哨兵：赋值不生效时保持不变，据此判"不支持"
          try { _cx.fillStyle = key; } catch (e) { /* 非法颜色 */ }
          const norm = String(_cx.fillStyle || '').toLowerCase();
          if (norm && !(norm === '#010203' && s !== '#010203')) {
            out = (norm.charAt(0) === '#' ? hexToRgb(norm) : parseRgbText(norm)) || out;
          }
        }
      }
    }
    _colCache.set(key, out);
    return out;
  };
  const rgb = c => { const p = parseCol(c); return p.ok ? p.rgb : -1; };   // -1 = 没有/解析不到颜色
  const num = v => parseFloat(v) || 0;
  const alphaOf = c => { const p = parseCol(c); return p.ok ? p.a : 0; };
  /* 取"代表色"：优先 background-color；透明则取渐变里的第一个颜色停靠点。
     -1 = 没有颜色（下游必须按"存在性"判断，不能按真值判断）。 */
  const bgcol = cs => {
    const c = parseCol(cs.backgroundColor);
    if (c.ok && c.a > 0.001) return c.rgb;
    const stops = String(cs.backgroundImage || '').match(
      /(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\([^)]*\)/g);
    if (stops) {
      for (const st of stops) {
        const g = parseCol(st);
        if (g.ok && g.a > 0.001) return g.rgb;
      }
    }
    return -1;
  };
  /* 最近的不透明祖先背景（用于把半透明文字合成成不透明色） */
  const opaqueBg = el => {
    let p = el;
    while (p && p.nodeType === 1) {
      const cs = getComputedStyle(p);
      if (alphaOf(cs.backgroundColor) > 0.999) {
        const c = bgcol(cs);
        if (c) return c;
      }
      p = p.parentElement;
    }
    return 0xFFFFFF;
  };
  const blend = (fg, bg, a) => {
    const ch = (f, b) => Math.round(f * a + b * (1 - a));     // 一次取整，避免 ±1/255
    return (ch((fg >> 16) & 255, (bg >> 16) & 255) << 16)
         + (ch((fg >> 8) & 255, (bg >> 8) & 255) << 8)
         + ch(fg & 255, bg & 255);
  };
  const effAlpha = (cs, el) => {
    const pc = parseCol(cs.color);
    let a = pc.ok ? pc.a : 1, p = el;
    while (p && p.nodeType === 1) {
      const o = parseFloat(getComputedStyle(p).opacity);      // 不能用 num()：opacity:0 会被算成 1
      a *= isNaN(o) ? 1 : o;
      p = p.parentElement;
    }
    return a;
  };
  /* 不可见 = display:none / visibility:hidden / 祖先（含自身）opacity≈0。
     最后一条不能少：`.sr-only{opacity:0}` 那种"浏览器里看不见、PPT 里却实心显示"是静默错版。 */
  const hidden = el => {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') return true;
    let p = el;
    while (p && p.nodeType === 1) {
      const o = parseFloat(getComputedStyle(p).opacity);
      if (!isNaN(o) && o < 0.02) return true;
      p = p.parentElement;
    }
    return false;
  };
  const rect = el => {
    if (!el) return null;                    // 选择器匹配不到时不要整段测量崩掉
    const b = el.getBoundingClientRect();
    return {x: b.x, y: b.y, w: b.width, h: b.height};
  };
  /* 字体盒内 baseline 的比例：**实测**，不写死。不同字体族差 0.75–0.87，写死会在换字体后
     把上下标的偏移算偏。做法：插一个 0 高、vertical-align:baseline 的行内块，它的底边
     就是基线；与同行的字体盒（Range 矩形）相比即得比例。失败退回缺省值。 */
  const baselineRatio = (() => {
    try {
      const probe = document.createElement('div');
      probe.style.cssText = 'position:absolute;left:-99999px;top:0;line-height:1;visibility:hidden';
      const bcs = getComputedStyle(document.body);
      probe.style.fontFamily = bcs.fontFamily;
      probe.style.fontSize = bcs.fontSize || '16px';
      probe.innerHTML = '<span style="display:inline-block;width:0;height:0;' +
                        'vertical-align:baseline"></span>M';
      document.body.appendChild(probe);
      const rng = document.createRange();
      rng.selectNodeContents(probe);
      const boxes = Array.from(rng.getClientRects()).filter(r => r.height > 0);
      const marker = probe.firstChild.getBoundingClientRect();
      document.body.removeChild(probe);
      if (!boxes.length) return ASC_FALLBACK;
      const r = (marker.bottom - boxes[0].top) / boxes[0].height;
      return (r > 0.5 && r < 1.0) ? r : ASC_FALLBACK;
    } catch (e) {
      return ASC_FALLBACK;
    }
  })();
  const ASC = baselineRatio;
  const cls = el => (el.className && el.className.baseVal !== undefined)
                    ? el.className.baseVal : (el.className || '');
  /* transform：只认"纯旋转"（等比），返回旋转角与未变换尺寸；缩放/斜切只报 other */
  const tfOf = el => {
    const cs = getComputedStyle(el);
    if (!cs.transform || cs.transform === 'none') return null;
    const m = String(cs.transform).match(/^matrix\(([^)]+)\)$/);
    if (!m) return {other: true};
    const v = m[1].split(',').map(Number), a = v[0], b = v[1], c = v[2], d = v[3];
    if (Math.abs(Math.hypot(a, b) - 1) > 0.01 || Math.abs(Math.hypot(c, d) - 1) > 0.01) return {other: true};
    return {rot: Math.round(Math.atan2(b, a) * 180 / Math.PI * 100) / 100,
            ow: el.offsetWidth, oh: el.offsetHeight};
  };
  const contentBox = el => {
    const cs = getComputedStyle(el), b = el.getBoundingClientRect();
    const px = k => num(cs[k]);
    return {x: b.x + px('borderLeftWidth') + px('paddingLeft'),
            y: b.y + px('borderTopWidth') + px('paddingTop'),
            w: b.width - px('borderLeftWidth') - px('borderRightWidth') - px('paddingLeft') - px('paddingRight'),
            h: b.height - px('borderTopWidth') - px('borderBottomWidth') - px('paddingTop') - px('paddingBottom')};
  };
  /* 点是否落在"圆角矩形"内部（CSS border-radius 的可见区域） */
  const insideRound = (px, py, a, r) => {
    if (r <= 0) return px >= a.left && px <= a.right && py >= a.top && py <= a.bottom;
    const x1 = a.left + r, x2 = a.right - r, y1 = a.top + r, y2 = a.bottom - r;
    if (px < x1 && py < y1) return Math.hypot(px - x1, py - y1) <= r;
    if (px > x2 && py < y1) return Math.hypot(px - x2, py - y1) <= r;
    if (px < x1 && py > y2) return Math.hypot(px - x1, py - y2) <= r;
    if (px > x2 && py > y2) return Math.hypot(px - x2, py - y2) <= r;
    return px >= a.left && px <= a.right && py >= a.top && py <= a.bottom;
  };
  /* 被祖先 overflow:hidden（含圆角）裁切的情况：full=完全不可见，partial=只露出一部分。
     overflow:clip 一样会裁（只是不可滚动）→ 不能像旧版那样把它排除在外。
     每个会裁的祖先都要看：内层不裁不代表外层不裁。 */
  const clipCheck = (el, box) => {
    let p = el.parentElement;
    while (p && p !== document.body && p !== document.documentElement) {
      const pcs = getComputedStyle(p);
      if (pcs.overflow !== 'visible') {
        const a = p.getBoundingClientRect(), r = num(pcs.borderTopLeftRadius);
        let out = 0;
        for (const px of [box.x, box.x + box.w])
          for (const py of [box.y, box.y + box.h])
            if (!insideRound(px, py, a, r)) out++;
        if (out === 4) return {full: true};
        if (out > 0) return {partial: true};
        if (box.x < a.left - 1 || box.y < a.top - 1
            || box.x + box.w > a.right + 1 || box.y + box.h > a.bottom + 1) return {partial: true};
      }
      p = p.parentElement;
    }
    return null;
  };
  /* 逐角圆角：子元素若与"有圆角且会裁切"的祖先在同一角上重合，
     该角在浏览器里会被裁掉 → PPT 要按同半径圆角画（prstGeom 只能四角同半径）。 */
  const cornerInfo = el => {
    let p = el.parentElement;
    while (p && p.nodeType === 1) {
      const pcs = getComputedStyle(p);
      const pr = num(pcs.borderTopLeftRadius);
      if (pr > 1 && pcs.overflow !== 'visible') {
        /* 与父**内容盒**比（父有 border/padding 时子元素并不贴外框） */
        const pc = contentBox(p), b = el.getBoundingClientRect();
        const c = [0, 0, 0, 0];
        if (Math.abs(pc.x - b.left) < 2 && Math.abs(pc.y - b.top) < 2) c[0] = pr;
        if (Math.abs(pc.x + pc.w - b.right) < 2 && Math.abs(pc.y - b.top) < 2) c[1] = pr;
        if (Math.abs(pc.x + pc.w - b.right) < 2 && Math.abs(pc.y + pc.h - b.bottom) < 2) c[2] = pr;
        if (Math.abs(pc.x - b.left) < 2 && Math.abs(pc.y + pc.h - b.bottom) < 2) c[3] = pr;
        return c.some(v => v > 0) ? c : null;
      }
      p = p.parentElement;
    }
    return null;
  };
  const median = xs => {
    if (!xs.length) return 0;
    const s = xs.slice().sort((a, b) => a - b), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  /* 先登记所有"被选择器命中"的文本元素：段落遍历时遇到它们要**跳过**，
     否则 <li> 在 .note 里会被输出两次（.note 一份 + li 一份）。 */
  const picked = new Set();
  const plan = [];
  CFG.texts.forEach(([sel, mode]) => document.querySelectorAll(sel).forEach(el => {
    if (hidden(el)) return;
    picked.add(el); plan.push([el, mode, sel]);
  }));
  const PRESERVE = ws => ws === 'pre' || ws === 'pre-wrap' || ws === 'pre-line';

  /* 按段拆：block 子元素 / <br> 都是分段落点；每段记录首行字体盒高 fh 与行高 lhpx，
     以及该段自己的**文字原点 x / 右边界**（<dd>/<ol>/<blockquote> 的缩进不能丢）。
     Range.getClientRects() 给出的是**字体盒**（ascent+descent），不是 CSS 行盒。
     每个 run 还记录：下划线/删除线/大小写变换/垂直偏移（按视觉行实测基线）。 */
  function paragraphs(el, baseX, baseRight) {
    const cs0 = getComputedStyle(el), out = [];
    let cur = {rects: [], runs: [], lhpx: 0, ox: baseX, oright: baseRight};
    const flush = () => {
      if (cur.runs.some(r => r.t.trim())) {
        const rs = cur.rects;
        /* 先按垂直重叠把矩形聚成"视觉行"：同一行的字体盒互相重叠 ≥50%，
           相邻行几乎不重叠。基线偏移只在**同一行内**比较才有意义。 */
        const groups = [];
        for (const r of rs.slice().sort((a, b) => a.y - b.y)) {
          let hit = false;
          for (const g of groups) {
            const ov = Math.max(...g.map(q => Math.max(0, Math.min(r.y + r.h, q.y + q.h) - Math.max(r.y, q.y))));
            if (ov > 0.5 * Math.min(r.h, ...g.map(q => q.h))) { r.line = groups.indexOf(g); g.push(r); hit = true; break; }
          }
          if (!hit) { r.line = groups.length; groups.push([r]); }
        }
        const lineBase = groups.map(g => median(g.map(q => q.y + ASC * q.h)));
        const y = Math.min(...rs.map(r => r.y));
        const b = Math.max(...rs.map(r => r.y + r.h));
        const first = rs.reduce((a, c) => (c.y < a.y ? c : a), rs[0]);
        cur.runs.forEach(run => {
          const sh = (run.rects || []).map(q => (q.y + ASC * q.h) - lineBase[q.line]);
          run.shift = sh.length ? Math.round(median(sh) * 100) / 100 : 0;
          delete run.rects;
        });
        out.push({y, h: b - y, fh: first.h, runs: cur.runs, lhpx: cur.lhpx,
                  ox: cur.ox, oright: cur.oright});
      }
      cur = {rects: [], runs: [], lhpx: 0, ox: baseX, oright: baseRight};
    };
    const pick = node => {
      const rg = document.createRange(); rg.selectNodeContents(node);
      const rs = [];
      for (const rc of rg.getClientRects()) if (rc.height > 0) { rs.push({x: rc.x, y: rc.y, w: rc.width, h: rc.height}); cur.rects.push(rs[rs.length - 1]); }
      if (cur.runs.length) cur.runs[cur.runs.length - 1].rects = rs;
    };
    const mk = (cs, node, tag, sub) => {
      const deco = String(cs.textDecorationLine || cs.textDecoration || '');
      const a = effAlpha(cs, node);
      const col = rgb(cs.color);
      const colOk = col >= 0;          // -1 = 颜色解析不到（oklch 等极端情况）→ 由下游告警
      return {size: parseFloat(cs.fontSize),
              bold: +cs.fontWeight >= 600, italic: cs.fontStyle === 'italic',
              color: (colOk && a < 0.99) ? blend(col, opaqueBg(node), a) : (colOk ? col : 0),
              colorOk: colOk,
              hide: a < 0.02,
              u: deco.indexOf('underline') >= 0, s: deco.indexOf('line-through') >= 0,
              tt: cs.textTransform, sub: sub || tag === 'sub'};
    };
    (function walk(node, st, lhpx, keep) {
      if (node.nodeType === 3) {
        const s = keep ? node.textContent : node.textContent.replace(/\s+/g, ' ');
        if (s.length) { cur.runs.push({t: s, ...st}); cur.lhpx = Math.max(cur.lhpx, lhpx || 0); pick(node); }
        return;
      }
      if (node.nodeType !== 1) return;
      const tag = node.tagName.toLowerCase();
      if (tag === 'br') { flush(); return; }
      const cs = getComputedStyle(node);
      if (cs.visibility === 'hidden' || cs.display === 'none') return;    // 不可见内容不进 PPT
      if (node !== el && picked.has(node)) return;      // 已被别的选择器收走 → 不重复输出
      const ns = mk(cs, node, tag, st.sub);
      const own = parseFloat(cs.lineHeight) || lhpx;
      const keep2 = keep || PRESERVE(cs.whiteSpace);
      if (cs.display === 'block' && node !== el) {
        flush();
        const cb = contentBox(node);                   // 缩进块的文字原点
        cur.ox = cb.x; cur.oright = Math.max(cb.x + cb.w, baseRight);
        for (const ch of node.childNodes) walk(ch, ns, own, keep2);
        flush();
        return;
      }
      for (const ch of node.childNodes) walk(ch, ns, own, keep2);
    })(el, mk(cs0, el, el.tagName.toLowerCase(), false), parseFloat(cs0.lineHeight) || 0,
       PRESERVE(cs0.whiteSpace));
    flush();
    return out;
  }

  const rects = [], texts = [], images = [], bullets = [];
  let bulletsSkipped = 0, nestedCols = 0;
  CFG.rects.forEach(sel => document.querySelectorAll(sel).forEach(el => {
    if (hidden(el)) return;
    const cs = getComputedStyle(el);
    const rb = rect(el), clr = clipCheck(el, rb);
    if (clr && clr.full) return;
    rects.push({sel, cls: String(cls(el)), box: rb, clipped: !!(clr && clr.partial), fill: bgcol(cs),
                bw: [num(cs.borderTopWidth), num(cs.borderRightWidth),
                     num(cs.borderBottomWidth), num(cs.borderLeftWidth)],
                bc: [rgb(cs.borderTopColor), rgb(cs.borderRightColor),
                     rgb(cs.borderBottomColor), rgb(cs.borderLeftColor)],
                bstyle: cs.borderTopStyle, radius: num(cs.borderTopLeftRadius),
                bstyles: [cs.borderTopStyle, cs.borderRightStyle, cs.borderBottomStyle, cs.borderLeftStyle],
                corners: cornerInfo(el),
                shadow: cs.boxShadow !== 'none',
                outline: cs.outlineStyle !== 'none' && num(cs.outlineWidth) > 0,
                /* 圆角 + overflow:hidden 会裁切子元素背景，PPT 不会裁 → 要告警 */
                clipRisk: num(cs.borderTopLeftRadius) > 1 && cs.overflow !== 'visible'
                          && el.querySelector('*') !== null,
                tf: tfOf(el)});
  }));
  plan.forEach(([el, mode, sel]) => {
    const cs = getComputedStyle(el), outer = rect(el), box = contentBox(el);
    if (box.w < 4 || box.h < 4) return;
    const clr = clipCheck(el, outer);
    if (clr && clr.full) return;
    /* 内容比盒子宽（超长单词/nowrap）时 PPT 不能自动换行，否则换行点与浏览器不同 */
    const overflowX = el.scrollWidth > el.clientWidth + 1;
    const common = {sel, cls: String(cls(el)), mode, align: cs.textAlign,
                    color: rgb(cs.color), outer, clipped: !!(clr && clr.partial), tf: tfOf(el), overflowX,
                    outline: cs.outlineStyle !== 'none' && num(cs.outlineWidth) > 0,
                    nowrap: cs.whiteSpace === 'nowrap' || PRESERVE(cs.whiteSpace)};
    if (mode === 'hv') {
      const flat = [];
      paragraphs(el, box.x, box.x + box.w).forEach(p => flat.push(...p.runs));
      if (!flat.some(x => x.t.trim())) return;
      texts.push({...common, para: 0, npara: 1, box: outer, runs: flat, fh: outer.h, lhpx: 0});
      return;
    }
    /* 左对齐的"收缩宽度"元素（面板标题等）实测宽度 = 文字宽度，PPT 里字宽略大就会
       在不该换行处换行 → 可用宽度放宽到父容器内容盒右边界 */
    let rightEdge = box.x + box.w;
    if (el.parentElement && (cs.textAlign === 'left' || cs.textAlign === 'start')) {
      const pc = contentBox(el.parentElement);
      if (pc.x + pc.w > rightEdge + 1) rightEdge = pc.x + pc.w;
    }
    const paras = paragraphs(el, box.x, rightEdge);
    paras.forEach((pa, i) => {
      const runs = pa.runs.filter(r => !r.hide);
      if (!runs.length) return;
      texts.push({...common, para: i, npara: paras.length, lhpx: pa.lhpx, fh: pa.fh,
                  ox: pa.ox, oright: pa.oright,
                  box: {x: pa.ox, y: pa.y, w: Math.max(4, pa.oright - pa.ox), h: pa.h}, runs});
    });
  });
  /* 兜底扫描：选择器没覆盖到的块级文本元素（裸 <div>/<dd>/<dt>/<blockquote>/<pre>…）
     也收进来，否则这段文字在 PPT 里会整段消失（实测 <p> 就这样丢过）。
     注意：文字全在**行内子元素**里也算（`<div><span>甲</span><span>乙</span></div>` 常见于
     作者/单位/图标+标签行）——旧版要求"直接文本子节点"，这类整行都会消失，而且所有门禁
     都发现不了（它们只看被测到的东西）。 */
  document.querySelectorAll('body *').forEach(el => {
    if (picked.has(el) || hidden(el)) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'inline' || cs.display === 'inline-block' || cs.display === 'contents') return;
    for (let p = el.parentElement; p; p = p.parentElement) if (picked.has(p)) return;
    let hasOwnText = false;
    for (const n of el.childNodes) if (n.nodeType === 3 && n.textContent.trim().length) hasOwnText = true;
    if (!hasOwnText) {
      /* 没有直接文本子节点：只有在"块级子元素之外的文字"确实存在时才收，
         避免把纯容器（其内容由更深的块负责）重复输出。 */
      const inlineOnly = Array.from(el.childNodes).some(n =>
        n.nodeType === 3 ? n.textContent.trim().length > 0
                         : (n.nodeType === 1 && (function d(x) {
                             const ds = getComputedStyle(x).display;
                             if (ds !== 'inline' && ds !== 'inline-block' && ds !== 'contents') return false;
                             return Array.from(x.childNodes).some(y =>
                               y.nodeType === 3 ? y.textContent.trim().length > 0 : (y.nodeType === 1 && d(y)));
                           })(n)));
      if (!inlineOnly) return;
    }
    const box = contentBox(el);
    if (box.w < 4 || box.h < 4) return;
    const outer = rect(el), clr = clipCheck(el, outer);
    if (clr && clr.full) return;
    let re2 = box.x + box.w;
    if (el.parentElement && (cs.textAlign === 'left' || cs.textAlign === 'start')) {
      const pc = contentBox(el.parentElement);
      if (pc.x + pc.w > re2 + 1) re2 = pc.x + pc.w;
    }
    const paras = paragraphs(el, box.x, re2);
    const flat = [];
    paras.forEach((pa, i) => {
      const runs = pa.runs.filter(r => !r.hide);
      if (runs.length) flat.push({...pa, para: i, npara: paras.length, runs});
    });
    if (!flat.length) return;
    flat.forEach(pa => texts.push({
      sel: 'auto', cls: String(cls(el)), mode: '', align: cs.textAlign, color: rgb(cs.color),
      outer, clipped: !!(clr && clr.partial), tf: tfOf(el), overflowX: el.scrollWidth > el.clientWidth + 1,
      outline: cs.outlineStyle !== 'none' && num(cs.outlineWidth) > 0,
      nowrap: cs.whiteSpace === 'nowrap' || PRESERVE(cs.whiteSpace),
      para: pa.para, npara: pa.npara, lhpx: pa.lhpx, fh: pa.fh, ox: pa.ox, oright: pa.oright,
      box: {x: pa.ox, y: pa.y, w: Math.max(4, pa.oright - pa.ox), h: pa.h}, runs: pa.runs}));
  });
  document.querySelectorAll('img').forEach(el => {
    if (hidden(el)) return;
    const ib = rect(el), icl = clipCheck(el, ib);
    if (icl && icl.full) return;
    const cs = getComputedStyle(el);
    /* object-fit / object-position / border-radius / transform 都要给下游：
       cover 必须按 srcRect 裁切，直接按框拉伸会把横幅压扁（实测）。 */
    images.push({src: el.getAttribute('src'), box: ib, clipped: !!(icl && icl.partial),
                 fit: cs.objectFit, pos: String(cs.objectPosition || '50% 50%'),
                 radius: num(cs.borderTopLeftRadius), tf: tfOf(el)});
  });
  /* 项目符号（li::before）：只收集**真的画出来了**的伪元素；没有 ::before（原生
     list-style 圆点）或尺寸为 0 的必须跳过，否则会给每个 li 补一个假方块。
     有描边无底色的（空心符号）也要收，否则会被整颗丢掉。 */
  document.querySelectorAll('li').forEach(el => {
    if (hidden(el)) return;
    const b = el.getBoundingClientRect();
    if (b.width < 4) return;
    const ps = getComputedStyle(el, '::before');
    const px = k => num(ps[k]);
    const content = String(ps.content || '').trim();
    const w = px('width'), h = px('height');
    const fill = rgb(ps.backgroundColor);
    const blw = px('borderTopWidth'), blc = rgb(ps.borderTopColor);
    const bw2 = px('borderLeftWidth'), bh2 = px('borderBottomWidth'), br2 = px('borderRightWidth');
    const hasBorder = Math.max(blw, bw2, bh2, br2) > 0;
    if (!content || content === 'none' || content === 'normal' || w <= 0 || h <= 0) {
      bulletsSkipped++; return;
    }
    /* fill/line = -1 表示"没有颜色"；黑色（#000）是 0，必须按存在性判断 */
    const hasFill = fill >= 0, hasLine = hasBorder && blc >= 0;
    if (!hasFill && !hasLine) { bulletsSkipped++; return; }     // 纯文字符号（◆ 等）不画方块
    bullets.push({box: {x: b.x + px('left'), y: b.y + px('top'), w, h},
                  fill: hasFill ? fill : -1, line: hasLine ? blc : -1,
                  lw: hasLine ? Math.max(blw, bw2, bh2, br2) : 0,
                  radius: px('borderTopLeftRadius') || 0});
  });
  /* 已经用逐角圆角还原过裁切的元素：不再报"被裁切"（.panel-head 这种贴角子元素就是） */
  rects.forEach(rc => { if (rc.corners) rc.clipped = false; });
  /* 已经被逐角圆角处理过的父容器：不再告警"PPT 不裁切" */
  rects.forEach(rc => {
    if (!rc.clipRisk) return;
    const b = rc.box;
    rc.clipRisk = !rects.some(o => o.corners && o.box.x >= b.x - 2 && o.box.y >= b.y - 2
                                 && o.box.x + o.box.w <= b.x + b.w + 2
                                 && o.box.y + o.box.h <= b.y + b.h + 2);
  });
  /* 嵌套 .col（.col 里还有 .col）会让门禁的"栏底对齐/栏区边距"算出无意义的结果 */
  document.querySelectorAll(CFG.columns).forEach(c => {
    if (c.querySelector(CFG.columns)) nestedCols++;
  });

  /* ---------------- 几何门禁 ---------------- */
  const gate = {};
  gate.bodyScroll = [document.body.scrollWidth, document.body.scrollHeight];
  gate.docScroll = [document.documentElement.scrollWidth, document.documentElement.scrollHeight];
  const poster = document.querySelector(CFG.poster), content = document.querySelector(CFG.content);
  /* 选择器命中数：为 0 时下游必须**判失败**（"检查没跑成"≠"通过"），这里把数字给出来 */
  gate.selectors = {
    poster: CFG.poster, content: CFG.content, columns: CFG.columns, panels: CFG.panels,
    nPoster: poster ? 1 : 0, nContent: content ? 1 : 0,
    nColumns: document.querySelectorAll(CFG.columns).length,
    nPanels: document.querySelectorAll(CFG.panels).length,
    panelBody: CFG.panelBody || '.panel-body',
    nPanelBodies: document.querySelectorAll(CFG.panelBody || '.panel-body').length
  };
  gate.poster = rect(poster);
  gate.content = content ? rect(content) : null;
  gate.contentScroll = content ? [content.scrollWidth, content.scrollHeight] : null;
  gate.nestedCols = nestedCols;
  /* 祖先 transform（"按 2× 设计再整体 scale(0.5)"这种写法）：rect 全是变换后的坐标，
     栏高/画布却是布局尺寸 → 门禁会误判 PASS，而 PPT 里整张墙报缩在左上角。
     只要 .poster 或它的祖先有非 none 的 transform 就报出来。 */
  gate.ancestorTransform = (() => {
    let p = poster, found = null;
    while (p && p.nodeType === 1) {
      const t = getComputedStyle(p).transform;
      if (t && t !== 'none') found = (String(cls(p)) || p.tagName.toLowerCase()) + ':' + t.slice(0, 40);
      p = p.parentElement;
    }
    return found;
  })();
  /* 横向/纵向越界：poster 外（或画布外）的内容会被 overflow:hidden 静默裁掉 */
  gate.clip = {n: 0, samples: []};
  if (poster) {
    const pb = poster.getBoundingClientRect();
    poster.querySelectorAll('*').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.display === 'none' || cs.visibility === 'hidden') return;
      const b = el.getBoundingClientRect();
      if (!b.width && !b.height) return;
      if (b.right > pb.right + 2 || b.bottom > pb.bottom + 2
          || b.left < pb.left - 2 || b.top < pb.top - 2) {
        gate.clip.n++;
        if (gate.clip.samples.length < 5) {
          gate.clip.samples.push({cls: String(cls(el)) || el.tagName.toLowerCase(),
                                  l: Math.round(b.left - pb.left), t: Math.round(b.top - pb.top),
                                  r: Math.round(b.right - pb.right), b: Math.round(b.bottom - pb.bottom)});
        }
      }
    });
  }
  gate.panels = [];
  let panelsNoBody = 0;
  document.querySelectorAll(CFG.panels).forEach((p, i) => {
    const body = p.querySelector(CFG.panelBody || '.panel-body');
    const head = p.querySelector(CFG.panelHead || '.panel-head');
    const title = (head ? head.innerText : p.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    /* 没有 .panel-body 时**不要**崩：记一条 noBody，由下游判失败并提示选择器不对 */
    if (!body) {
      panelsNoBody++;
      gate.panels.push({i, title, panel: rect(p), head: head ? rect(head) : null, noBody: true,
                        bodyScroll: 0, bodyClient: 0, childOverflow: 0, overlap: 0});
      return;
    }
    /* 内容被 overflow:hidden 裁掉时 scrollHeight 会被"压平"，所以同时看
       scrollHeight 与最后一个子元素的实际底边 */
    const kids = Array.from(body.children);
    const boxBottom = kids.length
      ? Math.max(...kids.map(k => k.getBoundingClientRect().bottom)) - body.getBoundingClientRect().top : 0;
    /* flex 会把子元素压扁（box 不溢出），但子元素**自己的内容**仍会溢出 → 也要算 */
    const kidOver = Math.max(0, ...kids.map(k => k.scrollHeight - k.clientHeight));
    /* .panel 自己也是 overflow:hidden：内容超出时 body.scrollHeight 可能"被压平"
       （body 长高了，但 panel 裁掉了它）→ 必须看 panel.scrollHeight - panel.clientHeight
       （overflow:hidden 的元素 scrollHeight 仍报内容高）。实测：注 59 段正文时只有这一项报出来。 */
    const panelOver = Math.max(0, p.scrollHeight - p.clientHeight);
    gate.panels.push({i, title, panel: rect(p), head: head ? rect(head) : null,
                      bodyScroll: body.scrollHeight,
                      bodyClient: body.clientHeight,
                      childOverflow: Math.max(kidOver, Math.round(boxBottom - body.clientHeight)),
                      panelOver: panelOver,
                      overlap: Math.max(0, body.scrollHeight - body.clientHeight)});
  });
  gate.panelsNoBody = panelsNoBody;
  gate.columns = [];
  /* 栏里的面板用 ':scope > 子选择器' 找：CFG.panels 可能写成 '.col > .panel'，
     必须先剥掉祖先部分，否则 ':scope > .col > .panel' 一个也匹配不到（实测踩过）。 */
  const panelChildSel = (() => {
    const parts = String(CFG.panels).split('>').map(s => s.trim()).filter(Boolean);
    return parts.length > 1 ? parts[parts.length - 1] : String(CFG.panels).trim();
  })();
  document.querySelectorAll(CFG.columns).forEach(c => {
    if (c.querySelector(CFG.columns)) return;                 // 嵌套列不算独立栏
    const boxes = Array.from(c.querySelectorAll(':scope > ' + panelChildSel)).map(rect).filter(Boolean);
    if (!boxes.length) return;
    const gaps = [];
    for (let k = 1; k < boxes.length; k++) gaps.push(Math.round(boxes[k].y - (boxes[k - 1].y + boxes[k - 1].h)));
    gate.columns.push({panels: boxes.length, firstTop: Math.round(boxes[0].y),
                       lastBottom: Math.round(boxes[boxes.length - 1].y + boxes[boxes.length - 1].h), gaps});
  });
  /* 栏组左右留白：栏区必须和页头(标题块/指标行)用同一对左右边距，
     否则右栏会比页头缩进去一条（实测 48 px = 12.7 mm）。 */
  const cols = Array.from(document.querySelectorAll(CFG.columns))
                    .filter(c => !c.querySelector(CFG.columns)).map(rect).filter(Boolean);
  gate.colEdge = (cols.length && gate.content) ? {
    left: Math.round(Math.min(...cols.map(b => b.x)) - gate.content.x),
    right: Math.round(gate.content.x + gate.content.w - Math.max(...cols.map(b => b.x + b.w)))
  } : null;
  /* 图片：<img> 总数 vs 真的测到的数量（差异必须能解释，否则是静默丢图） */
  gate.images = {nTags: document.querySelectorAll('img').length, nHidden: 0, nClipped: 0,
                 nMeasured: images.length, nNoSrc: 0};
  document.querySelectorAll('img').forEach(el => {
    if (hidden(el)) { gate.images.nHidden++; return; }
    const ic = clipCheck(el, rect(el));
    if (ic && ic.full) { gate.images.nClipped++; return; }
    if (!el.getAttribute('src')) gate.images.nNoSrc++;
  });
  return {rects, texts, images, bullets, bulletsSkipped, nestedCols, gate, canvas: CFG.canvas,
          baselineRatio: ASC};
}
