export const companySections = [
  { id: "health-score", label: "Health Score", icon: "health" },
  { id: "trajectory", label: "Tendencia", icon: "trend" },
  { id: "cash-truth", label: "Origen de la caja", icon: "cash" },
  { id: "scenarios", label: "Escenarios", icon: "scenarios" },
] as const;

export function withCompanyContext(href: string, companyId: string | null): string {
  if (!companyId || !/^COMP_\d{4,10}$/.test(companyId) || !href.startsWith("/groups/")) return href;
  const hashIndex = href.indexOf("#");
  const hash = hashIndex < 0 ? "" : href.slice(hashIndex);
  const address = hashIndex < 0 ? href : href.slice(0, hashIndex);
  const queryIndex = address.indexOf("?");
  const pathname = queryIndex < 0 ? address : address.slice(0, queryIndex);
  const query = new URLSearchParams(queryIndex < 0 ? "" : address.slice(queryIndex + 1));
  query.set("entity", companyId);
  return `${pathname}?${query.toString()}${hash}`;
}
