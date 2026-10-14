"""轻量自检（无需登录）：python -m chaoxing_dl.parse_test"""

from .parse import (
    parse_course_url,
    parse_materials,
    resolve_save_filename,
    sanitize_filename,
)

SAMPLE = r"""
<dt onclick="toOpen('%E8%AE%B2%E4%B9%89','afolder',12345,'x','y','z',0,0,'a','folderencABC'">
<dt onclick="toOpen('intro.pdf','pdf',67890,'x','y','z',0,0,'a','fileencXYZ'">
"""

URL = (
    "https://mooc1.s.ecust.edu.cn/mooc2-ans/mooc2-ans/mycourse/stu"
    "?courseid=441650002012905&clazzid=441650002045776"
    "&cpi=441650002535197&enc=693a23eb91f4a3ab1c26f5f87d29c30f"
)


def main() -> None:
    c = parse_course_url(URL)
    assert c.courseid == "441650002012905"
    assert c.clazzid == "441650002045776"
    assert c.cpi == "441650002535197"
    assert "ecust" in c.host
    items = parse_materials(SAMPLE)
    assert len(items) == 2
    assert items[0].is_folder and items[0].name == "讲义"
    assert items[1].type == "pdf" and items[1].data_id == 67890
    assert sanitize_filename('a/b:c*.pdf') == "a_b_c_.pdf"
    assert (
        resolve_save_filename(
            preferred_name="第1章 绪论.pptx",
            cdn_name="a1b2c3d4e5f6789012345678abcdef01.pptx",
        )
        == "第1章 绪论.pptx"
    )
    assert (
        resolve_save_filename(
            preferred_name="讲义大纲",
            cdn_name="deadbeefdeadbeefdeadbeefdeadbeef.pdf",
            dtype="pdf",
        )
        == "讲义大纲.pdf"
    )
    print("parse_test OK")


if __name__ == "__main__":
    main()
