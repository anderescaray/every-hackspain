import assert from "node:assert/strict";
import test from "node:test";
import { groupDetailSchema } from "../types/groupDetail";
import { fixtureGroups, groupCompanyFixtures } from "./fixtures/groupDetails";
import { companyDetailSchema } from "../types/companyDetail";
import { groupMoney, groupScore } from "../lib/groupPresentation";

function group() { return structuredClone(fixtureGroups.GROUP_0042); }

test("los formatos conservan cero, datos ausentes y decimales españoles", () => {
  assert.equal(groupScore(0), "0");
  assert.equal(groupScore(null), "—");
  assert.equal(groupScore(73.45), "73,5");
  assert.equal(groupMoney(null), "No disponible");
  assert.equal(groupMoney(0), "0 €");
});

test("el grupo conserva sociedades, relaciones y recomendaciones sin Group Health Score", () => {
  const value = groupDetailSchema.parse(group());
  assert.equal(value.members.length, 6);
  assert.equal(value.members.filter((member) => member.trajectory === "deteriorating").length, 2);
  assert.equal("health_score" in value, false);
  assert.equal("group_health_score" in value, false);
  assert.equal(value.recommendations.length, 8);
  assert.ok(value.recommendations.some((item) => item.id.startsWith("advisor-")));
  assert.ok(value.relations.some((relation) => relation.status === "identified"));
  assert.ok(value.relations.some((relation) => relation.status === "candidate"));
  assert.ok(value.relations.some((relation) => relation.status === "unknown" && relation.to_company_id === null));
});

test("los enlaces a sociedades de la demo tienen fichas consistentes", () => {
  for (const member of group().members) {
    const company = companyDetailSchema.parse(groupCompanyFixtures[member.company_id]);
    assert.equal(company.group_id, "GROUP_0042");
    assert.equal(company.health_score, member.health_score);
    assert.deepEqual(company.dimensions, member.dimensions);
  }
});

test("la liquidez y deuda agregadas se reciben sin calcularlas desde las sociedades", () => {
  const value = group();
  value.available_liquidity.value = 123456;
  assert.equal(groupDetailSchema.parse(value).available_liquidity.value, 123456);
  value.available_liquidity.value = null;
  assert.equal(groupDetailSchema.parse(value).available_liquidity.value, null);
  value.available_liquidity.value = 0;
  assert.equal(groupDetailSchema.parse(value).available_liquidity.value, 0);
});

test("rechaza duplicados, referencias rotas, autoenlaces y supuestos sin evidencia", () => {
  const mutations = [
    (value: ReturnType<typeof group>) => { value.members.push(value.members[0]); },
    (value: ReturnType<typeof group>) => { value.relations[0].to_company_id = "COMP_9999"; },
    (value: ReturnType<typeof group>) => { value.relations[0].to_company_id = value.relations[0].from_company_id; },
    (value: ReturnType<typeof group>) => { value.relations[0].to_company_id = null; },
    (value: ReturnType<typeof group>) => { value.relations[0].evidence_refs = []; },
    (value: ReturnType<typeof group>) => { value.relations[0].evidence_refs = ["group-positions"]; },
    (value: ReturnType<typeof group>) => { value.recommendations[0].relation_refs = ["missing"]; },
    (value: ReturnType<typeof group>) => { value.insights[0].company_refs = ["COMP_9999"]; },
    (value: ReturnType<typeof group>) => { value.recommendations[0].evidence_refs = ["missing"]; },
    (value: ReturnType<typeof group>) => { value.coverage.known_company_count = 1; },
    (value: ReturnType<typeof group>) => { value.available_liquidity.covered_company_ids = []; },
    (value: ReturnType<typeof group>) => { value.members[4].outlook.funding_need = 0; },
  ];
  for (const mutate of mutations) {
    const value = group();
    mutate(value);
    assert.equal(groupDetailSchema.safeParse(value).success, false, mutate.toString());
  }
  assert.equal(groupDetailSchema.safeParse({ ...group(), group_health_score: 80 }).success, false);
});

test("un grupo sin sociedades ni métricas disponibles no genera resultados falsos", () => {
  const empty = groupDetailSchema.parse(fixtureGroups.GROUP_0099);
  assert.equal(empty.members.length, 0);
  assert.equal(empty.available_liquidity.value, null);
  assert.equal(empty.relations.length, 0);
  assert.equal(empty.recommendations.length, 0);
});
