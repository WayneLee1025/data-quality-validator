# python-journey

李邦都的 Python 学习仓库（B 方案）。每个知识点以「可运行脚本」沉淀，不做空笔记。

## 环境
托管 Python 3.13.12 隔离环境（已装 pandas/numpy/requests/openpyxl/python-dotenv）：
```
C:\Users\12821\.workbuddy\binaries\python\envs\default\Scripts\python.exe
```

## 运行
```
PY python-journey/week1_explore.py              # 默认读 sample.csv
PY python-journey/week1_explore.py 数据.xlsx    # 读自己的文件
```
（PY = 上面的 python.exe 路径）

## 周计划索引
- `week1_explore.py` —— 第 1 周：读文件 / 看结构 / 查空值 / 预览（已跑通）
- `week3_validation.py` —— 第 3 周：监管报送校验规则 pandas 版（非空/唯一/格式/取值域/外键/业务规则），含 `data/` 示例数据（已跑通，命中 15 条植入违规）
- 后续：元数据比对器、FastAPI 工具服务、RAG 报送口径问答 ……（按《Python高效学习路径-B方案.md》推进）
