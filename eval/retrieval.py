#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""词法检索基线（BM25 + 中文字符二元组），用来量「检索命中」这一层。

为什么要一个不调模型的基线：
  三层指标里，检索命中只跟切块和召回有关，跟模型无关。先有基线，才知道后面
  上向量检索是「真的变好了」还是「只是换了个方法」。

用法：
    python eval/retrieval.py                          # 跑 9 道已核题的抽检
    python eval/retrieval.py --ask "C3类信息能否委托处理"   # 单条查询看召回
    python eval/retrieval.py -k 5                     # 改 top-k
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
from collections import Counter

BASE = pathlib.Path(__file__).parent
CHUNKS = BASE / "chunks.jsonl"

# 已回原文核对过的 9 道题：题号 -> 可接受的正确块（命中任意一个算命中）
# 说明：这是抽检集，不是全量标注。数字只代表这 9 道的检索表现。
GOLD: dict[str, list[str]] = {
    "Q13": ["C:4.2"],
    "Q14": ["C:4.2"],
    "Q15": ["C:4.3"],
    "Q16": ["C:6.1.2"],
    "Q17": ["C:6.1.4.4"],
    "Q26": ["C:4.2", "A:第十八条"],
    "Q27": ["A:第六十九条", "C:7.5"],
    "Q28": ["A:第三十条", "A:第三十一条", "C:6.1.4.4"],
    "Q30": ["C:4.2", "A:第十八条"],
}


def grams(text: str) -> list[str]:
    """中文无空格，用字符二元组做词项；英文数字按词切。"""
    text = re.sub(r"\s+", "", text)
    out = [text[i : i + 2] for i in range(len(text) - 1)]
    out += re.findall(r"[a-zA-Z0-9]+", text)
    return out


class BM25:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.tf = [Counter(grams(d["text"])) for d in docs]
        self.len = [sum(t.values()) for t in self.tf]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df: Counter = Counter()
        for t in self.tf:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.k1, self.b = 1.5, 0.75

    def search(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        q = grams(query)
        scores = []
        for i, t in enumerate(self.tf):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
            for w in q:
                f = t.get(w)
                if not f:
                    continue
                s += self.idf.get(w, 0.0) * f * (self.k1 + 1) / (f + norm)
            scores.append((self.docs[i]["id"], s))
        scores.sort(key=lambda x: -x[1])
        return scores[:k]


def load_chunks() -> list[dict]:
    if not CHUNKS.exists():
        raise SystemExit("缺少 chunks.jsonl：先跑 python eval/chunk.py")
    return [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]


def gold_ids(keys: list[str], docs: list[dict]) -> set[str]:
    """把「A:第十八条」「C:4.2」翻译成块 id。"""
    ids: set[str] = set()
    for key in keys:
        code, clause = key.split(":", 1)
        for d in docs:
            if d["doc"] == code and d["clause"] == clause:
                ids.add(d["id"])
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ask")
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()

    docs = load_chunks()
    bm = BM25(docs)

    if args.ask:
        for cid, score in bm.search(args.ask, args.k):
            d = next(x for x in docs if x["id"] == cid)
            head = d["text"][:70].replace("\n", " ")
            print(f"{score:6.2f}  {cid}  [{d['doc']} {d['clause']}]  {head}")
        return

    # 抽检：读题面，看 gold 是否进 top-k
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO((BASE / "questions.csv").read_text(encoding="utf-8-sig"))))
    qmap = {r["id"]: r["question"] for r in rows}

    hit = 0
    for qid, keys in GOLD.items():
        gids = gold_ids(keys, docs)
        got = [cid for cid, _ in bm.search(qmap.get(qid, ""), args.k)]
        ok = bool(gids & set(got))
        hit += ok
        print(f"{qid} {'✓' if ok else '✗'}  期望 {sorted(gids) or '（未找到对应块）'}  实得 {got}")

    total = len(GOLD)
    print(f"\n检索命中 recall@{args.k} = {hit}/{total} = {hit/total:.1%}（抽检集，仅 9 题已核）")
    if hit < total:
        print("未命中的题：先看切块是否切碎了答案，再考虑上向量检索；别一上来就换方案。")


if __name__ == "__main__":
    main()
