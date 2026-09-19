import Link from "next/link";
import type { CashTruth } from "@/types/companyDetail";
import { cashCategoryLabel, exactMoney, money } from "@/lib/companyFormat";
import { getIdentifiedCashTotal, getSupportPresentation, getTreasuryState } from "@/lib/cashPresentation";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import { AccountTransfers } from "./AccountTransfers";
import styles from "./insights.module.css";

const treasuryBadges = { none: "Sin movimientos", pending: "Pendiente de emparejar", unavailable: "Datos insuficientes", identified: "No es caja nueva" } as const;

export function CashTruthSection({ cash, companyId, groupId, onOpen }: { cash: CashTruth; companyId: string; groupId: string | null; onOpen: OpenEvidence }) {
  const comparison = cash.comparison;
  const operating = cash.components.find((item) => item.category === "operating");
  const supportView = getSupportPresentation(cash, groupId);
  const support = supportView.component;
  const visibleComponents = cash.components.filter((item) => item.category !== "support" || supportView.visible);
  const circulation = cash.components.find((item) => item.category === "circulation");
  const uncertain = cash.components.find((item) => item.category === "uncertain");
  const treasury = cash.own_account_circulation;
  const treasuryState = getTreasuryState(cash);
  const identifiedCash = getIdentifiedCashTotal(cash);

  return (
    <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Origen de la caja">
      <SectionHeading number="03" title="Origen de la caja" description="¿De dónde viene realmente la liquidez?"><span className={styles.featureBadge}>{cash.period}</span></SectionHeading>
      <aside className={styles.cashConclusion} aria-label="Conclusión del origen de la caja">
        <span className={styles.eyebrow}>Conclusión</span>
        <h3>{cash.headline}</h3>
        <p>{cash.explanation}</p>
        <div className={styles.cashConclusionMeta}><Confidence value={cash.confidence} /><EvidenceButton refs={cash.evidence_refs} title="Origen de la caja" onOpen={onOpen} /></div>
      </aside>
      <div className={styles.identifiedCashTotal} role="group" aria-label="Total de caja neta identificada">
        <div className={styles.identifiedCashMain}>
          <h3>Total de caja neta identificada</h3>
          <strong data-testid="identified-cash-total">{identifiedCash.total === null ? "No disponible" : exactMoney(identifiedCash.total)}</strong>
        </div>
        <span className={styles.cashSumOperator} aria-hidden="true">=</span>
        <div className={styles.cashSumTerm}>
          <span>Generación operativa</span>
          <strong data-testid="cash-total-operating">{identifiedCash.operating === null ? "No identificado" : exactMoney(identifiedCash.operating)}</strong>
        </div>
        <span className={styles.cashSumOperator} aria-hidden="true">{identifiedCash.support !== null && identifiedCash.support < 0 ? "−" : "+"}</span>
        <div className={styles.cashSumTerm}>
          <span>{supportView.visible ? supportView.label : identifiedCash.support === 0 ? "Sin apoyo identificado" : "Financiación o apoyo sin dato"}</span>
          <strong data-testid="cash-total-support">{identifiedCash.support === null ? "No identificado" : exactMoney(Math.abs(identifiedCash.support))}</strong>
          {identifiedCash.support !== null && identifiedCash.support < 0 && <small>Salida neta: resta del total</small>}
        </div>
      </div>
      <p className={styles.cashTotalDefinition}>Lo generado por la actividad más el apoyo recibido. No es el saldo bancario disponible.</p>
      {identifiedCash.total === null && <p className={styles.disclaimer} role="status">No se puede completar el total: falta un neto identificado. No se sustituye por cero.</p>}
      <div className={styles.cashOrigins} role="group" aria-label="Origen de la liquidez">
        <article className={styles.operatingOrigin} aria-label="Generación operativa">
          <h3>Generación operativa</h3>
          <strong title={operating?.net_amount == null ? undefined : exactMoney(operating.net_amount)}>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</strong>
          <p>Cobros menos pagos de la actividad.</p>
          <EvidenceButton refs={operating?.evidence_refs ?? []} title="Generación operativa" onOpen={onOpen} />
        </article>
        {supportView.visible && <article className={styles.supportOrigin} aria-label={supportView.label}>
          <h3>{supportView.label}</h3>
          <strong title={support?.net_amount == null ? undefined : exactMoney(support.net_amount)}>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</strong>
          <p>{supportView.description}</p>
          <EvidenceButton refs={support?.evidence_refs ?? []} title={supportView.label} onOpen={onOpen} />
        </article>}
        <article className={styles.unidentifiedOrigin} aria-label={uncertain?.label ?? "No identificado"}>
          <h3>{uncertain?.label ?? "No identificado"}</h3>
          <strong title={uncertain ? exactMoney(uncertain.gross_movement) : undefined}>{uncertain ? money(uncertain.gross_movement) : "No disponible"}</strong>
          <p>Volumen bruto sin clasificar. No entra en el total.</p>
          {uncertain?.evidence_refs.length ? <EvidenceButton refs={uncertain.evidence_refs} title="Movimientos no identificados" onOpen={onOpen} /> : <Confidence value={uncertain?.confidence ?? null} />}
        </article>
      </div>
      {supportView.unavailable && <p className={styles.smallText}>Sin datos suficientes sobre financiación o apoyo: no se confirma que no exista.</p>}
      <details className={styles.cashBreakdown}>
        <summary>Ver desglose y movimientos brutos</summary>
        <div className={styles.cashTotal}><div><span className={styles.eyebrow}>Volumen total movido · bruto</span><strong title={exactMoney(cash.total_gross_movement)}>{money(cash.total_gross_movement)}</strong></div></div>
        <p className={styles.smallText}>Entradas y salidas sumadas, incluidos los traslados entre cuentas. No es dinero disponible.</p>
        <div className={styles.cashRows}>{visibleComponents.map((component) => <div className={styles.cashRow} key={component.category}>
          <span className={`${styles.cashMarker} ${styles[component.category]}`} aria-hidden="true" />
          <div className={styles.cashLabel}><span className={`${styles.category} ${styles[component.category]}`}>{cashCategoryLabel(component.category, groupId)}</span><h3>{component.category === "support" ? supportView.label : component.label}</h3><p>{component.explanation}</p><div className={styles.evidenceMeta}><Confidence value={component.confidence} /><EvidenceButton refs={component.evidence_refs} title={component.category === "support" ? supportView.label : component.label} onOpen={onOpen} /></div></div>
          <div className={styles.cashAmount}><strong>{component.net_amount === null ? "No identificado" : money(component.net_amount, true)}</strong><span>neto identificado</span><small title={exactMoney(component.gross_movement)}>Bruto: {money(component.gross_movement)}</small></div>
        </div>)}</div>
        <p className={styles.smallText}>Bruto: entradas más salidas. Neto: entradas menos salidas. No se suman entre sí.</p>
        <ul className={styles.cashEvidenceCounts}>{cash.evidence_summary.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
      <section className={styles.treasurySection} aria-label="Movimientos de tesorería">
        <div className={styles.treasuryHeading}><h3>Movimientos de tesorería</h3><span className={styles.periodBadge}>{treasuryBadges[treasuryState]}</span></div>
        {treasuryState === "identified" && treasury ? <div className={styles.treasuryCard}>
          <div className={styles.treasuryValue}>
            <span className={styles.treasuryIcon} aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 8h14m-4-4 4 4-4 4M20 16H6m4-4-4 4 4 4" /></svg></span>
            <div><strong title={exactMoney(treasury.transferred_amount)}>{money(treasury.transferred_amount, false, 1)}</strong><span>transferidos</span></div>
          </div>
          <div className={styles.treasuryText}>
            <h4>Circulación entre cuentas propias</h4>
            <p>Dinero que pasa de una cuenta de la empresa a otra: cambia dónde está, no cuánto hay.</p>
            <div className={styles.treasuryMeta}><span>{treasury.transfer_count} {treasury.transfer_count === 1 ? "traslado identificado" : "traslados identificados"}</span><Confidence value={treasury.confidence} /><EvidenceButton refs={treasury.evidence_refs} title="Movimientos de tesorería" onOpen={onOpen} /></div>
          </div>
        </div> : <div className={styles.treasuryStatus} role="status">
          {treasuryState === "none" ? <>
            <h4>No se han detectado movimientos entre cuentas propias</h4>
            <p>Sin traslados identificados entre cuentas de la empresa en este periodo.</p>
            <Confidence value={treasury?.confidence ?? null} />
          </> : treasuryState === "pending" ? <>
            <h4>Hay movimientos pendientes de emparejar</h4>
            <p>Aún no hay traslados confirmados: no se puede afirmar que no existan ni que su neto sea cero.</p>
          </> : <>
            <div className={styles.treasuryStatusHead}><h4>No hay datos suficientes sobre los traslados</h4><span className={styles.statusPill}>No disponible</span></div>
            <p>La falta de información no significa que no haya movimientos entre cuentas.</p>
            <p className={styles.smallText}>No se deduce este importe de la circulación bruta ni de muestras sueltas.</p>
          </>}
        </div>}
        {treasuryState === "identified" && <details className={styles.methodology}><summary>Cómo se identifica este importe</summary><p>{treasury?.explanation}</p><p>Cada traslado se cuenta una sola vez. No se suma a la generación operativa ni al apoyo y no es un saldo disponible.</p></details>}
        {treasuryState !== "none" && <details className={styles.accountDisclosure}><summary>Ver cuentas y transferencias</summary><AccountTransfers data={cash.account_flows} companyId={companyId} groupId={groupId} onOpen={onOpen} /></details>}
      </section>
      {comparison && <div className={styles.comparison}>
        <div className={styles.inlineHeading}><div><span className={styles.eyebrow}>Comparación</span><h3>Misma posición aparente de caja. Distinta realidad financiera.</h3></div><Link className={styles.evidenceButton} href={`/companies/${comparison.company_id}`}>Explorar {comparison.company_id} <span aria-hidden="true">↗</span></Link></div>
        <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Comparación del origen de la caja"><table><caption>{cash.period}</caption><thead><tr><th scope="col">Empresa</th><th scope="col" className={styles.numeric}>Neto aparente</th><th scope="col" className={styles.numeric}>Neto operativo</th><th scope="col" className={styles.numeric}>Apoyo neto</th><th scope="col" className={styles.numeric}>Circulación bruta</th></tr></thead><tbody>
          <tr><th scope="row">{companyId} <small>Empresa actual</small></th><td className={styles.numeric}>{cash.apparent_net === null ? "No identificado" : money(cash.apparent_net, true)}</td><td className={styles.numeric}>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{circulation ? money(circulation.gross_movement) : "No identificado"}</td></tr>
          <tr><th scope="row">{comparison.company_id}</th><td className={styles.numeric}>{money(comparison.apparent_net, true)}</td><td className={styles.numeric}>{money(comparison.operating_net, true)}</td><td className={styles.numeric}>{money(comparison.support_net, true)}</td><td className={styles.numeric}>{money(comparison.circulation_gross)}</td></tr>
        </tbody></table></div><p className={styles.smallText}>{comparison.explanation}</p>
      </div>}
    </section>
  );
}
