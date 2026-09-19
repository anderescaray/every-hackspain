import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { CompanyDataError, getCompanyDetail } from "../services/companyData";
import { fixtureCompanies } from "./fixtures/companyDetails";
import { writeFixtureSnapshot } from "./fixtures/snapshot";

let directory: string;
const previous = { root: process.env.PULSE_GENERATED_DIR, mode: process.env.COMPANY_DATA_MODE, loose: process.env.COMPANY_ANALYSIS_DIR };
const payload = { ...structuredClone(fixtureCompanies.COMP_0356), source: "generated" as const };
before(async () => { directory = await mkdtemp(path.join(os.tmpdir(), "pulse-web-contract-")); process.env.PULSE_GENERATED_DIR = directory; delete process.env.COMPANY_DATA_MODE; });
after(async () => {
  for (const [key, value] of Object.entries({ PULSE_GENERATED_DIR: previous.root, COMPANY_DATA_MODE: previous.mode, COMPANY_ANALYSIS_DIR: previous.loose })) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
  await rm(directory, { recursive: true, force: true });
});

test("sin puntero no hay fallback a archivos legacy ni fixtures", async () => {
  const loose = path.join(directory, "companies");
  await mkdir(loose);
  await writeFile(path.join(loose, "COMP_0356.json"), JSON.stringify(payload));
  process.env.COMPANY_ANALYSIS_DIR = loose;
  assert.equal(await getCompanyDetail("COMP_0356"), null);
  for (const id of ["__proto__", "../COMP_0356", "COMP_0356/../COMP_1171"]) assert.equal(await getCompanyDetail(id), null);
});

test("lee el snapshot íntegro y preserva el Health del motor", async () => {
  await writeFixtureSnapshot(directory, { "companies/COMP_0356.json": payload });
  assert.equal((await getCompanyDetail("COMP_0356"))?.health_score, payload.pulse.health);
  assert.equal(await getCompanyDetail("COMP_9999"), null);
});

test("rechaza mezcla de run, modificación de método, aliases o fichero sin hash", async () => {
  for (const changed of [{ ...payload, run_id: "other-run" }, { ...payload, score_version: "financial_smoothed_v2" }, { ...payload, dimensions: { ...payload.dimensions, debt: 50 } }, { ...payload, company_id: "COMP_9999" }]) {
    await writeFixtureSnapshot(directory, { "companies/COMP_0356.json": changed });
    await assert.rejects(getCompanyDetail("COMP_0356"), CompanyDataError);
  }
  const snapshot = await writeFixtureSnapshot(directory, { "companies/COMP_0356.json": payload });
  await writeFile(path.join(snapshot, "companies/COMP_0356.json"), JSON.stringify({ ...payload, health_score: 0 }));
  await assert.rejects(getCompanyDetail("COMP_0356"), CompanyDataError);
});

test("fixtures requieren directorio y modo explícitos, nunca fallback normal", async () => {
  const loose = path.join(directory, "companies");
  await writeFile(path.join(loose, "COMP_0356.json"), JSON.stringify(fixtureCompanies.COMP_0356));
  process.env.COMPANY_ANALYSIS_DIR = loose;
  process.env.COMPANY_DATA_MODE = "fixtures";
  try { assert.equal((await getCompanyDetail("COMP_0356"))?.source, "fixture"); }
  finally { delete process.env.COMPANY_DATA_MODE; }
});

test("runtime no importa fixtures ni contiene cálculo de score", async () => {
  const service = await readFile(new URL("../services/companyData.ts", import.meta.url), "utf8");
  assert.doesNotMatch(service, /import[^\n]+(?:fixtures|mockCompanies)/);
  const labels = await readFile(new URL("../lib/healthScore.ts", import.meta.url), "utf8");
  assert.doesNotMatch(labels, /calculateHealthScore|Math\.round|reduce\(|HEALTH_SCORE_WEIGHTS|demo-v1/);
});
