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


def decide_signal(top1: float, top2: float, docs_hit: list[str],
                  low: float, high: float, margin_th: float) -> str:
    """纯信号判定 —— 判定逻辑的单一真相源，pipeline 与 closure_eval 共用。

    只看检索信号，不看题面类型。分差比 = (top1-top2)/top1：
    两份文档分数接近（margin 小）→ 更可能口径冲突/需跨文档整合；
    top1 远高于次名 → 单一答案，别误判冲突。
    """
    margin = (top1 - top2) / top1 if top1 else 1.0
    if top1 < low:
        return "no_answer"
    if len(docs_hit) >= 2 and margin < margin_th:
        return "conflict"
    if top1 < high:
        return "low_confidence"
    return "answered"


def decide(hits, citations, low: float, high: float, margin_th: float) -> dict:
    """把纯信号判定包装成带理由和人工标记的结果。不生成答案文本。"""
    top1 = hits[0][1] if hits else 0.0
    top2 = hits[1][1] if len(hits) > 1 else 0.0
    docs_hit = sorted({c["doc"] for c in citations})
    verdict = decide_signal(top1, top2, docs_hit, low, high, margin_th)
    margin = (top1 - top2) / top1 if top1 else 1.0

    reasons = {
        "no_answer": f"top1={top1:.2f} < 阈值 {low}，判定为资料未覆盖；不硬编答案",
        "conflict": f"命中 {len(docs_hit)} 份文档（{docs_hit}）且分差比={margin:.3f}<{margin_th}，"
                    "口径可能冲突；须人工说清适用条件，不自动择一",
        "low_confidence": f"top1={top1:.2f} 落在灰区 [{low},{high})；转人工复核，不自动作答",
        "answered": f"top1={top1:.2f} ≥ {high} 且未触发多文档冲突；给出引用，答案要点仍须人工回原文核对",
    }
    result = {"verdict": verdict, "needs_human": verdict in ("conflict", "low_confidence"),
              "reason": reasons[verdict], "citations": citations}
    if verdict == "answered":
        result["answer_points"] = "TODO(W4)：接真模型时用引用块生成，不得脱离原文"
    return result


def run(query: str, k: int, low: float, high: float, margin_th: float) -> dict:
    docs = load_chunks()
    hits = retrieve(docs, query, k)
    citations = cite(hits, docs)
    result = decide(hits, citations, low, high, margin_th)
    return {"query": query,
            "thresholds": {"low": low, "high": high, "margin": margin_th, "top_k": k},
            **result}


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


# 四条各覆盖一个判定分支（校准阈值 low=10 / high=11 / margin=0.1，k=5）：
#   answered       top1 高且单一文档主导
#   no_answer      top1 < low
#   conflict       多份文档同时高分且分差比小
#   low_confidence top1 落在灰区 [low,high)
DEMO = [
    "数据分类分级怎么建",       # answered
    "公司年度团建预算应该定多少",  # no_answer
    "个人信息保护",              # conflict（多文档+分差小）
    "委托处理",                  # low_confidence（top1≈10.7，落在灰区）
]


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 最小闭环骨架（检索→引用→判定→兜底）")
    ap.add_argument("--ask", help="单条查询")
    ap.add_argument("--demo", action="store_true", help="跑内置四类判定样例")
    ap.add_argument("-k", type=int, default=5, help="top-k，默认 5（k=5 跨文档召回优于 k=3）")
    ap.add_argument("--low", type=float, default=10.0, help="无答案阈值，默认 10.0（30 题校准）")
    ap.add_argument("--high", type=float, default=11.0, help="高置信阈值，默认 11.0（30 题校准）")
    ap.add_argument("--margin", type=float, default=0.10, help="分差比冲突阈值，默认 0.10")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    queries = DEMO if args.demo else ([args.ask] if args.ask else [])
    if not queries:
        ap.error("给 --ask 或 --demo")

    results = [run(q, args.k, args.low, args.high, args.margin) for q in queries]
    if args.json:
        print(json.dumps(results if args.demo else results[0], ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            if i:
                print("\n" + "-" * 60)
            print(pretty(r))


if __name__ == "__main__":
    main()
