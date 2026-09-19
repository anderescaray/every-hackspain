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
  const [company, setCompany] = useState("all");
  const [relationFilter, setRelationFilter] = useState(group.relations.some((relation) => relation.id === initialRelation) ? initialRelation : undefined);
  const selectedRelation = group.relations.find((relation) => relation.id === relationFilter);
  const items = [...group.recommendations]
    .filter((item) => (priority === "all" || item.priority === priority) && (company === "all" || item.company_refs.includes(company)) && (!relationFilter || item.relation_refs.includes(relationFilter)))
    .sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);

  return (
    <section className={base.panel} aria-label="Revisiones propuestas de tesorería">
      <div className={styles.panelHeading}>
        <div>
          <span className={base.eyebrow}>Plan de revisión</span>
          <h2>Qué revisar ahora</h2>
          <p>Priorizadas para el vídeo: mira el título, abre el detalle si hace falta.</p>
        </div>
        <span className={base.periodBadge}>{items.length} revisiones</span>
      </div>

      {selectedRelation && (
        <div className={styles.activeContext}>
          <span>Relación: {relationName(selectedRelation)}</span>
          <button className={base.evidenceButton} onClick={() => setRelationFilter(undefined)}>Quitar filtro de relación</button>
        </div>
      )}
      {initialRelation && !group.relations.some((relation) => relation.id === initialRelation) && (
        <p className={base.emptyState}>La relación solicitada no está en este análisis. Se muestran las revisiones disponibles sin ese filtro.</p>
      )}

      <div className={styles.filters}>
        <label>Prioridad<select aria-label="Prioridad" value={priority} onChange={(event) => setPriority(event.target.value)}><option value="all">Todas</option><option value="high">Alta</option><option value="medium">Media</option><option value="low">Baja</option></select></label>
        <label>Sociedad<select aria-label="Sociedad implicada" value={company} onChange={(event) => setCompany(event.target.value)}><option value="all">Todas</option>{group.members.map((member) => <option key={member.company_id}>{member.company_id}</option>)}</select></label>
        <button className={base.secondaryButton} onClick={() => { setPriority("all"); setCompany("all"); setRelationFilter(undefined); }}>Restablecer filtros</button>
      </div>

      <div className={styles.recommendationBoard}>
        {items.map((item, index) => (
          <article key={item.id} className={`${styles.recommendationVisual} ${styles[`priority-${item.priority}`]}`}>
            <header>
              <span className={styles.recommendationRank}>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <span className={`${base.severity} ${base[item.priority]}`}>Prioridad {severityLabels[item.priority].toLowerCase()}</span>
                <h3>{item.title}</h3>
                <p className={styles.recommendationType}>{recommendationLabels[item.type]} · {item.period}</p>
              </div>
            </header>

            <p className={styles.recommendationWhy}>{item.explanation}</p>

            <div className={styles.signalChips}>
              {item.signals.map((signal, signalIndex) => (
                <span key={`${signal.source}-${signalIndex}`} className={styles.signalChip} title={signal.observation}>
                  {signalLabels[signal.source]}
                </span>
              ))}
            </div>

            <details className={styles.recommendationExpand}>
              <summary>Ver pasos y límites <span className={styles.expandMarker} aria-hidden="true">+</span></summary>
              <div className={styles.recommendationBody}>
                <div className={styles.recommendationColumns}>
                  <div>
                    <h4>Por qué aparece</h4>
                    <ul className={styles.signalList}>
                      {item.signals.map((signal, signalIndex) => (
                        <li key={`${signal.source}-detail-${signalIndex}`}>
                          <span>{signalLabels[signal.source]}</span>
                          <p>{signal.observation}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4>Qué revisar</h4>
                    <ol className={styles.reviewSteps}>{item.review_steps.map((step) => <li key={step}>{step}</li>)}</ol>
                    <div className={styles.constraints}>
                      <h4>Antes de decidir</h4>
                      <ul>{item.constraints.map((constraint) => <li key={constraint}>{constraint}</li>)}</ul>
                    </div>
                  </div>
                </div>
                <div className={styles.recommendationFooter}>
                  <Confidence value={item.confidence} />
                  <EvidenceButton refs={item.evidence_refs} title={item.title} onOpen={onOpen} />
                </div>
                <GroupLinks group={group} companies={item.company_refs} relations={item.relation_refs} />
              </div>
            </details>
          </article>
        ))}
      </div>

      {!items.length && (
        <p className={base.emptyState}>{group.recommendations.length ? "No hay recomendaciones que coincidan con estos filtros." : "No se han suministrado recomendaciones. No implica ausencia de riesgos u oportunidades."}</p>
      )}
    </section>
  );
}
