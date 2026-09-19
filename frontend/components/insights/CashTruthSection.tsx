import Link from "next/link";
import type { CashTruth } from "@/types/companyDetail";
import { cashCategoryLabels, exactMoney, money } from "@/lib/companyFormat";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function CashTruthSection({ cash, companyId, onOpen }: { cash: CashTruth; companyId: string; onOpen: OpenEvidence }) {
  const comparison = cash.comparison;
  const correction = cash.correction;
  const operating = cash.components.find((item) => item.category === "operating");
  const support = cash.components.find((item) => item.category === "support");
  const circulation = cash.components.find((item) => item.category === "circulation");

  return (
    <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Origen de la caja">
      <SectionHeading number="03" title="Origen de la caja" description="¿De dónde viene realmente la liquidez?"><span className={styles.featureBadge}>Más allá del saldo</span></SectionHeading>
      {correction && <div className={styles.correction}>
        <div className={styles.correctionBefore}><span className={styles.eyebrow}>Antes de separar la circulación</span><span>Caja operativa aparente</span><strong title={exactMoney(correction.apparent_operating)}>{money(correction.apparent_operating)}</strong><small>La clasificación puede mostrar una falsa debilidad</small></div>
        <div className={styles.correctionAfter}><span className={styles.eyebrow}>Después de separar la circulación</span><span>Caja operativa identificada</span><strong title={exactMoney(correction.identified_operating)}>{money(correction.identified_operating, true)}</strong><small>Una corrección, no nueva generación de caja</small></div>
        <div className={styles.correctionSupport}><span className={styles.eyebrow}>La dependencia que permanece</span><span>Apoyo de liquidez observado</span><strong title={exactMoney(correction.observed_support)}>{money(correction.observed_support, true)}</strong><small>El apoyo no es rendimiento operativo</small></div>
      </div>}
      <div className={styles.cashLayout}>
        <div>
          <div className={styles.cashTotal}><div><span className={styles.eyebrow}>Movimiento total de caja · bruto</span><strong title={exactMoney(cash.total_gross_movement)}>{money(cash.total_gross_movement)}</strong></div><span className={styles.smallText}>{cash.period}</span></div>
          <div className={styles.cashRows}>{cash.components.map((component) => <div className={styles.cashRow} key={component.category}>
            <span className={`${styles.cashMarker} ${styles[component.category]}`} aria-hidden="true" />
            <div className={styles.cashLabel}><span className={`${styles.category} ${styles[component.category]}`}>{cashCategoryLabels[component.category]}</span><h3>{component.label}</h3><p>{component.explanation}</p><div className={styles.evidenceMeta}><Confidence value={component.confidence} /><EvidenceButton refs={component.evidence_refs} title={component.label} onOpen={onOpen} /></div></div>
            <div className={styles.cashAmount}><strong title={exactMoney(component.category === "circulation" || component.net_amount === null ? component.gross_movement : component.net_amount)}>{component.category === "circulation" || component.net_amount === null ? money(component.gross_movement) : money(component.net_amount, true)}</strong><span>{component.category === "circulation" || component.net_amount === null ? "movimiento bruto" : "neto identificado"}</span><small>{component.net_amount === null ? "Neto no identificado" : component.category === "circulation" ? `${money(component.net_amount)} de neto identificado` : `Bruto: ${money(component.gross_movement)}`}</small></div>
          </div>)}</div>
          <p className={styles.smallText}>Bruto: suma de movimientos en valor absoluto, contando entrada y salida de tesorería. Neto: entradas menos salidas. Los importes principales usan la base indicada y no deben sumarse entre sí. Lo no identificado no se considera operativo.</p>
        </div>
        <aside className={styles.cashInterpretation}>
          <span className={styles.eyebrow}>Qué nos dice la caja</span><h3>{cash.headline}</h3><p>{cash.explanation}</p>
          <div className={styles.interpretationEvidence}><Confidence value={cash.confidence} /><ul>{cash.evidence_summary.map((item) => <li key={item}>{item}</li>)}</ul><EvidenceButton refs={cash.evidence_refs} title="Origen de la caja" onOpen={onOpen} /></div>
          {correction && <details className={styles.methodology}><summary>Cómo interpretar la corrección</summary><p>{correction.explanation}</p></details>}
        </aside>
      </div>
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
