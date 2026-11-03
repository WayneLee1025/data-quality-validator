"""Week 1 任务：用 Python 探索任意一份数据文件（CSV / Excel）。

这是 python-journey 仓库的第一个脚本，目标是让你跑通：
  读文件 -> 看结构 -> 查空值 -> 预览。
对应作战档案「战线① 第 1 个产出」。

运行：
  PY python-journey/week1_explore.py                 # 默认读 sample.csv
  PY python-journey/week1_explore.py 路径/数据.xlsx  # 读你自己的文件
（PY = C:/Users/12821/.workbuddy/binaries/python/envs/default/Scripts/python.exe）
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

SAMPLE = Path(__file__).with_name("sample.csv")


def explore(path: str) -> None:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(p)
    else:
        df = pd.read_csv(p)

    print(f"文件: {p}")
    print(f"行数: {df.shape[0]}    列数: {df.shape[1]}")
    print("\n列名与空值数:")
    nulls = df.isnull().sum()
    for col in df.columns:
        print(f"  - {col}: 空值 {int(nulls[col])}")
    print("\n前 5 行预览:")
    print(df.head().to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser(description="Week1: 探索任意 Excel/CSV 数据")
    ap.add_argument(
        "file",
        nargs="?",
        default=str(SAMPLE),
        help="数据文件路径（默认 sample.csv）",
    )
    args = ap.parse_args()
    if not Path(args.file).exists():
        print(f"文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)
    explore(args.file)


if __name__ == "__main__":
    main()
