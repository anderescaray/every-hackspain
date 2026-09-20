import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { StressTestSection, preferredObservedHorizon } from "../components/insights/StressTestSection";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";
import { fixtureStressTest } from "./fixtures/stressTest";
import { STRESS_DEMO_COMPANY_ID, STRESS_DEMO_SOURCE, isStressDemoCompany, stressDemoComp1122 } from "../fixtures/stressTestComp1122";

const html = (stressTest = fixtureStressTest, companyId?: string) => renderToStaticMarkup(createElement(StressTestSection, { stressTest, companyId }));

test("contrato opcional estricto acepta escenario observado y preserva resultados nulos", () => {
  const company = fixtureCompanies.COMP_0356;
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  assert.equal(companyDetailSchema.safeParse({ ...company, stress_test: { ...fixtureStressTest, as_of: "2026-07-31" } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, stress_test: { ...fixtureStressTest, scenarios: [fixtureStressTest.scenarios[0], fixtureStressTest.scenarios[0]] } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, stress_test: { ...fixtureStressTest, scenarios: [{ ...fixtureStressTest.scenarios[0], results: [{ ...fixtureStressTest.scenarios[0].results[0], status: "unavailable", health: 50 }] }] } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, stress_test: undefined }).success, true);
});

test("resultado y atribución proceden del JSON, sin sliders nativos ni horizontes futuros", () => {
  const rendered = html();
  assert.match(rendered, />Adverso</);
  assert.match(rendered, /data-testid="stress-health">54/);
  assert.match(rendered, /Qué explica el impacto/);
  assert.match(rendered, /Exposición sostenida/);
  assert.match(rendered, /1 mes 68/);
  assert.match(rendered, /Verde → Ámbar/);
  assert.match(rendered, /hipotético · no previsión/);
  assert.doesNotMatch(rendered, /type="range"|próximos 3 meses|pronóstico/);
});

test("factores condicionales y categorías aparecen solo si el contrato los trae", () => {
  const rendered = html();
  assert.match(rendered, /Personalizar stress/);
  assert.match(rendered, /Cliente principal · 31% de los cobros/);
  assert.match(rendered, /Nómina/);
  assert.match(rendered, /FX USD/);
  assert.match(rendered, /Antes de perder el tramo actual/);
  const emptyCustom = html({ ...fixtureStressTest, custom_factors: [], reverse_limits: [] });
  assert.doesNotMatch(emptyCustom, /Personalizar stress|Límite de resistencia/);
});

test("la ausencia de datos no genera Health y distingue motivos", () => {
  assert.match(renderToStaticMarkup(createElement(StressTestSection)), /Stress Test aún no disponible/);
  assert.match(renderToStaticMarkup(createElement(StressTestSection)), /Falta histórico comparable/);
  const noHealth = { ...fixtureStressTest, status: "insufficient_data" as const, reason: "v2_score_unavailable", baseline_health: null, baseline_band: null, default_scenario_id: null, custom_factors: [], reverse_limits: [], scenarios: [] };
  const rendered = html(noHealth);
  assert.match(rendered, /Stress Test no disponible/);
  assert.match(rendered, /El Health todavía no es calculable para este corte/);
  assert.doesNotMatch(rendered, /data-testid="stress-health"/);
  const history = html({ ...noHealth, reason: "insufficient_quality_months" });
  assert.match(history, /Stress Test aún no disponible/);
  assert.doesNotMatch(history, /no identificable/);
});

test("sin exposures avanzadas el módulo básico sigue renderizando Health", () => {
  const core = ["collections", "margin", "adverse", "operating_inflow:-10", "operating_outflow:+10"];
  const basic = {
    ...fixtureStressTest,
    default_scenario_id: "margin",
    custom_factors: fixtureStressTest.custom_factors.filter((factor) => factor.factor === "operating_inflow" || factor.factor === "operating_outflow"),
    reverse_limits: fixtureStressTest.reverse_limits.filter((item) => item.factor === "operating_inflow" || item.factor === "operating_outflow"),
    scenarios: fixtureStressTest.scenarios.filter((scenario) => core.includes(scenario.id)).map((scenario) => scenario.id === "collections"
      ? { ...scenario, shocks: [{ factor: "operating_inflow", relative_pct: -10, unit: "pct" as const }] }
      : scenario.id === "adverse"
        ? { ...scenario, shocks: scenario.shocks.filter((shock) => shock.factor === "operating_inflow" || shock.factor === "operating_outflow") }
        : scenario),
  };
  const rendered = html(basic);
  assert.match(rendered, /data-testid="stress-health">60/);
  assert.match(rendered, />Margen</);
  assert.doesNotMatch(rendered, /Cliente principal|FX USD|>Financiación</);
});

test("horizonte inicial elige solo un resultado ya calculado", () => {
  assert.equal(preferredObservedHorizon(fixtureStressTest.scenarios.find((scenario) => scenario.id === "adverse") ?? null), 6);
  const threeMissing = { ...fixtureStressTest.scenarios[0], results: fixtureStressTest.scenarios[0].results.map((result) => result.observed_months === 6 ? { ...result, status: "insufficient_quality_months" as const, health: null, delta_points: null, band: null, attribution: null, score_terms: null } : result) };
  assert.equal(preferredObservedHorizon(threeMissing), 3);
  assert.equal(preferredObservedHorizon(null), 6);
});

test("COMP_1122 usa un fixture de presentación aislado y no se activa en otras empresas", () => {
  assert.equal(isStressDemoCompany(STRESS_DEMO_COMPANY_ID), true);
  assert.equal(isStressDemoCompany("COMP_0356"), false);
  assert.equal(stressDemoComp1122.source, STRESS_DEMO_SOURCE);
  const demo = html(undefined, STRESS_DEMO_COMPANY_ID);
  assert.match(demo, /data-testid="stress-health">52/);
  assert.match(demo, /65/);
  assert.match(demo, /−13 pts/);
  assert.match(demo, /−118k €\/mes/);
  assert.match(demo, /data-stress-demo="comp-1122"/);
  assert.match(demo, />Severo</);
  assert.match(demo, />Leve</);
  assert.match(demo, />Personalizado</);
  assert.match(demo, /Retraso de cobros/);
  assert.match(demo, /Días extra del cliente principal identificado/);
  assert.match(demo, /Recorrido de 0d a \+60d/);
  assert.match(demo, /Escenario, no predicción/);
  assert.match(demo, /El frontend no calcula puntuaciones ni interpola combinaciones/);
  assert.match(demo, /La tesorería no absorbe el shock/);
  assert.match(demo, /6 meses/);
  const live = html(fixtureStressTest, "COMP_0356");
  assert.doesNotMatch(live, /data-stress-demo="comp-1122"/);
  assert.doesNotMatch(live, /−118k €/);
  assert.match(live, /data-testid="stress-health">54/);
});
