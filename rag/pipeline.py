#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RAG 最小闭环骨架（W3）：检索 → 引用回溯 → 判定 → 人工兜底。

不调模型、不花钱：判定层是规则化的，离线可跑、可复现。
这不是「能聊天的助手」，是把 RAG 最容易翻车的三件事
（无答案硬编 / 版本冲突瞎选 / 低置信乱答）用可验证规则兜住的工程骨架。

闭环四环节：
  1. 检索   —— 复用 eval/retrieval.py 的 BM25 + 中文字符二元组，不重造
  2. 引用回溯 —— 每个命中块带 doc/chapter/clause + 原文 text，可回到原文
  3. 判定   —— top1 分数分带 → 无答案 / 有答案 / 低置信；多文档高分 → 冲突
  4. 兜底   —— 冲突与低置信一律 needs_human=true，不自动下结论

用法：
  python rag/pipeline.py --ask "发生数据安全事件后多长时间报告监管"
  python rag/pipeline.py --ask "完全无关的问题xyzzy"
  python rag/pipeline.py --demo        # 内置样例，展示四类判定

阈值 low/high 是启发式初值（来自实测分数分布），必须用 eval/questions.csv
的 30 题标注集校准；详见 rag/README.md。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_retrieval():
    """从文件路径加载 eval/retrieval.py，避开 `eval` 作为包名的坑。"""
    path = ROOT / "eval" / "retrieval.py"
    spec = importlib.util.spec_from_file_location("_rag_retrieval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_chunks() -> list[dict]:
    rt = _load_retrieval()
    return rt.load_chunks()


def retrieve(docs: list[dict], query: str, k: int) -> list[tuple[str, float]]:
    rt = _load_retrieval()
    return rt.BM25(docs).search(query, k)


def cite(hits: list[tuple[str, float]], docs: list[dict], quote_len: int = 80) -> list[dict]:
    """引用回溯：块 id → 所属文档/章/条 + 原文片段。面试看的是能不能回到原文。"""
    by_id = {d["id"]: d for d in docs}
    out = []
    for cid, score in hits:
        d = by_id[cid]
        out.append(
            {
                "chunk_id": cid,
                "doc": d["doc"],
                "chapter": d.get("chapter", ""),
                "clause": d.get("clause", ""),
                "quote": d["text"][:quote_len].replace("\n", " "),
                "score": round(score, 2),
            }
        )
    return out


def decide(hits, citations, low: float, high: float) -> dict:
    """规则化判定。不生成答案，只给『能不能答 / 要不要人看』的可验证结论。"""
    if not hits:
        return {"verdict": "no_answer", "needs_human": False,
                "reason": "检索无结果", "citations": []}

    top = hits[0][1]
    if top < low:
        return {"verdict": "no_answer", "needs_human": False,
                "reason": f"top1={top:.2f} < 阈值 {low}，判定为资料未覆盖；不硬编答案",
                "citations": citations}

    # 冲突：多个文档同时高分命中 → 口径可能不同，列各自适用条件，不替用户选
    strong = [(cid, s) for cid, s in hits if s >= high * 0.8]
    doc_set = {c["doc"] for c in citations if c["score"] >= high * 0.8}
    if len(doc_set) >= 2:
        return {"verdict": "conflict", "needs_human": True,
                "reason": f"命中 {len(doc_set)} 份不同文档（{sorted(doc_set)}）且均高分，"
                          "口径可能冲突；须人工说清各自适用条件，不自动择一",
                "citations": citations}

    if top < high:
        return {"verdict": "low_confidence", "needs_human": True,
                "reason": f"top1={top:.2f} 落在灰区 [{low},{high})；转人工复核，不自动作答",
                "citations": citations}

    return {"verdict": "answered", "needs_human": False,
            "reason": f"top1={top:.2f} ≥ {high}；给出引用，答案要点仍须人工回原文核对",
            "citations": citations, "answer_points": "TODO(W4)：接真模型时用引用块生成，不得脱离原文"}


def run(query: str, k: int, low: float, high: float) -> dict:
    docs = load_chunks()
    hits = retrieve(docs, query, k)
    citations = cite(hits, docs)
    result = decide(hits, citations, low, high)
    return {"query": query, "thresholds": {"low": low, "high": high, "top_k": k}, **result}


def pretty(r: dict) -> str:
    label = {"answered": "有答案", "no_answer": "无答案(拒答)",
             "conflict": "版本冲突", "low_confidence": "低置信兜底"}
    lines = [f"查询：{r['query']}", f"判定：{label[r['verdict']]}  "
             f"(needs_human={r['needs_human']})", f"依据：{r['reason']}"]
    if r["citations"]:
        lines.append("引用回溯：")
        for c in r["citations"]:
            lines.append(f"  - {c['doc']} {c['clause']} [{c['score']}] {c['quote']}…")
    return "\n".join(lines)


# 四条已实测、各覆盖一个判定分支（阈值 low=8 / high=13，BM25 top-3）：
#   answered       top1≈23，单一文档 A 主导
#   no_answer      top1≈6.5  < low
#   conflict       多份文档 A/B/C 同时高分（语义上也确实跨办法与指引）
#   low_confidence top1≈8.9 落在灰区 [8,13)
DEMO = [
    "数据分类分级怎么建",
    "公司年度团建预算应该定多少",
    "个人信息保护",
    "数据治理",
]


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 最小闭环骨架（检索→引用→判定→兜底）")
    ap.add_argument("--ask", help="单条查询")
    ap.add_argument("--demo", action="store_true", help="跑内置四类判定样例")
    ap.add_argument("-k", type=int, default=3, help="top-k，默认 3")
    ap.add_argument("--low", type=float, default=8.0, help="无答案阈值，默认 8.0")
    ap.add_argument("--high", type=float, default=13.0, help="高置信阈值，默认 13.0")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    queries = DEMO if args.demo else ([args.ask] if args.ask else [])
    if not queries:
        ap.error("给 --ask 或 --demo")

    results = [run(q, args.k, args.low, args.high) for q in queries]
    if args.json:
        print(json.dumps(results if args.demo else results[0], ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            if i:
                print("\n" + "-" * 60)
            print(pretty(r))


if __name__ == "__main__":
    main()
