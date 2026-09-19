"use client";

import Link from "next/link";
import { useState } from "react";
import type { GroupDetail, GroupInsight, GroupMetric } from "@/types/groupDetail";
import { dateLabel, severityLabels, trajectoryLabels } from "@/lib/companyFormat";
import { groupMoney, groupScore, priorityOrder, roleLabels } from "@/lib/groupPresentation";
import { EvidenceButton, type OpenEvidence } from "@/components/insights/InsightPrimitives";
import { GroupLinks } from "./GroupLinks";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

function Metric({ label, metric, group, onOpen }: { label: string; metric: GroupMetric; group: GroupDetail; onOpen: OpenEvidence }) {
  return <div className={styles.groupMetric}><span>{label}</span><strong>{groupMoney(metric.value)}</strong><small>{metric.covered_company_ids.length} de {group.members.length} sociedades observadas cubiertas</small><p>{metric.explanation}</p><EvidenceButton refs={metric.evidence_refs} title={label} onOpen={onOpen} /></div>;
}

function Insights({ items, group, onOpen }: { items: GroupInsight[]; group: GroupDetail; onOpen: OpenEvidence }) {
  return <div className={styles.insightList}>{items.map((item) => <article key={item.id}>
    <span className={`${base.severity} ${base[item.severity]}`}>Prioridad {severityLabels[item.severity].toLowerCase()}</span><h3>{item.title}</h3><p>{item.explanation}</p>
    <GroupLinks group={group} companies={item.company_refs} relations={item.relation_refs} /><EvidenceButton refs={item.evidence_refs} title={item.title} onOpen={onOpen} />
  </article>)}</div>;
}

