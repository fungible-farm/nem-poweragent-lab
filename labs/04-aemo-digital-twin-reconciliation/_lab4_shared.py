"""Shared constants and helpers for Lab 4's four scripts (fetch_day.py,
map_duids.py, reconcile.py, explain_constraint.py) -- kept in one place so
the chosen date/region/cache-path/tolerance can't drift between scripts,
the same role `labs/_shared/gridfit.py` plays for Labs 1-3.

Sandbox note: unlike Labs 1-3 (fully offline, gitignored `data/` populated
once by `scripts/fetch_csiro_nem_data.py`), Lab 4 makes a live network call
to nemweb.com.au (AEMO's public MMS data archive) via NEMOSIS every run.
That is not a sandbox stand-in -- it is the real thing docs/VISION.md's
Definition of Done asks for ("the NEMOSIS pull from AEMO's NEMWeb... cached
exactly like the others after first run") -- but it is the one place in
this repo where "real data" means "a real HTTP call," so it is named here
up front rather than only in each script's docstring.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = LAB_DIR.parent.parent
sys.path.insert(0, str(LAB_DIR.parent))  # for `from _shared.gridfit import ...`

import pandapower as pp  # noqa: E402
from _shared.gridfit import load_case  # noqa: E402

# Real CSIRO Synthetic-NEM-2000-Bus South-Australia-only case, same file
# Lab 1 uses (see scripts/fetch_csiro_nem_data.py).
DATA_FILE: Final[Path] = REPO_ROOT / "data" / "snemSA.m"

# NEMOSIS's on-disk cache. Gitignored by the existing root `.gitignore`
# `data/*` rule (same as `data/snemSA.m` etc.) -- never vendored, refetched
# (or served from NEMOSIS's own cache) on every clean checkout, exactly like
# scripts/fetch_csiro_nem_data.py's CHECKSUMS-verified fetch for Labs 1-3.
NEMOSIS_CACHE_DIR: Final[Path] = REPO_ROOT / "data" / "nemosis_cache"
# NEMOSIS's dynamic_data_compiler raises UserInputError if raw_data_location
# doesn't already exist as a directory (confirmed: it does not create it
# itself) -- fetch_day.py already mkdir'd this before its own nemosis calls,
# but reconcile.py/map_duids.py/explain_constraint.py called nemosis
# directly without it, working only by accident on a host where some prior
# run (or ./install.sh) had already populated data/nemosis_cache/. Created
# here, once, at import time, so every one of this lab's four scripts gets
# it regardless of import order -- including a genuinely fresh checkout or
# container image where data/nemosis_cache/ has never existed before.
NEMOSIS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# docs/LAB4_AEMO_REAL_DATA.md Part A step 1: "default: SA1, since it lines
# up with the snemSA.m case already used in Lab 1." snemSA.m is a
# South-Australia-only island reduction of the full CSIRO 2000-bus case, so
# SA1 is the only region this lab's synthetic network can represent at all.
LAB4_REGION: Final[str] = "SA1"

# NEMOSIS table name for DUID -> STATIONID -> PARTICIPANTID registration
# metadata, shared by fetch_day.py and map_duids.py so both agree on which
# table they're pulling.
DUID_TABLE_NAME: Final[str] = "DUDETAILSUMMARY"

# The "one recent, unremarkable day" (docs/LAB4_AEMO_REAL_DATA.md Part A
# step 1). Chosen by direct trial at implementation time (2026-07-31): the
# July-2026 MMSDM monthly archive is not yet published (a real HTTP 404 on
# nemweb.com.au's PUBLIC_ARCHIVE#DISPATCHPRICE zip for 2026/07 at build
# time -- AEMO publishes each month's MMSDM historical extract with a
# roughly one-month lag), while June 2026's archive is live (verified
# `curl -I` 200, and a real `nemosis.dynamic_data_compiler()` pull for this
# exact date succeeded during implementation). 15 June 2026 has nothing
# notable in AEMO's public record for SA1 -- ordinary weekday demand
# (~1.8 GW), no extreme-price interval, no SA-wide event.
LAB4_DATE: Final[str] = "2026-06-15"

# Dispatch interval used for Part A's reconciliation. Chosen (by direct
# trial) as an interval with no SA1-attributed binding constraint, so the
# reconciliation gap Part A is scoring is purely "synthetic topology meets
# real SCADA," not "synthetic topology meets a congested/constrained
# interval" -- a cleaner first read of the mechanic. Part B (explain_
# constraint.py) deliberately searches the same day for an interval where a
# real constraint *is* binding instead (see CONSTRAINT_SEARCH_START below) --
# the two scripts intentionally use different intervals of the same day for
# different teaching points; each prints which interval it used.
RECONCILE_INTERVAL: Final[str] = f"{LAB4_DATE} 12:00:00"

# Half-open window nemosis.dynamic_data_compiler() needs for a single
# dispatch interval pull: SETTLEMENTDATE-stamped rows are keyed to the
# interval's *end* time, so [interval, interval + 5min) reliably returns
# exactly the rows for that interval regardless of which side NEMOSIS
# treats as inclusive.
DISPATCH_INTERVAL_MINUTES: Final[int] = 5

# docs/LAB4_AEMO_REAL_DATA.md Part A step 7, verbatim: "Score pass within a
# stated, generous tolerance (e.g. +/-15%) -- deliberately looser than Lab
# 1's tight synthetic-fit tolerance, because a synthetic topology meeting
# real data is expected to diverge." Taken directly at the spec's own
# suggested value rather than invented separately -- see this lab's
# README.md "Sandbox notes" for the full rationale (aggregated slack-bus
# equivalent for two real interconnectors with different impedance/loss
# characteristics, unmatched generators left at base-case dispatch, a
# single uniform load-scaling factor standing in for AEMO's actual
# bus-by-bus real demand).
RECONCILE_TOLERANCE_FRACTION: Final[float] = 0.15

# Floor on the denominator used by the relative tolerance check, so a
# near-zero actual interconnector flow (which does occur on some 5-minute
# intervals) can't make the pass/fail check meaningless (a tiny absolute
# MW delta would otherwise be an enormous relative error). 10 MW is small
# relative to Heywood's ~600 MW rating and SA1's typical >1000 MW demand --
# it only engages on intervals where the real interconnector flow is
# itself near zero.
RECONCILE_TOLERANCE_FLOOR_MW: Final[float] = 10.0

# The two real AEMO interconnectors terminating in SA1 (from
# DISPATCHINTERCONNECTORRES's INTERCONNECTORID values, confirmed by a real
# pull for LAB4_DATE): V-SA is the Heywood interconnector (VIC1<->SA1,
# AC), V-S-MNSP1 is Murraylink (VIC1<->SA1, DC). snemSA.m being an
# SA-only island reduction of the full NEM case has no separate branches
# for these -- see INTERCONNECTOR_EQUIVALENT_BUS below for how the
# synthetic model represents their combined effect.
SA_INTERCONNECTOR_IDS: Final[tuple[str, str]] = ("V-SA", "V-S-MNSP1")

# snemSA.m's mpc.gen has exactly one generator with MATPOWER bus type 3
# (reference/slack): bus 986 (1-indexed MATPOWER numbering; bus 985 here,
# pandapower's 0-indexed numbering after powerio's conversion), tied to bus
# 1800 by a branch of ~1e-9 p.u. impedance (effectively a zero-impedance
# tie). Every other one of the case's 57 generators is a normal PV bus.
# A single-region MATPOWER island case needs exactly one reference bus to
# solve; CSIRO's choice of bus 986 for that role -- an otherwise-ordinary-
# looking generator with an unusually wide reactive band (Qmax/Qmin
# +71/-243 Mvar vs. a ~37 MVA mBase) and a near-zero-impedance tie -- reads
# as the case's stand-in for "the rest of the NEM," i.e. the model's own
# equivalent of the real Heywood + Murraylink interconnection. This lab
# treats this bus's post-power-flow output as the modelled counterpart of
# SA_INTERCONNECTOR_IDS' combined real flow. Named explicitly (not
# inferred silently) because nothing in snemSA.m's own metadata labels it
# as such -- reconcile.py asserts this is in fact the net's unique slack
# generator at runtime and fails loudly if that assumption ever breaks.
INTERCONNECTOR_EQUIVALENT_BUS: Final[int] = 985

# Optional Part C (docs/LAB4_AEMO_REAL_DATA.md): the 2016 SA Black System
# event date, and a pre-event interval confirmed (by direct trial) to have
# real MMSDM archive data available. 15:30 AEST is ~48 minutes before the
# cascading trips that began the event (documented at ~16:18 AEST in
# AEMO's integrated final report -- see README references) -- late enough
# to show the real high-wind-penetration pre-event dispatch mix the report
# describes, early enough that this is an ordinary (if unusually windy)
# dispatch interval, not the event itself. See reconcile.py's
# PART_C_CAVEAT for the required "not a fault-reproduction claim" caveat
# this interval is always printed alongside.
PART_C_DATE: Final[str] = "2016-09-28"
PART_C_INTERVAL: Final[str] = "2016-09-28 15:30:00"


def load_synthetic_net() -> tuple[pp.pandapowerNet, list[str]]:
    """Load snemSA.m the same way Lab 1 does, failing the same way if the
    CSIRO fetch hasn't been run yet.

    Returns:
        (net, warnings) from `_shared.gridfit.load_case`.
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)
    return load_case(DATA_FILE)


def slack_bus(net: pp.pandapowerNet) -> int:
    """Return the net's unique slack generator's bus id, asserting it
    matches INTERCONNECTOR_EQUIVALENT_BUS.

    Raises:
        AssertionError: if snemSA.m's slack bus is ever not exactly
            INTERCONNECTOR_EQUIVALENT_BUS -- i.e. the documented assumption
            behind treating it as the interconnector-equivalent bus no
            longer holds (e.g. a future CSIRO data revision), so this lab
            fails loudly instead of silently reconciling against the wrong
            bus.
    """
    slack_rows = net.gen[net.gen["slack"]]
    assert len(slack_rows) == 1, (
        f"expected exactly one slack generator in snemSA.m, found "
        f"{len(slack_rows)}"
    )
    bus = int(slack_rows.iloc[0]["bus"])
    assert bus == INTERCONNECTOR_EQUIVALENT_BUS, (
        f"snemSA.m's slack bus is {bus}, expected "
        f"{INTERCONNECTOR_EQUIVALENT_BUS} -- INTERCONNECTOR_EQUIVALENT_BUS "
        f"in _lab4_shared.py is now stale, see its docstring"
    )
    return bus
