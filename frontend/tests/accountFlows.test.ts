import assert from "node:assert/strict";
import test from "node:test";
import { companyDetailSchema } from "../types/companyDetail";
import { fixtureCompanies } from "./fixtures/companyDetails";

function example() {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  assert.ok(company.cash_truth.account_flows);
  return company as typeof company & { cash_truth: typeof company.cash_truth & { account_flows: NonNullable<typeof company.cash_truth.account_flows> } };
}

test("las cuentas y transferencias no son obligatorias para los JSON existentes", () => {
  const company = structuredClone(fixtureCompanies.COMP_0356);
  delete company.cash_truth.account_flows;
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  company.cash_truth.account_flows = null;
  assert.equal(companyDetailSchema.safeParse(company).success, true);
});

test("traslado propio, apoyo intragrupo y origen desconocido están separados", () => {
  const company = example();
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  const [own, group, unknown] = company.cash_truth.account_flows.transfers;
  assert.equal(own.kind, "own_transfer");
  assert.equal(own.amount, 2500000);
  assert.equal(own.gross_movement, 5000000);
  assert.equal(own.company_net_amount, 0);
  assert.equal(group.kind, "intragroup_transfer");
  assert.equal(group.company_net_amount, 600000);
  assert.equal(group.category, "support");
  assert.equal(unknown.kind, "unresolved");
  assert.equal(unknown.company_net_amount, null);
  assert.equal(company.cash_truth.components.find((component) => component.category === "operating")?.net_amount, 25600);
  assert.equal(company.cash_truth.total_gross_movement, 179046800);
});

test("no se infiere emparejamiento ni neto cero cuando solo se observa una salida propia", () => {
  const company = example();
  const transfer = company.cash_truth.account_flows.transfers[0];
  transfer.credit = null;
  transfer.match_status = "partial";
  transfer.company_net_amount = null;
  transfer.gross_movement = 2500000;
  transfer.category = "uncertain";
  const debit = company.evidence[0].rows[0];
  assert.ok(debit.kind === "transaction");
  debit.category = "uncertain";
  assert.equal(companyDetailSchema.safeParse(company).success, true);
  transfer.company_net_amount = 0;
  assert.equal(companyDetailSchema.safeParse(company).success, false);
});

test("una transferencia del grupo no es necesariamente apoyo financiero", () => {
  const company = example();
  company.cash_truth.account_flows.transfers[1].category = "operating";
  const row = company.evidence[0].rows.find((item) => item.id === "DEMO-TX-007");
  assert.ok(row && row.kind === "transaction");
  row.category = "operating";
  assert.equal(companyDetailSchema.safeParse(company).success, true);
});

test("se rechazan titularidad, referencias o emparejamientos incompatibles", () => {
  const mutations: ((company: ReturnType<typeof example>) => void)[] = [
    (company) => { company.cash_truth.account_flows.accounts[0].owner_company_id = "COMP_9999"; },
    (company) => { company.cash_truth.account_flows.accounts[2].owner_group_id = "GROUP_9999"; },
    (company) => { company.cash_truth.account_flows.accounts[0].ownership_source = null; },
    (company) => { company.cash_truth.account_flows.accounts.push(company.cash_truth.account_flows.accounts[0]); },
    (company) => { company.cash_truth.account_flows.transfers[0].from_account_id = "NO_EXISTE"; },
    (company) => { company.cash_truth.account_flows.transfers[0].to_account_id = company.cash_truth.account_flows.transfers[0].from_account_id; },
    (company) => { company.cash_truth.account_flows.transfers[0].category = "support"; },
    (company) => { company.cash_truth.account_flows.transfers[0].company_net_amount = 2500000; },
    (company) => { company.cash_truth.account_flows.transfers[0].credit = null; },
    (company) => { company.cash_truth.account_flows.transfers[0].credit!.transaction_id = "NO_EXISTE"; },
    (company) => { company.cash_truth.account_flows.transfers[0].credit!.evidence_id = "ar-timing"; },
    (company) => { company.cash_truth.account_flows.transfers[0].amount = 100; },
    (company) => { const row = company.evidence[0].rows[1]; if (row.kind === "transaction") row.transaction_date = "2026-09-01"; },
    (company) => {
      company.evidence.push({ ...structuredClone(company.evidence[0]), id: "copied-evidence" });
      const transfer = structuredClone(company.cash_truth.account_flows.transfers[0]);
      transfer.id = "duplicate-physical-transfer";
      transfer.debit!.evidence_id = "copied-evidence";
      transfer.credit!.evidence_id = "copied-evidence";
      company.cash_truth.account_flows.transfers.push(transfer);
    },
    (company) => { company.cash_truth.account_flows.transfers[0].gross_movement = 2500000; },
    (company) => { company.cash_truth.account_flows.transfers[1].kind = "own_transfer"; },
    (company) => { company.cash_truth.account_flows.transfers[2].company_net_amount = 0; },
    (company) => { company.cash_truth.account_flows.transfers[2].category = "support"; },
    (company) => { company.cash_truth.account_flows.transfers.push(company.cash_truth.account_flows.transfers[0]); },
    (company) => { const row = company.evidence[0].rows[0]; if (row.kind === "transaction") row.account_id = "NO_EXISTE"; },
  ];
  for (const mutate of mutations) {
    const company = example();
    mutate(company);
    assert.equal(companyDetailSchema.safeParse(company).success, false, mutate.toString());
  }
});
