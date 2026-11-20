import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfidenceMeter, Notice, Button } from "../components/ui/ui";
import ResultView from "../components/diagnosis/ResultView";
import { ApiError } from "../lib/api";
import type { DiagnosisResult } from "../lib/types";

const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);

const base: DiagnosisResult = {
  id: null, saved: false, created_at: "2026-11-20T10:00:00Z", status: "confident", message: null, model_version: "v-test",
  latency_ms: 90, plant: null, diagnosis: null, alternatives: [], findings: [], ood: null,
  quality: { sharpness: 100, brightness: 120, warnings: [] }, image_url: null, heatmap_url: null, expert_help: [],
  notes: null, feedback: null, plant_id: null,
};

describe("ConfidenceMeter", () => {
  it("exposes the value as an accessible meter and colours by threshold", () => {
    const { container } = render(<ConfidenceMeter value={0.55} />);
    const m = screen.getByRole("meter");
    expect(m).toHaveAttribute("aria-valuenow", "55");
    expect(container.querySelector(".bg-warn-600")).not.toBeNull();
  });
});

describe("Button", () => {
  it("is disabled and busy while loading", async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Save</Button>);
    const b = screen.getByRole("button", { name: /save/i });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("aria-busy", "true");
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("Notice", () => {
  it("uses role=alert for errors", () => {
    render(<Notice tone="bad">Broken</Notice>);
    expect(screen.getByRole("alert")).toHaveTextContent("Broken");
  });
});

describe("ResultView", () => {
  it("never shows a diagnosis for an unknown image and explains why", () => {
    wrap(<ResultView r={{ ...base, status: "unknown", message: "This photo doesn't look like the plant images the model was trained on" }} />);
    expect(screen.getByText("Not recognised")).toBeInTheDocument();
    expect(screen.getByText(/doesn't look like the plant images/)).toBeInTheDocument();
    expect(screen.getByText(/No diagnosis/)).toBeInTheDocument();
  });

  it("offers plant candidates when the plant is unclear", async () => {
    const onTypePlant = vi.fn();
    wrap(<ResultView onTypePlant={onTypePlant} r={{ ...base, status: "needs_input", message: "Tell me the plant",
      plant: { source: "image", model_crop: "Tomato", confidence: 0.4, typed: null, info: null,
        candidates: [{ crop: "Tomato", probability: 0.4, info: null }, { crop: "Potato", probability: 0.35, info: null }] } }} />);
    await userEvent.click(screen.getByRole("button", { name: /Potato/ }));
    expect(onTypePlant).toHaveBeenCalledWith("Potato");
  });

  it("asks guests to create an account to save results", () => {
    wrap(<ResultView guest r={{ ...base, status: "tentative", message: "Possible match" }} />);
    expect(screen.getByText(/wasn't saved/)).toBeInTheDocument();
  });
});

describe("ApiError", () => {
  it("finds field errors", () => {
    const e = new ApiError(422, "validation_error", "bad", [{ field: "email", message: "Enter a valid email address." }]);
    expect(e.fieldError("email")).toMatch(/valid email/);
    expect(e.fieldError("name")).toBeUndefined();
  });
});
