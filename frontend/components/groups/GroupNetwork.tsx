"use client";

import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import { useCallback, useRef, useState } from "react";
import type { GroupDetail, GroupMember, GroupRelation } from "@/types/groupDetail";
import { numberLabel, severityLabels, trajectoryLabels } from "@/lib/companyFormat";
import { groupMoney, groupScore, relationChangeLabels, relationKindLabels, relationName, relationStatusLabels, roleLabels } from "@/lib/groupPresentation";
import { Confidence, EvidenceButton, type OpenEvidence } from "@/components/insights/InsightPrimitives";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";
import { NetworkCanvas, type FocusMode } from "./network/NetworkCanvas";

function MemberDetail({ member, group, onOpen, onShowEgo, onShowNetwork, focusMode }: {
  member: GroupMember;
  group: GroupDetail;
  onOpen: OpenEvidence;
  onShowEgo: () => void;
  onShowNetwork: () => void;
  focusMode: FocusMode;
}) {
  const alerts = group.alerts.filter((alert) => alert.company_refs.includes(member.company_id));
  return <>
    <span className={base.eyebrow}>Sociedad</span>
    <h3>{member.company_id}</h3>
    <span className={styles.roleBadge}>{roleLabels[member.role]}</span>
    <dl className={styles.selectionMetrics}>
      <div><dt>Health Score</dt><dd data-testid="selection-health-score">{groupScore(member.health_score)}</dd></div>
      <div><dt>Momentum</dt><dd>{groupScore(member.dimensions.momentum)}</dd></div>
      <div><dt>Liquidez</dt><dd>{groupMoney(member.available_liquidity)}</dd></div>
      <div><dt>Trayectoria</dt><dd>{member.trajectory ? trajectoryLabels[member.trajectory] : "Sin evaluar"}</dd></div>
    </dl>
    <p>{member.summary}</p>
    {alerts.length > 0 && (
      <>
        <h4>Alertas</h4>
        <ul className={styles.simpleList}>{alerts.map((alert) => <li key={alert.id}><span className={`${base.severity} ${base[alert.severity]}`}>{severityLabels[alert.severity]}</span><strong>{alert.title}</strong></li>)}</ul>
      </>
    )}
    <div className={styles.networkFocusActions}>
      {focusMode === "ego" ? (
        <button type="button" className={base.secondaryButton} onClick={onShowNetwork}>Ver toda la red</button>
      ) : (
        <button type="button" className={base.secondaryButton} onClick={onShowEgo}>Ver relaciones de esta sociedad</button>
      )}
    </div>
    <EvidenceButton refs={member.evidence_refs} title={`Sociedad ${member.company_id}`} onOpen={onOpen} />
    <Link href={`/companies/${member.company_id}`} className={base.primaryButton}>Abrir ficha de {member.company_id}</Link>
  </>;
}

function RelationDetail({ relation, group, onOpen }: { relation: GroupRelation; group: GroupDetail; onOpen: OpenEvidence }) {
  return <>
    <span className={base.eyebrow}>Transferencia</span>
    <h3>{relationKindLabels[relation.kind]}</h3>
    <span className={`${styles.relationBadge} ${styles[relation.status]}`}>{relationStatusLabels[relation.status]}</span>
    <p className={styles.relationEndpoints}>{relationName(relation)}</p>
    {relation.status !== "identified" && <p className={styles.candidateNotice}>No confirmada. No permite afirmar apoyo ni disponibilidad.</p>}
    <dl className={styles.selectionMetrics}>
      <div><dt>Volumen</dt><dd>{groupMoney(relation.volume)}</dd></div>
      <div><dt>Movimientos</dt><dd>{relation.transfer_count ?? "—"}</dd></div>
      <div><dt>Recurrencia</dt><dd>{relation.recurrence}</dd></div>
      <div><dt>Cambio</dt><dd>{relationChangeLabels[relation.change]}</dd></div>
    </dl>
    <p className={base.smallText}>{relation.explanation}</p>
    <Confidence value={relation.confidence} />
    <EvidenceButton refs={relation.evidence_refs} title={`Relación ${relationName(relation)}`} onOpen={onOpen} />
    <div className={styles.contextLinks}>
      {[relation.from_company_id, relation.to_company_id].filter((id): id is string => id !== null).map((id) => <Link key={id} href={`/companies/${id}`}>Ver {id} ↗</Link>)}
      <Link href={`/groups/${group.group_id}/recommendations?relation=${encodeURIComponent(relation.id)}`}>Revisiones relacionadas →</Link>
    </div>
  </>;
}

