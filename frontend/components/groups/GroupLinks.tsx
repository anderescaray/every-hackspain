import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import styles from "./groups.module.css";

/** Enlaces de contexto de una revisión. Las relaciones ya no enlazan: la vista de grafo se retiró. */
export function GroupLinks({ companies }: { companies: string[] }) {
  return <div className={styles.contextLinks}>
    {companies.map((id) => <Link key={id} href={`/companies/${id}`}>Ver {id} <span aria-hidden="true">↗</span></Link>)}
  </div>;
}
