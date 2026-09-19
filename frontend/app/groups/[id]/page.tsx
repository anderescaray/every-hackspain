import { GroupRoute } from "@/components/groups/GroupRoute";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function GroupOverviewPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ entity?: string | string[] }> }) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <GroupRoute groupId={id} view="overview" contextCompany={typeof query.entity === "string" ? query.entity : undefined} />;
}
