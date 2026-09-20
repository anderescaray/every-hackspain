import assert from "node:assert/strict";
import test from "node:test";
import { companySections, hasSimulator, visibleCompanySections, withCompanyContext } from "../lib/analysisNavigation";

test("empresa tiene cinco accesos estables incluyendo Cómo actuar y Stress Testing", () => {
  assert.deepEqual(companySections.map((section) => section.id), ["health-score", "trajectory", "actionability", "cash-truth", "scenarios"]);
  assert.equal(companySections.find((section) => section.id === "actionability")?.label, "Cómo actuar");
  assert.equal(companySections.find((section) => section.id === "scenarios")?.label, "Stress Testing");
});

test("el contexto de empresa se mantiene sin borrar filtros o fragmentos", () => {
  assert.equal(withCompanyContext("/groups/GROUP_0042", "COMP_0412"), "/groups/GROUP_0042?entity=COMP_0412");
  assert.equal(withCompanyContext("/groups/GROUP_0042/recommendations?relation=support-0412#detail", "COMP_0356"), "/groups/GROUP_0042/recommendations?relation=support-0412&entity=COMP_0356#detail");
  assert.equal(withCompanyContext("/groups/GROUP_0042/recommendations?entity=COMP_0007", "COMP_0412"), "/groups/GROUP_0042/recommendations?entity=COMP_0412");
});

test("no atribuye contexto ficticio ni modifica enlaces de empresas o externos", () => {
  for (const href of ["/companies/COMP_0412", "#cash-truth", "https://example.com/groups/GROUP_0042"]) assert.equal(withCompanyContext(href, "COMP_0356"), href);
  assert.equal(withCompanyContext("/groups/GROUP_0042", null), "/groups/GROUP_0042");
  assert.equal(withCompanyContext("/groups/GROUP_0042", "../COMP_0412"), "/groups/GROUP_0042");
});

test("sin escenarios precalculados no se ofrece el acceso al simulador", () => {
  assert.equal(hasSimulator({ scenarios: [{ id: "s1" }] }), true);
  for (const empty of [{ scenarios: [] }, {}, null, undefined]) assert.equal(hasSimulator(empty), false);
  const withSimulator = visibleCompanySections({ simulator: true }).map((section) => section.id);
  const without = visibleCompanySections({ simulator: false }).map((section) => section.id);
  assert.deepEqual(withSimulator, ["health-score", "trajectory", "actionability", "cash-truth", "scenarios"]);
  assert.deepEqual(without, ["health-score", "trajectory", "actionability", "cash-truth"]);
  // El resto de accesos no se tocan: solo desaparece el que no tiene sección detrás.
  assert.equal(without.includes("scenarios"), false);
});
