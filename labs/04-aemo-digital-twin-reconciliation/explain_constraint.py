#!/usr/bin/env python3
"""Lab 4 step 4 -- decode one real binding constraint into plain English.

    uv run labs/04-aemo-digital-twin-reconciliation/explain_constraint.py

Pulls DISPATCHCONSTRAINT for LAB4_DATE, filters to constraints with a
nonzero marginal value (i.e. actually binding -- docs/LAB4_AEMO_REAL_
DATA.md Part B step 1), searches for one that is SA1-relevant (its LHS
terms touch the SA1 region, an SA1 interconnector, or an SA1 DUID -- not
guessed from the constraint ID string, but decoded via the same library
this step is demonstrating), decodes it with the vendored NEM_constraints
functions (see nem_constraints_vendored.py for why vendored, not a normal
dependency), and prints a plain-English translation.

Note on which interval this uses: this deliberately scans the *whole* of
LAB4_DATE for a binding, SA1-relevant constraint rather than reusing
reconcile.py's RECONCILE_INTERVAL. reconcile.py's interval was chosen
specifically because nothing was binding there (a clean read on the
topology-vs-real-data gap, see _lab4_shared.py); this step's job is the
opposite -- find where something *was* binding. Confirmed at
implementation time: LAB4_DATE's Heywood-interconnector-limit test
constraint (VS_HEY_600_TEST) binds at several intervals in the mid-
afternoon, none of them RECONCILE_INTERVAL (12:00) -- the printed output
always states exactly which interval it used, so this is never hidden.
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from typing import Final, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
from _lab4_shared import LAB4_DATE, LAB4_REGION, NEMOSIS_CACHE_DIR, SA_INTERCONNECTOR_IDS
from nem_constraints_vendored import find_constraint, get_constraint_details

from nemosis import dynamic_data_compiler

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
MAPPING_CSV: Final[Path] = LAB_DIR / "duid_mapping.csv"

# How many of the day's binding constraints (sorted by total |marginal
# value| that day, most-binding first) to check for SA1-relevance before
# giving up and falling back to the single most-binding one regardless of
# region. Bounded so a day with no SA1-relevant constraint at all still
# finishes in a reasonable number of (cached-after-first-hit) MMSDM
# archive lookups rather than scanning all ~80+ candidates.
MAX_CANDIDATES_CHECKED: Final[int] = 20

# find_constraint searches backward month-by-month from LAB4_DATE looking
# for the constraint's GENCONDATA definition (constraints are revised
# infrequently, so the definition effective on LAB4_DATE may live in an
# earlier month's archive extract -- see nem_constraints_vendored.py).
# 2024-01-01 is a practical floor: none of this lab's candidate
# constraints (checked at implementation time) predate it, and it keeps a
# worst-case "not found anywhere" search from scanning back to 2009.
CONSTRAINT_SEARCH_FLOOR: Final[datetime.date] = datetime.date(2024, 1, 1)


class DecodedConstraint(TypedDict):
    """Everything explain_constraint needs to print and translate one
    binding constraint."""

    constraint_id: str
    interval: str
    marginal_value: float
    rhs: float
    description: str
    is_sa1_relevant: bool
    matched_synthetic_buses: list[int]


def _day_window(date: str) -> tuple[str, str]:
    day = datetime.date.fromisoformat(date)
    next_day = day + datetime.timedelta(days=1)
    fmt = "%Y/%m/%d %H:%M:%S"
    start = datetime.datetime.combine(day, datetime.time.min).strftime(fmt)
    end = datetime.datetime.combine(next_day, datetime.time.min).strftime(fmt)
    return start, end


def _binding_constraints(date: str) -> pd.DataFrame:
    """All (non-intervention) binding DISPATCHCONSTRAINT rows for `date`,
    i.e. MARGINALVALUE != 0 -- the "actually binding" filter
    docs/LAB4_AEMO_REAL_DATA.md Part B step 1 asks for.

    Args:
        date: ISO date already fetched by fetch_day.py.

    Returns:
        DISPATCHCONSTRAINT rows, INTERVENTION == 0 and MARGINALVALUE != 0.
    """
    start, end = _day_window(date)
    dc = dynamic_data_compiler(
        start, end, "DISPATCHCONSTRAINT", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    return dc[(dc["INTERVENTION"] == 0) & (dc["MARGINALVALUE"] != 0)]


def _candidate_order(binding: pd.DataFrame) -> list[str]:
    """Unique CONSTRAINTIDs from `binding`, ordered by total |marginal
    value| that day, descending (most economically significant first)."""
    return list(
        binding.groupby("CONSTRAINTID")["MARGINALVALUE"]
        .apply(lambda s: s.abs().sum())
        .sort_values(ascending=False)
        .index
    )


def _is_sa1_relevant(lhs: pd.DataFrame, sa1_duids: set[str]) -> bool:
    """Whether a constraint's decoded LHS terms touch SA1 at all: a
    REGION term for SA1, an INTERCONNECTOR term for one of
    SA_INTERCONNECTOR_IDS, or a CONNECTIONPOINT term whose DUID is a real
    SA1 generator DUID.

    This is the "use the library to find out, don't guess from the ID
    string" check -- several plausible-looking IDs in LAB4_DATE's binding
    set (e.g. "S^DVPL_CRK_VCS") turned out on decoding to be unrelated to
    SA1's generation/interconnection when checked at implementation time.

    Args:
        lhs: get_LHS_terms() output.
        sa1_duids: real SA1 DUIDs (from DUDETAILSUMMARY).

    Returns:
        True if any LHS row touches SA1.
    """
    if lhs.empty:
        return False
    region_hit = ((lhs["type"] == "REGION") & (lhs["ID"] == LAB4_REGION)).any()
    interconnector_hit = (
        (lhs["type"] == "INTERCONNECTOR") & (lhs["ID"].isin(SA_INTERCONNECTOR_IDS))
    ).any()
    duid_hit = (
        (lhs["type"] == "CONNECTIONPOINT") & (lhs["DUID"].isin(sa1_duids))
    ).any()
    return bool(region_hit or interconnector_hit or duid_hit)


def _sa1_duids(date: str) -> set[str]:
    """Real SA1 DUIDs (any DISPATCHTYPE) for `date`, used only for the
    LHS-relevance check above (a superset of map_duids.py's GENERATOR-only
    filter, since a binding constraint can legitimately reference a load
    DUID too)."""
    start, end = _day_window(date)
    dud = dynamic_data_compiler(
        start, end, "DUDETAILSUMMARY", str(NEMOSIS_CACHE_DIR),
        fformat="parquet", keep_csv=False,
    )
    return set(dud[dud["REGIONID"] == LAB4_REGION]["DUID"])


def find_sa1_binding_constraint(
    date: str = LAB4_DATE, verbose: bool = True
) -> tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Search LAB4_DATE's binding constraints for one that is SA1-relevant.

    Args:
        date: ISO date to search.
        verbose: if True, print each candidate checked.

    Returns:
        (constraint_id, description_df, lhs, rhs, binding_row) for the
        first SA1-relevant candidate found, or -- if none of the first
        MAX_CANDIDATES_CHECKED are SA1-relevant -- the single most-binding
        candidate overall, clearly flagged as such by the caller.
    """
    binding = _binding_constraints(date)
    candidates = _candidate_order(binding)[:MAX_CANDIDATES_CHECKED]
    sa1_duids = _sa1_duids(date)

    fallback: Optional[tuple[str, pd.DataFrame, pd.DataFrame, pd.DataFrame]] = None
    for cid in candidates:
        gencon_def, found = find_constraint(cid, start_date=CONSTRAINT_SEARCH_FLOOR)
        if not found:
            if verbose:
                print(f"  {cid}: definition not found in GENCONDATA archive, skipping")
            continue
        effective = pd.to_datetime(gencon_def.iloc[0]["EFFECTIVEDATE"])
        description, lhs, rhs = get_constraint_details(cid, effective.month, effective.year)
        relevant = _is_sa1_relevant(lhs, sa1_duids)
        if verbose:
            desc_text = description.iloc[0]["DESCRIPTION"] if not description.empty else "?"
            print(f"  {cid}: {'SA1-relevant' if relevant else 'not SA1-relevant'} -- {desc_text}")
        if fallback is None:
            fallback = (cid, description, lhs, rhs)
        if relevant:
            binding_row = binding[binding["CONSTRAINTID"] == cid].loc[
                binding[binding["CONSTRAINTID"] == cid]["MARGINALVALUE"].abs().idxmax()
            ]
            return cid, description, lhs, rhs, binding_row

    if fallback is None:
        print("[FAIL] no candidate constraint's definition could be found", file=sys.stderr)
        sys.exit(1)
    cid, description, lhs, rhs = fallback
    if verbose:
        print(
            f"No SA1-relevant constraint found in the first "
            f"{len(candidates)} candidates -- falling back to the single "
            f"most-binding constraint of the day ({cid}), not SA1-specific."
        )
    binding_row = binding[binding["CONSTRAINTID"] == cid].loc[
        binding[binding["CONSTRAINTID"] == cid]["MARGINALVALUE"].abs().idxmax()
    ]
    return cid, description, lhs, rhs, binding_row


