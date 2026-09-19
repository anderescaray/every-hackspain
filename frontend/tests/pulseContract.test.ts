import assert from "node:assert/strict";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { companyDetailSchema } from "../types/companyDetail";
import { createRequire } from "node:module";
import partial from "./fixtures/pulse1084.json";
import { fixtureCompanies } from "./fixtures/companyDetails";

test("COMP_1084 mantiene Health/Debt desconocidos y los tres pilares disponibles", () => {
  const company = companyDetailSchema.parse(partial);
  assert.equal(company.company_id, "COMP_1084");
  assert.equal(company.status, "partial");
  assert.equal(company.health_score, null);
  assert.equal(company.dimensions.debt, null);
  assert.equal(company.dimensions.cash_generation, 0);
  assert.equal(company.dimensions.resilience, 0);
  assert.equal(company.dimensions.momentum, company.pulse.pillars.momentum.score);
  assert.equal(company.pulse.pillars.debt_obligations.evidence_status, "unknown");
  assert.equal(company.pulse.contributions.debt_obligations, null);
  assert.deepEqual(company.pulse.missing_components, ["debt_obligations"]);
  assert.equal(company.pulse.known_weight, 0.8);
  for (const replacement of [0, 50, 100]) {
    assert.equal(companyDetailSchema.safeParse({ ...company, health_score: replacement }).success, false);
    assert.equal(companyDetailSchema.safeParse({ ...company, dimensions: { ...company.dimensions, debt: replacement } }).success, false);
  }
});

test("la forma pública no permite tratar ausencia total de historia como score parcial conocido", () => {
  const company = companyDetailSchema.parse(structuredClone(partial));
  company.status = "insufficient_evidence";
  company.pulse.status = "partial"; // Original engine status remains intact.
  company.dimensions = { momentum: null, cash_generation: null, resilience: null, debt: null };
  company.pulse.missing_components = ["generation", "momentum", "resilience", "debt_obligations"];
  company.pulse.known_weight = 0;
  company.pulse.health_min = 0;
  company.pulse.health_max = 100;
  for (const key of ["generation", "momentum", "resilience", "debt_obligations"] as const) {
    company.pulse.pillars[key].score = null;
    company.pulse.pillars[key].health_contribution = null;
    company.pulse.contributions[key] = null;
  }
  assert.equal(companyDetailSchema.parse(company).health_score, null);
});

test("rechaza Cash Truth ajeno y modelos heredados aunque haya Health numérico", () => {
  const company = fixtureCompanies.COMP_0356;
  assert.equal(companyDetailSchema.safeParse({ ...company, canonical_cash_truth: { ...company.canonical_cash_truth, currency: "USD" } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, pulse: { ...company.pulse, score_version: "financial_smoothed_v2" } }).success, false);
});

test("el gráfico no convierte una observación nula en punto cero", async () => {
  // Node does not load CSS modules; this check asserts markup, not styles.
  const require = createRequire(import.meta.url);
  const previous = require.extensions[".css"];
  require.extensions[".css"] = (module) => { module.exports = {}; };
  const { TrajectoryChart } = await import("../components/insights/TrajectoryChart");
  if (previous) require.extensions[".css"] = previous; else delete require.extensions[".css"];
  const markup = renderToStaticMarkup(createElement(TrajectoryChart, { history: [{ month: "2026-08-31", health_score: null }], trajectory: null }));
  assert.match(markup, /No hay Health Score identificado/);
  assert.doesNotMatch(markup, /<polyline|<circle/);
});
