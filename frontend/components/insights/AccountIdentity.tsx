import type { CashAccount } from "@/types/companyDetail";
import { accountOwnershipLabels } from "@/lib/accountPresentation";
import styles from "./insights.module.css";

export function AccountIdentity({ account, accountId }: { account?: CashAccount; accountId?: string | null }) {
  return <div className={styles.accountIdentity}>
    <span className={styles.accountOwnership}>{account ? accountOwnershipLabels[account.ownership] : "Titularidad no confirmada"}</span>
    <strong>{account?.label ?? "Cuenta no identificada"}</strong>
    {(account?.account_id || accountId) && <span className={styles.mono}>{account?.account_id ?? accountId}</span>}
    <span>{account?.bank_name ?? "Banco no identificado"}{account ? ` · ${account.currency}` : ""}</span>
    <span>Titular: <b>{account?.owner_company_id ?? "No identificado"}</b></span>
    {account?.owner_group_id && <small>Grupo: {account.owner_group_id}</small>}
  </div>;
}