def _matched_synthetic_buses(lhs: pd.DataFrame) -> list[int]:
    """Cross-reference a constraint's LHS connection-point DUIDs against
    duid_mapping.csv (docs/LAB4_AEMO_REAL_DATA.md Part B step 3: "cross-
    referencing which of Part A's matched synthetic generators/lines the
    constraint's DUIDs correspond to").

    Args:
        lhs: get_LHS_terms() output for the chosen constraint.

    Returns:
        Sorted, deduplicated synthetic generator bus ids that Part A
        mapped at least one of this constraint's LHS DUIDs onto. Empty if
        duid_mapping.csv doesn't exist yet or none of the LHS DUIDs were
        matched.
    """
    if not MAPPING_CSV.exists() or lhs.empty:
        return []
    mapping = pd.read_csv(MAPPING_CSV)
    lhs_duids = set(lhs["DUID"])
    matched = mapping[mapping["real_duid"].isin(lhs_duids)]
    return sorted(set(int(b) for b in matched["synthetic_gen_bus"]))


def _plain_english(
    constraint_id: str, description: str, lhs: pd.DataFrame, rhs: pd.DataFrame,
    marginal_value: float, rhs_value: float, matched_buses: list[int],
) -> str:
    """Compose the one-paragraph plain-English translation docs/LAB4_
    AEMO_REAL_DATA.md Part B step 4 asks for.

    Sandbox note: same as Lab 2's draft_memo / reconcile.py's
    _reconciliation_memo -- this sandbox has no live LLM server (see
    labs/01-simple-loadflow-fit/run.py's module docstring), so this is a
    plain Python f-string template over the real decoded LHS/RHS terms,
    not an LLM's free-form summary. docs/LAB4_AEMO_REAL_DATA.md Part B
    step 3 describes this as "PowerSkills-style progressive disclosure" --
    this template implements the first ("what does this constraint say")
    level only; the "why is it binding" escalation is out of scope here
    (it would need bid-stack/dispatch-price data this lab doesn't pull).

    Args:
        constraint_id: the GENCONID.
        description: GENCONDATA's free-text DESCRIPTION for this
            constraint.
        lhs: decoded LHS terms.
        rhs: decoded RHS terms.
        marginal_value: the real $/MWh shadow price at the binding
            interval.
        rhs_value: the real RHS (limit) value at the binding interval.
        matched_buses: output of _matched_synthetic_buses.

    Returns:
        The paragraph.
    """
    lhs_kinds = lhs["type"].value_counts().to_dict() if not lhs.empty else {}
    kind_text = ", ".join(f"{n} {k.lower()}" for k, n in lhs_kinds.items()) or "no terms"

    match_text = (
        f"Part A's DUID mapping ties this constraint to synthetic "
        f"generator bus(es) {matched_buses}, so a modeller using this "
        f"lab's digital twin could locate the constraint's real-world "
        f"physical location on the synthetic network directly."
        if matched_buses
        else "None of this constraint's DUIDs were matched to a synthetic "
        "generator by Part A's duid_mapping.csv (it may be an "
        "interconnector- or region-level constraint with no generator "
        "connection-point terms, or reference DUIDs Part A's matching "
        "didn't reach)."
    )

    return (
        f"Constraint {constraint_id} ({description}) was binding with a "
        f"real shadow price of ${marginal_value:.2f}/MWh against a limit "
        f"(RHS) of {rhs_value:.1f}. Its left-hand side sums {kind_text} -- "
        f"in plain terms, AEMO's dispatch engine is holding some "
        f"combination of generation, interconnector flow, or regional "
        f"demand at or below this limit, and the nonzero shadow price "
        f"means at least one participant's cheapest available bid is "
        f"being displaced by more expensive generation elsewhere to "
        f"respect it -- that displaced-cost figure is exactly the "
        f"marginal value. {match_text}"
    )


