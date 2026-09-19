import type { GroupMember, GroupRecommendation, GroupRelation, GroupView } from "../types/groupDetail";
import { money, numberLabel } from "./companyFormat";

export const groupTabs: { key: GroupView; label: string; description: string; suffix: string }[] = [
  { key: "overview", label: "Visión general", description: "Magnitudes y sociedades a revisar", suffix: "" },
  { key: "network", label: "Red financiera", description: "Grafo de flujos del grupo", suffix: "/network" },
  { key: "recommendations", label: "Recomendaciones", description: "Revisiones priorizadas", suffix: "/recommendations" },
];
export const roleLabels: Record<GroupMember["role"], string> = { provider: "Aportante", receiver: "Receptora", both: "Aporta y recibe", none_identified: "Sin rol interno identificado", unknown: "Rol no determinado" };
export const relationStatusLabels: Record<GroupRelation["status"], string> = { identified: "Identificada · evidencia alta", candidate: "Candidata · por confirmar", unknown: "Desconocida · no atribuible" };
export const relationKindLabels: Record<GroupRelation["kind"], string> = { support: "Apoyo financiero", transfer: "Transferencia intragrupo", cash_pooling: "Centralización de tesorería", treasury_circulation: "Circulación identificada", commercial: "Relación comercial", unknown: "Tipo no determinado" };
export const relationChangeLabels: Record<GroupRelation["change"], string> = { new: "Nueva relación observada", increasing: "Volumen en aumento", stable: "Sin cambio destacado", decreasing: "Volumen en descenso", unknown: "Cambio no evaluable" };
export const recommendationLabels: Record<GroupRecommendation["type"], string> = { recurring_support: "Apoyo recurrente", liquidity_distribution: "Distribución de liquidez", increasing_dependency: "Dependencia", funding_structure: "Financiación", concentration: "Concentración", stress_liquidity: "Escenarios de revisión", insufficient_evidence: "Evidencia insuficiente" };
export const signalLabels: Record<GroupRecommendation["signals"][number]["source"], string> = { health: "Health Score", momentum: "Momentum", resilience: "Resiliencia", cash_truth: "Origen de la caja", network: "Red financiera", liquidity: "Liquidez", obligations: "Deuda y obligaciones", outlook: "Perspectiva futura", concentration: "Concentración", confidence: "Calidad de los datos" };
export const priorityOrder = { high: 0, medium: 1, low: 2, unknown: 3 };
export const groupMoney = (value: number | null, signed = false) => value === null ? "No disponible" : money(value, signed);
export const groupScore = (value: number | null) => value === null ? "—" : numberLabel(value, 1);
export const relationName = (relation: GroupRelation) => `${relation.from_company_id ?? "Origen no identificado"} → ${relation.to_company_id ?? "Destino no identificado"}`;
export const relationHref = (groupId: string, relationId: string) => `/groups/${groupId}/network?relation=${encodeURIComponent(relationId)}`;
