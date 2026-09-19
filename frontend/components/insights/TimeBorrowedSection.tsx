"use client";

import { useState } from "react";
import type { TimeBorrowed, TimingSnapshot } from "@/types/companyDetail";
import { signedNumber } from "@/lib/companyFormat";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

function TimingClock({ label, before, after, tone, definition }: { label: string; before: number; after: number; tone: string; definition: string }) {
  return <div className={styles.timingClock}><span className={styles.eyebrow}>{label}</span><div className={styles.clockComparison}><div className={styles.previousClock}><strong>{before}</strong><span>days before</span></div><span className={styles.clockArrow} aria-hidden="true">→</span><div className={styles.currentClock}><strong>{after}</strong><span>days now</span></div></div><span className={tone}>{signedNumber(after - before)} days</span><p>{definition}</p></div>;
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

  return <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Time Borrowed">
    <SectionHeading number="04" title="Time Borrowed" description="Is cash arriving faster, or did the payment terms change?"><div className={styles.segmented} role="group" aria-label="Invoice side"><button aria-pressed={side === "ar"} onClick={() => setSide("ar")}>AR · Customers</button><button aria-pressed={side === "ap"} onClick={() => setSide("ap")}>AP · Suppliers</button></div></SectionHeading>
    {!data ? <p className={styles.emptyState}>Not identifiable with sufficient confidence. No {side === "ar" ? "customer" : "supplier"} timing evidence is available.</p> : <>
      <div className={styles.timingContext}><span className={styles.mono}>{data.counterparty_id}</span><span>{data.before.period} <span aria-hidden="true">→</span> {data.after.period}</span><Confidence value={data.confidence} /></div>
      <div className={styles.clocks}>
        <TimingClock label="Payment term" before={data.before.payment_term} after={data.after.payment_term} tone={tone("payment_term")} definition={side === "ar" ? "Time granted to the customer before the invoice is due." : "Time received from the supplier before payment is due."} />
        <TimingClock label={side === "ar" ? "Time to cash" : "Time to payment"} before={data.before.time_to_cash} after={data.after.time_to_cash} tone={tone("time_to_cash")} definition={side === "ar" ? "Observed time from invoice issue to customer payment." : "Observed time from invoice issue to supplier payment."} />
        <TimingClock label="Delay" before={data.before.delay} after={data.after.delay} tone={tone("delay")} definition="Late payment: observed days beyond the due date." />
      </div>
      <div className={styles.timingInsight}><div><span className={styles.eyebrow}>The timing behind the number</span><h3>{data.headline}</h3><p>{data.explanation}</p></div><EvidenceButton refs={data.evidence_refs} title={`${side === "ar" ? "Customer" : "Supplier"} payment timing`} onOpen={onOpen} /></div>
      <details className={styles.methodology}><summary>How to read these clocks · {data.evidence_count} invoices</summary><p>{data.methodology}</p><p>{side === "ar" ? "AR: more time granted means the company finances the customer for longer." : "AP: less time received means the company needs cash earlier. Additional late payment is not treated as an improvement."} No motives are assumed.</p></details>
    </>}
  </section>;
}
