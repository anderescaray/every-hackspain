import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type { GroupMember, GroupRelation } from "@/types/groupDetail";
import { numberLabel } from "@/lib/companyFormat";

export const NODE_WIDTH = 168;
export const NODE_HEIGHT = 92;

export type NetworkEdgeData = {
  relation: GroupRelation;
  dimmed: boolean;
  selected: boolean;
  showLabel: boolean;
  onSelect?: (id: string) => void;
};

export type NetworkNodeData = {
  member: GroupMember;
  dimmed: boolean;
  selected: boolean;
  related: boolean;
  onSelect?: (id: string) => void;
};

export function compactEdgeMoney(value: number | null): string | null {
  if (value === null) return null;
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) {
    const decimals = absolute >= 10_000_000 ? 0 : 1;
    return `${numberLabel(absolute / 1_000_000, decimals)} M€`;
  }
  if (absolute >= 1_000) {
    const decimals = absolute >= 10_000 ? 0 : absolute % 1000 === 0 ? 0 : 0;
    return `${numberLabel(absolute / 1_000, decimals)} k €`;
  }
  return `${numberLabel(absolute, 0)} €`;
}

export function drawableRelations(relations: GroupRelation[]): GroupRelation[] {
  return relations.filter((relation) => relation.from_company_id !== null && relation.to_company_id !== null);
}

export function connectedIds(relations: GroupRelation[], companyId: string): Set<string> {
  const ids = new Set<string>([companyId]);
  for (const relation of relations) {
    if (relation.from_company_id === companyId && relation.to_company_id) ids.add(relation.to_company_id);
    if (relation.to_company_id === companyId && relation.from_company_id) ids.add(relation.from_company_id);
  }
  return ids;
}

export function shouldShowEdgeLabel(relation: GroupRelation, edgeCount: number, selected: boolean, focusCompany: string | null): boolean {
  if (relation.volume === null) return false;
  if (selected) return true;
  if (focusCompany && (relation.from_company_id === focusCompany || relation.to_company_id === focusCompany)) return true;
  if (edgeCount <= 8 && relation.status === "identified") return true;
  if (edgeCount <= 5) return true;
  return relation.status === "identified" && relation.volume >= 500_000 && edgeCount <= 14;
}

export function layoutNetwork(
  members: GroupMember[],
  relations: GroupRelation[],
  options?: { rankdir?: "LR" | "TB" },
): { nodes: Node<NetworkNodeData>[]; edges: Edge<NetworkEdgeData>[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: options?.rankdir ?? "LR",
    nodesep: members.length > 12 ? 48 : 64,
    ranksep: members.length > 12 ? 90 : 110,
    edgesep: 28,
    marginx: 40,
    marginy: 40,
  });

  for (const member of members) {
    graph.setNode(member.company_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  const drawn = drawableRelations(relations);
  for (const relation of drawn) {
    graph.setEdge(relation.from_company_id!, relation.to_company_id!, { id: relation.id });
  }
  dagre.layout(graph);

  const nodes: Node<NetworkNodeData>[] = members.map((member) => {
    const position = graph.node(member.company_id);
    return {
      id: member.company_id,
      type: "company",
      position: {
        x: (position?.x ?? 0) - NODE_WIDTH / 2,
        y: (position?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: { member, dimmed: false, selected: false, related: false },
      draggable: false,
      selectable: true,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    };
  });

  const edges: Edge<NetworkEdgeData>[] = drawn.map((relation) => ({
    id: relation.id,
    source: relation.from_company_id!,
    target: relation.to_company_id!,
    type: "relation",
    data: { relation, dimmed: false, selected: false, showLabel: false },
    selectable: true,
  }));

  return { nodes, edges };
}
