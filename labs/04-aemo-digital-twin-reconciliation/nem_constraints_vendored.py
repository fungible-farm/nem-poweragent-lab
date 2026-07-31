"""Vendored from https://github.com/susantoj/NEM_constraints
(NEMDE_constraints.py), commit 62f6a1efa87b8b68804ed32dbe16ae2589e69301
(accessed 2026-07-31), MIT License Copyright (c) 2023 Julius Susanto -- see
LICENSE-NEM_constraints in this directory for the full text.

Why vendored instead of a normal dependency: docs/LAB4_AEMO_REAL_DATA.md is
explicit that this is "a public library for [decoding constraint
equations]... use this rather than writing a constraint-equation parser."
It is not, however, published to PyPI, and `uv pip install git+https://
github.com/susantoj/NEM_constraints` fails at resolve time (checked
directly at implementation time): the repo has no `pyproject.toml`/
`setup.py`, so uv/pip has nothing to build. AGENTS.md's sandbox-stand-in
convention for exactly this situation ("vendor just the specific functions
you need... with a comment citing the exact source file/commit... do not
write your own constraint-equation parser") is what this file is.

Two deliberate changes from the upstream source, both documented inline
below where they occur -- everything else (the actual constraint-decoding
logic: which MMS tables to join, how LHS/RHS terms are assembled) is
unchanged from upstream, since inventing a different join would be exactly
the "hand-rolled parser" the spec says not to write:

1. `get_mms_table`'s URL construction for the modern ("PUBLIC_ARCHIVE",
   post-July-2024) MMSDM archive layout double-percent-encodes the '#'
   separator (literal '%2523' in the upstream source, which decodes to
   '%23' -- i.e. a still-encoded '#' -- rather than to '#' itself). This
   is a confirmed bug, not a style choice: fetching upstream's own
   unmodified URL for any date after July 2024 returns a real HTTP 404
   from nemweb.com.au (checked directly at implementation time). This
   file uses '%23' (single-encoded) instead, which resolves correctly
   (checked directly against the June 2026 and April 2026 archives).
2. `get_mms_table` gained an in-process memoization cache
   (`functools.lru_cache`), because the unmodified function re-downloads
   the same multi-megabyte monthly zip from nemweb.com.au on every call --
   `get_constraint_details` alone calls it 5 times, and explain_
   constraint.py calls the LHS/RHS lookup for several candidate
   constraints per run before finding an SA1-relevant one. This is a
   caching addition only; it does not change what get_mms_table returns
   for a given (month, year, table), only how many times it's fetched.
"""
from __future__ import annotations

import functools
from datetime import date
from typing import Optional

import pandas as pd
from dateutil.relativedelta import relativedelta


@functools.lru_cache(maxsize=None)
def get_mms_table(month: int, year: int, table: str) -> pd.DataFrame:
    """Get a table from the MMS historical data archive for a specific
    month/year and return a DataFrame.

    Vendored from upstream `get_mms_table` with the two changes described
    in this module's docstring (URL fix, added memoization). The dropped
    `print(url_prefix + table + url_suffix)` debug line is the only other
    omission -- explain_constraint.py prints its own progress instead.

    Args:
        month: 1-12.
        year: 4-digit year.
        table: MMSDM table name, e.g. "GENCONDATA".

    Returns:
        The full table for that month, including AEMO's trailing
        end-of-file marker row (callers drop it, matching upstream).
    """
    str_month = f"{month:02d}"
    if ((year >= 2024) and (month > 7)) or (year >= 2025):
        url_prefix = (
            "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/"
            f"{year}/MMSDM_{year}_{str_month}/MMSDM_Historical_Data_SQLLoader/"
            "DATA/PUBLIC_ARCHIVE%23"  # was '%2523' upstream -- see docstring
        )
        url_suffix = f"%23FILE01%23{year}{str_month}010000.zip"  # was '%2523...%2523'
    else:
        url_prefix = (
            "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/"
            f"{year}/MMSDM_{year}_{str_month}/MMSDM_Historical_Data_SQLLoader/"
            "DATA/PUBLIC_DVD_"
        )
        url_suffix = f"_{year}{str_month}010000.zip"

    return pd.read_csv(
        url_prefix + table + url_suffix, compression="zip", header=1, low_memory=False
    )


