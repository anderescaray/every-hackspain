"use client";

import { useEffect, useRef } from "react";
import type { CashAccount, EvidenceGroup, ObservationEvidence } from "@/types/companyDetail";
import { cashCategoryLabel, dateLabel, exactMoney, numberLabel } from "@/lib/companyFormat";
import { Confidence } from "./InsightPrimitives";
import { AccountIdentity } from "./AccountIdentity";
import styles from "./insights.module.css";

function observationValue(value: number, unit: ObservationEvidence["unit"]) {
  return unit === "EUR" ? exactMoney(value) : `${numberLabel(value)} ${unit === "days" ? "días" : "%"}`;
}

export function EvidenceDialog({ title, groups, accounts = [], groupId, isMock, onClose }: { title: string; groups: EvidenceGroup[]; accounts?: CashAccount[]; groupId: string | null; isMock: boolean; onClose: () => void }) {
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
          <div><span className={styles.eyebrow}>{isMock ? "Evidencia de ejemplo" : "Evidencia"}</span><h2 id="evidence-title">{title}</h2></div>
          <button autoFocus className={styles.iconButton} onClick={onClose} aria-label="Cerrar evidencia">×</button>
        </header>
        <p className={styles.disclaimer}>{isMock ? "Registros ilustrativos para la demo, no evidencia financiera verificada." : "Registros representativos del análisis suministrado."} Las muestras no son el conjunto completo ni constituyen una conciliación integral.</p>
        {!groups.length && <p className={styles.emptyState}>No identificable con suficiente confianza.</p>}
        {groups.map((group) => {
          const transactions = group.rows.filter((row) => row.kind === "transaction");
          const invoices = group.rows.filter((row) => row.kind === "invoice");
          const observations = group.rows.filter((row) => row.kind === "observation");
          return (
            <section className={styles.evidenceGroup} key={group.id}>
              <div className={styles.inlineHeading}><h3>{group.title}</h3><Confidence value={group.confidence} /></div>
              <p className={styles.smallText}>{group.period} · {group.rows.length} registros representativos de {group.total_count} en el conjunto{isMock ? " de ejemplo" : ""}</p>
              <p>{group.explanation}</p>
              {transactions.length > 0 && <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: movimientos`}><table><caption>Movimientos representativos · EUR</caption><thead><tr><th scope="col">Movimiento / fecha</th><th scope="col">Cuenta y titular</th><th scope="col">Categoría</th><th scope="col">Descripción</th><th scope="col" className={styles.numeric}>Importe</th></tr></thead><tbody>{transactions.map((row) => <tr key={row.id}><td><span className={styles.mono}>{row.id}</span><small>{dateLabel(row.transaction_date)}</small></td><td><AccountIdentity account={accounts.find((account) => account.account_id === row.account_id)} accountId={row.account_id} /></td><td><span className={`${styles.category} ${styles[row.category]}`}>{cashCategoryLabel(row.category, groupId)}</span></td><td>{row.description}</td><td className={styles.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
              {invoices.length > 0 && <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: facturas`}><table><caption>Facturas representativas · EUR</caption><thead><tr><th scope="col">Factura</th><th scope="col">Emisión</th><th scope="col">Vencimiento</th><th scope="col">Fecha de pago</th><th scope="col" className={styles.numeric}>Importe</th></tr></thead><tbody>{invoices.map((row) => <tr key={row.id}><td className={styles.mono}>{row.invoice}<small>{row.side === "ar" ? "Cliente" : "Proveedor"} · {row.counterparty_id}</small></td><td>{dateLabel(row.issue_date)}</td><td>{dateLabel(row.due_date)}</td><td>{row.payment_date ? dateLabel(row.payment_date) : "No observado"}</td><td className={styles.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
              {observations.length > 0 && <div className={styles.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: indicadores`}><table><caption>Indicadores agregados{isMock ? " de ejemplo" : ""} · {group.period}</caption><thead><tr><th scope="col">Indicador</th><th scope="col" className={styles.numeric}>Antes</th><th scope="col" className={styles.numeric}>Ahora</th></tr></thead><tbody>{observations.map((row) => <tr key={row.id}><th scope="row">{row.metric}</th><td className={styles.numeric}>{observationValue(row.before, row.unit)}</td><td className={styles.numeric}>{observationValue(row.after, row.unit)}</td></tr>)}</tbody></table></div>}
              {!group.rows.length && <p className={styles.emptyState}>No hay registros representativos disponibles para esta explicación.</p>}
            </section>
          );
        })}
        <footer className={styles.dialogFooter}>La evidencia describe lo observado. No establece causas ni motivos.</footer>
      </div>
    </dialog>
  );
}
