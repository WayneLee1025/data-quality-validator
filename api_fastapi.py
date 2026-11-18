#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RAG 闭环 HTTP 服务（FastAPI 版）：POST /ask。

与 api.py（标准库版）共用同一个 pipeline.run()，判定逻辑零重复。
两版并存理由：FastAPI 版展示工程规范（自动文档/参数校验/类型），
标准库版保证零依赖可跑。面试官 clone 后按环境二选一。

启动：
  pip install fastapi uvicorn
  uvicorn api_fastapi:app --host 127.0.0.1 --port 8765
  # 打开 http://127.0.0.1:8765/docs 看自动生成的接口文档

调用：
  curl -s -X POST http://127.0.0.1:8765/ask -H "Content-Type: application/json" \
    -d '{"question":"发生数据安全事件后多长时间报告监管"}'
"""
from __future__ import annotations

import pathlib
import sys

from fastapi import FastAPI
from pydantic import BaseModel, Field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "rag"))
import pipeline  # noqa: E402

app = FastAPI(title="RAG 判定闭环 API", version="1.0",
              description="检索→引用回溯→信号判定→人工兜底。判定不调模型，离线可复现。")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="自然语言问题")
    k: int = Field(5, ge=1, le=20, description="top-k 检索条数")


@app.get("/health")
def health():
    return {"status": "ok", "chunks": len(pipeline.load_chunks())}


@app.get("/thresholds")
def thresholds():
    return {"low": 11.0, "high": 12.0, "margin": 0.10, "top_k": 5,
            "note": "50 题标注集网格校准，启发式值，换语料需重标"}


@app.post("/ask")
def ask(req: AskRequest):
    result = pipeline.run(req.question, k=req.k, low=11.0, high=12.0, margin_th=0.10)
    return {"ok": True, **result}
