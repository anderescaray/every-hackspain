import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ActionabilitySection, selectActionLever } from "../components/insights/ActionabilitySection";
import { companyDetailSchema, type Actionability, type ActionLever } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

const treasury: ActionLever = {
  lever: "ap_on_time", type: "treasury", label: "Pagar antes a proveedores",
  level_before: 56.2, level_after: 63.1, health_before: 55.8, health_after: 62.7, delta_points: 6.9,
  cash_equivalent: 52000, source_grid_rel_change: 0.25,
  quantity: { label: "Retraso a proveedores", before: 27, after: 18, unit: "days", direction: "decrease" },
  resources: { kind: "liquidity", required: 52000, own_available: 31000, gap: 21000, currency: "EUR", feasibility: "requires_financing", scope: "selected_grid_scenario" },
  efficiency: { value: 1.35, unit: "level_points_per_10k", label: "Eficiencia de liquidez" },
  horizon: { k1_level_delta: 1.2, k6_level_delta: 6.9, full_effect_months: 6 },
  next_breakpoint: { available: true, quantity: 15, unit: "days" }, scenario_id: null,
};
const business: ActionLever = {
  ...treasury, lever: "cut_outflow", type: "business", label: "Reducir salidas",
  resources: null, efficiency: null, cash_equivalent: null, delta_points: 4.2,
};
const advisor: Actionability = {
  status: "available", reason: null, method: "company_sensitivity_v1", month: "2026-08-01",
  primary: treasury, alternatives: [business],
  next_band: { current_level: 56.2, target_level: 70, projected_level: 63.1, reachable_with_primary: false },
  structural_issue: false, assumptions: ["Cada palanca se evalúa aislada"],
  source: { method: "company_sensitivity_v1", inputs_sha256: { "company_monthly_scores.parquet": "a".repeat(64) } },
};

function render(value?: Actionability) { return renderToStaticMarkup(createElement(ActionabilitySection, { actionability: value })); }

test("contrato opcional acepta asesoría tipada y conserva nulos, sin afectar JSON anteriores", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  const parsed = companyDetailSchema.parse({ ...company, actionability: advisor });
  assert.equal(parsed.actionability?.primary?.scenario_id, null);
  assert.equal(parsed.actionability?.alternatives[0].efficiency, null);
  assert.equal(parsed.actionability?.primary?.health_after, 62.7);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, primary: { ...treasury, efficiency: { value: 1.35, unit: "health_points_per_10k", label: "Eficiencia de liquidez" } } } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, status: "no_actionable_lever" } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, primary: null } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, alternatives: [{ ...business, efficiency: { value: 1, unit: "level_points_per_10k", label: "Eficiencia de caja" }, lever: "raise_inflow" }] } }).success, false);
});

test("la lectura principal muestra Health suministrado, factibilidad y tramo de nivel", () => {
  const html = render(advisor);
  assert.match(html, /Qué puede mover tu Health/);
  assert.match(html, /Pagar antes a proveedores/);
  assert.match(html, /<span>56<\/span>/); // Health se redondea solo en presentación.
  assert.match(html, /63/);
  assert.match(html, /Faltan 21 mil €/);
  assert.match(html, /Eficiencia de liquidez · nivel/);
  assert.match(html, /\+1,35 pts \/ €10k/);
  assert.match(html, /Camino al siguiente tramo/);
  assert.match(html, /Objetivo/);
  assert.match(html, /href="#scenarios"/);
  assert.doesNotMatch(html, /health_points_per_10k/);
});

test("sensibilidad de negocio no se presenta como recomendación de tesorería ni inventa eficiencia", () => {
  const value: Actionability = { ...advisor, status: "business_sensitivity", primary: business, alternatives: [], structural_issue: true };
  const html = render(value);
  assert.match(html, /SENSIBILIDAD · NEGOCIO/);
  assert.match(html, /Problema principalmente operativo/);
  assert.match(html, /Negocio = sensibilidad, no recomendación/);
  assert.doesNotMatch(html, /€10k/);
});

test("sin datos o sin palanca útil conserva estado quieto y no simula ceros", () => {
  assert.match(render(), /Todavía no hay sensibilidades calculadas/);
  assert.match(render({ ...advisor, status: "no_actionable_lever", primary: null, alternatives: [], next_band: null }), /Ningún cambio aislado/);
  assert.doesNotMatch(render(), /actionability-primary-score/);
});

test("alternativa solo selecciona valores ya recibidos; no deriva delta, caja ni escenario", () => {
  const selected = selectActionLever(advisor, "cut_outflow");
  assert.equal(selected, business);
  assert.equal(selected?.delta_points, 4.2);
  assert.equal(selected?.efficiency, null);
  assert.equal(selectActionLever(advisor, "ap_on_time"), treasury);
  assert.equal(selectActionLever(advisor, null), treasury);
});

test("nulls de Health y liquidez no se convierten en cero", () => {
  const value: Actionability = { ...advisor, primary: { ...treasury, health_before: null, health_after: null, delta_points: null, resources: { ...treasury.resources!, own_available: null, gap: null, feasibility: "unknown" }, efficiency: null }, alternatives: [] };
  const html = render(value);
  assert.match(html, /Nivel · escenario a seis meses/);
  assert.match(html, /Liquidez no evaluable/);
  assert.doesNotMatch(html, /€10k/);
});
