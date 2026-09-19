import { GroupRoute } from "@/components/groups/GroupRoute";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function GroupNetworkPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ relation?: string | string[]; company?: string | string[] }> }) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <GroupRoute groupId={id} view="network" initialRelation={typeof query.relation === "string" ? query.relation : undefined} initialCompany={typeof query.company === "string" ? query.company : undefined} />;
}
