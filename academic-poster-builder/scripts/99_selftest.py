# -*- coding: utf-8 -*-
"""99_selftest.py —— 技能包自检：在一台新机器上验证整条链路能不能跑通。

    python scripts/99_selftest.py                     # 用包内模板测（默认）
    python scripts/99_selftest.py --html poster.html  # 用自己的墙报测（门禁会按你的版式判）

六步（0–5），任何一步失败都会指出是哪一环：
  0) 包结构与许可（根目录结构 / LICENSE 是 Apache-2.0 / frontmatter / 无联系方式泄漏）
  1) 环境体检（调用 00_check_env.py --json，探测逻辑只此一份）
  2) 起浏览器（默认屏幕外；同端口已在跑会复用）
  3) 测量 + 门禁 + 导出 PDF/预览图（10_measure_gate_export.py）
  4) 生成可编辑 PPTX（20_html2pptx.py）
  5) 一致性校验（PPTX→PDF → 40_verify_pptx.py；需要 LibreOffice kit）

退出码 0 = 全绿；1 = 有环节失败。缺 LibreOffice kit 时第 5 步记为 SKIP 并在结论里明说
（"PASS（含 N 项跳过：…）"），绝不假装全绿；要把它当硬门禁用 --require-verify。
结束时会关掉**自己起的**浏览器（进程树清理；绝不用 --kill-all，以免关掉用户的浏览器）。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import edge_cdp          # noqa: E402  （同目录模块，浏览器探测逻辑只此一份）

STEPS: list[tuple[str, str, str]] = []       # (名称, 状态, 说明)；状态 ∈ PASS/FAIL/SKIP/WARN


def _record(name: str, status: str, detail: str = "") -> bool:
    STEPS.append((name, status, detail))
    print("  [%s] %s%s" % (status, name, ("  —— " + detail) if detail else ""))
    return status == "PASS"


def step(name: str, ok: bool, detail: str = "") -> bool:
    return _record(name, "PASS" if ok else "FAIL", detail)


def skip(name: str, detail: str = "") -> bool:
    """跳过 ≠ 通过：记 SKIP，结论里必须点出来（--require-verify 时改记 FAIL）。"""
    return _record(name, "SKIP", detail)


def warn(name: str, detail: str = "") -> bool:
    """只是提示，不影响退出码（例如包被解压到了改过名的目录）。"""
    return _record(name, "WARN", detail)


def frontmatter(text: str) -> str:
    """取 SKILL.md 的 frontmatter 正文；没有 frontmatter 时返回空串（不抛 IndexError）。"""
    if not text.startswith("---"):
        return ""
    parts = text.split("---")
    return parts[1] if len(parts) > 1 else ""


def run(cmd):
    # 解码固定 utf-8（脚本自己会把 stdout/stderr 重设成 utf-8）；**不替子进程设
    # PYTHONIOENCODING** —— 让每个脚本自己扛住 Windows 中文控制台的 GBK 编码，
    # 否则子进程打印 "−/≈" 之类字符会 UnicodeEncodeError 崩掉（实测踩过）。
    env = dict(os.environ)
    env.pop("PYTHONIOENCODING", None)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=str(HERE.parent / "templates" / "poster_template.html"))
    ap.add_argument("--canvas", default="3402x4536")
    ap.add_argument("--pdf-size", default="900x1200")
    ap.add_argument("--slide-mm", default="900x1200")
    ap.add_argument("--port", type=int, default=9223)
    ap.add_argument("--work", default="_work/_selftest")
    ap.add_argument("--font", default="Microsoft YaHei")
    ap.add_argument("--libreoffice-cli", default=os.environ.get("LIBREOFFICE_KIT_CLI"))
    ap.add_argument("--require-verify", action="store_true",
                    help="缺 LibreOffice kit 时把「PPTX→PDF 一致性校验」从 SKIP 升级为 FAIL")
    ap.add_argument("--keep", action="store_true", help="保留中间产物")
    a = ap.parse_args()

    # 每次自检都从零开始：清掉上次的产物，避免"上一轮的 PDF/PPTX 被当成这一轮跑出来的"。
    work = os.path.abspath(a.work)
    guard = {os.path.abspath(os.curdir), str(HERE), str(HERE.parent)}
    if work in guard:
        print("--work 不能指向当前目录或技能包目录：%s" % work)
        return 1
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    a.work = work
    html = os.path.abspath(a.html)
    print("== academic-poster-builder 自检 ==")
    print("   python %s" % sys.version.split()[0])
    print("   目标 HTML: %s" % html)
    print("   工作目录: %s（已清空）" % a.work)

    print("\n0) 包结构与许可")
    root = HERE.parent
    entries = sorted(p.name for p in root.iterdir())
    allowed = {"SKILL.md", "references", "scripts", "templates"}
    # 下划线开头的是运行期工作目录（_work 等），不是包内容：允许存在，不算结构违规。
    extra = [e for e in entries if e not in allowed and not e.startswith("_")]
    workdirs = [e for e in entries if e not in allowed and e.startswith("_")]
    step("根目录结构", not extra,
         "根目录 %s%s%s" % (entries,
                            "；多出 %s（规范只允许 SKILL.md/references/scripts/templates）" % extra if extra else "",
                            "；_ 开头的工作目录已忽略：%s" % workdirs if workdirs else ""))
    lic = root / "references" / "LICENSE"
    lt = lic.read_text(encoding="utf-8") if lic.is_file() else ""
    lic_ok = (lic.is_file() and "Apache License" in lt and "Version 2.0, January 2004" in lt
              and "Yangming Hu" in lt and "专有许可" not in lt)
    step("许可文件 LICENSE", lic_ok,
         (str(lic.relative_to(root)) + "（Apache-2.0 + 署名 Yangming Hu）") if lic_ok
         else "references/LICENSE 缺失或不是 Apache-2.0（或出现『专有许可』回退）")
    skill_md = root / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
    fm = frontmatter(text)
    step("SKILL.md frontmatter 可解析", bool(fm),
         "" if fm else "SKILL.md 缺失或开头没有 --- 分隔的 frontmatter")
    nm = [l.split(":", 1)[1].strip() for l in fm.splitlines() if l.startswith("name:")]
    if bool(nm) and nm[0] == root.name:
        step("包名与根目录一致", True, "name=%s" % nm[0])
    else:
        # 解压到改过名的目录是正常用法，不能因此判失败；只提示。
        warn("包名与根目录一致", "name=%s 根目录=%s（解压目录被改名不影响使用，仅提示）"
             % (nm[0] if nm else "?", root.name))
    need = ["name:", "version:", "author:", "license:"]
    miss = [k for k in need if k not in fm]
    step("frontmatter 必填项", not miss, "缺 %s" % miss if miss else "name/version/author/license 齐全")
    import re as _re
    leaks = []
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        if any(part.startswith("_") for part in rel.parts[:-1]) or rel.parts[0].startswith("_"):
            continue                      # 工作目录是运行期数据，不是交付内容
        t = f.read_text(encoding="utf-8", errors="ignore")
        if _re.search(r"1[3-9]\d{9}", t) or _re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t):
            leaks.append(str(rel))
    step("无联系方式泄漏", not leaks, ", ".join(leaks) if leaks else "全包无手机号 / 邮箱")

    print("\n1) 环境体检")
    rc, out = run([sys.executable, str(HERE / "00_check_env.py"), "--json",
                   "--font", a.font, "--libreoffice-cli", a.libreoffice_cli or ""])
    line = [l for l in out.strip().splitlines() if l.strip().startswith("{")]
    env = json.loads(line[-1]) if line else {}
    if not env:
        step("00_check_env", False, out.strip().splitlines()[-1] if out.strip() else "无输出")
        print("\n结论：FAIL（环境体检未通过）")
        return 1
    for m, v in env["modules"].items():
        step("模块 %s" % m, bool(v))
    ok = step("python >= 3.10", env["python_ok"], env["python"])
    ok &= step("浏览器", bool(env["browser"]), env["browser"] or "找不到 Edge/Chrome/Chromium（设 CHROME_PATH）")
    print("   font=%s found=%s | kit=%s | node=%s"
          % (env["font"], env["font_ok"], env["libreoffice_cli"] or "-", env["node"] or "-"))
    if not ok:
        print("\n结论：FAIL（依赖不全，先装依赖：pip install playwright pymupdf python-pptx Pillow numpy）")
        return 1

    started = False
    try:
        print("\n2) 起浏览器（端口 %d）" % a.port)
        if edge_cdp.probe(a.port):
            print("   端口已在用，复用现有实例")
        else:
            ns = argparse.Namespace(port=a.port, profile=os.path.join(a.work, "edgeprofile"),
                                    exe=None, wait=25)
            started = edge_cdp.cmd_start(ns) == 0
            ok &= step("启动浏览器", started)
        if not started and not edge_cdp.probe(a.port):
            raise RuntimeError("浏览器未就绪")

        print("\n3) 测量 + 门禁 + 导出 PDF/预览图")
        rc, out = run([sys.executable, str(HERE / "10_measure_gate_export.py"),
                       "--html", html, "--canvas", a.canvas, "--pdf-size", a.pdf_size,
                       "--pdf", os.path.join(a.work, "selftest.pdf"),
                       "--png", os.path.join(a.work, "selftest.png"),
                       "--shapes", os.path.join(a.work, "shapes.json"),
                       "--report", os.path.join(a.work, "gate.json"),
                       "--cdp", "http://127.0.0.1:%d" % a.port,
                       "--js", str(HERE / "poster_measure.js")])
        tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
        ok &= step("10_measure_gate_export", rc == 0, tail[0] if tail else out[-160:])

        print("\n4) 生成可编辑 PPTX")
        rc, out = run([sys.executable, str(HERE / "20_html2pptx.py"),
                       "--shapes", os.path.join(a.work, "shapes.json"),
                       "--out", os.path.join(a.work, "selftest.pptx"),
                       "--html", html, "--font", a.font, "--slide-mm", a.slide_mm])
        tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
        ok &= step("20_html2pptx", rc == 0, tail[0] if tail else out[-160:])

        print("\n5) 一致性校验（需要 LibreOffice kit）")
        cli, node = env["libreoffice_cli"], env["node"]
        if cli and node:
            conv_rc, out = run([node, cli, "convert",
                                "--input", os.path.join(a.work, "selftest.pptx"),
                                "--output", os.path.join(a.work, "selftest.pptx.pdf")])
            pdf = os.path.join(a.work, "selftest.pptx.pdf")
            # 必须同时看退出码：只看文件在不在的话，上一轮遗留的 PDF 会被当成这一轮转出来的。
            conv = conv_rc == 0 and os.path.isfile(pdf)
            ok &= step("PPTX→PDF", conv,
                       "" if conv else "rc=%d%s" % (conv_rc, ("  " + out[-160:]) if out.strip() else ""))
            if conv:
                rc, out = run([sys.executable, str(HERE / "40_verify_pptx.py"),
                               "--pptx", os.path.join(a.work, "selftest.pptx"),
                               "--shapes", os.path.join(a.work, "shapes.json"),
                               "--html", html,
                               "--pdf-preview", os.path.join(a.work, "selftest.png"),
                               "--pptx-pdf", os.path.join(a.work, "selftest.pptx.pdf"),
                               "--pdf-size", a.pdf_size, "--work", a.work])
                tail = [l for l in out.strip().splitlines() if l.strip()][-1:]
                ok &= step("40_verify_pptx", rc == 0, tail[0] if tail else "")
        else:
            why = ("未提供 LibreOffice kit（--libreoffice-cli 或 LIBREOFFICE_KIT_CLI）" if not cli
                   else "找到了 kit 但没找到 node（用 LIBREOFFICE_KIT_NODE 指定）")
            detail = "%s；本次没有验证 PPTX↔PDF 一致性" % why
            if a.require_verify:
                ok &= step("PPTX→PDF 一致性校验", False, detail + "（--require-verify：按失败处理）")
            else:
                skip("PPTX→PDF 一致性校验", detail)
                print("        需要全绿请装 kit，或加 --require-verify 让它直接判失败")
    except Exception as exc:
        ok = False
        step("执行过程", False, "%s: %s" % (type(exc).__name__, exc))
    finally:
        if started:                     # 只关自己起的那棵树
            edge_cdp.cmd_stop(argparse.Namespace(port=a.port,
                                                 profile=os.path.join(a.work, "edgeprofile"),
                                                 exe=None, wait=25, kill_all=False))
            time.sleep(1)

    print("\n=== 自检汇总 ===")
    for name, status, _ in STEPS:
        print("  %-28s %s" % (name, status))
    nfail = sum(1 for _, st, _ in STEPS if st == "FAIL")
    nskip = sum(1 for _, st, _ in STEPS if st == "SKIP")
    nwarn = sum(1 for _, st, _ in STEPS if st == "WARN")
    tail = ""
    if nskip:                       # 跳过必须在结论里点名，不能悄悄算全绿
        tail += "（含 %d 项跳过：%s）" % (nskip, "、".join(n for n, st, _ in STEPS if st == "SKIP"))
    if nwarn:
        tail += "（含 %d 项提示）" % nwarn
    verdict = "PASS" if (ok and not nfail) else "FAIL"
    print("  结论：%s%s（共 %d 步，失败 %d，跳过 %d）" % (verdict, tail, len(STEPS), nfail, nskip))
    if not a.keep and os.path.isdir(a.work):
        shutil.rmtree(a.work, ignore_errors=True)
        print("  中间产物已清理（--keep 可保留）")
    return 0 if (ok and not nfail) else 1


if __name__ == "__main__":
    sys.exit(main())
