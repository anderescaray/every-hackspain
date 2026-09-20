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
    <small>Escenario modelado; no equivale a una operación ejecutable.</small>
  </div>;
}

function LeverRow({ lever, onSelect }: { lever: ActionLever; onSelect?: () => void }) {
  const content = <><span className={styles.actionRowName}>{lever.label}<small>{lever.change_description}</small></span><strong>{lever.delta_points === null ? "No evaluable" : `${signedNumber(lever.delta_points)} pts`}</strong>{onSelect && <span aria-hidden="true">→</span>}</>;
  return <li>{onSelect ? <button type="button" onClick={onSelect} aria-label={`Ver escenario de ${lever.label}`}>{content}</button> : <div className={styles.actionStaticRow}>{content}</div>}</li>;
}

function BusinessSensitivities({ levers }: { levers: ActionLever[] }) {
  if (!levers.length) return null;
  return <div className={styles.actionAlternatives} aria-label="Sensibilidades de negocio"><h3>Sensibilidades de negocio</h3><ul>{levers.map((lever) => <LeverRow key={lever.lever} lever={lever} />)}</ul><p className={styles.actionBusinessNote}>Sensibilidad, no recomendación.</p></div>;
}

function BandPath({ actionability, selected }: { actionability: Actionability; selected: ActionLever }) {
  const band = actionability.next_band;
  if (!band || selected.health_after === null) return null;
  return <div className={styles.actionPath} aria-label={`Health actual ${numberLabel(band.current_health, 0)}, escenario ${numberLabel(selected.health_after, 0)}, objetivo ${numberLabel(band.target_health, 0)}`}>
    <div className={styles.actionPathTop}><h3>Camino al siguiente tramo</h3><strong>{numberLabel(band.target_health, 0)}</strong></div>
    <div className={styles.actionPathTrack} aria-hidden="true">
      <span className={styles.actionPathCurrent} style={{ left: `${band.current_health}%` }} />
      <span className={styles.actionPathScenario} style={{ left: `${selected.health_after}%` }} />
      <span className={styles.actionPathTarget} style={{ left: `${band.target_health}%` }} />
    </div>
    <div className={styles.actionPathLegend}><span><i className={styles.actionLegendCurrent} />Actual <strong>{numberLabel(band.current_health, 0)}</strong></span><span><i className={styles.actionLegendScenario} />Escenario <strong>{numberLabel(selected.health_after, 0)}</strong></span><span><i className={styles.actionLegendTarget} />Objetivo <strong>{numberLabel(band.target_health, 0)}</strong></span></div>
    <p>Umbral de nivel V2 expresado en Health con Momentum fijo.</p>
    {selected.lever === actionability.primary?.lever && band.reachable_with_primary === true && <strong className={styles.actionPathReached}>Cruza el siguiente tramo.</strong>}
  </div>;
}

export function selectActionLever(actionability: Actionability | undefined, selectedId: ActionLever["lever"] | null): ActionLever | null {
  if (!actionability || actionability.status !== "actionable_treasury") return null;
  return actionability.treasury_actions.find((lever) => lever.lever === selectedId) ?? actionability.primary;
}

