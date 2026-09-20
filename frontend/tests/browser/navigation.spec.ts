import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function openMenu(page: Page) {
  await page.getByTestId("analysis-shell").waitFor();
  const trigger = page.getByRole("button", { name: "Abrir navegación", exact: true });
  if (await trigger.isVisible()) await trigger.click();
}

async function closeMenu(page: Page) {
  const close = page.getByRole("button", { name: "Cerrar navegación", exact: true });
  if (await close.isVisible()) await close.click();
}

test("un menú reúne las cinco secciones de empresa y las tres del grupo", async ({ page }, testInfo) => {
  await page.goto("/companies/COMP_0356");
  await openMenu(page);
  const company = page.getByRole("navigation", { name: "Secciones de empresa", exact: true });
  const group = page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true });
  await expect(company.getByRole("link")).toHaveCount(5);
  await expect(group.getByRole("link")).toHaveCount(3);
  for (const label of ["Health Score", "Tendencia", "Origen de la caja", "Tiempo financiado", "Escenarios"]) await expect(company.getByRole("link", { name: label, exact: true })).toBeVisible();
  await expect(page.getByRole("separator")).toBeVisible();
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations.map((item) => ({ id: item.id, nodes: item.nodes.map((node) => ({ html: node.html, issue: node.failureSummary })) }))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("unified-menu.png"), fullPage: true });
  await page.getByRole("button", { name: "Secciones de empresa", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Secciones de empresa", exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Secciones de empresa", exact: true }).click();
  await page.getByRole("button", { name: "Secciones de grupo", exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Secciones de grupo", exact: true }).click();
  await closeMenu(page);
});

test("los accesos desplazan a la sección elegida sin quitar alertas o escenarios", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  for (const [label, id] of [["Tendencia", "trajectory"], ["Origen de la caja", "cash-truth"], ["Tiempo financiado", "time-borrowed"], ["Escenarios", "scenarios"], ["Health Score", "health-score"]]) {
    await openMenu(page);
    await page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/companies/COMP_0356#${id}$`));
    await expect(page.locator(`#${id}`)).toBeInViewport();
    await expect(page.getByRole("dialog", { name: "Navegación de empresa y grupo" })).not.toBeVisible();
    if (id === "cash-truth") {
      await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }));
      await openMenu(page);
      await page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: label, exact: true }).click();
      await expect(page.locator(`#${id}`)).toBeInViewport();
    }
  }
  await expect(page.getByRole("region", { name: "Alertas priorizadas", exact: true })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: "Escenarios", exact: true })).toHaveCount(1);
});

test("empresa seleccionada se conserva al recorrer grupo y regresar a caja", async ({ page }) => {
  await page.goto("/companies/COMP_0412");
  for (const [label, suffix] of [["Visión general", ""], ["Red financiera", "/network"], ["Recomendaciones", "/recommendations"]]) {
    await openMenu(page);
    const menu = page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true });
    await menu.getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/groups/GROUP_0042${suffix}\\?entity=COMP_0412$`));
    await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
  }
  await openMenu(page);
  await page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: "Origen de la caja", exact: true }).click();
  await expect(page).toHaveURL(/\/companies\/COMP_0412#cash-truth$/);
  await expect(page.getByRole("heading", { name: "COMP_0412", exact: true })).toHaveCount(1);
  await expect(page.locator("#cash-truth")).toBeInViewport();
});

test("los enlaces de relaciones conservan contexto sin pisar el filtro de sociedad", async ({ page }) => {
  await page.goto("/groups/GROUP_0042?entity=COMP_0356");
  const list = page.getByRole("list", { name: "Tabla de sociedades", exact: true });
  await page.getByRole("button", { name: /Todas/ }).click();
  const row = list.getByRole("listitem").filter({ hasText: "COMP_0412" });
  await row.locator("summary").click();
  await row.getByRole("link", { name: "Ver en la red", exact: true }).click();
  await expect(page).toHaveURL(/\/groups\/GROUP_0042\/network\?/);
  const url = new URL(page.url());
  expect(url.searchParams.get("company")).toBe("COMP_0412");
  expect(url.searchParams.get("entity")).toBe("COMP_0356");
  await expect(page.getByRole("complementary", { name: "Detalle de la selección" }).getByRole("heading", { name: "COMP_0412", exact: true })).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: "Health Score", exact: true })).toHaveAttribute("href", "/companies/COMP_0356#health-score");
});

test("sin grupo se oculta el bloque; con JSON de grupo ausente se conserva el retorno", async ({ page }) => {
  await page.goto("/companies/COMP_9001");
  await openMenu(page);
  await expect(page.getByRole("button", { name: "Secciones de grupo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link")).toHaveCount(5);
  await closeMenu(page);
  await page.goto("/groups/GROUP_0087?entity=COMP_0655");
  await expect(page.getByRole("heading", { name: "Datos del grupo no disponibles.", exact: true })).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: "Health Score", exact: true })).toHaveAttribute("href", "/companies/COMP_0655#health-score");
  await closeMenu(page);
  await page.goto("/groups/GROUP_0042?entity=COMP_9001");
  await openMenu(page);
  await expect(page.getByRole("navigation", { name: "Secciones de empresa", exact: true }).getByRole("link", { name: "Health Score", exact: true })).toHaveAttribute("href", "/companies/COMP_0356#health-score");
});

test("escritorio permite contraer el lateral; móvil cierra con Escape y devuelve foco", async ({ page }, testInfo) => {
  await page.goto("/companies/COMP_0356");
  if (testInfo.project.name === "mobile") {
    const trigger = page.getByRole("button", { name: "Abrir navegación", exact: true });
    await trigger.click();
    await expect(page.getByRole("dialog", { name: "Navegación de empresa y grupo", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await expect(page.getByRole("dialog", { name: "Navegación de empresa y grupo", exact: true })).not.toBeVisible();
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe("hidden");
  } else {
    await page.getByRole("button", { name: "Contraer menú lateral", exact: true }).click();
    await expect(page.getByRole("button", { name: "Expandir menú lateral", exact: true })).toBeVisible();
    await page.getByRole("navigation", { name: "Vistas de inteligencia de grupo", exact: true }).getByRole("link", { name: "Red financiera", exact: true }).click();
    await expect(page.getByRole("button", { name: "Expandir menú lateral", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Expandir menú lateral", exact: true }).click();
    await expect(page.getByRole("button", { name: "Contraer menú lateral", exact: true })).toBeVisible();
  }
  for (const width of [320, 768, 981, 1100, 1280, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
