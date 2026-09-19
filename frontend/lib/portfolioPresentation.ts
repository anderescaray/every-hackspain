import type { Portfolio, PortfolioAttention, PortfolioItem, PortfolioStatus } from "../types/portfolio";
import { isCompleteStatus } from "../types/pulse";
import type { Trajectory } from "../types/companyDetail";

export const SORT_KEYS = ["attention", "health_score", "delta_vs_prev", "confidence", "support_dependency_ratio", "company_id"] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export type PortfolioQuery = {
  trajectory: Trajectory | "all";
  attention: PortfolioAttention | "all";
  status: PortfolioStatus | "all";
  group: string;
  q: string;
  sort: SortKey;
  order: "asc" | "desc";
};

export const DEFAULT_QUERY: PortfolioQuery = { trajectory: "all", attention: "all", status: "all", group: "", q: "", sort: "attention", order: "desc" };

const ATTENTION_RANK: Record<PortfolioAttention, number> = { high: 3, medium: 2, low: 1, unknown: 0 };

export const attentionLabels: Record<PortfolioAttention, string> = { high: "Alta", medium: "Media", low: "Baja", unknown: "Sin evaluar" };
export const statusLabels: Record<PortfolioStatus, string> = { complete: "Identificada", complete_verified: "Identificada · verificada", complete_bounded: "Identificada · acotada", partial: "No plenamente identificada", insufficient_evidence: "Evidencia insuficiente" };
export const sortLabels: Record<SortKey, string> = {
  attention: "Atención", health_score: "Puntuación principal", delta_vs_prev: "Cambio Extended", confidence: "Cobertura",
  support_dependency_ratio: "Dependencia de apoyo", company_id: "Identificador",
};

// v1.0.1 is a reproducible historical snapshot; v1.1 never falls back from Operating to Extended.
export function primaryPortfolioScore(item: PortfolioItem): number | null {
  return item.operating_health === undefined ? item.health_score : item.operating_health;
}

function pick<T extends string>(value: string | undefined, allowed: readonly T[], fallback: T): T {
  return value !== undefined && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export function parseQuery(params: Record<string, string | string[] | undefined>): PortfolioQuery {
  const single = (key: string) => { const value = params[key]; return Array.isArray(value) ? value[0] : value; };
  return {
    trajectory: pick(single("trajectory"), ["all", "improving", "deteriorating", "stable"] as const, "all"),
    attention: pick(single("attention"), ["all", "high", "medium", "low", "unknown"] as const, "all"),
    status: pick(single("status"), ["all", "complete", "complete_verified", "complete_bounded", "partial", "insufficient_evidence"] as const, "all"),
    group: (single("group") ?? "").trim().slice(0, 40),
    q: (single("q") ?? "").trim().slice(0, 40),
    sort: pick(single("sort"), SORT_KEYS, "attention"),
    order: pick(single("order"), ["asc", "desc"] as const, "desc"),
  };
}

export function filterItems(items: PortfolioItem[], query: PortfolioQuery): PortfolioItem[] {
  const q = query.q.toUpperCase();
  const group = query.group.toUpperCase();
  return items.filter((item) =>
    (query.trajectory === "all" || item.trajectory === query.trajectory)
    && (query.attention === "all" || item.attention === query.attention)
    && (query.status === "all" || (query.status === "complete" ? isCompleteStatus(item.score_status) : item.score_status === query.status))
    && (!group || (item.group_id ?? "").toUpperCase() === group)
    && (!q || item.company_id.includes(q) || (item.group_id ?? "").toUpperCase().includes(q)));
}

function value(item: PortfolioItem, key: SortKey): number | string | null {
  if (key === "attention") return ATTENTION_RANK[item.attention];
  if (key === "company_id") return item.company_id;
  if (key === "health_score") return primaryPortfolioScore(item);
  return item[key];
}

export function sortItems(items: PortfolioItem[], key: SortKey, order: "asc" | "desc"): PortfolioItem[] {
  const direction = order === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const va = value(a, key), vb = value(b, key);
    if (va === null && vb === null) return a.company_id.localeCompare(b.company_id);
    if (va === null) return 1;              // los nulos siempre al final, sea cual sea el orden
    if (vb === null) return -1;
    if (typeof va === "string" && typeof vb === "string") return direction * va.localeCompare(vb);
    if (va === vb) {
      if (key === "attention") return (primaryPortfolioScore(b) ?? -1) - (primaryPortfolioScore(a) ?? -1) || a.company_id.localeCompare(b.company_id);
      return a.company_id.localeCompare(b.company_id);
    }
    return direction * ((va as number) - (vb as number));
  });
}

export function summarize(portfolio: Portfolio) {
  const items = portfolio.items;
  const count = (predicate: (item: PortfolioItem) => boolean) => items.filter(predicate).length;
  return {
    total: items.length,
    scored: count((item) => primaryPortfolioScore(item) !== null),
    improving: count((item) => item.trajectory === "improving"),
    deteriorating: count((item) => item.trajectory === "deteriorating"),
    highAttention: count((item) => item.attention === "high"),
    dependent: count((item) => (item.support_dependency_ratio ?? 0) >= 0.3),
  };
}
