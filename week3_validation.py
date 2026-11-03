"""Week 3 任务：把一条监管报送校验规则从 PL/SQL 改写成 pandas 版。

背景：光大监管报送有 78 条校验规则，原为 PL/SQL 存储过程逐行判断。
这里用向量化方式复刻同类逻辑，输出违规清单——这就是能写进简历的
"第一个小工具"（数据质量校验器 / 报送前置质检）。

涵盖规则类型（监管报送常见）：
  1) 非空校验      2) 唯一性          3) 格式（证件号长度 / 日期）
  4) 取值域        5) 引用完整性(外键) 6) 业务规则（数值非负）

运行：PY week3_validation.py
（PY = C:/Users/12821/.workbuddy/binaries/python/envs/default/Scripts/python.exe）
"""
from pathlib import Path
import argparse

import pandas as pd

DEFAULT_DATA = Path(__file__).parent / "data"

# 取值域 / 格式常量（对应 PL/SQL 里的校验码表）
STATUS_DOMAIN = {"0", "1"}
TXN_TYPE_DOMAIN = {"01", "02", "03"}
ID_NO_LEN = 18
DATE_RE = r"^\d{4}-\d{2}-\d{2}$"


def load(name: str, data_dir: Path = DEFAULT_DATA) -> pd.DataFrame:
    # 关键：代码型字段（id_no/status/txn_type 等）必须按字符串读，
    # 否则 "01" 会被 pandas 误转成整数 1，后续取值域校验全误报。
    df = pd.read_csv(data_dir / name, dtype=str)
    # 金额列再显式转数值，供业务规则比较
    for c in ("balance", "txn_amt"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def report(rule_name: str, bad: pd.DataFrame) -> int:
    """统一汇报一条规则的命中情况，返回违规条数。"""
    n = len(bad)
    print(f"[规则] {rule_name}: 命中 {n} 条")
    if n:
        print(bad.to_string(index=False))
    print()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="监管报送前置质检（pandas 版）")
    ap.add_argument(
        "--data",
        default=str(DEFAULT_DATA),
        help="数据目录（默认 data/，可指向任意报送抽取样本）",
    )
    args = ap.parse_args()
    data_dir = Path(args.data)

    cust = load("cust.csv", data_dir)
    acct = load("acct.csv", data_dir)
    txn = load("txn.csv", data_dir)
    total = 0

    # 1) 非空校验
    non_nulls = [
        (cust, ["cust_id", "cust_name", "id_no", "open_date"], "客户表"),
        (acct, ["acct_no", "cust_id", "balance", "status"], "账户表"),
        (txn, ["txn_id", "acct_no", "txn_amt", "txn_date", "txn_type"], "交易表"),
    ]
    for df, cols, label in non_nulls:
        for c in cols:
            bad = df[df[c].isnull()]
            total += report(f"{label}.{c} 非空", bad)

    # 2) 唯一性
    for df, col, label in [
        (cust, "cust_id", "cust"),
        (acct, "acct_no", "acct"),
        (txn, "txn_id", "txn"),
    ]:
        dup = df[df[col].duplicated(keep=False)]
        total += report(f"{label}.{col} 唯一性", dup)

    # 3) 格式：证件号长度、日期格式
    bad_id = cust[~cust["id_no"].astype(str).str.len().eq(ID_NO_LEN)]
    total += report("cust.id_no 长度=18", bad_id)
    bad_date = txn[~txn["txn_date"].astype(str).str.match(DATE_RE)]
    total += report("txn.txn_date 格式 YYYY-MM-DD", bad_date)

    # 4) 取值域
    bad_status = acct[~acct["status"].astype(str).isin(STATUS_DOMAIN)]
    total += report("acct.status 取值域", bad_status)
    bad_type = txn[~txn["txn_type"].astype(str).isin(TXN_TYPE_DOMAIN)]
    total += report("txn.txn_type 取值域", bad_type)

    # 5) 引用完整性（外键）
    bad_fk_acct = acct[~acct["cust_id"].isin(cust["cust_id"])]
    total += report("acct.cust_id -> cust 引用完整性", bad_fk_acct)
    bad_fk_txn = txn[~txn["acct_no"].isin(acct["acct_no"])]
    total += report("txn.acct_no -> acct 引用完整性", bad_fk_txn)

    # 6) 业务规则（数值非负）
    bad_bal = acct[acct["balance"] < 0]
    total += report("acct.balance >= 0", bad_bal)
    bad_amt = txn[txn["txn_amt"] < 0]
    total += report("txn.txn_amt >= 0", bad_amt)

    print(f"==== 报送前置质检完成：共 {total} 条违规 ====")


if __name__ == "__main__":
    main()
