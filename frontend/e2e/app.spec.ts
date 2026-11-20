import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";

const SAMPLE = path.resolve(process.cwd(), "public/samples/tomato-early-blight.jpg");
const uid = () => Math.random().toString(36).slice(2, 8);

async function axe(page: import("@playwright/test").Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = r.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.flatMap((v) => v.nodes.map((n) => `${v.id} ${n.target.join(" ")} :: ${(n.any[0]?.message ?? "").slice(0, 110)}`))).toEqual([]);
}

test("landing page: live demo runs the real model", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Know what's wrong");
  await page.getByRole("button", { name: /Analyse sample: Tomato, early blight/i }).click();
  await expect(page.getByText("Early blight", { exact: true }).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("meter")).toBeVisible();
  await axe(page);
});

test("register → diagnose with typed plant → history → report", async ({ page }) => {
  const email = `e2e-${uid()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Your name").fill("E2E Grower");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("green-field-2026");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app/);
  await page.goto("/app/diagnose");
  await page.getByRole("button", { name: /I know the plant/ }).click();
  await page.getByRole("combobox", { name: "Plant name" }).fill("tamatar");
  await page.getByRole("option", { name: /Tomato/ }).click();
  await page.locator('input[type=file][aria-label="Choose photo"]').setInputFiles(SAMPLE);
  await page.getByRole("button", { name: "Analyse photo" }).click();
  await expect(page.getByRole("heading", { name: "Early blight" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Named by you")).toBeVisible();
  await page.getByRole("tab", { name: "Treatment plan" }).click();
  await expect(page.getByText("Read before spraying")).toBeVisible();
  const pdf = page.getByRole("link", { name: /Download PDF report/ });
  const href = await pdf.getAttribute("href");
  const res = await page.request.get(href!);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  await page.goto("/app/diagnoses");
  await expect(page.getByText("Early blight").first()).toBeVisible();
});

test("guest gets a refusal, not a guess, for a non-plant image", async ({ page }) => {
  await page.goto("/try");
  await page.getByRole("button", { name: /Identify it from a photo/ }).click();
  const buf = Buffer.from(await (await page.request.get("/favicon.svg")).body());
  // A flat-colour PNG generated in the page is not a plant.
  const png = await page.evaluate(async () => {
    const c = document.createElement("canvas"); c.width = c.height = 300;
    const g = c.getContext("2d")!; g.fillStyle = "#3366cc"; g.fillRect(0, 0, 300, 300);
    return c.toDataURL("image/png").split(",")[1];
  });
  void buf;
  await page.locator('input[type=file][aria-label="Choose photo"]').setInputFiles({ name: "blue.png", mimeType: "image/png", buffer: Buffer.from(png, "base64") });
  await page.getByRole("button", { name: "Analyse photo" }).click();
  await expect(page.getByText(/Tell us the plant|Not recognised|No plant found|Inconclusive/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/wasn't saved/)).toBeVisible();
});

test("auth pages and disease library are accessible", async ({ page }) => {
  for (const url of ["/login", "/register", "/knowledge"]) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    await axe(page);
  }
  await page.goto("/knowledge");
  await page.getByLabel("Search").fill("yellow rust");
  await expect(page.getByText("Yellow (stripe) rust")).toBeVisible();
});

test("protected routes redirect to sign in", async ({ page }) => {
  await page.goto("/app/diagnoses");
  await expect(page).toHaveURL(/\/login\?next=/);
});
