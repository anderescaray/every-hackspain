import assert from "node:assert/strict";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";
import { portfolioSchema } from "../types/portfolio";
import { groupDetailSchema } from "../types/groupDetail";
import { pulseSchema } from "../types/pulse";
import { primaryPortfolioScore, sortItems } from "../lib/portfolioPresentation";
import historical from "./fixtures/pulseBounded.json";

const operatingContributions = { generation: 35.12345, momentum: 9.375, resilience: 31.25 };
const operatingHealth = 75.74844999999999;
const operatingWeights = { generation: 0.5, momentum: 0.1875, resilience: 0.3125 };
const compositionVersion = "operating-extended-health-v1";

function dualCompany() {
  const source = structuredClone(historical.company);
  const composition = {
    composition_version: compositionVersion,
    operating_health: operatingHealth,
    extended_health: source.pulse.health,
    health_level: "extended_bounded",
    insights_available: ["operating_health", "debt_obligations", "extended_health"],
    missing_modules: [],
    operating_contributions: operatingContributions,
    operating_weights: operatingWeights,
  };
  return {
    ...source, score_version: "PulseFourPillars-v1.1", config_version: "pulse-config-v1.1",
    health_score_model: { ...source.health_score_model, version: "PulseFourPillars-v1.1" },
    debt_obligations: source.pulse.pillars.debt_obligations,
    ...composition,
    pulse: { ...source.pulse, score_version: "PulseFourPillars-v1.1", config_version: "pulse-config-v1.1", ...composition },
  };
}

test("v1.1 conserva Operating y Extended distintos con Debt bounded y trazabilidad", () => {
  const company = companyDetailSchema.parse(dualCompany());
  assert.equal(company.operating_health, operatingHealth);
  assert.equal(company.extended_health, historical.company.pulse.health);
  assert.equal(company.health_score, company.extended_health, "alias histórico sólo de Extended");
  assert.equal(company.health_level, "extended_bounded");
  assert.equal(company.pulse.pillars.debt_obligations.evidence_status, "bounded");
  assert.deepEqual(company.pulse.identified_range, historical.company.pulse.identified_range);
  assert.equal(Object.values(operatingContributions).reduce((sum, value) => sum + value, 0), company.operating_health);
  assert.equal(Object.values(company.pulse.contributions).reduce<number>((sum, value) => sum + (value ?? 0), 0), company.extended_health);
});

test("Debt ausente deja Operating identificado y Extended null; no acepta fallback", () => {
  const complete = dualCompany();
  const debt = complete.pulse.pillars.debt_obligations;
  const known = complete.pulse.contributions.generation + complete.pulse.contributions.momentum + complete.pulse.contributions.resilience;
  const partial = {
    ...complete, status: "partial", health_score: null, extended_health: null, health_level: "operating_only",
    debt_obligations: { ...complete.debt_obligations, score: null, health_contribution: null, evidence_status: "partial",
      reason: "debt_uncertainty_material", evidence_reason: "debt_uncertainty_material", score_estimation: null,
      score_range: { min: 30, max: 90 }, score_range_width: 60 },
    dimensions: { ...complete.dimensions, debt: null },
    history: complete.history.map((point, index) => index === complete.history.length - 1 ? { ...point, health_score: null } : point),
    pulse: {
      ...complete.pulse, status: "partial", health: null, extended_health: null, health_level: "operating_only",
      health_evidence: "partial", identified_range: null, known_weight: 0.8, health_min: known, health_max: known + 20,
      missing_components: ["debt_obligations"], contributions: { ...complete.pulse.contributions, debt_obligations: null },
      pillars: { ...complete.pulse.pillars, debt_obligations: {
        ...debt, score: null, health_contribution: null, evidence_status: "partial", reason: "debt_uncertainty_material", evidence_reason: "debt_uncertainty_material",
        score_estimation: null, score_range: { min: 30, max: 90 }, score_range_width: 60,
      } },
    },
  };
  const parsed = companyDetailSchema.parse(partial);
  assert.equal(parsed.operating_health, operatingHealth);
  assert.equal(parsed.extended_health, null);
  assert.equal(parsed.health_score, null);
  assert.equal(parsed.pulse.pillars.debt_obligations.score, null);
  assert.equal(companyDetailSchema.safeParse({ ...partial, extended_health: historical.company.pulse.health }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...partial, operating_health: null }).success, false);
  const missingG = { ...partial.pulse, operating_health: null, extended_health: null, health_level: null,
    operating_contributions: { ...operatingContributions, generation: null }, missing_components: ["generation", "debt_obligations"],
    pillars: { ...partial.pulse.pillars, generation: { ...partial.pulse.pillars.generation, score: null, health_contribution: null } },
    contributions: { ...partial.pulse.contributions, generation: null },
  };
  assert.ok(pulseSchema.safeParse(missingG).success, "G/M/R faltante admite ambos scores null");
  assert.equal(pulseSchema.safeParse({ ...missingG, operating_health: operatingHealth }).success, false);
});

