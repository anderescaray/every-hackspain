"""Pipeline del advisor (WP5): publicación con staging y manifiesto, tablas, informe, papel en el grupo y anclaje."""
import json
from pathlib import Path

import pandas as pd
import pytest

from advisor_fixtures import make_group_state
from xray.artifacts import sha256
from xray.group_advisor import pipeline
from xray.group_advisor.config import AdvisorConfig
from xray.group_advisor.pipeline import (GROUP_SCHEMA, LEVER_SCHEMA, LIMITATIONS, STEP_SCHEMA, check_out_dir, default_config,
                                         group_context, run, run_from_states)
from xray.paths import PROCESSED_DIR

CONFIG = AdvisorConfig(fx_rates_to_eur={"EUR": 1.0, "USD": 1.17, "GBP": 0.86}, fx_source="approximate", fx_asof="2026-09-01")
H = CONFIG.horizon_months
HASHES = {"company_monthly_features.parquet": "a" * 64, "scores_v2/company_monthly_scores.parquet": "b" * 64}
REAL_DATA = (PROCESSED_DIR / "scores_v2").exists()
FLAT_FILES = ("advisor_steps.parquet", "advisor_groups.parquet", "sensitivity_levers.parquet", "_advisor_report.json", "_advisor_manifest.json")


def donor(cid, cash, currency="EUR", inflow=6e6, outflow=4e6):
    return {"company_id": cid, "currency": currency, "level_inflow_sum": inflow, "window_outflow_sum": outflow, "window_debt_service_sum": 0.,
            "tx_outflow_ma3": outflow / H, "reconstructed_cash": cash, "runway_months": 3.0}


def weak_recipient(cid, cash=1.2e4, runway=0.1, **extra):
    row = {"company_id": cid, "level_inflow_sum": 1e5, "window_outflow_sum": 1e5 * 1.25 / 0.75, "window_debt_service_sum": 3e4,
           "ap_delay_w": 30., "ap_delay_count_w": 8, "inv_ap_overdue_amount": 6e4, "inv_ap_due_30_amount": 3e4, "inv_ap_due_60_amount": 1.5e4,
           "reconstructed_cash": cash, "runway_months": runway, "tx_outflow_ma3": 1e5 * 1.25 / 0.75 / H}
    row.update(extra)
    return row


def synthetic_states():
    """Tres grupos: uno con plan (D1 y P, una acción cruzada USD→EUR), uno sin palancas y uno unipersonal."""
    buffer = 2 * (4e6 / H)
    with_plan = make_group_state([donor("COMP_0222", buffer + 4e4), donor("COMP_0415", buffer + 2e5, currency="USD"), weak_recipient("COMP_0738"),
                                  {"company_id": "COMP_0911", "currency": "EUR", "score_reason": "insufficient_window_history"}],
                                 config=CONFIG, group_id="GROUP_0064", consolidated_scores={"EUR": 63.5, "USD": 90.9})
    no_levers = make_group_state([{"company_id": "COMP_0301", "level_inflow_sum": 6e6, "window_outflow_sum": 4e6, "window_debt_service_sum": 0.,
                                   "tx_outflow_ma3": 4e6 / H},
                                  weak_recipient("COMP_0302", cash=9e4, runway=1.1, tx_outflow_ma3=1e5), weak_recipient("COMP_0303", cash=4e4, runway=0.5)],
                                 config=CONFIG, group_id="GROUP_0131", consolidated_scores={"EUR": 58.9})
    single = make_group_state([donor("COMP_0555", 9.5e4)], config=CONFIG, group_id="GROUP_0200", consolidated_scores={"EUR": 74.0})
    return [with_plan, no_levers, single]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    root = tmp_path_factory.mktemp("advisor")
    features_dir = root / "processed"
    features_dir.mkdir()
    out_dir = features_dir / "advisor"
    report = run_from_states(synthetic_states(), HASHES, CONFIG, out_dir, features_dir=features_dir, verbose=False)
    return {"root": root, "features_dir": features_dir, "out_dir": out_dir, "report": report}


# ---------------------------------------------------------------- ficheros, manifiesto, aislamiento


def test_publishes_every_file_of_the_contract(published):
    out = published["out_dir"]
    for name in FLAT_FILES:
        assert (out / name).is_file(), name
    for group_id in ("GROUP_0064", "GROUP_0131", "GROUP_0200"):
        assert (out / "group_plans" / f"{group_id}.json").is_file() and (out / "group_plans" / f"{group_id}.md").is_file()
    for company_id in ("COMP_0222", "COMP_0415", "COMP_0738", "COMP_0911", "COMP_0301", "COMP_0302", "COMP_0303", "COMP_0555"):
        assert (out / "company_sensitivity" / f"{company_id}.json").is_file() and (out / "company_sensitivity" / f"{company_id}.md").is_file()
    assert not list(out.glob(".staging-*")) and not (out / ".pipeline.lock").exists()


