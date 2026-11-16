#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 docs/ 下的三份监管文本切成带条款元数据的块，输出 chunks.jsonl。

为什么按「条/节」切而不是按固定字数切：
  监管文件的一条就是一个完整要求，固定长度切会把「C3 不得委托」和「委托需去标识化」
  切到两个块里，检索到任意一块都答不完整。按结构切，天然对齐评测题的答案边界。

用法：
    python eval/chunk.py            # 读 eval/docs/*.txt，写 eval/chunks.jsonl
    python eval/chunk.py --stats    # 只打印统计
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).parent / "docs"
OUT = pathlib.Path(__file__).parent / "chunks.jsonl"

MAX_CHARS = 700   # 单块上限，超出则另起一块（长条不硬切，允许超一点）
MIN_CHARS = 60    # 太短的块并到下一块

# A/B：第X条 开头的条文
RE_ARTICLE = re.compile(r"^第[一二三四五六七八九十百零]+条")
# C：形如 4.2 / 6.1.4.4 / 7.5 的编号标题
RE_SECTION = re.compile(r"^(\d+(?:\.\d+){0,3})\s+\S")
# 章节标题，仅作元数据
RE_CHAPTER = re.compile(r"^第[一二三四五六七八九十]+章\s*(\S*)")


def read_doc(code: str) -> str:
    hits = sorted(DOCS.glob(f"{code}_*.txt"))
    if not hits:
        sys.exit(f"缺少 {code} 语料，请先跑 fetch_docs.py / extract_pdf.py")
    return hits[0].read_text(encoding="utf-8")


def split_articles(code: str, text: str) -> list[dict]:
    chunks: list[dict] = []
    chapter = ""
    cur_clause = ""
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            chunks.append({"doc": code, "chapter": chapter, "clause": cur_clause, "text": body})
        buf.clear()

    for line in text.splitlines():
        m_ch = RE_CHAPTER.match(line)
        if m_ch:
            flush()
            chapter = line.strip()
            cur_clause = ""
            continue
        if RE_ARTICLE.match(line):
            # 一条一块：短条（如「本办法由总局负责解释」）也独立成块，
            # 合并会让「第X条」在被引用时找不到对应块
            flush()
            cur_clause = RE_ARTICLE.match(line).group(0)
            buf.append(line)
            continue
        if buf and sum(len(x) for x in buf) + len(line) > MAX_CHARS:
            flush()
            cur_clause = cur_clause or ""
        buf.append(line)
    flush()
    return chunks


def split_sections(code: str, text: str) -> list[dict]:
    chunks: list[dict] = []
    cur_no = ""
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            chunks.append({"doc": code, "chapter": "", "clause": cur_no, "text": body})
        buf.clear()

    for line in text.splitlines():
        if "...." in line:          # 目录点线，对检索是纯噪声
            continue
        m = RE_SECTION.match(line)
        if m:
            flush()
            cur_no = m.group(1)
            buf.append(line)
            continue
        if buf and sum(len(x) for x in buf) + len(line) > MAX_CHARS:
            flush()
        buf.append(line)
    flush()
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    plan = [("A", split_articles), ("B", split_articles), ("C", split_sections)]
    all_chunks: list[dict] = []
    for code, fn in plan:
        text = read_doc(code)
        parts = fn(code, text)
        # 过滤目录/封面/来源声明类碎片（短条文也要留，附则类常只有一句）
        parts = [
            p for p in parts
            if len(p["text"]) >= 20 and not (p["text"].startswith(("ICS", "银行业金融机构数据治理指引（", "银行保险机构数据安全管理办法（")))
        ]
        for i, p in enumerate(parts, 1):
            p["id"] = f"{code}-{i:03d}"
        all_chunks.extend(parts)
        lens = [len(p["text"]) for p in parts]
        print(f"{code}: {len(parts)} 块｜平均 {sum(lens)//max(len(lens),1)} 字｜最长 {max(lens) if lens else 0}")

    lens = [len(c["text"]) for c in all_chunks]
    print(f"合计 {len(all_chunks)} 块｜总 {sum(lens)} 字｜平均 {sum(lens)//max(len(lens),1)} 字")

    if args.stats:
        return

    with OUT.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"已写出 {OUT}")


if __name__ == "__main__":
    main()
