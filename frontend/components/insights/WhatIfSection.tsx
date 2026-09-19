"use client";

import { useState } from "react";
import type { ScenarioInputs, Simulation } from "@/types/companyDetail";
import { calculateScenario, defaultScenarioInputs } from "@/lib/companyScenario";
import { signedNumber } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function WhatIfSection({ currentPulse, simulation }: { currentPulse: number; simulation: Simulation }) {
  const [requested, setRequested] = useState<ScenarioInputs>({ ...defaultScenarioInputs });
  const scenario = calculateScenario(currentPulse, simulation, requested);
  const changed = Object.values(scenario.inputs).some((value) => value !== 0);

  return <section className={styles.panel} aria-label="What-if">
    <SectionHeading number="07" title="What-if" description="Explore the mechanics. Not a prediction of what happens next."><span className={styles.scenarioBadge}>Scenario, not forecast.</span></SectionHeading>
    <div className={styles.simulationLayout}><div className={styles.simulationControls}>
      <div className={styles.simulationToolbar}><span className={styles.smallText}>Adjustments relative to the current snapshot</span><button className={styles.evidenceButton} onClick={() => setRequested({ ...simulation.example })}>Try example</button></div>
      {simulation.inputs.map((input) => <div className={styles.scenarioControl} key={input.key}>
        <div className={styles.inputHeading}><label htmlFor={`scenario-${input.key}`}>{input.label}</label><output htmlFor={`scenario-${input.key}`}>{signedNumber(scenario.inputs[input.key])} {input.unit}</output></div>
        <input id={`scenario-${input.key}`} type="range" min={input.min} max={input.max} step={input.step} value={scenario.inputs[input.key]} onChange={(event) => setRequested({ ...requested, [input.key]: Number(event.target.value) })} aria-valuetext={`${signedNumber(scenario.inputs[input.key])} ${input.unit} adjustment`} />
        <div className={styles.rangeLabels}><span>{signedNumber(input.min)} {input.unit}</span><span>{input.unit === "days" ? `${input.baseline} → ${input.baseline + scenario.inputs[input.key]} days` : `${input.baseline + scenario.inputs[input.key]}% of current support`}</span><span>{signedNumber(input.max)} {input.unit}</span></div>
        <p>{input.explanation}</p>
      </div>)}
      <button className={styles.secondaryButton} disabled={!changed} onClick={() => setRequested({ ...defaultScenarioInputs })}>Reset scenario</button>
    </div><div className={styles.scenarioResult}>
      <span className={styles.eyebrow}>Illustrative sensitivity</span><div className={styles.scenarioScores} aria-live="polite" aria-atomic="true"><div><span>Current Pulse</span><strong>{currentPulse}</strong></div><span className={styles.scenarioArrow} aria-hidden="true">→</span><div><span>Scenario Pulse</span><strong data-testid="scenario-pulse">{scenario.pulse}</strong></div></div>
      <p className={styles.scenarioDelta}>{signedNumber(scenario.pulse - currentPulse)} pts <span>in this mechanical scenario</span></p>
      <div className={styles.impactList}>{scenario.impacts.map((impact) => <div key={impact.key}><span>{impact.label}</span><strong className={impact.points > 0 ? styles.positiveText : impact.points < 0 ? styles.negativeText : styles.muted}>{signedNumber(impact.points)} pts</strong></div>)}</div>
      <p className={styles.disclaimer}><strong>Scenario, not forecast.</strong> Mock weights, not a validated financial model. No future outcome or cash amount is predicted. Actual terms and support may not be changeable.</p>
      <details className={styles.methodology}><summary>Show mock assumptions</summary><p>{simulation.methodology}</p><ul>{simulation.inputs.map((input) => <li key={input.key}>{input.label}: {signedNumber(input.pulse_points_per_unit)} Pulse points per {input.unit === "days" ? "day" : "1% change"}.</li>)}</ul><p>Contributions are unrounded; displayed Pulse is rounded and capped. The current company snapshot is never changed.</p></details>
    </div></div>
  </section>;
}
