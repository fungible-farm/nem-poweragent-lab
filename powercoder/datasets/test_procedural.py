"""N-1 and free-text pool tasks are checked on the network they pose, and say everything they need."""

from __future__ import annotations

import re

import pytest

from powercoder.datasets import generate, procedural
from powercoder.distillation.filter import _check_fit
from powercoder.inference.studies import run_study_trial

CASE: str = "ieee39"  # pandapower built-in: no data/ needed, and held out of every pool


def test_pool_and_held_out_networks_never_overlap() -> None:
    assert not set(procedural.POOL_NETWORKS) & set(procedural.HELD_OUT_NETWORKS)
    assert "snem-1803" in procedural.HELD_OUT_NETWORKS


@pytest.fixture(scope="module")
def n1_row() -> dict:
    elements = procedural.discover_load_scale_buses(CASE)
    line = procedural.safe_outages(CASE)[0]
    for i in range(20):
        row = generate._gen_fit_example("pf-load-scale-fit", CASE, elements, i, procedural.PROCEDURAL_SEED,
                                        generate.EndpointCache(), contingency_line=line)
        if row["lifecycle"]["status"] == "verified":
            return row
    pytest.skip("no verified N-1 fit drawn")


def test_an_n1_fit_is_checked_with_its_outage_applied(n1_row: dict) -> None:
    inputs = n1_row["task"]["inputs"]
    scale = n1_row["expected"]["structured"]["scale_factor"]
    passed, evidence, _ = _check_fit(n1_row, {"scale_factor": scale})
    assert passed and f"line {inputs['contingency_line']} out of service" in n1_row["task"]["prompt"]
    bus = int(inputs["element"].split()[-1])
    tool = run_study_trial(network_id=CASE, operation="load_scale", scale=scale, observation="bus_voltage",
                           observation_id=bus, max_iter=50, contingency_line=inputs["contingency_line"])
    intact = run_study_trial(network_id=CASE, operation="load_scale", scale=scale, observation="bus_voltage",
                             observation_id=bus, max_iter=50)
    assert evidence["metric"] == pytest.approx(tool.data["metric"], abs=1e-9)
    assert evidence["metric"] != pytest.approx(intact.data["metric"], abs=1e-9), "the outage must matter"


def test_a_free_text_prompt_states_every_quantity_the_fit_needs(n1_row: dict) -> None:
    inputs = n1_row["task"]["inputs"]
    for template in procedural.FREE_TEXT_TEMPLATES:
        prompt = procedural.free_text(n1_row, template)
        for needed in (CASE, f"line {inputs['contingency_line']}", inputs["element"].split()[-1],
                       f"{inputs['target']:.6f}", str(inputs["tolerance"]), str(inputs["scale_lo"]), str(inputs["scale_hi"])):
            assert needed in prompt, (needed, prompt)
        assert re.search(r"\bevery load|all demand", prompt), "what is scaled must be explicit"
