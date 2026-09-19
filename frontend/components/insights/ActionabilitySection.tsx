"use client";

import { useState } from "react";
import type { Actionability, ActionLever } from "@/types/companyDetail";
import { exactMoney, money, numberLabel, signedNumber } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

const quantityLabel = (value: number, unit: ActionLever["quantity"]["unit"]) => unit === "days" ? `${numberLabel(value)} días` : money(value);

function Feasibility({ lever }: { lever: ActionLever }) {
  const resources = lever.resources;
  if (!resources) return null;
  const state = resources.feasibility === "own_liquidity_sufficient"
    ? "Viable con caja propia"
    : resources.feasibility === "requires_financing" && resources.gap !== null
      ? `Faltan ${money(resources.gap)}`
      : "Liquidez no evaluable";
  return <div className={styles.actionFeasibility}>
    <span className={styles.actionStatusDot} data-state={resources.feasibility} aria-hidden="true" />
    <span>{state}</span>
    {resources.required !== null && resources.own_available !== null && <small>{exactMoney(resources.required)} requeridos · {exactMoney(resources.own_available)} disponibles</small>}
    {resources.scope === "selected_grid_scenario" && <small>Para el escenario mostrado; no implica una operación ejecutable.</small>}
  </div>;
}

function BandPath({ actionability, selected }: { actionability: Actionability; selected: ActionLever }) {
  const band = actionability.next_band;
  if (!band || band.current_level === null || band.target_level === null) return <div className={styles.actionPathEmpty}>Siguiente tramo no disponible.</div>;
  return <div className={styles.actionPath} aria-label={`Nivel actual ${numberLabel(band.current_level, 0)}, escenario ${numberLabel(selected.level_after, 0)}, siguiente tramo ${numberLabel(band.target_level, 0)}`}>
    <div className={styles.actionPathTop}><h3>Camino al siguiente tramo</h3><strong>{numberLabel(band.target_level, 0)}</strong></div>
    <div className={styles.actionPathTrack} aria-hidden="true">
      <span className={styles.actionPathCurrent} style={{ left: `${band.current_level}%` }} />
      <span className={styles.actionPathScenario} style={{ left: `${selected.level_after}%` }} />
      <span className={styles.actionPathTarget} style={{ left: `${band.target_level}%` }} />
    </div>
    <div className={styles.actionPathLegend}><span><i className={styles.actionLegendCurrent} />Actual <strong>{numberLabel(band.current_level, 0)}</strong></span><span><i className={styles.actionLegendScenario} />Escenario <strong>{numberLabel(selected.level_after, 0)}</strong></span><span><i className={styles.actionLegendTarget} />Objetivo <strong>{numberLabel(band.target_level, 0)}</strong></span></div>
    {selected.lever === actionability.primary?.lever && band.reachable_with_primary === true && <p>Cruza el siguiente tramo de nivel.</p>}
  </div>;
}

export function selectActionLever(actionability: Actionability | undefined, selectedId: ActionLever["lever"] | null): ActionLever | null {
  if (!actionability) return null;
  return [actionability.primary, ...actionability.alternatives].find((lever) => lever?.lever === selectedId) ?? actionability.primary;
}

