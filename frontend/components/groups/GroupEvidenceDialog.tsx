"use client";

import { useEffect, useRef } from "react";
import type { GroupEvidence } from "@/types/groupDetail";
import { dateLabel, exactMoney, numberLabel } from "@/lib/companyFormat";
import { Confidence } from "@/components/insights/InsightPrimitives";
import base from "@/components/insights/insights.module.css";
import styles from "./groups.module.css";

export function GroupEvidenceDialog({ title, evidence, isFixture, onClose }: { title: string; evidence: GroupEvidence[]; isFixture: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => trigger?.focus();
  }, []);

  return <dialog ref={dialog} className={base.evidenceDialog} aria-labelledby="group-evidence-title" onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className={base.dialogContent}>
      <header className={base.dialogHeader}><div><span className={base.eyebrow}>{isFixture ? "Evidencia de ejemplo" : "Evidencia"}</span><h2 id="group-evidence-title">{title}</h2></div><button autoFocus className={base.iconButton} aria-label="Cerrar evidencia de grupo" onClick={onClose}>×</button></header>
      <p className={base.disclaimer}>{isFixture ? "Registros ficticios para probar la interfaz. " : "Registros seleccionados del análisis recibido. "}Las muestras no son una conciliación completa. Una relación candidata no se convierte en identificada por abrir su evidencia.</p>
      {!evidence.length && <p className={base.emptyState}>No hay evidencia suficiente disponible para esta explicación.</p>}
      {evidence.map((group) => {
        const transactions = group.rows.filter((row) => row.kind === "transaction");
        const invoices = group.rows.filter((row) => row.kind === "invoice");
        const metrics = group.rows.filter((row) => row.kind === "metric");
        return <section key={group.id} className={base.evidenceGroup}>
          <div className={base.inlineHeading}><h3>{group.title}</h3><Confidence value={group.confidence} /></div>
          <p>{group.period} · {group.rows.length} registros mostrados de {group.total_count}. {group.explanation}</p>
          {transactions.length > 0 && <div className={base.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: movimientos`}><table><caption>Movimientos observados · EUR · una salida es negativa, una entrada positiva</caption><thead><tr><th scope="col">Registro / fecha</th><th scope="col">Sociedad observada</th><th scope="col">Contraparte</th><th scope="col">Concepto</th><th scope="col" className={base.numeric}>Importe</th></tr></thead><tbody>{transactions.map((row) => <tr key={row.id}><td><span className={base.mono}>{row.id}</span><small>{dateLabel(row.transaction_date)}</small></td><td>{row.company_id}</td><td>{row.counterparty_company_id ?? "No identificada"}</td><td>{row.category}<small>{row.description}</small></td><td className={base.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
          {invoices.length > 0 && <div className={base.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: facturas`}><table><caption>Facturas comerciales entre sociedades · EUR</caption><thead><tr><th scope="col">Factura / sociedades</th><th scope="col">Emisión</th><th scope="col">Vencimiento</th><th scope="col">Pago</th><th scope="col" className={base.numeric}>Importe</th></tr></thead><tbody>{invoices.map((row) => <tr key={row.id}><td><span className={base.mono}>{row.invoice}</span><small>Emisora: {row.issuer_company_id}</small><small>Cliente: {row.customer_company_id}</small></td><td>{dateLabel(row.issue_date)}</td><td>{dateLabel(row.due_date)}</td><td>{row.payment_date ? dateLabel(row.payment_date) : "No observado"}</td><td className={base.numeric}>{exactMoney(row.amount)}</td></tr>)}</tbody></table></div>}
          {metrics.length > 0 && <div className={base.tableScroll} tabIndex={0} role="region" aria-label={`${group.title}: indicadores`}><table><caption>Indicadores suministrados por sociedad; no recalculados en el frontend</caption><thead><tr><th scope="col">Sociedad</th><th scope="col">Indicador / periodo</th><th scope="col">Fuente</th><th scope="col" className={base.numeric}>Valor</th></tr></thead><tbody>{metrics.map((row) => <tr key={row.id}><td>{row.company_id}</td><td>{row.metric}<small>{row.period}</small></td><td>{row.source}</td><td className={base.numeric}>{row.value === null ? "No disponible" : row.unit === "EUR" ? exactMoney(row.value) : `${numberLabel(row.value)} ${row.unit === "days" ? "días" : row.unit === "score" ? "puntos" : "%"}`}</td></tr>)}</tbody></table></div>}
          {!group.rows.length && <p className={base.emptyState}>No se han suministrado registros representativos.</p>}
        </section>;
      })}
      <p className={styles.guardrail}>La evidencia no autoriza movimientos de fondos ni demuestra que la liquidez sea fungible entre sociedades.</p>
    </div>
  </dialog>;
}
