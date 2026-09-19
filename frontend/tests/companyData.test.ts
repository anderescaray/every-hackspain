import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { CompanyDataError, getCompanyDetail } from "../services/companyData";
import { fixtureCompanies } from "./fixtures/companyDetails";
import { companyDetailSchema } from "../types/companyDetail";

let directory: string;
const previousDirectory = process.env.COMPANY_ANALYSIS_DIR;
const previousMode = process.env.COMPANY_DATA_MODE;
const payload = { ...structuredClone(fixtureCompanies.COMP_0356), source: "generated" as const };

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), "embat-contract-test-"));
  process.env.COMPANY_ANALYSIS_DIR = directory;
  delete process.env.COMPANY_DATA_MODE;
});
after(async () => {
  if (previousDirectory === undefined) delete process.env.COMPANY_ANALYSIS_DIR; else process.env.COMPANY_ANALYSIS_DIR = previousDirectory;
  if (previousMode === undefined) delete process.env.COMPANY_DATA_MODE; else process.env.COMPANY_DATA_MODE = previousMode;
  await rm(directory, { recursive: true, force: true });
});

test("sin archivos no hay fallback a fixtures, tampoco para empresas conocidas", async () => {
  for (const id of ["COMP_0356", "COMP_0655", "COMP_1171", "COMP_9999"]) assert.equal(await getCompanyDetail(id), null);
});

test("IDs desconocidos, prototipos y rutas no permiten leer otros archivos", async () => {
  for (const id of ["missing", "__proto__", "constructor", "../COMP_0356", "%2e%2e", "COMP_0356/../COMP_1171"]) assert.equal(await getCompanyDetail(id), null);
});

test("la ruta predeterminada es public/generated/companies, sin manifiesto", async () => {
  const cwd = process.cwd();
  const root = await mkdtemp(path.join(os.tmpdir(), "embat-default-path-test-"));
  try {
    await mkdir(path.join(root, "public/generated/companies"), { recursive: true });
    await writeFile(path.join(root, "public/generated/companies/COMP_0356.json"), JSON.stringify(payload));
    delete process.env.COMPANY_ANALYSIS_DIR;
    process.chdir(root);
    assert.equal((await getCompanyDetail("COMP_0356"))?.health_score, 72);
  } finally {
    process.chdir(cwd);
    process.env.COMPANY_ANALYSIS_DIR = directory;
    await rm(root, { recursive: true, force: true });
  }
});

test("lee nuevos JSON y actualizaciones sin reiniciar ni modificar componentes", async () => {
  await writeFile(path.join(directory, "COMP_0356.json"), JSON.stringify(payload));
  const first = await getCompanyDetail("COMP_0356");
  assert.ok(first);
  first.health_score = 0;
  assert.equal((await getCompanyDetail("COMP_0356"))?.health_score, 72);
  const updated = structuredClone(payload);
  updated.health_score = 57;
  updated.history.at(-1)!.health_score = 57;
  await writeFile(path.join(directory, "COMP_0356.json"), JSON.stringify(updated));
  assert.equal((await getCompanyDetail("COMP_0356"))?.health_score, 57);
});

test("JSON malformado, ID distinto, campos ausentes y archivos grandes se rechazan", async () => {
  for (const content of ["{incompleto", JSON.stringify({ ...payload, company_id: "COMP_1171" }), "{}", " ".repeat(2 * 1024 * 1024 + 1)]) {
    await writeFile(path.join(directory, "COMP_0356.json"), content);
    await assert.rejects(getCompanyDetail("COMP_0356"), CompanyDataError);
  }
});

test("fixtures solo con habilitación explícita", async () => {
  await writeFile(path.join(directory, "COMP_0356.json"), JSON.stringify(fixtureCompanies.COMP_0356));
  await assert.rejects(getCompanyDetail("COMP_0356"), CompanyDataError);
  process.env.COMPANY_DATA_MODE = "fixtures";
  try { assert.equal((await getCompanyDetail("COMP_0356"))?.source, "fixture"); }
  finally { delete process.env.COMPANY_DATA_MODE; }
});

test("el contrato rechaza referencias rotas, duplicados, fechas y escenarios incoherentes", () => {
  const mutations = [
    (item: typeof payload) => { item.drivers[0].evidence_refs = ["inexistente"]; },
    (item: typeof payload) => { item.cash_truth.components[0].category = "support"; },
    (item: typeof payload) => { item.as_of = "2026-02-30"; },
    (item: typeof payload) => { item.history[1].month = item.history[0].month; },
    (item: typeof payload) => { item.history.at(-1)!.health_score = 0; },
    (item: typeof payload) => { item.simulation.example_id = "inexistente"; },
    (item: typeof payload) => { item.simulation.scenarios[0].inputs.customer_term = -999; },
    (item: typeof payload) => { item.simulation.scenarios.push(item.simulation.scenarios[0]); },
  ];
  for (const mutate of mutations) {
    const value = structuredClone(payload);
    mutate(value);
    assert.equal(companyDetailSchema.safeParse(value).success, false);
  }
});

test("el servicio de producción no importa datos ficticios ni calcula scores", async () => {
  const service = await readFile(new URL("../services/companyData.ts", import.meta.url), "utf8");
  assert.doesNotMatch(service, /import[^\n]+(?:fixtures|mockCompanies)/);
  const scoring = await readFile(new URL("../lib/healthScore.ts", import.meta.url), "utf8");
  assert.doesNotMatch(scoring, /calculateHealthScore|Math\.round|reduce\(/);
});
