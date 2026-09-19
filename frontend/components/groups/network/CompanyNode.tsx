"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { GroupMember } from "@/types/groupDetail";
import { groupScore, roleLabels } from "@/lib/groupPresentation";
import type { NetworkNodeData } from "@/lib/networkLayout";
import styles from "./network.module.css";

export type CompanyFlowNodeType = Node<NetworkNodeData, "company">;

function healthTone(score: number | null): "unknown" | "low" | "mid" | "high" {
  if (score === null) return "unknown";
  if (score < 50) return "low";
  if (score < 70) return "mid";
  return "high";
}

function CompanyNodeComponent({ data }: NodeProps<CompanyFlowNodeType>) {
  const { member, dimmed, selected, related, onSelect } = data;
  const tone = healthTone(member.health_score);
  const activate = () => onSelect?.(member.company_id);
  return (
    <div
      className={`${styles.companyNode} ${styles[`tone-${tone}`]} ${styles[`attention-${member.attention}`]}`}
      data-selected={selected || undefined}
      data-related={related || undefined}
      data-dimmed={dimmed || undefined}
      role="button"
      tabIndex={0}
      aria-label={`Seleccionar sociedad ${member.company_id}: Health Score ${groupScore(member.health_score)}, Momentum ${groupScore(member.dimensions.momentum)}, Resiliencia ${groupScore(member.dimensions.resilience)}`}
      aria-pressed={selected}
      title={`${member.company_id} · ${roleLabels[member.role]}`}
      onClick={(event) => {
        event.stopPropagation();
        activate();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          activate();
        }
      }}
    >
      <Handle type="target" position={Position.Left} className={styles.handle} isConnectable={false} />
      <span className={styles.nodeScore}>{groupScore(member.health_score)}</span>
      <span className={styles.nodeId}>{member.company_id}</span>
      <span className={styles.nodeMeta}>Health Score</span>
      <Handle type="source" position={Position.Right} className={styles.handle} isConnectable={false} />
    </div>
  );
}

export const CompanyNode = memo(CompanyNodeComponent);

export type { GroupMember };
