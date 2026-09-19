import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";

test("el primer ejemplo documentado es Pulse actual y conserva la evidencia parcial", async () => {
  const document = await readFile(new URL("../../docs/frontend-data-contract.md", import.meta.url), "utf8");
  const block = document.match(/```json\n([\s\S]*?)\n```/);
  assert.ok(block);
  const company = companyDetailSchema.parse(JSON.parse(block[1]));
  assert.equal(company.company_id, "COMP_1084");
  assert.equal(company.score_version, "PulseFourPillars-v1.0");
  assert.equal(company.health_score, null);
  assert.equal(company.dimensions.debt, null);
  assert.ok(company.pulse.missing_components.includes("debt_obligations"));
});
