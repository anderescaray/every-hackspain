import assert from "node:assert/strict";
import test from "node:test";
import { fixtureCompanies } from "./fixtures/companyDetails";
import { companyDetailSchema } from "../types/companyDetail";
import { selectScenario, defaultScenarioInputs } from "../lib/companyScenario";

for (const [id, fixture] of Object.entries(fixtureCompanies)) {
  test(`${id}: contrato completo, 24 meses y evidencia trazable`, () => {
    const company = companyDetailSchema.parse(fixture);
    assert.equal(company.source, "fixture");
    assert.equal(company.history.length, 24);
    assert.equal(company.history.at(-1)?.health_score, company.health_score);
    assert.equal(company.cash_truth.components.reduce((sum, item) => sum + item.gross_movement, 0), company.cash_truth.total_gross_movement);
    assert.deepEqual(company.cash_truth.components.map((item) => item.category), ["operating", "circulation", "support", "uncertain"]);
    assert.ok(company.alerts.length >= 2 && company.alerts.length <= 5);
    for (const group of company.evidence) {
      assert.ok(group.rows.length >= 5 && group.rows.length <= 10);
      for (const [index, row] of group.rows.entries()) {
        if (row.kind !== "invoice") continue;
        assert.ok(row.payment_date);
        const [start, end] = index < 3 ? ["2026-01-01", "2026-03-31"] : ["2026-06-01", "2026-08-31"];
        assert.ok(row.payment_date >= start && row.payment_date <= end);
      }
      for (const component of company.cash_truth.components) {
        const sampleGross = group.rows.reduce((sum, row) => sum + (row.kind === "transaction" && row.category === component.category ? Math.abs(row.amount) : 0), 0);
        assert.ok(sampleGross <= component.gross_movement);
      }
    }
    assert.equal(selectScenario(company.health_score, company.simulation, defaultScenarioInputs).health_score, company.health_score);
  });
}

test("la corrección de caja mantiene falsa debilidad y dependencia", () => {
  const company = fixtureCompanies.COMP_0356;
  assert.equal(company.cash_truth.correction?.apparent_operating, -86700000);
  assert.equal(company.cash_truth.correction?.identified_operating, 25600);
  assert.equal(company.cash_truth.correction?.observed_support, 4140000);
  assert.equal(company.cash_truth.apparent_net, fixtureCompanies.COMP_0655.cash_truth.apparent_net);
  assert.notEqual(company.cash_truth.components[0].net_amount, fixtureCompanies.COMP_0655.cash_truth.components[0].net_amount);
  assert.equal(company.cash_truth.components[3].confidence, null);
  assert.equal(company.cash_truth.components[3].net_amount, null);
});

test("el caso de puntualidad mantiene los tres tiempos independientes", () => {
  const ar = fixtureCompanies.COMP_1171.time_borrowed.ar;
  assert.ok(ar);
  assert.equal(ar.counterparty_id, "COUNTERPARTY_06105");
  assert.deepEqual([ar.before.payment_term, ar.before.delay, ar.before.time_to_cash], [62, 20, 81]);
  assert.deepEqual([ar.after.payment_term, ar.after.delay, ar.after.time_to_cash], [102, 0, 102]);
  assert.ok(fixtureCompanies.COMP_1171.time_borrowed.ap);
});

test("el simulador selecciona el resultado recibido sin calcularlo ni modificar la empresa", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  const example = company.simulation.scenarios[0];
  const result = selectScenario(company.health_score, company.simulation, example.inputs);
  assert.equal(result.health_score, 78);
  example.health_score = 43;
  assert.equal(selectScenario(company.health_score, company.simulation, example.inputs).health_score, 43);
  example.health_score = 0;
  assert.equal(selectScenario(company.health_score, company.simulation, example.inputs).health_score, 0);
  assert.equal(company.health_score, 72);
  assert.equal(selectScenario(company.health_score, company.simulation, { ...defaultScenarioInputs, internal_support: -10 }).health_score, 71);
});

test("no interpola combinaciones y funciona sin escenarios preparados", () => {
  const company = fixtureCompanies.COMP_0356;
  const inputs = { ...company.simulation.scenarios[0].inputs, customer_term: -16 };
  const result = selectScenario(company.health_score, company.simulation, inputs);
  assert.equal(result.health_score, null);
  assert.deepEqual(result.impacts, []);
  assert.equal(selectScenario(company.health_score, { ...company.simulation, scenarios: [], example_id: null }, inputs).health_score, null);
});

test("los controles acotan entradas inválidas y nunca permiten retrasos negativos", () => {
  const company = fixtureCompanies.COMP_1171;
  const result = selectScenario(company.health_score, company.simulation, { customer_term: NaN, collection_delay: -50, supplier_term: Infinity, internal_support: 999 });
  assert.deepEqual(result.inputs, { customer_term: 0, collection_delay: 0, supplier_term: 0, internal_support: 50 });
  assert.equal(result.health_score, null);
});
