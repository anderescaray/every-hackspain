"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GroupMember, GroupRelation } from "@/types/groupDetail";
import { numberLabel } from "@/lib/companyFormat";
import {
  connectedIds,
  drawableRelations,
  layoutNetwork,
  shouldShowEdgeLabel,
  type NetworkEdgeData,
  type NetworkNodeData,
} from "@/lib/networkLayout";
import { CompanyNode } from "./CompanyNode";
import { RelationEdge } from "./RelationEdge";
import styles from "./network.module.css";
import base from "@/components/insights/insights.module.css";

type Selection = { kind: "company" | "relation"; id: string } | null;
export type FocusMode = "network" | "ego";

type CanvasProps = {
  members: GroupMember[];
  relations: GroupRelation[];
  selection: Selection;
  focusMode: FocusMode;
  onSelectCompany: (id: string) => void;
  onSelectRelation: (id: string) => void;
  onClearSelection: () => void;
  expanded: boolean;
};

type FlowNode = Node<NetworkNodeData, "company">;
type FlowEdge = Edge<NetworkEdgeData, "relation">;

const nodeTypes = { company: CompanyNode };
const edgeTypes = { relation: RelationEdge };

const STATUS_COLOR = {
  identified: "#0c7a6c",
  candidate: "#9a6b1f",
  unknown: "#677488",
} as const;

function buildGraph(
  members: GroupMember[],
  relations: GroupRelation[],
  selection: Selection,
  focusMode: FocusMode,
  onSelectCompany: (id: string) => void,
  onSelectRelation: (id: string) => void,
  reduceMotion: boolean,
): { nodes: FlowNode[]; edges: FlowEdge[]; layoutKey: string; drawn: GroupRelation[] } {
  const drawn = drawableRelations(relations);
  const layoutKey = `${members.map((member) => member.company_id).join(",")}|${drawn.map((relation) => relation.id).join(",")}`;
  const { nodes: laidOutNodes, edges: laidOutEdges } = layoutNetwork(members, drawn);
  const focusCompany = selection?.kind === "company" ? selection.id : null;
  const neighborIds = focusCompany && focusMode === "ego" ? connectedIds(drawn, focusCompany) : null;
  const edgeCount = drawn.length;

  const nodes: FlowNode[] = laidOutNodes.map((node) => {
    const selected = selection?.kind === "company" && selection.id === node.id;
    const relatedToRelation = Boolean(
      selection?.kind === "relation"
      && drawn.some((relation) => relation.id === selection.id && (relation.from_company_id === node.id || relation.to_company_id === node.id)),
    );
    const relatedToCompany = Boolean(
      selection?.kind === "company"
      && selection.id !== node.id
      && drawn.some((relation) =>
        (relation.from_company_id === selection.id || relation.to_company_id === selection.id)
        && (relation.from_company_id === node.id || relation.to_company_id === node.id),
      ),
    );
    const related = relatedToRelation || relatedToCompany || Boolean(neighborIds?.has(node.id));
    const dimmed = Boolean(
      (focusMode === "ego" && neighborIds && !neighborIds.has(node.id))
      || (selection?.kind === "relation" && !related && !selected)
      || (selection?.kind === "company" && focusMode === "network" && !selected && !related),
    );
    return {
      ...node,
      type: "company",
      data: {
        ...node.data!,
        selected,
        related: related && !selected,
        dimmed,
        onSelect: onSelectCompany,
      },
    };
  });

  const edges: FlowEdge[] = laidOutEdges.map((edge) => {
    const selected = selection?.kind === "relation" && selection.id === edge.id;
    const touchesFocus = Boolean(focusCompany && (edge.source === focusCompany || edge.target === focusCompany));
    const dimmed = Boolean(
      (focusMode === "ego" && focusCompany && !touchesFocus)
      || (selection?.kind === "relation" && !selected)
      || (selection?.kind === "company" && focusMode === "network" && !touchesFocus),
    );
    return {
      ...edge,
      type: "relation",
      animated: selected && !reduceMotion,
      zIndex: selected ? 8 : dimmed ? 0 : 1,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: selected ? 18 : 16,
        height: selected ? 18 : 16,
        color: STATUS_COLOR[edge.data!.relation.status],
      },
      data: {
        ...edge.data!,
        selected,
        dimmed,
        showLabel: shouldShowEdgeLabel(
          edge.data!.relation,
          edgeCount,
          selected,
          focusMode === "ego" || selection?.kind === "company" ? focusCompany ?? selection?.id ?? null : null,
        ),
        onSelect: onSelectRelation,
      },
    };
  });

  return { nodes, edges, layoutKey, drawn };
}

