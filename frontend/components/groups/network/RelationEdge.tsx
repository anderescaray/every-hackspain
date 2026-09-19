"use client";

import { BaseEdge, EdgeLabelRenderer, getBezierPath, useStore, type EdgeProps } from "@xyflow/react";
import { memo } from "react";
import { compactEdgeMoney, type NetworkEdgeData } from "@/lib/networkLayout";
import { relationKindLabels, relationName, relationStatusLabels } from "@/lib/groupPresentation";
import styles from "./network.module.css";

function RelationEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps & { data?: NetworkEdgeData }) {
  const zoom = useStore((state) => state.transform[2]);
  const labelScale = zoom > 0 ? 1 / zoom : 1;
  const relation = data?.relation;
  const selected = Boolean(data?.selected);
  const dimmed = Boolean(data?.dimmed);
  const hovered = Boolean(data?.hovered);
  const showLabel = Boolean(data?.showLabel);
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    curvature: 0.18,
  });
  const status = relation?.status ?? "unknown";
  const label = relation ? compactEdgeMoney(relation.volume) : null;
  const onSelect = data?.onSelect;
  const prominent = selected || hovered;
  const labelTransform = `translate(-50%, -50%) translate(${labelX}px, ${labelY}px) scale(${labelScale})`;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className={`${styles.relationEdge} ${styles[`edge-${status}`]}`}
        style={{
          strokeWidth: selected ? 3.4 : hovered ? 2.8 : 2.2,
          opacity: dimmed ? 0.14 : 1,
          transition: "opacity 180ms ease, stroke-width 180ms ease",
        }}
        interactionWidth={36}
      />
      {relation ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            className={styles.edgeHit}
            style={{ transform: labelTransform }}
            aria-label={`Seleccionar relación ${relationName(relation)}: ${relationStatusLabels[relation.status]}${label ? `, ${label}` : ""}`}
            aria-pressed={selected}
            title={`${relationName(relation)} · ${relationKindLabels[relation.kind]}`}
            onClick={(event) => {
              event.stopPropagation();
              onSelect?.(relation.id);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                event.stopPropagation();
                onSelect?.(relation.id);
              }
            }}
          />
          {showLabel && label ? (
            <button
              type="button"
              className={styles.edgeLabel}
              data-selected={selected || undefined}
              data-hovered={hovered || undefined}
              data-status={status}
              data-prominent={prominent || undefined}
              style={{ transform: labelTransform }}
              aria-hidden="true"
              tabIndex={-1}
              onClick={(event) => {
                event.stopPropagation();
                onSelect?.(relation.id);
              }}
            >
              {label}
            </button>
          ) : null}
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const RelationEdge = memo(RelationEdgeComponent);
