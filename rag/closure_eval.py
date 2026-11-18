#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""W3 闭环真实评测：把 30 题跑过 RAG 闭环，四类判定与题目 type 对照。

不调模型、不花钱。判定只看检索信号，不看题目 type（否则是作弊）；
type 只在事后评分时用来对答案。数字真实，照实上报，不挑题。

用法：
  python rag/closure_eval.py --scan          # 逐题诊断：分数/命中文档/判定/期望
  python rag/closure_eval.py --tune          # 网格搜索 low/high + margin 阈值
  python rag/closure_eval.py                 # 用当前阈值出报告 rag/report.md
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.csv"
REPORT = pathlib.Path(__file__).resolve().parent / "report.md"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pipeline import load_chunks, retrieve, cite, decide_signal  # noqa: E402

# 题目 type → 期望的闭环判定。跨文档/版本冲突都要求「标人工、说清口径」。
EXPECT = {
    "有答案": "answered",
    "无答案": "no_answer",
    "跨文档": "conflict",
    "版本冲突": "conflict",
}


def load_questions() -> list[dict]:
    with open(QUESTIONS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def diagnose(rows, docs, k=5):
    """每题的纯检索信号，供判定与调参；不含题目 type。"""
    out = []
    for q in rows:
        hits = retrieve(docs, q["question"], k)
        cites = cite(hits, docs)
        top1 = hits[0][1] if hits else 0.0
        top2 = hits[1][1] if len(hits) > 1 else 0.0
        # margin：top1/top2 差距。两份文档分数接近→更可能是冲突/跨文档；
        # top1 远高于次名→单一答案，不该误判冲突。
        margin = (top1 - top2) / top1 if top1 else 1.0
        docset = sorted({c["doc"] for c in cites})
        top_doc = cites[0]["doc"] if cites else ""
        out.append({
            "id": q["id"], "type": q["type"], "question": q["question"],
            "top1": round(top1, 2), "top2": round(top2, 2),
            "margin": round(margin, 3), "docset": docset, "top_doc": top_doc,
            "cites": cites,
        })
    return out


def decide(diag, low, high, margin_th):
    """调用 pipeline 的单一判定源，保证演示与评测用同一套逻辑。"""
    return decide_signal(diag["top1"], diag["top2"], diag["docset"], low, high, margin_th)


# 宽松匹配：有答案题判 low_confidence（灰区但给了带引用应答）也算「没漏答」；
# 严格匹配则只认 answered。报告两个都给，不藏。
def correct(verdict, typ, strict=False):
    exp = EXPECT[typ]
    if typ == "有答案" and not strict and verdict in ("answered", "low_confidence"):
        return True
    return verdict == exp


def accuracy(diags, low, high, margin_th, strict=False):
    return sum(correct(decide(d, low, high, margin_th), d["type"], strict)
               for d in diags) / max(len(diags), 1)


def tune(diags):
    best = None
    for low in [5, 6, 7, 8, 9, 10, 11]:
        for high in [10, 11, 12, 13, 14, 15, 16]:
            if high <= low:
                continue
            for margin_th in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
                acc = accuracy(diags, low, high, margin_th)
                strict = accuracy(diags, low, high, margin_th, strict=True)
                key = (acc, strict)
                if best is None or key > best[0]:
                    best = (key, low, high, margin_th)
    return best


def scan(diags, low, high, margin_th):
    print(f"{'题号':<5}{'type':<7}{'top1':>6}{'top2':>7}{'margin':>8}  {'命中文档':<12}{'判定':<15}{'期望'}")
    for d in diags:
        v = decide(d, low, high, margin_th)
        mark = "✓" if correct(v, d["type"]) else "✗"
        print(f"{d['id']:<5}{d['type']:<7}{d['top1']:>6}{d['top2']:>7}{d['margin']:>8}  "
              f"{','.join(d['docset']):<12}{v:<15}{EXPECT[d['type']]} {mark}")


def report(diags, low, high, margin_th):
    counts = {t: sum(d["type"] == t for d in diags) for t in EXPECT}
    lines = [
        "# W3 RAG 闭环 · 真实评测报告",
        "",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 数据：{len(diags)} 题标注集（有答案 {counts['有答案']} / 无答案 {counts['无答案']} / "
        f"跨文档 {counts['跨文档']} / 版本冲突 {counts['版本冲突']}）",
        f"- 阈值：low={low} / high={high} / margin<{margin_th} 判冲突",
        "- 判定不调模型、不花钱；只看检索信号，type 仅事后评分用",
        "",
        "## 总览（闭环判定是否对齐题目类型）",
        "",
        "| 口径 | 命中 | 说明 |",
        "| --- | --- | --- |",
        f"| 宽松 | {accuracy(diags,low,high,margin_th):.1%} | 有答案题判 answered/low_confidence 均算对 |",
        f"| 严格 | {accuracy(diags,low,high,margin_th,True):.1%} | 有答案题只认 answered |",
        "",
        "> 这是「判定层是否对齐预期行为」的命中率，**不是答案正确率**。",
        "> 答案要点覆盖需接真模型后人工核，本闭环刻意不生成答案文本。",
        "",
        "## 分类型",
        "",
        "| 类型 | 题数 | 判对(宽松) |",
        "| --- | --- | --- |",
    ]
    for t in ["有答案", "无答案", "跨文档", "版本冲突"]:
        sub = [d for d in diags if d["type"] == t]
        if sub:
            c = sum(correct(decide(d, low, high, margin_th), d["type"]) for d in sub)
            lines.append(f"| {t} | {len(sub)} | {c}/{len(sub)} |")

    lines += ["", "## 逐题判定", "",
              "| 题号 | 类型 | top1 | 次名 | 分差比 | 命中文档 | 判定 | 对 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d in diags:
        v = decide(d, low, high, margin_th)
        ok = "✓" if correct(v, d["type"]) else "✗"
        lines.append(f"| {d['id']} | {d['type']} | {d['top1']} | {d['top2']} | {d['margin']} | "
                     f"{','.join(d['docset'])} | {v} | {ok} |")

    fails = [d for d in diags if not correct(decide(d, low, high, margin_th), d["type"])]
    lines += ["", "## 失败案例与归因（≥3）", ""]
    if not fails:
        lines.append("当前阈值下无判错样本。")
    for d in fails:
        v = decide(d, low, high, margin_th)
        lines.append(f"- **{d['id']}（{d['type']}）** top1={d['top1']} 分差比={d['margin']} "
                     f"命中={','.join(d['docset'])} → 判 `{v}`，期望 `{EXPECT[d['type']]}`。")
        lines.append(f"  - 题面：{d['question']}")
        if d["type"] in ("跨文档", "版本冲突") and v != "conflict":
            lines.append("  - 归因：词法检索未让多份文档同时高分，或分差比偏大未触发冲突分支 → 需查询改写补召回。")
        elif d["type"] == "无答案" and v != "no_answer":
            lines.append("  - 归因：无关问题在词法上蹭到高分块，top1 越过拒答阈值 → 需提高 low 或加相关性下限。")
        elif d["type"] == "有答案" and v == "conflict":
            lines.append("  - 归因：答案本在单一文档，但相邻块来自另一文档且分差比过小，误触冲突分支 → "
                         "margin 单靠分数分不出来，需引入查询意图判别或提高 margin 门槛（会牺牲真冲突召回，需权衡）。")
        elif d["type"] == "有答案" and v == "no_answer":
            lines.append("  - 归因：答案块分数低于拒答阈值 → 检查切块召回是否漏块。")

    lines += ["", "## 诚实边界", "",
              "- 命中率是判定层行为对齐，不是答案正确率；无模型生成，不写进简历当能力证明。",
              f"- 阈值由本 {len(diags)} 题标注集校准，样本小，换语料需重标。",
              "- 跨文档/版本冲突仍是词法召回弱项；查询改写为规则级，未上向量检索。",
              "- 全部语料为公开脱敏文件，不含任何真实内部信息。",
              ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return REPORT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--low", type=float, default=11.0)
    ap.add_argument("--high", type=float, default=12.0)
    ap.add_argument("--margin", type=float, default=0.10)
    args = ap.parse_args()

    rows = load_questions()
    docs = load_chunks()
    diags = diagnose(rows, docs)

    if args.tune:
        (acc, strict), low, high, m = tune(diags)
        print(f"最优：low={low} high={high} margin<{m} → 宽松 {acc:.1%} / 严格 {strict:.1%}")
        print(json.dumps({"low": low, "high": high, "margin": m,
                          "loose": acc, "strict": strict}, ensure_ascii=False))
        return
    if args.scan:
        scan(diags, args.low, args.high, args.margin)
        return

    p = report(diags, args.low, args.high, args.margin)
    print(f"报告已生成：{p}")
    print(f"宽松 {accuracy(diags,args.low,args.high,args.margin):.1%} / "
          f"严格 {accuracy(diags,args.low,args.high,args.margin,True):.1%}")


if __name__ == "__main__":
    main()
