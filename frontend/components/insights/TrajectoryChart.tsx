"use client";

import { useId, useState, type PointerEvent } from "react";
import type { HistoryPoint, Trajectory } from "@/types/companyDetail";
import { dateLabel, signedNumber, trajectoryLabels } from "@/lib/companyFormat";
import { SectionHeading } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function TrajectoryChart({ history: observations, trajectory }: { history: HistoryPoint[]; trajectory: Trajectory | null }) {
  const history = observations.filter((point): point is HistoryPoint & { health_score: number } => point.health_score !== null);
  const direction = trajectory ? trajectoryLabels[trajectory] : "Trayectoria no evaluable";
  const [activeIndex, setActiveIndex] = useState(Math.max(0, history.length - 1));
  const chartId = useId();
  const current = history[Math.min(activeIndex, history.length - 1)];
  const first = history[0];
  const last = history.at(-1);
  const step = 680 / Math.max(1, history.length - 1);
  const x = (index: number) => 44 + index * step;
  const y = (value: number) => 224 - value * 2;
  const points = history.map((point, index) => `${x(index)},${y(point.health_score)}`).join(" ");
  const tone = trajectory === "improving" ? styles.positiveText : trajectory === "deteriorating" ? styles.negativeText : styles.muted;
  const selectFromPointer = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const index = Math.round(((event.clientX - box.left) / box.width * 760 - 44) / step);
    setActiveIndex(Math.max(0, Math.min(history.length - 1, index)));
  };
  const labelX = current ? Math.max(66, Math.min(702, x(activeIndex))) : 0;

  return (
    <section className={styles.panel} aria-label="Tendencia">
      <SectionHeading number="01" title="Tendencia"><span className={styles.periodBadge}>{history.length} meses</span></SectionHeading>
      {!current || !first || !last ? <p className={styles.emptyState}>Todavía no hay histórico de Health Score publicado.</p> : <>
        <div className={styles.chartSummary}>
          <div><strong>{first.health_score} <span aria-hidden="true">→</span> {last.health_score}</strong><span className={tone}>{history.length > 1 ? `${signedNumber(last.health_score - first.health_score)} puntos · ` : "Una observación · "}{direction}</span></div>
          <div className={styles.chartReadout} aria-live="polite"><span>{dateLabel(current.month, true)}</span><strong>{current.health_score}<small>/ 100</small></strong></div>
        </div>
        <svg viewBox="0 0 760 266" className={styles.chart} role="img" aria-labelledby={`${chartId}-title ${chartId}-description`} onPointerMove={selectFromPointer}>
          <title id={`${chartId}-title`}>{`Tendencia del Health Score: de ${first.health_score} a ${last.health_score}`}</title>
          <desc id={`${chartId}-description`}>{`${history.length} observaciones mensuales de ${dateLabel(first.month, true)} a ${dateLabel(last.month, true)}. ${direction}. Usa el selector de mes o la tabla para consultar cada valor.`}</desc>
          <defs><linearGradient id={`${chartId}-fill`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3878f6" stopOpacity="0.15" /><stop offset="100%" stopColor="#3878f6" stopOpacity="0" /></linearGradient></defs>
          {[0, 25, 50, 75, 100].map((value) => <g key={value}><line x1="44" x2="724" y1={y(value)} y2={y(value)} stroke="#e4e8f0" strokeDasharray={value === 0 ? undefined : "3 5"} /><text x="30" y={y(value) + 4} textAnchor="end" fill="#5c6478" fontSize="12">{value}</text></g>)}
          <polygon points={`${x(0)},224 ${points} ${x(history.length - 1)},224`} fill={`url(#${chartId}-fill)`} />
          <polyline points={points} fill="none" stroke="#326ce0" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
          <line x1={x(activeIndex)} x2={x(activeIndex)} y1="24" y2="224" stroke="#9babd0" strokeDasharray="4 4" />
          {history.map((point, index) => <circle key={point.month} cx={x(index)} cy={y(point.health_score)} r={index === activeIndex ? 6 : 3} fill={index === activeIndex ? "#326ce0" : "white"} stroke="#326ce0" strokeWidth="2"><title>{`${dateLabel(point.month, true)}: Health Score ${point.health_score}`}</title></circle>)}
          <g aria-hidden="true" className={styles.chartTooltip}>
            <rect x={labelX - 22} y={y(current.health_score) - 42} width="44" height="28" rx="7" fill="#050b2c" />
            <text x={labelX} y={y(current.health_score) - 22} textAnchor="middle" fill="white" fontSize="17" fontWeight="650">{current.health_score}</text>
          </g>
          {history.filter((_, index) => index === 0 || index === history.length - 1 || index % 6 === 0).map((point) => <text key={point.month} x={x(history.indexOf(point))} y="253" textAnchor="middle" fill="#5c6478" fontSize="12">{dateLabel(point.month, true)}</text>)}
        </svg>
        <label className={styles.chartSlider}>Explorar mes <input type="range" min="0" max={history.length - 1} value={activeIndex} onChange={(event) => setActiveIndex(Number(event.target.value))} aria-valuetext={`${dateLabel(current.month, true)}: Health Score ${current.health_score}`} /></label>
        <details className={styles.methodology}><summary>Ver valores mensuales</summary><div className={styles.tableScroll}><table><caption>Histórico mensual del Health Score</caption><thead><tr><th scope="col">Mes</th><th scope="col">Health Score</th></tr></thead><tbody>{history.map((point) => <tr key={point.month}><td>{dateLabel(point.month, true)}</td><td>{point.health_score}</td></tr>)}</tbody></table></div></details>
      </>}
    </section>
  );
}
