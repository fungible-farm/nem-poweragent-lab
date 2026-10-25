"""Build the pilot kit zip: release binaries, checksums, docs, fixtures, evidence, dependency inventory.

usage (from WSL, via `just poweragent::pack`): python3 pack.py
The kit is UNSIGNED and for lab evaluation. Its SHA256SUMS detect corruption, not a malicious
publisher; signing is the Gate 5 work (docs/poweragent/gate0-status.md).
"""
import hashlib, os, re, shutil, subprocess, sys, zipfile

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rust = os.path.join(repo, "rust")
dist = os.path.join(repo, "dist")

ver = re.search(r'^version = "([^"]+)"', open(os.path.join(rust, "poweragent", "Cargo.toml")).read(), re.M).group(1)
try:
    rev = subprocess.check_output(["git", "-C", repo, "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
except Exception:
    rev = "unknown"
name = f"poweragent-pilot-{ver}-{rev}-win-x64"
stage = os.path.join(dist, name)

subprocess.check_call(["cargo.exe", "build", "--release", "--locked", "-p", "poweragent", "-p", "poweragent-exec", "-p", "poweragent-probe"], cwd=rust)

shutil.rmtree(stage, ignore_errors=True)
os.makedirs(os.path.join(stage, "bin"))
for exe in ("poweragent.exe", "poweragent-worker.exe", "poweragent-probe.exe"):
    shutil.copy2(os.path.join(rust, "target", "release", exe), os.path.join(stage, "bin", exe))
shutil.copytree(os.path.join(repo, "docs", "it-pack"), os.path.join(stage, "docs"))
shutil.copytree(os.path.join(repo, "docs", "poweragent", "fixtures"), os.path.join(stage, "fixtures"))
shutil.copytree(os.path.join(repo, "docs", "poweragent", "evidence"), os.path.join(stage, "evidence"))
shutil.copy2(os.path.join(repo, "docs", "poweragent", "gate0-status.md"), os.path.join(stage, "docs", "gate-status.md"))
shutil.copy2(os.path.join(repo, "scripts", "poweragent", "kit", "Verify-Pilot.ps1"), stage)
shutil.copy2(os.path.join(repo, "docs", "it-pack", "README.md"), os.path.join(stage, "README.md"))
for lic in ("LICENSE", "LICENSE-MIT", "LICENSE-APACHE"):
    p = os.path.join(repo, lic)
    if os.path.exists(p):
        shutil.copy2(p, stage)
subprocess.check_call([sys.executable, os.path.join(repo, "scripts", "poweragent", "deps.py"), os.path.join(stage, "docs", "DEPENDENCIES.md")])

lines = []
for base, _, files in os.walk(stage):
    for f in sorted(files):
        full = os.path.join(base, f)
        rel = os.path.relpath(full, stage).replace(os.sep, "/")
        lines.append(f"{hashlib.sha256(open(full, 'rb').read()).hexdigest()}  {rel}")
lines.sort(key=lambda l: l.split("  ", 1)[1])
open(os.path.join(stage, "SHA256SUMS"), "w", newline="\n").write("\n".join(lines) + "\n")

zpath = os.path.join(dist, name + ".zip")
if os.path.exists(zpath):
    os.remove(zpath)
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk(stage):
        for f in sorted(files):
            full = os.path.join(base, f)
            z.write(full, os.path.join(name, os.path.relpath(full, stage)))
zsha = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
open(zpath + ".sha256", "w", newline="\n").write(f"{zsha}  {name}.zip\n")
print(f"{zpath}\nsha256 {zsha}\n{len(lines)} files, {os.path.getsize(zpath)//1024} KiB")
