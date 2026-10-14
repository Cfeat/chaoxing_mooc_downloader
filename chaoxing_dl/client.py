"""超星资料区 API 客户端（兼容官方域名与各校门户）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import cookies_for_requests, has_session
from .parse import (
    CourseRef,
    MaterialItem,
    is_login_page,
    parse_cd_filename,
    parse_courses,
    parse_materials,
    resolve_save_filename,
    sanitize_filename,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DOWNLOAD_REFERER = "https://pan-yz.chaoxing.com/"
TIMEOUT = 25
DOWNLOAD_TIMEOUT = (15, 180)


def _is_school_host(host: str) -> bool:
    h = host.lower()
    return "chaoxing.com" not in h and "cldisk.com" not in h


class ChaoxingClient:
    """登录态下访问课程列表 / 资料区 / 下载。"""

    def __init__(
        self,
        *,
        session_root: Optional[Path] = None,
        course_host: str = "",
        request_interval: float = 0.25,
    ):
        if not has_session(session_root):
            raise FileNotFoundError(
                "尚未登录。请先运行: python -m chaoxing_dl login"
            )
        self.session_root = session_root
        self.course_host = course_host
        self.request_interval = request_interval
        self._last_req = 0.0

        self.http = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.6,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        self.http.mount("https://", HTTPAdapter(max_retries=retries))
        self.http.mount("http://", HTTPAdapter(max_retries=retries))
        self.http.headers.update(
            {
                "User-Agent": UA,
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        for name, value in cookies_for_requests(session_root).items():
            self.http.cookies.set(name, value)

    def _throttle(self) -> None:
        gap = self.request_interval - (time.time() - self._last_req)
        if gap > 0:
            time.sleep(gap)
        self._last_req = time.time()

    def get(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        kwargs.setdefault("timeout", TIMEOUT)
        return self.http.get(url, **kwargs)

    # ---- 端点解析 ---------------------------------------------------------

    def datalist_candidates(self, host: str) -> list[str]:
        """按优先级返回资料列表 URL 模板（format: course params 已拼好前缀）。"""
        urls: list[str] = []
        if host and _is_school_host(host):
            # 华东理工等：mooc1.s.xxx.edu.cn/mooc2-ans/mooc2-ans/...
            urls.append(
                f"https://{host}/mooc2-ans/mooc2-ans/coursedata/stu-datalist"
            )
            urls.append(f"https://{host}/mooc2-ans/coursedata/stu-datalist")
        urls.append(
            "https://mooc2-ans.chaoxing.com/mooc2-ans/coursedata/stu-datalist"
        )
        # 去重保序
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def download_candidates(self, host: str) -> list[str]:
        urls: list[str] = []
        if host and _is_school_host(host):
            urls.append(f"https://{host}/coursedata/downloadData")
            urls.append(f"https://{host}/mooc-ans/coursedata/downloadData")
        urls.append("https://mooc1.chaoxing.com/coursedata/downloadData")
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    # ---- 课程列表 ---------------------------------------------------------

    def list_courses(self) -> list[CourseRef]:
        url = (
            "https://mooc2-ans.chaoxing.com/mooc2-ans/visit/courselistdata"
            "?courseType=1&courseFolderId=0&courseFolderSize=0"
        )
        r = self.get(url, headers={"Referer": "https://i.chaoxing.com/"})
        if is_login_page(r.text):
            raise RuntimeError("会话已失效，请重新登录: python -m chaoxing_dl login")
        courses = parse_courses(r.text)
        if not courses:
            # 互动页兜底
            r2 = self.get(
                "https://mooc2-ans.chaoxing.com/visit/interaction",
                headers={"Referer": "https://i.chaoxing.com/"},
            )
            courses = parse_courses(r2.text)
        return courses

    # ---- 资料区 -----------------------------------------------------------

    def fetch_materials(
        self,
        course: CourseRef,
        folder_data_id: int = 0,
        folder_enc: str = "",
    ) -> list[MaterialItem]:
        host = course.host or self.course_host
        params = {
            "courseid": course.courseid,
            "clazzid": course.clazzid,
            "cpi": course.cpi,
            "ut": "s",
        }
        if folder_data_id:
            params["dataId"] = folder_data_id
            params["enc"] = folder_enc

        last_err: Optional[Exception] = None
        for base in self.datalist_candidates(host):
            try:
                r = self.get(
                    base,
                    params=params,
                    headers={
                        "Referer": (
                            f"https://{host}/mooc2-ans/mooc2-ans/mycourse/stu"
                            f"?courseid={course.courseid}"
                            if host
                            else "https://mooc2-ans.chaoxing.com/"
                        )
                    },
                )
                if is_login_page(r.text):
                    raise RuntimeError("会话已失效，请重新登录")
                if r.status_code != 200:
                    continue
                items = parse_materials(r.text)
                # 空列表也可能是真的空文件夹；若 HTML 很短且无 toOpen，试下一个端点
                if items or "toOpen" in r.text or "dataBody" in r.text or len(r.text) > 800:
                    return items
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise last_err
        return []

    def build_tree(
        self,
        course: CourseRef,
        *,
        max_depth: int = 12,
        on_progress=None,
    ) -> list[MaterialItem]:
        """递归拉取整棵资料树，path 写入每项。"""
        visited: set[tuple[int, str]] = set()

        def walk(
            folder_id: int,
            enc: str,
            prefix: str,
            depth: int,
        ) -> list[MaterialItem]:
            if depth > max_depth:
                return []
            key = (folder_id, enc)
            if key in visited:
                return []
            visited.add(key)
            try:
                items = self.fetch_materials(course, folder_id, enc)
            except Exception as e:
                if on_progress:
                    on_progress(f"跳过文件夹 {prefix or '/'}: {e}")
                return []
            out: list[MaterialItem] = []
            for it in items:
                it.path = f"{prefix}{it.name}" if prefix else it.name
                if on_progress:
                    kind = "📁" if it.is_folder else "📄"
                    on_progress(f"  {kind} {it.path}")
                if it.is_folder:
                    it.children = walk(
                        it.data_id, it.enc, f"{it.path}/", depth + 1
                    )
                out.append(it)
            return out

        return walk(0, "", "", 1)

    def collect_files(
        self,
        course: CourseRef,
        *,
        max_depth: int = 12,
        on_progress=None,
    ) -> list[MaterialItem]:
        tree = self.build_tree(course, max_depth=max_depth, on_progress=on_progress)
        files: list[MaterialItem] = []
        for node in tree:
            files.extend(node.flatten_files())
        return files

    # ---- 下载 -------------------------------------------------------------

    def download_file(
        self,
        course: CourseRef,
        item: MaterialItem,
        save_dir: Path,
        *,
        keep_structure: bool = True,
    ) -> dict:
        """下载单个资料文件，返回 {path, size, name}。"""
        save_dir = Path(save_dir)
        if keep_structure and item.path and "/" in item.path:
            rel_parent = Path(item.path).parent
            target_dir = save_dir / rel_parent
        else:
            target_dir = save_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # objectId 兜底路径（少数校区模板）
        if item.type == "object" and item.enc:
            return self._download_via_ananas(item.enc, target_dir, item.name)

        host = course.host or self.course_host
        params = {
            "dataId": item.data_id,
            "classId": course.clazzid,
            "cpi": course.cpi,
            "courseId": course.courseid,
            "ut": "s",
        }
        last_err: Optional[Exception] = None
        for base in self.download_candidates(host):
            try:
                r = self.get(
                    base,
                    params=params,
                    allow_redirects=False,
                    headers={"Referer": DOWNLOAD_REFERER},
                )
                if r.status_code not in (301, 302, 303, 307, 308):
                    last_err = RuntimeError(f"{base} -> HTTP {r.status_code}")
                    continue
                cdn = r.headers.get("Location")
                if not cdn:
                    last_err = RuntimeError("无 Location")
                    continue
                if not cdn.startswith("http"):
                    cdn = urljoin(base, cdn)
                return self._stream_cdn(
                    cdn, target_dir, preferred_name=item.name, dtype=item.type
                )
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(
            f"下载失败: {item.name} ({last_err})"
        )

    def _stream_cdn(
        self,
        cdn: str,
        target_dir: Path,
        *,
        preferred_name: str = "",
        dtype: str = "",
    ) -> dict:
        with self.http.get(
            cdn,
            headers={"Referer": DOWNLOAD_REFERER, "User-Agent": UA},
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
        ) as r:
            if r.status_code != 200:
                raise RuntimeError(f"CDN HTTP {r.status_code}")
            cd = r.headers.get("Content-Disposition", "")
            cdn_name = parse_cd_filename(cd)
            # 优先用资料区显示名，避免 CDN 返回的 objectId/blob 名
            fname = resolve_save_filename(
                preferred_name=preferred_name,
                cdn_name=cdn_name,
                dtype=dtype,
            )
            path = target_dir / sanitize_filename(fname)
            # 重名追加序号
            if path.exists():
                stem, suffix = path.stem, path.suffix
                n = 2
                while path.exists():
                    path = target_dir / f"{stem}_{n}{suffix}"
                    n += 1
            tmp = path.with_suffix(path.suffix + ".part")
            total = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            tmp.replace(path)
            return {"path": str(path), "size": total, "name": path.name}

    def _download_via_ananas(
        self, object_id: str, target_dir: Path, preferred_name: str
    ) -> dict:
        """少数模板只有 objectId 时，走 ananas/status 取直链。"""
        for host in (
            "https://mooc2-ans.chaoxing.com",
            "https://mooc1.chaoxing.com",
        ):
            url = (
                f"{host}/ananas/status/{object_id}"
                f"?flag=normal&_dc={int(time.time() * 1000)}"
            )
            r = self.get(url, headers={"Referer": "https://mooc2-ans.chaoxing.com/"})
            if r.status_code != 200:
                continue
            try:
                data = r.json()
            except Exception:
                continue
            if data.get("status") == "success" and data.get("download"):
                # 仍以资料区显示名为准；ananas 文件名只作扩展名等兜底
                server_name = data.get("filename") or data.get("name") or ""
                name = preferred_name or server_name
                return self._stream_cdn(
                    data["download"],
                    target_dir,
                    preferred_name=name,
                    dtype="",
                )
        raise RuntimeError(f"ananas 无法解析 objectId={object_id}")
