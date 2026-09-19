import { expect, test } from "@playwright/test";

for (const scenario of [
  { id: "COMP_0356", total: "4.165.600 €", operating: "25.600 €", support: "4.140.000 €", supportLabel: "Apoyo intragrupo" },
  { id: "COMP_9001", total: "4.165.600 €", operating: "3.850.000 €", support: "315.600 €", supportLabel: "Financiación o apoyo externo" },
  { id: "COMP_9002", total: "3.850.000 €", operating: "3.850.000 €", support: "0 €", supportLabel: "Sin apoyo identificado" },
]) {
  test(`${scenario.id}: el total aparece primero y explica sus dos sumandos`, async ({ page }, testInfo) => {
    await page.goto(`/companies/${scenario.id}#cash-truth`);
    const cash = page.getByRole("region", { name: "Origen de la caja", exact: true });
    const total = cash.getByRole("group", { name: "Total de caja neta identificada", exact: true });
    await expect(total.getByTestId("identified-cash-total")).toHaveText(scenario.total);
    await expect(total.getByTestId("cash-total-operating")).toHaveText(scenario.operating);
    await expect(total.getByTestId("cash-total-support")).toHaveText(scenario.support);
    await expect(total.getByText(scenario.supportLabel, { exact: true })).toBeVisible();
    await expect(total.getByText("=", { exact: true })).toBeVisible();
    await expect(total.getByText("+", { exact: true })).toBeVisible();
    await expect(cash.getByText("No es el saldo bancario disponible.", { exact: false })).toBeVisible();
    expect(await cash.locator('[data-testid="identified-cash-total"]').evaluate((node) => {
      const sources = node.closest("section")?.querySelector('[aria-label="Origen de la liquidez"]');
      return Boolean(sources && (node.compareDocumentPosition(sources) & Node.DOCUMENT_POSITION_FOLLOWING));
    })).toBe(true);
    await total.screenshot({ path: testInfo.outputPath("cash-total.png") });
    for (const width of [320, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  });
}