export function ActionabilitySection({ actionability }: { actionability?: Actionability }) {
  const [selectedId, setSelectedId] = useState<ActionLever["lever"] | null>(null);
  const levers = actionability ? [actionability.primary, ...actionability.alternatives].filter((item): item is ActionLever => item !== null) : [];
  const selected = selectActionLever(actionability, selectedId);
  const alternatives = levers.filter((lever) => lever.lever !== selected?.lever).slice(0, 4);
  const metricIsHealth = selected != null && selected.health_before !== null && selected.health_after !== null;
  const metricBefore = metricIsHealth ? selected?.health_before : selected?.level_before;
  const metricAfter = metricIsHealth ? selected?.health_after : selected?.level_after;

  return <section className={`${styles.panel} ${styles.actionSection}`} aria-label="Qué puede mover tu Health">
    <SectionHeading number="03" title="Qué puede mover tu Health" description="Palancas con mayor impacto bajo las condiciones actuales." />
    {!selected ? <div className={styles.actionQuietState} role="status"><strong>No hay una palanca evaluable.</strong><span>{actionability?.status === "no_actionable_lever" ? "Ningún cambio aislado muestra un efecto positivo suficiente." : "Todavía no hay sensibilidades calculadas para esta empresa."}</span></div> : <div className={styles.actionLayout}>
      <div className={styles.actionPrimary}>
        <div className={styles.actionIdentity}><span>{selected.type === "treasury" ? selected.lever === actionability?.primary?.lever ? "MEJOR PALANCA · TESORERÍA" : "PALANCA · TESORERÍA" : "SENSIBILIDAD · NEGOCIO"}</span><h3>{selected.label}</h3></div>
        {actionability?.status === "business_sensitivity" && selected.type === "business" && <p className={styles.actionStructural}>{actionability.structural_issue ? "Problema principalmente operativo" : "Sin palanca de tesorería con impacto suficiente"}</p>}
        <div className={styles.actionMetric} data-testid="actionability-primary-score"><span>{metricBefore === null || metricBefore === undefined ? "—" : numberLabel(metricBefore, 0)}</span><span className={styles.actionMetricArrow} aria-hidden="true">→</span><strong>{metricAfter === null || metricAfter === undefined ? "—" : numberLabel(metricAfter, 0)}</strong>{selected.delta_points !== null && <em>{signedNumber(selected.delta_points)} pts</em>}</div>
        <div className={styles.actionMetricCaption}>{metricIsHealth ? "Health · escenario a seis meses" : "Nivel · escenario a seis meses"}</div>
        <div className={styles.actionQuantity}><span>{selected.quantity.label}</span><strong>{quantityLabel(selected.quantity.before, selected.quantity.unit)} <span aria-hidden="true">→</span> {quantityLabel(selected.quantity.after, selected.quantity.unit)}</strong></div>
        <div className={styles.actionStats}>
          {selected.resources?.required !== null && selected.resources?.required !== undefined && <div><strong>{money(selected.resources.required)}</strong><span>{selected.resources.kind === "liquidity" ? "Liquidez requerida" : "Alivio de caja"}</span></div>}
          {!selected.resources && selected.cash_equivalent !== null && selected.lever === "debt_service_cut" && <div><strong>{money(selected.cash_equivalent)}</strong><span>Alivio de caja modelado</span></div>}
          {selected.efficiency && <div><strong>{selected.efficiency.value > 0 ? "+" : selected.efficiency.value < 0 ? "−" : ""}{numberLabel(Math.abs(selected.efficiency.value), 2)} pts / €10k</strong><span>{selected.efficiency.label} · nivel</span></div>}
          <div><strong>{selected.horizon.full_effect_months} meses</strong><span>Efecto pleno modelado</span></div>
        </div>
        <Feasibility lever={selected} />
      </div>
      <div className={styles.actionSide}>
        {actionability && <BandPath actionability={actionability} selected={selected} />}
        <div className={styles.actionAlternatives}><h3>Otras palancas</h3>{alternatives.length ? <ul>{alternatives.map((lever) => <li key={lever.lever}><button type="button" onClick={() => setSelectedId(lever.lever)} aria-label={`Ver sensibilidad de ${lever.label}`}><span>{lever.label}</span><small>{lever.type === "treasury" ? "TESORERÍA" : "NEGOCIO"}</small><strong>{lever.delta_points === null ? "No evaluable" : `${signedNumber(lever.delta_points)} pts`}</strong><span aria-hidden="true">→</span></button></li>)}</ul> : <p>No hay otras palancas evaluables.</p>}</div>
        {levers.some((lever) => lever.type === "business") && <p className={styles.actionBusinessNote}>Negocio = sensibilidad, no recomendación.</p>}
        <a href="#scenarios" className={styles.actionExplore}>Explorar escenarios <span aria-hidden="true">→</span></a>
      </div>
    </div>}
  </section>;
}
