import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { filterItems, parseQuery, sortItems, summarize } from "../lib/portfolioPresentation";
import { getPortfolio, PortfolioDataError } from "../services/portfolioData";
import { writeFixtureSnapshot } from "./fixtures/snapshot";
import { fixtureEnvelope } from "./fixtures/pulseData";
import { portfolioSchema, type Portfolio, type PortfolioItem } from "../types/portfolio";

const item = (overrides: Partial<PortfolioItem>): PortfolioItem => ({
  company_id: "COMP_0001", group_id: "GROUP_0001", health_score: 60, delta_vs_prev: 1.2, trajectory: "stable", trajectory_stage: null,
  confidence: 80, score_status: "complete", status_reason: null, main_signal: "Margen operativo (6m)", main_signal_impact: -2.1,
  support_dependency_ratio: 0.1, attention: "low", has_detail: true, run_id: fixtureEnvelope.run_id, dimensions: { momentum: 60, cash_generation: 60, resilience: 60, debt: 60 }, missing_components: [], robustness: "not_tested", ...overrides,
});

const portfolio: Portfolio = {
  schema_version: "2.0", ...fixtureEnvelope, source: "generated", as_of: "2026-08-31", period: "sep 2024 – ago 2026", currency: "EUR",
  summary: "Cartera de prueba.",
  items: [
    item({ company_id: "COMP_0001" }),
    item({ company_id: "COMP_0002", health_score: 30, trajectory: "deteriorating", trajectory_stage: "confirmed", attention: "high", support_dependency_ratio: 0.6 }),
    item({ company_id: "COMP_0003", group_id: null, health_score: null, delta_vs_prev: null, trajectory: null, confidence: null, score_status: "insufficient_evidence", status_reason: "no_usable_transactions", main_signal: null, main_signal_impact: null, support_dependency_ratio: null, attention: "low", has_detail: false }),
    item({ company_id: "COMP_0004", health_score: 85, trajectory: "improving", trajectory_stage: "emerging", attention: "medium", score_status: "complete", status_reason: "coverage_account_change" }),
  ],
};

let directory: string;
const previous = process.env.PULSE_GENERATED_DIR;
before(async () => { directory = await mkdtemp(path.join(os.tmpdir(), "embat-portfolio-test-")); });
after(async () => { if (previous === undefined) delete process.env.PULSE_GENERATED_DIR; else process.env.PULSE_GENERATED_DIR = previous; await rm(directory, { recursive: true, force: true }); });

test("el contrato acepta la cartera de prueba y rechaza incoherencias", () => {
  assert.ok(portfolioSchema.safeParse(portfolio).success);
  const broken = structuredClone(portfolio);
  broken.items[2].health_score = 40;
  assert.equal(portfolioSchema.safeParse(broken).success, false, "sin puntuar no puede tener score");
  const duplicated = structuredClone(portfolio);
  duplicated.items.push(item({ company_id: "COMP_0001" }));
  assert.equal(portfolioSchema.safeParse(duplicated).success, false);
});

test("los filtros combinan trayectoria, atención, estado, grupo y búsqueda", () => {
  assert.deepEqual(filterItems(portfolio.items, parseQuery({ trajectory: "deteriorating" })).map((i) => i.company_id), ["COMP_0002"]);
  assert.deepEqual(filterItems(portfolio.items, parseQuery({ status: "insufficient_evidence" })).map((i) => i.company_id), ["COMP_0003"]);
  assert.deepEqual(filterItems(portfolio.items, parseQuery({ group: "group_0001", attention: "medium" })).map((i) => i.company_id), ["COMP_0004"]);
  assert.deepEqual(filterItems(portfolio.items, parseQuery({ q: "0003" })).map((i) => i.company_id), ["COMP_0003"]);
  assert.equal(filterItems(portfolio.items, parseQuery({ trajectory: "nonsense" })).length, 4, "valores desconocidos se ignoran");
});

test("la ordenación pone los nulos al final sea cual sea el sentido y ordena atención por gravedad", () => {
  assert.deepEqual(sortItems(portfolio.items, "health_score", "desc").map((i) => i.company_id), ["COMP_0004", "COMP_0001", "COMP_0002", "COMP_0003"]);
  assert.deepEqual(sortItems(portfolio.items, "health_score", "asc").map((i) => i.company_id), ["COMP_0002", "COMP_0001", "COMP_0004", "COMP_0003"]);
  assert.deepEqual(sortItems(portfolio.items, "attention", "desc").map((i) => i.company_id), ["COMP_0002", "COMP_0004", "COMP_0001", "COMP_0003"]);
});

test("el resumen cuenta sin convertir nulos en cero", () => {
  assert.deepEqual(summarize(portfolio), { total: 4, scored: 3, improving: 1, deteriorating: 1, highAttention: 1, dependent: 1 });
});

test("getPortfolio lee el snapshot y rechaza fixtures o runs mezclados", async () => {
  process.env.PULSE_GENERATED_DIR = directory;
  assert.equal(await getPortfolio(), null);
  await writeFixtureSnapshot(directory, { "portfolio.json": portfolio });
  assert.equal((await getPortfolio())?.items.length, 4);
  for (const value of [{ ...portfolio, source: "fixture" }, { ...portfolio, run_id: "other" }]) {
    await writeFixtureSnapshot(directory, { "portfolio.json": value });
    await assert.rejects(getPortfolio(), PortfolioDataError);
  }
});
