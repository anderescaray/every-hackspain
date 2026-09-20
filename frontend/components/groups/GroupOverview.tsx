"use client";

import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import { useState } from "react";
import type { GroupDetail, GroupInsight, GroupMetric, GroupMember } from "@/types/groupDetail";
import { dateLabel, severityLabels, trajectoryLabels } from "@/lib/companyFormat";
import { groupMoney, groupScore, priorityOrder, roleLabels } from "@/lib/groupPresentation";
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
      <small>{metric.covered_company_ids.length} de {group.members.length} sociedades</small>
      <EvidenceButton refs={metric.evidence_refs} title={label} onOpen={onOpen} />
    </div>
  );
}

function MemberRow({ member, group, onOpen }: { member: GroupMember; group: GroupDetail; onOpen: OpenEvidence }) {
  return (
    <li>
      <details className={`${styles.memberRow} ${styles[`attention-${member.attention}`]}`}>
        <summary>
          <div className={styles.memberScoreBlock} aria-label={`Health Score ${groupScore(member.health_score)}`}>
            <strong className={styles.memberHealth}>{groupScore(member.health_score)}</strong>
            <span>Health</span>
          </div>
          <div className={styles.memberIdentity}>
            <strong className={styles.companyLink}>{member.company_id}</strong>
            <div className={styles.memberMeta}>
              <span className={`${styles.attentionMark} ${styles[`mark-${member.attention}`]}`}>{attentionLabels[member.attention]}</span>
              <span>{member.trajectory ? trajectoryLabels[member.trajectory] : "Sin trayectoria"}</span>
              <span>{roleLabels[member.role]}</span>
            </div>
          </div>
          <div className={styles.memberFigures}>
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
  const [focus, setFocus] = useState<"attention" | "all">("attention");
  const highAttention = group.members.filter((member) => member.attention === "high").length;
  const sortedAlerts = [...group.alerts].sort((a, b) => priorityOrder[a.severity] - priorityOrder[b.severity]);
  const members = [...group.members]
    .filter((member) => focus === "all" || member.attention === "high")
    .sort((a, b) => priorityOrder[a.attention] - priorityOrder[b.attention] || (a.health_score ?? 999) - (b.health_score ?? 999));

  return <>
    <section className={styles.summaryStrip} aria-label="Magnitudes observadas del grupo">
      <Metric label="Liquidez observada" metric={group.available_liquidity} group={group} onOpen={onOpen} />
      <Metric label="Deuda externa" metric={group.identified_debt} group={group} onOpen={onOpen} />
      <Metric label={`Vence · ${group.obligations.horizon}`} metric={group.obligations} group={group} onOpen={onOpen} />
    </section>

    <div className={styles.overviewBoard}>
      <section className={styles.overviewPrimary} aria-label="Sociedades del grupo observado">
        <header className={styles.overviewSectionHead}>
          <div>
            <h2>Dónde mirar primero</h2>
            <p>
              {focus === "attention"
                ? highAttention
                  ? `${highAttention} sociedades en prioridad alta, ordenadas por Health Score.`
                  : "Ninguna sociedad en prioridad alta. Revisa el perímetro completo."
                : `${group.members.length} sociedades del perímetro observado.`}
            </p>
          </div>
          <span className={styles.overviewCount}>
            {members.length}<small> / {group.members.length}</small>
          </span>
        </header>

        <div className={styles.focusTabs} role="group" aria-label="Filtro de atención">
          <button type="button" aria-pressed={focus === "attention"} className={focus === "attention" ? styles.focusTabActive : styles.focusTab} onClick={() => setFocus("attention")}>
            Prioridad alta ({highAttention})
          </button>
          <button type="button" aria-pressed={focus === "all"} className={focus === "all" ? styles.focusTabActive : styles.focusTab} onClick={() => setFocus("all")}>
            Todas ({group.members.length})
          </button>
        </div>

        <div className={styles.memberTableHead} aria-hidden="true">
          <span>Score</span>
          <span>Sociedad</span>
          <span>Caja</span>
          <span />
        </div>

        {members.length ? (
          <ul className={styles.memberCards} aria-label="Tabla de sociedades">
            {members.map((member) => (
              <MemberRow key={member.company_id} member={member} group={group} onOpen={onOpen} />
            ))}
          </ul>
        ) : (
          <p className={base.emptyState}>{group.members.length ? "No hay sociedades que coincidan con estos filtros." : "No hay sociedades con análisis disponible en el grupo observado."}</p>
        )}
      </section>

      <aside className={styles.overviewAside} aria-label="Alertas del grupo">
        <header className={styles.overviewSectionHead}>
          <div>
            <h2>Alertas</h2>
            <p>{sortedAlerts.length ? "Señales a contrastar antes de mover caja." : "Sin alertas preparadas en este perímetro."}</p>
          </div>
          <span className={styles.overviewCount}>{sortedAlerts.length}</span>
        </header>
        {sortedAlerts.length ? (
          <AlertList items={sortedAlerts} group={group} onOpen={onOpen} />
        ) : (
          <p className={base.emptyState}>No hay alertas preparadas. No es una garantía de ausencia de riesgos.</p>
        )}
      </aside>
    </div>

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
      <span><small>Siguiente</small><strong>Red financiera del grupo</strong></span>
      <span aria-hidden="true">→</span>
    </Link>
  </>;
}
