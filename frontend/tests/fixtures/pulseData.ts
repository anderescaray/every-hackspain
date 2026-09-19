// Explicit synthetic contract fixtures, never imported by application code.
import type { CompanyDetail } from "../../types/companyDetail";
import type { PulseResult } from "../../types/pulse";
import values from "./pulseValues.json";

export const fixtureEnvelope = {
  snapshot_id: `web-${"a".repeat(64)}`,
  run_id: "pulse-explicit-contract-fixture",
  score_version: "PulseFourPillars-v1.0" as const,
  classification_version: "cash-truth-v1",
  cleaning_version: "cleaning-v1",
  facts_version: "monthly-facts-v1",
  config_version: "pulse-config-v1",
  as_of: "2026-08-31",
  currency: "EUR" as const,
};
export const fixtureWeights = { momentum: 0.15, cash_generation: 0.40, resilience: 0.25, debt: 0.20 };
export const fixtureModel = { version: fixtureEnvelope.score_version, provisional: false, weights: fixtureWeights };

export function fixturePulse(companyId: string, value: number): PulseResult {
  const data = values[String(value) as keyof typeof values];
  if (!data) throw new Error("Missing explicit precalculated fixture");
  const feature = (name: keyof typeof data.raw_features, formula: string) => ({ raw: data.raw_features[name], score: value, numerator: data.raw_features[name], denominator: 1, formula_id: formula, anchors: [], missing_reason: null });
  return {
    schema_version: "1.0", ...fixtureEnvelope, company_id: companyId,
    status: "complete", health: value, known_weight: 1, health_min: value, health_max: value,
    bounds_kind: "identification_bounds_not_confidence_interval", missing_components: [],
    pillars: {
      generation: { score: value, weight: 0.4, health_contribution: data.contributions.generation, features: { generation_ratio: feature("generation_ratio", "generation-net-over-outflows-v1") } },
      momentum: { score: value, weight: 0.15, health_contribution: data.contributions.momentum, features: { operating_net_trend: feature("operating_net_trend", "theil-sen-six-month-net-v1") } },
      resilience: { score: value, weight: 0.25, health_contribution: data.contributions.resilience, features: { operating_downside_ratio: feature("operating_downside_ratio", "observed-operating-downside-v1") } },
      debt_obligations: { score: value, weight: 0.2, health_contribution: data.contributions.debt_obligations, features: { observed_debt_service_burden: feature("observed_debt_service_burden", "observed-debt-service-pressure-v1") }, evidence_status: "verified" },
    },
    raw_features: data.raw_features,
    normalized_features: { generation_ratio: value, operating_net_trend: value, operating_downside_ratio: value, observed_debt_service_burden: value },
    contributions: data.contributions,
    confidence: { history_coverage: 1, classification_coverage: 1, uncertain_amount_share: 0, debt_evidence: { status: "verified" }, perimeter_consistency: "fixture", currency_consistency: { currency: "EUR" } },
    evidence: { source: "explicit_synthetic_fixture" }, lineage: { source: "explicit_synthetic_fixture" },
    robustness: { level: "not_tested" }, change: {}, critical_movements: [], flags: ["explicit_fixture"], direction: "stable",
  };
}

export function fixtureFields(companyId: string, health: number) {
  return {
    ...fixtureEnvelope, status: "complete" as const, pulse: fixturePulse(companyId, health),
    canonical_cash_truth: { schema_version: "1.0" as const, classification_version: "cash-truth-v1", facts_version: "monthly-facts-v1", company_id: companyId, currency: "EUR" as const, as_of: fixtureEnvelope.as_of, summary: {}, coverage: {}, classes: [], evidence: { source: "explicit_synthetic_fixture" }, critical_movements: [], flags: ["explicit_fixture"] },
  };
}
export function syncFixtureIdentity(company: CompanyDetail) {
  company.pulse.company_id = company.company_id;
  company.canonical_cash_truth.company_id = company.company_id;
  company.pulse.direction = company.trajectory ?? "unknown";
}
