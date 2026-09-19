"use client";

import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import { useState } from "react";
import type { GroupDetail, GroupInsight, GroupMetric } from "@/types/groupDetail";
import { dateLabel, severityLabels, trajectoryLabels } from "@/lib/companyFormat";
import { groupMoney, groupScore, priorityOrder } from "@/lib/groupPresentation";
import { EvidenceButton, type OpenEvidence } from "@/components/insights/InsightPrimitives";
import { GroupLinks } from "./GroupLinks";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

const attentionLabels = { high: "Prioridad alta", medium: "Vigilar", low: "Estable", unknown: "Sin priorizar" } as const;

function Metric({ label, metric, group, onOpen }: { label: string; metric: GroupMetric; group: GroupDetail; onOpen: OpenEvidence }) {
  return (
    <div className={styles.groupMetric}>
      <span>{label}</span>
      <strong>{groupMoney(metric.value)}</strong>
      <small>{metric.covered_company_ids.length}/{group.members.length} sociedades</small>
      <EvidenceButton refs={metric.evidence_refs} title={label} onOpen={onOpen} />
    </div>
  );
}

function AlertList({ items, group, onOpen }: { items: GroupInsight[]; group: GroupDetail; onOpen: OpenEvidence }) {
  return (
    <div className={styles.alertCards}>
      {items.map((item) => (
        <details key={item.id} className={styles.alertCard}>
          <summary>
            <span className={`${base.severity} ${base[item.severity]}`}>{severityLabels[item.severity]}</span>
            <strong>{item.title}</strong>
            <span className={styles.expandMarker} aria-hidden="true">+</span>
          </summary>
          <div className={styles.alertCardBody}>
            <p>{item.explanation}</p>
            <GroupLinks group={group} companies={item.company_refs} relations={item.relation_refs} />
            <EvidenceButton refs={item.evidence_refs} title={item.title} onOpen={onOpen} />
          </div>
        </details>
      ))}
    </div>
  );
}

