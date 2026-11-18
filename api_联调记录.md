# /ask 端点联调记录（2026-11-18 23:10，真实实测）

## 环境
- Python：WorkBuddy 便携版 3.x（default env）
- FastAPI 0.164.0 / Uvicorn 0.54.0 / pydantic 2.14.3（网络重装成功）
- 服务：`uvicorn api_fastapi:app --host 127.0.0.1 --port 8765`
- 语料块：185（health 实测返回）

## 实测用例与真实返回

| # | 输入 | 期望 | 实测 verdict | needs_human | 判定依据（实测） |
|---|---|---|---|---|---|
| 1 | `GET /health` | 服务活 + 块数 | 200 `{"status":"ok","chunks":185}` | — | 语料加载成功 |
| 2 | 数据分类分级工作的组织责任落在哪个层级 | answered | `answered` | false | top1=23.32 ≥ 12.0 且未触发冲突 |
| 3 | 数据中台部署需要几台服务器、用什么配置 | no_answer | `no_answer` | false | top1=9.54 < 阈值 11.0，拒答 |
| 4 | 数据分类分级在办法与指引中分别如何规定 | conflict | `conflict` | true | 命中 A/B 两文档，分差比 0.062 < 0.1，转人工 |
| 5 | 数据标准管理包括哪些内容 | low_confidence | `low_confidence` | true | top1=11.14 落在灰区 [11,12) |
| 6 | POST `{"question":""}` | 参数校验拦截 | HTTP 422 | — | pydantic min_length=1 生效 |
| 7 | `GET /thresholds` | 阈值可查 | low=11/high=12/margin=0.1/k=5 | — | 与评测阈值一致 |

**四个判定分支全部真实触发**，不是 mock。

## 引用回溯实测（用例 2）
返回 5 个 citation，每条含 `chunk_id / doc / chapter / clause / quote / score`。
首条：`A-016`，第三章 数据分类分级，第十六条，原文片段「银行保险机构应当制定数据分类分级保护制度，建立数据目录和分类分级规范……」，score=23.32。
——命中块能回到文档/章/条 + 原文，满足「引用可回溯」硬要求。

## 标准库 fallback 版（api.py）
- 启动 `python api.py --port 8766`，health 同样返回 185 块。
- /ask 用例 5 返回 `low_confidence`，与 FastAPI 版判定一致（共用 pipeline.run 单一判定源）。
- 价值：面试官环境不装 FastAPI 也能跑；两版业务口径零漂移。

## 已知边界（如实记录）
- 判定层只输出 verdict + 引用 + 理由，**不生成答案文本**（answer_points 仍 TODO）；这是刻意设计，不把「判定对」说成「答得准」。
- 阈值是 50 题标注集网格校准的启发式值（low=11/high=12/margin<0.1），换语料需重标。
- 无会话、无持久化、无鉴权；单端点演示用，非生产服务。
- quote 里有极少数字符因终端编码显示为乱码（如 clause 的「第ä」），是 curl 在 Windows GBK 终端的显示问题，JSON 本体是 UTF-8 正确的；不影响判定。
