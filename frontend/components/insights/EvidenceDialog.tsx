"use client";

import { useEffect, useRef } from "react";
import type { EvidenceGroup } from "@/types/companyDetail";
import { dateLabel, exactMoney } from "@/lib/companyFormat";
import { Confidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function EvidenceDialog({ title, groups, isMock, onClose }: { title: string; groups: EvidenceGroup[]; isMock: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => trigger?.focus();
  }, []);

  return (
    <dialog ref={dialog} className={styles.evidenceDialog} aria-labelledby="evidence-title" onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className={styles.dialogContent}>
        <header className={styles.dialogHeader}>
          <div><span className={styles.eyebrow}>Traceable by design · {isMock ? "Mock evidence" : "Prepared evidence"}</span><h2 id="evidence-title">{title}</h2></div>
          <button autoFocus className={styles.iconButton} onClick={onClose} aria-label="Close evidence">×</button>
        </header>
        <p className={styles.disclaimer}>{isMock ? "Illustrative records for the demo, not verified financial evidence." : "Representative records from the supplied snapshot."} Samples are not the full cohort and do not constitute a complete reconciliation.</p>
        {!groups.length && <p className={styles.emptyState}>Not identifiable with sufficient confidence.</p>}
        {groups.map((group) => {
          const transactions = group.rows.filter((row) => row.kind === "transaction");
          const invoices = group.rows.filter((row) => row.kind === "invoice");
          return (
            <section className={styles.evidenceGroup} key={group.id}>
              <div className={styles.inlineHeading}><h3>{group.title}</h3><Confidence value={group.confidence} /></div>
              <p className={styles.smallText}>{group.period} · {group.rows.length} representative records of {group.total_count} in the {isMock ? "mock " : ""}cohort</p>
              <p>{group.explanation}</p>
              {transactions.length > 0 && <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={`${group.title} transactions`}><table><caption>Representative transactions · EUR</caption><thead><tr><th scope="col">Transaction / date</th><th scope="col">Category</th><th scope="col">Description</th><th scope="col" className={styles.numeric}>Amount</th></tr></thead><tbody>{transactions.map((row) => <tr key={row.id}><td><span className={styles.mono}>{row.id}</span><small>{dateLabel(row.transaction_date)}</small></td><td><span className={`${styles.category} ${styles[row.category]}`}>{row.category}</span></td><td>{row.description}</td><td className={styles.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
              {invoices.length > 0 && <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={`${group.title} invoices`}><table><caption>Representative {invoices[0].side.toUpperCase()} invoices · {invoices[0].counterparty_id} · EUR</caption><thead><tr><th scope="col">Invoice</th><th scope="col">Issue date</th><th scope="col">Due date</th><th scope="col">Payment date</th><th scope="col" className={styles.numeric}>Amount</th></tr></thead><tbody>{invoices.map((row) => <tr key={row.id}><td className={styles.mono}>{row.invoice}</td><td>{dateLabel(row.issue_date)}</td><td>{dateLabel(row.due_date)}</td><td>{row.payment_date ? dateLabel(row.payment_date) : "Not observed"}</td><td className={styles.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
              {!group.rows.length && <p className={styles.emptyState}>No representative records available for this explanation.</p>}
            </section>
          );
        })}
        <footer className={styles.dialogFooter}>Evidence describes what was observed. It does not establish causes or motives.</footer>
      </div>
    </dialog>
  );
}