def test_manifest_has_input_output_hashes_code_config_and_fx(published):
    out = published["out_dir"]
    manifest = load(out / "_advisor_manifest.json")
    assert manifest["method"] == "treasury_advisor_v1" and manifest["inputs_sha256"] == HASHES
    outputs = manifest["outputs_sha256"]
    published_files = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and ".history" not in p.parts}
    assert set(outputs) == published_files - {"_advisor_manifest.json"}
    assert all(sha256(out / name) == digest for name, digest in outputs.items())
    assert manifest["fx"] == {"fx_rates_to_eur": CONFIG.fx_rates_to_eur, "fx_source": "approximate", "fx_asof": "2026-09-01"}
    assert manifest["config"]["fractions"] == list(CONFIG.fractions) and manifest["config"]["fx_rates_to_eur"] == CONFIG.fx_rates_to_eur
    assert "group_advisor" in manifest["code"] and "src/xray/group_advisor/pipeline.py" in manifest["code"]["group_advisor"]["source_sha256"]
    assert set(manifest["versions"]) == {"python", "pandas", "numpy"}


def test_nothing_is_written_outside_out_dir(published):
    root, features_dir, out = published["root"], published["features_dir"], published["out_dir"]
    outside = [p for p in root.rglob("*") if p not in (features_dir, out) and out not in p.parents]
    assert outside == []


def test_report_is_native_json_with_limitations_and_zero_grounding_failures(published):
    report = published["report"]
    saved = load(published["out_dir"] / "_advisor_report.json")
    assert saved == json.loads(json.dumps(report, allow_nan=False))
    assert report["month"] == "2026-08-01" and report["inputs_sha256"] == HASHES and report["limitations"] == list(LIMITATIONS)
    groups, companies = report["groups"], report["companies"]
    assert groups["total"] == 3 and groups["by_status"] == {"plan": 1, "no_feasible_levers": 1, "single_subsidiary": 1}
    assert groups["grounding_failures"] == 0 and companies["grounding_failures"] == 0
    assert groups["plans"]["count"] == 1 and groups["plans"]["steps_total"] == sum(groups["plans"]["steps_by_lever"].values()) >= 2
    assert groups["plans"]["delta_utility_k6"]["count"] == 1 and groups["plans"]["delta_utility_k6"]["max"] > 0
    assert groups["plans"]["cash_committed_reporting_ccy"]["total"] == pytest.approx(sum(groups["plans"]["cash_committed_reporting_ccy"]["by_lever"].values()))
    assert groups["reasons"] and all(isinstance(v, int) for v in groups["reasons"].values())
    assert companies["total"] == 8 and companies["scored"] == 7 and companies["not_scored"] == 1
    assert companies["with_any_lever"] == 7 and set(companies["top_lever_by_pct_by_tramo"]) == {"red", "amber", "green"}
    assert companies["reachable_next_tramo"] >= 1 and set(companies["rel_change_needed_by_lever"]) >= {"cut_outflow", "ap_on_time"}
    for key in ("generated_at", "config", "timings"):
        assert key in report


# ---------------------------------------------------------------- tablas


def test_parquet_tables_follow_schema_and_plan(published):
    out = published["out_dir"]
    plan = load(out / "group_plans" / "GROUP_0064.json")
    steps = pd.read_parquet(out / "advisor_steps.parquet")
    groups = pd.read_parquet(out / "advisor_groups.parquet")
    levers = pd.read_parquet(out / "sensitivity_levers.parquet")
    assert list(steps.columns) == list(STEP_SCHEMA) and list(groups.columns) == list(GROUP_SCHEMA) and list(levers.columns) == list(LEVER_SCHEMA)
    assert len(groups) == 3 and groups.group_id.tolist() == ["GROUP_0064", "GROUP_0131", "GROUP_0200"]
    assert groups.status.tolist() == ["plan", "no_feasible_levers", "single_subsidiary"] and groups.grounding_ok.all()
    row = groups.set_index("group_id").loc["GROUP_0064"]
    assert row.steps == len(plan["plan"]["steps"]) == len(steps) and steps.group_id.eq("GROUP_0064").all()
    assert row.utility_before == pytest.approx(plan["baseline"]["group_utility_0_100"])
    assert row.utility_after_k6 == pytest.approx(plan["plan"]["totals"][f"k{H}"]["group_utility_after"])
    assert row.cash_committed_reporting_ccy == pytest.approx(sum(s["amount"]["reporting_ccy"] for s in plan["plan"]["steps"]))
    for _, step in steps.iterrows():
        source = plan["plan"]["steps"][int(step.step) - 1]
        effect = source["effects"][f"k{H}"]
        assert step.lever == source["lever"] and step.donor == source["donor"] and step.recipient == source["recipient"]
        assert step.delta_utility_k6 == pytest.approx(effect["group_utility_after"] - effect["group_utility_before"])
        assert step.binding_constraints == "|".join(source["binding_constraints"])
    without_plan = groups.loc[groups.status.ne("plan")]
    assert without_plan.steps.eq(0).all() and without_plan.cash_committed_reporting_ccy.eq(0).all() and without_plan.greedy_gap.isna().all()
    assert (without_plan.utility_after_k6 == without_plan.utility_before).all()  # sin pasos los totales son el baseline
    assert set(levers.company_id) == {"COMP_0222", "COMP_0415", "COMP_0738", "COMP_0301", "COMP_0302", "COMP_0303", "COMP_0555"}
    assert levers.company_id.is_monotonic_increasing and levers.month.eq(pd.Timestamp("2026-08-01")).all()
    ap = levers.loc[levers.lever.eq("ap_on_time")].set_index("company_id")
    assert ap.loc["COMP_0738", "covered_by_group_plan"] == True and ap.loc["COMP_0302", "covered_by_group_plan"] == False  # noqa: E712
    assert levers.loc[levers.lever.ne("ap_on_time"), "covered_by_group_plan"].isna().all()