def get_constraint_list(
    month: int, year: int, prefix: Optional[str] = None
) -> pd.DataFrame:
    """Get list of constraints from a specific month/year, optional prefix
    filter (e.g. 'Q_', 'S_'). Vendored unchanged (aside from typing)."""
    df = get_mms_table(month, year, "GENCONDATA")
    df = df.drop(index=df.index[-1], axis=0)
    if prefix:
        df = df[df["GENCONID"].str.startswith(prefix)]
    return df


def find_constraint(
    constraint: str,
    start_date: date = date(2009, 7, 1),
    end_date: Optional[date] = None,
) -> tuple[pd.DataFrame, bool]:
    """Find the last update of a specific constraint by searching backward
    through monthly GENCONDATA archives. Vendored unchanged (aside from
    typing and dropped print statements -- callers print their own
    progress)."""
    df = pd.DataFrame()
    if not end_date:
        end_date = date.today() - relativedelta(months=2)
    cur_date = end_date
    while df.empty and cur_date > start_date:
        df = get_mms_table(cur_date.month, cur_date.year, "GENCONDATA")
        df = df.drop(index=df.index[-1], axis=0)
        df = df[df["GENCONID"].str.startswith(constraint)]
        cur_date = cur_date - relativedelta(months=1)
    found = not df.empty
    if found:
        df = df.drop(df.columns[[0, 2, 3]], axis=1)
    return df, found


def get_LHS_terms(constraint: str, month: int, year: int) -> pd.DataFrame:
    """Get LHS terms (connection points, interconnectors, regions) for a
    constraint equation. Vendored unchanged."""
    dict_LHS: dict = {"type": [], "ID": [], "DUID": [], "factor": [], "bidtype": []}

    df = get_mms_table(month, year, "SPDCONNECTIONPOINTCONSTRAINT")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["GENCONID"] == constraint]
    if not df.empty:
        df_lookup = get_mms_table(month, year, "DUDETAIL")
        df_lookup = df_lookup.drop(index=df_lookup.index[-1], axis=0)
        for i in range(len(df)):
            df_DUID = df_lookup[
                df_lookup["CONNECTIONPOINTID"] == df["CONNECTIONPOINTID"].iloc[i]
            ]["DUID"]
            DUID = "DUID not found" if df_DUID.empty else df_DUID.iloc[0]
            dict_LHS["type"].append("CONNECTIONPOINT")
            dict_LHS["ID"].append(df["CONNECTIONPOINTID"].iloc[i])
            dict_LHS["DUID"].append(DUID)
            dict_LHS["factor"].append(df["FACTOR"].iloc[i])
            dict_LHS["bidtype"].append(df["BIDTYPE"].iloc[i])

    df = get_mms_table(month, year, "SPDINTERCONNECTORCONSTRAINT")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["GENCONID"] == constraint]
    if not df.empty:
        for i in range(len(df)):
            dict_LHS["type"].append("INTERCONNECTOR")
            dict_LHS["ID"].append(df["INTERCONNECTORID"].iloc[i])
            dict_LHS["DUID"].append(df["INTERCONNECTORID"].iloc[i])
            dict_LHS["factor"].append(df["FACTOR"].iloc[i])
            dict_LHS["bidtype"].append("N/A")

    df = get_mms_table(month, year, "SPDREGIONCONSTRAINT")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["GENCONID"] == constraint]
    if not df.empty:
        for i in range(len(df)):
            dict_LHS["type"].append("REGION")
            dict_LHS["ID"].append(df["REGIONID"].iloc[i])
            dict_LHS["DUID"].append(df["REGIONID"].iloc[i])
            dict_LHS["factor"].append(df["FACTOR"].iloc[i])
            dict_LHS["bidtype"].append("N/A")

    return pd.DataFrame(dict_LHS)