export function GroupOverview({ group, onOpen }: { group: GroupDetail; onOpen: OpenEvidence }) {
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<"attention" | "all">("attention");
  const highAttention = group.members.filter((member) => member.attention === "high").length;
  const members = [...group.members]
    .filter((member) => member.company_id.toLowerCase().includes(query.toLowerCase()))
    .filter((member) => focus === "all" || member.attention === "high")
    .sort((a, b) => priorityOrder[a.attention] - priorityOrder[b.attention] || (a.health_score ?? 999) - (b.health_score ?? 999));

  return <>
    <section className={styles.summaryStrip} aria-label="Magnitudes observadas del grupo">
      <Metric label="Liquidez observada" metric={group.available_liquidity} group={group} onOpen={onOpen} />
      <Metric label="Deuda externa" metric={group.identified_debt} group={group} onOpen={onOpen} />
      <Metric label={`Vence · ${group.obligations.horizon}`} metric={group.obligations} group={group} onOpen={onOpen} />
    </section>

    <section className={base.panel} aria-label="Sociedades del grupo observado">
      <div className={styles.panelHeading}>
        <div>
          <span className={base.eyebrow}>Sociedad a sociedad</span>
          <h2>Dónde mirar primero</h2>
          <p>Sin Health Score de grupo. Empieza por las sociedades en prioridad alta.</p>
        </div>
        <span className={base.periodBadge}>{highAttention} de {group.members.length} en foco</span>
      </div>

      <div className={styles.focusTabs} role="group" aria-label="Filtro de atención">
        <button type="button" aria-pressed={focus === "attention"} className={focus === "attention" ? styles.focusTabActive : styles.focusTab} onClick={() => setFocus("attention")}>
          Prioridad alta ({highAttention})
        </button>
        <button type="button" aria-pressed={focus === "all"} className={focus === "all" ? styles.focusTabActive : styles.focusTab} onClick={() => setFocus("all")}>
          Todas ({group.members.length})
        </button>
        <label className={styles.inlineSearch}>
          Buscar
          <input type="search" aria-label="Buscar sociedad" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="COMP_…" />
        </label>
      </div>

      {members.length ? (
        <ul className={styles.memberCards} aria-label="Tabla de sociedades">
          {members.map((member) => (
            <li key={member.company_id}>
              <details className={`${styles.memberCard} ${styles[`attention-${member.attention}`]}`}>
                <summary>
                  <div className={styles.memberCardMain}>
                    <strong className={styles.companyLink}>{member.company_id}</strong>
                    <span className={`${styles.attentionChip} ${styles[`chip-${member.attention}`]}`}>{attentionLabels[member.attention]}</span>
                    <span className={styles.trajectoryChip}>{member.trajectory ? trajectoryLabels[member.trajectory] : "Sin evaluar"}</span>
                  </div>
                  <div className={styles.memberCardScores}>
                    <div><span>Health</span><strong className={styles.memberHealth}>{groupScore(member.health_score)}</strong></div>
                    <div><span>Liquidez</span><strong>{groupMoney(member.available_liquidity)}</strong></div>
                    <div><span>Obligaciones</span><strong>{groupMoney(member.obligations_due)}</strong></div>
                  </div>
                  <span className={styles.expandMarker} aria-hidden="true">+</span>
                </summary>
                <div className={styles.memberCardBody}>
                  <p>{member.summary}</p>
                  <dl className={styles.dimensionGrid}>
                    <div><dt>Generación de caja</dt><dd>{groupScore(member.dimensions.cash_generation)}</dd></div>
                    <div><dt>Momentum</dt><dd>{groupScore(member.dimensions.momentum)}</dd></div>
                    <div><dt>Resiliencia</dt><dd>{groupScore(member.dimensions.resilience)}</dd></div>
                    <div><dt>Deuda</dt><dd>{groupScore(member.dimensions.debt)}</dd></div>
                    <div><dt>Deuda identificada</dt><dd>{groupMoney(member.identified_debt)}</dd></div>
                    <div><dt>Datos a</dt><dd>{dateLabel(group.as_of)}</dd></div>
                  </dl>
                  <div className={styles.memberCardActions}>
                    <Link className={base.evidenceButton} href={`/companies/${member.company_id}`}>Abrir ficha</Link>
                    <Link className={base.evidenceButton} href={`/groups/${group.group_id}/network?company=${member.company_id}`}>Ver en la red</Link>
                    <EvidenceButton refs={member.evidence_refs} title={`Sociedad ${member.company_id}`} onOpen={onOpen} />
                  </div>
                </div>
              </details>
            </li>
          ))}
        </ul>
      ) : (
        <p className={base.emptyState}>{group.members.length ? "No hay sociedades que coincidan con estos filtros." : "No hay sociedades con análisis disponible en el grupo observado."}</p>
      )}
    </section>

    <section className={base.panel} aria-label="Alertas del grupo">
      <div className={styles.panelHeading}>
        <div>
          <h2>Alertas</h2>
          <p>Despliega solo lo que necesites revisar.</p>
        </div>
      </div>
      {group.alerts.length ? (
        <AlertList items={[...group.alerts].sort((a, b) => priorityOrder[a.severity] - priorityOrder[b.severity])} group={group} onOpen={onOpen} />
      ) : (
        <p className={base.emptyState}>No hay alertas preparadas. No es una garantía de ausencia de riesgos.</p>
      )}
    </section>

    {group.recent_changes.length > 0 && (
      <details className={`${base.panel} ${styles.collapsiblePanel}`}>
        <summary className={styles.collapsibleSummary}>
          <span>
            <h2>Cambios recientes</h2>
            <p>{group.recent_changes.length} cambios suministrados</p>
          </span>
          <span className={styles.expandMarker} aria-hidden="true">+</span>
        </summary>
        <div className={styles.changeList}>
          {group.recent_changes.map((change) => (
            <article key={change.id}>
              <time dateTime={change.date}>{dateLabel(change.date)}</time>
              <h3>{change.title}</h3>
              <p>{change.explanation}</p>
              <GroupLinks group={group} companies={change.company_refs} relations={change.relation_refs} />
              <EvidenceButton refs={change.evidence_refs} title={change.title} onOpen={onOpen} />
            </article>
          ))}
        </div>
      </details>
    )}

    <Link className={styles.nextStep} href={`/groups/${group.group_id}/network`}>
      <span><small>Siguiente</small><strong>Ver cómo circula el dinero en el grupo</strong></span>
      <span aria-hidden="true">→</span>
    </Link>
  </>;
}
