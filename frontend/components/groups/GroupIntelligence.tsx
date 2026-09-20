"use client";

import { useState } from "react";
import type { GroupDetail, GroupView } from "@/types/groupDetail";
import { dateLabel } from "@/lib/companyFormat";
import { groupTabs } from "@/lib/groupPresentation";
import { Confidence } from "@/components/insights/InsightPrimitives";
import { GroupOverview } from "./GroupOverview";
import { GroupRecommendations } from "./GroupRecommendations";
import { GroupEvidenceDialog } from "./GroupEvidenceDialog";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

const questions: Record<GroupView, string> = {
  overview: "Resumen del perímetro y sociedades a revisar primero.",
  recommendations: "Escenarios precalculados para mejorar la filial más débil. Requieren aprobación humana.",
};

export function GroupIntelligence({ group, view, initialRelation }: { group: GroupDetail; view: GroupView; initialRelation?: string }) {
  const [evidence, setEvidence] = useState<{ refs: string[]; title: string } | null>(null);
  const openEvidence = (refs: string[], title: string) => setEvidence({ refs, title });
  const tab = groupTabs.find((item) => item.key === view)!;
  const deteriorating = group.members.filter((member) => member.trajectory === "deteriorating").length;
  const improving = group.members.filter((member) => member.trajectory === "improving").length;
  const stable = group.members.filter((member) => member.trajectory === "stable").length;
  const unknown = group.members.filter((member) => member.trajectory === null).length;

  return <main className={`${base.page} ${styles.groupPage}`}>
    <a href="#group-content" className={base.skipLink}>Ir al análisis de grupo</a>
    <div className={base.contextBar}><span className={base.breadcrumb}>Grupo <span aria-hidden="true">/</span> {group.group_id} <span aria-hidden="true">/</span> {tab.label}</span><span className={base.demoBadge}>{group.source === "fixture" ? "Datos de ejemplo" : "Datos preparados"}</span></div>
    <header className={styles.groupHeader}>
      <div className={styles.headerTop}><span className={styles.headerEyebrow}>{group.group_id}</span><span>Datos a {dateLabel(group.as_of)}</span></div>
      <h1>{tab.label}</h1>
      <p className={styles.headerQuestion}>{questions[view]}</p>
      {view === "overview" ? (
        <div className={styles.overviewSnapshot}>
          <p className={styles.headerSummary}>{group.summary}</p>
          <div className={styles.overviewFacts}>
            <div className={styles.overviewTrajectories} aria-label="Trayectorias del perímetro">
              <span><strong>{deteriorating}</strong> deteriorándose</span>
              <span><strong>{stable}</strong> estables</span>
              <span><strong>{improving}</strong> mejorando</span>
              {unknown > 0 ? <span><strong>{unknown}</strong> sin evaluar</span> : null}
            </div>
            <div className={styles.overviewConfidence}><Confidence value={group.coverage.confidence} /><span>{group.period}</span></div>
          </div>
        </div>
      ) : (
        <>
          <p className={styles.headerSummary}>{group.summary}</p>
          <div className={styles.groupHeaderMeta}><span><strong>{group.members.length}</strong> sociedades observadas{group.coverage.known_company_count === null ? " · total del grupo no disponible" : ` de ${group.coverage.known_company_count} conocidas`}</span><Confidence value={group.coverage.confidence} /><span>{group.period}</span></div>
          <div className={styles.trajectoryStrip}><span><i className={styles.deterioratingDot} />{deteriorating} deteriorándose</span><span><i className={styles.stableDot} />{stable} estables</span><span><i className={styles.improvingDot} />{improving} mejorando</span>{unknown > 0 && <span>{unknown} sin evaluar</span>}<small>Sociedades, no una puntuación única del grupo</small></div>
        </>
      )}
    </header>
    {view === "overview" ? (
      <div className={styles.scopeNote}><strong>Perímetro observado.</strong> {group.coverage.explanation}</div>
    ) : (
      <div className={styles.scopeNote}><strong>Perímetro observado, no consolidación completa.</strong> {group.coverage.explanation}</div>
    )}
    <div id="group-content" className={styles.groupContent}>
      {view === "overview" && <GroupOverview group={group} onOpen={openEvidence} />}
      {view === "recommendations" && <GroupRecommendations group={group} onOpen={openEvidence} initialRelation={initialRelation} />}
    </div>
    <footer className={base.pageFooter}><span>X Ray</span><span>{group.source === "fixture" ? "Sin operaciones reales." : "Sin ejecución de operaciones."}</span></footer>
    {evidence && <GroupEvidenceDialog title={evidence.title} evidence={group.evidence.filter((item) => evidence.refs.includes(item.id))} isFixture={group.source === "fixture"} onClose={() => setEvidence(null)} />}
  </main>;
}
