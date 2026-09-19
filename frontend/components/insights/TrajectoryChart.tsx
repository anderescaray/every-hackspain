"use client";

import { useId, useState } from "react";
import type { HistoryPoint, Trajectory } from "@/types/companyDetail";
import { dateLabel, signedNumber } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function TrajectoryChart({ history, trajectory }: { history: HistoryPoint[]; trajectory: Trajectory }) {
  const [showHealth, setShowHealth] = useState(false);
  const [activeIndex, setActiveIndex] = useState(Math.max(0, history.length - 1));
  const chartId = useId();
  const current = history[Math.min(activeIndex, history.length - 1)];
  const first = history[0];
  const last = history.at(-1);
  const x = (index: number) => 44 + index * (680 / Math.max(1, history.length - 1));
  const y = (value: number) => 224 - value * 2;
  const points = (key: "pulse" | "health") => history.map((point, index) => `${x(index)},${y(point[key])}`).join(" ");

  return (
    <section className={styles.panel} aria-label="Trajectory">
      <SectionHeading number="01" title="Trajectory" description="Not just where you are. Where you’re heading."><span className={styles.periodBadge}>{history.length} months</span></SectionHeading>
      {!current || !first || !last ? <p className={styles.emptyState}>No history is available for this company.</p> : <>
        <div className={styles.chartSummary}><div><strong>{first.pulse} <span aria-hidden="true">→</span> {last.pulse}</strong><span className={trajectory === "improving" ? styles.positiveText : trajectory === "deteriorating" ? styles.negativeText : styles.muted}>{signedNumber(last.pulse - first.pulse)} pts · {trajectory}</span></div><label className={styles.checkbox}><input type="checkbox" checked={showHealth} onChange={(event) => setShowHealth(event.target.checked)} />Show Health</label></div>
        <div className={styles.chartLegend}><span><i className={styles.pulseDot} />Pulse</span>{showHealth && <span><i className={styles.healthDot} />Health</span>}<span className={styles.chartReadout}>{dateLabel(current.month, true)} · Pulse {current.pulse}{showHealth ? ` · Health ${current.health}` : ""}</span></div>
        <svg viewBox="0 0 760 266" className={styles.chart} role="img" aria-labelledby={`${chartId}-title ${chartId}-description`}>
          <title id={`${chartId}-title`}>{`Pulse trajectory: ${first.pulse} to ${last.pulse}`}</title>
          <desc id={`${chartId}-description`}>{`${history.length} monthly observations from ${dateLabel(first.month, true)} to ${dateLabel(last.month, true)}. ${trajectory}. Use the month slider or data table for individual values.`}</desc>
          <defs><linearGradient id={`${chartId}-fill`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#157c79" stopOpacity="0.13" /><stop offset="100%" stopColor="#157c79" stopOpacity="0" /></linearGradient></defs>
          {[0, 25, 50, 75, 100].map((value) => <g key={value}><line x1="44" x2="724" y1={y(value)} y2={y(value)} stroke="#e6edf0" strokeDasharray={value === 0 ? undefined : "3 5"} /><text x="30" y={y(value) + 4} textAnchor="end" fill="#667983" fontSize="11">{value}</text></g>)}
          <polygon points={`${x(0)},224 ${points("pulse")} ${x(history.length - 1)},224`} fill={`url(#${chartId}-fill)`} />
          {showHealth && <polyline points={points("health")} fill="none" stroke="#8997b5" strokeWidth="2" strokeDasharray="5 5" />}
          <polyline points={points("pulse")} fill="none" stroke="#157c79" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
          <line x1={x(activeIndex)} x2={x(activeIndex)} y1="24" y2="224" stroke="#9cbbbc" strokeDasharray="4 4" />
          {history.map((point, index) => <circle key={point.month} cx={x(index)} cy={y(point.pulse)} r={index === activeIndex ? 5 : 3} fill={index === activeIndex ? "#157c79" : "white"} stroke="#157c79" strokeWidth="2" onMouseEnter={() => setActiveIndex(index)}><title>{`${dateLabel(point.month, true)}: Pulse ${point.pulse}`}</title></circle>)}
          {history.filter((_, index) => index === 0 || index === history.length - 1 || index % 6 === 0).map((point) => <text key={point.month} x={x(history.indexOf(point))} y="253" textAnchor="middle" fill="#667983" fontSize="11">{dateLabel(point.month, true)}</text>)}
        </svg>
        <label className={styles.chartSlider}>Explore month <input type="range" min="0" max={history.length - 1} value={activeIndex} onChange={(event) => setActiveIndex(Number(event.target.value))} aria-valuetext={`${dateLabel(current.month, true)}: Pulse ${current.pulse}${showHealth ? `, Health ${current.health}` : ""}`} /></label>
        <details className={styles.methodology}><summary>View monthly values</summary><div className={styles.tableScroll}><table><caption>Monthly score history</caption><thead><tr><th scope="col">Month</th><th scope="col">Pulse</th><th scope="col">Health</th></tr></thead><tbody>{history.map((point) => <tr key={point.month}><td>{dateLabel(point.month, true)}</td><td>{point.pulse}</td><td>{point.health}</td></tr>)}</tbody></table></div></details>
      </>}
    </section>
  );
}
