"use client";

import { useState } from "react";
import type { GroupDetail, GroupView } from "@/types/groupDetail";
import { dateLabel } from "@/lib/companyFormat";
import { groupTabs } from "@/lib/groupPresentation";
import { Confidence } from "@/components/insights/InsightPrimitives";
import { GroupOverview } from "./GroupOverview";
import { GroupNetwork } from "./GroupNetwork";
import { GroupRecommendations } from "./GroupRecommendations";
import { GroupEvidenceDialog } from "./GroupEvidenceDialog";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

const questions: Record<GroupView, string> = {
  overview: "Tres números del grupo y las sociedades a las que mirar primero.",
  network: "El grafo: quién se conecta con quién y por cuánto.",
  recommendations: "Las revisiones priorizadas antes de mover caja.",
};

export function GroupIntelligence({ group, view, initialRelation, initialCompany }: { group: GroupDetail; view: GroupView; initialRelation?: string; initialCompany?: string }) {
  const [evidence, setEvidence] = useState<{ refs: string[]; title: string } | null>(null);
  const openEvidence = (refs: string[], title: string) => setEvidence({ refs, title });
  const tab = groupTabs.find((item) => item.key === view)!;
  const deteriorating = group.members.filter((member) => member.trajectory === "deteriorating").length;
  const improving = group.members.filter((member) => member.trajectory === "improving").length;
  const stable = group.members.filter((member) => member.trajectory === "stable").length;
  const unknown = group.members.filter((member) => member.trajectory === null).length;

  return <main className={`${base.page} ${styles.groupPage}`}>
    <a href="#group-content" className={base.skipLink}>Ir al análisis de grupo</a>
    <div className={base.contextBar}><span className={base.breadcrumb}>Grupo <span aria-hidden="true">/</span> {tab.label}</span><span className={base.demoBadge}>{group.source === "fixture" ? "Demo · Datos de ejemplo" : "Análisis preparado"}</span></div>
    <header className={styles.groupHeader}>
      <div className={styles.headerTop}><span className={styles.headerEyebrow}>Grupo observado · {group.group_id}</span><span>Datos a {dateLabel(group.as_of)}</span></div>
      <h1>{tab.label}</h1><p className={styles.headerQuestion}>{questions[view]}</p><p className={styles.headerSummary}>{group.summary}</p>
      <div className={styles.groupHeaderMeta}><span><strong>{group.members.length}</strong> sociedades observadas{group.coverage.known_company_count === null ? " · total del grupo no disponible" : ` de ${group.coverage.known_company_count} conocidas`}</span><Confidence value={group.coverage.confidence} /><span>{group.period}</span></div>
      <div className={styles.trajectoryStrip}><span><i className={styles.deterioratingDot} />{deteriorating} deteriorándose</span><span><i className={styles.stableDot} />{stable} estables</span><span><i className={styles.improvingDot} />{improving} mejorando</span>{unknown > 0 && <span>{unknown} sin evaluar</span>}<small>Sociedades, no una puntuación única del grupo</small></div>
    </header>
    <div className={styles.scopeNote}><strong>Perímetro observado, no consolidación completa.</strong> {group.coverage.explanation}</div>
    <div id="group-content" className={styles.groupContent}>
      {view === "overview" && <GroupOverview group={group} onOpen={openEvidence} />}
      {view === "network" && <GroupNetwork group={group} onOpen={openEvidence} initialRelation={initialRelation} initialCompany={initialCompany} />}
      {view === "recommendations" && <GroupRecommendations group={group} onOpen={openEvidence} initialRelation={initialRelation} />}
    </div>
    <section className={styles.limits} aria-label="Límites del análisis de grupo"><h2>Antes de decidir</h2><p>La caja no se considera libremente transferible entre sociedades. Ninguna recomendación ejecuta movimientos ni sustituye la revisión del responsable de tesorería.</p><ul>{group.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>
    <footer className={base.pageFooter}><span>Embat Pulse · Inteligencia de grupo</span><span>{group.source === "fixture" ? "Datos de ejemplo aislados. Sin operaciones reales." : "Análisis precalculado. Sin ejecución de operaciones."}</span></footer>
    {evidence && <GroupEvidenceDialog title={evidence.title} evidence={group.evidence.filter((item) => evidence.refs.includes(item.id))} isFixture={group.source === "fixture"} onClose={() => setEvidence(null)} />}
  </main>;
}
