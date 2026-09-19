import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { companyDetailSchema } from "../types/companyDetail";
import { groupDetailSchema } from "../types/groupDetail";

const execFileAsync = promisify(execFile);

test("el JSON completo de la documentación cumple el contrato de Data y el validador CLI", async () => {
  const document = await readFile(new URL("../../docs/frontend-data-contract.md", import.meta.url), "utf8");
  const block = document.match(/```json\n([\s\S]*?)\n```/);
  assert.ok(block, "Falta el ejemplo JSON completo");
  const company = companyDetailSchema.parse(JSON.parse(block[1]));
  assert.equal(company.source, "generated");
  assert.equal(company.history.length, 24);
  assert.equal(company.health_score, 72);
  assert.ok(company.time_borrowed.ar && company.time_borrowed.ap);
  assert.equal(company.simulation.scenarios.length, 2);
  assert.equal(company.cash_truth.account_flows?.accounts.length, 3);
  assert.equal(company.cash_truth.account_flows?.transfers.length, 3);
  assert.equal(company.cash_truth.correction, null);
  assert.equal(company.cash_truth.own_account_circulation?.transferred_amount, 86725600);
  assert.equal(company.cash_truth.own_account_circulation?.transfer_count, 34);
  const directory = await mkdtemp(path.join(os.tmpdir(), "embat-doc-contract-"));
  try {
    await writeFile(path.join(directory, `${company.company_id}.json`), block[1]);
    const { stdout } = await execFileAsync(process.execPath, ["--import", "tsx", "scripts/validateGenerated.ts"], { env: { ...process.env, COMPANY_ANALYSIS_DIR: directory, COMPANY_DATA_MODE: "generated" } });
    assert.match(stdout, /COMP_0356.json: contrato válido/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("el JSON de grupo documentado cumple el esquema y el CLI de grupos", async () => {
  const document = await readFile(new URL("../../docs/frontend-data-contract.md", import.meta.url), "utf8");
  const payload = [...document.matchAll(/```json\n([\s\S]*?)\n```/g)].map((block) => JSON.parse(block[1])).find((item) => Array.isArray(item.members));
  const group = groupDetailSchema.parse(payload);
  assert.equal(group.source, "generated");
  assert.equal(group.members.length, 2);
  assert.equal(group.relations[0].status, "identified");
  assert.equal("health_score" in group, false);
  const directory = await mkdtemp(path.join(os.tmpdir(), "embat-group-doc-"));
  try {
    await writeFile(path.join(directory, `${group.group_id}.json`), JSON.stringify(group));
    const { stdout } = await execFileAsync(process.execPath, ["--import", "tsx", "scripts/validateGenerated.ts", "--groups"], { env: { ...process.env, GROUP_ANALYSIS_DIR: directory, COMPANY_DATA_MODE: "generated" } });
    assert.match(stdout, /GROUP_0042.json: contrato válido/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
