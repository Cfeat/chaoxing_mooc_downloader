"""URL / HTML 解析与文件名处理。"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class CourseRef:
    """一门课的定位参数（URL 四件套）。"""

    courseid: str
    clazzid: str
    cpi: str
    enc: str = ""
    host: str = "mooc1.chaoxing.com"
    name: str = ""
    teacher: str = ""

    def as_dict(self) -> dict:
        return {
            "courseid": self.courseid,
            "clazzid": self.clazzid,
            "cpi": self.cpi,
            "enc": self.enc,
            "host": self.host,
            "name": self.name,
            "teacher": self.teacher,
        }


@dataclass
class MaterialItem:
    """资料区一项（文件夹或文件）。"""

    type: str  # "afolder" 或 pdf/doc/ppt/...
    name: str
    data_id: int
    enc: str = ""
    path: str = ""  # 相对路径，如 "讲义/第1章.pdf"
    children: list["MaterialItem"] = field(default_factory=list)

    @property
    def is_folder(self) -> bool:
        return self.type == "afolder"

    def flatten_files(self) -> list["MaterialItem"]:
        if not self.is_folder:
            return [self]
        out: list[MaterialItem] = []
        for child in self.children:
            out.extend(child.flatten_files())
        return out


def parse_course_url(url: str) -> CourseRef:
    """从课程页 / 资料页 URL 提取 courseid、clazzid、cpi、enc、host。"""
    parsed = urlparse(url.strip())
    qs = parse_qs(parsed.query)
    # 兼容 courseId / courseid 等大小写
    lower = {k.lower(): v for k, v in qs.items()}

    def first(*keys: str) -> str:
        for k in keys:
            if k in lower and lower[k]:
                return lower[k][0]
        return ""

    courseid = first("courseid", "course_id")
    clazzid = first("clazzid", "classid", "clazz_id", "class_id")
    cpi = first("cpi")
    enc = first("enc")
    if not (courseid and clazzid and cpi):
        raise ValueError(
            "URL 中缺少 courseid / clazzid / cpi。\n"
            "请打开课程页后复制地址栏完整链接。\n"
            "若在 PowerShell 里传 --url，请用 .\\run.ps1，或运行后按提示粘贴链接\n"
            "（不要用 run.bat 传带 & 的 URL，& 会被拆开）。"
        )
    host = parsed.netloc or "mooc1.chaoxing.com"
    return CourseRef(
        courseid=courseid,
        clazzid=clazzid,
        cpi=cpi,
        enc=enc,
        host=host,
    )


def parse_materials(html: str) -> list[MaterialItem]:
    """解析资料区 stu-datalist HTML。

    前端 toOpen(name, type, dataId, ..., enc) 点击回调里带齐字段。
    """
    items: list[MaterialItem] = []
    pattern = (
        r"<dt onclick=\"toOpen\('([^']*)','([^']*)',(\d+),'([^']*)',\s*"
        r"'([^']*)','([^']*)',([^,]+),([^,]+),'([^']*)','([^']*)'"
    )
    for m in re.finditer(pattern, html):
        raw_name, dtype, dataid, fenc = m.group(1), m.group(2), m.group(3), m.group(10)
        name = html_mod.unescape(unquote(raw_name))
        items.append(
            MaterialItem(
                type=dtype,
                name=name,
                data_id=int(dataid),
                enc=fenc,
            )
        )
    # 兜底：部分校区模板用 dataBody_td + objectid（仅文件、无文件夹下钻）
    if not items:
        for tag in re.findall(r"<[^>]*dataBody_td[^>]*>", html):
            o = re.search(r'objectid="([0-9a-f]{32})"', tag, re.I)
            n = re.search(r'dataname="([^"]+)"', tag, re.I)
            if not o:
                continue
            name = html_mod.unescape(n.group(1)) if n else o.group(1)
            # objectId 模式无法用 downloadData，标记 type=object 供上层走 ananas
            items.append(
                MaterialItem(
                    type="object",
                    name=name,
                    data_id=0,
                    enc=o.group(1).lower(),
                )
            )
    return items


def parse_courses(html: str) -> list[CourseRef]:
    """从课程列表页解析课程。"""
    courses: list[CourseRef] = []
    seen: set[tuple[str, str, str]] = set()
    for m in re.finditer(
        r"stucoursemiddle\?courseid=(\d+)&clazzid=(\d+)&cpi=(\d+)", html
    ):
        cid, clazz, cpi = m.groups()
        key = (cid, clazz, cpi)
        if key in seen:
            continue
        seen.add(key)
        seg = html[m.end() : m.end() + 1600]
        nm = re.search(r'course-name[^>]*title="([^"]+)"', seg)
        name = html_mod.unescape(nm.group(1)) if nm else f"课程{cid}"
        teacher = ""
        for pm in re.finditer(r">([^<]{2,20})<", seg):
            txt = pm.group(1).strip()
            if txt and txt != name and "课程" not in txt:
                teacher = html_mod.unescape(txt)
                break
        courses.append(
            CourseRef(
                courseid=cid,
                clazzid=clazz,
                cpi=cpi,
                name=name,
                teacher=teacher,
            )
        )
    return courses


def parse_cd_filename(content_disposition: str) -> str:
    """从 Content-Disposition 还原文件名（修复学习通 CDN 裸 UTF-8）。"""
    m = re.search(r"filename\*=(?:UTF-8|utf-8)''([^;]+)", content_disposition)
    if not m:
        m = re.search(r'filename="?([^";]+)"?', content_disposition)
    if not m:
        return ""
    raw = m.group(1).strip()
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return unquote(raw)


def sanitize_filename(name: str, fallback: str = "download.bin") -> str:
    name = name.strip().strip(".").replace("..", "_")
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = " ".join(name.split())
    return (name or fallback)[:180]


def looks_like_blob_name(name: str) -> bool:
    """CDN/对象存储常见的无意义文件名（32 位 hex、UUID、纯 objectId 等）。"""
    stem = Path(name).stem.strip()
    if not stem:
        return True
    if re.fullmatch(r"[0-9a-f]{32}", stem, re.I):
        return True
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        stem,
        re.I,
    ):
        return True
    if re.fullmatch(r"[0-9a-f]{40}", stem, re.I):
        return True
    return False


def resolve_save_filename(
    preferred_name: str = "",
    cdn_name: str = "",
    dtype: str = "",
) -> str:
    """优先使用网站资料区显示名，避免落成 blob/objectId。

    若显示名缺扩展名，则从 CDN 文件名或资料类型补全。
    """
    preferred = (preferred_name or "").strip()
    cdn = (cdn_name or "").strip()

    def ensure_ext(name: str) -> str:
        if "." in Path(name).name:
            return name
        # 先从 CDN 名借扩展名
        cdn_ext = Path(cdn).suffix if cdn else ""
        if cdn_ext and len(cdn_ext) <= 8:
            return name + cdn_ext
        type_ext = guess_ext_from_type(dtype)
        if type_ext:
            return name + type_ext
        return name

    if preferred and not looks_like_blob_name(preferred):
        return ensure_ext(preferred)
    if cdn and not looks_like_blob_name(cdn):
        return ensure_ext(cdn)
    if preferred:
        return ensure_ext(preferred)
    if cdn:
        return ensure_ext(cdn)
    return ensure_ext("download")


def is_login_page(html: str) -> bool:
    head = html[:5000]
    return (
        "用户登录" in head
        or "passport2.chaoxing.com/login" in head
        or "passport2.chaoxing.com/fanyalogin" in head
    )


def guess_ext_from_type(dtype: str) -> str:
    mapping = {
        "pdf": ".pdf",
        "doc": ".doc",
        "docx": ".docx",
        "ppt": ".ppt",
        "pptx": ".pptx",
        "xls": ".xls",
        "xlsx": ".xlsx",
        "zip": ".zip",
        "rar": ".rar",
        "txt": ".txt",
        "mp4": ".mp4",
        "mp3": ".mp3",
        "png": ".png",
        "jpg": ".jpg",
        "jpeg": ".jpeg",
    }
    return mapping.get(dtype.lower(), "")
