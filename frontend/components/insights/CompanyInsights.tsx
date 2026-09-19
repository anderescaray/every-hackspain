"use client";

import { useState } from "react";
import type { CompanyDetail, EvidenceRef } from "@/types/companyDetail";
import { dateLabel, signedNumber } from "@/lib/companyFormat";
import { TrajectoryChart } from "./TrajectoryChart";
import { CashTruthSection } from "./CashTruthSection";
import { TimeBorrowedSection } from "./TimeBorrowedSection";
import { WhatIfSection } from "./WhatIfSection";
import { EvidenceDialog } from "./EvidenceDialog";
import { Confidence, EvidenceButton, SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

const severityOrder = { high: 0, medium: 1, low: 2 };

export function CompanyInsights({ company }: { company: CompanyDetail }) {
  const [evidence, setEvidence] = useState<{ refs: EvidenceRef[]; title: string } | null>(null);
  const openEvidence = (refs: EvidenceRef[], title: string) => setEvidence({ refs, title });
  const alerts = [...company.alerts].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
  const isMock = company.source === "mock";
  const trajectorySymbol = company.trajectory === "improving" ? "↑" : company.trajectory === "deteriorating" ? "↓" : "→";
  const momentumSymbol = company.momentum.direction === "improving" ? "↑" : company.momentum.direction === "deteriorating" ? "↓" : "→";

  return <main className={styles.page} id="company-insights">
    <a href="#cash-truth" className={styles.skipLink}>Skip to Cash Truth</a>
    <div className={styles.contextBar}><span className={styles.wordmark}>embat <strong>Pulse</strong><span className={styles.contextDivider} />Company intelligence</span><span className={styles.demoBadge}>{isMock ? "Demo · Mock data" : "Prepared snapshot"}</span></div>
    <header className={styles.companyHeader}>
      <div className={styles.headerIdentity}><div><div className={styles.companyMeta}><span className={styles.eyebrow}>{company.group_id}</span><span>As of {dateLabel(company.as_of)}</span></div><h1>{company.company_id}</h1><p>{company.summary}</p></div><div className={`${styles.trajectoryBadge} ${styles[company.trajectory]}`}><span aria-hidden="true">{trajectorySymbol}</span>{company.trajectory} trajectory</div></div>
      <div className={styles.scoreStrip}>
        <div className={styles.pulseScore}><span>Pulse Score</span><div><strong>{company.pulse}</strong><span>/ 100</span></div><small>Overall signal, not a verdict</small></div>
        <div className={styles.metric}><span>Health</span><strong>{company.health}<small>/ 100</small></strong><div className={styles.metricTrack}><i style={{ width: `${company.health}%` }} /></div><small>Current financial condition</small></div>
        <div className={styles.metric}><span>Momentum</span><strong className={`${styles.momentum} ${company.momentum.direction === "improving" ? styles.positiveText : company.momentum.direction === "deteriorating" ? styles.negativeText : styles.muted}`}>{company.momentum.label} <span aria-hidden="true">{momentumSymbol}</span></strong><small>Direction of movement</small></div>
        <div className={styles.metric}><span>Stability</span><strong>{company.stability}<small>/ 100</small></strong><div className={styles.metricTrack}><i style={{ width: `${company.stability}%` }} /></div><small>Consistency over time</small></div>
        <div className={styles.metric}><span>Confidence</span><strong>{company.confidence === null ? "—" : `${company.confidence}%`}</strong><small>{company.confidence === null ? "Insufficient evidence" : "Evidence coverage, not certainty"}</small></div>
      </div>
    </header>
    <div className={styles.overviewGrid}>
      <TrajectoryChart history={company.history} trajectory={company.trajectory} />
      <section className={styles.panel} aria-label="Pulse drivers"><SectionHeading number="02" title="Why is Pulse changing?" description="The main signals behind the movement." /><p className={styles.smallText}>{company.drivers_period}</p><div className={styles.drivers}>{company.drivers.map((driver) => <article className={styles.driver} key={driver.id}><div className={styles.inlineHeading}><h3>{driver.driver}</h3><strong className={driver.direction === "positive" ? styles.positiveText : driver.direction === "negative" ? styles.negativeText : styles.muted}>{signedNumber(driver.impact)} <small>pts</small></strong></div><p>{driver.explanation}</p><div className={styles.evidenceMeta}><span>{driver.evidence_count} supporting records</span><EvidenceButton refs={driver.evidence_refs} title={driver.driver} onOpen={openEvidence} /></div></article>)}</div>{!company.drivers.length && <p className={styles.emptyState}>No sufficiently supported drivers available.</p>}<p className={styles.disclaimer}>{isMock ? "Illustrative contributions. " : "Selected contributions. "}These drivers do not necessarily sum to the full change in Pulse.</p></section>
    </div>
    <div id="cash-truth"><CashTruthSection cash={company.cash_truth} companyId={company.company_id} onOpen={openEvidence} /></div>
    <TimeBorrowedSection timing={company.time_borrowed} onOpen={openEvidence} />
    <div className={styles.bottomGrid}>
      <section className={styles.panel} aria-label="Prioritized alerts"><SectionHeading number="05" title="What deserves attention" description="Prioritized signals. Evidence before conclusions."><span className={styles.periodBadge}>{alerts.length} alerts</span></SectionHeading><div className={styles.alerts}>{alerts.map((alert, index) => <details className={styles.alert} key={alert.id}><summary><span className={styles.alertRank}>{String(index + 1).padStart(2, "0")}</span><span className={styles.alertTitle}><span className={`${styles.severity} ${styles[alert.severity]}`}>{alert.severity}</span><strong>{alert.title}</strong><small>{alert.period}</small></span><span className={styles.expandIcon} aria-hidden="true">+</span></summary><div className={styles.alertDetail}><p>{alert.explanation}</p><EvidenceButton refs={alert.evidence_refs} title={alert.title} onOpen={openEvidence} /></div></details>)}</div>{!alerts.length && <p className={styles.emptyState}>No prioritized alerts in this snapshot. This is not a guarantee of financial health.</p>}</section>
      <section className={styles.panel} aria-label="Evidence library"><SectionHeading number="06" title="Evidence, not a black box" description="Every important explanation has a source." /><p className={styles.evidenceIntro}>{isMock ? "Representative mock records make the reasoning inspectable. Replace the data, not the experience." : "Inspect the representative records supplied with this company snapshot."}</p><div className={styles.evidenceLibrary}>{company.evidence.map((group) => <div key={group.id}><div><h3>{group.title}</h3><span className={styles.smallText}>{group.rows.length} sample records · <Confidence value={group.confidence} /></span></div><EvidenceButton refs={[group.id]} title={group.title} onOpen={openEvidence} /></div>)}</div>{!company.evidence.length && <p className={styles.emptyState}>Not identifiable with sufficient confidence.</p>}<p className={styles.disclaimer}>Coverage is not certainty. Missing or uncertain evidence stays visible.</p></section>
    </div>
    <WhatIfSection currentPulse={company.pulse} simulation={company.simulation} />
    <footer className={styles.pageFooter}><span>Embat Pulse · HackSpain 2026 / Embat X-Ray</span><span>{isMock ? "Prepared mock data. No live financial processing." : "Precomputed snapshot. No live financial processing."}</span></footer>
    {evidence && <EvidenceDialog title={evidence.title} groups={company.evidence.filter((group) => evidence.refs.includes(group.id))} isMock={isMock} onClose={() => setEvidence(null)} />}
  </main>;
}
