import { mockCompanies } from "../data/mockCompanies";
import type { CompanyDetail } from "../types/companyDetail";

export async function getCompanyDetail(companyId: string): Promise<CompanyDetail | null> {
  if (!Object.hasOwn(mockCompanies, companyId)) return null;
  return structuredClone(mockCompanies[companyId]);
}
