import { GroupRoute } from "@/components/groups/GroupRoute";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function GroupRecommendationsPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ relation?: string | string[] }> }) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <GroupRoute groupId={id} view="recommendations" initialRelation={typeof query.relation === "string" ? query.relation : undefined} />;
}
