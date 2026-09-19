"""Pulse-only presentation export: immutable source → one atomic web snapshot.

No score is calculated, rounded, substituted or fitted here. Legacy V2 export
is available only in ``legacy_frontend_export`` for explicit research use.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from xray.artifacts import check_output_path, recursive_hashes, sha256, verify_run
from xray.paths import ROOT
from xray.pulse.contracts import PILLARS

FRONTEND_GENERATED = ROOT / "frontend" / "public" / "generated"
METHOD = "PulseFourPillars-v1.0.1"
SUPPORTED_METHODS = {"PulseFourPillars-v1.0": "pulse-config-v1", METHOD: "pulse-config-v1.0.1"}
COMPLETE_STATUSES = {"complete", "complete_verified", "complete_bounded"}
EXPORTER_VERSION = "pulse-frontend-v1.1"
ALIASES = {"momentum": "momentum", "cash_generation": "generation",
           "resilience": "resilience", "debt": "debt_obligations"}
VERSIONS = ("score_version", "classification_version", "cleaning_version", "facts_version", "config_version")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _load(path: Path) -> dict[str, Any]:
    def invalid(value: str) -> None:
        raise ValueError(f"Nonfinite JSON number: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(value) + "\n", encoding="utf-8")


def _identifier(value: str, kind: str) -> str:
    if not re.fullmatch(rf"{kind}_\d{{4,10}}", value):
        raise ValueError(f"Invalid {kind} identifier: {value!r}")
    return value


@dataclass(frozen=True)
class WebEnvelope:
    run_id: str
    snapshot_id: str
    score_version: str
    classification_version: str
    cleaning_version: str
    facts_version: str
    config_version: str
    as_of: str
    currency: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _validate_score(score: dict[str, Any], cash: dict[str, Any], envelope: WebEnvelope) -> None:
    """Integrity assertions only; never manufacture or replace engine values."""
    method = score.get("score_version")
    if method not in SUPPORTED_METHODS or score.get("schema_version") != "1.0":
        raise ValueError("Only registered PulseFourPillars contracts are supported; no legacy fallback")
    if score.get("config_version") != SUPPORTED_METHODS[method]:
        raise ValueError("Score methodology and configuration version disagree")
    for key, expected in envelope.to_dict().items():
        if key != "snapshot_id" and score.get(key) != expected:
            raise ValueError(f"Mixed score provenance: {key}")
    for key in ("company_id", "currency", "as_of", "classification_version", "facts_version"):
        if cash.get(key) != score.get(key):
            raise ValueError(f"Cash Truth and score disagree: {key}")
    if cash.get("schema_version") != "1.0":
        raise ValueError("Unsupported canonical Cash Truth schema")
    if set(score.get("pillars", {})) != set(PILLARS):
        raise ValueError("Pulse requires exactly four pillar results")
    missing = []
    contributions = []
    for name in PILLARS:
        pillar = score["pillars"][name]
        value, weight, contribution = pillar["score"], pillar["weight"], pillar["health_contribution"]
        if not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("Invalid source weight")
        if score["contributions"].get(name) != contribution:
            raise ValueError("Source contribution breakdown disagrees")
        if value is None:
            missing.append(name)
            if contribution is not None:
                raise ValueError("Missing pillar must have a null contribution")
        else:
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("Invalid source score")
            if contribution is None or not math.isclose(value * weight, contribution, rel_tol=0, abs_tol=1e-10):
                raise ValueError("Source weighted contribution does not reconcile")
            contributions.append(contribution)
    if set(missing) != set(score["missing_components"]):
        raise ValueError("Missing component metadata disagrees")
    health = score["health"]
    if missing:
        allowed = {"partial", "insufficient_evidence"} if method == METHOD else {"partial"}
        if health is not None or score["status"] not in allowed:
            raise ValueError("Incomplete Pulse evidence cannot supply Health")
    elif health is None or score["status"] not in (
        {"complete_verified", "complete_bounded"} if method == METHOD else {"complete"}
    ) or not math.isclose(
        math.fsum(contributions), health, rel_tol=0, abs_tol=1e-10
    ):
        raise ValueError("Complete source Health does not reconcile")
    if method == METHOD:
        _validate_bounded_contract(score)
    elif score["pillars"]["debt_obligations"].get("evidence_status") == "bounded":
        raise ValueError("Historical v1.0 cannot contain bounded Debt")
    # Check every nested value, including features and robustness, is finite JSON.
    _json(score)
    _json(cash)


def _validate_bounded_contract(score: dict[str, Any]) -> None:
    """Validate supplied identification bounds, never derive a replacement score."""
    debt = score["pillars"]["debt_obligations"]
    required = {"identified_score", "score_range", "score_range_width", "score_estimation", "reason",
                "identified_service", "service_bounds", "service_absence_verified", "uncertainty", "evidence_status"}
    if not required <= debt.keys() or not {"health_evidence", "identified_range"} <= score.keys():
        raise ValueError("Missing bounded Debt contract fields")
    if not {"debt_principal_paid", "debt_interest_paid", "verified_financing_fees", "debt_service_paid",
            "observed_months", "required_months", "history_complete"} <= debt["identified_service"].keys():
        raise ValueError("Missing identified service breakdown")
    if not {"debt_possible_uncertain_outflows", "debt_impossible_uncertain_outflows",
            "debt_unresolved_uncertain_outflows", "potentially_financial_uncertain_outflows", "version"} <= debt["uncertainty"].keys():
        raise ValueError("Missing Debt uncertainty breakdown")
    if debt["uncertainty"]["version"] != "debt-uncertainty-v1":
        raise ValueError("Unsupported Debt uncertainty evidence version")
    status = debt["evidence_status"]
    if status not in {"verified", "bounded", "partial", "unknown"} or debt["reason"] != debt["evidence_reason"]:
        raise ValueError("Invalid bounded Debt evidence")
    interval = debt["score_range"]
    lo, hi = interval["min"], interval["max"]
    if (lo is None) != (hi is None) or (lo is not None and not 0 <= lo <= hi <= 100):
        raise ValueError("Invalid Debt identification range")
    if debt["score"] is not None and (lo is None or not lo <= debt["score"] <= hi):
        raise ValueError("Debt point is outside its identification range")
    if status == "bounded" and (debt["score"] is None or debt["score_estimation"] != "bounded_midpoint"):
        raise ValueError("Bounded Debt must retain its point estimation provenance")
    if status == "verified" and (debt["score"] is None or debt["score_estimation"] != "identified"):
        raise ValueError("Verified Debt must retain its identified score")
    if status in {"unknown", "partial"} and debt["score"] is not None:
        raise ValueError("Unidentified Debt cannot supply a point score")
    if debt["service_absence_verified"] is not False:
        raise ValueError("This method cannot certify absence of debt service")
    expected_evidence = {"complete_verified": "verified", "complete_bounded": "bounded",
                         "partial": "partial", "insufficient_evidence": "unknown"}[score["status"]]
    if score["health_evidence"] != expected_evidence:
        raise ValueError("Health evidence disagrees with identification status")
    if score["status"] in {"complete_verified", "complete_bounded"} and status != expected_evidence:
        raise ValueError("Complete Health must preserve Debt evidence status")
    identified = score["identified_range"]
    if identified is not None:
        if identified["kind"] != "identification_bounds_not_confidence_interval" or not 0 <= identified["min"] <= identified["max"] <= 100:
            raise ValueError("Invalid Health identification range")
        if score["health"] is not None and not identified["min"] <= score["health"] <= identified["max"]:
            raise ValueError("Health point is outside its identification range")
        if score["health"] is not None and (identified["min"] != score["health_min"] or identified["max"] != score["health_max"]):
            raise ValueError("Complete Health bounds disagree with supplied identification range")
    elif score["health"] is not None:
        raise ValueError("Identified Health requires supplied identification bounds")


def _identification_fields(score: dict[str, Any]) -> dict[str, Any]:
    # Historical v1.0 has no bounded contract: retain that absence explicitly.
    return {key: score[key] for key in ("identified_range", "health_evidence") if key in score}


def _status(score: dict[str, Any]) -> str:
    if all(score["pillars"][name]["score"] is None for name in PILLARS):
        return "insufficient_evidence"
    return score["status"]


def _dimensions(score: dict[str, Any]) -> dict[str, float | None]:
    return {alias: score["pillars"][name]["score"] for alias, name in ALIASES.items()}


def _cash_view(cash: dict[str, Any]) -> dict[str, Any]:
    """Display grouping of canonical classes, not an economic reclassification."""
    classes = {row["economic_class"]: row for row in cash["classes"]}
    summary, evidence = cash["summary"], cash["evidence"]
    period = f"{evidence['window_start']} – {evidence['window_end']}"
    groups = {
        "operating": ("operating",), "circulation": ("own_account_circulation",),
        "support": ("group_or_internal",),
        "uncertain": ("external_financing", "debt_service", "investment", "uncertain"),
    }
    labels = {"operating": "Generación operativa identificada", "circulation": "Circulación propia observada",
              "support": "Flujos candidatos intragrupo", "uncertain": "Otros flujos no operativos y no identificados"}
    explanations = {
        "operating": "Neto operativo del Cash Truth canónico; excluye financiación, servicio de deuda y circulación propia.",
        "circulation": "Clasificación canónica de circulación propia. Sin evidencia explícita de ambos tramos no se afirma emparejamiento ni neto cero.",
        "support": "Flujos candidatos internos o de grupo; no acreditan por sí solos apoyo financiero ni libre disponibilidad de caja.",
        "uncertain": "Agrupa para esta vista financiación externa, servicio de deuda, inversión y movimientos inciertos. Las clases y sus importes se conservan por separado en canonical_cash_truth; no todos son desconocidos.",
    }
    components: list[dict[str, Any]] = []
    for category, names in groups.items():
        gross = math.fsum(classes[name]["amount_abs"] for name in names if name in classes)
        net = summary["net_operating_cash"] if category == "operating" else None
        if category in ("support", "circulation") and gross == 0:
            net = 0.0
        components.append({"category": category, "label": labels[category], "gross_movement": gross,
                           "net_amount": net, "explanation": explanations[category], "confidence": None, "evidence_refs": []})
    return {"period": period, "total_gross_movement": math.fsum(c["gross_movement"] for c in components),
            "apparent_net": summary["eligible_net_cash"], "own_account_circulation": None,
            "account_flows": None, "components": components,
            "headline": "Flujos observados según el Cash Truth canónico.",
            "explanation": "Caja operativa, circulación y otros flujos separados; no es saldo bancario, solvencia ni prueba de apoyo confirmado.",
            "confidence": None, "evidence_refs": [],
            "evidence_summary": [f"{cash['coverage']['transaction_count']} movimientos observados; detalle por transaction_id en el ledger del run."],
            "correction": None, "comparison": None}


def company_detail(score: dict[str, Any], cash: dict[str, Any], group_id: str | None,
                   envelope: WebEnvelope) -> dict[str, Any]:
    _validate_score(score, cash, envelope)
    status = _status(score)
    missing = ", ".join(score["missing_components"])
    assessment = "Health disponible" if status in COMPLETE_STATUSES else "Health no evaluable · evidencia parcial"
    if status == "complete_bounded":
        assessment = "Health identificado con incertidumbre acotada"
    if status == "insufficient_evidence":
        assessment = "Evidencia insuficiente para evaluar los pilares"
    reason = f"Componentes no evaluables: {missing}." if missing else "Los cuatro pilares están identificados."
    if status == "complete_bounded":
        reason = "Deuda y Health incluyen una estimación acotada; el intervalo identifica la incertidumbre observada."
    direction = score["direction"] if score["direction"] in {"improving", "deteriorating", "stable"} else None
    period = f"Seis meses completos hasta {score['as_of']}"
    return {"schema_version": "3.0", "source": "generated", **envelope.to_dict(),
            "company_id": _identifier(score["company_id"], "COMP"), "group_id": group_id,
            "status": status, "health_score": score["health"], "dimensions": _dimensions(score),
            "health_score_model": {"version": score["score_version"], "provisional": status not in {"complete", "complete_verified"},
                                   "weights": {alias: score["pillars"][name]["weight"] for alias, name in ALIASES.items()}},
            "assessment": assessment, "confidence": None, "trajectory": direction,
            "summary": f"{reason} Diagnóstico de caja y alerta temprana, no probabilidad de impago. Momentum es nowcast, no forecast.",
            "history": [{"month": score["as_of"], "health_score": score["health"]}],
            "drivers_period": period, "drivers": [], "cash_truth": _cash_view(cash),
            "time_borrowed": {"ar": None, "ap": None}, "alerts": [], "evidence": [],
            "simulation": {"inputs": [], "scenarios": [], "example_id": None,
                           "methodology": "No hay escenarios publicados para este run Pulse. No se simulan puntuaciones en la interfaz."},
            "pulse": score, "canonical_cash_truth": cash}


def portfolio_export(details: dict[str, dict[str, Any]], envelope: WebEnvelope) -> dict[str, Any]:
    items = []
    for cid, detail in sorted(details.items()):
        score = detail["pulse"]
        change = score.get("change", {})
        missing = score["missing_components"]
        items.append({"company_id": cid, "group_id": detail["group_id"], "run_id": envelope.run_id,
                      **_identification_fields(score),
                      "health_score": score["health"], "dimensions": detail["dimensions"],
                      "delta_vs_prev": change.get("delta") if change.get("comparable_to_previous") else None,
                      "trajectory": detail["trajectory"], "trajectory_stage": None, "confidence": None,
                      "score_status": detail["status"], "status_reason": ", ".join(missing) if missing else None,
                      "missing_components": missing, "robustness": score.get("robustness", {}).get("level", "indeterminate"),
                      "main_signal": detail["assessment"], "main_signal_impact": None,
                      "support_dependency_ratio": None, "attention": "unknown", "has_detail": True})
    return {"schema_version": "2.0", "source": "generated", **envelope.to_dict(),
            "period": f"Seis meses completos hasta {envelope.as_of}",
            "summary": f"{len(items)} empresas observadas en {envelope.currency}; incluye evidencia parcial. Fuente única: {envelope.score_version}.",
            "items": items}


def group_detail(group_id: str, details: list[dict[str, Any]], envelope: WebEnvelope) -> dict[str, Any]:
    def metric(label: str) -> dict[str, Any]:
        return {"value": None, "covered_company_ids": [], "explanation": f"{label}: no existe una posición consolidada identificada en este run.", "evidence_refs": []}
    members = []
    for detail in sorted(details, key=lambda value: value["company_id"]):
        members.append({"company_id": detail["company_id"], "health_score": detail["health_score"],
                        **_identification_fields(detail["pulse"]),
                        "dimensions": detail["dimensions"], "score_status": detail["status"],
                        "missing_components": detail["pulse"]["missing_components"], "trajectory": detail["trajectory"],
                        "role": "unknown", "available_liquidity": None, "identified_debt": None, "obligations_due": None,
                        "cash_generation_net": detail["canonical_cash_truth"]["summary"]["net_operating_cash"],
                        "internal_received": None, "internal_provided": None, "confidence": None, "attention": "unknown",
                        "summary": detail["assessment"], "outlook": {"status": "insufficient", "horizon": "No disponible",
                        "summary": "Este run contiene diagnóstico observado, no pronóstico de necesidades futuras.",
                        "funding_need": None, "confidence": None, "evidence_refs": []}, "evidence_refs": []})
    return {"schema_version": "2.0", "source": "generated", **envelope.to_dict(),
            "group_id": _identifier(group_id, "GROUP"), "health_score": None, "status": "insufficient_evidence",
            "period": f"Seis meses completos hasta {envelope.as_of}",
            "summary": f"{len(members)} sociedades observadas. No se calcula ni promedia un Health Score de grupo.",
            "coverage": {"known_company_count": None, "confidence": None, "explanation": "Perímetro observado en la moneda de esta vista, no perímetro jurídico completo."},
            "available_liquidity": metric("Liquidez disponible"), "identified_debt": metric("Deuda contractual"),
            "obligations": {**metric("Obligaciones futuras"), "horizon": "No evaluable"},
            "limitations": ["Sin Health Score de grupo; no se promedian empresas.", "No se presume caja fungible ni apoyo confirmado.",
                            "Sólo sociedades con un panel en la moneda explícita de esta vista."],
            "members": members, "insights": [], "alerts": [], "concentration": [], "recent_changes": [],
            "relations": [], "recommendations": [], "evidence": []}


def _safe_destination(root: Path) -> None:
    for path in (root, *root.parents, root / "snapshots", root / "current.json", root / ".publish.lock"):
        if path.is_symlink():
            raise ValueError(f"Symbolic publication path: {path}")


def _verify_snapshot(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Symbolic snapshot path")
    manifest = _load(path / "manifest.json")
    if recursive_hashes(path, exclude=("manifest.json",)) != manifest["outputs_sha256"]:
        raise ValueError("Web snapshot integrity failure")
    return manifest


def _publish(staged: Path, root: Path, manifest: dict[str, Any]) -> Path:
    _safe_destination(root)
    snapshots = root / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    snapshot_id = manifest["snapshot_id"]
    if not re.fullmatch(r"web-[a-f0-9]{64}", snapshot_id):
        raise ValueError("Invalid snapshot identity")
    target = snapshots / snapshot_id
    descriptor = os.open(root / ".publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        pointer_tmp = root / f".current-{uuid4().hex}.tmp"
        try:
            _safe_destination(root)
            _verify_snapshot(staged)
            if target.exists() or target.is_symlink():
                _verify_snapshot(target)
                if recursive_hashes(target) != recursive_hashes(staged):
                    raise ValueError("Immutable web snapshot conflict")
            else:
                os.rename(staged, target)
            keys = ("run_id", "snapshot_id", *VERSIONS, "as_of", "currency")
            pointer = {"schema_version": "1.0", **{key: manifest[key] for key in keys},
                       "manifest_sha256": sha256(target / "manifest.json")}
            with pointer_tmp.open("x", encoding="utf-8") as stream:
                stream.write(_json(pointer) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pointer_tmp, root / "current.json")
        finally:
            pointer_tmp.unlink(missing_ok=True)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return target


def run(run_dir: Path, out_dir: Path = FRONTEND_GENERATED, *, currency: str = "EUR",
        verbose: bool = True) -> dict[str, Any]:
    if currency != "EUR":
        raise ValueError("This web contract is an explicit EUR view; no FX consolidation or currency relabelling")
    run_dir, out_dir = Path(run_dir).absolute(), Path(out_dir).absolute()
    check_output_path(out_dir, run_dir)
    _safe_destination(out_dir)
    source = verify_run(run_dir)
    source_hash = sha256(run_dir / "manifest.json")
    if source.get("versions", {}).get("score_version") not in SUPPORTED_METHODS:
        raise ValueError("A verified registered PulseFourPillars run is required; legacy export is research-only")
    version_fields = {key: source["versions"][key] for key in VERSIONS}
    identity = {"source_manifest_sha256": source_hash, "exporter_sha256": sha256(Path(__file__)),
                "export_dependencies_sha256": {"artifacts.py": sha256(Path(__file__).parents[1] / "artifacts.py"),
                                               "pulse/contracts.py": sha256(Path(__file__).parents[1] / "pulse" / "contracts.py")},
                "exporter_version": EXPORTER_VERSION, "currency": currency, "schemas": ["3.0", "2.0", "2.0"]}
    snapshot_id = "web-" + hashlib.sha256(_json(identity).encode()).hexdigest()
    envelope = WebEnvelope(run_id=source["run_id"], snapshot_id=snapshot_id,
                           as_of=source["as_of"], currency=currency, **version_fields)
    catalog = pd.read_parquet(run_dir / "cleaned" / "companies.parquet", columns=["company_id", "group_id"])
    if catalog.company_id.duplicated().any():
        raise ValueError("Company catalog must be unique")
    groups_by_company = {row.company_id: None if pd.isna(row.group_id) else _identifier(str(row.group_id), "GROUP")
                         for row in catalog.itertuples(index=False)}
    details: dict[str, dict[str, Any]] = {}
    excluded = []
    for path in sorted((run_dir / "companies").glob("*/*/score.json")):
        cid, panel_currency = path.parent.parent.name, path.parent.name
        _identifier(cid, "COMP")
        if cid not in source["companies"] or cid not in groups_by_company:
            raise ValueError("Source score is outside the declared company perimeter")
        if panel_currency != currency:
            excluded.append({"company_id": cid, "currency": panel_currency})
            continue
        score, cash = _load(path), _load(path.with_name("cash_truth.json"))
        if score.get("company_id") != cid:
            raise ValueError("Company identity disagrees with its source path")
        details[cid] = company_detail(score, cash, groups_by_company[cid], envelope)
    if not details:
        raise ValueError("No company panels in the requested currency; current web snapshot was not replaced")
    group_details: dict[str, list[dict[str, Any]]] = {}
    for detail in details.values():
        if detail["group_id"] is not None:
            group_details.setdefault(detail["group_id"], []).append(detail)
    counts = {"companies": len(details), "groups": len(group_details),
              "statuses": {status: sum(d["status"] == status for d in details.values())
                           for status in ("complete", "complete_verified", "complete_bounded", "partial", "insufficient_evidence")},
              "excluded_currency_panels": len(excluded)}
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pulse-web-", dir=out_dir) as directory:
        staged = Path(directory)
        _write(staged / "portfolio.json", portfolio_export(details, envelope))
        for cid, detail in details.items():
            _write(staged / "companies" / f"{cid}.json", detail)
        for gid, members in group_details.items():
            _write(staged / "groups" / f"{gid}.json", group_detail(gid, members, envelope))
        manifest = {"schema_version": "1.0", **envelope.to_dict(), **identity, "counts": counts,
                    "excluded_currency_panels": excluded,
                    "companies_without_export_currency": sorted(set(source["companies"]) - set(details)),
                    "outputs_sha256": recursive_hashes(staged)}
        _write(staged / "manifest.json", manifest)
        if sha256(run_dir / "manifest.json") != source_hash or verify_run(run_dir) != source:
            raise ValueError("Source run changed during export; current snapshot was not replaced")
        target = _publish(staged, out_dir, manifest)
    if verbose:
        print(f"{envelope.score_version}: {counts['companies']} empresas · {counts['groups']} grupos · {counts['statuses']} -> {target}")
    return manifest
