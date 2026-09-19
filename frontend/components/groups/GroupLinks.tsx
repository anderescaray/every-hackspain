import { AnalysisLink as Link } from "@/components/navigation/AnalysisLink";
import { relationHref } from "@/lib/groupPresentation";
import type { GroupDetail } from "@/types/groupDetail";
import styles from "./groups.module.css";

export function GroupLinks({ group, companies, relations }: { group: GroupDetail; companies: string[]; relations: string[] }) {
  return <div className={styles.contextLinks}>
    {companies.map((id) => <Link key={id} href={`/companies/${id}`}>Ver {id} <span aria-hidden="true">↗</span></Link>)}
    {relations.map((id) => { const relation = group.relations.find((item) => item.id === id); return relation ? <Link key={id} href={relationHref(group.group_id, id)}>Ver relación {relation.from_company_id ?? "sin origen"} → {relation.to_company_id ?? "sin destino"}</Link> : null; })}
  </div>;
}
