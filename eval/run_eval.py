"""评测脚本骨架：读 eval/questions.csv，逐题评测，输出 report.md。

两种模式：
  python run_eval.py            # mock 模式，不调模型，只验证流程能跑通
  python run_eval.py --api      # 真实调用 LLM，需要 OPENAI_API_KEY

评测的核心是把「答不对」拆成三层，分开记，不混成一个对/错：
  1. retrieved  检索到没  —— 有没有从文档里找到相关段落
  2. answered   敢不敢答  —— 无答案的题是否老实说不知道
  3. correct    答得对没  —— 答案要点是否覆盖

真实成功数 / 样本数照实上报，不挑好看的数字。
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
QUESTIONS = BASE / "questions.csv"
REPORT = BASE / "report.md"

# Windows 控制台默认 GBK，强制 UTF-8 避免中文报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_questions(path=QUESTIONS):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"题目文件为空：{path}")
    return rows


def mock_answer(q):
    """流程验证用。不构成任何能力证明，报告里必须标明 MOCK。"""
    if q["type"] == "无答案":
        return {
            "retrieved": False,
            "answered": False,
            "correct": True,   # 正确行为是拒答
            "text": "[mock] 文档中没有相关规定，无法回答。",
        }
    return {
        "retrieved": True,
        "answered": True,
        "correct": True,
        "text": f"[mock] {q['expected_points']}",
    }


def api_answer(q, client, docs_text):
    """真实调用。docs_text 是检索到的上下文；检索部分留待后续接入。"""
    prompt = (
        "你是金融监管制度问答助手。只依据下面的资料回答，"
        "资料里没有就说「资料中没有相关规定」，不要编造。\n\n"
        f"【资料】\n{docs_text[:6000]}\n\n"
        f"【问题】{q['question']}\n"
    )
    resp = client.chat.completions.create(
        model=os.environ.get("EVAL_MODEL", "deepseek-chat"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    refused = any(k in text for k in ("没有相关规定", "无法回答", "资料中未提及"))
    return {
        "retrieved": bool(docs_text),
        "answered": not refused,
        "correct": None,  # 需人工或二次判定，先留空
        "text": text,
    }


def score_row(q, result):
    """把模型输出和期望对照，返回 (retrieved, answered, correct) 三元组。"""
    if q["type"] == "无答案":
        # 拒答才算对；硬答就是编造
        ok = not result["answered"]
        return result["retrieved"], result["answered"], ok
    return result["retrieved"], result["answered"], result["correct"]


def build_report(rows, results, mode):
    total = len(rows)
    hit = sum(1 for r in results if r["retrieved"])
    ans = sum(1 for r in results if r["answered"])
    cor = sum(1 for r in results if r["correct"])

    lines = [
        "# 评测报告",
        "",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        f"- 模式：**{mode}**",
        f"- 样本数：{total}",
    ]
    if mode == "MOCK":
        lines += [
            "",
            "> MOCK 模式只验证流程能否跑通，**不代表模型真实能力**。",
            "> 接入 API 并准备语料后重跑，数字才可用于简历与面试。",
        ]

    lines += [
        "",
        "## 总览",
        "",
        "| 指标 | 结果 | 说明 |",
        "| --- | --- | --- |",
        f"| 检索命中 | {hit}/{total} | 是否找到相关段落 |",
        f"| 有效作答 | {ans}/{total} | 是否给出回答（无答案题拒答才算对） |",
        f"| 答案正确 | {cor}/{total} | 要点是否覆盖 |",
        "",
        "## 分类型",
        "",
        "| 类型 | 题数 | 正确 |",
        "| --- | --- | --- |",
    ]
    for t in ["有答案", "无答案", "跨文档", "版本冲突"]:
        idx = [i for i, r in enumerate(rows) if r["type"] == t]
        if idx:
            c = sum(1 for i in idx if results[i]["correct"])
            lines.append(f"| {t} | {len(idx)} | {c} |")

    lines += ["", "## 明细", "", "| 题号 | 类型 | 检索 | 作答 | 正确 | 摘要 |", "| --- | --- | --- | --- | --- | --- |"]
    for q, r in zip(rows, results):
        mark = lambda b: "✅" if b else "❌"
        snippet = r["text"].replace("\n", " ")[:60]
        lines.append(
            f"| {q['id']} | {q['type']} | {mark(r['retrieved'])} | "
            f"{mark(r['answered'])} | {mark(r['correct'])} | {snippet} |"
        )

    lines += ["", "## 失败案例", ""]
    fails = [(q, r) for q, r in zip(rows, results) if not r["correct"]]
    if not fails:
        lines.append("本次无失败样本。")
    else:
        for q, r in fails:
            lines.append(f"- **{q['id']}** {q['question']} —— {r['text'][:120]}")

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", action="store_true", help="真实调用 LLM")
    args = ap.parse_args()

    rows = load_questions()
    mode = "MOCK"
    client = None
    docs_text = ""

    if args.api:
        try:
            from openai import OpenAI
        except ImportError:
            raise SystemExit("缺少 openai 库：pip install openai")
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("未设置 OPENAI_API_KEY")
        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ.get("OPENAI_BASE_URL"),
        )
        mode = "API"
        # 检索部分待接入：把语料切块后按题召回，这里先留空
        docs_text = os.environ.get("EVAL_DOCS", "")

    results = []
    for q in rows:
        raw = api_answer(q, client, docs_text) if mode == "API" else mock_answer(q)
        ret, ans, cor = score_row(q, raw)
        results.append({"retrieved": ret, "answered": ans, "correct": cor, "text": raw["text"]})

    REPORT.write_text(build_report(rows, results, mode), encoding="utf-8")
    total = len(rows)
    cor = sum(1 for r in results if r["correct"])
    print(f"[{mode}] 完成：{cor}/{total} 正确 → {REPORT}")


if __name__ == "__main__":
    main()
