"use client";

import { useState } from "react";
import type { TimeBorrowed, TimingSnapshot } from "@/types/companyDetail";
import { signedNumber } from "@/lib/companyFormat";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

function TimingClock({ label, before, after, tone, definition }: { label: string; before: number; after: number; tone: string; definition: string }) {
  return <div className={styles.timingClock}><span className={styles.eyebrow}>{label}</span><div className={styles.clockComparison}><div className={styles.previousClock}><strong>{before}</strong><span>días antes</span></div><span className={styles.clockArrow} aria-hidden="true">→</span><div className={styles.currentClock}><strong>{after}</strong><span>días ahora</span></div></div><span className={tone}>{signedNumber(after - before)} días</span><p>{definition}</p></div>;
}

export function TimeBorrowedSection({ timing, onOpen }: { timing: TimeBorrowed; onOpen: OpenEvidence }) {
  const [side, setSide] = useState<"ar" | "ap">("ar");
  const data = timing[side];
  const tone = (metric: keyof Omit<TimingSnapshot, "period">) => {
    if (!data) return styles.muted;
    const change = data.after[metric] - data.before[metric];
    if (change === 0 || (side === "ap" && metric !== "payment_term")) return styles.muted;
    const positive = side === "ar" ? change < 0 : change > 0;
    return positive ? styles.positiveText : styles.negativeText;
  };

  return <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Tiempo financiado">
    <SectionHeading number="05" title="Tiempo financiado" description="Plazos de cobro a clientes y pago a proveedores."><div className={styles.segmented} role="group" aria-label="Tipo de contraparte"><button aria-pressed={side === "ar"} onClick={() => setSide("ar")}>Clientes · AR</button><button aria-pressed={side === "ap"} onClick={() => setSide("ap")}>Proveedores · AP</button></div></SectionHeading>
    {!data ? <p className={styles.emptyState}>No identificable con suficiente confianza. No hay evidencia de plazos de {side === "ar" ? "clientes" : "proveedores"} disponible.</p> : <>
      <div className={styles.timingContext}><span className={styles.mono}>{data.counterparty_id}</span><span>{data.before.period} <span aria-hidden="true">→</span> {data.after.period}</span><Confidence value={data.confidence} /></div>
      <div className={styles.clocks}>
        <TimingClock label="Plazo acordado" before={data.before.payment_term} after={data.after.payment_term} tone={tone("payment_term")} definition={side === "ar" ? "Tiempo concedido al cliente antes del vencimiento de la factura." : "Tiempo recibido del proveedor antes del vencimiento del pago."} />
        <TimingClock label={side === "ar" ? "Tiempo hasta cobro" : "Tiempo hasta pago"} before={data.before.time_to_cash} after={data.after.time_to_cash} tone={tone("time_to_cash")} definition={side === "ar" ? "Tiempo observado desde la emisión de la factura hasta el cobro." : "Tiempo observado desde la emisión de la factura hasta el pago al proveedor."} />
        <TimingClock label="Retraso" before={data.before.delay} after={data.after.delay} tone={tone("delay")} definition="Días observados de pago después del vencimiento." />
      </div>
      <div className={styles.timingInsight}><div><span className={styles.eyebrow}>Plazos</span><h3>{data.headline}</h3><p>{data.explanation}</p></div><EvidenceButton refs={data.evidence_refs} title={side === "ar" ? "Plazos y cobros de clientes" : "Plazos y pagos a proveedores"} onOpen={onOpen} /></div>
      <details className={styles.methodology}><summary>Cómo interpretar los tiempos · {data.evidence_count} facturas</summary><p>{data.methodology}</p><p>{side === "ar" ? "Clientes (AR): conceder más plazo significa financiarlos durante más tiempo." : "Proveedores (AP): recibir menos plazo significa necesitar caja antes. Un mayor retraso al pagar no se considera una mejora."} No se presuponen motivos.</p></details>
    </>}
  </section>;
}
