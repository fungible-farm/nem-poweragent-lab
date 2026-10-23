"""Check the CGMES export against pypowsybl, an independent CGMES implementation (backlog 0034).

pypowsybl publishes no Linux ARM64 wheel and no sdist, so its half runs on an x86-64 peer
(``scripts/cgmes_peer_check.sh``, ``just powercoder::cgmes-peer-check``). Three steps:

    export   (here)   solve snemSA with pandapower; write EQ/TP/SSH as a CGMES zip and the
                      pandapower bus voltages by name
    check    (peer)   pypowsybl imports the zip, solves AC, writes element counts, status and
                      bus voltages by name (needs ``pypowsybl``; nothing else from this repo)
    compare  (here)   per-bus |dV| between the two solvers; exit 1 above the tolerance

Measured 2026-10-23 (pypowsybl 1.16.1 on sm3lly): every element imported (503 buses, 295
lines, 403 transformers, 57 generators, 186 loads, 782 shunts), OpenLoadFlow converged,
max |dV| 1.38e-5 pu over all 503 buses (mean 5.1e-7).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

CASE: str = "snem-sa-2000"
# Gate on the cross-solver agreement: measured max 1.38e-5 pu (2026-10-23), so 1e-4 pu
# fails a real modelling regression (a dropped tap changer gave 0.275 pu) but not solver noise.
VOLTAGE_TOLERANCE_PU: float = 1e-4
# pypowsybl names a bus "<topological node name>_<index within its voltage level>".
BUS_SUFFIX: re.Pattern[str] = re.compile(r"_\d+$")


def export(zip_path: Path, voltages_path: Path) -> dict[str, int]:
    """Solve the case, write its CGMES profiles and pandapower's bus voltages by name."""
    import pandapower as pp

    from powercoder.inference import powermcp as pm
    from powercoder.semantic.cgmes import solved_reactive_power, split_profiles
    from powercoder.semantic.export import export_network

    net, _ = pm._load_network_object(CASE)
    pp.runpp(net, numba=True)
    docs = split_profiles(export_network(net, CASE), CASE, initial_q=solved_reactive_power(net, CASE))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for profile in ("EQ", "TP", "SSH"):
            buffer = io.BytesIO()
            docs[profile].serialize(buffer, format="xml")
            archive.writestr(f"{CASE}_{profile}.xml", buffer.getvalue())
    voltages_path.write_text(json.dumps({str(net.bus.name[b]): float(net.res_bus.vm_pu[b]) for b in net.bus.index}))
    return {profile: len(doc) for profile, doc in docs.items()}


def check(zip_path: Path, out_path: Path) -> dict:
    """Import with pypowsybl, solve AC, and record counts, status and voltages (run on the peer)."""
    import pypowsybl
    import pypowsybl.loadflow as lf
    import pypowsybl.network as pn

    net = pn.load(str(zip_path))
    kinds = ("buses", "lines", "2_windings_transformers", "generators", "loads", "shunt_compensators")
    result = {"pypowsybl": pypowsybl.__version__,
              "counts": {kind: len(getattr(net, f"get_{kind}")()) for kind in kinds},
              "loadflow": [str(component.status) for component in lf.run_ac(net)]}
    generators = net.get_generators()
    result["voltage_regulating_generators"] = int(generators.voltage_regulator_on.sum())
    buses, levels = net.get_buses(), net.get_voltage_levels()
    result["vm_by_name"] = {str(bus["name"]): float(bus.v_mag / levels.loc[bus.voltage_level_id, "nominal_v"])
                            for _, bus in buses.iterrows()}
    out_path.write_text(json.dumps(result, indent=1))
    return result


def compare(voltages_path: Path, peer_path: Path, tolerance: float = VOLTAGE_TOLERANCE_PU) -> dict:
    """Per-bus |dV| between pandapower and pypowsybl; ``passed`` when every bus is within tolerance."""
    ours = json.loads(voltages_path.read_text())
    peer = json.loads(peer_path.read_text())
    differences = {BUS_SUFFIX.sub("", name): abs(v - ours[BUS_SUFFIX.sub("", name)])
                   for name, v in peer["vm_by_name"].items() if BUS_SUFFIX.sub("", name) in ours and v == v}
    worst = max(differences.items(), key=lambda item: item[1]) if differences else (None, float("inf"))
    return {"counts": peer["counts"], "loadflow": peer["loadflow"],
            "voltage_regulating_generators": peer.get("voltage_regulating_generators"),
            "buses_compared": len(differences), "buses_in_case": len(ours),
            "max_abs_dv_pu": worst[1], "worst_bus": worst[0],
            "mean_abs_dv_pu": sum(differences.values()) / len(differences) if differences else None,
            "tolerance_pu": tolerance,
            "passed": len(differences) == len(ours) and worst[1] <= tolerance
                      and all(status.endswith("CONVERGED") for status in peer["loadflow"])}


def main() -> int:
    """Run one step (see the module docstring)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    steps = parser.add_subparsers(dest="step", required=True)
    e = steps.add_parser("export")
    e.add_argument("--zip", type=Path, required=True)
    e.add_argument("--voltages", type=Path, required=True)
    c = steps.add_parser("check")
    c.add_argument("--zip", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    m = steps.add_parser("compare")
    m.add_argument("--voltages", type=Path, required=True)
    m.add_argument("--peer", type=Path, required=True)
    args = parser.parse_args()
    if args.step == "export":
        print(json.dumps(export(args.zip, args.voltages)))
        return 0
    if args.step == "check":
        result = check(args.zip, args.out)
        print(json.dumps({k: v for k, v in result.items() if k != "vm_by_name"}))
        return 0
    report = compare(args.voltages, args.peer)
    print(json.dumps(report, indent=1))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
