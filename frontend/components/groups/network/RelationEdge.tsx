"use client";

import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";
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
  const relation = data?.relation;
  const selected = Boolean(data?.selected);
  const dimmed = Boolean(data?.dimmed);
  const showLabel = Boolean(data?.showLabel);
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    curvature: 0.22,
  });
  const status = relation?.status ?? "unknown";
  const label = relation ? compactEdgeMoney(relation.volume) : null;
  const onSelect = data?.onSelect;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className={`${styles.relationEdge} ${styles[`edge-${status}`]}`}
        style={{
          strokeWidth: selected ? 3.2 : 2,
          opacity: dimmed ? 0.16 : 1,
          transition: "opacity 220ms ease, stroke-width 220ms ease",
        }}
        interactionWidth={30}
      />
      {relation ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            className={styles.edgeHit}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            aria-label={`Seleccionar relación ${relationName(relation)}: ${relationStatusLabels[relation.status]}`}
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
            <div
              className={styles.edgeLabel}
              data-selected={selected || undefined}
              data-status={status}
              style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY + (showLabel ? -16 : 0)}px)` }}
            >
              {label}
            </div>
          ) : null}
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const RelationEdge = memo(RelationEdgeComponent);
