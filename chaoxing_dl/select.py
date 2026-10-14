"""交互式文件/文件夹选择。"""

from __future__ import annotations

import re
from typing import Iterable

from .parse import MaterialItem


def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def flatten_indexed(tree: list[MaterialItem]) -> list[tuple[str, MaterialItem]]:
    """展开为 [(display_path, item)]，仅文件。"""
    rows: list[tuple[str, MaterialItem]] = []
    for node in tree:
        for f in node.flatten_files():
            rows.append((f.path or f.name, f))
    return rows


def print_tree(tree: list[MaterialItem], *, indent: str = "") -> None:
    for node in tree:
        if node.is_folder:
            print(f"{indent}📁 {node.name}/")
            print_tree(node.children, indent=indent + "  ")
        else:
            print(f"{indent}📄 {node.name}  [{node.type}]")


def print_file_table(files: list[tuple[str, MaterialItem]]) -> None:
    if not files:
        print("（资料区为空）")
        return
    width = len(str(len(files)))
    for i, (path, item) in enumerate(files, 1):
        print(f"  [{i:>{width}}]  {path}  ({item.type})")


def parse_selection(text: str, total: int) -> list[int]:
    """解析选择串：all / * / 1,3,5-8 / pdf / .pptx

    返回 1-based 索引列表（去重保序）。扩展名筛选返回空列表时由调用方处理。
    """
    text = text.strip()
    if not text:
        return []
    lower = text.lower()
    if lower in ("all", "*", "全部", "a"):
        return list(range(1, total + 1))

    # 纯扩展名 / 类型过滤标记：交给调用方
    if re.fullmatch(r"\*?\.?[a-z0-9]{1,8}", lower):
        return []  # 特殊：空 + 原文本由 filter_by_ext 处理

    idxs: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            if a.strip().isdigit() and b.strip().isdigit():
                lo, hi = int(a), int(b)
                if lo > hi:
                    lo, hi = hi, lo
                idxs.extend(range(lo, hi + 1))
            continue
        if part.isdigit():
            idxs.append(int(part))
    # 合法范围
    seen, out = set(), []
    for i in idxs:
        if 1 <= i <= total and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def filter_by_ext(
    files: list[tuple[str, MaterialItem]], pattern: str
) -> list[int]:
    """按扩展名或 type 过滤，返回 1-based 索引。"""
    pat = pattern.strip().lower().lstrip("*")
    if pat.startswith("."):
        pat = pat[1:]
    hits = []
    for i, (path, item) in enumerate(files, 1):
        name = path.lower()
        if name.endswith("." + pat) or item.type.lower() == pat:
            hits.append(i)
    return hits


def interactive_pick(
    files: list[tuple[str, MaterialItem]],
) -> list[MaterialItem]:
    """打印列表并循环读取用户选择。"""
    print_file_table(files)
    print()
    print("选择说明:")
    print("  all / *          全部下载")
    print("  1,3,5-9          按编号（可区间）")
    print("  pdf / .pptx      按类型/扩展名")
    print("  q                取消")
    print()

    while True:
        raw = input("请选择要下载的项 > ").strip()
        if raw.lower() in ("q", "quit", "exit", "取消"):
            return []
        if not raw:
            continue

        # 扩展名？
        if re.fullmatch(r"\*?\.?[A-Za-z0-9]{1,8}", raw) and not raw.isdigit():
            idxs = filter_by_ext(files, raw)
            if not idxs:
                print(f"没有匹配 {raw} 的文件，请重试")
                continue
        else:
            idxs = parse_selection(raw, len(files))
            if not idxs and raw.lower() not in ("all", "*", "全部", "a"):
                # 可能是扩展名被误判
                idxs = filter_by_ext(files, raw)
            if not idxs:
                print("无效选择，请重试")
                continue

        chosen = [files[i - 1][1] for i in idxs]
        print(f"已选 {len(chosen)} 个文件。确认下载？[Y/n] ", end="")
        conf = input().strip().lower()
        if conf in ("", "y", "yes", "是"):
            return chosen
        print("已取消本次选择，可重新输入。")


def summarize_tree(tree: Iterable[MaterialItem]) -> tuple[int, int]:
    folders = files = 0
    for node in tree:
        if node.is_folder:
            folders += 1
            f2, fo2 = summarize_tree(node.children)
            # summarize_tree returns (files, folders)
            files += f2
            folders += fo2
        else:
            files += 1
    return files, folders
