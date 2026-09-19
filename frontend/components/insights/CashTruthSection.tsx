import Link from "next/link";
import type { CashTruth } from "@/types/companyDetail";
import { exactMoney, money } from "@/lib/companyFormat";
import { Confidence, EvidenceButton, SectionHeading, type OpenEvidence } from "./InsightPrimitives";
import styles from "./insights.module.css";

export function CashTruthSection({ cash, companyId, onOpen }: { cash: CashTruth; companyId: string; onOpen: OpenEvidence }) {
  const comparison = cash.comparison;
  const correction = cash.correction;
  const operating = cash.components.find((item) => item.category === "operating");
  const support = cash.components.find((item) => item.category === "support");
  const circulation = cash.components.find((item) => item.category === "circulation");

  return (
    <section className={`${styles.panel} ${styles.featurePanel}`} aria-label="Cash Truth">
      <SectionHeading number="03" title="Cash Truth" description="Is this cash generated, circulating, or coming from support?"><span className={styles.featureBadge}>Behind the balance</span></SectionHeading>
      {correction && <div className={styles.correction}>
        <div className={styles.correctionBefore}><span className={styles.eyebrow}>Before separating circulation</span><span>Apparent operating cash</span><strong title={exactMoney(correction.apparent_operating)}>{money(correction.apparent_operating)}</strong><small>Classification can create false weakness</small></div>
        <div className={styles.correctionAfter}><span className={styles.eyebrow}>After separating circulation</span><span>Identified operating cash</span><strong title={exactMoney(correction.identified_operating)}>{money(correction.identified_operating, true)}</strong><small>Correction, not new cash generation</small></div>
        <div className={styles.correctionSupport}><span className={styles.eyebrow}>The remaining dependency</span><span>Observed liquidity support</span><strong title={exactMoney(correction.observed_support)}>{money(correction.observed_support, true)}</strong><small>Support is not operating performance</small></div>
      </div>}
      <div className={styles.cashLayout}>
        <div>
          <div className={styles.cashTotal}><div><span className={styles.eyebrow}>Cash movement total · gross</span><strong title={exactMoney(cash.total_gross_movement)}>{money(cash.total_gross_movement)}</strong></div><span className={styles.smallText}>{cash.period}</span></div>
          <div className={styles.cashRows}>{cash.components.map((component) => <div className={styles.cashRow} key={component.category}>
            <span className={`${styles.cashMarker} ${styles[component.category]}`} aria-hidden="true" />
            <div className={styles.cashLabel}><span className={`${styles.category} ${styles[component.category]}`}>{component.category}</span><h3>{component.label}</h3><p>{component.explanation}</p><div className={styles.evidenceMeta}><Confidence value={component.confidence} /><EvidenceButton refs={component.evidence_refs} title={component.label} onOpen={onOpen} /></div></div>
            <div className={styles.cashAmount}><strong title={exactMoney(component.category === "circulation" || component.net_amount === null ? component.gross_movement : component.net_amount)}>{component.category === "circulation" || component.net_amount === null ? money(component.gross_movement) : money(component.net_amount, true)}</strong><span>{component.category === "circulation" || component.net_amount === null ? "gross movement" : "identified net"}</span><small>{component.net_amount === null ? "Net not identified" : component.category === "circulation" ? `${money(component.net_amount)} identified net` : `Gross ${money(component.gross_movement)}`}</small></div>
          </div>)}</div>
          <p className={styles.smallText}>Gross = sum of absolute movements, including both treasury legs. Net = inflows minus outflows. Headline amounts use the labelled basis and must not be added together. Uncertain is not assumed to be operating.</p>
        </div>
        <aside className={styles.cashInterpretation}>
          <span className={styles.eyebrow}>What this tells us</span><h3>{cash.headline}</h3><p>{cash.explanation}</p>
          <div className={styles.interpretationEvidence}><Confidence value={cash.confidence} /><ul>{cash.evidence_summary.map((item) => <li key={item}>{item}</li>)}</ul><EvidenceButton refs={cash.evidence_refs} title="Cash Truth explanation" onOpen={onOpen} /></div>
          {correction && <details className={styles.methodology}><summary>How the correction is read</summary><p>{correction.explanation}</p></details>}
        </aside>
      </div>
      {comparison && <div className={styles.comparison}>
        <div className={styles.inlineHeading}><div><span className={styles.eyebrow}>A useful comparison</span><h3>Same apparent cash position. Different financial reality.</h3></div><Link className={styles.evidenceButton} href={`/companies/${comparison.company_id}`}>Explore {comparison.company_id} <span aria-hidden="true">↗</span></Link></div>
        <div className={styles.tableScroll} tabIndex={0} role="region" aria-label="Cash source comparison"><table><caption>{cash.period} · supplied mock observations, not a complete reconciliation</caption><thead><tr><th scope="col">Company</th><th scope="col" className={styles.numeric}>Apparent net</th><th scope="col" className={styles.numeric}>Operating net</th><th scope="col" className={styles.numeric}>Support net</th><th scope="col" className={styles.numeric}>Circulation gross</th></tr></thead><tbody>
          <tr><th scope="row">{companyId} <small>Current company</small></th><td className={styles.numeric}>{money(cash.apparent_net, true)}</td><td className={styles.numeric}>{operating?.net_amount != null ? money(operating.net_amount, true) : "Not identified"}</td><td className={styles.numeric}>{support?.net_amount != null ? money(support.net_amount, true) : "Not identified"}</td><td className={styles.numeric}>{circulation ? money(circulation.gross_movement) : "Not identified"}</td></tr>
          <tr><th scope="row">{comparison.company_id}</th><td className={styles.numeric}>{money(comparison.apparent_net, true)}</td><td className={styles.numeric}>{money(comparison.operating_net, true)}</td><td className={styles.numeric}>{money(comparison.support_net, true)}</td><td className={styles.numeric}>{money(comparison.circulation_gross)}</td></tr>
        </tbody></table></div><p className={styles.smallText}>{comparison.explanation} Unclassified movement is excluded from identified net attribution.</p>
      </div>}
    </section>
  );
}
