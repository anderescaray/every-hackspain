"use client";

import {
  Background,
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
  NODE_HEIGHT,
  NODE_WIDTH,
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
  identified: "#0d5c52",
  candidate: "#8a6918",
  unknown: "#5a6570",
} as const;

function buildGraph(
  members: GroupMember[],
  relations: GroupRelation[],
  selection: Selection,
  focusMode: FocusMode,
  hoveredEdge: string | null,
  onSelectCompany: (id: string) => void,
  onSelectRelation: (id: string) => void,
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
    const hovered = hoveredEdge === edge.id;
    const touchesFocus = Boolean(focusCompany && (edge.source === focusCompany || edge.target === focusCompany));
    const dimmed = Boolean(
      (focusMode === "ego" && focusCompany && !touchesFocus)
      || (selection?.kind === "relation" && !selected)
      || (selection?.kind === "company" && focusMode === "network" && !touchesFocus),
    );
    return {
      ...edge,
      type: "relation",
      animated: false,
      zIndex: selected || hovered ? 8 : dimmed ? 0 : 1,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: selected ? 20 : 17,
        height: selected ? 20 : 17,
        color: STATUS_COLOR[edge.data!.relation.status],
      },
      data: {
        ...edge.data!,
        selected,
        hovered,
        dimmed,
        showLabel: shouldShowEdgeLabel(
          edge.data!.relation,
          edgeCount,
          selected,
          focusMode === "ego" || selection?.kind === "company" ? focusCompany ?? selection?.id ?? null : null,
          hovered,
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
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const graph = useMemo(
    () => buildGraph(members, relations, selection, focusMode, hoveredEdge, onSelectCompany, onSelectRelation),
    [members, relations, selection, focusMode, hoveredEdge, onSelectCompany, onSelectRelation],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<FlowEdge>([]);
  const [zoomPct, setZoomPct] = useState(100);
  const selectionKey = selection ? `${selection.kind}:${selection.id}` : "";
  const centeredSelection = useRef("");
  const zoomLockUntil = useRef(0);

  const reportZoom = (pct: number, lockMs = 0) => {
    if (lockMs > 0) zoomLockUntil.current = Date.now() + lockMs;
    setZoomPct(pct);
  };

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
    const frame = requestAnimationFrame(() => {
      if (cancelled) return;
      fitView({ padding: 0.18, duration: reduceMotion ? 0 : 260, minZoom: 0.4, maxZoom: 1.15 });
      window.setTimeout(() => {
        if (!cancelled && Date.now() >= zoomLockUntil.current) {
          setZoomPct(Math.round(getViewport().zoom * 100));
        }
      }, reduceMotion ? 40 : 300);
    });
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [graph.layoutKey, fitView, getViewport, reduceMotion]);

  useEffect(() => {
    if (!selection || centeredSelection.current === selectionKey) return;
    centeredSelection.current = selectionKey;
    const duration = reduceMotion ? 0 : 200;
    const timer = window.setTimeout(() => {
      if (selection.kind === "company") {
        const node = getNode(selection.id);
        if (!node) return;
        setCenter(node.position.x + NODE_WIDTH / 2, node.position.y + NODE_HEIGHT / 2, {
          zoom: 1,
          duration,
        });
        reportZoom(100, duration + 120);
      } else {
        const relation = graph.drawn.find((item) => item.id === selection.id);
        if (!relation?.from_company_id || !relation.to_company_id) return;
        fitView({
          nodes: [{ id: relation.from_company_id }, { id: relation.to_company_id }],
          padding: 0.35,
          duration,
          maxZoom: 1.1,
        });
        window.setTimeout(() => {
          reportZoom(Math.round(getViewport().zoom * 100), 80);
        }, duration + 30);
      }
    }, 40);
    return () => window.clearTimeout(timer);
  }, [selection, selectionKey, fitView, getNode, getViewport, setCenter, reduceMotion, graph.drawn]);

  const nudgeZoom = (direction: -1 | 1) => {
    const snapped = Math.round(zoomPct / 20) * 20;
    const nextPct = Math.min(180, Math.max(40, snapped + direction * 20));
    const viewport = getViewport();
    setViewport({ ...viewport, zoom: nextPct / 100 }, { duration: reduceMotion ? 0 : 160 });
    reportZoom(nextPct, 200);
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
          {!selection ? " · selecciona una sociedad o transferencia" : ""}
        </span>
        <div className={styles.toolbarActions}>
          <button type="button" aria-label="Reducir zoom de la red" disabled={zoomPct <= 40} onClick={() => nudgeZoom(-1)}>−</button>
          <output aria-label="Zoom de la red">{numberLabel(zoomPct, 0)} %</output>
          <button type="button" aria-label="Ampliar zoom de la red" disabled={zoomPct >= 180} onClick={() => nudgeZoom(1)}>+</button>
          <button
            type="button"
            className={styles.toolButton}
            onClick={() => {
              fitView({ padding: 0.18, duration: reduceMotion ? 0 : 260 });
              window.setTimeout(() => {
                if (Date.now() >= zoomLockUntil.current) {
                  setZoomPct(Math.round(getViewport().zoom * 100));
                }
              }, reduceMotion ? 0 : 280);
            }}
          >
            Encajar red
          </button>
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
          onEdgeMouseEnter={(_, edge) => setHoveredEdge(edge.id)}
          onEdgeMouseLeave={() => setHoveredEdge(null)}
          onInit={(instance) => {
            instance.fitView({ padding: 0.18, minZoom: 0.4, maxZoom: 1.15 });
            setZoomPct(Math.round(instance.getViewport().zoom * 100));
          }}
          onMoveEnd={(_, viewport) => {
            if (Date.now() < zoomLockUntil.current) return;
            setZoomPct(Math.round(viewport.zoom * 100));
          }}
          fitView
          fitViewOptions={{ padding: 0.18, minZoom: 0.4, maxZoom: 1.15 }}
          minZoom={0.3}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          panOnScroll
          zoomOnScroll
          zoomOnPinch
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "relation" }}
        >
          <Background gap={32} size={0.45} color="#e4e7e4" />
          {members.length > 18 ? <MiniMap pannable zoomable nodeStrokeWidth={2} style={{ width: 112, height: 72 }} /> : null}
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
