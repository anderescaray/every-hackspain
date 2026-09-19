import assert from "node:assert/strict";
import test from "node:test";
import { getSupportPresentation, getTreasuryState } from "../lib/cashPresentation";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

function cash() { return structuredClone(fixtureCompanies.COMP_0356.cash_truth); }

test("apoyo visible con grupo y financiación externa sin grupo", () => {
  assert.equal(getSupportPresentation(cash(), "GROUP_0042").label, "Apoyo intragrupo");
  const external = getSupportPresentation(cash(), null);
  assert.equal(external.label, "Financiación o apoyo externo");
  assert.equal(external.visible, true);
  assert.match(external.description, /extern/);
});

test("sin movimientos de apoyo no hay tarjeta, con independencia del grupo", () => {
  const data = cash();
  const support = data.components.find((item) => item.category === "support")!;
  support.gross_movement = 0;
  support.net_amount = 0;
  for (const group of [null, "GROUP_0042"]) assert.equal(getSupportPresentation(data, group).visible, false);
  support.net_amount = null;
  assert.equal(getSupportPresentation(data, null).visible, false);
  assert.equal(getSupportPresentation(data, null).unavailable, true);
});

test("neto cero no es ausencia: se conserva apoyo si hay entradas y salidas", () => {
  const data = cash();
  data.components.find((item) => item.category === "support")!.net_amount = 0;
  assert.equal(getSupportPresentation(data, null).visible, true);
});

test("tesorería distingue movimientos, ausencia confirmada, pendientes y datos ausentes", () => {
  const data = cash();
  assert.equal(getTreasuryState(data), "identified");
  data.own_account_circulation = null;
  assert.equal(getTreasuryState(data), "unavailable");
  data.own_account_circulation = { transferred_amount: 0, transfer_count: 0, explanation: "Sin traslados identificados en el periodo.", confidence: 90, evidence_refs: [] };
  data.account_flows = null;
  assert.equal(getTreasuryState(data), "none");
  data.account_flows = cash().account_flows;
  data.account_flows!.transfers[0].match_status = "partial";
  assert.equal(getTreasuryState(data), "pending");
});

test("una empresa independiente puede tener cuentas propias sin grupo", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  company.group_id = null;
  company.cash_truth.account_flows = null;
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  const original = fixtureCompanies.COMP_0356.cash_truth.account_flows!;
  company.cash_truth.account_flows = { ...structuredClone(original), accounts: original.accounts.slice(0, 2).map((account) => ({ ...account, owner_group_id: null })), transfers: [original.transfers[0]] };
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  company.cash_truth.account_flows.accounts.push({ ...original.accounts[2], owner_group_id: null });
  assert.equal(companyDetailSchema.safeParse(company).success, false);
});

test("dos empresas sin grupo no se convierten en sociedades del mismo grupo", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  company.group_id = null;
  company.cash_truth.account_flows!.accounts = company.cash_truth.account_flows!.accounts.map((account) => ({ ...account, owner_group_id: null, ownership: account.ownership === "group_company" ? "external" : account.ownership }));
  company.cash_truth.account_flows!.transfers[1].kind = "external_transfer";
  assert.equal(companyDetailSchema.safeParse(company).success, true);
});
