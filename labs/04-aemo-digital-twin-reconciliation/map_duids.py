#!/usr/bin/env python3
"""Lab 4 step 2 -- map real SA1 DUIDs onto snemSA.m's synthetic generators.

    uv run labs/04-aemo-digital-twin-reconciliation/map_duids.py

Joins DUDETAILSUMMARY (PARTICIPANTID -> STATIONID -> DUID, per the
mms-guide versioning pattern cited in docs/LAB4_AEMO_REAL_DATA.md: dedup by
START_DATE desc / LASTCHANGED desc, take the first row) to the nearest
synthetic generator in snemSA.m and writes the auditable, committed
`duid_mapping.csv` (real_duid -> synthetic_gen_bus, with a `rationale`
column) that reconcile.py and explain_constraint.py both read.

Sandbox stand-ins (both real, network-verified limitations of this
sandbox, not shortcuts -- see this lab's README "Sandbox notes" for the
full writeup):

1. Fuel-type matching is unavailable on *both* sides of the join, so this
   script matches on nameplate-capacity proximity only, never fuel type,
   despite docs/LAB4_AEMO_REAL_DATA.md describing fuel type as the primary
   key "where the CSIRO metadata records it": (a) snemSA.m's own generator
   metadata (mpc.gen / mpc.gen_data) carries no fuel-type field at all --
   only a bus-indexed name like "gen_1683_1"; (b) AEMO's real fuel-type
   source, the NEM Registration and Exemption List
   (https://www.aemo.com.au/-/media/Files/Electricity/NEM/Participant_
   Information/NEM-Registration-and-Exemption-List.xls, what
   `nemosis.static_table('Generators and Scheduled Loads', ...)` fetches),
   returns a genuine HTTP 403 from this sandbox (Cloudflare bot
   protection on www.aemo.com.au -- confirmed by a direct `curl -I`, while
   nemweb.com.au, the actual MMSDM archive this lab depends on, is fully
   reachable). This is the documented "else nameplate-capacity proximity"
   fallback in the spec, exercised because the primary path is blocked,
   not skipped as a shortcut.
2. The real DUID's "nameplate capacity" figure is also not directly
   available: DUDETAILSUMMARY carries no capacity column, and the table
   that does (DUDETAIL.REGISTEREDCAPACITY) is a fully-versioned table that
   NEMOSIS's dynamic_data_compiler only knows how to fetch by scanning
   every month from 2009 to the present (confirmed by a real trial run:
   over 200 monthly archive downloads, several minutes, for one table) --
   wildly disproportionate for a lab step meant to run in seconds. This
   script instead uses each real DUID's own day-max SCADA output (from
   DISPATCH_UNIT_SCADA, already fetched by fetch_day.py) as a real,
   physically-grounded capacity proxy: never a fabricated number, but an
   approximation of nameplate capacity (a generator running below its
   rated capacity all day will look smaller than it really is). Named
   here and in the CSV's `rationale` column, not hidden.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from _lab4_shared import (
    DUID_TABLE_NAME,
    INTERCONNECTOR_EQUIVALENT_BUS,
    LAB4_DATE,
    LAB4_REGION,
    NEMOSIS_CACHE_DIR,
    load_synthetic_net,
)

from nemosis import dynamic_data_compiler

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
OUTPUT_CSV: Final[Path] = LAB_DIR / "duid_mapping.csv"

# Only real DUIDs whose DISPATCHTYPE is GENERATOR are matched against
# snemSA.m's generators. Real LOAD/BIDIRECTIONAL DUIDs (scheduled loads,
# batteries operating as load) have no synthetic-generator counterpart to
# match against in this lab's scope.
MATCHABLE_DISPATCH_TYPE: Final[str] = "GENERATOR"


class DuidMappingRow(TypedDict):
    """One row of duid_mapping.csv -- also the shape `reconcile.py` reads."""

    real_duid: str
    station_id: str
    participant_id: str
    region: str
    capacity_proxy_mw: float
    synthetic_gen_bus: int
    synthetic_gen_max_p_mw: float
    capacity_diff_mw: float
    rationale: str


def _load_real_duids(date: str, region: str) -> pd.DataFrame:
    """Load DUDETAILSUMMARY for `date` and return one deduplicated row per
    real generator DUID in `region`.

    Dedup rule per the mms-guide versioning pattern cited in
    docs/LAB4_AEMO_REAL_DATA.md: sort by (START_DATE desc, LASTCHANGED
    desc), keep the first row per DUID -- the most recently effective,
    most recently changed version of that DUID's registration record.

    Args:
        date: ISO date already fetched by fetch_day.py (re-fetching here
            is a fast NEMOSIS cache hit, not a fresh download).
        region: AEMO region id to filter to.

    Returns:
        One row per real generator DUID, columns from DUDETAILSUMMARY.
    """
    import datetime

    day = datetime.date.fromisoformat(date)
    next_day = day + datetime.timedelta(days=1)
    fmt = "%Y/%m/%d %H:%M:%S"
    start = datetime.datetime.combine(day, datetime.time.min).strftime(fmt)
    end = datetime.datetime.combine(next_day, datetime.time.min).strftime(fmt)

    dud = dynamic_data_compiler(
        start, end, DUID_TABLE_NAME, str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    dud = dud[
        (dud["REGIONID"] == region) & (dud["DISPATCHTYPE"] == MATCHABLE_DISPATCH_TYPE)
    ]
    dud = dud.sort_values(["START_DATE", "LASTCHANGED"], ascending=False)
    return dud.drop_duplicates(subset="DUID", keep="first")


def _real_capacity_proxies(date: str, duids: list[str]) -> pd.Series:
    """Day-max SCADA MW per real DUID -- the capacity-proxy source named
    in the module docstring.

    Args:
        date: ISO date already fetched by fetch_day.py.
        duids: real DUIDs to compute a proxy for.

    Returns:
        Series indexed by DUID, day-max SCADAVALUE (floored at 0.0 -- a
        few DUIDs report small negative SCADA, i.e. auxiliary
        self-consumption, which is not a meaningful "capacity").
    """
    import datetime

    day = datetime.date.fromisoformat(date)
    next_day = day + datetime.timedelta(days=1)
    fmt = "%Y/%m/%d %H:%M:%S"
    start = datetime.datetime.combine(day, datetime.time.min).strftime(fmt)
    end = datetime.datetime.combine(next_day, datetime.time.min).strftime(fmt)

    scada = dynamic_data_compiler(
        start, end, "DISPATCH_UNIT_SCADA", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    scada = scada[scada["DUID"].isin(duids)]
    day_max = scada.groupby("DUID")["SCADAVALUE"].max().clip(lower=0.0)
    return day_max


def _synthetic_generator_capacities() -> pd.DataFrame:
    """Every non-slack synthetic generator's bus id and max_p_mw.

    The slack generator (INTERCONNECTOR_EQUIVALENT_BUS) is excluded: it
    stands in for the real interconnector ties (see _lab4_shared.py), not
    a matchable real generator.

    Returns:
        DataFrame with columns bus, max_p_mw, indexed by net.gen row.
    """
    net, _warnings = load_synthetic_net()
    gens = net.gen[~net.gen["slack"]][["bus", "max_p_mw"]].copy()
    assert INTERCONNECTOR_EQUIVALENT_BUS not in set(gens["bus"]), (
        "slack-exclusion filter did not remove the interconnector-"
        "equivalent bus -- see _lab4_shared.slack_bus()"
    )
    return gens.reset_index(drop=True)


def build_mapping(date: str = LAB4_DATE, region: str = LAB4_REGION) -> list[DuidMappingRow]:
    """Build the full real-DUID -> synthetic-generator mapping.

    For each real generator DUID (with a computable capacity proxy),
    finds the synthetic generator whose max_p_mw is numerically closest
    (nearest-neighbour on a single scalar -- capacity proximity, per the
    module docstring's fuel-type-unavailable explanation). Multiple real
    DUIDs may map to the same synthetic generator (57 synthetic
    generators vs. ~80+ real SA1 DUIDs, so this is expected, not an
    error); reconcile.py sums all real DUIDs mapped to a given synthetic
    generator when imposing SCADA MW.

    Args:
        date: ISO date to pull DUID metadata and SCADA for.
        region: AEMO region id.

    Returns:
        One DuidMappingRow per real DUID with a usable capacity proxy,
        sorted by capacity_proxy_mw descending (largest real generators
        first, for a readable printed table).
    """
    real = _load_real_duids(date, region)
    proxies = _real_capacity_proxies(date, real["DUID"].tolist())
    synthetic = _synthetic_generator_capacities()

    rows: list[DuidMappingRow] = []
    for _, real_row in real.iterrows():
        duid = real_row["DUID"]
        if duid not in proxies.index:
            continue  # no SCADA that day (e.g. mothballed/not dispatched)
        capacity_proxy = float(proxies[duid])
        diffs = (synthetic["max_p_mw"] - capacity_proxy).abs()
        nearest_idx = diffs.idxmin()
        nearest = synthetic.loc[nearest_idx]
        rows.append(
            {
                "real_duid": duid,
                "station_id": real_row["STATIONID"],
                "participant_id": real_row["PARTICIPANTID"],
                "region": region,
                "capacity_proxy_mw": round(capacity_proxy, 3),
                "synthetic_gen_bus": int(nearest["bus"]),
                "synthetic_gen_max_p_mw": round(float(nearest["max_p_mw"]), 3),
                "capacity_diff_mw": round(float(diffs[nearest_idx]), 3),
                "rationale": (
                    f"nameplate-capacity proximity: real day-max SCADA "
                    f"{capacity_proxy:.1f} MW vs synthetic gen max_p_mw "
                    f"{nearest['max_p_mw']:.1f} MW at bus {int(nearest['bus'])} "
                    f"(diff {diffs[nearest_idx]:.1f} MW); fuel-type matching "
                    f"unavailable on both sides, see map_duids.py docstring"
                ),
            }
        )
    rows.sort(key=lambda r: r["capacity_proxy_mw"], reverse=True)
    return rows


def print_table(rows: list[DuidMappingRow]) -> None:
    """Print the mapping as a readable table (README step 2's "printed
    table of real DUID -> matched synthetic generator ID -> match
    rationale")."""
    print(
        f"{'real_duid':>12} {'capacity_mw':>11} {'synth_bus':>9} "
        f"{'synth_max_mw':>12} {'diff_mw':>8}"
    )
    for row in rows:
        print(
            f"{row['real_duid']:>12} {row['capacity_proxy_mw']:>11.1f} "
            f"{row['synthetic_gen_bus']:>9} {row['synthetic_gen_max_p_mw']:>12.1f} "
            f"{row['capacity_diff_mw']:>8.1f}"
        )
    print(f"{len(rows)} real DUIDs mapped to synthetic generators")


def write_csv(rows: list[DuidMappingRow], path: Path = OUTPUT_CSV) -> None:
    """Write the mapping to a committed, human-auditable CSV."""
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {len(rows)} rows to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=LAB4_DATE)
    parser.add_argument("--region", default=LAB4_REGION)
    args = parser.parse_args()

    rows = build_mapping(args.date, args.region)
    print_table(rows)
    write_csv(rows)


if __name__ == "__main__":
    main()
