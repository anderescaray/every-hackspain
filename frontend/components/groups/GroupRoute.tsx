import Link from "next/link";
import { notFound } from "next/navigation";
import { getGroupDetail, GroupDataError } from "@/services/groupData";
import { CompanyDataError, getCompanyDetail } from "@/services/companyData";
import type { GroupView } from "@/types/groupDetail";
import { withCompanyContext } from "@/lib/analysisNavigation";
import { AnalysisShell } from "@/components/navigation/AnalysisShell";
import { GroupIntelligence } from "./GroupIntelligence";
import base from "@/components/insights/insights.module.css";

export async function GroupRoute({ groupId, view, initialRelation, initialCompany, contextCompany }: { groupId: string; view: GroupView; initialRelation?: string; initialCompany?: string; contextCompany?: string }) {
  if (!/^GROUP_\d{4,10}$/.test(groupId)) notFound();
  let group;
  let invalid = false;
  try {
    group = await getGroupDetail(groupId);
  } catch (error) {
    if (!(error instanceof GroupDataError)) throw error;
    invalid = true;
  }
  const requestedCompany = contextCompany ?? initialCompany;
  let companyId = requestedCompany && group?.members.some((member) => member.company_id === requestedCompany) ? requestedCompany : null;
  if (!companyId && requestedCompany && /^COMP_\d{4,10}$/.test(requestedCompany)) {
    try {
      const company = await getCompanyDetail(requestedCompany);
      if (company?.group_id === groupId) companyId = company.company_id;
    } catch (error) {
      if (!(error instanceof CompanyDataError)) throw error;
    }
  }
  companyId ??= group?.members[0]?.company_id ?? null;
  return <AnalysisShell companyId={companyId} groupId={groupId} view={view}>
    {!group ? <main className={`${base.page} ${base.routeState}`}><span className={base.eyebrow}>Embat Pulse</span><h1>{invalid ? "Los datos del grupo necesitan revisión." : "Datos del grupo no disponibles."}</h1><p>{groupId} · {invalid ? "El archivo no cumple el contrato esperado. No se muestran conclusiones parciales." : "No hay datos para este grupo. No se inventan sociedades, relaciones ni recomendaciones."}</p><Link className={base.primaryButton} href={withCompanyContext(`/groups/${groupId}`, companyId)}>Volver al grupo</Link></main> : <GroupIntelligence key={`${group.group_id}:${view}:${initialRelation ?? ""}:${initialCompany ?? ""}`} group={group} view={view} initialRelation={initialRelation} initialCompany={initialCompany} />}
  </AnalysisShell>;
}
