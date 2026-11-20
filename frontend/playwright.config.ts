import { defineConfig, devices } from "@playwright/test";

// E2E against a throwaway backend on :8010 (temp data dir, CPU inference) serving the built SPA.
const TMP = "/tmp/pd-e2e";
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8010", channel: process.env.PW_CHANNEL ?? "chrome", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], channel: process.env.PW_CHANNEL ?? "chrome" } },
  ],
  webServer: {
    command: `rm -rf ${TMP} && mkdir -p ${TMP}/extra/_sources && cd .. && PD_DATA_DIR=${TMP} PD_DB_URL=sqlite:///${TMP}/e2e.db PD_DEVICE=cpu PD_LLM=0 PD_GUEST_SCANS_PER_DAY=50 PD_ADMIN_EMAILS=admin@e2e.test .venv/bin/uvicorn app.server:app --port 8010`,
    url: "http://127.0.0.1:8010/api/v1/health/ready",
    timeout: 120_000,
    reuseExistingServer: false,
  },
});
