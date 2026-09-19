import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type { GroupMember, GroupRelation } from "@/types/groupDetail";
import { numberLabel } from "@/lib/companyFormat";

export const NODE_WIDTH = 148;
export const NODE_HEIGHT = 72;

export type NetworkEdgeData = {
  relation: GroupRelation;
  dimmed: boolean;
  selected: boolean;
  showLabel: boolean;
  hovered?: boolean;
  onSelect?: (id: string) => void;
};

export type NetworkNodeData = {
  member: GroupMember;
  dimmed: boolean;
  selected: boolean;
  related: boolean;
  isolated: boolean;
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
    return `${numberLabel(absolute / 1_000, decimals)} k€`;
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

export function shouldShowEdgeLabel(relation: GroupRelation, edgeCount: number, selected: boolean, focusCompany: string | null, hovered = false): boolean {
  if (relation.volume === null) return false;
  if (selected || hovered) return true;
  if (focusCompany && (relation.from_company_id === focusCompany || relation.to_company_id === focusCompany)) return true;
  if (edgeCount <= 8 && relation.status === "identified") return true;
  if (edgeCount <= 5) return true;
  return relation.status === "identified" && relation.volume >= 500_000 && edgeCount <= 12;
}

function linkedMemberIds(relations: GroupRelation[]): Set<string> {
  const ids = new Set<string>();
  for (const relation of drawableRelations(relations)) {
    ids.add(relation.from_company_id!);
    ids.add(relation.to_company_id!);
  }
  return ids;
}

export function layoutNetwork(
  members: GroupMember[],
  relations: GroupRelation[],
  options?: { rankdir?: "LR" | "TB" },
): { nodes: Node<NetworkNodeData>[]; edges: Edge<NetworkEdgeData>[] } {
  const drawn = drawableRelations(relations);
  const linked = linkedMemberIds(drawn);
  const connectedMembers = members.filter((member) => linked.has(member.company_id));
  const isolatedMembers = members.filter((member) => !linked.has(member.company_id));
  const count = Math.max(connectedMembers.length, 1);

  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: options?.rankdir ?? "LR",
    nodesep: count > 20 ? 56 : count > 10 ? 68 : 84,
    ranksep: count > 20 ? 120 : count > 10 ? 140 : 160,
    edgesep: count > 12 ? 36 : 44,
    marginx: 48,
    marginy: 36,
  });

  for (const member of connectedMembers) {
    graph.setNode(member.company_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const relation of drawn) {
    graph.setEdge(relation.from_company_id!, relation.to_company_id!, { id: relation.id });
  }
  if (connectedMembers.length) dagre.layout(graph);

  let minX = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const connectedNodes: Node<NetworkNodeData>[] = connectedMembers.map((member) => {
    const position = graph.node(member.company_id);
    const x = (position?.x ?? 0) - NODE_WIDTH / 2;
    const y = (position?.y ?? 0) - NODE_HEIGHT / 2;
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x + NODE_WIDTH);
    maxY = Math.max(maxY, y + NODE_HEIGHT);
    return {
      id: member.company_id,
      type: "company",
      position: { x, y },
      data: { member, dimmed: false, selected: false, related: false, isolated: false },
      draggable: false,
      selectable: true,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      style: { width: NODE_WIDTH, height: NODE_HEIGHT },
    };
  });

  if (!Number.isFinite(minX)) {
    minX = 0;
    maxX = 0;
    maxY = 0;
  }

  const isolatedGap = NODE_WIDTH + 36;
  const isolatedStartY = connectedNodes.length ? maxY + 96 : 0;
  const isolatedNodes: Node<NetworkNodeData>[] = isolatedMembers.map((member, index) => ({
    id: member.company_id,
    type: "company",
    position: {
      x: minX + index * isolatedGap,
      y: isolatedStartY,
    },
    data: { member, dimmed: false, selected: false, related: false, isolated: true },
    draggable: false,
    selectable: true,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    style: { width: NODE_WIDTH, height: NODE_HEIGHT },
  }));

  const nodes = [...connectedNodes, ...isolatedNodes];
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
