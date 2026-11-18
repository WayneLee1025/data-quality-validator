#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RAG 闭环的 HTTP 服务层：单端点 POST /ask。

设计取舍（面试可讲）：
  - 用标准库 http.server，不引 FastAPI/Flask。理由：本项目的价值在「判定逻辑 +
    可复现评测」，不在框架。零依赖意味着任何面试官 clone 下来 python api.py 就能跑，
    不会卡在 pip install。要上生产换成 FastAPI 只需替换本文件的路由层，
    pipeline.run() 不动——这就是把业务逻辑和传输层解耦的收益。
  - /ask 只做三件事：校验入参 → 调 pipeline.run()（单一判定源）→ 结构化返回。
    判定逻辑一行都不在这里重写，避免 API 和评测两套口径。

启动：
  python api.py            # 默认 127.0.0.1:8765
  python api.py --port 9000

调用：
  curl -s -X POST http://127.0.0.1:8765/ask ^
    -H "Content-Type: application/json" ^
    -d "{\"question\":\"发生数据安全事件后多长时间报告监管\"}"

其他端点：GET /health（健康检查）、GET /thresholds（当前阈值，便于复现）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "rag"))
import pipeline  # noqa: E402

DEFAULT_PORT = 8765
MAX_Q_LEN = 500


class AskHandler(BaseHTTPRequestHandler):
    server_version = "RAGClosure/1.0"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok", "chunks": len(pipeline.load_chunks())})
        elif self.path == "/thresholds":
            self._send(200, {"low": 11.0, "high": 12.0, "margin": 0.10, "top_k": 5})
        else:
            self._send(404, {"error": "not found", "endpoints": ["/ask", "/health", "/thresholds"]})

    def do_POST(self) -> None:
        if self.path != "/ask":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 100_000:
                self._send(400, {"error": "empty or oversized body"})
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            q = data.get("question", "")
            if not isinstance(q, str) or not q.strip():
                self._send(400, {"error": "question must be a non-empty string"})
                return
            q = q.strip()
            if len(q) > MAX_Q_LEN:
                self._send(400, {"error": f"question too long (>{MAX_Q_LEN})"})
                return
            k = int(data.get("k", 5))
            if not 1 <= k <= 20:
                self._send(400, {"error": "k must be 1..20"})
                return

            result = pipeline.run(q, k=k, low=11.0, high=12.0, margin_th=0.10)
            self._send(200, {"ok": True, **result})
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, {"error": f"bad request: {e}"})
        except Exception as e:  # noqa: BLE001 - 服务层兜底，返回结构化错误而非裸栈
            self._send(500, {"error": f"internal error: {type(e).__name__}: {e}"})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[ask] " + (fmt % args) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="RAG 闭环 HTTP 服务 · POST /ask")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    n = len(pipeline.load_chunks())
    print(f"chunks loaded: {n} | serving http://{args.host}:{args.port}/ask", flush=True)
    ThreadingHTTPServer((args.host, args.port), AskHandler).serve_forever()


if __name__ == "__main__":
    main()
