"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { StressScenario, StressTest } from "@/types/companyDetail";
import {
  demoChannels,
  demoGroupTitles,
  demoHealthAtHorizon,
  demoShocksFromValues,
  demoStressCopy,
  demoValuesFromShocks,
  isStressDemoCompany,
  resolveComp1122Custom,
  stressDemoComp1122,
  type StressDemoControl,
  type StressDemoEconomic,
  type StressDemoOutcome,
} from "@/fixtures/stressTestComp1122";
import { numberLabel } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

const factorNames: Record<string, string> = {
  operating_inflow: "Cobros",
  operating_outflow: "Costes",
  observed_debt_service: "Deuda",
  customer_delay: "Cliente",
  variable_rate: "Tipos",
  cost_payroll: "Nómina",
  cost_utilities: "Suministros",
  cost_payment_processing: "Procesamiento",
  cost_other_operating_payment: "Otros pagos",
};
const groupNames = { comercial: "Comercial", costes: "Costes", financiacion: "Financiación", mercado: "Mercado" } as const;
const bandNames = { green: "Verde", amber: "Ámbar", red: "Rojo" } as const;
const factorLabel = (factor: string) => factor.startsWith("fx_") ? (factor === "fx_CAD" ? "CAD" : `FX ${factor.slice(3)}`) : factorNames[factor] ?? "Factor";
const attributionLabel = (factor: string) => factor === "customer_delay" ? "Cliente principal" : factor.startsWith("fx_") ? `FX ${factor.slice(3)}` : factorLabel(factor);
const pointLabel = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${numberLabel(Math.abs(value), 1)}`;
const compactShock = (shock: { factor: string; relative_pct: number; unit: string }) => {
  const name = factorLabel(shock.factor);
  if (shock.unit === "days") return `${name} +${shock.relative_pct}d`;
  if (shock.unit === "bp") return `${name} +${shock.relative_pct} pb`;
  return `${name} ${shock.relative_pct > 0 ? "+" : "−"}${Math.abs(shock.relative_pct)}%`;
};
const tickLabel = (value: number, unit: string) => {
  if (unit === "days") return value === 0 ? "0d" : `+${value}d`;
  if (unit === "bp") return value === 0 ? "0 pb" : `+${value} pb`;
  if (value === 0) return "0%";
  return `${value > 0 ? "+" : "−"}${Math.abs(value)}%`;
};
const sliderLabel = (control: StressDemoControl, value: number) => {
  if (control.factor === "operating_inflow") return `${Math.abs(value)}%`;
  return tickLabel(value, control.unit);
};
const reverseValue = (item: StressTest["reverse_limits"][number]) => item.unit === "days" ? `+${item.value} d` : item.unit === "bp" ? `+${item.value} pb` : `${item.value > 0 ? "+" : "−"}${Math.abs(item.value)} %`;
const reasonNames: Record<string, string> = {
  no_observed_debt_service: "Sin servicio financiero observado con calidad suficiente.",
  insufficient_quality_months: "Falta histórico comparable para aplicar shocks sin inventar datos.",
  v2_scenario_score_unavailable: "El motor V2 no pudo identificar este resultado.",
  v2_score_unavailable: "El Health todavía no es calculable para este corte.",
};
const reasonLabel = (reason: string | null) => reason ? reasonNames[reason] ?? "Resultado no identificable con la evidencia actual." : "Resultado no disponible.";
const emptyCopy = (stressTest?: StressTest) => stressTest?.reason === "v2_score_unavailable"
  ? { title: "Stress Test no disponible", body: "El Health todavía no es calculable para este corte." }
  : { title: "Stress Test aún no disponible", body: "Falta histórico comparable para aplicar shocks sin inventar datos." };
const scenarioResult = (scenario: StressScenario | null, horizon: 1 | 3 | 6) => scenario?.results.find((result) => result.observed_months === horizon) ?? null;
const horizons: Array<1 | 3 | 6> = [1, 3, 6];
const horizonLabel = (horizon: 1 | 3 | 6) => horizon === 1 ? "1 mes" : `${horizon} meses`;

export function preferredObservedHorizon(scenario: StressScenario | null): 1 | 3 | 6 {
  return ([6, 3, 1] as const).find((horizon) => scenarioResult(scenario, horizon)?.status === "available") ?? 6;
}

function StressBoard({ config, result, demo }: { config: ReactNode; result: ReactNode; demo?: boolean }) {
  return <div className={styles.stressBoard} data-stress-demo={demo ? "comp-1122" : undefined}>
    <div className={styles.stressConfig}>{config}</div>
    <aside className={styles.stressResult}>{result}</aside>
  </div>;
}

function TickControl({ control, value, disabled, onChange }: {
  control: { factor: string; label: string; unit: string; positions: number[] };
  value: number; disabled?: boolean; onChange: (value: number) => void;
}) {
  const max = control.positions.length - 1;
  const index = Math.max(0, control.positions.findIndex((position) => position === value));
  const marker = max <= 0 ? 0 : (index / max) * 100;
  return <div className={styles.stressTicks} data-disabled={disabled || undefined}>
    <div className={styles.stressTickTrack} aria-hidden="true"><i style={{ left: `${marker}%` }} /></div>
    <div className={styles.stressTickRow} role="radiogroup" aria-label={control.label}>
      {control.positions.map((position) => <button type="button" key={position} role="radio" aria-checked={position === value} disabled={disabled} onClick={() => onChange(position)}>{tickLabel(position, control.unit)}</button>)}
    </div>
  </div>;
}

function RangeControl({ control, value, onChange }: {
  control: StressDemoControl; value: number; onChange: (value: number) => void;
}) {
  const max = Math.max(control.positions.length - 1, 1);
  const index = Math.max(0, control.positions.findIndex((position) => position === value));
  const display = sliderLabel(control, value);
  const id = `stress-${control.factor}`;
  const start = sliderLabel(control, control.positions[0] ?? 0);
  const end = sliderLabel(control, control.positions[control.positions.length - 1] ?? 0);
  return <div className={styles.stressSlider}>
    <div className={styles.stressSliderHead}>
      <div>
        <label htmlFor={id}>{control.label}</label>
        {control.microcopy && <p>{control.microcopy}</p>}
      </div>
      <output htmlFor={id}>{display}</output>
    </div>
    <div className={styles.stressRange}>
      <input
        id={id}
        type="range"
        min={0}
        max={max}
        step={1}
        value={index}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={index}
        aria-valuetext={`${display}. Recorrido de ${start} a ${end}`}
        onChange={(event) => onChange(control.positions[Number(event.target.value)] ?? 0)}
      />
      <div className={styles.stressAxis} aria-hidden="true">
        {control.positions.map((position, offset) => <i key={position} data-active={position === value || undefined} style={{ left: `${(offset / max) * 100}%` }} />)}
      </div>
      <div className={styles.stressAxisLabels} aria-hidden="true">
        <span>{start}</span>
        <span>{end}</span>
      </div>
    </div>
  </div>;
}

function StressDisclaimer() {
  return <details className={styles.stressInfo}>
    <summary>Escenario, no predicción</summary>
    <p>El resultado describe unas condiciones supuestas, no lo que ocurrirá. El frontend no calcula puntuaciones ni interpola combinaciones. Los plazos y el apoyo reales pueden no ser modificables.</p>
  </details>;
}

function Attribution({ factors }: { factors: { factor: string; points: number }[] }) {
  if (!factors.length) return null;
  const max = Math.max(...factors.map((item) => Math.abs(item.points)), 0.01);
  return <div className={styles.stressAttribution}>
    <h4>Qué explica el impacto</h4>
    <p>Contribución al cambio total de Health.</p>
    {factors.map((item) => <div key={item.factor}>
      <span>{attributionLabel(item.factor)}</span>
      <b><i style={{ width: `${Math.round((Math.abs(item.points) / max) * 100)}%` }} /></b>
      <strong>{pointLabel(item.points)}</strong>
    </div>)}
  </div>;
}

function Outcome({ baseline, health, delta, fromBand, toBand, path, economic }: {
  baseline: number; health: number; delta: number; fromBand: keyof typeof bandNames; toBand: keyof typeof bandNames;
  path: { observed_months: number; health: number }[]; economic?: StressDemoEconomic | null;
}) {
  return <div className={styles.stressHero} aria-live="polite">
    <div className={styles.stressScores}>
      <span>Health</span>
      <strong>{numberLabel(baseline, 0)}</strong>
      <em aria-hidden="true">→</em>
      <strong data-testid="stress-health">{numberLabel(health, 0)}</strong>
      <small className={delta < 0 ? styles.negativeText : delta > 0 ? styles.positiveText : undefined}>{pointLabel(delta)} pts</small>
    </div>
    <p className={styles.stressBand}>{bandNames[fromBand]} → {bandNames[toBand]}</p>
    {path.length > 0 && <p className={styles.stressPath}><span>Exposición sostenida</span><span>{path.map((item) => `${horizonLabel(item.observed_months as 1 | 3 | 6)} ${numberLabel(item.health, 0)}`).join(" · ")}</span></p>}
    {economic && <p className={styles.stressMoney}><span>{economic.label}</span><strong>{economic.value}</strong></p>}
  </div>;
}

function DemoResult({ baseline, health, delta, money, channels }: {
  baseline: number; health: number; delta: number; money: string;
  channels: { id: string; label: string; active: boolean }[];
}) {
  const copy = demoStressCopy(health, delta, money);
  return <>
    <div className={styles.stressDemoReadout} aria-live="polite">
      <span className={styles.stressKicker}>Health</span>
      <div className={styles.stressScores}>
        <strong>{numberLabel(baseline, 0)}</strong>
        <em aria-hidden="true">→</em>
        <strong data-testid="stress-health">{numberLabel(health, 0)}</strong>
        <small className={delta < 0 ? styles.negativeText : delta > 0 ? styles.positiveText : undefined}>{pointLabel(delta)} pts</small>
      </div>
      <span className={styles.stressKicker}>Impacto mensual</span>
      <p className={styles.stressImpact}>{money}</p>
      <ul className={styles.stressChannels}>
        {channels.map((channel) => <li key={channel.id} data-active={channel.active || undefined}>{channel.label}</li>)}
      </ul>
      <p className={styles.stressHeadline}>{copy.headline}</p>
      <p>{copy.body}</p>
      <p>{copy.close}</p>
    </div>
    <StressDisclaimer />
  </>;
}

function DemoStress() {
  const [selectedId, setSelectedId] = useState<string>(stressDemoComp1122.default_preset_id);
  const [horizon, setHorizon] = useState<1 | 3 | 6>(stressDemoComp1122.default_horizon);
  const [values, setValues] = useState(() => demoValuesFromShocks(stressDemoComp1122.presets.find((preset) => preset.id === stressDemoComp1122.default_preset_id)?.shocks ?? []));
  const preset = stressDemoComp1122.presets.find((item) => item.id === selectedId) ?? null;
  const custom = selectedId === "custom";
  const outcome: StressDemoOutcome = custom ? resolveComp1122Custom(values) : preset!.outcome;
  const health = demoHealthAtHorizon(outcome, horizon);
  const delta = health - stressDemoComp1122.baseline_health;
  const groups = (Object.keys(demoGroupTitles) as Array<keyof typeof demoGroupTitles>).filter((group) => stressDemoComp1122.controls.some((control) => control.group === group));
  const choosePreset = (id: string) => {
    const next = stressDemoComp1122.presets.find((item) => item.id === id);
    if (!next) return;
    setSelectedId(id);
    setValues(demoValuesFromShocks(next.shocks));
  };
  const changeControl = (factor: string, value: number) => {
    setSelectedId("custom");
    setValues((current) => ({ ...current, [factor]: value }));
  };
  return <StressBoard demo config={<>
    <div className={styles.stressPills} role="tablist" aria-label="Escenarios">
      {stressDemoComp1122.presets.map((item) => <button type="button" role="tab" key={item.id} aria-selected={selectedId === item.id} onClick={() => choosePreset(item.id)}>{item.label}</button>)}
      <button type="button" role="tab" aria-selected={custom} onClick={() => setSelectedId("custom")}>Personalizado</button>
    </div>
    {groups.map((group) => <div key={group} className={styles.stressCustomGroup}>
      <h5>{demoGroupTitles[group]}</h5>
      {stressDemoComp1122.controls.filter((control) => control.group === group).map((control) => (
        <RangeControl key={control.factor} control={control} value={values[control.factor] ?? 0} onChange={(value) => changeControl(control.factor, value)} />
      ))}
    </div>)}
    <div className={styles.stressCustomGroup}>
      <h5>Horizonte</h5>
      <div className={styles.stressPills} role="tablist" aria-label="Horizonte observado">
        {horizons.map((item) => <button type="button" role="tab" key={item} aria-selected={horizon === item} onClick={() => setHorizon(item)}>{horizonLabel(item)}</button>)}
      </div>
    </div>
  </>} result={<DemoResult baseline={stressDemoComp1122.baseline_health} health={health} delta={delta} money={outcome.economic.value} channels={demoChannels(custom ? values : demoValuesFromShocks(preset?.shocks ?? demoShocksFromValues(values)))} />} />;
}

function liveControls(stressTest: StressTest): StressDemoControl[] {
  return stressTest.custom_factors.map((factor) => ({
    factor: factor.factor, group: factor.group, label: factorLabel(factor.factor),
    microcopy: "", context: factor.factor === "customer_delay" && factor.context?.top1_share != null
      ? `Cliente principal · ${numberLabel(factor.context.top1_share * 100, 0)}% de los cobros`
      : factor.factor === "variable_rate" && factor.context?.outstanding_eur != null
        ? `Deuda variable identificada · €${numberLabel(factor.context.outstanding_eur / 1_000_000, 1)}M`
        : factor.context?.currency ? `Exposición neta ${factor.context.currency}` : null,
    unit: factor.unit, positions: factor.positions.includes(0) ? [...factor.positions].sort((a, b) => a - b) : [0, ...factor.positions].sort((a, b) => a - b),
  }));
}

function LiveStress({ stressTest }: { stressTest: StressTest }) {
  const presets = useMemo(() => stressTest.scenarios.filter((scenario) => scenario.kind === "preset" && scenario.status === "available"), [stressTest]);
  const singles = useMemo(() => stressTest.scenarios.filter((scenario) => scenario.kind === "single_factor" && scenario.status === "available"), [stressTest]);
  const defaultScenario = stressTest.scenarios.find((scenario) => scenario.id === stressTest.default_scenario_id && scenario.status === "available") ?? presets[0] ?? null;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [horizonPick, setHorizonPick] = useState<1 | 3 | 6 | null>(null);
  const selected = stressTest.scenarios.find((scenario) => scenario.id === selectedId && scenario.status === "available") ?? defaultScenario;
  const custom = selected?.kind === "single_factor";
  const horizon = horizonPick ?? preferredObservedHorizon(selected);
  const result = scenarioResult(selected, horizon);
  const controls = liveControls(stressTest);
  const values: Record<string, number> = {};
  for (const control of controls) values[control.factor] = 0;
  for (const shock of selected?.shocks ?? []) values[shock.factor] = shock.relative_pct;
  const choosePreset = (id: string) => {
    const scenario = presets.find((item) => item.id === id);
    if (scenario) {
      setSelectedId(scenario.id);
      setHorizonPick(null);
    }
  };
  const changeControl = (factor: string, value: number) => {
    if (value === 0) {
      setSelectedId(presets[0]?.id ?? null);
      return;
    }
    const match = singles.find((scenario) => scenario.shocks[0]?.factor === factor && scenario.shocks[0]?.relative_pct === value);
    if (match) setSelectedId(match.id);
  };
  const groups = (Object.keys(groupNames) as Array<keyof typeof groupNames>).filter((group) => controls.some((control) => control.group === group));
  return <StressBoard config={<>
    <div className={styles.stressPills} role="tablist" aria-label="Escenarios">
      {presets.map((scenario) => <button type="button" role="tab" key={scenario.id} aria-selected={!custom && selected?.id === scenario.id} onClick={() => choosePreset(scenario.id)}>{scenario.label}</button>)}
      {controls.length > 0 && <button type="button" role="tab" aria-selected={!!custom} onClick={() => singles[0] && setSelectedId(singles[0].id)}>Personalizado</button>}
    </div>
    <p className={styles.stressShocks}>{(selected?.shocks ?? []).map(compactShock).join(" · ") || "Sin shocks activos"}</p>
    {controls.length > 0 && <div className={styles.stressCustom}>
      <h4>Personalizar stress</h4>
      {groups.map((group) => <div key={group} className={styles.stressCustomGroup}>
        <h5>{groupNames[group]}</h5>
        {controls.filter((control) => control.group === group).map((control) => <div key={control.factor} className={styles.stressCustomFactor}>
          <div>
            <span>{control.label}</span>
            {control.context && <small>{control.context}</small>}
          </div>
          <TickControl control={control} value={values[control.factor] ?? 0} onChange={(value) => changeControl(control.factor, value)} />
        </div>)}
      </div>)}
    </div>}
    {stressTest.reverse_limits.length > 0 && <div className={styles.stressLimits}><h4>Límite de resistencia</h4><p>Antes de perder el tramo actual</p><ul>{stressTest.reverse_limits.map((item) => <li key={item.factor}><span>{factorLabel(item.factor)}</span><strong>{reverseValue(item)}</strong></li>)}</ul></div>}
    <div className={styles.stressCustomGroup}>
      <h5>Horizonte</h5>
      <div className={styles.stressPills} role="tablist" aria-label="Horizonte observado">
        {horizons.map((item) => <button type="button" role="tab" key={item} aria-selected={horizon === item} onClick={() => setHorizonPick(item)}>{horizonLabel(item)}</button>)}
      </div>
    </div>
  </>} result={result?.status === "available" && result.health !== null && result.delta_points !== null && result.band && stressTest.baseline_band && stressTest.baseline_health != null
    ? <><Outcome baseline={stressTest.baseline_health} health={result.health} delta={result.delta_points} fromBand={stressTest.baseline_band} toBand={result.band} path={selected?.path ?? []} />
      <Attribution factors={result.attribution?.factors ?? []} /><StressDisclaimer /></>
    : <><div className={styles.stressResultEmpty} role="status"><strong>Resultado no identificable</strong><span>{reasonLabel(result?.reason ?? selected?.reason ?? null)}</span></div><StressDisclaimer /></>} />;
}

export function StressTestSection({ stressTest, companyId }: { stressTest?: StressTest; companyId?: string }) {
  const empty = emptyCopy(stressTest);
  return <section id="stress-test" data-company-section="stress-test" className={`${styles.panel} ${styles.stressSection}`} aria-label="Stress Test">
    <SectionHeading number="07" title="Stress Test" description="Simula cómo respondería el Health ante shocks adversos.">
      <span className={styles.scenarioBadge}>hipotético · no previsión</span>
    </SectionHeading>
    {isStressDemoCompany(companyId) ? <DemoStress /> : !stressTest || stressTest.status === "insufficient_data" || !stressTest.scenarios.some((scenario) => scenario.status === "available")
      ? <div className={styles.stressEmpty} role="status"><strong>{empty.title}</strong><span>{empty.body}</span></div>
      : <LiveStress stressTest={stressTest} />}
  </section>;
}
