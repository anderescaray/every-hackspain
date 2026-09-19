import assert from "node:assert/strict";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

const company = fixtureCompanies.COMP_0356;

test("Pulse copia pesos, pilares y Health sin mapping V2 ni cálculo en UI", () => {
  assert.deepEqual(company.health_score_model.weights, { momentum: 0.15, cash_generation: 0.4, resilience: 0.25, debt: 0.2 });
  assert.equal(companyDetailSchema.parse(company).health_score, company.pulse.health);
  assert.equal(Object.values(company.pulse.contributions).reduce<number>((sum, value) => sum + value!, 0), company.health_score);
  assert.equal(company.health_score_model.version, "PulseFourPillars-v1.0");
});

test("rechaza cambiar el resultado o pesos en la capa de presentación", () => {
  const payload = structuredClone(company);
  payload.health_score = 55;
  payload.history.at(-1)!.health_score = 55;
  assert.equal(companyDetailSchema.safeParse(payload).success, false);
  payload.health_score = company.health_score;
  payload.history = company.history;
  payload.health_score_model.weights = { momentum: 1, cash_generation: 0, resilience: 0, debt: 0 };
  assert.equal(companyDetailSchema.safeParse(payload).success, false);
});

test("la confianza describe evidencia y nunca modifica Health", () => {
  for (const confidence of [null, 0, 50, 88, 100]) assert.equal(companyDetailSchema.parse({ ...company, confidence }).health_score, company.health_score);
});

test("rechaza dimensiones inválidas y metodología legacy", () => {
  for (const debt of [NaN, Infinity, -1, 101]) assert.equal(companyDetailSchema.safeParse({ ...company, dimensions: { ...company.dimensions, debt } }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, score_version: "financial_smoothed_v2" }).success, false);
  assert.equal(companyDetailSchema.safeParse({ ...company, schema_version: "2.0" }).success, false);
});
