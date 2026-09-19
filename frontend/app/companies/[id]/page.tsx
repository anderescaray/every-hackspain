import { notFound } from "next/navigation";
import { CompanyInsights } from "@/components/insights/CompanyInsights";
import { getCompanyDetail } from "@/services/companyData";

export default async function CompanyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const company = await getCompanyDetail(id);
  if (!company) notFound();
  return <CompanyInsights key={company.company_id} company={company} />;
}
