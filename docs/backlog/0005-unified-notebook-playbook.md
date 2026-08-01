# 0005 — Suggestion: a notebook playbook binding all 5 labs' visual outputs together

- **Status:** proposed (this is a recommendation, not yet agreed scope)
- **Depends on:** 0001–0004
- **Prompted by:** "ideally something that is a playbook like a jupyter notebook to bind them all
  together" — evaluated against this repo's existing, non-negotiable conventions below, not
  proposed in the abstract.

## The tension to resolve first

`AGENTS.md` "Non-negotiable conventions" states plainly: **"The proof scripts are the proof, not a
transcript. ... Running commands ad hoc in a session is not proof anything works — a committed
script re-deriving the same result on a clean checkout is."** A raw `.ipynb` — hand-run, outputs
baked into the file, no forced re-execution — is exactly the "ad hoc session masquerading as
proof" this repo already explicitly rejects. So the suggestion below is deliberately **not** "add
a notebook that computes things," it's "add a notebook that narrates and renders things the
committed scripts already proved" — a strict layer on top of, never a replacement for, the
existing five `--step check` proof scripts.

## Concrete suggestion

`notebooks/lab_playbook.py`, authored in **[jupytext](https://jupytext.readthedocs.io/) `percent`
format**, not a raw `.ipynb`:

- Plain-text `.py` with `# %%` cell markers — diffable and reviewable in a normal PR, unlike a
  JSON `.ipynb` with embedded base64 image blobs. `jupytext` is on PyPI, one new dev-only
  dependency. Opens as a normal notebook in Jupyter/VS Code via the jupytext extension; nothing
  about the interactive experience is lost, only the "outputs committed to git" anti-pattern.
- Structure — one section per lab, in the same order the README already teaches them
  (`install.sh` → Lab 1 → 2 → 3 → 4 → 5), each section:
  1. Shells out to (or imports and calls) that lab's own `--step check` and asserts PASS —
     **fails loudly, in-notebook, if a lab's proof doesn't hold**, rather than silently plotting
     stale numbers.
  2. Loads that lab's already-committed fixture/result file
     (`expected_fit.json`/`expected_contingency_table.json`/`scorecard.json`/
     `expected_reconciliation.json`/Lab 5's transient output) — never recomputes independently.
  3. Renders exactly the chart(s) scoped in 0003/0004: Lab 1's convergence curve, Lab 2's
     contingency loading bar, Lab 3's provider scorecard bars, Lab 4's modelled-vs-actual time
     series, Lab 5's topology graph plus the existing transient waveform.
- Execution discipline, matching the rest of the repo's self-checking convention: add a
  `uv run jupytext --to notebook --execute notebooks/lab_playbook.py` step (or an `nbconvert
  --execute`) to `scripts/run_labs_1_3.sh`/`run_lab4.sh`'s spirit — i.e. this notebook gets
  *executed*, not just eyeballed, the same way every other "proof" in this repo is. A notebook
  that only renders correctly when someone happens to run it by hand is the same failure mode
  `AGENTS.md` already warns about, one layer up.

## Why this is the right shape given the existing lab requirements

- It doesn't introduce a second orchestration system — it calls the five labs' existing CLIs
  exactly as documented in `AGENTS.md` "Running the labs," so there's exactly one way to run
  anything in this repo, just an additional way to *look* at the results.
- It matches `docs/VISION.md` §11's asciinema-recording philosophy almost exactly: "the recording
  is an artifact of this repo, not a separate hand-edited video — re-running the script after any
  lab changes regenerates it, so the walkthrough can't drift out of sync with the actual code."
  Substitute "notebook" for "recording" and the same argument holds, and re-executing on demand is
  the mechanism that keeps that true.
- It's the natural home for exactly the "bind them all together" narrative the user asked for —
  one linear document a presenter can step through instead of five terminal windows — without
  weakening any lab's individual, already-implemented self-check.

## Explicitly out of scope for this item

Committing rendered chart images *inside* the notebook's own git history (defeats the diffability
point of choosing jupytext over `.ipynb` in the first place) — PNGs belong in each lab's own
directory (per 0003/0004's "committed PNG" pattern), the notebook only renders/displays them
inline when executed, it doesn't own them.