def get_RHS_terms(constraint: str, month: int, year: int) -> pd.DataFrame:
    """Get RHS terms for a constraint equation. Vendored unchanged."""
    dict_RHS: dict = {
        "term_ID": [], "ID": [], "type": [], "description": [], "factor": [],
        "operation": [],
    }
    df = get_mms_table(month, year, "GENERICCONSTRAINTRHS")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["GENCONID"] == constraint]

    if not df.empty:
        df_ems = get_mms_table(month, year, "EMSMASTER")
        df_ems = df_ems.drop(index=df_ems.index[-1], axis=0)
        for i in range(len(df)):
            spd_type = df["SPD_TYPE"].iloc[i]
            if spd_type in ["A", "S", "I", "T", "R"]:
                df1 = df_ems[df_ems["SPD_ID"] == df["SPD_ID"].iloc[i]]["DESCRIPTION"]
                desc = "-" if df1.empty else df1.iloc[0]
            elif spd_type == "X":
                desc = "Generic RHS function"
            else:
                desc = "-"
            str_op = str(df["OPERATION"].iloc[i])
            if str_op == "nan":
                str_op = "-"
            dict_RHS["term_ID"].append(df["TERMID"].iloc[i])
            dict_RHS["ID"].append(df["SPD_ID"].iloc[i])
            dict_RHS["description"].append(desc)
            dict_RHS["factor"].append(df["FACTOR"].iloc[i])
            dict_RHS["operation"].append(str_op)
            dict_RHS["type"].append(spd_type)

    return pd.DataFrame(dict_RHS).sort_values(by="term_ID")


def get_constraint_details(
    constraint: str, month: int, year: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Get description + LHS + RHS terms for a constraint equation.
    Vendored unchanged."""
    df = get_mms_table(month, year, "GENCONDATA")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["GENCONID"] == constraint]
    if not df.empty:
        df = df.drop(df.columns[[0, 2, 3]], axis=1)
    return df, get_LHS_terms(constraint, month, year), get_RHS_terms(constraint, month, year)


def find_generic_RHS_func(
    equation_id: str,
    start_date: date = date(2009, 7, 1),
    end_date: Optional[date] = None,
) -> tuple[pd.DataFrame, bool]:
    """Find the last update of a specific generic RHS function by
    searching backward through monthly GENERICEQUATIONDESC archives.
    Vendored unchanged (aside from typing/dropped prints). Not exercised
    by explain_constraint.py's chosen constraint (SPD_TYPE != 'X' -- see
    that script's printed RHS terms), but included for API completeness
    against the six functions docs/LAB4_AEMO_REAL_DATA.md names."""
    df = pd.DataFrame()
    if not end_date:
        end_date = date.today() - relativedelta(months=2)
    cur_date = end_date
    while df.empty and cur_date > start_date:
        df = get_mms_table(cur_date.month, cur_date.year, "GENERICEQUATIONDESC")
        df = df.drop(index=df.index[-1], axis=0)
        df = df[df["EQUATIONID"].str.startswith(equation_id)]
        cur_date = cur_date - relativedelta(months=1)
    found = not df.empty
    if found:
        df = df.drop(df.columns[[0, 2, 3]], axis=1)
    return df, found


def get_generic_RHS_func(equation_id: str, month: int, year: int) -> pd.DataFrame:
    """Get terms for a generic RHS function (SPD_TYPE == 'X' RHS terms
    reference one of these instead of a plain SCADA/constant value).
    Vendored unchanged."""
    dict_RHS_func: dict = {
        "term_ID": [], "ID": [], "type": [], "description": [], "factor": [],
        "operation": [],
    }
    df = get_mms_table(month, year, "GENERICEQUATIONRHS")
    df = df.drop(index=df.index[-1], axis=0)
    df = df[df["EQUATIONID"] == equation_id]

    if not df.empty:
        df_ems = get_mms_table(month, year, "EMSMASTER")
        df_ems = df_ems.drop(index=df_ems.index[-1], axis=0)
        for i in range(len(df)):
            spd_type = df["SPD_TYPE"].iloc[i]
            if spd_type in ["A", "S", "I", "T", "R"]:
                df1 = df_ems[df_ems["SPD_ID"] == df["SPD_ID"].iloc[i]]["DESCRIPTION"]
                desc = "-" if df1.empty else df1.iloc[0]
            else:
                desc = "-"
            str_op = str(df["OPERATION"].iloc[i])
            if str_op == "nan":
                str_op = "-"
            dict_RHS_func["term_ID"].append(df["TERMID"].iloc[i])
            dict_RHS_func["ID"].append(df["SPD_ID"].iloc[i])
            dict_RHS_func["description"].append(desc)
            dict_RHS_func["factor"].append(df["FACTOR"].iloc[i])
            dict_RHS_func["operation"].append(str_op)
            dict_RHS_func["type"].append(spd_type)

    return pd.DataFrame(dict_RHS_func).sort_values(by="term_ID")
