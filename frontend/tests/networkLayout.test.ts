import assert from "node:assert/strict";
import test from "node:test";
import type { GroupMember, GroupRelation } from "../types/groupDetail";
import {
  compactEdgeMoney,
  connectedIds,
  drawableRelations,
  layoutNetwork,
  shouldShowEdgeLabel,
} from "../lib/networkLayout";

function member(id: string, score = 70): GroupMember {
  return {
    company_id: id as GroupMember["company_id"],
    health_score: score,
    dimensions: { momentum: score, cash_generation: score, resilience: score, debt: score },
    trajectory: "stable",
    role: "none_identified",
    available_liquidity: 1000,
    identified_debt: 1000,
    obligations_due: 100,
    cash_generation_net: 50,
    internal_received: null,
    internal_provided: null,
    confidence: 80,
    attention: "low",
    score_status: "complete",
    missing_components: [],
    summary: "Sociedad de prueba para layout.",
    outlook: { status: "available", horizon: "30d", summary: "Sin necesidad.", funding_need: 0, confidence: 80, evidence_refs: [] },
    evidence_refs: [],
  };
}

function relation(id: string, from: string, to: string, volume = 420_000): GroupRelation {
  return {
    id,
    from_company_id: from as GroupRelation["from_company_id"],
    to_company_id: to as GroupRelation["to_company_id"],
    kind: "support",
    status: "identified",
    volume,
    transfer_count: 2,
    period: "ago 2026",
    recurrence: "Mensual",
    change: "stable",
    first_seen: "2026-01-01",
    last_seen: "2026-08-01",
    explanation: "Relación sintética de stress test.",
    confidence: 80,
    evidence_refs: [],
  };
}

test("compactEdgeMoney usa formato corto legible", () => {
  assert.equal(compactEdgeMoney(420_000), "420 k€");
  assert.equal(compactEdgeMoney(1_300_000), "1,3 M€");
  assert.equal(compactEdgeMoney(null), null);
});

test("drawableRelations omite extremos nulos", () => {
  const rows = [
    relation("a", "COMP_0001", "COMP_0002"),
    { ...relation("b", "COMP_0001", "COMP_0002"), to_company_id: null },
  ];
  assert.equal(drawableRelations(rows).length, 1);
});

test("layoutNetwork coloca nodos sin solaparse en grupos pequeños", () => {
  const members = [member("COMP_0001", 85), member("COMP_0002", 42), member("COMP_0003", 70)];
  const relations = [relation("r1", "COMP_0001", "COMP_0002"), relation("r2", "COMP_0001", "COMP_0003")];
  const { nodes, edges } = layoutNetwork(members, relations);
  assert.equal(nodes.length, 3);
  assert.equal(edges.length, 2);
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const dx = Math.abs(nodes[i].position.x - nodes[j].position.x);
      const dy = Math.abs(nodes[i].position.y - nodes[j].position.y);
      assert.ok(dx > 40 || dy > 40, "nodos demasiado cercanos");
    }
  }
});

test("layoutNetwork coloca sociedades aisladas fuera del componente conectado", () => {
  const members = [member("COMP_0001", 85), member("COMP_0002", 42), member("COMP_9999", 60)];
  const relations = [relation("r1", "COMP_0001", "COMP_0002")];
  const { nodes } = layoutNetwork(members, relations);
  const linked = nodes.filter((node) => node.id !== "COMP_9999");
  const isolated = nodes.find((node) => node.id === "COMP_9999")!;
  const maxLinkedY = Math.max(...linked.map((node) => node.position.y));
  assert.ok(isolated.position.y > maxLinkedY + 40);
  assert.equal(isolated.data?.isolated, true);
});

test("layoutNetwork escala a muchas sociedades sin coordenadas manuales", () => {
  const size = 36;
  const members = Array.from({ length: size }, (_, index) => member(`COMP_${String(index + 1).padStart(4, "0")}` as `COMP_${string}`, 55 + (index % 40)));
  const relations = Array.from({ length: size - 1 }, (_, index) =>
    relation(`edge-${index}`, members[0].company_id, members[index + 1].company_id, 100_000 + index * 10_000),
  );
  const { nodes, edges } = layoutNetwork(members, relations);
  assert.equal(nodes.length, size);
  assert.equal(edges.length, size - 1);
  const xs = nodes.map((node) => node.position.x);
  const ys = nodes.map((node) => node.position.y);
  assert.ok(Math.max(...xs) - Math.min(...xs) > 200);
  assert.ok(Math.max(...ys) - Math.min(...ys) > 80);
  const ids = connectedIds(relations, members[0].company_id);
  assert.equal(ids.size, size);
  assert.equal(shouldShowEdgeLabel(relations[0], edges.length, false, null), false);
  assert.equal(shouldShowEdgeLabel(relations[0], 4, false, null), true);
});

test("layoutNetwork mantiene composición compacta en 5/15/30/50 nodos", () => {
  for (const size of [5, 15, 30, 50]) {
    const members = Array.from({ length: size }, (_, index) => member(`COMP_${String(index + 1).padStart(4, "0")}` as `COMP_${string}`, 40 + (index % 50)));
    const relations = Array.from({ length: Math.max(size - 2, 1) }, (_, index) =>
      relation(`e-${size}-${index}`, members[index % Math.max(size - 1, 1)].company_id, members[(index + 1) % size].company_id, 250_000 * (index + 1)),
    );
    // deja 1 aislada en tamaños grandes
    const linkedRelations = size >= 15 ? relations.slice(0, -1) : relations;
    const { nodes, edges } = layoutNetwork(members, linkedRelations);
    assert.equal(nodes.length, size);
    assert.equal(edges.length, linkedRelations.length);
    const isolated = nodes.filter((node) => node.data?.isolated);
    if (size >= 15) assert.ok(isolated.length >= 1);
    const boxW = Math.max(...nodes.map((node) => node.position.x)) - Math.min(...nodes.map((node) => node.position.x));
    const boxH = Math.max(...nodes.map((node) => node.position.y)) - Math.min(...nodes.map((node) => node.position.y));
    assert.ok(boxW + boxH > size * 8, `bbox demasiado compacto para ${size}`);
    assert.equal(shouldShowEdgeLabel(linkedRelations[0], edges.length, false, null), edges.length <= 8);
  }
});
