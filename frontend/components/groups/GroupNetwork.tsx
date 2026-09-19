"use client";

import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import { useId, useRef, useState } from "react";
import type { GroupDetail, GroupMember, GroupRelation } from "@/types/groupDetail";
import { numberLabel, severityLabels, trajectoryLabels } from "@/lib/companyFormat";
import { groupMoney, groupScore, relationChangeLabels, relationKindLabels, relationName, relationStatusLabels, roleLabels } from "@/lib/groupPresentation";
import { Confidence, EvidenceButton, type OpenEvidence } from "@/components/insights/InsightPrimitives";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

function MemberDetail({ member, group, onOpen }: { member: GroupMember; group: GroupDetail; onOpen: OpenEvidence }) {
  const alerts = group.alerts.filter((alert) => alert.company_refs.includes(member.company_id));
  return <>
    <span className={base.eyebrow}>Sociedad</span>
    <h3>{member.company_id}</h3>
    <span className={styles.roleBadge}>{roleLabels[member.role]}</span>
    <dl className={styles.selectionMetrics}>
      <div><dt>Health Score</dt><dd>{groupScore(member.health_score)}</dd></div>
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
  const [zoom, setZoom] = useState(1);
  const graphId = useId();
  const detailPanel = useRef<HTMLElement>(null);
  const visible = group.relations.filter((relation) => (status === "all" || relation.status === status) && (company === "all" || relation.from_company_id === company || relation.to_company_id === company));
  const resolved = visible.filter((relation) => relation.from_company_id !== null && relation.to_company_id !== null);
  const member = selection?.kind === "company" ? group.members.find((item) => item.company_id === selection.id) : undefined;
  const relation = selection?.kind === "relation" ? visible.find((item) => item.id === selection.id) : undefined;
  const canvasWidth = Math.max(760, group.members.length * 70);
  const canvasHeight = Math.max(520, canvasWidth * 0.7);
  const positions = new Map(group.members.map((item, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(1, group.members.length);
    return [item.company_id, { x: canvasWidth / 2 + Math.cos(angle) * (canvasWidth / 2 - 110), y: canvasHeight / 2 + Math.sin(angle) * (canvasHeight / 2 - 90) }];
  }));
  const selectItem = (kind: "company" | "relation", id: string) => {
    setSelection({ kind, id });
    requestAnimationFrame(() => detailPanel.current?.scrollIntoView({ block: "nearest", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));
  };
  const selectRelation = (id: string) => selectItem("relation", id);

  return <>
    <section className={`${base.panel} ${styles.networkHero}`} aria-label="Explorar la red del grupo">
      <div className={styles.panelHeading}>
        <div>
          <h2>Grafo del grupo</h2>
          <p>Haz clic en una flecha para ver la transferencia. Los nodos son sociedades.</p>
        </div>
        <div className={styles.networkLegend}>
          {Object.entries(relationStatusLabels).map(([key, label]) => <span key={key}><i className={styles[key]} />{label}</span>)}
        </div>
      </div>

      <div className={styles.filters}>
        <label>Evidencia<select aria-label="Evidencia de la relación" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Todas</option><option value="identified">Identificadas</option><option value="candidate">Candidatas</option><option value="unknown">Desconocidas</option></select></label>
        <label>Sociedad<select aria-label="Sociedad conectada" value={company} onChange={(event) => setCompany(event.target.value)}><option value="all">Todas</option>{group.members.map((item) => <option key={item.company_id}>{item.company_id}</option>)}</select></label>
        <button className={base.secondaryButton} onClick={() => { setStatus("all"); setCompany("all"); setSelection(null); setZoom(1); }}>Restablecer</button>
      </div>

      <div className={styles.networkLayout}>
        <div className={styles.graphPanel}>
          <div className={styles.graphToolbar}>
            <span role="status">{visible.length} transferencias · {resolved.length} en el grafo</span>
            <div>
              <button aria-label="Reducir zoom de la red" disabled={zoom <= 0.6} onClick={() => setZoom(Math.max(0.6, zoom - 0.2))}>−</button>
              <output aria-label="Zoom de la red">{numberLabel(zoom * 100, 0)} %</output>
              <button aria-label="Ampliar zoom de la red" disabled={zoom >= 1.6} onClick={() => setZoom(Math.min(1.6, zoom + 0.2))}>+</button>
            </div>
          </div>
          {group.members.length ? (
            <div className={styles.graphViewport} tabIndex={0} role="region" aria-label="Lienzo desplazable de la red">
              <svg width={canvasWidth * zoom} height={canvasHeight * zoom} viewBox={`0 0 ${canvasWidth} ${canvasHeight}`} role="group" aria-label="Grafo interactivo de sociedades y relaciones">
                <defs>{["identified", "candidate", "unknown"].map((state) => <marker key={state} id={`${graphId}-${state}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L8,4 L0,8 Z" fill={state === "identified" ? "#3368bd" : state === "candidate" ? "#92651d" : "#677488"} /></marker>)}</defs>
                {resolved.map((edge, index) => {
                  const start = positions.get(edge.from_company_id!)!;
                  const end = positions.get(edge.to_company_id!)!;
                  const dx = end.x - start.x;
                  const dy = end.y - start.y;
                  const distance = Math.max(1, Math.hypot(dx, dy));
                  const offset = (index % 2 ? -1 : 1) * (36 + index % 3 * 12);
                  const path = `M ${start.x + dx / distance * 39} ${start.y + dy / distance * 39} Q ${(start.x + end.x) / 2 - dy / distance * offset} ${(start.y + end.y) / 2 + dx / distance * offset} ${end.x - dx / distance * 41} ${end.y - dy / distance * 41}`;
                  return <g key={edge.id} role="button" tabIndex={0} aria-label={`Seleccionar relación ${relationName(edge)}: ${relationStatusLabels[edge.status]}`} aria-pressed={relation?.id === edge.id} className={styles.graphEdge} onClick={() => selectRelation(edge.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectRelation(edge.id); } }}>
                    <title>{`${relationName(edge)} · ${relationKindLabels[edge.kind]} · ${groupMoney(edge.volume)}`}</title>
                    <path d={path} fill="none" stroke="transparent" strokeWidth="22" />
                    <path d={path} fill="none" stroke={edge.status === "identified" ? "#3368bd" : edge.status === "candidate" ? "#92651d" : "#677488"} strokeWidth={relation?.id === edge.id ? 4.5 : 2.5} strokeDasharray={edge.status === "candidate" ? "8 5" : edge.status === "unknown" ? "2 6" : undefined} markerEnd={`url(#${graphId}-${edge.status})`} />
                  </g>;
                })}
                {group.members.map((item) => {
                  const position = positions.get(item.company_id)!;
                  return <g key={item.company_id} role="button" tabIndex={0} aria-label={`Seleccionar sociedad ${item.company_id}: Health Score ${groupScore(item.health_score)}, Momentum ${groupScore(item.dimensions.momentum)}, Resiliencia ${groupScore(item.dimensions.resilience)}`} aria-pressed={member?.company_id === item.company_id} transform={`translate(${position.x}, ${position.y})`} className={styles.graphNode} onClick={() => selectItem("company", item.company_id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectItem("company", item.company_id); } }}>
                    <circle r="38" fill={member?.company_id === item.company_id ? "#e7efff" : "white"} stroke={item.attention === "high" ? "#a76539" : "#7694c7"} strokeWidth={member?.company_id === item.company_id ? 3.5 : 2} />
                    <text textAnchor="middle" y="-6" fill="#52647d" fontSize="9">Health</text>
                    <text textAnchor="middle" y="16" fill="#142d56" fontSize="24" fontWeight="600">{groupScore(item.health_score)}</text>
                    <text textAnchor="middle" y="56" fill="#243b5c" fontSize="12" fontWeight="600">{item.company_id}</text>
                    <title>{`${item.company_id} · ${roleLabels[item.role]} · Liquidez: ${groupMoney(item.available_liquidity)}`}</title>
                  </g>;
                })}
              </svg>
            </div>
          ) : (
            <p className={base.emptyState}>No hay sociedades observadas para dibujar una red.</p>
          )}
          {!resolved.length && group.members.length > 0 && <p className={base.emptyState}>No hay conexiones dibujables con estos filtros.</p>}
        </div>

        <aside ref={detailPanel} id="group-network-selection" className={styles.selectionPanel} aria-label="Detalle de la selección" aria-live="polite">
          {member ? (
            <MemberDetail member={member} group={group} onOpen={onOpen} />
          ) : relation ? (
            <RelationDetail relation={relation} group={group} onOpen={onOpen} />
          ) : (
            <>
              <span className={base.eyebrow}>Explora</span>
              <h3>{selection ? "Selección no disponible" : "Pulsa un nodo o una flecha"}</h3>
              <p>{selection ? "Ajusta los filtros o elige otro elemento." : "El detalle aparece aquí: sociedad o transferencia."}</p>
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
