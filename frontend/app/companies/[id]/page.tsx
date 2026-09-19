import { notFound } from "next/navigation";
import { CompanyInsights } from "@/components/insights/CompanyInsights";
import { CompanyDataState } from "@/components/insights/CompanyDataState";
import { CompanyDataError, getCompanyDetail } from "@/services/companyData";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^COMP_\d{4,10}$/.test(id)) notFound();
  let company;
  try {
    company = await getCompanyDetail(id);
  } catch (error) {
    if (error instanceof CompanyDataError) return <CompanyDataState companyId={id} invalid />;
    throw error;
  }
  if (!company) return <CompanyDataState companyId={id} />;
  return <CompanyInsights key={company.company_id} company={company} />;
}
