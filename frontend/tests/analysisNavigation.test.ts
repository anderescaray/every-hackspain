import assert from "node:assert/strict";
import test from "node:test";
import { companySections, withCompanyContext } from "../lib/analysisNavigation";

test("empresa tiene cinco accesos estables incluyendo Escenarios", () => {
  assert.deepEqual(companySections.map((section) => section.id), ["health-score", "trajectory", "cash-truth", "time-borrowed", "scenarios"]);
});

test("el contexto de empresa se mantiene sin borrar filtros o fragmentos", () => {
  assert.equal(withCompanyContext("/groups/GROUP_0042", "COMP_0412"), "/groups/GROUP_0042?entity=COMP_0412");
  assert.equal(withCompanyContext("/groups/GROUP_0042/network?company=COMP_0007&relation=support-0412#detail", "COMP_0356"), "/groups/GROUP_0042/network?company=COMP_0007&relation=support-0412&entity=COMP_0356#detail");
  assert.equal(withCompanyContext("/groups/GROUP_0042/recommendations?entity=COMP_0007", "COMP_0412"), "/groups/GROUP_0042/recommendations?entity=COMP_0412");
});

test("no atribuye contexto ficticio ni modifica enlaces de empresas o externos", () => {
  for (const href of ["/companies/COMP_0412", "#cash-truth", "https://example.com/groups/GROUP_0042"]) assert.equal(withCompanyContext(href, "COMP_0356"), href);
  assert.equal(withCompanyContext("/groups/GROUP_0042", null), "/groups/GROUP_0042");
  assert.equal(withCompanyContext("/groups/GROUP_0042", "../COMP_0412"), "/groups/GROUP_0042");
});