function NetworkCanvasInner({
  members,
  relations,
  selection,
  focusMode,
  onSelectCompany,
  onSelectRelation,
  onClearSelection,
  expanded,
}: CanvasProps) {
  const { fitView, setViewport, getViewport, setCenter, getNode } = useReactFlow();
  const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const graph = useMemo(
    () => buildGraph(members, relations, selection, focusMode, onSelectCompany, onSelectRelation, reduceMotion),
    [members, relations, selection, focusMode, onSelectCompany, onSelectRelation, reduceMotion],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>([]);
  const [zoomState, setZoomState] = useState({ key: graph.layoutKey, pct: 100 });
  const zoomPct = zoomState.key === graph.layoutKey ? zoomState.pct : 100;
  const setZoomPct = (pct: number) => setZoomState({ key: graph.layoutKey, pct });
  const selectionKey = selection ? `${selection.kind}:${selection.id}` : "";
  const centeredSelection = useRef("");

  useEffect(() => {
    const sync = () => {
      setNodes(graph.nodes);
      setEdges(graph.edges);
    };
    const frame = requestAnimationFrame(sync);
    return () => cancelAnimationFrame(frame);
  }, [graph, setNodes, setEdges]);

  useEffect(() => {
    let cancelled = false;
    const run = () => {
      if (cancelled) return;
      fitView({ padding: 0.22, duration: reduceMotion ? 0 : 280, minZoom: 0.45, maxZoom: 1.2 });
    };
    const frame = requestAnimationFrame(() => {
      run();
      window.setTimeout(run, 100);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [graph.layoutKey, fitView, reduceMotion]);

  useEffect(() => {
    if (!selection || centeredSelection.current === selectionKey) return;
    centeredSelection.current = selectionKey;
    const duration = reduceMotion ? 0 : 320;
    const timer = window.setTimeout(() => {
      if (selection.kind === "company") {
        const node = getNode(selection.id);
        if (!node) return;
        setCenter(node.position.x + 84, node.position.y + 46, { zoom: Math.max(getViewport().zoom, 0.95), duration });
      } else {
        const relation = graph.drawn.find((item) => item.id === selection.id);
        if (!relation?.from_company_id || !relation.to_company_id) return;
        fitView({
          nodes: [{ id: relation.from_company_id }, { id: relation.to_company_id }],
          padding: 0.4,
          duration,
        });
      }
    }, 40);
    return () => window.clearTimeout(timer);
  }, [selection, selectionKey, fitView, getNode, getViewport, setCenter, reduceMotion, graph.drawn]);

  const nudgeZoom = (delta: number) => {
    const viewport = getViewport();
    const nextZoom = Math.min(1.8, Math.max(0.4, Number((viewport.zoom + delta).toFixed(2))));
    const nextPct = Math.min(180, Math.max(40, zoomPct + Math.round(delta * 100)));
    setViewport({ ...viewport, zoom: nextZoom }, { duration: reduceMotion ? 0 : 160 });
    setZoomPct(nextPct);
  };

  if (!members.length) {
    return <p className={`${base.emptyState} ${styles.emptyCanvas}`}>No hay sociedades observadas para dibujar una red.</p>;
  }

  return (
    <div className={styles.canvasShell} data-expanded={expanded} data-testid="network-canvas">
      <div className={styles.toolbar}>
        <span role="status">
          {relations.length} transferencias · {graph.drawn.length} en el grafo
          {focusMode === "ego" && selection?.kind === "company" ? ` · foco ${selection.id}` : ""}
        </span>
        <div className={styles.toolbarActions}>
          <button type="button" aria-label="Reducir zoom de la red" disabled={zoomPct <= 40} onClick={() => nudgeZoom(-0.2)}>−</button>
          <output aria-label="Zoom de la red">{numberLabel(zoomPct, 0)} %</output>
          <button type="button" aria-label="Ampliar zoom de la red" disabled={zoomPct >= 180} onClick={() => nudgeZoom(0.2)}>+</button>
          <button type="button" className={styles.toolButton} onClick={() => fitView({ padding: 0.22, duration: reduceMotion ? 0 : 320 })}>
            Encajar red
          </button>
          {selection?.kind === "company" ? (
            <button
              type="button"
              className={styles.toolButton}
              onClick={() => {
                const node = getNode(selection.id);
                if (!node) return;
                setCenter(node.position.x + 84, node.position.y + 46, { zoom: Math.max(getViewport().zoom, 1), duration: reduceMotion ? 0 : 280 });
              }}
            >
              Centrar selección
            </button>
          ) : null}
        </div>
      </div>
      <div className={styles.flowHost} role="group" aria-label="Grafo interactivo de sociedades y relaciones">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onPaneClick={onClearSelection}
          onNodeClick={(_, node) => onSelectCompany(node.id)}
          onEdgeClick={(_, edge) => onSelectRelation(edge.id)}
          onInit={(instance) => instance.fitView({ padding: 0.22, minZoom: 0.45, maxZoom: 1.2 })}
          fitView
          fitViewOptions={{ padding: 0.22, minZoom: 0.45, maxZoom: 1.2 }}
          minZoom={0.35}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          panOnScroll
          zoomOnScroll
          zoomOnPinch
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={22} size={1} color="#c5d4cc" />
          <Controls showInteractive={false} position="bottom-left" />
          {members.length > 10 ? <MiniMap pannable zoomable nodeStrokeWidth={2} style={{ width: 120, height: 80 }} /> : null}
        </ReactFlow>
      </div>
      {!graph.drawn.length ? <p className={`${base.emptyState} ${styles.emptyCanvas}`}>No hay conexiones dibujables con estos filtros.</p> : null}
    </div>
  );
}

export function NetworkCanvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <NetworkCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