export function GroupNetwork({ group, onOpen, initialRelation, initialCompany }: { group: GroupDetail; onOpen: OpenEvidence; initialRelation?: string; initialCompany?: string }) {
  const [selection, setSelection] = useState<{ kind: "company" | "relation"; id: string } | null>(initialRelation ? { kind: "relation", id: initialRelation } : initialCompany ? { kind: "company", id: initialCompany } : null);
  const [status, setStatus] = useState("all");
  const [company, setCompany] = useState(initialCompany && group.members.some((member) => member.company_id === initialCompany) ? initialCompany : "all");
  const [focusMode, setFocusMode] = useState<FocusMode>(initialCompany ? "ego" : "network");
  const detailPanel = useRef<HTMLElement>(null);
  const visible = group.relations.filter((relation) => (status === "all" || relation.status === status) && (company === "all" || relation.from_company_id === company || relation.to_company_id === company));
  const member = selection?.kind === "company" ? group.members.find((item) => item.company_id === selection.id) : undefined;
  const relation = selection?.kind === "relation" ? visible.find((item) => item.id === selection.id) ?? group.relations.find((item) => item.id === selection.id) : undefined;
  const hasSelection = Boolean(member || relation);

  const selectItem = useCallback((kind: "company" | "relation", id: string) => {
    setSelection({ kind, id });
    requestAnimationFrame(() => detailPanel.current?.scrollIntoView({ block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
  }, []);

  const selectCompany = useCallback((id: string) => selectItem("company", id), [selectItem]);
  const selectRelation = useCallback((id: string) => selectItem("relation", id), [selectItem]);
  const clearSelection = useCallback(() => {
    setSelection(null);
    setFocusMode("network");
  }, []);

  const resetView = () => {
    setStatus("all");
    setCompany("all");
    setSelection(null);
    setFocusMode("network");
  };

  return <>
    <section className={`${base.panel} ${styles.networkHero}`} aria-label="Explorar la red del grupo">
      <div className={styles.panelHeading}>
        <div>
          <h2>Grafo del grupo</h2>
          <p>Pan, zoom y selección sobre la red. Las flechas son transferencias; los nodos, sociedades.</p>
        </div>
        <div className={styles.networkLegend}>
          {Object.entries(relationStatusLabels).map(([key, label]) => <span key={key}><i className={styles[key]} />{label}</span>)}
        </div>
      </div>

      <div className={styles.filters}>
        <label>Evidencia<select aria-label="Evidencia de la relación" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Todas</option><option value="identified">Identificadas</option><option value="candidate">Candidatas</option><option value="unknown">Desconocidas</option></select></label>
        <label>Sociedad<select aria-label="Sociedad conectada" value={company} onChange={(event) => { setCompany(event.target.value); if (event.target.value !== "all") { setSelection({ kind: "company", id: event.target.value }); setFocusMode("ego"); } else setFocusMode("network"); }}><option value="all">Todas</option>{group.members.map((item) => <option key={item.company_id}>{item.company_id}</option>)}</select></label>
        <button className={base.secondaryButton} onClick={resetView}>Restablecer</button>
      </div>

      <div className={styles.networkLayout} data-has-selection={hasSelection || undefined}>
        <NetworkCanvas
          members={group.members}
          relations={visible}
          selection={selection}
          focusMode={focusMode}
          expanded={!hasSelection}
          onSelectCompany={selectCompany}
          onSelectRelation={selectRelation}
          onClearSelection={clearSelection}
        />

        <aside ref={detailPanel} id="group-network-selection" className={styles.selectionPanel} aria-label="Detalle de la selección" aria-live="polite">
          {member ? (
            <MemberDetail
              member={member}
              group={group}
              onOpen={onOpen}
              focusMode={focusMode}
              onShowEgo={() => setFocusMode("ego")}
              onShowNetwork={() => setFocusMode("network")}
            />
          ) : relation ? (
            <RelationDetail relation={relation} group={group} onOpen={onOpen} />
          ) : (
            <>
              <span className={base.eyebrow}>Explora</span>
              <h3>{selection ? "Selección no disponible" : "Pulsa un nodo o una flecha"}</h3>
              <p>{selection ? "Ajusta los filtros o elige otro elemento." : `${numberLabel(group.members.length, 0)} sociedades en el lienzo. Encaja la red o filtra por evidencia.`}</p>
            </>
          )}
        </aside>
      </div>

      <details className={styles.transferDrawer}>
        <summary>
          <strong>Ver todas las transferencias</strong>
          <span>{visible.length}</span>
          <span className={styles.expandMarker} aria-hidden="true">+</span>
        </summary>
        <section className={styles.relationshipList} aria-label="Lista de relaciones">
          {visible.map((edge) => (
            <button key={edge.id} className={styles.relationshipRow} aria-pressed={relation?.id === edge.id} onClick={() => selectRelation(edge.id)}>
              <span>
                <strong>{relationName(edge)}</strong>
                <small>{relationKindLabels[edge.kind]} · {edge.recurrence}</small>
              </span>
              <span className={`${styles.relationBadge} ${styles[edge.status]}`}>{relationStatusLabels[edge.status]}</span>
              <span>{groupMoney(edge.volume)}<small>{relationChangeLabels[edge.change]}</small></span>
              <span aria-hidden="true">→</span>
            </button>
          ))}
          {!visible.length && <p className={base.emptyState}>No hay transferencias con estos filtros.</p>}
        </section>
      </details>
    </section>

    <Link className={styles.nextStep} href={`/groups/${group.group_id}/recommendations`}>
      <span><small>Siguiente</small><strong>Qué revisar antes de actuar</strong></span>
      <span aria-hidden="true">→</span>
    </Link>
  </>;
}
