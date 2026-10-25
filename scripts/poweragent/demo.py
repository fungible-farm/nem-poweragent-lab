# Reproduces docs/poweragent/evidence/phase2-run: authorized run, unauthorized run, HTML report. Run via `just poweragent::demo`.
import json, os, shutil, subprocess, sys
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).replace("\\", "/")
def wp(x):  # path the Windows binaries understand (this may run under WSL as /mnt/d/...)
    return (x[5].upper() + ":" + x[6:]) if x.startswith("/mnt/") else x
d = root + "/docs/poweragent/evidence/phase2-run"
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d + "/in"); os.makedirs(d + "/out")
open(d + "/in/data.bin", "wb").write(bytes([1, 2, 3, 4, 250]))
caps = [
    {"kind": "fs_read", "path": wp(d) + "/in"},
    {"kind": "fs_write", "path": wp(d) + "/out"},
    {"kind": "sidecar", "name": "pandapower"},
    {"kind": "sidecar", "name": "powerio"},
]
json.dump({"apiVersion": "poweragent.dev/v1alpha1", "kind": "TaskProfile", "metadata": {"name": "nem-study"},
           "spec": {"untrustedCode": True, "timeoutSeconds": 20, "capabilities": caps}}, open(d + "/profile.json", "w"), indent=1)
json.dump({"allowedCapabilities": caps, "allowedFallbacks": []}, open(d + "/policy.json", "w"), indent=1)
json.dump({"allowedCapabilities": [], "allowedFallbacks": []}, open(d + "/policy-empty.json", "w"))
json.dump([{"name": "pandapower", "runtime": "podman"},
           {"name": "powerio", "runtime": "podman", "dependsOn": ["pandapower"]},
           {"name": "powerfactory-adapter", "runtime": "windows"}], open(d + "/registry.json", "w"), indent=1)

exe = root + "/rust/target/debug/poweragent.exe"
D = wp(d)
def run(label, policy, out):
    r = subprocess.run([exe, "run", "--profile", D + "/profile.json", "--policy", D + "/" + policy,
                        "--registry", D + "/registry.json", "--audit", D + "/audit.jsonl",
                        "--in", D + "/in/data.bin", "--out", D + "/out/" + out], capture_output=True, text=True)
    print(f"{label}: exit={r.returncode} stderr={r.stderr.strip()} output_exists={os.path.exists(d + '/out/' + out)}")
run("authorized", "policy.json", "sum.txt")
print("sum.txt =", open(d + "/out/sum.txt").read() if os.path.exists(d + "/out/sum.txt") else None)
run("unauthorized", "policy-empty.json", "sum2.txt")
r = subprocess.run([exe, "report", "--audit", D + "/audit.jsonl", "--out", D + "/report.html"])
print("report exit =", r.returncode)
html = open(d + "/report.html", encoding="utf-8").read()
print("verified line:", [l for l in html.split("<") if l.startswith("p class=ok>")][:1])
print("rows:", html.count("<tr><td>"), " script tags:", html.count("<script"))
