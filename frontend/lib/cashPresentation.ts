import type { CashTruth } from "../types/companyDetail";
import { cashCategoryLabel } from "./companyFormat";

export function getSupportPresentation(cash: CashTruth, groupId: string | null) {
  const component = cash.components.find((item) => item.category === "support");
  const label = cashCategoryLabel("support", groupId);
  const net = component?.net_amount;
  const origin = groupId === null ? "financiación o apoyo externo" : "apoyo intragrupo";
  const direction = groupId === null ? "a financiadores o aportantes externos" : "al grupo";
  const source = groupId === null ? "de financiación o aportes externos" : "del grupo";
  const description = net == null ? `Importe neto de ${origin} no identificado.` : net < 0 ? `Salida neta de liquidez ${direction}.` : net === 0 ? "Hay movimientos identificados, pero sus entradas y salidas se compensan en neto." : `Liquidez neta recibida ${source}.`;
  return {
    component,
    label,
    visible: component !== undefined && component.gross_movement > 0,
    unavailable: component === undefined || (component.gross_movement === 0 && net === null),
    description,
  };
}

export function getIdentifiedCashTotal(cash: CashTruth) {
  const cents = (value: number | null | undefined) => {
    if (value == null || !Number.isFinite(value)) return null;
    const rounded = Math.round((value + Math.sign(value) * Number.EPSILON) * 100);
    return Number.isSafeInteger(rounded) ? rounded || 0 : null;
  };
  const operating = cents(cash.components.find((item) => item.category === "operating")?.net_amount);
  const support = cents(cash.components.find((item) => item.category === "support")?.net_amount);
  const sum = operating !== null && support !== null ? operating + support : null;
  return {
    operating: operating === null ? null : operating / 100,
    support: support === null ? null : support / 100,
    total: sum !== null && Number.isSafeInteger(sum) ? sum / 100 : null,
  };
}

export function getTreasuryState(cash: CashTruth) {
  if (!cash.own_account_circulation) return "unavailable";
  if (cash.own_account_circulation.transfer_count > 0) return "identified";
  if (cash.account_flows?.transfers.some((transfer) => transfer.kind === "own_transfer" && transfer.match_status !== "matched")) return "pending";
  return "none";
}
