import assert from "node:assert/strict";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

function example() {
  return structuredClone(fixtureCompanies.COMP_0356);
}

test("el importe entre cuentas propias se recibe aparte y no se obtiene dividiendo el bruto", () => {
  const company = example();
  const summary = company.cash_truth.own_account_circulation;
  assert.ok(summary);
  assert.equal(summary.transferred_amount, 86725600);
  assert.equal(summary.transfer_count, 34);
  summary.transferred_amount = 7000000;
  assert.equal(companyDetailSchema.parse(company).cash_truth.own_account_circulation?.transferred_amount, 7000000);
  assert.equal(company.cash_truth.components.find((item) => item.category === "circulation")?.gross_movement, 173451200);
});

test("los JSON anteriores siguen siendo válidos sin inventar un agregado de cuentas propias", () => {
  const company = example();
  delete company.cash_truth.own_account_circulation;
  assert.equal(companyDetailSchema.parse(company).cash_truth.own_account_circulation, undefined);
  company.cash_truth.own_account_circulation = null;
  assert.equal(companyDetailSchema.parse(company).cash_truth.own_account_circulation, null);
});

test("cero transferido es un dato válido, distinto de no disponer de datos", () => {
  const company = example();
  assert.ok(company.cash_truth.own_account_circulation);
  company.cash_truth.own_account_circulation.transferred_amount = 0;
  company.cash_truth.own_account_circulation.transfer_count = 0;
  company.cash_truth.own_account_circulation.evidence_refs = [];
  company.cash_truth.account_flows = null;
  assert.equal(companyDetailSchema.parse(company).cash_truth.own_account_circulation?.transferred_amount, 0);
});

test("el agregado de cuentas propias rechaza importes, recuentos y referencias inválidos", () => {
  for (const mutate of [
    (company: ReturnType<typeof example>) => { company.cash_truth.own_account_circulation!.transferred_amount = -1; },
    (company: ReturnType<typeof example>) => { company.cash_truth.own_account_circulation!.transfer_count = 1.5; },
    (company: ReturnType<typeof example>) => { company.cash_truth.own_account_circulation!.transfer_count = 0; },
    (company: ReturnType<typeof example>) => { company.cash_truth.own_account_circulation!.transferred_amount = 0; },
    (company: ReturnType<typeof example>) => {
      company.cash_truth.own_account_circulation!.transferred_amount = 0;
      company.cash_truth.own_account_circulation!.transfer_count = 0;
    },
    (company: ReturnType<typeof example>) => { company.cash_truth.own_account_circulation!.evidence_refs = ["inexistente"]; },
  ]) {
    const company = example();
    assert.ok(company.cash_truth.own_account_circulation);
    mutate(company);
    assert.equal(companyDetailSchema.safeParse(company).success, false);
  }
});
