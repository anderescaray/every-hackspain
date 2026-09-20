import { notFound } from "next/navigation";
import { CompanyInsights } from "@/components/insights/CompanyInsights";
import { CompanyDataState } from "@/components/insights/CompanyDataState";
import { AnalysisShell } from "@/components/navigation/AnalysisShell";
import { CompanyDataError, getCompanyDetail } from "@/services/companyData";
import { hasSimulator } from "@/lib/analysisNavigation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^COMP_\d{4,10}$/.test(id)) notFound();
  let company;
  let invalid = false;
  try {
    company = await getCompanyDetail(id);
  } catch (error) {
    if (!(error instanceof CompanyDataError)) throw error;
    invalid = true;
  }
  return <AnalysisShell companyId={id} groupId={company?.group_id} view="company" simulator={hasSimulator(company?.simulation)}>
    {company ? <CompanyInsights key={company.company_id} company={company} /> : <CompanyDataState companyId={id} invalid={invalid} />}
  </AnalysisShell>;
}
