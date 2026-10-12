# -*- coding: utf-8 -*-
"""check_package.py —— 技能包打包门禁（离线可跑，不需要浏览器 / LibreOffice）。

把"技能包规范"变成可执行检查：根目录结构、frontmatter 必填项、@references 引用能否落地、
许可自洽、编码、隐私（通用规则）、zip 容器规范。上传前或 CI 里跑一次，
把"平台解析失败 / 误带数据 / 许可口径漂移"挡在本地。

用法：
    python scripts/check_package.py                  # 检查本脚本所在的包目录
    python scripts/check_package.py <目录 或 zip>     # 检查指定目标
    python scripts/check_package.py --json           # 机器可读
    python scripts/check_package.py --selftest       # 门禁自身的负向测试（11 项）

退出码：0 = 全部通过（可有警告）；1 = 有硬错误；2 = 用法/读取错误。

隐私检查只使用**通用规则**（手机号 / 邮箱 / 绝对路径 / 数据类扩展名 / NUL），
具体项目标识请用环境变量 `PRIVACY_DENY` 在运行时传入（分号或换行分隔），
不要把要隐藏的字符串写进本文件 —— 本文件会随包公开分发。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import zipfile

# Windows 中文控制台：统一按 UTF-8 输出，避免被父进程按 UTF-8 读取时乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:      # pragma: no cover
    pass

REQUIRED_FM = ["description", "description_zh", "description_en", "version", "author"]
ALLOWED_ROOT = {"SKILL.md", "references", "scripts", "templates"}
DATA_EXT = {".txt", ".csv", ".tsv", ".xlsx", ".xls", ".mat", ".dat", ".zy", ".bin"}
SELF_NAME = "check_package.py"

# 通用隐私规则（不包含任何具体项目标识）
PATTERNS = [
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("邮箱", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")),
    ("绝对路径(Windows)", re.compile(r"[A-Za-z]:[\\/](?:Users|Documents|Desktop|data|work)", re.I)),
    ("绝对路径(类 Unix)", re.compile(r"/(?:home|Users|mnt|media)/[\w.-]+/")),
]
# 许可残留（本包口径：Apache-2.0）
LICENSE_BAD = [
    ("专有许可", re.compile(r"专有许可")),
    ("保留所有权利", re.compile(r"保留所有权利")),
    ("PolyForm", re.compile(r"PolyForm")),
    ("MIT", re.compile(r"\bMIT\b")),
]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.infos: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            fm[m.group(1)] = v
    return fm


def check_texts(files: dict[str, bytes], rep: Report, skip: set[str]) -> None:
    """对所有文本文件做编码与隐私检查。files: {包内相对路径: 字节}"""
    deny = [w for w in re.split(r"[;\n]+", os.environ.get("PRIVACY_DENY", "")) if w.strip()]
    for rel, raw in sorted(files.items()):
        if b"\x00" in raw:
            rep.err("%s 含 NUL 字节（会让平台解析失败）" % rel)
        if raw[:3] == b"\xef\xbb\xbf":
            rep.err("%s 含 UTF-8 BOM（本包要求无 BOM）" % rel)
        if b"\r\n" in raw:
            rep.err("%s 含 CRLF（本包要求 LF）" % rel)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            rep.err("%s 不是合法 UTF-8" % rel)
            continue
        if rel in skip:
            continue
        for label, pat in PATTERNS:
            for m in pat.finditer(text):
                rep.err("%s 命中%s：%s" % (rel, label, m.group(0)[:40]))
        for w in deny:
            if w in text:
                rep.err("%s 命中 PRIVACY_DENY 词：%s" % (rel, w[:20]))


def check_license(files: dict[str, bytes], rep: Report) -> None:
    key = "references/LICENSE"
    if key not in files:
        rep.err("缺 references/LICENSE（Apache-2.0 正文）")
        return
    text = files[key].decode("utf-8", "replace")
    if "Apache License" not in text or "Version 2.0, January 2004" not in text:
        rep.err("references/LICENSE 不是 Apache-2.0 正文")
    if re.search(r"\[yyyy\]|\[name of copyright owner\]", text):
        rep.err("references/LICENSE 附录未填（仍有 [yyyy] / [name of copyright owner] 占位）")
    if not re.search(r"Copyright\s+\d{4}\s+\S", text):
        rep.err("references/LICENSE 缺已填写的版权行")
    for label, pat in LICENSE_BAD:
        if pat.search(text):
            rep.err("references/LICENSE 残留旧许可字样：%s" % label)
    # 许可类文档不得出现"法律意见"式表述（声明文件里写"不构成法律意见"等于自我作废）
    for rel, raw in files.items():
        if not (rel.endswith("LICENSE") or "NOTICE" in rel or "许可" in rel):
            continue
        t = raw.decode("utf-8", "replace")
        for bad in ("不构成法律意见", "非法律意见", "建议咨询律师"):
            if bad in t:
                rep.err("%s 含法律意见式表述：%s" % (rel, bad))


def check_refs(files: dict[str, bytes], rep: Report) -> None:
    have = set(files)
    for rel, raw in sorted(files.items()):
        if not rel.endswith((".md", ".py", ".js")):
            continue
        text = raw.decode("utf-8", "replace")
        # 历史叙述里已明确标注"已不存在"的旧文件名不算失效引用
        text = "\n".join(l for l in text.splitlines() if "已不存在" not in l)
        for m in re.finditer(r"@?references/([\w\-.]+\.\w+)", text):
            if "references/" + m.group(1) not in have:
                rep.err("%s 引用了不存在的 references/%s" % (rel, m.group(1)))
        for m in re.finditer(r"scripts/([\w\-.]+\.(?:py|js))", text):
            if "scripts/" + m.group(1) not in have:
                rep.err("%s 引用了不存在的 scripts/%s" % (rel, m.group(1)))


def check_tree(files: dict[str, bytes], root_name: str, rep: Report, allow_rename: bool = False) -> dict:
    skill = "SKILL.md"
    if skill not in files:
        rep.err("包根缺 SKILL.md")
        return {}
    tops = {rel.split("/")[0] for rel in files}
    extra = sorted(t for t in tops if t not in ALLOWED_ROOT)
    if extra:
        rep.err("包根出现规范外的条目：%s（只允许 %s）" % (extra, sorted(ALLOWED_ROOT)))
    for rel in files:
        if "__pycache__" in rel or rel.endswith(".pyc"):
            rep.err("包内不应含 __pycache__ / .pyc：%s" % rel)
        if pathlib.PurePosixPath(rel).name.startswith("."):
            rep.err("包内不应含隐藏文件：%s" % rel)
    fm = parse_frontmatter(files[skill].decode("utf-8", "replace"))
    if not fm:
        rep.err("SKILL.md frontmatter 无法解析（需 --- 包裹的 YAML 头）")
        return {}
    miss = [k for k in REQUIRED_FM if not fm.get(k)]
    if miss:
        rep.err("frontmatter 缺必填项：%s" % miss)
    name = fm.get("name", "")
    if not name:
        rep.err("frontmatter 缺 name")
    elif name != root_name:
        if allow_rename:
            rep.warn("frontmatter name=%r 与目录名 %r 不一致（已按 --allow-root-rename 放行："
                     "把包解压/复制到改名的目录是正常用法，但打包 zip 时必须一致）" % (name, root_name))
        else:
            rep.err("frontmatter name=%r 与包根目录名 %r 不一致" % (name, root_name))
    ver = fm.get("version", "")
    if ver and not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        rep.err("version 不是 x.y.z 形式：%r" % ver)
    if not fm.get("license"):
        rep.warn("frontmatter 未声明 license（本包口径为 Apache-2.0）")
    elif "Apache" not in fm["license"]:
        rep.err("frontmatter license 不是 Apache-2.0：%r" % fm["license"])
    rep.info("name=%s version=%s author=%s" % (name, ver, fm.get("author", "")))
    return fm


def check_zip(path: pathlib.Path, rep: Report) -> None:
    try:
        z = zipfile.ZipFile(path)
    except Exception as exc:
        rep.err("无法读取 zip：%s" % exc)
        return
    names = z.namelist()
    if not names:
        rep.err("zip 是空的")
        return
    dirs = [n for n in names if n.endswith("/")]
    if dirs:
        rep.err("zip 含目录条目 %d 个（本包规范：不写目录条目）" % len(dirs))
    tops = {n.split("/")[0] for n in names}
    if len(tops) != 1:
        rep.err("zip 顶层目录不唯一：%s" % sorted(tops))
    else:
        rep.info("zip 顶层目录：%s" % sorted(tops)[0])
    bad_c = [i.filename for i in z.infolist() if i.compress_type != zipfile.ZIP_DEFLATED]
    if bad_c:
        rep.err("zip 内有非 deflate 条目：%s" % bad_c[:3])
    for i in z.infolist():
        if not i.filename.isascii() and not (i.flag_bits & 0x800):
            rep.err("zip 内非 ASCII 文件名未置 UTF-8 标志：%s" % i.filename)
    if path.stat().st_size > 4 * 1024 * 1024:
        rep.warn("zip 体积 %.1f MB 偏大" % (path.stat().st_size / 1048576))


def collect_from_dir(root: pathlib.Path) -> tuple[dict[str, bytes], list[str]]:
    """收集包内文件。根目录下 `_` 开头的是运行期工作目录（_work/_backup），不算包内容。"""
    files, skipped = {}, []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.split("/")[0].startswith("_"):
            if rel.split("/")[0] not in skipped:
                skipped.append(rel.split("/")[0])
            continue
        files[rel] = p.read_bytes()
    return files, skipped


def collect_from_zip(path: pathlib.Path) -> tuple[dict[str, bytes], str]:
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if not n.endswith("/")]
    top = names[0].split("/")[0] if names else path.stem
    files = {}
    for n in names:
        parts = n.split("/")
        rel = "/".join(parts[1:]) if len(parts) > 1 else parts[0]
        files[rel] = z.read(n)
    return files, top


def run(target: pathlib.Path, allow_rename: bool = False) -> Report:
    rep = Report()
    is_zip = target.is_file() and target.suffix.lower() == ".zip"
    if is_zip:
        files, root_name = collect_from_zip(target)
        check_zip(target, rep)
    elif target.is_dir():
        files, skipped = collect_from_dir(target)
        root_name = target.name
        if skipped:
            rep.info("已忽略运行期工作目录：%s（它们是产物，不是包内容）" % ", ".join(skipped))
    else:
        rep.err("目标不存在或不是目录/zip：%s" % target)
        return rep

    fm = check_tree(files, root_name, rep, allow_rename)
    check_license(files, rep)
    check_refs(files, rep)
    # 本门禁自身不做跳过：它用动态拼接构造测试夹具，因此可以被自己扫（更严格）
    check_texts(files, rep, skip=set())

    bad_ext = sorted(r for r in files if pathlib.PurePosixPath(r).suffix.lower() in DATA_EXT)
    if bad_ext:
        rep.err("包内出现数据类文件：%s" % bad_ext)
    rep.info("文件数 %d" % len(files))
    return rep


# ---------------------------------------------------------------- 负向测试
def _mutate(src: pathlib.Path, dst: pathlib.Path, kind: str) -> None:
    # 忽略 __pycache__：它是构建产物，不属于包内容（门禁本身仍会抓包内残留的 .pyc）
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    skill = dst / "SKILL.md"
    # 测试夹具用动态拼接，避免门禁自己扫自己时误报
    fake_ref = "@references/" + "does-not-exist" + ".md"
    fake_mail = "someone" + "@" + "example" + ".com"
    if kind == "extra_root_file":
        (dst / "README.md").write_text("x\n", encoding="utf-8")
    elif kind == "root_name_mismatch":
        pass  # 由调用方改名
    elif kind == "drop_author":
        t = skill.read_text(encoding="utf-8")
        skill.write_text(re.sub(r"^author:.*$", "", t, flags=re.M), encoding="utf-8")
    elif kind == "drop_description_en":
        t = skill.read_text(encoding="utf-8")
        skill.write_text(re.sub(r"^description_en:.*$", "", t, flags=re.M), encoding="utf-8")
    elif kind == "bad_ref":
        t = skill.read_text(encoding="utf-8")
        skill.write_text(t.replace("@references/01-workflow.md", fake_ref, 1),
                         encoding="utf-8")
    elif kind == "mit_license":
        (dst / "references" / "LICENSE").write_text("MIT License\n\nPermission is hereby granted...\n",
                                                    encoding="utf-8")
    elif kind == "unfilled_appendix":
        lic = dst / "references" / "LICENSE"
        lic.write_text(lic.read_text(encoding="utf-8") + "\n[yyyy] [name of copyright owner]\n",
                       encoding="utf-8")
    elif kind == "nul_byte":
        p = dst / "references" / "01-workflow.md"
        p.write_bytes(p.read_bytes() + b"\x00\n")
    elif kind == "email":
        p = dst / "references" / "01-workflow.md"
        p.write_bytes(p.read_bytes() + ("\n联系 " + fake_mail + "\n").encode())
    elif kind == "abs_path":
        p = dst / "references" / "01-workflow.md"
        p.write_bytes(p.read_bytes() + ("\n路径 " + "D:" + "\\Users\\x\\poster.html\n").encode())
    elif kind == "legal_opinion":
        p = dst / "references" / "LICENSE"
        p.write_text(p.read_text(encoding="utf-8") + "\n本文件不构成法律意见。\n", encoding="utf-8")


def selftest(pkg: pathlib.Path) -> int:
    cases = ["extra_root_file", "drop_author", "drop_description_en", "bad_ref", "mit_license",
             "unfilled_appendix", "nul_byte", "email", "abs_path", "legal_opinion"]
    print("== check_package 负向测试 ==")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cpkg_"))
    passed = failed = 0
    try:
        # 正向：正常包必须无硬错误
        rep = run(pkg)
        ok = rep.ok
        print("  %-22s %s" % ("正常包（应通过）", "PASS" if ok else "FAIL → %s" % rep.errors[:2]))
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

        for kind in cases:
            d = tmp / kind / pkg.name
            d.parent.mkdir(parents=True, exist_ok=True)
            _mutate(pkg, d, kind)
            rep = run(d)
            good = not rep.ok
            print("  %-22s %s" % (kind, "PASS" if good else "FAIL（没抓到）"))
            passed, failed = (passed + 1, failed) if good else (passed, failed + 1)

        # 目录名与 name 不一致
        d = tmp / "root_name_mismatch" / "wrong-name"
        d.parent.mkdir(parents=True, exist_ok=True)
        _mutate(pkg, d, "root_name_mismatch")
        rep = run(d)
        good = not rep.ok
        print("  %-22s %s" % ("root_name_mismatch", "PASS" if good else "FAIL（没抓到）"))
        passed, failed = (passed + 1, failed) if good else (passed, failed + 1)

        # zip 里加目录条目
        zpath = tmp / "with_dir_entry.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("%s/" % pkg.name, "")
            for p in sorted(pkg.rglob("*")):
                if p.is_file():
                    z.write(p, "%s/%s" % (pkg.name, p.relative_to(pkg).as_posix()))
        rep = run(zpath)
        good = not rep.ok
        print("  %-22s %s" % ("zip 含目录条目", "PASS" if good else "FAIL（没抓到）"))
        passed, failed = (passed + 1, failed) if good else (passed, failed + 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("结论：%s（通过 %d / 失败 %d）" % ("PASS" if failed == 0 else "FAIL", passed, failed))
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="技能包打包门禁")
    ap.add_argument("target", nargs="?", default=None, help="包目录或 zip；默认本脚本所在包")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="门禁自身的负向测试")
    ap.add_argument("--allow-root-rename", action="store_true",
                    help="目录名与 frontmatter name 不一致时只警告（用于把包解压到改名目录的场景）")
    a = ap.parse_args(argv)

    here = pathlib.Path(__file__).resolve().parent.parent
    if a.selftest:
        return selftest(here)
    target = pathlib.Path(a.target).resolve() if a.target else here

    rep = run(target, allow_rename=a.allow_root_rename)
    if a.json:
        print(json.dumps({"target": str(target), "ok": rep.ok, "errors": rep.errors,
                          "warnings": rep.warns, "info": rep.infos}, ensure_ascii=False, indent=2))
    elif not a.quiet:
        print("== check_package：%s ==" % target)
        for i in rep.infos:
            print("  · %s" % i)
        for w in rep.warns:
            print("  [警告] %s" % w)
        for e in rep.errors:
            print("  [错误] %s" % e)
        print("PACKAGE %s" % ("PASS" if rep.ok else "FAIL（%d 处硬错误）" % len(rep.errors)))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
