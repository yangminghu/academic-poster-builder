# -*- coding: utf-8 -*-
"""edge_cdp.py —— 自己拉起 / 查看 / 关闭一个带 CDP 端口的浏览器实例。

为什么不用 Playwright 的 headless 启动：实测 headless Edge 会挂死（连续 180 s 超时）
并残留进程、拖死整台机器。自己拉起 + connect_over_cdp 最稳，进程树也由我们负责杀干净。

    python edge_cdp.py start  --port 9223 [--profile _work/edgeprofile] [--exe ...]
    python edge_cdp.py status --port 9223
    python edge_cdp.py stop   --port 9223          # 只杀命令行里带本实例 profile 的进程
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

for _s in (sys.stdout, sys.stderr):        # Windows 中文控制台默认 GBK：打印 "−/≈/✓" 会崩
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WIN = platform.system() == "Windows"
DETACHED_PROCESS = 0x00000008
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000      # 浏览器在后台跑，桌面不被抢
# Windows 上"可能是我们的实例"的进程名：Chromium 系浏览器的可执行文件名（含 beta/dev 变体）。
# 查询时按名 + profile + 排除自身三重过滤，见 _ps_pids()。
BROWSER_NAMES = ("msedge", "chrome", "chromium", "brave", "vivaldi", "opera")
CANDIDATES = {
    "Windows": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "Linux": ["/usr/bin/google-chrome", "/usr/bin/microsoft-edge", "/usr/bin/chromium",
              "/usr/bin/chromium-browser"],
}


def find_browser(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for name in ("CHROME_PATH", "EDGE_PATH", "BROWSER_PATH"):
        if os.environ.get(name) and os.path.isfile(os.environ[name]):
            return os.environ[name]
    for p in CANDIDATES.get(platform.system(), []):
        if os.path.isfile(p):
            return p
    for exe in ("msedge", "google-chrome", "chromium", "chrome"):
        p = shutil.which(exe)
        if p:
            return p
    return None


def probe(port: int, timeout=3.0):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _ps_pids(profile: str, extra=(), include_helpers: bool = False):
    """Windows：列出「命令行里带本实例 profile」的浏览器进程 PID。

    这里有两个必须同时满足的约束，否则查询会把自己也匹配上（这是曾经的严重缺陷）：
      1) 查询脚本经 `-EncodedCommand` 传入，profile 字符串**不会**出现在 powershell 的
         命令行里 —— 否则那个 powershell 自己也带 profile，`my_pids()` 永远不会为空，
         `stop` 永远报残留、`status` 显示幽灵进程、`--kill-all` 被误触发去强杀用户的浏览器；
      2) 仍然双保险：只认浏览器进程名，并显式排除查询进程自身（$PID）。
    profile 用 String.Contains 精确子串匹配（不用 -like：路径里的 []*? 在通配符里另有含义）。
    """
    conds = ["$_.ProcessId -ne $PID",
             "$_.CommandLine -ne $null -and $_.CommandLine.Contains($pat)"]
    if BROWSER_NAMES:
        conds.insert(0, "(" + " -or ".join(
            "$_.Name -like '%s*.exe'" % n for n in BROWSER_NAMES) + ")")
    if not include_helpers:
        conds.append("$_.CommandLine -notlike '*crashpad-handler*'")
    conds.extend(extra)
    script = ("$pat = '%s'; " % profile.replace("'", "''")
              + "Get-CimInstance Win32_Process | Where-Object { " + " -and ".join(conds)
              + " } | Select-Object -ExpandProperty ProcessId")
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                         capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def _posix_pids(profile: str, need_port: bool = False, include_helpers: bool = False):
    """POSIX：按命令行里的 profile 过滤，并排除查询用的 ps 与本次 python 自身。"""
    out = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
    me = os.getpid()
    rows = []
    for line in out.splitlines():
        if profile not in line or "ps -eo" in line:
            continue
        if need_port and "--remote-debugging-port" not in line:
            continue
        if not include_helpers and "crashpad-handler" in line:
            continue
        try:
            pid = int(line.split(None, 1)[0])
        except (ValueError, IndexError):
            continue
        if pid != me:
            rows.append(pid)
    return rows


def my_pids(profile: str, include_helpers: bool = False):
    """只认自己的实例（按 --user-data-dir 匹配），不碰用户的浏览器。

    默认过滤 crashpad-handler：它在主进程退出后会反复重生几秒，算成"残留"就是误报。
    """
    if not WIN:
        return _posix_pids(profile, include_helpers=include_helpers)
    return _ps_pids(profile, include_helpers=include_helpers)


def root_pid(profile: str, port: int | None = None):
    """浏览器主进程 = 命令行里既有 profile 又有 --remote-debugging-port 的那个。"""
    if not WIN:
        ids = _posix_pids(profile, need_port=True)
        return ids[0] if ids else None
    if port:
        # 优先精确到本端口；历史实例换了端口时退回"只带调试开关"的宽松匹配
        ids = _ps_pids(profile, ["$_.CommandLine -like '*--remote-debugging-port=%d*'" % port])
        if ids:
            return ids[0]
    ids = _ps_pids(profile, ["$_.CommandLine -like '*--remote-debugging-port*'"])
    return ids[0] if ids else None


def cmd_start(a) -> int:
    if probe(a.port):
        print("CDP 端口 %d 已经在跑（复用现有实例，不再新开窗口）" % a.port); return 0
    exe = find_browser(a.exe)
    if not exe:
        print("找不到浏览器；用 --exe 指定，或设置 CHROME_PATH"); return 2
    profile = os.path.abspath(a.profile)
    os.makedirs(profile, exist_ok=True)
    flags = ["--remote-debugging-port=%d" % a.port, "--user-data-dir=%s" % profile,
             "--no-first-run", "--no-default-browser-check", "--disable-extensions",
             "--disable-background-mode",        # 不留下后台常驻进程
             "--disable-component-update", "--mute-audio",
             "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
             # 屏幕外窗口也要照常渲染：关掉"被遮挡就降频/停渲染"
             "--disable-features=CalculateNativeWinOcclusion",
             "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
             "about:blank"]
    if getattr(a, "onscreen", False):      # 别的脚本可能自己构造参数对象，属性要容错
        flags.insert(-1, "--window-size=1400,900")
    else:
        # 放到屏幕外：桌面完全看不到，也不会抢焦点
        flags.insert(-1, "--window-position=-32000,-32000")
        flags.insert(-1, "--window-size=900,700")
    print("launching %s (profile=%s%s)" % (exe, profile, "，可见窗口" if getattr(a, "onscreen", False) else "，屏幕外"))
    if WIN:
        subprocess.Popen([exe] + flags,
                         creationflags=DETACHED_PROCESS | BELOW_NORMAL_PRIORITY_CLASS)
    else:
        subprocess.Popen([exe] + flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    for _ in range(a.wait):
        time.sleep(1)
        if probe(a.port):
            print("CDP up: %s" % (probe(a.port) or {}).get("Browser"))
            return 0
    print("CDP 端口未就绪（%ds）" % a.wait)
    return 1


def cmd_status(a) -> int:
    info = probe(a.port)
    pids = my_pids(os.path.abspath(a.profile))
    print("CDP %s: %s" % (a.port, (info or {}).get("Browser", "DOWN")))
    print("my browser processes: %d %s" % (len(pids), pids[:8]))
    return 0 if info else 1


def cmd_stop(a) -> int:
    """先杀浏览器主进程的整棵树，再兜底清扫；最多尝试 5 轮。

    默认只杀「命令行里带本实例 profile」的进程（不碰用户自己的浏览器）。
    仍有残留时用 --kill-all（确认用户没有开着自己的浏览器再用）。
    """
    profile, port = os.path.abspath(a.profile), a.port
    killed = 0
    import signal
    for _ in range(5):
        root = root_pid(profile, port)
        pids = my_pids(profile)
        if not root and not pids:
            break
        if root:
            if WIN:
                subprocess.run(["taskkill", "/PID", str(root), "/T", "/F"], capture_output=True)
            else:
                try:
                    os.killpg(os.getpgid(root), signal.SIGTERM)
                except Exception:
                    try:
                        os.kill(root, signal.SIGTERM)
                    except Exception:
                        pass
            killed += 1
        for pid in my_pids(profile):                       # 兜底：仍在的直接强杀
            if pid == root:
                continue
            if WIN:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            killed += 1
        time.sleep(1.5)
    left = my_pids(profile)
    if left and getattr(a, "kill_all", False):
        # 只有用户显式传了 --kill-all 才可能走到这里；my_pids() 的幽灵进程缺陷修掉之后，
        # left 只在真有本实例残留时才非空，不会再"总是为真"而误杀用户的浏览器。
        exe = find_browser(None)
        name = os.path.basename(exe)[:-4] if exe else "msedge"
        if WIN:
            subprocess.run(["taskkill", "/IM", name + ".exe", "/F"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", name], capture_output=True)
        time.sleep(1.5)
        killed += len(left)
        left = my_pids(profile)
    time.sleep(2)                                          # crashpad-handler 可能短暂重生
    left = my_pids(profile)
    helpers = len(my_pids(profile, include_helpers=True)) - len(left)
    print("stopped %d process(es); leftover %d%s"
          % (killed, len(left),
             ("  (另有 %d 个 crashpad 辅助进程，会自行退出，不算残留)" % helpers) if helpers else ""))
    if left:
        print("提示：仍有残留；确认用户没开自己的浏览器后可加 --kill-all 强制清理")
    return 0 if not left else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("start", cmd_start), ("status", cmd_status), ("stop", cmd_stop)):
        sp = sub.add_parser(name)
        sp.add_argument("--port", type=int, default=9223)
        sp.add_argument("--profile", default="_work/edgeprofile")
        sp.add_argument("--exe", default=None)
        sp.add_argument("--wait", type=int, default=25, help="start: 等待端口就绪的秒数")
        sp.add_argument("--kill-all", action="store_true",
                        help="stop: 兜底按进程名强杀（确认用户未开浏览器）")
        sp.add_argument("--onscreen", action="store_true",
                        help="start: 把窗口放到桌面上（默认屏幕外，避免打扰用户）")
        sp.set_defaults(func=fn)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