def explain(date: str = LAB4_DATE, verbose: bool = True) -> DecodedConstraint:
    """Run Part B end to end: find, decode, and explain one SA1-relevant
    binding constraint.

    Args:
        date: ISO date to search (LAB4_DATE by default).
        verbose: if True, print the search, the decoded terms, and the
            plain-English paragraph (see README step 4).

    Returns:
        A DecodedConstraint summarizing the result.
    """
    if verbose:
        print(f"Searching {date}'s binding constraints for an SA1-relevant one...")
    cid, description, lhs, rhs, binding_row = find_sa1_binding_constraint(date, verbose)

    # GENCONDATA can carry more than one VERSIONNO row within a single
    # month's archive extract (a mid-month revision); take the latest.
    if not description.empty:
        latest = description.sort_values("VERSIONNO", ascending=False).iloc[0]
        desc_text = str(latest["DESCRIPTION"])
        constraint_type = str(latest["CONSTRAINTTYPE"])
        constraint_value = latest["CONSTRAINTVALUE"]
    else:
        desc_text, constraint_type, constraint_value = "(no description found)", "?", None

    interval = str(binding_row["SETTLEMENTDATE"])
    marginal_value = float(binding_row["MARGINALVALUE"])
    rhs_value = float(binding_row["RHS"])
    sa1_duids = _sa1_duids(date)
    relevant = _is_sa1_relevant(lhs, sa1_duids)
    matched_buses = _matched_synthetic_buses(lhs)

    # LHS/RHS both carry one row per (EFFECTIVEDATE, VERSIONNO) the
    # archive extract has seen, not just the current one (same upstream
    # behaviour noted in nem_constraints_vendored.get_RHS_terms's
    # docstring) -- deduped here for a readable printed table only, the
    # underlying decode is untouched.
    lhs_display = lhs.drop_duplicates() if not lhs.empty else lhs
    rhs_display = (
        rhs.drop_duplicates(subset=["term_ID", "ID", "factor", "operation"])
        if not rhs.empty else rhs
    )

    if verbose:
        print()
        print(f"Constraint: {cid}")
        print(f"Description: {desc_text}")
        print(f"Type: {constraint_type} {constraint_value}  (GENCONDATA CONSTRAINTTYPE/CONSTRAINTVALUE)")
        print(f"Binding interval: {interval}  marginal_value=${marginal_value:.2f}/MWh  RHS={rhs_value:.1f}")
        print(f"SA1-relevant: {relevant}")
        print()
        print(f"LHS terms ({len(lhs_display)} unique of {len(lhs)} raw rows):")
        print(lhs_display.to_string(index=False) if not lhs_display.empty else "  (none)")
        print()
        print(f"RHS terms ({len(rhs_display)} unique of {len(rhs)} raw rows -- "
              f"see nem_constraints_vendored.get_RHS_terms docstring, "
              f"upstream's GENERICCONSTRAINTRHS carries multiple EFFECTIVEDATE/ "
              f"VERSIONNO rows per term):")
        if rhs_display.empty:
            print(
                f"  (none -- this constraint's RHS is a fixed value from "
                f"GENCONDATA directly: {constraint_type} {constraint_value}, "
                f"not a computed GENERICCONSTRAINTRHS formula)"
            )
        else:
            print(rhs_display.to_string(index=False))
        print()
        print(_plain_english(cid, desc_text, lhs_display, rhs, marginal_value, rhs_value, matched_buses))

    return {
        "constraint_id": cid,
        "interval": interval,
        "marginal_value": round(marginal_value, 3),
        "rhs": round(rhs_value, 3),
        "description": desc_text,
        "is_sa1_relevant": relevant,
        "matched_synthetic_buses": matched_buses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=LAB4_DATE)
    args = parser.parse_args()
    explain(args.date)


if __name__ == "__main__":
    main()
