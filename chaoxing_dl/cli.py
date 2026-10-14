"""命令行入口：login / list / download / 交互向导。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .auth import (
    DEFAULT_LOGIN_URL,
    clear_session,
    has_session,
    interactive_login,
    session_path,
)
from .client import ChaoxingClient
from .parse import CourseRef, parse_course_url
from .select import (
    flatten_indexed,
    format_size,
    interactive_pick,
    print_tree,
    summarize_tree,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_login(args: argparse.Namespace) -> int:
    url = args.url or DEFAULT_LOGIN_URL
    # 若给了课程链接，直接打开该页（学校 SSO 更顺）
    interactive_login(
        url,
        session_root=_project_root(),
        headless=False,
        timeout_sec=args.timeout,
    )
    return 0


def cmd_logout(_: argparse.Namespace) -> int:
    clear_session(_project_root())
    print("[*] 已清除本地登录会话")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    root = _project_root()
    if has_session(root):
        print(f"[*] 已登录，会话文件: {session_path(root)}")
    else:
        print("[*] 未登录。运行: python -m chaoxing_dl login")
    return 0


def _prompt_course_url(hint: str = "") -> str:
    """交互粘贴课程链接（避免 PowerShell/cmd 吃掉 URL 里的 &）。"""
    print()
    if hint:
        print(hint)
    print("请粘贴课程页完整 URL（含 courseid、clazzid、cpi），然后回车：")
    raw = input("> ").strip().strip('"').strip("'")
    if not raw:
        raise SystemExit("未输入 URL")
    return raw


def _resolve_course(args: argparse.Namespace) -> CourseRef:
    url = (getattr(args, "url", None) or "").strip()
    if url:
        try:
            course = parse_course_url(url)
        except ValueError as e:
            # 常见于 bat/PowerShell 把 & 后面截断，只剩 courseid
            print(f"[!] {e}")
            url = _prompt_course_url("刚才的 --url 不完整，请重新粘贴完整链接。")
            course = parse_course_url(url)
        if args.name:
            course.name = args.name
        return course
    if args.course_id and args.clazz_id and args.cpi:
        return CourseRef(
            courseid=str(args.course_id),
            clazzid=str(args.clazz_id),
            cpi=str(args.cpi),
            enc=args.enc or "",
            host=args.host or "mooc1.chaoxing.com",
            name=args.name or "",
        )
    # 无参数时先尝试粘贴 URL，再退回选课列表
    try:
        print("未指定课程。可直接粘贴课程 URL，或回车后从课程列表选择。")
        raw = input("课程 URL（直接回车=从列表选）> ").strip().strip('"').strip("'")
        if raw:
            course = parse_course_url(raw)
            if args.name:
                course.name = args.name
            return course
    except EOFError:
        pass
    raise SystemExit(
        "请提供 --url 课程链接，或同时提供 --course-id --clazz-id --cpi\n"
        "PowerShell 推荐: .\\run.ps1 download --url \"完整链接\""
    )


def _pick_course_interactive(client: ChaoxingClient) -> CourseRef:
    print("[*] 正在拉取课程列表...")
    courses = client.list_courses()
    if not courses:
        raise SystemExit("未解析到课程。请改用 --url 传入课程页链接。")
    print()
    width = len(str(len(courses)))
    for i, c in enumerate(courses, 1):
        teacher = f"  · {c.teacher}" if c.teacher else ""
        print(f"  [{i:>{width}}] {c.name}{teacher}")
        print(
            f"       courseid={c.courseid}  clazzid={c.clazzid}  cpi={c.cpi}"
        )
    print()
    while True:
        raw = input("选择课程编号（或 q 退出）> ").strip()
        if raw.lower() in ("q", "quit"):
            raise SystemExit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(courses):
            return courses[int(raw) - 1]
        print("无效编号")


def cmd_courses(_: argparse.Namespace) -> int:
    client = ChaoxingClient(session_root=_project_root())
    courses = client.list_courses()
    if not courses:
        print("未找到课程")
        return 1
    for i, c in enumerate(courses, 1):
        print(f"{i}. {c.name}  (teacher={c.teacher or '-'})")
        print(f"   courseid={c.courseid} clazzid={c.clazzid} cpi={c.cpi}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    client = ChaoxingClient(session_root=_project_root())
    if args.url or (args.course_id and args.clazz_id and args.cpi):
        course = _resolve_course(args)
    else:
        course = _pick_course_interactive(client)

    print(f"[*] 课程: {course.name or course.courseid}  host={course.host}")
    print("[*] 扫描资料区（含文件夹）...")
    tree = client.build_tree(
        course,
        max_depth=args.depth,
        on_progress=(lambda m: print(m)) if args.verbose else None,
    )
    files_n, folders_n = summarize_tree(tree)
    print()
    print_tree(tree)
    print()
    print(f"合计: {files_n} 个文件, {folders_n} 个文件夹")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    client = ChaoxingClient(
        session_root=_project_root(),
        request_interval=args.interval,
    )
    if args.url or (args.course_id and args.clazz_id and args.cpi):
        course = _resolve_course(args)
    else:
        course = _pick_course_interactive(client)

    title = course.name or f"course_{course.courseid}"
    out = Path(args.out)
    if not args.flat:
        # 默认按课名分子目录
        safe = "".join(
            ch if ch not in r'\/:*?"<>|' else "_" for ch in title
        ).strip() or course.courseid
        out = out / safe

    print(f"[*] 课程: {title}")
    print(f"[*] 输出目录: {out.resolve()}")
    print("[*] 扫描资料区...")
    tree = client.build_tree(
        course,
        max_depth=args.depth,
        on_progress=(lambda m: print(m)) if args.verbose else None,
    )
    indexed = flatten_indexed(tree)
    if not indexed:
        print("资料区没有可下载文件。")
        return 1

    files_n, folders_n = summarize_tree(tree)
    print(f"[*] 发现 {files_n} 个文件 / {folders_n} 个文件夹")

    if args.all:
        chosen = [item for _, item in indexed]
    elif args.select:
        import re

        from .select import filter_by_ext, parse_selection

        raw = args.select.strip()
        idxs: list[int] = []
        if raw.lower() in ("all", "*", "全部", "a"):
            idxs = list(range(1, len(indexed) + 1))
        elif re.fullmatch(r"\*?\.?[A-Za-z][A-Za-z0-9]{0,7}", raw):
            idxs = filter_by_ext(indexed, raw)
        else:
            idxs = parse_selection(raw, len(indexed))
            if not idxs:
                idxs = filter_by_ext(indexed, raw)
        if not idxs:
            print(f"没有匹配 --select {raw!r} 的项")
            return 1
        chosen = [indexed[i - 1][1] for i in idxs]
    else:
        # 交互选择
        print()
        chosen = interactive_pick(indexed)
        if not chosen:
            print("已取消")
            return 0

    print(f"[*] 开始下载 {len(chosen)} 个文件...\n")
    ok = fail = 0
    total_bytes = 0
    for i, item in enumerate(chosen, 1):
        label = item.path or item.name
        try:
            result = client.download_file(
                course, item, out, keep_structure=not args.flat
            )
            ok += 1
            total_bytes += result["size"]
            print(
                f"  [{i}/{len(chosen)}] OK  {result['name']}  "
                f"({format_size(result['size'])})"
            )
        except Exception as e:
            fail += 1
            print(f"  [{i}/{len(chosen)}] FAIL {label}: {e}")

    print()
    print(
        f"完成: 成功 {ok} / 失败 {fail} / 共 {len(chosen)}，"
        f"约 {format_size(total_bytes)} -> {out.resolve()}"
    )
    return 0 if fail == 0 else 2


def cmd_wizard(args: argparse.Namespace) -> int:
    """零参数向导：登录（如需）→ 选课 → 选文件 → 下载。"""
    root = _project_root()
    if not has_session(root):
        print("尚未登录，即将打开浏览器…")
        start = args.url or DEFAULT_LOGIN_URL
        interactive_login(start, session_root=root, timeout_sec=args.timeout)
    elif args.relogin:
        interactive_login(
            args.url or DEFAULT_LOGIN_URL,
            session_root=root,
            timeout_sec=args.timeout,
        )

    # 复用 download 的交互路径
    ns = argparse.Namespace(
        url=args.url,
        course_id=None,
        clazz_id=None,
        cpi=None,
        enc="",
        host="",
        name="",
        out=args.out,
        flat=False,
        all=False,
        select=None,
        depth=args.depth,
        verbose=args.verbose,
        interval=args.interval,
    )
    # 若给了完整课程 URL，直接下；否则选课
    return cmd_download(ns)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chaoxing_dl",
        description=(
            "超星 / 学习通 / 泛雅 课程「资料」批量下载工具\n"
            "Playwright 登录一次，之后可交互选择或批量下载。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m chaoxing_dl login
  python -m chaoxing_dl login --url "https://mooc1.s.ecust.edu.cn/..."
  python -m chaoxing_dl courses
  python -m chaoxing_dl list --url "课程页URL"
  python -m chaoxing_dl download --url "课程页URL"          # 交互勾选
  python -m chaoxing_dl download --url "..." --all
  python -m chaoxing_dl download --url "..." --select pdf
  python -m chaoxing_dl                        # 向导模式
        """,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    # login
    sp = sub.add_parser("login", help="打开浏览器登录并保存会话")
    sp.add_argument("--url", default="", help="登录起始页（推荐直接贴课程链接）")
    sp.add_argument("--timeout", type=int, default=300, help="登录等待秒数")
    sp.set_defaults(func=cmd_login)

    sp = sub.add_parser("logout", help="清除本地会话")
    sp.set_defaults(func=cmd_logout)

    sp = sub.add_parser("status", help="查看登录状态")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("courses", help="列出我的课程")
    sp.set_defaults(func=cmd_courses)

    def add_course_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--url", default="", help="课程页完整 URL")
        parser.add_argument("--course-id", default="", help="courseid")
        parser.add_argument("--clazz-id", default="", help="clazzid")
        parser.add_argument("--cpi", default="", help="cpi")
        parser.add_argument("--enc", default="", help="enc（可选）")
        parser.add_argument("--host", default="", help="校区域名（可选）")
        parser.add_argument("--name", default="", help="课程显示名（可选）")
        parser.add_argument("--depth", type=int, default=12, help="文件夹下钻深度")
        parser.add_argument("-v", "--verbose", action="store_true", help="打印扫描过程")

    sp = sub.add_parser("list", help="列出资料区文件树")
    add_course_args(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("download", help="下载资料（默认交互选择）")
    add_course_args(sp)
    sp.add_argument(
        "--out",
        default=str(_project_root() / "downloads"),
        help="下载根目录（默认 ./downloads）",
    )
    sp.add_argument("--all", action="store_true", help="下载全部文件")
    sp.add_argument(
        "--select",
        default="",
        help="非交互选择：all / 1,3,5-9 / pdf / .pptx",
    )
    sp.add_argument(
        "--flat",
        action="store_true",
        help="不保留文件夹结构（全部放同一目录）",
    )
    sp.add_argument(
        "--interval",
        type=float,
        default=0.3,
        help="请求间隔秒（降低风控，默认 0.3）",
    )
    sp.set_defaults(func=cmd_download)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    # 无子命令 → 向导
    if not argv or argv[0].startswith("-") and argv[0] not in (
        "-h",
        "--help",
        "--version",
    ):
        # 允许 `python -m chaoxing_dl --url ...` 进向导
        wiz = argparse.ArgumentParser(add_help=False)
        wiz.add_argument("--url", default="")
        wiz.add_argument("--out", default=str(_project_root() / "downloads"))
        wiz.add_argument("--depth", type=int, default=12)
        wiz.add_argument("--timeout", type=int, default=300)
        wiz.add_argument("--interval", type=float, default=0.3)
        wiz.add_argument("-v", "--verbose", action="store_true")
        wiz.add_argument("--relogin", action="store_true")
        # 若第一个参数是已知子命令，走正常解析
        known = {
            "login",
            "logout",
            "status",
            "courses",
            "list",
            "download",
        }
        if argv and argv[0] in known:
            args = parser.parse_args(argv)
            return int(args.func(args) or 0)
        if argv and argv[0] in ("-h", "--help"):
            parser.print_help()
            return 0
        wargs, _ = wiz.parse_known_args(argv)
        return cmd_wizard(wargs)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args) or 0)
    except FileNotFoundError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断")
        return 130
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
