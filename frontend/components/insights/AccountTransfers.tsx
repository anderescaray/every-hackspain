"use client";

import { useState } from "react";
import type { AccountFlows, AccountTransfer } from "@/types/companyDetail";
import { cashCategoryLabel, dateLabel, exactMoney, money } from "@/lib/companyFormat";
import { transferEvidenceRecords, transferEvidenceRefs, transferKindLabels, transferMatchLabels } from "@/lib/accountPresentation";
import { AccountIdentity } from "./AccountIdentity";
import { Confidence, EvidenceButton, type OpenEvidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function AccountTransfers({ data, companyId, groupId, onOpen }: { data?: AccountFlows | null; companyId: string; groupId: string | null; onOpen: OpenEvidence }) {
  const [filter, setFilter] = useState<AccountTransfer["kind"] | "all">("all");
  const transfers = data?.transfers.filter((transfer) => filter === "all" || transfer.kind === filter) ?? [];

  return <section className={styles.accountSection} aria-label="Cuentas y transferencias">
    <div className={styles.inlineHeading}><h3>Cuentas y transferencias</h3>{data && <span className={styles.periodBadge}>{data.period}</span>}</div>
    <p className={styles.accountIntro}>Mover dinero entre cuentas propias no es generarlo. Lo que cambia la lectura es quién es el titular de cada cuenta.</p>
    {!data ? <p className={styles.emptyState}>Detalle por cuentas todavía no disponible.</p> : <>
      <details className={styles.accountDirectory}>
        <summary>Ver cuentas y titularidad · {data.accounts.length} cuentas documentadas</summary>
        <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Registro de cuentas y titularidad"><table><caption>Cuentas incluidas en las muestras; no se muestran saldos ni se presume cobertura completa.</caption><thead><tr><th scope="col">Cuenta, banco y titular</th><th scope="col">Fuente de titularidad</th><th scope="col">Cobertura</th></tr></thead><tbody>{data.accounts.map((account) => <tr key={account.account_id}><td><AccountIdentity account={account} /></td><td>{account.ownership_source ?? "No identificable con suficiente confianza."}</td><td><Confidence value={account.confidence} /></td></tr>)}</tbody></table></div>
        {!data.accounts.length && <p className={styles.emptyState}>No se han suministrado cuentas identificadas.</p>}
      </details>
      <div className={styles.accountFilters} role="group" aria-label="Filtrar transferencias por titularidad">
        <button aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Todas</button>
        {Object.entries(transferKindLabels).map(([kind, label]) => <button key={kind} aria-pressed={filter === kind} onClick={() => setFilter(kind as AccountTransfer["kind"])}>{label}</button>)}
      </div>
      <p className={styles.smallText} role="status">{transfers.length} {transfers.length === 1 ? "muestra" : "muestras"} · ya incluidas en los importes anteriores.</p>
      <div className={styles.accountTransferList}>{transfers.map((transfer) => <article className={styles.accountTransfer} key={transfer.id} aria-label={transferKindLabels[transfer.kind]}>
        <div className={styles.inlineHeading}><h4>{transferKindLabels[transfer.kind]}</h4><span className={styles.smallText}>{dateLabel(transfer.date)}</span></div>
        <div className={styles.accountRoute}>
          <div><span className={styles.eyebrow}>Origen</span><AccountIdentity account={data.accounts.find((account) => account.account_id === transfer.from_account_id)} /></div>
          <span className={styles.transferArrow} aria-hidden="true">→</span>
          <div><span className={styles.eyebrow}>Destino</span><AccountIdentity account={data.accounts.find((account) => account.account_id === transfer.to_account_id)} /></div>
        </div>
        <dl className={styles.transferAmounts}>
          <div><dt>Importe trasladado</dt><dd title={exactMoney(transfer.amount)}>{money(transfer.amount)}</dd></div>
          <div><dt>Bruto en {companyId}</dt><dd title={exactMoney(transfer.gross_movement)}>{money(transfer.gross_movement)}</dd></div>
          <div><dt>Neto identificado en {companyId}</dt><dd title={transfer.company_net_amount === null ? undefined : exactMoney(transfer.company_net_amount)}>{transfer.company_net_amount === null ? "No identificado" : money(transfer.company_net_amount, true)}</dd></div>
        </dl>
        <p className={styles.transferExplanation}>{transfer.explanation}</p>
        <div className={styles.transferEvidence}>
          <span className={`${styles.category} ${styles[transfer.category]}`}>{cashCategoryLabel(transfer.category, transfer.kind === "external_transfer" ? null : groupId)}</span>
          <span className={styles.matchStatus}>{transferMatchLabels[transfer.match_status]}</span>
          <Confidence value={transfer.confidence} />
          <EvidenceButton records={transferEvidenceRecords(transfer)} refs={transferEvidenceRefs(transfer)} title={`Transferencia: ${transferKindLabels[transfer.kind]}`} onOpen={onOpen} />
        </div>
        {transfer.kind === "own_transfer" && transfer.match_status !== "matched" && <p className={styles.disclaimer}>Falta completar el emparejamiento. No se afirma neto cero ni generación operativa.</p>}
      </article>)}</div>
      {!transfers.length && <p className={styles.emptyState}>No hay muestras suministradas para este filtro. No significa que no existan movimientos de este tipo.</p>}
      <details className={styles.methodology}><summary>Sobre estas muestras</summary><p>{data.explanation}</p><p>La titularidad, el emparejamiento y la clasificación los suministra el equipo de datos. Coincidir en importe, banco o fecha no demuestra por sí solo un traslado propio. El neto se refiere a la empresa, no al grupo consolidado ni al saldo disponible de una cuenta.</p></details>
    </>}
  </section>;
}
