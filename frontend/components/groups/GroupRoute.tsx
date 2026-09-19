import Link from "next/link";
import { notFound } from "next/navigation";
import { getGroupDetail, GroupDataError } from "@/services/groupData";
import type { GroupView } from "@/types/groupDetail";
import { GroupIntelligence } from "./GroupIntelligence";
import base from "@/components/insights/insights.module.css";

export async function GroupRoute({ groupId, view, initialRelation, initialCompany }: { groupId: string; view: GroupView; initialRelation?: string; initialCompany?: string }) {
  if (!/^GROUP_\d{4,10}$/.test(groupId)) notFound();
  let group;
  let invalid = false;
  try {
    group = await getGroupDetail(groupId);
  } catch (error) {
    if (!(error instanceof GroupDataError)) throw error;
    invalid = true;
  }
  if (!group) return <main className={`${base.page} ${base.routeState}`}><span className={base.eyebrow}>Embat Pulse · Inteligencia de grupo</span><h1>{invalid ? "Los datos del grupo necesitan revisión." : "Datos de análisis del grupo todavía no disponibles."}</h1><p>{groupId} · {invalid ? "El archivo no cumple el contrato esperado. No se muestran conclusiones parciales." : "El análisis solicitado no está disponible. No se inventan sociedades, relaciones ni recomendaciones mientras faltan los datos del grupo."}</p><Link className={base.primaryButton} href={`/groups/${groupId}`}>Volver a comprobar</Link></main>;
  return <GroupIntelligence key={`${group.group_id}:${view}:${initialRelation ?? ""}:${initialCompany ?? ""}`} group={group} view={view} initialRelation={initialRelation} initialCompany={initialCompany} />;
}
