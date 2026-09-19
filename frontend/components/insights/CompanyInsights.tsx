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
  const debt = company.pulse.pillars.debt_obligations;
  const dualHealth = company.score_version === "PulseFourPillars-v1.1";
  const primaryHealth = dualHealth ? company.operating_health : company.health_score;
  const primaryLabel = dualHealth ? "Operating Health" : "Extended Health histórico";
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
        <span className={styles.periodBadge}>Análisis financiero</span>
      </div>
      <div className={styles.healthOverview}>
        <section className={styles.healthHero} aria-label="Diagnóstico financiero">
          <h2>{primaryLabel}</h2>
          <div className={styles.healthValue}><strong data-testid="health-score">{primaryHealth == null ? "—" : numberLabel(primaryHealth, 2)}</strong>{primaryHealth != null && <span>/ 100</span>}</div>
          <p className={styles.assessment}>{dualHealth ? primaryHealth == null ? "Dinámica operativa no identificada: faltan pilares G/M/R." : "Salud de la dinámica operativa de caja, calculada con Generation, Momentum y Resilience." : `${company.health_score === null ? "Salud no plenamente identificada. " : ""}${company.assessment}`}</p>
          {dualHealth && <dl className={styles.healthSecondary}>
            <div><dt>Debt &amp; Obligations</dt><dd>{debt.score === null ? "No identificado" : numberLabel(debt.score, 2)}</dd></div>
            <div><dt>Extended Health</dt><dd>{company.extended_health == null ? "—" : numberLabel(company.extended_health, 2)}</dd></div>
          </dl>}
          {dualHealth && <p className={styles.healthEvidenceNote}>{company.extended_health == null ? "Extended Health no se calcula sin Debt identificado." : "La diferencia entre ambos niveles refleja evidencia financiera adicional, no un cambio económico temporal."}</p>}
          <span className={`${styles.trajectoryBadge} ${company.trajectory ? styles[company.trajectory] : styles.muted}`}>{company.trajectory ? trajectoryLabels[company.trajectory] : "Trayectoria no evaluable"} <span aria-hidden="true">{company.trajectory ? trajectorySymbol : ""}</span></span>
          <div className={styles.analysisConfidence}>
            <span>Confianza del análisis: <strong>{confidenceLabel(company.confidence)}</strong></span>
            <Confidence value={company.confidence} />
            <small>Calidad y cobertura de la información, no probabilidad de acierto. No forma parte del Health Score.</small>
          </div>
        </section>
        <section className={styles.composition} aria-label="Composición de Operating y Extended Health">
          <span className={styles.eyebrow}>Pilares suministrados por Pulse</span>
          <h2>{dualHealth ? "Composición y módulo de deuda" : "Composición de Extended Health histórico"}</h2>
          <p>{dualHealth ? "Operating usa G/M/R; Debt es independiente y solo entra en Extended cuando está identificado." : "Cuatro dimensiones, una única visión de la empresa."}</p>
          <dl className={styles.dimensionList}>
            {HEALTH_DIMENSIONS.map((dimension) => <div key={dimension.key}>
              <dt><span>{dimension.label}</span><small>{dimension.explanation}</small>{company.dimensions[dimension.key] !== null && <span className={styles.dimensionTrack} aria-hidden="true"><i style={{ width: `${company.dimensions[dimension.key]}%` }} /></span>}</dt>
              <dd><strong>{company.dimensions[dimension.key] === null ? "No identificado" : numberLabel(company.dimensions[dimension.key]!, 2)}</strong><span>{dualHealth ? dimension.key === "debt" ? "20 % de Extended · no entra en Operating" : `${numberLabel((dimension.key === "cash_generation" ? company.operating_weights?.generation : dimension.key === "momentum" ? company.operating_weights?.momentum : company.operating_weights?.resilience)! * 100)} % de Operating` : `${numberLabel(company.health_score_model.weights[dimension.key] * 100)} % del total`}</span></dd>
            </div>)}
          </dl>
          <details className={styles.methodology}>
            <summary>Cómo se calcula · {company.status === "complete_bounded" ? "identificación acotada" : company.health_score_model.provisional ? "evidencia parcial" : "PulseFourPillars"}</summary>
            {dualHealth && <p>Operating Health: 50 % Generation + 18,75 % Momentum + 31,25 % Resilience. Extended Health: 40 % Generation + 15 % Momentum + 25 % Resilience + 20 % Debt. Son resultados distintos, suministrados por el motor.</p>}
            {!dualHealth && <p>{HEALTH_DIMENSIONS.map(({ key, label }) => `${numberLabel(company.health_score_model.weights[key] * 100)} % ${label}`).join(" + ")}. Valores suministrados por el motor, sin recalcular ni completar componentes ausentes.</p>}
            <p>Pesos iniciales no calibrados científicamente. Diagnóstico de tesorería y alerta temprana, no probabilidad de impago. Momentum describe la trayectoria observada, no un pronóstico; deuda mide presión del servicio observado, no solvencia ni deuda contractual total.</p>
            {company.pulse.identified_range && <p>Rango identificado de {dualHealth ? "Extended Health" : "Health"}: {numberLabel(company.pulse.identified_range.min, 2)}–{numberLabel(company.pulse.identified_range.max, 2)}. {company.status === "complete_bounded" ? "El valor de Extended Health es una estimación acotada, no una identificación exacta. " : ""}No es un intervalo de confianza.</p>}
            {debt.evidence_status === "bounded" && debt.score_range?.min != null && debt.score_range?.max != null && <p>Deuda con incertidumbre acotada: {numberLabel(debt.score_range.min, 2)}–{numberLabel(debt.score_range.max, 2)}. Estimación suministrada por el motor.</p>}
            {company.health_score === null && <p>Límites de identificación de {dualHealth ? "Extended Health" : "Health"}: {numberLabel(company.pulse.health_min, 2)}–{numberLabel(company.pulse.health_max, 2)}. No son intervalos de confianza. Componentes ausentes: {company.pulse.missing_components.join(", ")}.</p>}
            {dualHealth && company.missing_modules && company.missing_modules.length > 0 && <p>Módulos no identificados: {company.missing_modules.join(", ")}.</p>}
            <p>Método: {company.score_version} · Clasificación: {company.classification_version} · Run: {company.run_id}</p>
          </details>
        </section>
      </div>
    </header>
    <div id="trajectory" data-company-section="trajectory" className={styles.overviewGrid}>
      <TrajectoryChart history={company.history} trajectory={dualHealth ? null : company.trajectory} scoreLabel={dualHealth ? "Extended Health" : "Health Score"} />
      <section className={styles.panel} aria-label="Señales de evolución financiera">
        <SectionHeading number="02" title={dualHealth ? "Señales de evolución financiera" : "¿Por qué está cambiando el Health Score?"} description="Las señales detrás de la evolución financiera." />
        <p className={styles.smallText}>{company.drivers_period}</p>
        <div className={styles.drivers}>{company.drivers.map((driver) => <article className={styles.driver} key={driver.id}>
          <div className={styles.inlineHeading}><h3>{driver.driver}</h3><strong className={driver.direction === "positive" ? styles.positiveText : driver.direction === "negative" ? styles.negativeText : styles.muted}>{signedNumber(driver.impact)} <small>puntos</small></strong></div>
          <p>{driver.explanation}</p>
          <p className={styles.dimensionContext}>Afecta a {HEALTH_DIMENSIONS.filter(({ key }) => driver.affected_dimensions.includes(key)).map(({ label }) => label).join(" · ")}</p>
          <div className={styles.evidenceMeta}><span>{driver.evidence_count} registros de respaldo</span><EvidenceButton refs={driver.evidence_refs} title={driver.driver} onOpen={openEvidence} /></div>
        </article>)}</div>
        {!company.drivers.length && <p className={styles.emptyState}>No hay factores con suficiente respaldo para este análisis.</p>}
        <p className={styles.disclaimer}>{isMock ? "Contribuciones ilustrativas. " : "Contribuciones seleccionadas. "}No tienen por qué sumar la variación completa de {dualHealth ? "Extended Health" : "Health Score"}.</p>
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
    <WhatIfSection currentHealthScore={company.health_score} simulation={company.simulation} scoreLabel={dualHealth ? "Extended Health" : "Health Score"} />
    <footer className={styles.pageFooter}><span>Embat Pulse · HackSpain 2026 / Embat X-Ray</span><span>{isMock ? "Datos de ejemplo. Sin procesamiento financiero en tiempo real." : "Datos precalculados. Sin procesamiento financiero en tiempo real."}</span></footer>
    {evidence && <EvidenceDialog groupId={company.group_id} title={evidence.title} groups={company.evidence.filter((group) => evidence.refs.includes(group.id)).map((group) => evidence.records ? { ...group, rows: group.rows.filter((row) => evidence.records?.some((record) => record.evidence_id === group.id && record.transaction_id === row.id)) } : group)} accounts={company.cash_truth.account_flows?.accounts ?? []} isMock={isMock} onClose={() => setEvidence(null)} />}
  </main>;
}