export function GroupOverview({ group, onOpen }: { group: GroupDetail; onOpen: OpenEvidence }) {
  const [query, setQuery] = useState("");
  const [trajectory, setTrajectory] = useState("all");
  const members = [...group.members].filter((member) => member.company_id.toLowerCase().includes(query.toLowerCase()) && (trajectory === "all" || (member.trajectory ?? "unknown") === trajectory)).sort((a, b) => priorityOrder[a.attention] - priorityOrder[b.attention]);
  const internal = group.members.filter((member) => ["provider", "receiver", "both"].includes(member.role));
  return <>
    <section className={styles.summaryStrip} aria-label="Magnitudes observadas del grupo">
      <Metric label="Liquidez disponible observada" metric={group.available_liquidity} group={group} onOpen={onOpen} />
      <Metric label="Deuda externa identificada" metric={group.identified_debt} group={group} onOpen={onOpen} />
      <Metric label={`Obligaciones · ${group.obligations.horizon}`} metric={group.obligations} group={group} onOpen={onOpen} />
    </section>
    <section className={base.panel} aria-label="Sociedades del grupo observado">
      <div className={styles.panelHeading}><div><span className={base.eyebrow}>Salud financiera, sociedad a sociedad</span><h2>Dónde prestar atención</h2><p>Sin promediar el Health Score del grupo. Las cuatro dimensiones se muestran en escala 0–100.</p></div><span className={base.periodBadge}>{group.members.length} sociedades observadas</span></div>
      <div className={styles.filters}>
        <label>Buscar sociedad<input type="search" aria-label="Buscar sociedad" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="COMP_…" /></label>
        <label>Trayectoria<select aria-label="Trayectoria" value={trajectory} onChange={(event) => setTrajectory(event.target.value)}><option value="all">Todas las trayectorias</option><option value="deteriorating">Deteriorándose</option><option value="stable">Estable</option><option value="improving">Mejorando</option><option value="unknown">Sin evaluar</option></select></label>
        <span role="status" className={base.smallText}>{members.length} {members.length === 1 ? "sociedad visible" : "sociedades visibles"} · prioridad suministrada por Data</span>
      </div>
      {members.length ? <div className={base.tableScroll} tabIndex={0} role="region" aria-label="Tabla de sociedades"><table className={styles.memberTable}>
        <caption>Datos a {dateLabel(group.as_of)}. Obligaciones: {group.obligations.horizon}. Un guion significa que falta el dato, no cero.</caption>
        <thead><tr><th scope="col">Sociedad / trayectoria</th><th scope="col">Health Score</th><th scope="col">Generación de caja</th><th scope="col">Momentum</th><th scope="col">Resiliencia</th><th scope="col">Deuda y obligaciones</th><th scope="col">Liquidez disponible</th><th scope="col">Deuda identificada</th><th scope="col">Obligaciones próximas</th><th scope="col">Detalle</th></tr></thead>
        <tbody>{members.map((member) => <tr key={member.company_id}>
          <th scope="row"><Link href={`/companies/${member.company_id}`} className={styles.companyLink}>{member.company_id}</Link><small>{member.trajectory ? trajectoryLabels[member.trajectory] : "Sin evaluar"}</small><small>{roleLabels[member.role]}</small></th>
          <td><strong className={styles.memberHealth}>{groupScore(member.health_score)}</strong></td><td>{groupScore(member.dimensions.cash_generation)}</td><td>{groupScore(member.dimensions.momentum)}</td><td>{groupScore(member.dimensions.resilience)}</td><td>{groupScore(member.dimensions.debt)}</td>
          <td className={base.numeric}>{groupMoney(member.available_liquidity)}</td><td className={base.numeric}>{groupMoney(member.identified_debt)}</td><td className={base.numeric}>{groupMoney(member.obligations_due)}</td>
          <td><Link className={base.evidenceButton} href={`/groups/${group.group_id}/network?company=${member.company_id}`}>Ver en la red</Link><EvidenceButton refs={member.evidence_refs} title={`Sociedad ${member.company_id}`} onOpen={onOpen} /></td>
        </tr>)}</tbody>
      </table></div> : <p className={base.emptyState}>{group.members.length ? "No hay sociedades que coincidan con estos filtros." : "No hay sociedades con análisis disponible en el grupo observado."}</p>}
    </section>
    <div className={styles.twoColumns}>
      <section className={base.panel} aria-label="Señales principales del grupo"><div className={styles.panelHeading}><div><h2>Lo que merece atención</h2><p>Señales preparadas para orientar la revisión.</p></div></div>{group.insights.length ? <Insights items={group.insights} group={group} onOpen={onOpen} /> : <p className={base.emptyState}>Sin señales suficientemente respaldadas disponibles.</p>}</section>
      <section className={base.panel} aria-label="Concentración y dependencias"><div className={styles.panelHeading}><div><h2>Concentración y dependencias</h2><p>El agregado no debe ocultar dónde se concentran los recursos.</p></div></div>{group.concentration.length ? <Insights items={group.concentration} group={group} onOpen={onOpen} /> : <p className={base.emptyState}>Concentración no evaluable con los datos suministrados.</p>}</section>
    </div>
    <section className={base.panel} aria-label="Roles de liquidez interna">
      <div className={styles.panelHeading}><div><h2>Quién aporta y quién recibe</h2><p>Roles y flujos internos suministrados para {group.period}. No son saldos ni una autorización para redistribuir fondos.</p></div><Link className={base.evidenceButton} href={`/groups/${group.group_id}/network`}>Explorar la red financiera →</Link></div>
      {internal.length ? <div className={styles.roleList}>{internal.map((member) => <article key={member.company_id}><div><Link href={`/companies/${member.company_id}`} className={styles.companyLink}>{member.company_id}</Link><span className={styles.roleBadge}>{roleLabels[member.role]}</span></div><dl><div><dt>Recibe internamente</dt><dd>{groupMoney(member.internal_received)}</dd></div><div><dt>Aporta internamente</dt><dd>{groupMoney(member.internal_provided)}</dd></div><div><dt>Generación operativa neta</dt><dd>{groupMoney(member.cash_generation_net, true)}</dd></div></dl><p>{member.summary}</p><Link className={base.evidenceButton} href={`/groups/${group.group_id}/network?company=${member.company_id}`}>Revisar conexiones →</Link></article>)}</div> : <p className={base.emptyState}>No hay roles de aportante o receptor identificados con suficiente evidencia. No implica ausencia de relaciones.</p>}
    </section>
    <div className={styles.twoColumns}>
      <section className={base.panel} aria-label="Alertas del grupo"><div className={styles.panelHeading}><div><h2>Alertas del grupo</h2><p>Prioridad y explicaciones recibidas del análisis.</p></div></div>{group.alerts.length ? <Insights items={[...group.alerts].sort((a, b) => priorityOrder[a.severity] - priorityOrder[b.severity])} group={group} onOpen={onOpen} /> : <p className={base.emptyState}>No hay alertas preparadas. No es una garantía de ausencia de riesgos.</p>}</section>
      <section className={base.panel} aria-label="Cambios recientes"><div className={styles.panelHeading}><div><h2>Cambios recientes</h2><p>Qué ha cambiado en el grupo observado.</p></div></div><div className={styles.changeList}>{group.recent_changes.map((change) => <article key={change.id}><time dateTime={change.date}>{dateLabel(change.date)}</time><h3>{change.title}</h3><p>{change.explanation}</p><GroupLinks group={group} companies={change.company_refs} relations={change.relation_refs} /><EvidenceButton refs={change.evidence_refs} title={change.title} onOpen={onOpen} /></article>)}</div>{!group.recent_changes.length && <p className={base.emptyState}>No hay cambios recientes suministrados.</p>}</section>
    </div>
    <Link className={styles.nextStep} href={`/groups/${group.group_id}/network`}><span><small>Siguiente paso</small><strong>Entender cómo circula la liquidez</strong></span><span aria-hidden="true">→</span></Link>
  </>;
}
