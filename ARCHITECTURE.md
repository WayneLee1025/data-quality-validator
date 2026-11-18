# 架构图（白板版 + mermaid 版）

## 一、能画在白板上的极简版（30 秒画完）

```
   三份公开监管文件(gov.cn)
        │  fetch_docs / extract_pdf
        ▼
   A81条 B55条 C25011字  →按条/节切→ 185 chunks
        │
        ▼
  ┌──────────── 判定闭环（pipeline.py，单一真相源）────────────┐
  │  查询 → ①BM25检索(top5) → ②引用回溯 → ③信号判定 → ④兜底   │
  │                                    ↓                        │
  │                        answered/no_answer/conflict/          │
  │                              low_confidence                  │
  └──────────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
   /ask HTTP端点                  50题标注集 → closure_eval
   (FastAPI/标准库)                → 网格校准 → report.md
```

口播锚点：**上面是数据、中间是判定、下面左边是服务、右边是评测。判定逻辑只有一份。**

## 二、mermaid 版（GitHub README 原生渲染）

```mermaid
flowchart TD
    SRC[公开监管文件<br/>gov.cn 三份] --> EXTRACT[fetch_docs / extract_pdf<br/>抓取清洗]
    EXTRACT --> CORPUS[A 81条 / B 55条 / C 25011字]
    CORPUS --> CHUNK[chunk.py<br/>按条/节切块]
    CHUNK --> STORE[(185 chunks<br/>chunks.jsonl)]

    STORE --> RETR[① BM25 + 中文字符二元组<br/>top-5 检索]
    Q[用户查询] --> RETR
    RETR --> CITE[② 引用回溯<br/>doc/chapter/clause/原文]
    CITE --> DECIDE[③ decide_signal<br/>单一判定源]
    DECIDE --> V1[answered]
    DECIDE --> V2[no_answer 拒答]
    DECIDE --> V3[conflict]
    DECIDE --> V4[low_confidence]
    V3 --> HUMAN[④ needs_human=true<br/>转人工不自动下结论]
    V4 --> HUMAN

    DECIDE --> API[/ask HTTP 端点<br/>FastAPI + 标准库双实现]
    DECIDE --> EVAL[closure_eval<br/>50题标注集]
    EVAL --> TUNE[网格搜索阈值<br/>low=11 high=12 margin=0.1]
    TUNE --> REPORT[report.md<br/>宽松76% 严格74%<br/>12个失败案例归因]
```

## 三、两个体现设计能力的关键决策

1. **判定逻辑单一真相源**：`decide_signal()` 只实现一次，`pipeline --demo`（演示）、`closure_eval`（评测）、`api.py`（服务）三处共用。改动只改一处，不会出现"演示说对了、评测说另一套"。
2. **业务层与传输层解耦**：`pipeline.run()` 不依赖任何 HTTP 框架。FastAPI 版和标准库版都只是薄封装，判定逻辑零重复。换框架、加鉴权、加会话都不动核心。

## 四、下一步（明确没做，不装）
- 向量检索补跨文档召回（依据：recall@3 6/9，3 道未命中全在跨文档/版本冲突）
- 查询改写 + 相关性下限（依据：无答案题蹭高分块，12 个失败案例里有实证）
- `answer_points` 接真模型后生成，答案要点须人工回原文核对
