import Link from "next/link";
import type { CashTruth } from "@/types/companyDetail";
import { cashCategoryLabel, exactMoney, money } from "@/lib/companyFormat";
import { getIdentifiedCashTotal, getSupportPresentation, getTreasuryState } from "@/lib/cashPresentation";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import { AccountTransfers } from "./AccountTransfers";
import styles from "./insights.module.css";

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
      <div className={styles.identifiedCashTotal} role="group" aria-label="Total de caja neta identificada">
        <div className={styles.identifiedCashMain}>
          <h3>Total de caja neta identificada</h3>
          <strong data-testid="identified-cash-total">{identifiedCash.total === null ? "No disponible" : exactMoney(identifiedCash.total)}</strong>
          <span>Flujos netos del periodo</span>
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
      <p className={styles.cashTotalDefinition}><strong>Es la suma de la generación operativa y el apoyo o financiación identificados.</strong> No es el saldo bancario disponible. Excluye la circulación entre cuentas y los movimientos no identificados.</p>
      {identifiedCash.total === null && <p className={styles.disclaimer} role="status">No se puede completar el total: falta un neto identificado o su importe no puede representarse con precisión. No se sustituye por cero.</p>}
      <div className={styles.cashOrigins} role="group" aria-label="Origen de la liquidez">
        <article className={styles.operatingOrigin} aria-label="Generación operativa">
          <h3>Generación operativa</h3>
          <strong title={operating?.net_amount == null ? undefined : exactMoney(operating.net_amount)}>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</strong>
          <p>Caja neta identificada generada por la actividad. Cobros operativos menos pagos operativos.</p>
          <small>No es beneficio contable.</small>
          <EvidenceButton refs={operating?.evidence_refs ?? []} title="Generación operativa" onOpen={onOpen} />
        </article>
        {supportView.visible && <article className={styles.supportOrigin} aria-label={supportView.label}>
          <h3>{supportView.label}</h3>
          <strong title={support?.net_amount == null ? undefined : exactMoney(support.net_amount)}>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</strong>
          <p>{supportView.description} No procede de la actividad ordinaria.</p>
          <small>Separada de la generación operativa.</small>
          <EvidenceButton refs={support?.evidence_refs ?? []} title={supportView.label} onOpen={onOpen} />
        </article>}
        <article className={styles.unidentifiedOrigin} aria-label="No identificado">
          <h3>No identificado</h3>
          <strong title={uncertain ? exactMoney(uncertain.gross_movement) : undefined}>{uncertain ? money(uncertain.gross_movement) : "No disponible"}</strong>
          <p>Movimientos cuyo origen no puede determinarse con suficiente confianza.</p>
          <small>Volumen bruto, no generación neta de caja.</small>
          {uncertain?.evidence_refs.length ? <EvidenceButton refs={uncertain.evidence_refs} title="Movimientos no identificados" onOpen={onOpen} /> : <Confidence value={uncertain?.confidence ?? null} />}
        </article>
      </div>
      <p className={styles.cashBasisNote}>Los importes identificados se muestran en neto. Lo no identificado es volumen bruto: no sumes estas cifras como si fueran caja generada.</p>
      {supportView.unavailable && <p className={styles.smallText}>No hay información suficiente sobre financiación o apoyo. Su ausencia en el resumen no confirma que no exista.</p>}
      <aside className={styles.cashReading}>
        <div><h3>{cash.headline}</h3><p>{cash.explanation}</p></div>
        <div className={styles.cashReadingEvidence}><Confidence value={cash.confidence} /><EvidenceButton refs={cash.evidence_refs} title="Origen de la caja" onOpen={onOpen} /></div>
      </aside>
      <details className={styles.cashBreakdown}>
        <summary>Ver desglose y movimientos brutos</summary>
        <div className={styles.cashTotal}><div><span className={styles.eyebrow}>Volumen total movido · bruto</span><strong title={exactMoney(cash.total_gross_movement)}>{money(cash.total_gross_movement)}</strong></div></div>
        <p className={styles.smallText}>No es el dinero disponible. Cuenta entradas y salidas, incluidos los traslados entre cuentas.</p>
        <div className={styles.cashRows}>{visibleComponents.map((component) => <div className={styles.cashRow} key={component.category}>
          <span className={`${styles.cashMarker} ${styles[component.category]}`} aria-hidden="true" />
          <div className={styles.cashLabel}><span className={`${styles.category} ${styles[component.category]}`}>{cashCategoryLabel(component.category, groupId)}</span><h3>{component.category === "support" ? supportView.label : component.label}</h3><p>{component.explanation}</p><div className={styles.evidenceMeta}><Confidence value={component.confidence} /><EvidenceButton refs={component.evidence_refs} title={component.category === "support" ? supportView.label : component.label} onOpen={onOpen} /></div></div>
          <div className={styles.cashAmount}><strong>{component.net_amount === null ? "No identificado" : money(component.net_amount, true)}</strong><span>neto identificado</span><small title={exactMoney(component.gross_movement)}>Bruto: {money(component.gross_movement)}</small></div>
        </div>)}</div>
        <p className={styles.smallText}>Bruto: entradas y salidas en valor absoluto. Neto: entradas menos salidas. No sumar bruto y neto. Los movimientos sin identificar no se consideran cero ni se asignan a la operación.</p>
        <ul className={styles.cashEvidenceCounts}>{cash.evidence_summary.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
      <section className={styles.treasurySection} aria-label="Movimientos de tesorería">
        <div className={styles.treasuryHeading}><h3>Movimientos de tesorería</h3><span className={styles.periodBadge}>{treasuryState === "none" ? "Sin movimientos" : treasuryState === "pending" ? "Pendiente de emparejar" : treasuryState === "unavailable" ? "Datos insuficientes" : "Redistribución, no generación"}</span></div>
        {treasuryState === "none" ? <div className={styles.treasuryStatus} role="status">
          <h4>No se han detectado movimientos entre cuentas propias</h4>
          <p>No hay traslados identificados entre cuentas de la empresa en los datos analizados de este periodo.</p>
          <Confidence value={treasury?.confidence ?? null} />
        </div> : treasuryState === "pending" ? <div className={styles.treasuryStatus} role="status">
          <h4>Hay movimientos pendientes de emparejar</h4>
          <p>No hay traslados confirmados todavía. No se puede concluir que no existan movimientos ni afirmar un neto cero.</p>
        </div> : <>
          <div className={styles.treasurySummary}>
            <div><h4>{treasuryState === "unavailable" ? "No hay datos suficientes sobre los traslados" : "Circulación entre cuentas propias"}</h4><p>{treasuryState === "unavailable" ? "La falta de información no significa que no haya movimientos entre cuentas." : "Movimientos identificados entre cuentas de la propia empresa. Cambian dónde está el dinero, pero no cuánto dinero tiene la empresa en conjunto."}</p></div>
            <div className={styles.treasuryValue}>{treasury ? <><strong title={exactMoney(treasury.transferred_amount)}>{money(treasury.transferred_amount, false, 1)}</strong><span>transferidos</span></> : <><strong>No disponible</strong><span>Importe entre cuentas propias no suministrado</span></>}</div>
          </div>
          {treasury ? <div className={styles.treasuryMeta}><span>{treasury.transfer_count} {treasury.transfer_count === 1 ? "traslado identificado" : "traslados identificados"}</span><Confidence value={treasury.confidence} /><EvidenceButton refs={treasury.evidence_refs} title="Movimientos de tesorería" onOpen={onOpen} /></div> : <p className={styles.smallText}>No se deduce este importe de la circulación bruta ni de unas pocas muestras. Se mostrará cuando el equipo de datos lo identifique.</p>}
        </>}
        {treasuryState === "identified" && <>
          <details className={styles.methodology}><summary>Cómo se identifica este importe</summary><p>{treasury?.explanation}</p></details>
          <p className={styles.treasuryNote}>Cada traslado se cuenta una sola vez. No sumar este importe a la generación operativa ni a la financiación o apoyo recibido. No representa un saldo disponible.</p>
        </>}
        {treasuryState !== "none" && <details className={styles.accountDisclosure}><summary>Ver cuentas y transferencias</summary><AccountTransfers data={cash.account_flows} companyId={companyId} groupId={groupId} onOpen={onOpen} /></details>}
      </section>
      {comparison && <div className={styles.comparison}>
        <div className={styles.inlineHeading}><div><span className={styles.eyebrow}>Una comparación útil</span><h3>Misma posición aparente de caja. Distinta realidad financiera.</h3></div><Link className={styles.evidenceButton} href={`/companies/${comparison.company_id}`}>Explorar {comparison.company_id} <span aria-hidden="true">↗</span></Link></div>
        <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Comparación del origen de la caja"><table><caption>{cash.period} · observaciones suministradas, no una conciliación completa</caption><thead><tr><th scope="col">Empresa</th><th scope="col" className={styles.numeric}>Neto aparente</th><th scope="col" className={styles.numeric}>Neto operativo</th><th scope="col" className={styles.numeric}>Apoyo neto</th><th scope="col" className={styles.numeric}>Circulación bruta</th></tr></thead><tbody>
          <tr><th scope="row">{companyId} <small>Empresa actual</small></th><td className={styles.numeric}>{cash.apparent_net === null ? "No identificado" : money(cash.apparent_net, true)}</td><td className={styles.numeric}>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{circulation ? money(circulation.gross_movement) : "No identificado"}</td></tr>
          <tr><th scope="row">{comparison.company_id}</th><td className={styles.numeric}>{money(comparison.apparent_net, true)}</td><td className={styles.numeric}>{money(comparison.operating_net, true)}</td><td className={styles.numeric}>{money(comparison.support_net, true)}</td><td className={styles.numeric}>{money(comparison.circulation_gross)}</td></tr>
        </tbody></table></div><p className={styles.smallText}>{comparison.explanation} El movimiento no clasificado queda fuera de la atribución del neto identificado.</p>
      </div>}
    </section>
  );
}
