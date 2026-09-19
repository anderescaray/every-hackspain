import assert from "node:assert/strict";
import test from "node:test";
import { HEALTH_SCORE_WEIGHTS } from "../lib/healthScore";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

const company = fixtureCompanies.COMP_0356;

test("pesos provisionales centralizados, cuatro dimensiones y una puntuación recibida", () => {
  assert.deepEqual(HEALTH_SCORE_WEIGHTS, { momentum: 0.25, cash_generation: 0.3, resilience: 0.25, debt: 0.2 });
  assert.equal(Object.values(HEALTH_SCORE_WEIGHTS).reduce((sum, weight) => sum + weight, 0), 1);
  assert.equal(company.health_score, 72);
  assert.equal("pulse" in company, false);
  assert.equal("stability" in company, false);
});

test("los pesos y la puntuación de Data se respetan sin recomputar el resultado", () => {
  const payload = structuredClone(company);
  payload.health_score = 55;
  payload.history.at(-1)!.health_score = 55;
  payload.health_score_model.weights = { momentum: 1, cash_generation: 0, resilience: 0, debt: 0 };
  assert.equal(companyDetailSchema.parse(payload).health_score, 55);
});

test("la confianza es cobertura independiente, nunca un factor de puntuación", () => {
  for (const confidence of [null, 0, 50, 88, 100]) assert.equal(companyDetailSchema.parse({ ...company, confidence }).health_score, 72);
});

test("rechaza dimensiones y pesos fuera del contrato", () => {
  for (const debt of [NaN, Infinity, -1, 101]) assert.equal(companyDetailSchema.safeParse({ ...company, dimensions: { ...company.dimensions, debt } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, health_score_model: { ...company.health_score_model, weights: { momentum: 0, cash_generation: 0, resilience: 0, debt: 0 } } }).success, false);
});

test("crecimiento bajo presión es una explicación trazable, no otro score", () => {
  const growthCompany = fixtureCompanies.COMP_1171;
  const growth = growthCompany.drivers.find((driver) => driver.id === "growth-pressure");
  assert.ok(growth && growth.impact < 0);
  assert.deepEqual(growth.affected_dimensions, ["momentum", "cash_generation", "resilience"]);
  assert.ok(growthCompany.alerts.some((alert) => alert.id === "growth-pressure"));
  assert.equal(growthCompany.evidence.find((group) => group.id === "growth-signals")?.rows.length, 6);
  assert.equal("growth_score" in growthCompany, false);
});
