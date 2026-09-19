import type { EvidenceRef, TransactionEvidenceRef } from "@/types/companyDetail";
import styles from "./insights.module.css";

export type OpenEvidence = (refs: EvidenceRef[], title: string, records?: TransactionEvidenceRef[]) => void;

export function EvidenceButton({ refs, title, records, onOpen }: { refs: EvidenceRef[]; title: string; records?: TransactionEvidenceRef[]; onOpen: OpenEvidence }) {
  if (!refs.length) return <span className={styles.unavailable}>Sin evidencia enlazada</span>;
  return <button type="button" className={styles.evidenceButton} onClick={() => onOpen(refs, title, records)} aria-label={`Ver evidencia: ${title}`}>Ver evidencia <span aria-hidden="true">↗</span></button>;
}

export function Confidence({ value }: { value: number | null }) {
  return <span className={styles.confidence}>{value === null ? "Cobertura no evaluable" : `Cobertura de datos: ${value} %`}</span>;
}

export function SectionHeading({ number, title, description, children }: { number: string; title: string; description?: string; children?: React.ReactNode }) {
  return <div className={styles.sectionHeading}><div><div className={styles.sectionTitle}><span className={styles.sectionNumber}>{number}</span><h2>{title}</h2></div>{description && <p>{description}</p>}</div>{children}</div>;
}
