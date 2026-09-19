import type { AccountTransfer, CashAccount, TransactionEvidenceRef } from "../types/companyDetail";

export const accountOwnershipLabels: Record<CashAccount["ownership"], string> = {
  company: "Cuenta de esta empresa",
  group_company: "Cuenta de otra sociedad del grupo",
  external: "Cuenta de un tercero",
  unknown: "Titularidad no confirmada",
};

export const transferKindLabels: Record<AccountTransfer["kind"], string> = {
  own_transfer: "Entre cuentas propias",
  intragroup_transfer: "Entre empresas del grupo",
  external_transfer: "Con terceros",
  unresolved: "Origen o destino sin identificar",
};

export const transferMatchLabels: Record<AccountTransfer["match_status"], string> = {
  matched: "Salida y entrada emparejadas",
  partial: "Solo un tramo observado",
  unmatched: "Sin emparejar",
};

export function transferEvidenceRecords(transfer: AccountTransfer): TransactionEvidenceRef[] {
  return [transfer.debit, transfer.credit].filter((record): record is TransactionEvidenceRef => record !== null);
}

export function transferEvidenceRefs(transfer: AccountTransfer): string[] {
  return [...new Set(transferEvidenceRecords(transfer).map((record) => record.evidence_id))];
}