# ---------------------------------------------------------------- papel en el grupo y cobertura por el plan


def test_group_context_matches_plan_steps(published):
    out = published["out_dir"]
    plan = load(out / "group_plans" / "GROUP_0064.json")
    steps = plan["plan"]["steps"]
    donors = {s["donor"] for s in steps}
    assert "COMP_0738" in {s["recipient"] for s in steps} and any(s["lever"] == "P" and s["recipient"] == "COMP_0738" for s in steps)
    for donor_id in donors:
        sens = load(out / "company_sensitivity" / f"{donor_id}.json")
        assert sens["group_context"] == {"has_group_plan": True, "role": "donor",
                                         "steps": sorted(s["step"] for s in steps if s["donor"] == donor_id)}
    recipient = load(out / "company_sensitivity" / "COMP_0738.json")
    assert recipient["group_context"] == {"has_group_plan": True, "role": "recipient",
                                          "steps": sorted(s["step"] for s in steps if s["recipient"] == "COMP_0738")}
    ap = next(lv for lv in recipient["levers"] if lv["lever"] == "ap_on_time")
    assert ap["available"] and ap["feasibility"]["covered_by_group_plan"] is True
    assert all("covered_by_group_plan" not in lv.get("feasibility", {}) for lv in recipient["levers"] if lv["lever"] != "ap_on_time")
    not_scored = load(out / "company_sensitivity" / "COMP_0911.json")
    assert not_scored["status"] == "not_scored" and not_scored["group_context"] == {"has_group_plan": True, "role": "none", "steps": []}
    other = load(out / "company_sensitivity" / "COMP_0302.json")
    assert other["group_context"] == {"has_group_plan": False, "role": "none", "steps": []}
    assert next(lv for lv in other["levers"] if lv["lever"] == "ap_on_time")["feasibility"]["covered_by_group_plan"] is False
    assert (out / "company_sensitivity" / "COMP_0738.md").read_text(encoding="utf-8").count("## Papel en el grupo") == 1
    assert "## Papel en el grupo" not in (out / "company_sensitivity" / "COMP_0302.md").read_text(encoding="utf-8")
    assert all(load(out / "company_sensitivity" / f"{cid}.json")["generated_at"] == plan["generated_at"]
               for cid in ("COMP_0222", "COMP_0738", "COMP_0302"))


def test_group_context_role_when_company_donates_and_receives():
    plan = {"status": "plan", "plan": {"steps": [{"step": 1, "lever": "D1", "donor": "COMP_0001", "recipient": "COMP_0002"},
                                                 {"step": 2, "lever": "P", "donor": "COMP_0002", "recipient": "COMP_0003"}]}}
    assert group_context(plan, "COMP_0001") == {"has_group_plan": True, "role": "donor", "steps": [1]}
    assert group_context(plan, "COMP_0002") == {"has_group_plan": True, "role": "both", "steps": [1, 2]}  # dona y recibe
    assert group_context(plan, "COMP_0003") == {"has_group_plan": True, "role": "recipient", "steps": [2]}
    assert group_context(plan, "COMP_0009") == {"has_group_plan": True, "role": "none", "steps": []}
    assert group_context({"status": "no_feasible_levers", "plan": {"steps": []}}, "COMP_0001") == {"has_group_plan": False, "role": "none", "steps": []}


# ---------------------------------------------------------------- rutas protegidas, republicación, run()


