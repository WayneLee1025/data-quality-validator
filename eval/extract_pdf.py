#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把标准类 PDF 转成可检索的纯文本（用于 C：JR/T 0171—2020）。

用法：
    python eval/extract_pdf.py 桌面上的文件.pdf                     # 自动生成 docs/C_<标题>.txt
    python eval/extract_pdf.py xxx.pdf --out eval/docs/C_x.txt       # 指定输出
    python eval/extract_pdf.py xxx.pdf --check                       # 只检查有没有文字层

设计要点（面试可讲）：
  1. 先判文字层。扫描版 PDF 提取出来是空字符串，必须转 OCR，不能假装读到了。
  2. 去页眉页脚。标准类 PDF 每页重复「JR/T 0171—2020」和页码，留着会污染检索与切块。
  3. 不做段落合并。中文 PDF 的换行位置不可靠，硬合并容易把两条要求粘成一条。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("缺少 pypdf：pip install pypdf")

# 页码形态：罗马数字、纯数字、带「第 x 页」前缀
RE_PAGE_NO = re.compile(r"^(?:第\s*)?(?:\d{1,3}|[IVXLC]{1,5})(?:\s*页)?$", re.I)


def looks_like_header(line: str, std_no: str | None) -> bool:
    """判断是否为重复页眉。"""
    if std_no and re.sub(r"\s", "", line) == re.sub(r"\s", "", std_no):
        return True
    # 单独一行只有标准号，如 JR/T 0171—2020
    if re.fullmatch(r"JR/?T\s*\d{3,5}[—\-–]\d{4}", line):
        return True
    return False


def detect_std_no(pages: list[str]) -> str | None:
    """从首页猜标准号，用于去页眉。"""
    head = pages[0][:500] if pages else ""
    m = re.search(r"(JR/?T\s*\d{3,5}[—\-–]\d{4})", head)
    return m.group(1) if m else None


def extract(path: pathlib.Path) -> tuple[str, dict]:
    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    empty = [i + 1 for i, t in enumerate(pages) if len(t.strip()) < 10]
    std_no = detect_std_no(pages)

    lines: list[str] = []
    for text in pages:
        for raw in text.splitlines():
            line = re.sub(r"[ \t\u3000]+", " ", raw).strip()
            if not line:
                continue
            if looks_like_header(line, std_no) or RE_PAGE_NO.match(line):
                continue
            lines.append(line)

    body = "\n".join(lines)
    meta = {
        "pages": len(pages),
        "empty_pages": empty,
        "chars": len(body),
        "std_no": std_no or "未识别",
        "text_layer": bool(body.strip()),
    }
    return body, meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", help="输出 txt 路径，默认按标准号生成")
    ap.add_argument("--check", action="store_true", help="只打印检查结果，不写文件")
    args = ap.parse_args()

    src = pathlib.Path(args.pdf).expanduser()
    if not src.exists():
        sys.exit(f"找不到文件：{src}")

    body, meta = extract(src)
    print(f"页数 {meta['pages']}｜字符数 {meta['chars']}｜标准号 {meta['std_no']}")
    if meta["empty_pages"]:
        print(f"无文字层页：{meta['empty_pages']}")
    if not meta["text_layer"]:
        sys.exit("整份 PDF 没有文字层，是扫描件，需先 OCR；本脚本不做图像识别。")
    if meta["empty_pages"]:
        print("提示：个别空页通常是版权页或空白页；若空页比例高，说明是扫描件混排。")

    if args.check:
        return

    out = pathlib.Path(args.out) if args.out else pathlib.Path("eval/docs") / (
        f"C_{src.stem}.txt" if not meta["std_no"].startswith("JR") else "C_个人金融信息保护技术规范.txt"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"已写出 {out}（{out.stat().st_size} 字节）")


if __name__ == "__main__":
    main()
