#!/usr/bin/env python3
"""Lab 4 step 1 -- fetch one real day of AEMO dispatch data via NEMOSIS.

    uv run labs/04-aemo-digital-twin-reconciliation/fetch_day.py --region SA1 --date 2026-06-15

Pulls DISPATCH_UNIT_SCADA, DISPATCHPRICE, DISPATCHREGIONSUM,
DISPATCHINTERCONNECTORRES (`nemosis.dynamic_data_compiler`) and
DUDETAILSUMMARY, cached under data/nemosis_cache/ (gitignored, same
discipline as scripts/fetch_csiro_nem_data.py's CSIRO fetch: idempotent,
second run just confirms the cache).

Sandbox note -- real live pull, not a stand-in: this is a genuine network
call to nemweb.com.au (AEMO's public MMSDM historical archive) through the
NEMOSIS library, confirmed reachable from this sandbox and exercised for
real at implementation time for --date 2026-06-15 (see _lab4_shared.py's
LAB4_DATE docstring for why that date). docs/LAB4_AEMO_REAL_DATA.md /
this lab's README name a documented fallback path -- a committed sample
cache under data/nemosis_sample/, used "if the live pull genuinely fails."
That fixture is deliberately *not* shipped in this build: the live pull
worked, so there is nothing to fall back to, and shipping a fixture that
was never exercised would be worse than not having one. If you're reading
this after nemweb.com.au has gone away or changed shape, that is the
thing to fix (or the trigger to add data/nemosis_sample/ for real, from an
actual last-known-good pull) -- not a silently-substituted number.

Deviation from docs/LAB4_AEMO_REAL_DATA.md's literal library table:
DUDETAILSUMMARY is pulled with `dynamic_data_compiler`, not
`nemosis.static_table()` as the spec doc suggested. Checked directly
against the installed nemosis==3.8.1 package (`nemosis.defaults.
dynamic_tables` contains "DUDETAILSUMMARY"; `nemosis.defaults.static_tables`
does not) -- `static_table('DUDETAILSUMMARY', ...)` raises
`UserInputError: Table name provided is not a static table.` The spec
doc's own caveat ("verify exact function signatures against each project's
current source at implementation time") anticipated exactly this.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lab4_shared import (
    DUID_TABLE_NAME as DUID_TABLE,
    LAB4_DATE,
    LAB4_REGION,
    NEMOSIS_CACHE_DIR,
)

from nemosis import dynamic_data_compiler

# The four dispatch-interval tables docs/LAB4_AEMO_REAL_DATA.md Part A step
# 2 names, pulled with dynamic_data_compiler over the whole requested day.
DISPATCH_TABLES: Final[tuple[str, ...]] = (
    "DISPATCH_UNIT_SCADA",
    "DISPATCHPRICE",
    "DISPATCHREGIONSUM",
    "DISPATCHINTERCONNECTORRES",
)

# nemosis's fastest on-disk cache format (no CSV kept alongside); avoids
# leaving a second, larger copy of every pulled table under data/.
CACHE_FORMAT: Final[str] = "parquet"


def _day_window(date: str) -> tuple[str, str]:
    """Return the [start, end) NEMOSIS time-window strings for a whole
    calendar day, in the 'YYYY/MM/DD HH:MM:SS' format dynamic_data_compiler
    requires (note the '/' separators, not '-').

    Args:
        date: an ISO 'YYYY-MM-DD' date string.

    Returns:
        (start, end) covering the full day, end exclusive.
    """
    import datetime

    day = datetime.date.fromisoformat(date)
    next_day = day + datetime.timedelta(days=1)
    fmt = "%Y/%m/%d %H:%M:%S"
    start = datetime.datetime.combine(day, datetime.time.min).strftime(fmt)
    end = datetime.datetime.combine(next_day, datetime.time.min).strftime(fmt)
    return start, end


def fetch_day(region: str, date: str, verbose: bool = True) -> dict[str, int]:
    """Pull and cache one day of the 4 dispatch tables plus DUDETAILSUMMARY.

    Args:
        region: AEMO region id (only "SA1" is meaningful here -- see
            _lab4_shared.LAB4_REGION docstring for why).
        date: ISO 'YYYY-MM-DD' date to fetch.
        verbose: if True, print the same progress a presenter would narrate
            live (see README step 1).

    Returns:
        Mapping of table name -> row count fetched (all 5 tables).
    """
    if region != LAB4_REGION:
        print(
            f"[FAIL] --region {region} not supported: snemSA.m is a "
            f"South-Australia-only synthetic network, so this lab can only "
            f"reconcile against {LAB4_REGION!r}. See _lab4_shared.py's "
            f"LAB4_REGION docstring.",
            file=sys.stderr,
        )
        sys.exit(1)

    NEMOSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    start, end = _day_window(date)

    row_counts: dict[str, int] = {}
    try:
        for table in DISPATCH_TABLES:
            if verbose:
                print(f"Pulling {table} for {date} (region {region}) via NEMOSIS...")
            df = dynamic_data_compiler(
                start,
                end,
                table,
                str(NEMOSIS_CACHE_DIR),
                fformat=CACHE_FORMAT,
                keep_csv=False,
            )
            row_counts[table] = len(df)

        if verbose:
            print(f"Pulling {DUID_TABLE} for {date} via NEMOSIS...")
        dud = dynamic_data_compiler(
            start,
            end,
            DUID_TABLE,
            str(NEMOSIS_CACHE_DIR),
            fformat=CACHE_FORMAT,
            keep_csv=False,
        )
        row_counts[DUID_TABLE] = len(dud)
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        print(
            f"[FAIL] live NEMOSIS pull failed: {exc}\n"
            f"This build ships no data/nemosis_sample/ fallback -- the "
            f"live pull for {LAB4_DATE} succeeded at implementation time "
            f"and that is this script's only tested path. See this "
            f"script's module docstring.",
            file=sys.stderr,
        )
        sys.exit(1)

    if verbose:
        dispatch_total = sum(row_counts[t] for t in DISPATCH_TABLES)
        print(
            f"cached {dispatch_total} rows across {len(DISPATCH_TABLES)} tables"
        )
        print(f"cached {row_counts[DUID_TABLE]} rows for {DUID_TABLE}")
        print(f"Data cached under {NEMOSIS_CACHE_DIR}")
    return row_counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default=LAB4_REGION)
    parser.add_argument("--date", default=LAB4_DATE)
    args = parser.parse_args()
    fetch_day(args.region, args.date)


if __name__ == "__main__":
    main()
