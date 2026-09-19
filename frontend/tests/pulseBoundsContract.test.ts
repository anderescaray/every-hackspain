import assert from "node:assert/strict";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";
import { portfolioSchema } from "../types/portfolio";
import { groupDetailSchema } from "../types/groupDetail";
import { filterItems, parseQuery, statusLabels } from "../lib/portfolioPresentation";
import fixture from "./fixtures/pulseBounded.json";

// Authored from the Python scorer/exporter, never imported by the application.
test("v1.0.1 conserva punto acotado, rango, evidencia y contribuciones originales", () => {
  const company = companyDetailSchema.parse(fixture.company);
  const debt = company.pulse.pillars.debt_obligations;
  assert.equal(company.status, "complete_bounded");
  assert.equal(company.health_score, fixture.company.pulse.health);
  assert.equal(company.dimensions.debt, debt.score);
  assert.notEqual(debt.score, debt.identified_score);
  assert.deepEqual(company.pulse.identified_range, fixture.company.pulse.identified_range);
  assert.deepEqual(company.pulse.contributions, fixture.company.pulse.contributions);
  assert.equal(Object.values(company.pulse.contributions).reduce<number>((sum, value) => sum + (value ?? 0), 0), company.health_score);
  assert.equal(debt.score_estimation, "bounded_midpoint");
  assert.equal(debt.service_absence_verified, false);
  assert.equal(company.pulse.health_evidence, "bounded");
});

test("v1.0.1 rechaza campos obligatorios ausentes y no encubre bounded como verified", () => {
  const source = structuredClone(fixture.company);
  const missing = { ...source, pulse: { ...source.pulse, identified_range: undefined } };
  assert.equal(companyDetailSchema.safeParse(missing).success, false);
  const debtMissing = structuredClone(source);
  Reflect.deleteProperty(debtMissing.pulse.pillars.debt_obligations, "identified_service");
  assert.equal(companyDetailSchema.safeParse(debtMissing).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...source, status: "complete_verified", pulse: { ...source.pulse, status: "complete_verified", health_evidence: "verified" } }).success, false);
  const changedMethod = { ...source, config_version: "pulse-config-v1", pulse: { ...source.pulse, config_version: "pulse-config-v1" } };
  assert.equal(companyDetailSchema.safeParse(changedMethod).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...source, dimensions: { ...source.dimensions, debt: source.pulse.pillars.debt_obligations.identified_score } }).success, false);
});

test("cartera y grupo preservan los mismos límites sin agregado de Health", () => {
  const portfolio = portfolioSchema.parse(fixture.portfolio);
  const group = groupDetailSchema.parse(fixture.group);
  assert.deepEqual(portfolio.items[0].identified_range, fixture.company.pulse.identified_range);
  assert.deepEqual(group.members[0].identified_range, fixture.company.pulse.identified_range);
  assert.equal(group.health_score, null);
  assert.equal(portfolio.items[0].health_evidence, "bounded");
  assert.equal(statusLabels.complete_bounded, "Identificada · acotada");
  assert.equal(filterItems(portfolio.items, parseQuery({ status: "complete" })).length, 1);
  assert.equal(filterItems(portfolio.items, parseQuery({ status: "complete_bounded" })).length, 1);
  assert.equal(filterItems(portfolio.items, parseQuery({ status: "complete_verified" })).length, 0);
  const incomplete = structuredClone(fixture.portfolio);
  Reflect.deleteProperty(incomplete.items[0], "identified_range");
  assert.equal(portfolioSchema.safeParse(incomplete).success, false);
  assert.equal(portfolioSchema.safeParse({ ...fixture.portfolio, score_version: "PulseFourPillars-v1.0" }).success, false);
});

test("rangos suministrados invertidos, incompletos o fuera de escala fallan cerrados", () => {
  for (const range of [{ min: 95, max: 90 }, { min: null, max: 90 }, { min: 0, max: 101 }]) {
    const company = structuredClone(fixture.company);
    Object.assign(company.pulse.pillars.debt_obligations, { score_range: range });
    assert.equal(companyDetailSchema.safeParse(company).success, false);
  }
});

test("el loader consume snapshot v1.1 íntegro y rechaza mezclar metodología", async () => {
  const { mkdtemp, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const { writeFixtureSnapshot } = await import("./fixtures/snapshot");
  const { pulseEnvelopeSchema } = await import("../types/pulse");
  const { getCompanyDetail, CompanyDataError } = await import("../services/companyData");
  const directory = await mkdtemp(join(tmpdir(), "pulse-bounded-snapshot-"));
  const previous = process.env.PULSE_GENERATED_DIR;
  process.env.PULSE_GENERATED_DIR = directory;
  try {
    const company = { ...fixture.company, source: "generated" };
    const envelope = pulseEnvelopeSchema.parse(company);
    await writeFixtureSnapshot(directory, { "companies/COMP_1084.json": company }, envelope, "pulse-frontend-v1.1");
    assert.equal((await getCompanyDetail("COMP_1084"))?.status, "complete_bounded");
    await writeFixtureSnapshot(directory, { "companies/COMP_1084.json": { ...company, score_version: "PulseFourPillars-v1.0" } }, envelope, "pulse-frontend-v1.1");
    await assert.rejects(getCompanyDetail("COMP_1084"), CompanyDataError);
  } finally {
    if (previous === undefined) delete process.env.PULSE_GENERATED_DIR; else process.env.PULSE_GENERATED_DIR = previous;
    await rm(directory, { recursive: true, force: true });
  }
});

test("la ficha muestra identificación acotada y los rangos del servidor sin rediseño", async () => {
  const { createRequire } = await import("node:module");
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  const require = createRequire(import.meta.url);
  const previous = require.extensions[".css"];
  require.extensions[".css"] = (module) => { module.exports = {}; };
  try {
    const { CompanyInsights } = await import("../components/insights/CompanyInsights");
    const markup = renderToStaticMarkup(createElement(CompanyInsights, { company: companyDetailSchema.parse(fixture.company) }));
    assert.match(markup, /Health identificado con incertidumbre acotada/);
    assert.match(markup, /Rango identificado de Health/);
    assert.match(markup, /Deuda con incertidumbre acotada/);
    assert.match(markup, /No es un intervalo de confianza/);
  } finally {
    if (previous) require.extensions[".css"] = previous; else delete require.extensions[".css"];
  }
});

test("servicio identificado no convierte un límite superior desconocido en cero", async () => {
  const { pulseSchema } = await import("../types/pulse");
  const unknown = pulseSchema.parse(fixture.unknown_score);
  assert.equal(unknown.health, null);
  assert.equal(unknown.pillars.debt_obligations.score, null);
  assert.deepEqual(unknown.pillars.debt_obligations.service_bounds, { min: 0, max: null });
  assert.deepEqual(unknown.pillars.debt_obligations.score_range, { min: null, max: null });
  const wide = pulseSchema.parse(fixture.wide_score);
  assert.equal(wide.status, "partial");
  assert.equal(wide.health, null);
  assert.equal(wide.pillars.debt_obligations.score, null);
  assert.notEqual(wide.identified_range, null);
  assert.notEqual(wide.pillars.debt_obligations.score_range?.min, null);
});
