import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const view of [
  { route: "", title: "Visión general" },
  { route: "/network", title: "Red financiera" },
  { route: "/recommendations", title: "Recomendaciones" },
]) {
  test(`grupo ${view.title}: español, accesibilidad, responsive y sin errores de cliente`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`/groups/GROUP_0042${view.route}`);
    await expect(page.getByRole("heading", { name: view.title, exact: true })).toBeVisible();
    await expect(page.getByText("Demo · Datos de ejemplo")).toBeVisible();
    const menuButton = page.getByRole("button", { name: "Abrir navegación", exact: true });
    if (await menuButton.isVisible()) await menuButton.click();
    await expect(page.getByRole("navigation", { name: "Vistas de inteligencia de grupo" }).locator('[aria-current="page"]')).toHaveCount(1);
    const closeMenu = page.getByRole("button", { name: "Cerrar navegación", exact: true });
    if (await closeMenu.isVisible()) await closeMenu.click();
    expect(await page.locator("main").textContent()).not.toMatch(/Group Health Score|Group Overview|Group Network|Group Recommendations|View evidence|Review recurring|Insufficient evidence/);
    await page.screenshot({ path: testInfo.outputPath("group-page.png"), fullPage: true });
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => ({ html: node.html, issue: node.failureSummary })) }))).toEqual([]);
    for (const width of [320, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    expect(errors).toEqual([]);
  });
}

test("el acceso aparece automáticamente solo en empresas con grupo", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  await page.getByTestId("analysis-shell").waitFor();
  const openMenu = page.getByRole("button", { name: "Abrir navegación", exact: true });
  if (await openMenu.isVisible()) await openMenu.click();
  await page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true }).getByRole("link", { name: "Visión general", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Visión general", exact: true })).toBeVisible();
  await expect(page.getByText("2 deteriorándose", { exact: true })).toBeVisible();
  await expect(page.getByText("6 sociedades observadas de 8 conocidas", { exact: false })).toBeVisible();
  await page.goto("/companies/COMP_9001");
  await page.getByTestId("analysis-shell").waitFor();
  if (await openMenu.isVisible()) await openMenu.click();
  await expect(page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true })).toHaveCount(0);
});

