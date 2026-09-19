export function money(value: number, signed = false): string {
  const absolute = Math.abs(value);
  const divisor = absolute >= 1000000 ? 1000000 : absolute >= 1000 ? 1000 : 1;
  const suffix = divisor === 1000000 ? "M" : divisor === 1000 ? "k" : "";
  const amount = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(absolute / divisor);
  return `${value < 0 ? "−" : signed && value > 0 ? "+" : ""}€${amount}${suffix}`;
}

export function exactMoney(value: number): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(value);
}

export function dateLabel(value: string, monthOnly = false): string {
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", ...(monthOnly ? {} : { day: "numeric" }), timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function signedNumber(value: number): string {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 }).format(Math.abs(value))}`;
}
