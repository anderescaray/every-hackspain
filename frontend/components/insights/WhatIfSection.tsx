"use client";

import { useState } from "react";
import type { ScenarioInputs, Simulation } from "@/types/companyDetail";
import { selectScenario, defaultScenarioInputs } from "@/lib/companyScenario";
import { signedNumber } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function WhatIfSection({ currentHealthScore, simulation }: { currentHealthScore: number | null; simulation: Simulation }) {
  const [requested, setRequested] = useState<ScenarioInputs>({ ...defaultScenarioInputs });
  const scenario = selectScenario(currentHealthScore, simulation, requested);
  const changed = Object.values(scenario.inputs).some((value) => value !== 0);
  const example = simulation.scenarios.find((item) => item.id === simulation.example_id);

  return <section className={styles.panel} aria-label="Simulador de escenarios">
    <SectionHeading number="06" title="Simulador de escenarios" description="¿Qué pasaría con el Health Score si cambian los plazos o el apoyo?"><span className={styles.scenarioBadge}>Escenario, no predicción.</span></SectionHeading>
    <div className={styles.simulationLayout}><div className={styles.simulationControls}>
      {simulation.scenarios.length > 0 ? <div className={styles.simulationToolbar}>
        <label className={styles.scenarioPicker}>Escenarios disponibles<select aria-label="Escenarios disponibles" value={simulation.scenarios.find((item) => simulation.inputs.every((input) => item.inputs[input.key] === scenario.inputs[input.key]))?.id ?? ""} onChange={(event) => { const selected = simulation.scenarios.find((item) => item.id === event.target.value); setRequested(selected ? { ...selected.inputs } : { ...defaultScenarioInputs }); }}><option value="">{changed ? "Combinación sin resultado precalculado" : "Situación actual"}</option>{simulation.scenarios.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        {example && <button className={styles.secondaryButton} onClick={() => setRequested({ ...example.inputs })}>Probar ejemplo</button>}
      </div> : <p className={styles.emptyState}>Todavía no hay escenarios precalculados disponibles.</p>}
      {simulation.inputs.map((input) => {
        const unit = input.unit === "days" ? "días" : "%";
        return <div className={styles.scenarioControl} key={input.key}>
          <div className={styles.inputHeading}><label htmlFor={`scenario-${input.key}`}>{input.label}</label><output htmlFor={`scenario-${input.key}`}>{signedNumber(scenario.inputs[input.key])} {unit}</output></div>
          <input id={`scenario-${input.key}`} type="range" min={input.min} max={input.max} step={input.step} value={scenario.inputs[input.key]} onChange={(event) => setRequested({ ...requested, [input.key]: Number(event.target.value) })} aria-valuetext={`Ajuste de ${signedNumber(scenario.inputs[input.key])} ${unit}`} />
          <div className={styles.rangeLabels}><span>{signedNumber(input.min)} {unit}</span><span>{input.unit === "days" ? `${input.baseline} → ${input.baseline + scenario.inputs[input.key]} días` : `${input.baseline + scenario.inputs[input.key]} % del apoyo actual`}</span><span>{signedNumber(input.max)} {unit}</span></div>
        </div>;
      })}
      {simulation.inputs.length > 0 && <button className={styles.secondaryButton} disabled={!changed} onClick={() => setRequested({ ...defaultScenarioInputs })}>Restablecer escenario</button>}
    </div><div className={styles.scenarioResult}>
      <span className={styles.eyebrow}>Resultado</span>
      <div className={styles.scenarioScores} aria-live="polite" aria-atomic="true"><div><span>Health Score actual</span><strong>{currentHealthScore ?? "—"}</strong></div><span className={styles.scenarioArrow} aria-hidden="true">→</span><div><span>Health Score escenario</span><strong data-testid="scenario-health-score">{scenario.health_score ?? "—"}</strong>{scenario.health_score === null && <small>No disponible</small>}</div></div>
      {scenario.health_score !== null && currentHealthScore !== null && <p className={`${styles.scenarioDelta} ${scenario.health_score > currentHealthScore ? styles.positiveText : scenario.health_score < currentHealthScore ? styles.negativeText : ""}`}>{signedNumber(scenario.health_score - currentHealthScore)} puntos <span>vs. situación actual</span></p>}
      <p className={styles.scenarioExplanation} role="status">{scenario.explanation}</p>
      {scenario.impacts.length > 0 && <div className={styles.impactList}>{scenario.impacts.map((impact) => <div key={impact.key}><span>{impact.label}</span><strong className={impact.points > 0 ? styles.positiveText : impact.points < 0 ? styles.negativeText : styles.muted}>{signedNumber(impact.points)} puntos</strong></div>)}</div>}
      <details className={styles.infoDisclosure}>
        <summary><span aria-hidden="true" className={styles.infoIcon}>i</span>Cómo funciona el simulador</summary>
        <div>
          <p><strong>Escenario, no predicción.</strong> El resultado describe unas condiciones supuestas, no lo que ocurrirá. El frontend no calcula puntuaciones ni interpola combinaciones. Los plazos y el apoyo reales pueden no ser modificables.</p>
          {simulation.inputs.length > 0 && <dl>{simulation.inputs.map((input) => <div key={input.key}><dt>{input.label}</dt><dd>{input.explanation}</dd></div>)}</dl>}
          <p>{simulation.methodology}</p>
          <p>El análisis actual nunca se modifica. La confianza del análisis no se recalcula.</p>
        </div>
      </details>
    </div></div>
  </section>;
}
