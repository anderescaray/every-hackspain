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
  change_description: "Reducir el retraso un 25 %", required_change: { absolute: 9, relative_pct: 25, unit: "days" },
  quantity: { label: "Retraso a proveedores", before: 27, after: 18, unit: "days", direction: "decrease" },
  resources: { kind: "liquidity", required: 52000, own_available: 31000, gap: 21000, currency: "EUR", feasibility: "requires_financing", scope: "selected_grid_scenario" },
  efficiency: { value: 1.35, unit: "level_points_per_10k", label: "Eficiencia de liquidez" },
  horizon: { k1_level_delta: 1.2, k6_level_delta: 6.9, full_effect_months: 6 },
  next_breakpoint: { available: true, quantity: 15, unit: "days" }, scenario_id: null,
};
const otherTreasury: ActionLever = { ...treasury, lever: "ar_faster", label: "Cobrar antes", change_description: "Cobrar un 25 % antes", resources: null, efficiency: null, cash_equivalent: null, delta_points: 4.8 };
const business: ActionLever = { ...treasury, lever: "cut_outflow", type: "business", label: "Reducir salidas", change_description: "Reducir salidas un 25 %", required_change: { absolute: 12000, relative_pct: 25, unit: "EUR" }, resources: null, efficiency: null, cash_equivalent: null, delta_points: 4.2 };
const advisor: Actionability = {
  status: "actionable_treasury", reason: null, method: "company_sensitivity_v1", month: "2026-08-01",
  primary: treasury, alternatives: [otherTreasury, business], treasury_actions: [treasury, otherTreasury], business_sensitivities: [business],
  next_band: { current_level: 56.2, target_level: 70, projected_level: 63.1, current_health: 55.8, projected_health: 62.7, target_health: 69.6, reachable_with_primary: false },
  band_basis: "level_v2",
  structural_issue: false, assumptions: ["Cada palanca se evalúa aislada"],
  source: { method: "company_sensitivity_v1", inputs_sha256: { "company_monthly_scores.parquet": "a".repeat(64) } },
};

function render(value?: Actionability) { return renderToStaticMarkup(createElement(ActionabilitySection, { actionability: value })); }

test("contrato opcional estricto acepta seis estados y rechaza primarios/eficiencias incompatibles", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  assert.equal(companyDetailSchema.parse({ ...company, actionability: advisor }).actionability?.primary?.health_after, 62.7);
  const top: Actionability = { ...advisor, status: "top_band_no_action", primary: null, alternatives: [], next_band: null };
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: top }).success, true);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, primary: null } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...top, primary: treasury } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, business_sensitivities: [{ ...business, efficiency: treasury.efficiency }] } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, actionability: { ...advisor, primary: { ...treasury, efficiency: { value: 1.35, unit: "health_points_per_10k", label: "Eficiencia de liquidez" } } } }).success, false);
});

test("tesorería explica causa→efecto Health y camino al siguiente tramo desde Health precalculado", () => {
  const html = render(advisor);
  assert.match(html, /TESORERÍA · CAMBIO EVALUADO/);
  assert.match(html, /Retraso a proveedores/);
  assert.match(html, /27 días/);
  assert.match(html, /18 días/);
  assert.match(html, /EFECTO MODELADO EN HEALTH/);
  assert.match(html, /<span>56<\/span>/);
  assert.match(html, /<strong>63<\/strong>/);
  assert.match(html, /\+6,9 pts/);
  assert.match(html, /Faltan 21 mil €/);
  assert.match(html, /\+1,35 pts \/ €10k/);
  assert.match(html, /Eficiencia de liquidez · nivel V2/);
  assert.match(html, /href="#stress-test"/);
  assert.match(html, /Camino al siguiente tramo/);
  assert.match(html, /Actual/);
  assert.match(html, /Objetivo/);
  assert.match(html, /Umbral de nivel V2 expresado en Health con Momentum fijo/);
  assert.doesNotMatch(html, /Nivel actual/);
});

test("alternativas muestran cambio necesario; negocio permanece secundario y no es la mejor palanca", () => {
  const html = render(advisor);
  assert.match(html, /Otras palancas de tesorería/);
  assert.match(html, /Cobrar un 25 % antes/);
  assert.match(html, /Sensibilidades de negocio/);
  assert.match(html, /Reducir salidas un 25 %/);
  assert.match(html, /Sensibilidad, no recomendación/);
  assert.doesNotMatch(html, /MEJOR PALANCA|Principal sensibilidad/);
});

test("solo sensibilidad de negocio y problema estructural no muestran hero financiero", () => {
  for (const status of ["business_sensitivity_only", "structural_issue"] as const) {
    const value: Actionability = { ...advisor, status, primary: business, alternatives: [], treasury_actions: [], business_sensitivities: [business] };
    const html = render(value);
    assert.match(html, /Sensibilidades de negocio/);
    assert.match(html, /Reducir salidas un 25 %/);
    assert.doesNotMatch(html, /actionability-primary-score|€10k|TESORERÍA · CAMBIO/);
    assert.match(html, status === "structural_issue" ? /Problema principalmente operativo/ : /Sin palanca de tesorería/);
  }
});

test("tramo superior, datos insuficientes y ausencia de impacto tienen estados distintos", () => {
  const noPrimary = { ...advisor, primary: null, alternatives: [], next_band: null };
  assert.match(render({ ...noPrimary, status: "top_band_no_action" }), /Sin siguiente tramo identificado/);
  assert.match(render({ ...noPrimary, status: "top_band_no_action" }), /nivel V2 ya está en su tramo superior/);
  assert.match(render({ ...noPrimary, status: "insufficient_data", treasury_actions: [], business_sensitivities: [] }), /Datos insuficientes/);
  assert.match(render({ ...noPrimary, status: "no_actionable_lever", treasury_actions: [], business_sensitivities: [] }), /No se identifica una palanca con impacto positivo/);
  assert.doesNotMatch(render({ ...noPrimary, status: "top_band_no_action" }), /actionability-primary-score/);
});

test("interacción solo selecciona una palanca de tesorería precalculada", () => {
  assert.equal(selectActionLever(advisor, "ar_faster"), otherTreasury);
  assert.equal(selectActionLever(advisor, "cut_outflow"), treasury);
  assert.equal(selectActionLever(advisor, null), treasury);
  assert.equal(selectActionLever({ ...advisor, status: "business_sensitivity_only", primary: business }, "ap_on_time"), null);
});

test("ausencia de Health, eficiencia y liquidez nunca se convierte en cero o Nivel", () => {
  const unknown: ActionLever = { ...treasury, health_before: null, health_after: null, delta_points: null, resources: { ...treasury.resources!, own_available: null, gap: null, feasibility: "unknown" }, efficiency: null };
  const html = render({ ...advisor, primary: unknown, treasury_actions: [unknown], alternatives: [] });
  assert.match(html, /Liquidez no evaluable/);
  assert.match(html, /<span>—<\/span>/);
  assert.doesNotMatch(html, /€10k/);
  assert.doesNotMatch(html, /Camino al siguiente tramo/);
  assert.doesNotMatch(render({ ...advisor, next_band: null }), /Camino al siguiente tramo/);
});