test("overview permite priorizar sociedades y revisar evidencias", async ({ page }) => {
  await page.goto("/groups/GROUP_0042");
  const list = page.getByRole("list", { name: "Tabla de sociedades", exact: true });
  await expect(list.getByRole("listitem")).toHaveCount(2);
  await page.getByRole("button", { name: /Todas/ }).click();
  await expect(list.getByRole("listitem")).toHaveCount(6);
  await page.getByLabel("Buscar sociedad", { exact: true }).fill("COMP_0412");
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await list.getByRole("listitem").locator("summary").click();
  const button = list.getByRole("button", { name: "Ver evidencia: Sociedad COMP_0412", exact: true });
  await button.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("columnheader", { name: "Sociedad observada", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(button).toBeFocused();
  await list.getByRole("link", { name: "Ver en la red", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Detalle de la selección" }).getByRole("heading", { name: "COMP_0412", exact: true })).toBeVisible();
});

test("la red selecciona nodos por teclado y abre la ficha de sociedad", async ({ page }) => {
  await page.goto("/groups/GROUP_0042/network");
  const node = page.getByRole("button", { name: /^Seleccionar sociedad COMP_0412:/ });
  await node.focus();
  await page.keyboard.press("Enter");
  const detail = page.getByRole("complementary", { name: "Detalle de la selección" });
  await expect(detail.getByRole("heading", { name: "COMP_0412", exact: true })).toBeVisible();
  await expect(detail.getByText("42", { exact: true })).toBeVisible();
  await expect(detail.getByText("Receptora", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reducir zoom de la red" }).click();
  await expect(page.getByLabel("Zoom de la red", { exact: true })).toHaveText("80 %");
  await detail.getByRole("link", { name: "Abrir ficha de COMP_0412", exact: true }).click();
  await expect(page.getByRole("heading", { name: "COMP_0412", exact: true })).toBeVisible();
  await expect(page.getByTestId("health-score")).toHaveText("42");
});

test("la red distingue candidatas, desconocidas y relaciones confirmadas", async ({ page }) => {
  await page.goto("/groups/GROUP_0042/network");
  await page.getByLabel("Evidencia de la relación", { exact: true }).selectOption("candidate");
  await page.getByText("Ver todas las transferencias", { exact: true }).click();
  const list = page.getByRole("region", { name: "Lista de relaciones", exact: true });
  await expect(list.getByRole("button")).toHaveCount(1);
  await list.getByRole("button").click();
  const detail = page.getByRole("complementary", { name: "Detalle de la selección" });
  await expect(detail.getByText("No confirmada.", { exact: false })).toBeVisible();
  await detail.getByRole("button", { name: /^Ver evidencia: Relación/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("G-P-001", { exact: true })).toBeVisible();
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
  await page.getByRole("button", { name: "Cerrar evidencia de grupo" }).click();
  await page.getByLabel("Evidencia de la relación", { exact: true }).selectOption("unknown");
  await expect(list.getByRole("button")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /^Seleccionar relación/ })).toHaveCount(0);
  await list.getByRole("button").click();
  await expect(detail.getByText("COMP_1033 → Destino no identificado", { exact: true })).toBeVisible();
  await expect(detail.getByText("—", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Restablecer", exact: true }).click();
  await expect(list.getByRole("button")).toHaveCount(5);
});

test("de la relación al plan de revisión, sin ejecución de transferencias", async ({ page }) => {
  await page.goto("/groups/GROUP_0042/network?relation=support-0412");
  const detail = page.getByRole("complementary", { name: "Detalle de la selección" });
  await expect(detail.getByText("1,3 M€", { exact: true })).toBeVisible();
  await expect(detail.getByText("Mensual · cuatro meses consecutivos", { exact: true })).toBeVisible();
  await detail.getByRole("link", { name: "Revisiones relacionadas", exact: false }).click();
  await expect(page.getByRole("heading", { name: "Recomendaciones", exact: true })).toBeVisible();
  await expect(page.getByText("Relación: COMP_0007 → COMP_0412", { exact: true })).toBeVisible();
  await expect(page.getByText("Revisar el apoyo interno recurrente", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Quitar filtro de relación" }).click();
  await page.getByLabel("Prioridad", { exact: true }).selectOption("medium");
  await expect(page.getByText("4 revisiones", { exact: true })).toBeVisible();
  await expect(page.getByText("Completar la evidencia antes de concluir", { exact: true })).toBeVisible();
  await page.getByRole("article").filter({ hasText: "Completar la evidencia antes de concluir" }).getByText("Ver pasos y límites").click();
  await expect(page.getByText("La falta de conexiones no demuestra ausencia de relaciones.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Ejecutar|Transferir|Pagar/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Restablecer filtros" }).click();
  await expect(page.getByText("7 revisiones", { exact: true })).toBeVisible();
});

test("sin JSON, con JSON inválido o perímetro vacío no se inventa inteligencia", async ({ page }) => {
  for (const route of ["", "/network", "/recommendations"]) {
    await page.goto(`http://127.0.0.1:3108/groups/GROUP_0042${route}`);
    await expect(page.getByRole("heading", { name: "Datos de análisis del grupo todavía no disponibles." })).toBeVisible();
    await expect(page.getByRole("group", { name: "Grafo interactivo de sociedades y relaciones" })).toHaveCount(0);
  }
  await page.goto("/groups/GROUP_9998");
  await expect(page.getByRole("heading", { name: "Los datos del grupo necesitan revisión." })).toBeVisible();
  await page.goto("/groups/invalid");
  await expect(page.getByRole("heading", { name: "Grupo no disponible" })).toBeVisible();
  await page.goto("/groups/GROUP_0099/network");
  await expect(page.getByText("No hay sociedades observadas para dibujar una red.")).toBeVisible();
  await page.goto("/groups/GROUP_0099/recommendations");
  await expect(page.getByText("No se han suministrado recomendaciones.", { exact: false })).toBeVisible();
});
