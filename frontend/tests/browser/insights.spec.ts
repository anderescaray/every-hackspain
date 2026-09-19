import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const id of ["COMP_0356", "COMP_0655", "COMP_1171"]) {
  test(`${id} has no automated accessibility violations`, async ({ page }, testInfo) => {
    await page.goto(`/companies/${id}`);
    await page.getByRole("checkbox", { name: "Show Health" }).check();
    await page.getByRole("checkbox", { name: "Show Health" }).uncheck();
    await page.screenshot({ path: testInfo.outputPath("company.png"), fullPage: true });
    await page.getByRole("region", { name: "Cash Truth", exact: true }).screenshot({ path: testInfo.outputPath("cash-truth.png") });
    await page.getByRole("region", { name: "Time Borrowed", exact: true }).screenshot({ path: testInfo.outputPath("time-borrowed.png") });
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => ({ html: node.html, issue: node.failureSummary })) }))).toEqual([]);
    await page.getByRole("button", { name: "View evidence: Cash Truth explanation", exact: true }).click();
    const evidence = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(evidence.violations).toEqual([]);
  });
}

for (const id of ["COMP_0356", "COMP_0655", "COMP_1171"]) {
  test(`${id} renders all insights without overflow or client errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const response = await page.goto(`/companies/${id}`);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: id, exact: true })).toBeVisible();
    await expect(page.getByText("Demo · Mock data")).toBeVisible();
    for (const name of ["Trajectory", "Cash Truth", "Time Borrowed", "What-if"]) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("Cash Truth correction, comparison and traceable modal", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const cash = page.getByRole("region", { name: "Cash Truth", exact: true });
  await expect(cash.getByText("−€86.7M", { exact: true })).toBeVisible();
  await expect(cash.getByText("+€25.6k", { exact: true }).first()).toBeVisible();
  await expect(cash.getByText("+€4.14M", { exact: true }).first()).toBeVisible();
  await expect(cash.getByText("False weakness. Real dependency.")).toBeVisible();
  const trigger = cash.getByRole("button", { name: "View evidence: Cash Truth explanation", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("DEMO-TX-001", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Mock evidence", { exact: false })).toBeVisible();
  await expect(dialog.getByRole("row")).toHaveCount(9);
  await expect(dialog.getByRole("button", { name: "Close evidence" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.querySelector("dialog")?.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await cash.getByRole("link", { name: "Explore COMP_0655" }).click();
  await expect(page.getByRole("heading", { name: "COMP_0655", exact: true })).toBeVisible();
});

test("Time Borrowed keeps punctuality distinct and switches AR/AP", async ({ page }) => {
  await page.goto("/companies/COMP_1171");
  const timing = page.getByRole("region", { name: "Time Borrowed", exact: true });
  await expect(timing.getByText("COUNTERPARTY_06105", { exact: true })).toBeVisible();
  await expect(timing.getByRole("heading", { name: "Punctuality improved. Cash conversion became slower." })).toBeVisible();
  await expect(timing.getByText("102", { exact: true })).toHaveCount(2);
  await expect(timing.getByText("81", { exact: true })).toBeVisible();
  await timing.getByText("How to read these clocks", { exact: false }).click();
  await expect(timing.getByText("Separate cohort medians", { exact: false })).toBeVisible();
  await timing.getByRole("button", { name: "View evidence: Customer payment timing", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("columnheader", { name: "Due date", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("row")).toHaveCount(7);
  await page.getByRole("button", { name: "Close evidence" }).click();
  await timing.getByRole("button", { name: "AP · Suppliers", exact: true }).click();
  await expect(timing.getByRole("button", { name: "AP · Suppliers", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(timing.getByText("Time to payment", { exact: true })).toBeVisible();
  await expect(timing.getByRole("heading", { name: "Less time received. Cash is needed earlier." })).toBeVisible();
  await timing.getByRole("button", { name: "AR · Customers", exact: true }).click();
  await expect(timing.getByText("COUNTERPARTY_06105", { exact: true })).toBeVisible();
});

test("trajectory can be explored by keyboard with optional Health", async ({ page }) => {
  await page.goto("/companies/COMP_0655");
  const trajectory = page.getByRole("region", { name: "Trajectory", exact: true });
  await trajectory.getByRole("checkbox", { name: "Show Health" }).check();
  const slider = trajectory.getByRole("slider", { name: "Explore month" });
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(slider).toHaveAttribute("aria-valuetext", "Sept 2024: Pulse 45, Health 50");
  await trajectory.getByText("View monthly values", { exact: true }).click();
  await expect(trajectory.getByRole("row")).toHaveCount(25);
});

test("alerts expand and provide evidence", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const alerts = page.getByRole("region", { name: "Prioritized alerts", exact: true });
  const summary = alerts.locator("summary").first();
  await expect(summary).toContainText("Liquidity dependency increasing");
  await summary.click();
  await alerts.getByRole("button", { name: "View evidence: Liquidity dependency increasing", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
});

test("what-if is mechanical, editable, resettable and separate from current Pulse", async ({ page }) => {
  await page.goto("/companies/COMP_0356");
  const scenario = page.getByRole("region", { name: "What-if", exact: true });
  await expect(scenario.getByTestId("scenario-pulse")).toHaveText("68");
  await expect(scenario.getByRole("button", { name: "Reset scenario" })).toBeDisabled();
  await scenario.getByRole("button", { name: "Try example" }).click();
  await expect(scenario.getByTestId("scenario-pulse")).toHaveText("74");
  await expect(scenario.getByText("Scenario, not forecast.", { exact: true }).first()).toBeVisible();
  const term = scenario.getByRole("slider", { name: "Customer payment term", exact: true });
  await term.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(term).toHaveValue("-16");
  await scenario.getByRole("button", { name: "Reset scenario" }).click();
  await expect(scenario.getByTestId("scenario-pulse")).toHaveText("68");
  await expect(term).toHaveValue("0");
  await page.goto("/companies/COMP_1171");
  await expect(page.getByRole("slider", { name: "Collection delay", exact: true })).toHaveAttribute("min", "0");
});

test("unknown companies show an honest not-found state", async ({ page }) => {
  await page.goto("/companies/COMP_9999");
  await expect(page.getByRole("heading", { name: "Company not available" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Cash Truth", exact: true })).not.toBeVisible();
});
