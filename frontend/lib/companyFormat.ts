import type { CashCategory, CompanyAlert, Trajectory } from "../types/companyDetail";

export const trajectoryLabels: Record<Trajectory, string> = {
  improving: "Mejorando",
  deteriorating: "Deteriorándose",
  stable: "Estable",
};

export const cashCategoryLabels: Record<CashCategory, string> = {
  operating: "Generación operativa",
  circulation: "Circulación de tesorería",
  support: "Financiación o apoyo",
  uncertain: "No identificado",
};

export function cashCategoryLabel(category: CashCategory, groupId: string | null): string {
  return category === "support" ? groupId === null ? "Financiación o apoyo externo" : "Apoyo intragrupo" : cashCategoryLabels[category];
}

export const severityLabels: Record<CompanyAlert["severity"], string> = {
  high: "Alta",
  medium: "Media",
  low: "Baja",
};

export function confidenceLabel(value: number | null): string {
  return value === null ? "No evaluable" : value >= 80 ? "Alta" : value >= 60 ? "Media" : "Limitada";
}

export function numberLabel(value: number, decimals = 1): string {
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: decimals }).format(value);
}

export function money(value: number, signed = false, decimals = 2): string {
  const absolute = Math.abs(value);
  const divisor = absolute >= 1000000 ? 1000000 : absolute >= 1000 ? 1000 : 1;
  const suffix = divisor === 1000000 ? " M€" : divisor === 1000 ? " mil €" : " €";
  return `${value < 0 ? "−" : signed && value > 0 ? "+" : ""}${numberLabel(absolute / divisor, decimals)}${suffix}`;
}

export function exactMoney(value: number): string {
  return new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
}

export function dateLabel(value: string, monthOnly = false): string {
  return new Intl.DateTimeFormat("es-ES", { month: "short", year: "numeric", ...(monthOnly ? {} : { day: "numeric" }), timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function signedNumber(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${numberLabel(Math.abs(value))}`;
}
