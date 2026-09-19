"use client";

import { useState } from "react";
import type { CompanyDetail, EvidenceRef, TransactionEvidenceRef } from "@/types/companyDetail";
import { confidenceLabel, dateLabel, numberLabel, severityLabels, signedNumber, trajectoryLabels } from "@/lib/companyFormat";
import { HEALTH_DIMENSIONS } from "@/lib/healthScore";
import { TrajectoryChart } from "./TrajectoryChart";
import { CashTruthSection } from "./CashTruthSection";
import { TimeBorrowedSection } from "./TimeBorrowedSection";
import { WhatIfSection } from "./WhatIfSection";
import { EvidenceDialog } from "./EvidenceDialog";
import { Confidence, EvidenceButton, SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

const severityOrder = { high: 0, medium: 1, low: 2 };

export function CompanyInsights({ company }: { company: CompanyDetail }) {
  const [evidence, setEvidence] = useState<{ refs: EvidenceRef[]; title: string; records?: TransactionEvidenceRef[] } | null>(null);
  const openEvidence = (refs: EvidenceRef[], title: string, records?: TransactionEvidenceRef[]) => setEvidence({ refs, title, records });
  const alerts = [...company.alerts].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
  const isMock = company.source === "fixture";
  const trajectorySymbol = company.trajectory === "improving" ? "↑" : company.trajectory === "deteriorating" ? "↓" : "→";

  return <main className={styles.page} id="company-insights">
    <a href="#cash-truth" className={styles.skipLink}>Ir al origen de la caja</a>
    <div className={styles.contextBar}>
      <span className={styles.breadcrumb}>Empresa <span aria-hidden="true">/</span> Análisis individual</span>
      <span className={styles.demoBadge}>{isMock ? "Demo · Datos de ejemplo" : "Datos preparados"}</span>
    </div>
    <header id="health-score" data-company-section="health-score" className={styles.companyHeader}>
      <div className={styles.headerIdentity}>
        <div><div className={styles.companyMeta}><span className={styles.eyebrow}>Empresa · {company.group_id === null ? "Sin grupo" : `Grupo ${company.group_id}`}</span><span>Datos a {dateLabel(company.as_of)}</span></div><h1>{company.company_id}</h1><p>{company.summary}</p></div>
      </div>
      <div className={styles.healthOverview}>
        <section className={styles.healthHero} aria-label="Estado financiero global">
          <h2>Health Score</h2>
          <div className={styles.healthValue}><strong data-testid="health-score">{company.health_score === null ? "—" : numberLabel(company.health_score, 2)}</strong>{company.health_score !== null && <span>/ 100</span>}</div>
          <p className={styles.assessment}>{company.health_score === null ? "Salud no plenamente identificada. " : ""}{company.assessment}</p>
          <span className={`${styles.trajectoryBadge} ${company.trajectory ? styles[company.trajectory] : styles.muted}`}>{company.trajectory ? trajectoryLabels[company.trajectory] : "Trayectoria no evaluable"} <span aria-hidden="true">{company.trajectory ? trajectorySymbol : ""}</span></span>
          <div className={styles.analysisConfidence}>
            <span>Confianza del análisis: <strong>{confidenceLabel(company.confidence)}</strong></span>
            <Confidence value={company.confidence} />
          </div>
        </section>
        <section className={styles.composition} aria-label="Composición del Health Score">
          <h2>Composición del Health Score</h2>
          <dl className={styles.dimensionList}>
            {HEALTH_DIMENSIONS.map((dimension) => <div key={dimension.key}>
              <dt><span>{dimension.label}</span><small>{dimension.explanation}</small><span className={styles.dimensionTrack} aria-hidden="true">{company.dimensions[dimension.key] !== null && <i style={{ width: `${company.dimensions[dimension.key]}%` }} />}</span></dt>
              <dd><strong className={company.dimensions[dimension.key] === null ? styles.muted : undefined}>{company.dimensions[dimension.key] === null ? "No evaluable" : numberLabel(company.dimensions[dimension.key]!, 2)}</strong></dd>
            </div>)}
          </dl>
          <details className={styles.methodology}>
            <summary>Cómo se calcula</summary>
            <p>{HEALTH_DIMENSIONS.map(({ key, label }) => `${numberLabel(company.health_score_model.weights[key] * 100)} % ${label}`).join(" + ")}. Valores suministrados por el motor, sin recalcular ni completar componentes ausentes.</p>
            <p>Pesos iniciales no calibrados científicamente. Diagnóstico de tesorería y alerta temprana, no probabilidad de impago. Momentum describe la trayectoria observada, no un pronóstico; deuda mide presión del servicio observado, no solvencia ni deuda contractual total.</p>
            <p>La confianza del análisis mide calidad y cobertura de la información, no probabilidad de acierto, y no forma parte del Health Score.</p>
            {company.health_score === null && <p>Límites de identificación: {numberLabel(company.pulse.health_min, 2)}–{numberLabel(company.pulse.health_max, 2)}. No son intervalos de confianza. Componentes ausentes: {company.pulse.missing_components.join(", ")}.</p>}
            <p>Método: {company.score_version} · Clasificación: {company.classification_version} · Run: {company.run_id}</p>
          </details>
        </section>
      </div>
    </header>
    <div id="trajectory" data-company-section="trajectory" className={styles.overviewGrid}>
      <TrajectoryChart history={company.history} trajectory={company.trajectory} />
      <section className={styles.panel} aria-label="Factores del Health Score">
        <SectionHeading number="02" title="¿Por qué cambia el Health Score?" />
        <div className={styles.drivers}>{company.drivers.map((driver) => <article className={styles.driver} key={driver.id}>
          <div className={styles.inlineHeading}><h3>{driver.driver}</h3><strong className={driver.direction === "positive" ? styles.positiveText : driver.direction === "negative" ? styles.negativeText : styles.muted}>{signedNumber(driver.impact)} <small>puntos</small></strong></div>
          <p>{driver.explanation}</p>
          <div className={styles.driverFooter}>
            <span className={styles.dimensionChips}>{HEALTH_DIMENSIONS.filter(({ key }) => driver.affected_dimensions.includes(key)).map(({ key, label }) => <span key={key}>{label}</span>)}</span>
            <EvidenceButton refs={driver.evidence_refs} title={driver.driver} onOpen={openEvidence} />
          </div>
        </article>)}</div>
        {!company.drivers.length && <p className={styles.emptyState}>No hay factores con suficiente respaldo para este análisis.</p>}
        <p className={styles.footnote}>{company.drivers_period}{company.drivers.length > 0 && !isMock ? " · Contribuciones seleccionadas: no suman necesariamente toda la variación." : ""}</p>
      </section>
    </div>
    <div id="cash-truth" data-company-section="cash-truth"><CashTruthSection cash={company.cash_truth} companyId={company.company_id} groupId={company.group_id} onOpen={openEvidence} /></div>
    <div id="time-borrowed" data-company-section="time-borrowed"><TimeBorrowedSection timing={company.time_borrowed} onOpen={openEvidence} /></div>
    <section className={styles.panel} aria-label="Alertas priorizadas">
      <SectionHeading number="05" title="Alertas" description="Qué merece atención."><span className={styles.periodBadge}>{alerts.length} alertas</span></SectionHeading>
      <div className={styles.alerts}>{alerts.map((alert, index) => <details className={styles.alert} key={alert.id}>
        <summary><span className={styles.alertRank}>{String(index + 1).padStart(2, "0")}</span><span className={styles.alertTitle}><span className={`${styles.severity} ${styles[alert.severity]}`}>Prioridad {severityLabels[alert.severity].toLowerCase()}</span><strong>{alert.title}</strong><small>{alert.period}</small></span><span className={styles.expandIcon} aria-hidden="true">+</span></summary>
        <div className={styles.alertDetail}><p>{alert.explanation}</p><EvidenceButton refs={alert.evidence_refs} title={alert.title} onOpen={openEvidence} /></div>
      </details>)}</div>
      {!alerts.length && <p className={styles.emptyState}>No hay alertas priorizadas en este análisis. Esto no garantiza la salud financiera.</p>}
    </section>
    <WhatIfSection currentHealthScore={company.health_score} simulation={company.simulation} />
    <footer className={styles.pageFooter}><span>Embat Pulse · HackSpain 2026 / Embat X-Ray</span><span>{isMock ? "Datos de ejemplo. Sin procesamiento financiero en tiempo real." : "Datos precalculados. Sin procesamiento financiero en tiempo real."}</span></footer>
    {evidence && <EvidenceDialog groupId={company.group_id} title={evidence.title} groups={company.evidence.filter((group) => evidence.refs.includes(group.id)).map((group) => evidence.records ? { ...group, rows: group.rows.filter((row) => evidence.records?.some((record) => record.evidence_id === group.id && record.transaction_id === row.id)) } : group)} accounts={company.cash_truth.account_flows?.accounts ?? []} isMock={isMock} onClose={() => setEvidence(null)} />}
  </main>;
}
