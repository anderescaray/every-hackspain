import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("el apoyo cambia de nombre según la pertenencia a un grupo", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  await expect(page.getByRole("group", { name: "Origen de la liquidez" }).getByRole("article", { name: "Apoyo intragrupo", exact: true })).toBeVisible();
  await page.goto("/companies/COMP_9001");
  await expect(page.locator("main > header").getByText("Empresa · Sin grupo")).toBeVisible();
  const cash = page.getByRole("region", { name: "Origen de la caja", exact: true });
  const origins = cash.getByRole("group", { name: "Origen de la liquidez" });
  await expect(origins.getByRole("article", { name: "Financiación o apoyo externo", exact: true })).toContainText("+315,6 mil €");
  await expect(origins.getByRole("article", { name: "Apoyo intragrupo", exact: true })).toHaveCount(0);
  await origins.getByRole("button", { name: "Ver evidencia: Financiación o apoyo externo", exact: true }).click();
  await expect(page.getByRole("dialog").getByText("Financiación o apoyo externo", { exact: true }).first()).toBeVisible();
  expect(await page.getByRole("dialog").textContent()).not.toMatch(/intragrupo/i);
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
});

test("sin apoyo no hay bloque y la ausencia de traslados es explícita", async ({ page }) => {
  await page.goto("/companies/COMP_9002");
  const cash = page.getByRole("region", { name: "Origen de la caja", exact: true });
  const origins = cash.getByRole("group", { name: "Origen de la liquidez" });
  await expect(origins.getByRole("article")).toHaveCount(2);
  await expect(origins.getByRole("article", { name: /apoyo/i })).toHaveCount(0);
  await expect(origins.getByRole("article", { name: "Generación operativa", exact: true })).toBeVisible();
  const treasury = cash.getByRole("region", { name: "Movimientos de tesorería" });
  await expect(treasury.getByRole("heading", { name: "No se han detectado movimientos entre cuentas propias", exact: true })).toBeVisible();
  await expect(treasury.getByText("Sin movimientos", { exact: true })).toBeVisible();
  await expect(treasury.getByText("transferidos", { exact: true })).toHaveCount(0);
  await expect(treasury.getByText("No disponible", { exact: true })).toHaveCount(0);
  await expect(treasury.getByText("Ver cuentas y transferencias", { exact: true })).toHaveCount(0);
  await cash.getByText("Ver desglose y movimientos brutos", { exact: true }).click();
  await expect(cash.getByRole("heading", { name: /Financiación o apoyo externo|Apoyo intragrupo/ })).toHaveCount(0);
  await page.goto("/companies/COMP_0655");
  const unavailable = page.getByRole("region", { name: "Movimientos de tesorería" });
  await expect(unavailable.getByText("Datos insuficientes", { exact: true })).toBeVisible();
  await expect(unavailable.getByText("La falta de información no significa que no haya movimientos entre cuentas.")).toBeVisible();
  await expect(unavailable.getByText("Sin movimientos", { exact: true })).toHaveCount(0);
});

for (const id of ["COMP_9001", "COMP_9002"]) {
  test(`${id}: estados dinámicos accesibles y responsive`, async ({ page }, testInfo) => {
    await page.goto(`/companies/${id}`);
    await page.getByRole("heading", { name: "Origen de la caja", exact: true }).waitFor();
    await page.getByRole("region", { name: "Origen de la caja", exact: true }).screenshot({ path: testInfo.outputPath("cash-states.png") });
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations.map((item) => ({ id: item.id, nodes: item.nodes.map((node) => node.failureSummary) }))).toEqual([]);
    for (const width of [320, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  });
}
