import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("dos cuentas propias se distinguen de otra sociedad y el bruto no es caja nueva", async ({ page }, testInfo) => {
  await page.goto("/companies/COMP_0356");
  await page.getByText("Ver cuentas y transferencias", { exact: true }).click();
  const section = page.getByRole("region", { name: "Cuentas y transferencias", exact: true });
  await section.getByRole("button", { name: "Entre cuentas propias", exact: true }).click();
  await expect(section.getByRole("article")).toHaveCount(1);
  const transfer = section.getByRole("article", { name: "Entre cuentas propias", exact: true });
  await expect(transfer.getByText("ACCOUNT_0356_A", { exact: true })).toBeVisible();
  await expect(transfer.getByText("ACCOUNT_0356_B", { exact: true })).toBeVisible();
  await expect(transfer.getByText("COMP_0356", { exact: true })).toHaveCount(2);
  await expect(transfer.getByText("2,5 M€", { exact: true })).toBeVisible();
  await expect(transfer.getByText("5 M€", { exact: true })).toBeVisible();
  await expect(transfer.getByText("0 €", { exact: true })).toBeVisible();
  await expect(transfer.getByText("Salida y entrada emparejadas", { exact: true })).toBeVisible();
  await section.screenshot({ path: testInfo.outputPath("cuentas-propias.png") });
  await transfer.getByRole("button", { name: "Ver evidencia: Transferencia: Entre cuentas propias", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("row")).toHaveCount(3);
  await expect(dialog.getByText("DEMO-TX-001", { exact: true })).toBeVisible();
  await expect(dialog.getByText("DEMO-TX-002", { exact: true })).toBeVisible();
  await expect(dialog.getByText("DEMO-TX-007", { exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("columnheader", { name: "Cuenta y titular", exact: true })).toBeVisible();
  await expect(dialog.getByText("Cuenta operativa", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Cuenta de tesorería", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
  await section.getByRole("button", { name: "Entre empresas del grupo", exact: true }).click();
  const group = section.getByRole("article", { name: "Entre empresas del grupo", exact: true });
  await expect(group.getByText("COMP_0007", { exact: true })).toBeVisible();
  await expect(group.getByText("COMP_0356", { exact: true })).toBeVisible();
  await expect(group.getByText("+600 mil €", { exact: true })).toBeVisible();
  await expect(group.getByText("Solo un tramo observado", { exact: true })).toBeVisible();
  await group.getByRole("button", { name: "Ver evidencia: Transferencia: Entre empresas del grupo", exact: true }).click();
  await expect(dialog.getByRole("row")).toHaveCount(2);
  await expect(dialog.getByText("DEMO-TX-007", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
});

test("sin titularidad o muestras no se presume apoyo ni neto cero", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  await page.getByText("Ver cuentas y transferencias", { exact: true }).click();
  const section = page.getByRole("region", { name: "Cuentas y transferencias", exact: true });
  await section.getByRole("button", { name: "Origen o destino sin identificar", exact: true }).click();
  const transfer = section.getByRole("article");
  await expect(transfer.getByText("Cuenta no identificada", { exact: true })).toBeVisible();
  await expect(transfer.locator("dd").last()).toHaveText("No identificado");
  await section.getByRole("button", { name: "Con terceros", exact: true }).click();
  await expect(section.getByRole("article")).toHaveCount(0);
  await expect(section.getByText("No hay muestras suministradas para este filtro.", { exact: false })).toBeVisible();
  await page.goto("/companies/COMP_0655");
  await page.getByText("Ver cuentas y transferencias", { exact: true }).click();
  await expect(page.getByRole("region", { name: "Cuentas y transferencias", exact: true }).getByText("Detalle por cuentas todavía no disponible.", { exact: false })).toBeVisible();
});

test("registro de cuentas explica el titular y conserva accesibilidad y responsive", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  await page.getByText("Ver cuentas y transferencias", { exact: true }).click();
  const section = page.getByRole("region", { name: "Cuentas y transferencias", exact: true });
  await section.getByText("Ver cuentas y titularidad", { exact: false }).click();
  const registry = section.getByRole("region", { name: "Registro de cuentas y titularidad" });
  await expect(registry.getByRole("row")).toHaveCount(4);
  await expect(registry.getByText("Registro de cuentas y sociedades de ejemplo", { exact: false })).toBeVisible();
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations.map((item) => ({ id: item.id, nodes: item.nodes.map((node) => node.failureSummary) }))).toEqual([]);
  for (const width of [320, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