test("cartera v1.1 ordena por Operating incluso si Extended difiere o falta", () => {
  const base = structuredClone(historical.portfolio);
  const source = base.items[0];
  const first = { ...source, composition_version: compositionVersion, operating_health: operatingHealth,
    extended_health: source.health_score, health_level: "extended_bounded", insights_available: ["operating_health", "extended_health"], missing_modules: [] };
  const second = { ...first, company_id: "COMP_0001", operating_health: 80, extended_health: null, health_score: null,
    health_level: "operating_only", score_status: "partial", health_evidence: "partial", identified_range: null,
    dimensions: { ...first.dimensions, debt: null }, missing_components: ["debt_obligations"] };
  const portfolio = portfolioSchema.parse({ ...base, score_version: "PulseFourPillars-v1.1", config_version: "pulse-config-v1.1", composition_version: compositionVersion, items: [first, second] });
  assert.equal(primaryPortfolioScore(portfolio.items[1]), 80);
  assert.equal(portfolio.items[1].extended_health, null);
  assert.deepEqual(sortItems(portfolio.items, "health_score", "desc").map((item) => item.company_id), ["COMP_0001", source.company_id]);
});

test("grupo preserva scores individuales sin inventar Group Health", () => {
  const source = structuredClone(historical.group);
  const members = source.members.map((member) => ({ ...member, composition_version: compositionVersion,
    operating_health: operatingHealth, extended_health: member.health_score, health_level: "extended_bounded",
    insights_available: ["operating_health", "debt_obligations", "extended_health"], missing_modules: [] }));
  const group = groupDetailSchema.parse({ ...source, score_version: "PulseFourPillars-v1.1",
    config_version: "pulse-config-v1.1", composition_version: compositionVersion, members });
  assert.equal(group.health_score, null);
  assert.equal(group.members[0].operating_health, operatingHealth);
  assert.equal(group.members[0].extended_health, historical.group.members[0].health_score);
});

test("la ficha v1.1 muestra Operating aunque Debt y Extended estén ausentes", async () => {
  const { createRequire } = await import("node:module");
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const require = createRequire(import.meta.url);
  const previous = require.extensions[".css"];
  require.extensions[".css"] = (module) => { module.exports = {}; };
  try {
    const { CompanyInsights } = await import("../components/insights/CompanyInsights");
    const complete = dualCompany();
    const partial = {
      ...complete, status: "partial", health_score: null, extended_health: null, health_level: "operating_only",
      debt_obligations: { ...complete.debt_obligations, score: null, health_contribution: null, evidence_status: "partial",
        reason: "debt_uncertainty_material", evidence_reason: "debt_uncertainty_material", score_estimation: null,
        score_range: { min: 30, max: 90 }, score_range_width: 60 },
      dimensions: { ...complete.dimensions, debt: null },
      history: complete.history.map((point, index) => index === complete.history.length - 1 ? { ...point, health_score: null } : point),
      pulse: { ...complete.pulse, status: "partial", health: null, extended_health: null, health_level: "operating_only",
        health_evidence: "partial", identified_range: null, missing_components: ["debt_obligations"],
        contributions: { ...complete.pulse.contributions, debt_obligations: null },
        pillars: { ...complete.pulse.pillars, debt_obligations: { ...complete.pulse.pillars.debt_obligations,
          score: null, health_contribution: null, evidence_status: "partial", reason: "debt_uncertainty_material",
          evidence_reason: "debt_uncertainty_material", score_estimation: null, score_range: { min: 30, max: 90 }, score_range_width: 60 } },
      },
    };
    const markup = renderToStaticMarkup(createElement(CompanyInsights, { company: companyDetailSchema.parse(partial) }));
    assert.match(markup, /Operating Health/);
    assert.match(markup, /Debt &amp; Obligations/);
    assert.match(markup, /No identificado/);
    assert.match(markup, /Extended Health/);
    assert.doesNotMatch(markup, /Health Score actual/);
  } finally {
    if (previous) require.extensions[".css"] = previous; else delete require.extensions[".css"];
  }
});