export function ActionabilitySection({ actionability }: { actionability?: Actionability }) {
  const [selectedId, setSelectedId] = useState<ActionLever["lever"] | null>(null);
  const selected = selectActionLever(actionability, selectedId);
  const treasury = actionability?.treasury_actions ?? [];
  const business = actionability?.business_sensitivities ?? [];
  const alternatives = treasury.filter((lever) => lever.lever !== selected?.lever);
  const hasRail = (actionability?.next_band != null && selected?.health_after != null) || alternatives.length > 0 || business.length > 0;

  return <section id="actionability" data-company-section="actionability" className={`${styles.panel} ${styles.actionSection}`} aria-label="Cómo actuar">
    <SectionHeading number="03" title="Cómo actuar" description="Palancas de tesorería frente a sensibilidades de negocio." />
    {selected && actionability?.status === "actionable_treasury" ? <div className={styles.actionLayout} data-has-rail={hasRail}>
      <div className={styles.actionPrimary}>
        <div className={styles.actionIdentity}><span>TESORERÍA · CAMBIO EVALUADO</span><h3>{selected.label}</h3></div>
        <div className={styles.actionQuantity}><span>{selected.quantity.label}</span><strong>{quantityLabel(selected.quantity.before, selected.quantity.unit)} <span aria-hidden="true">→</span> {quantityLabel(selected.quantity.after, selected.quantity.unit)}</strong></div>
        <div className={styles.actionEffect}>
          <span>EFECTO MODELADO EN HEALTH</span>
          <div className={styles.actionMetric} data-testid="actionability-primary-score">
            <span>{selected.health_before === null ? "—" : numberLabel(selected.health_before, 0)}</span><span className={styles.actionMetricArrow} aria-hidden="true">→</span><strong>{selected.health_after === null ? "—" : numberLabel(selected.health_after, 0)}</strong>{selected.delta_points !== null && <em>{signedNumber(selected.delta_points)} pts</em>}
          </div>
          <small>Escenario a {selected.horizon.full_effect_months} meses · Momentum constante</small>
        </div>
        {(selected.resources?.required != null || selected.cash_equivalent !== null && selected.lever === "debt_service_cut" || selected.efficiency !== null) && <div className={styles.actionStats}>
          {selected.resources?.required != null && <div><strong>{money(selected.resources.required)}</strong><span>Liquidez requerida</span></div>}
          {!selected.resources && selected.cash_equivalent !== null && selected.lever === "debt_service_cut" && <div><strong>{money(selected.cash_equivalent)}</strong><span>Alivio de caja modelado</span></div>}
          {selected.efficiency && <div><strong>{selected.efficiency.value > 0 ? "+" : selected.efficiency.value < 0 ? "−" : ""}{numberLabel(Math.abs(selected.efficiency.value), 2)} pts / €10k</strong><span>{selected.efficiency.label} · nivel V2</span></div>}
        </div>}
        <Feasibility lever={selected} />
      </div>
      {hasRail && <div className={styles.actionSide}>
        <BandPath actionability={actionability} selected={selected} />
        {alternatives.length > 0 && <div className={styles.actionAlternatives} aria-label="Otras palancas de tesorería"><h3>Otras palancas de tesorería</h3><ul>{alternatives.map((lever) => <LeverRow key={lever.lever} lever={lever} onSelect={() => setSelectedId(lever.lever)} />)}</ul></div>}
        <BusinessSensitivities levers={business} />
        <a href="#scenarios" className={styles.actionExplore}>Abrir Stress Testing <span aria-hidden="true">→</span></a>
      </div>}
    </div> : actionability?.status === "business_sensitivity_only" || actionability?.status === "structural_issue" ? <div className={styles.actionContext}>
      <div className={styles.actionContextLead}><strong>{actionability.status === "structural_issue" ? "Problema principalmente operativo" : "Sin palanca de tesorería con impacto identificado"}</strong><span>Las variaciones de negocio son sensibilidades del modelo, no acciones recomendadas.</span></div>
      <BusinessSensitivities levers={business} />
    </div> : <div className={styles.actionQuietState} role="status"><strong>{actionability?.status === "top_band_no_action" ? "Sin siguiente tramo identificado" : actionability?.status === "no_actionable_lever" ? "No se identifica una palanca con impacto positivo" : "Datos insuficientes para evaluar palancas"}</strong><span>{actionability?.status === "top_band_no_action" ? "El nivel V2 ya está en su tramo superior; Health también incorpora Momentum." : actionability?.status === "no_actionable_lever" ? "Los escenarios disponibles no mejoran el Health observado." : "Todavía no hay una sensibilidad fiable para esta empresa."}</span></div>}
  </section>;
}
