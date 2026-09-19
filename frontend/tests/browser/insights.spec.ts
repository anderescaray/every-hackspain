import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const untranslated = /Cash Truth|Time Borrowed|View evidence|Scenario, not forecast|Pulse Score|Current Pulse|Stability|Deteriorating|Improving|Mock data|Not identified|supporting records|Time to cash|Payment term|Late payment|\bdays\b/;

for (const id of ["COMP_0356", "COMP_0655", "COMP_1171"]) {
  test(`${id}: accesibilidad, español y capturas responsive`, async ({ page }, testInfo) => {
    await page.goto(`/companies/${id}`);
    await page.getByRole("slider", { name: "Explorar mes" }).fill("23");
    await page.screenshot({ path: testInfo.outputPath("company.png"), fullPage: true });
    await page.getByRole("region", { name: "Estado financiero global", exact: true }).screenshot({ path: testInfo.outputPath("health-score.png") });
    await page.getByRole("region", { name: "Origen de la caja", exact: true }).screenshot({ path: testInfo.outputPath("cash-truth.png") });
    await page.getByRole("region", { name: "Tiempo financiado", exact: true }).screenshot({ path: testInfo.outputPath("time-borrowed.png") });
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => ({ html: node.html, issue: node.failureSummary })) }))).toEqual([]);
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    expect(await page.locator("main").textContent()).not.toMatch(untranslated);
    await page.getByRole("button", { name: "Ver evidencia: Origen de la caja", exact: true }).click();
    expect(await page.getByRole("dialog").textContent()).not.toMatch(untranslated);
    const evidence = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(evidence.violations).toEqual([]);
  });

  test(`${id}: todas las secciones, sin desbordamiento ni errores de cliente`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const response = await page.goto(`/companies/${id}`);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: id, exact: true })).toBeVisible();
    await expect(page.getByText("Demo · Datos de ejemplo")).toBeVisible();
    for (const name of ["Tendencia", "Origen de la caja", "Tiempo financiado", "Simulador de escenarios"]) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("una puntuación protagonista, cuatro dimensiones y confianza separada", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const header = page.locator("main > header");
  await expect(header.getByRole("heading", { name: "Health Score", exact: true })).toHaveCount(1);
  await expect(header.getByTestId("health-score")).toHaveText("72");
  await expect(header.getByText("Confianza del análisis:", { exact: false })).toContainText("Alta");
  await expect(header.getByText("Cobertura de datos: 88 %")).toBeVisible();
  await expect(header.getByText("Señales de presión y dependencia de apoyo", { exact: true })).toBeVisible();
  await expect(header.locator("dt")).toHaveCount(4);
  await expect(header.locator("dd strong")).toHaveText(["72", "72", "72", "72"]);
  expect(await header.getByTestId("health-score").evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThan(70);
  expect(await header.locator("dd strong").first().evaluate((node) => parseFloat(getComputedStyle(node).fontSize))).toBeLessThan(25);
  await header.getByText("Cómo se calcula", { exact: false }).click();
  await expect(header.getByText("15 % Momentum + 40 % Generación de caja + 25 % Resiliencia + 20 % Deuda.", { exact: false })).toBeVisible();
  expect(await header.textContent()).not.toMatch(/Pulse Score|Stability|Estabilidad/);
});

