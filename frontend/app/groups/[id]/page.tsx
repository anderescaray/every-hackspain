import { GroupRoute } from "@/components/groups/GroupRoute";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export default async function GroupOverviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <GroupRoute groupId={id} view="overview" />;
}
