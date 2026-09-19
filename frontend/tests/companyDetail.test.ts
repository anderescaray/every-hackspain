import assert from "node:assert/strict";
import test from "node:test";
import { getCompanyDetail } from "../services/companyData";
import { mockCompanies } from "../data/mockCompanies";
import { calculateScenario, defaultScenarioInputs } from "../lib/companyScenario";

for (const id of Object.keys(mockCompanies)) {
  test(`${id}: complete, traceable 24-month mock contract`, async () => {
    const company = await getCompanyDetail(id);
    assert.ok(company);
    assert.equal(company.source, "mock");
    assert.equal(company.history.length, 24);
    assert.equal(new Set(company.history.map((point) => point.month)).size, 24);
    assert.equal(company.history.at(-1)?.pulse, company.pulse);
    assert.equal(company.history.at(-1)?.health, company.health);
    for (const point of company.history) {
      assert.ok(point.pulse >= 0 && point.pulse <= 100);
      assert.ok(point.health >= 0 && point.health <= 100);
    }
    assert.equal(company.cash_truth.components.reduce((sum, item) => sum + item.gross_movement, 0), company.cash_truth.total_gross_movement);
    assert.deepEqual(company.cash_truth.components.map((item) => item.category), ["operating", "circulation", "support", "uncertain"]);
    assert.ok(company.alerts.length >= 2 && company.alerts.length <= 5);
    const refs = new Set(company.evidence.map((group) => group.id));
    const explanations = [...company.drivers, ...company.alerts, company.cash_truth, ...company.cash_truth.components, company.time_borrowed.ar, company.time_borrowed.ap];
    for (const item of explanations) {
      if (!item) continue;
      for (const ref of item.evidence_refs) assert.ok(refs.has(ref), `Missing evidence ${ref}`);
    }
    for (const group of company.evidence) {
      assert.ok(group.rows.length >= 5 && group.rows.length <= 10);
      assert.ok(group.total_count >= group.rows.length);
      for (const [index, row] of group.rows.entries()) {
        if (row.kind !== "invoice") continue;
        assert.ok(row.issue_date <= row.due_date);
        assert.ok(row.payment_date && row.issue_date <= row.payment_date);
        const [start, end] = index < 3 ? ["2026-01-01", "2026-03-31"] : ["2026-06-01", "2026-08-31"];
        assert.ok(row.payment_date >= start && row.payment_date <= end, `${row.invoice} belongs to its displayed payment cohort`);
      }
      for (const component of company.cash_truth.components) {
        const sampleGross = group.rows.reduce((sum, row) => sum + (row.kind === "transaction" && row.category === component.category ? Math.abs(row.amount) : 0), 0);
        assert.ok(sampleGross <= component.gross_movement);
      }
    }
    const baseline = calculateScenario(company.pulse, company.simulation, defaultScenarioInputs);
    assert.equal(baseline.pulse, company.pulse);
    assert.ok(baseline.impacts.every((impact) => impact.points === 0));
  });
}

test("unknown and prototype IDs do not resolve to a mock company", async () => {
  for (const id of ["missing", "COMP_9999", "__proto__", "constructor"]) assert.equal(await getCompanyDetail(id), null);
});

test("adapter returns an isolated payload", async () => {
  const first = await getCompanyDetail("COMP_0356");
  assert.ok(first);
  first.pulse = 0;
  assert.equal((await getCompanyDetail("COMP_0356"))?.pulse, 68);
});

test("cash correction keeps false weakness distinct from support dependency", async () => {
  const company = await getCompanyDetail("COMP_0356");
  const comparison = await getCompanyDetail("COMP_0655");
  assert.ok(company && comparison);
  assert.equal(company.cash_truth.correction?.apparent_operating, -86700000);
  assert.equal(company.cash_truth.correction?.identified_operating, 25600);
  assert.equal(company.cash_truth.correction?.observed_support, 4140000);
  assert.equal(company.cash_truth.apparent_net, comparison.cash_truth.apparent_net);
  assert.notEqual(company.cash_truth.components[0].net_amount, comparison.cash_truth.components[0].net_amount);
  assert.equal(company.cash_truth.components[3].confidence, null);
  assert.equal(company.cash_truth.components[3].net_amount, null);
});

test("punctuality case preserves all three independent timing medians", async () => {
  const company = await getCompanyDetail("COMP_1171");
  const ar = company?.time_borrowed.ar;
  assert.ok(ar);
  assert.equal(ar.counterparty_id, "COUNTERPARTY_06105");
  assert.deepEqual([ar.before.payment_term, ar.before.delay, ar.before.time_to_cash], [62, 20, 81]);
  assert.deepEqual([ar.after.payment_term, ar.after.delay, ar.after.time_to_cash], [102, 0, 102]);
  assert.ok(company?.time_borrowed.ap);
});

test("scenario example moves 68 to 74 without changing source scores", async () => {
  const company = await getCompanyDetail("COMP_0356");
  assert.ok(company);
  const result = calculateScenario(company.pulse, company.simulation, company.simulation.example);
  assert.equal(result.pulse, 74);
  assert.equal(company.pulse, 68);
  const lessSupport = calculateScenario(company.pulse, company.simulation, { ...defaultScenarioInputs, internal_support: -10 });
  assert.ok(lessSupport.pulse < company.pulse);
});

test("scenario clamps inputs, non-finite values, zero delay and Pulse bounds", async () => {
  const company = await getCompanyDetail("COMP_1171");
  assert.ok(company);
  const result = calculateScenario(company.pulse, company.simulation, { customer_term: NaN, collection_delay: -50, supplier_term: Infinity, internal_support: 999 });
  assert.deepEqual(result.inputs, { customer_term: 0, collection_delay: 0, supplier_term: 0, internal_support: 50 });
  assert.equal(calculateScenario(99, company.simulation, { ...defaultScenarioInputs, customer_term: -30 }).pulse, 100);
  assert.equal(calculateScenario(1, company.simulation, { ...defaultScenarioInputs, customer_term: 30 }).pulse, 0);
});