@pytest.mark.parametrize("target", ["scores_v2", "scores", "company_monthly_features.parquet", "."])
def test_rejects_output_overlapping_protected_inputs(tmp_path, target, monkeypatch):
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    out_dir = (features_dir / target).resolve()
    with pytest.raises(ValueError):
        check_out_dir(out_dir, features_dir)
    monkeypatch.setattr(pipeline, "load_inputs", lambda *a, **k: pytest.fail("no debe leer entradas con una salida inválida"))
    with pytest.raises(ValueError):
        run(features_dir, out_dir, CONFIG, verbose=False)
    with pytest.raises(ValueError):
        run_from_states(synthetic_states(), HASHES, CONFIG, out_dir, features_dir=features_dir, verbose=False)
    assert not out_dir.exists() or not any(out_dir.iterdir()) or target in (".",)


def test_republishing_backs_up_previous_outputs_and_stays_consistent(tmp_path):
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    out_dir = features_dir / "advisor"
    first = run_from_states(synthetic_states(), HASHES, CONFIG, out_dir, features_dir=features_dir, verbose=False)
    second = run_from_states(synthetic_states(), HASHES, CONFIG, out_dir, features_dir=features_dir, verbose=False)
    backups = list((out_dir / ".history").iterdir())
    assert backups and any((b / "group_plans" / "GROUP_0064.json").exists() for b in backups)
    manifest = load(out_dir / "_advisor_manifest.json")
    assert all(sha256(out_dir / name) == digest for name, digest in manifest["outputs_sha256"].items())
    strip = lambda r: {k: v for k, v in r.items() if k not in ("generated_at", "timings")}  # noqa: E731
    assert strip(first) == strip(second)
    first_plan = next(b for b in backups if (b / "group_plans").exists()) / "group_plans" / "GROUP_0064.json"
    keep = lambda d: {k: v for k, v in d.items() if k != "generated_at"}  # noqa: E731
    assert keep(load(first_plan)) == keep(load(out_dir / "group_plans" / "GROUP_0064.json"))  # determinista salvo la marca de tiempo


def test_run_loads_inputs_once_and_publishes_default_out_dir(tmp_path, monkeypatch):
    features_dir = tmp_path / "processed"
    features_dir.mkdir()
    calls = []

    class FakeInputs:
        inputs_sha256 = HASHES
        last_month = pd.Timestamp("2026-08-01")

    def fake_load_inputs(directory, config):
        calls.append((Path(directory), config))
        return FakeInputs()

    def fake_iter(inputs, month, config):
        assert isinstance(inputs, FakeInputs) and month == pd.Timestamp("2026-08-01")
        yield from synthetic_states()

    monkeypatch.setattr(pipeline, "load_inputs", fake_load_inputs)
    monkeypatch.setattr(pipeline, "iter_group_states", fake_iter)
    report = run(features_dir, config=CONFIG, verbose=False)
    assert len(calls) == 1 and calls[0] == (features_dir, CONFIG)
    assert (features_dir / "advisor" / "_advisor_report.json").exists() and report["month"] == "2026-08-01"
    assert report["groups"]["grounding_failures"] == 0 and report["companies"]["grounding_failures"] == 0
    assert "load_inputs_s" in report["timings"] and report["inputs_sha256"] == HASHES


def test_default_config_carries_fx_table():
    config = default_config()
    assert config.fx_rates_to_eur["EUR"] == 1.0 and config.fx_source and config.fx_asof and config.month is None
    assert default_config(month="2026-08-01").month == "2026-08-01"


# ---------------------------------------------------------------- datos reales


@pytest.mark.skipif(not REAL_DATA, reason="Sin data/processed/scores_v2 en esta máquina")
def test_real_pipeline_publishes_250_groups_without_grounding_failures():
    out_dir = PROCESSED_DIR / "advisor"
    report = run(PROCESSED_DIR, out_dir, verbose=False)
    assert report["groups"]["total"] == 250 and report["groups"]["grounding_failures"] == 0
    assert report["companies"]["grounding_failures"] == 0 and report["companies"]["scored"] > 0
    groups = pd.read_parquet(out_dir / "advisor_groups.parquet")
    levers = pd.read_parquet(out_dir / "sensitivity_levers.parquet")
    assert len(groups) == 250 and groups.grounding_ok.all() and not levers.empty
    assert {status: int(groups.status.eq(status).sum()) for status in report["groups"]["by_status"]} == report["groups"]["by_status"]
    manifest = load(out_dir / "_advisor_manifest.json")
    assert manifest["inputs_sha256"] == report["inputs_sha256"] and "company_monthly_features.parquet" in manifest["inputs_sha256"]
    assert all(sha256(out_dir / name) == digest for name, digest in manifest["outputs_sha256"].items())
    assert sorted(p.stem for p in (out_dir / "group_plans").glob("*.json")) == sorted(groups.group_id)
