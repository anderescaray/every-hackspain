import assert from "node:assert/strict";
import test from "node:test";
import { getIdentifiedCashTotal } from "../lib/cashPresentation";
import { fixtureCompanies } from "./fixtures/companyDetails";

function example() { return structuredClone(fixtureCompanies.COMP_0356.cash_truth); }

function setNets(operating: number | null, support: number | null) {
  const cash = example();
  cash.components.find((item) => item.category === "operating")!.net_amount = operating;
  cash.components.find((item) => item.category === "support")!.net_amount = support;
  return cash;
}

test("el total es exactamente la suma visible de operación y apoyo", () => {
  const cash = example();
  const original = structuredClone(cash);
  assert.deepEqual(getIdentifiedCashTotal(cash), { operating: 25600, support: 4140000, total: 4165600 });
  assert.deepEqual(cash, original);
});

test("no utiliza circulación, no identificado, bruto ni neto aparente", () => {
  const cash = example();
  cash.components.find((item) => item.category === "circulation")!.net_amount = 999999;
  cash.components.find((item) => item.category === "uncertain")!.net_amount = 210000;
  cash.apparent_net = 99999999;
  cash.total_gross_movement = 999999999;
  assert.equal(getIdentifiedCashTotal(cash).total, 4165600);
});

test("funciona con financiación externa y con ausencia explícita de apoyo", () => {
  assert.equal(getIdentifiedCashTotal(fixtureCompanies.COMP_9001.cash_truth).total, 4165600);
  assert.deepEqual(getIdentifiedCashTotal(fixtureCompanies.COMP_9002.cash_truth), { operating: 3850000, support: 0, total: 3850000 });
});

test("un neto ausente no se sustituye por cero ni por el bruto", () => {
  assert.equal(getIdentifiedCashTotal(setNets(null, 4140000)).total, null);
  assert.equal(getIdentifiedCashTotal(setNets(25600, null)).total, null);
  const cash = example();
  cash.components = cash.components.filter((item) => item.category !== "support");
  assert.equal(getIdentifiedCashTotal(cash).total, null);
});

test("conserva cero y descuenta salidas netas", () => {
  assert.equal(getIdentifiedCashTotal(setNets(0, 0)).total, 0);
  assert.equal(getIdentifiedCashTotal(setNets(-10000, 5000)).total, -5000);
  assert.equal(getIdentifiedCashTotal(setNets(10000, -5000)).total, 5000);
});

test("la suma monetaria usa céntimos para evitar artefactos de coma flotante", () => {
  assert.deepEqual(getIdentifiedCashTotal(setNets(0.1, 0.2)), { operating: 0.1, support: 0.2, total: 0.3 });
  assert.deepEqual(getIdentifiedCashTotal(setNets(1.005, 2.005)), { operating: 1.01, support: 2.01, total: 3.02 });
});

test("no presenta totales no finitos ni fuera de la precisión monetaria segura", () => {
  for (const value of [NaN, Infinity, Number.MAX_VALUE]) assert.equal(getIdentifiedCashTotal(setNets(value, 1)).total, null);
});
