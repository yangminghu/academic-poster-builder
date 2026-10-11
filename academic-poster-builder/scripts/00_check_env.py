# -*- coding: utf-8 -*-
"""00_check_env.py —— 环境体检：本技能每个脚本依赖的东西，一次性报出来。

    python 00_check_env.py [--libreoffice-cli "<cli.js>"] [--font "Microsoft YaHei"] [--json]

只报缺什么、怎么装，不改环境。退出码 0 = 无阻塞项（字体/LibreOffice 只警告）。
`--json` 只输出一行机器可读结果，供 99_selftest.py 复用（探测逻辑只此一份）。
"""
from __future__ import annotations

import argparse
import glob
import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys

for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
OK, BAD, WARN = "  [ok]  ", "  [FAIL]", "  [warn]"
REQUIRED = (("playwright", "pip install playwright"),
            ("pymupdf", "pip install pymupdf"),
            ("pptx", "pip install python-pptx"),
            ("PIL", "pip install Pillow"),
            ("numpy", "pip install numpy"))
# 字体族（去空格小写）→ 可能的**文件名**片段。不能拿族名前几个字符去撞文件名：
# "microsoftyahei"[:6]="micros" 会命中 micross.ttf（Microsoft Sans Serif），
# 于是字体缺失也报"已找到"（实测踩过）。
FONT_HINTS = {"microsoftyahei": ("msyh",), "microsoftjhenghei": ("msjh",),
              "simsun": ("simsun",), "simhei": ("simhei",),
              "notosanscjksc": ("notosanscjksc", "notosanssc"),
              "sourcehansanssc": ("sourcehansanssc", "sourcehansanscn"),
              "pingfangsc": ("pingfang",), "segoeui": ("segoeui",),
              "arial": ("arial",), "helvetica": ("helvetica",),
              "dejavusans": ("dejavusans",)}


def find_node() -> str | None:
    """node 解释器：环境变量 → PATH → 常见运行时目录。

    只按「目录形状」找，不写死任何厂商/产品路径，也不写百分号展开的环境变量串
    （那既是不可移植的绝对路径，也会让本包自己的可移植性检查失败）。
    """
    p = os.environ.get("LIBREOFFICE_KIT_NODE")
    if p and os.path.isfile(p):
        return p
    p = shutil.which("node")
    if p:
        return p
    pats = []
    local = os.environ.get("LOCALAPPDATA")
    home = os.path.expanduser("~")
    if local:
        # 打包类应用常见布局：<LOCALAPPDATA>/Programs/<厂商>/resources/runtime/<版本>/dependencies/node/bin
        pats.append(os.path.join(local, "Programs", "*", "resources", "runtime", "*",
                                 "dependencies", "node", "bin", "node.exe"))
    if home and home != "~":
        pats += [os.path.join(home, "AppData", "Local", "Programs", "*", "resources", "runtime", "*",
                              "dependencies", "node", "bin", "node.exe"),
                 # 自带运行时目录的通用形状：<home>/.<某产品>/<某产品>-runtimes/<运行时>/dependencies/node/bin
                 os.path.join(home, ".*", "*-runtimes", "*", "dependencies", "node", "bin", "node.exe"),
                 os.path.join(home, "scoop", "apps", "nodejs", "current", "node.exe"),
                 os.path.join(home, ".nvm", "versions", "node", "*", "bin", "node"),
                 os.path.join(home, ".volta", "bin", "node")]
    pats += ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node", "/snap/bin/node"]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def find_font(family: str) -> bool:
    fam = "".join(ch for ch in family.lower() if ch.isalnum())
    # 一个系统字体可能装在多个目录：Linux 用户字体、macOS 系统字体都不在 /Library/Fonts 下，
    # 只看一个目录会把"装了的字体"报成缺失（这个信号决定断行点是否与 PDF 一致，不能假阴）。
    dirs = {"Windows": [os.path.expandvars(r"%SystemRoot%\Fonts"),
                        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")],
            "Darwin": ["/System/Library/Fonts", "/Library/Fonts",
                       os.path.expanduser("~/Library/Fonts")],
            "Linux": ["/usr/share/fonts", "/usr/local/share/fonts",
                      os.path.expanduser("~/.local/share/fonts"),
                      os.path.expanduser("~/.fonts")]}.get(platform.system(), [])
    hints = FONT_HINTS.get(fam) or (fam,)
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for _root, _dirs, files in os.walk(d):
            for f in files:
                if any(h in "".join(ch for ch in f.lower() if ch.isalnum()) for h in hints):
                    return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--libreoffice-cli", default=os.environ.get("LIBREOFFICE_KIT_CLI"))
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--json", action="store_true", help="只输出一行 JSON（供脚本复用）")
    args = ap.parse_args()

    mods, missing = {}, []
    for mod, hint in REQUIRED:
        try:
            m = importlib.import_module(mod)
        except Exception as exc:
            mods[mod] = ""
            missing.append((mod, "%s   → %s" % (exc, hint)))
            continue
        ver = getattr(m, "__version__", "") or ""
        if not ver:      # 有的包（如 playwright）不暴露 __version__
            try:
                ver = importlib.metadata.version({"PIL": "Pillow", "pptx": "python-pptx"}.get(mod, mod))
            except Exception:
                ver = ""
        mods[mod] = ver or "ok"

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:                                     # 浏览器：自己拉起 + CDP，不依赖 headless
        import edge_cdp
        browser = edge_cdp.find_browser(None)
    except Exception:
        browser = None
    cli = args.libreoffice_cli if (args.libreoffice_cli and os.path.isfile(args.libreoffice_cli)) else None
    node, font_ok = find_node(), find_font(args.font)
    py_ok = sys.version_info >= (3, 10)
    ok = py_ok and not missing and bool(browser)

    if args.json:
        print(json.dumps({"python": platform.python_version(), "python_ok": py_ok,
                          "modules": mods, "missing": [m for m, _ in missing],
                          "browser": browser, "libreoffice_cli": cli, "node": node,
                          "font": args.font, "font_ok": font_ok, "ok": ok}, ensure_ascii=False))
        return 0 if ok else 1

    print("python %s (%s)" % (platform.python_version(), sys.executable))
    print((OK if py_ok else BAD) + "Python 版本（需 >= 3.10）")
    for mod, _ in REQUIRED:
        print((OK + "%-12s %s" % (mod, mods[mod])) if mods.get(mod) else (BAD + "%-12s 缺失" % mod))
    for _, detail in missing:
        print("          → %s" % detail)
    print((OK if browser else BAD) +
          "browser: %s" % (browser or "找不到 Edge/Chrome/Chromium（用 CHROME_PATH 指定）"))
    if cli:
        print(OK + "libreoffice kit: %s" % cli)
        print(("  [ok]  " if node else WARN) + "node: %s" % (
            node or "未找到（转换需要 node；用 LIBREOFFICE_KIT_NODE 指定）"))
    else:
        print(WARN + "未提供 LibreOffice kit cli（--libreoffice-cli 或 LIBREOFFICE_KIT_CLI）；"
                     "PPTX→PDF 校验会跳过")
    print((OK if font_ok else WARN) + '字体 "%s" %s' % (
        args.font, "已找到" if font_ok else "未确认（Linux/mac 换成实际安装的字体族名）"))
    bad = (0 if py_ok else 1) + len(missing) + (0 if browser else 1)
    print("\n结果：%s" % ("环境就绪" if bad == 0 else "有 %d 项需要处理" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
