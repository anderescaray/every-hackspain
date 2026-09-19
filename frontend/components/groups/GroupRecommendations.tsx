"use client";

import { useState } from "react";
import type { GroupDetail } from "@/types/groupDetail";
import { severityLabels } from "@/lib/companyFormat";
import { priorityOrder, recommendationLabels, relationName, signalLabels } from "@/lib/groupPresentation";
import { Confidence, EvidenceButton, type OpenEvidence } from "@/components/insights/InsightPrimitives";
import { GroupLinks } from "./GroupLinks";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

export function GroupRecommendations({ group, onOpen, initialRelation }: { group: GroupDetail; onOpen: OpenEvidence; initialRelation?: string }) {
  const [priority, setPriority] = useState("all");
  const [type, setType] = useState("all");
  const [company, setCompany] = useState("all");
  const [relationFilter, setRelationFilter] = useState(group.relations.some((relation) => relation.id === initialRelation) ? initialRelation : undefined);
  const selectedRelation = group.relations.find((relation) => relation.id === relationFilter);
  const items = [...group.recommendations].filter((item) => (priority === "all" || item.priority === priority) && (type === "all" || item.type === type) && (company === "all" || item.company_refs.includes(company)) && (!relationFilter || item.relation_refs.includes(relationFilter))).sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

  return <section className={base.panel} aria-label="Revisiones propuestas de tesorería">
    <div className={styles.panelHeading}><div><span className={base.eyebrow}>Del diagnóstico a la revisión</span><h2>Decisiones que merece la pena estudiar</h2><p>Recomendaciones suministradas por el análisis, no decisiones ejecutadas por la aplicación.</p></div><span className={base.periodBadge}>{group.recommendations.length} revisiones preparadas</span></div>
    <p className={styles.guardrail}><strong>Revisar antes de actuar.</strong> No se ejecutan transferencias ni se considera fungible la caja. Contrasta disponibilidad, obligaciones y restricciones de cada sociedad.</p>
    {selectedRelation && <div className={styles.activeContext}><span>Relación: {relationName(selectedRelation)}</span><button className={base.evidenceButton} onClick={() => setRelationFilter(undefined)}>Quitar filtro de relación</button></div>}
    {initialRelation && !group.relations.some((relation) => relation.id === initialRelation) && <p className={base.emptyState}>La relación solicitada no está en este análisis. Se muestran las revisiones disponibles sin ese filtro.</p>}
    <div className={styles.filters}>
      <label>Prioridad<select aria-label="Prioridad" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="all">Todas las prioridades</option><option value="high">Alta</option><option value="medium">Media</option><option value="low">Baja</option></select></label>
      <label>Tipo de revisión<select aria-label="Tipo de revisión" value={type} onChange={(event) => setType(event.target.value)}><option value="all">Todos los tipos</option>{Object.entries(recommendationLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select></label>
      <label>Sociedad implicada<select aria-label="Sociedad implicada" value={company} onChange={(event) => setCompany(event.target.value)}><option value="all">Todas las sociedades</option>{group.members.map((member) => <option key={member.company_id}>{member.company_id}</option>)}</select></label>
      <button className={base.secondaryButton} onClick={() => { setPriority("all"); setType("all"); setCompany("all"); setRelationFilter(undefined); }}>Restablecer filtros</button>
    </div>
    <p className={base.smallText} role="status">{items.length} {items.length === 1 ? "revisión visible" : "revisiones visibles"}</p>
    <div className={styles.recommendationList}>{items.map((item, index) => <details className={styles.recommendation} key={item.id} open={index === 0}>
      <summary><span className={styles.recommendationRank}>{String(index + 1).padStart(2, "0")}</span><span><span className={`${base.severity} ${base[item.priority]}`}>Prioridad {severityLabels[item.priority].toLowerCase()}</span><strong>{item.title}</strong><small>{recommendationLabels[item.type]} · {item.period}</small></span><span className={styles.expandMarker} aria-hidden="true">+</span></summary>
      <div className={styles.recommendationBody}>
        <p className={styles.recommendationWhy}>{item.explanation}</p>
        <div className={styles.recommendationColumns}><div><h3>Por qué aparece</h3><ul className={styles.signalList}>{item.signals.map((signal, signalIndex) => <li key={`${signal.source}-${signalIndex}`}><span>{signalLabels[signal.source]}</span><p>{signal.observation}</p></li>)}</ul></div>
          <div><h3>Qué revisar</h3><ol className={styles.reviewSteps}>{item.review_steps.map((step) => <li key={step}>{step}</li>)}</ol><div className={styles.constraints}><h4>Antes de tomar una decisión</h4><ul>{item.constraints.map((constraint) => <li key={constraint}>{constraint}</li>)}</ul></div></div></div>
        <div className={styles.recommendationFooter}><Confidence value={item.confidence} /><EvidenceButton refs={item.evidence_refs} title={item.title} onOpen={onOpen} /></div>
        <GroupLinks group={group} companies={item.company_refs} relations={item.relation_refs} />
      </div>
    </details>)}</div>
    {!items.length && <p className={base.emptyState}>{group.recommendations.length ? "No hay recomendaciones que coincidan con estos filtros." : "No se han suministrado recomendaciones. No implica ausencia de riesgos u oportunidades."}</p>}
  </section>;
}