test("origen de liquidez separado de movimientos de tesorería", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const cash = page.getByRole("region", { name: "Origen de la caja", exact: true });
  const origins = cash.getByRole("group", { name: "Origen de la liquidez", exact: true });
  await expect(origins.getByRole("article", { name: "Generación operativa", exact: true }).getByText("+25,6 mil €", { exact: true })).toBeVisible();
  await expect(origins.getByRole("article", { name: "Apoyo intragrupo", exact: true }).getByText("+4,14 M€", { exact: true })).toBeVisible();
  await expect(origins.getByRole("article", { name: "Origen no identificado", exact: true }).getByText("210 mil €", { exact: true })).toBeVisible();
  await expect(origins.getByRole("article")).toHaveCount(3);
  const treasury = cash.getByRole("region", { name: "Movimientos de tesorería", exact: true });
  await expect(treasury.getByRole("heading", { name: "Circulación entre cuentas propias", exact: true })).toBeVisible();
  await expect(treasury.getByText("86,7 M€", { exact: true })).toBeVisible();
  await expect(treasury.getByText("transferidos", { exact: true })).toBeVisible();
  await expect(treasury.getByText("34 traslados identificados", { exact: true })).toBeVisible();
  await expect(origins.getByText("86,7 M€", { exact: true })).toHaveCount(0);
  await expect(treasury.getByRole("region", { name: "Cuentas y transferencias", exact: true })).not.toBeVisible();
  await expect(cash.getByRole("article", { name: "Lo que solo se mueve", exact: true })).toHaveCount(0);
  await expect(cash.getByRole("button", { name: "Ver evidencia: Lo que solo se mueve", exact: true })).toHaveCount(0);
  expect(await cash.textContent()).not.toMatch(/Antes de separar|Después de separar|Falsa debilidad|Cómo interpretar la corrección/);
  await expect(cash.getByText("Poca caja del negocio. Mucho apoyo del grupo.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /caja negra/i })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Biblioteca de evidencia" })).toHaveCount(0);
  await cash.getByText("Ver desglose y movimientos brutos", { exact: true }).click();
  await expect(cash.getByText("179,05 M€", { exact: true })).toBeVisible();
  const trigger = cash.getByRole("button", { name: "Ver evidencia: Origen de la caja", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("DEMO-TX-001", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("row")).toHaveCount(9);
  await expect(dialog.getByRole("button", { name: "Cerrar evidencia" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.querySelector("dialog")?.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await cash.getByRole("link", { name: "Explorar COMP_0655" }).click();
  await expect(page.getByRole("heading", { name: "COMP_0655", exact: true })).toBeVisible();
  const missingTreasury = page.getByRole("region", { name: "Movimientos de tesorería", exact: true });
  await expect(missingTreasury.getByText("No disponible", { exact: true })).toBeVisible();
  await expect(missingTreasury.getByText("No se deduce este importe", { exact: false })).toBeVisible();
  await expect(missingTreasury.getByText("1,2 M€", { exact: true })).toHaveCount(0);
});

test("tiempo financiado: puntualidad independiente y selector AR/AP", async ({ page }) => {
  await page.goto("/companies/COMP_1171");
  const timing = page.getByRole("region", { name: "Tiempo financiado", exact: true });
  await expect(timing.getByText("COUNTERPARTY_06105", { exact: true })).toBeVisible();
  await expect(timing.getByRole("heading", { name: "Más puntualidad. Más tiempo hasta convertir la venta en caja." })).toBeVisible();
  await expect(timing.getByText("102", { exact: true })).toHaveCount(2);
  for (const value of ["62", "81", "20", "0"]) await expect(timing.getByText(value, { exact: true })).toBeVisible();
  await timing.getByText("Cómo interpretar los tiempos", { exact: false }).click();
  await expect(timing.getByText("Son medianas independientes", { exact: false })).toBeVisible();
  await timing.getByRole("button", { name: "Ver evidencia: Plazos y cobros de clientes", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("columnheader", { name: "Vencimiento", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("row")).toHaveCount(7);
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
  await timing.getByRole("button", { name: "Proveedores · AP", exact: true }).click();
  await expect(timing.getByRole("button", { name: "Proveedores · AP", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(timing.getByText("Tiempo hasta pago", { exact: true })).toBeVisible();
  await expect(timing.getByRole("heading", { name: "Menos plazo recibido. La caja se necesita antes." })).toBeVisible();
  await timing.getByRole("button", { name: "Clientes · AR", exact: true }).click();
  await expect(timing.getByText("COUNTERPARTY_06105", { exact: true })).toBeVisible();
});

test("tendencia del Health Score: teclado y 24 meses en tabla", async ({ page }) => {
  await page.goto("/companies/COMP_0655");
  const trajectory = page.getByRole("region", { name: "Tendencia", exact: true });
  const slider = trajectory.getByRole("slider", { name: "Explorar mes" });
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(slider).toHaveAttribute("aria-valuetext", "sept 2024: Health Score 59");
  await trajectory.getByText("Ver valores mensuales", { exact: true }).click();
  await expect(trajectory.getByRole("row")).toHaveCount(25);
});

test("alertas priorizadas desplegables con evidencia", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const alerts = page.getByRole("region", { name: "Alertas priorizadas", exact: true });
  const summary = alerts.locator("summary").first();
  await expect(summary).toContainText("Aumenta la dependencia de liquidez");
  await summary.click();
  await alerts.getByRole("button", { name: "Ver evidencia: Aumenta la dependencia de liquidez", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
});

test("crecimiento bajo presión afecta dimensiones, no añade otro score", async ({ page }) => {
  await page.goto("/companies/COMP_1171");
  const drivers = page.getByRole("region", { name: "Factores del Health Score" });
  await expect(drivers.getByRole("heading", { name: "Crecimiento bajo presión", exact: true })).toBeVisible();
  await drivers.getByRole("button", { name: "Ver evidencia: Crecimiento bajo presión", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("rowheader", { name: "Facturación", exact: true })).toBeVisible();
  await expect(dialog.getByRole("rowheader", { name: "Conversión de ventas a caja", exact: true })).toBeVisible();
  await expect(dialog.getByText("no una relación causal demostrada", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar evidencia" }).click();
});

test("simulador: solo resultados precalculados, sin interpolación y con reset", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const scenario = page.getByRole("region", { name: "Simulador de escenarios", exact: true });
  await expect(scenario.getByTestId("scenario-health-score")).toHaveText("72");
  await expect(scenario.getByRole("button", { name: "Restablecer escenario" })).toBeDisabled();
  await scenario.getByRole("button", { name: "Probar ejemplo" }).click();
  await expect(scenario.getByTestId("scenario-health-score")).toHaveText("78");
  await expect(scenario.getByText("Escenario, no predicción.", { exact: true }).first()).toBeVisible();
  const term = scenario.getByRole("slider", { name: "Plazo acordado con clientes", exact: true });
  await term.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(term).toHaveValue("-16");
  await expect(scenario.getByTestId("scenario-health-score")).toHaveText("—");
  await expect(scenario.getByText("No hay un escenario precalculado", { exact: false })).toBeVisible();
  await scenario.getByRole("combobox", { name: "Escenarios disponibles" }).selectOption("less-support");
  await expect(scenario.getByTestId("scenario-health-score")).toHaveText("71");
  await scenario.getByRole("button", { name: "Restablecer escenario" }).click();
  await expect(scenario.getByTestId("scenario-health-score")).toHaveText("72");
  await expect(term).toHaveValue("0");
  await expect(page.getByTestId("health-score")).toHaveText("72");
  await page.goto("/companies/COMP_1171");
  await expect(page.getByRole("slider", { name: "Retraso en los cobros", exact: true })).toHaveAttribute("min", "0");
});

test("sin JSON: estado limpio incluso para los casos conocidos, nunca datos falsos", async ({ page }) => {
  for (const id of ["COMP_0356", "COMP_0655", "COMP_1171", "COMP_9999"]) {
    await page.goto(`http://127.0.0.1:3108/companies/${id}`);
    await expect(page.getByRole("heading", { name: "Datos de análisis todavía no disponibles." })).toBeVisible();
    await expect(page.getByTestId("health-score")).toHaveCount(0);
    await expect(page.getByText("Demo · Datos de ejemplo")).toHaveCount(0);
  }
});

test("JSON inválido e identificador inválido tienen estados honestos en español", async ({ page }) => {
  await page.goto("/companies/COMP_9998");
  await expect(page.getByRole("heading", { name: "Los datos de análisis necesitan revisión." })).toBeVisible();
  await expect(page.getByTestId("health-score")).toHaveCount(0);
  await page.goto("/companies/invalid");
  await expect(page.getByRole("heading", { name: "Empresa no disponible" })).toBeVisible();
});

test("sin desbordamiento en móvil estrecho y tablet", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  for (const width of [320, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});
