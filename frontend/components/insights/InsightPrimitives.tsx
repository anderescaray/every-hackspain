import type { EvidenceRef } from "@/types/companyDetail";
import styles from "./insights.module.css";

export type OpenEvidence = (refs: EvidenceRef[], title: string) => void;

export function EvidenceButton({ refs, title, onOpen }: { refs: EvidenceRef[]; title: string; onOpen: OpenEvidence }) {
  if (!refs.length) return <span className={styles.unavailable}>Not identifiable with sufficient confidence.</span>;
  return <button type="button" className={styles.evidenceButton} onClick={() => onOpen(refs, title)} aria-label={`View evidence: ${title}`}>View evidence <span aria-hidden="true">↗</span></button>;
}

export function Confidence({ value }: { value: number | null }) {
  return <span className={styles.confidence}>{value === null ? "Confidence unavailable" : `${value}% confidence`}</span>;
}

export function SectionHeading({ number, title, description, children }: { number: string; title: string; description: string; children?: React.ReactNode }) {
  return <div className={styles.sectionHeading}><div><div className={styles.sectionTitle}><span className={styles.sectionNumber}>{number}</span><h2>{title}</h2></div><p>{description}</p></div>{children}</div>;
}
