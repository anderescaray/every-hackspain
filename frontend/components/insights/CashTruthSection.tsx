import Link from "next/link";
import type { CashTruth } from "@/types/companyDetail";
import { cashCategoryLabels, exactMoney, money } from "@/lib/companyFormat";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import { AccountTransfers } from "./AccountTransfers";
import styles from "./insights.module.css";

export function CashTruthSection({ cash, companyId, onOpen }: { cash: CashTruth; companyId: string; onOpen: OpenEvidence }) {
  const comparison = cash.comparison;
  const operating = cash.components.find((item) => item.category === "operating");
  const support = cash.components.find((item) => item.category === "support");
  const circulation = cash.components.find((item) => item.category === "circulation");
  const uncertain = cash.components.find((item) => item.category === "uncertain");

  return (
    <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Origen de la caja">
      <SectionHeading number="03" title="Origen de la caja" description="¿El dinero lo genera el negocio o viene de apoyo?"><span className={styles.featureBadge}>{cash.period}</span></SectionHeading>
      <div className={styles.cashOrigins}>
        <article className={styles.operatingOrigin} aria-label="Lo que genera el negocio">
          <span className={styles.eyebrow}>La actividad de la empresa</span><h3>Lo que genera el negocio</h3>
          <strong>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</strong>
          <p>Neto operativo identificado: cobros de la actividad menos sus pagos. No es beneficio contable.</p>
          <EvidenceButton refs={operating?.evidence_refs ?? []} title="Lo que genera el negocio" onOpen={onOpen} />
        </article>
        <article className={styles.supportOrigin} aria-label="Lo que aporta el grupo">
          <span className={styles.eyebrow}>Apoyo identificado</span><h3>Lo que aporta el grupo</h3>
          <strong>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</strong>
          <p>Aportación neta clasificada como apoyo intragrupo. No es caja generada por vender o prestar servicios.</p>
          <EvidenceButton refs={support?.evidence_refs ?? []} title="Lo que aporta el grupo" onOpen={onOpen} />
        </article>
        <article className={styles.circulationOrigin} aria-label="Lo que solo se mueve">
          <span className={styles.eyebrow}>Circulación de tesorería</span><h3>Lo que solo se mueve</h3>
          <strong>{circulation?.net_amount != null ? money(circulation.net_amount, true) : "No identificado"}</strong>
          <p>{circulation?.net_amount === 0 ? "Neto cero en la circulación identificada. Mover dinero entre cuentas no es generar caja nueva." : "Neto de la circulación identificada, no generación operativa. No se presume que los movimientos se compensen."}</p>
          <EvidenceButton refs={circulation?.evidence_refs ?? []} title="Lo que solo se mueve" onOpen={onOpen} />
        </article>
      </div>
      <div className={styles.cashLayout}>
        <div>
          {uncertain && <div className={styles.uncertainNotice}><h3>Una parte sigue sin identificar</h3><p>{money(uncertain.gross_movement)} de movimientos brutos con origen no suficientemente identificado. {uncertain.net_amount === null ? "No se atribuye un neto ni se considera generación operativa." : `Neto suministrado: ${money(uncertain.net_amount, true)}; finalidad no identificada.`}</p><Confidence value={uncertain.confidence} /></div>}
          <details className={styles.cashBreakdown}>
            <summary>Ver desglose y movimientos brutos</summary>
            <div className={styles.cashTotal}><div><span className={styles.eyebrow}>Volumen total movido · bruto</span><strong title={exactMoney(cash.total_gross_movement)}>{money(cash.total_gross_movement)}</strong></div></div>
            <p className={styles.smallText}>No es el dinero disponible. Cuenta entradas y salidas, incluidos los traslados entre cuentas.</p>
            <div className={styles.cashRows}>{cash.components.map((component) => <div className={styles.cashRow} key={component.category}>
              <span className={`${styles.cashMarker} ${styles[component.category]}`} aria-hidden="true" />
              <div className={styles.cashLabel}><span className={`${styles.category} ${styles[component.category]}`}>{cashCategoryLabels[component.category]}</span><h3>{component.label}</h3><p>{component.explanation}</p><div className={styles.evidenceMeta}><Confidence value={component.confidence} /><EvidenceButton refs={component.evidence_refs} title={component.label} onOpen={onOpen} /></div></div>
              <div className={styles.cashAmount}><strong>{component.net_amount === null ? "No identificado" : money(component.net_amount, true)}</strong><span>neto identificado</span><small title={exactMoney(component.gross_movement)}>Bruto: {money(component.gross_movement)}</small></div>
            </div>)}</div>
            <p className={styles.smallText}>Bruto: entradas y salidas en valor absoluto. Neto: entradas menos salidas. No sumar bruto y neto. Los movimientos sin identificar no se consideran cero ni se asignan a la operación.</p>
          </details>
        </div>
        <aside className={styles.cashInterpretation}>
          <span className={styles.eyebrow}>Qué nos dice el origen</span><h3>{cash.headline}</h3><p>{cash.explanation}</p>
          <div className={styles.interpretationEvidence}><Confidence value={cash.confidence} /><ul>{cash.evidence_summary.map((item) => <li key={item}>{item}</li>)}</ul><EvidenceButton refs={cash.evidence_refs} title="Origen de la caja" onOpen={onOpen} /></div>
        </aside>
      </div>
      <AccountTransfers data={cash.account_flows} companyId={companyId} onOpen={onOpen} />
      {comparison && <div className={styles.comparison}>
        <div className={styles.inlineHeading}><div><span className={styles.eyebrow}>Una comparación útil</span><h3>Misma posición aparente de caja. Distinta realidad financiera.</h3></div><Link className={styles.evidenceButton} href={`/companies/${comparison.company_id}`}>Explorar {comparison.company_id} <span aria-hidden="true">↗</span></Link></div>
        <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Comparación del origen de la caja"><table><caption>{cash.period} · observaciones suministradas, no una conciliación completa</caption><thead><tr><th scope="col">Empresa</th><th scope="col" className={styles.numeric}>Neto aparente</th><th scope="col" className={styles.numeric}>Neto operativo</th><th scope="col" className={styles.numeric}>Apoyo neto</th><th scope="col" className={styles.numeric}>Circulación bruta</th></tr></thead><tbody>
          <tr><th scope="row">{companyId} <small>Empresa actual</small></th><td className={styles.numeric}>{money(cash.apparent_net, true)}</td><td className={styles.numeric}>{operating?.net_amount != null ? money(operating.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{support?.net_amount != null ? money(support.net_amount, true) : "No identificado"}</td><td className={styles.numeric}>{circulation ? money(circulation.gross_movement) : "No identificado"}</td></tr>
          <tr><th scope="row">{comparison.company_id}</th><td className={styles.numeric}>{money(comparison.apparent_net, true)}</td><td className={styles.numeric}>{money(comparison.operating_net, true)}</td><td className={styles.numeric}>{money(comparison.support_net, true)}</td><td className={styles.numeric}>{money(comparison.circulation_gross)}</td></tr>
        </tbody></table></div><p className={styles.smallText}>{comparison.explanation} El movimiento no clasificado queda fuera de la atribución del neto identificado.</p>
      </div>}
    </section>
  );
}
