import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const view of [
  { route: "", title: "Visión general" },
  { route: "/recommendations", title: "Recomendaciones" },
]) {
  test(`grupo ${view.title}: español, accesibilidad, responsive y sin errores de cliente`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`/groups/GROUP_0042${view.route}`);
    await expect(page.getByRole("heading", { name: view.title, exact: true })).toBeVisible();
    await expect(page.getByText("Datos de ejemplo")).toBeVisible();
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
  const row = list.getByRole("listitem").filter({ hasText: "COMP_0412" });
  await row.locator("summary").click();
  const button = row.getByRole("button", { name: "Ver evidencia: Sociedad COMP_0412", exact: true });
  await button.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("columnheader", { name: "Sociedad observada", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(button).toBeFocused();
  await row.getByRole("link", { name: "Abrir ficha", exact: true }).click();
  await expect(page.getByRole("heading", { name: "COMP_0412", exact: true })).toBeVisible();
});

test("sin JSON, con JSON inválido o perímetro vacío no se inventa inteligencia", async ({ page }) => {
  for (const route of ["", "/recommendations"]) {
    await page.goto(`http://127.0.0.1:3108/groups/GROUP_0042${route}`);
    await expect(page.getByRole("heading", { name: "Datos del grupo no disponibles." })).toBeVisible();
  }
  await page.goto("/groups/GROUP_9998");
  await expect(page.getByRole("heading", { name: "Los datos del grupo necesitan revisión." })).toBeVisible();
  await page.goto("/groups/invalid");
  await expect(page.getByRole("heading", { name: "Grupo no disponible" })).toBeVisible();
  await page.goto("/groups/GROUP_0099/recommendations");
  await expect(page.getByText("Ninguna acción supera las guardas de producción", { exact: false })).toBeVisible();
});
