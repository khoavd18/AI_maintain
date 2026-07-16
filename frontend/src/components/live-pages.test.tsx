import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import OverviewPage from "@/app/page";
import { AnomalyWorkspace } from "@/components/anomaly-workspace";
import { AppShell } from "@/components/app-shell";
import { AssetBrowser } from "@/components/asset-browser";
import { AssetDetailView } from "@/components/asset-detail-view";
import { TicketWorkspace } from "@/components/ticket-workspace";
import {
  anomalyFixture,
  assetDetailsFixture,
  assetsFixture,
  healthFixture,
  kpiFixture,
  preventiveFixture,
  recurringFixture,
  summaryFixture,
  ticketsFixture,
} from "@/test/fixtures";
import { mockApi, renderWithQuery } from "@/test/test-utils";

describe("live read-only screens", () => {
  it("renders overview values from mocked API responses", async () => {
    mockApi({
      "/assets": assetsFixture,
      "/tickets?limit=1000": ticketsFixture,
      "/maintenance/kpis": kpiFixture,
      "/maintenance/preventive": preventiveFixture,
    });
    renderWithQuery(<OverviewPage />);

    expect(await screen.findAllByText("GENERATOR_002")).not.toHaveLength(0);
    expect(screen.getByText("63.89")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });

  it("renders and filters the live asset list", async () => {
    mockApi({ "/assets": assetsFixture });
    renderWithQuery(<AssetBrowser />);

    expect(await screen.findAllByText("GENERATOR_002")).not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Tìm thiết bị"), { target: { value: "HVAC_001" } });
    await waitFor(() => expect(screen.queryByText("Máy phát điện dự phòng 002")).not.toBeInTheDocument());
    expect(screen.getAllByText("HVAC_001").length).toBeGreaterThan(0);
  });

  it("keeps missing optional analytics visibly empty", async () => {
    mockApi({
      "/assets": [
        {
          ...assetsFixture[1],
          risk_score: null,
          risk_level_code: null,
          risk_level: null,
          maintenance_status: null,
          maintenance_status_display: null,
        },
      ],
    });
    renderWithQuery(<AssetBrowser />);

    expect((await screen.findAllByText("Chưa có risk")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Chưa có lịch").length).toBeGreaterThan(0);
  });

  it("renders live asset details and handles an unknown asset", async () => {
    mockApi({
      "/assets/GENERATOR_002/details?limit=20": assetDetailsFixture,
    });
    const first = renderWithQuery(<AssetDetailView assetId="GENERATOR_002" />);
    expect(await screen.findByText("Máy phát điện dự phòng 002")).toBeInTheDocument();
    expect(screen.getByText("63.89")).toBeInTheDocument();
    expect(screen.getByText("Dữ liệu và yếu tố đo được")).toBeInTheDocument();
    first.unmount();

    mockApi({
      "/assets/UNKNOWN_999/details?limit=20": { status: 404, body: { detail: "missing" } },
    });
    renderWithQuery(<AssetDetailView assetId="UNKNOWN_999" />);
    expect(await screen.findByText("Không tìm thấy UNKNOWN_999")).toBeInTheDocument();
  });

  it("renders tickets from the API without enabled write controls", async () => {
    mockApi({ "/tickets?limit=1000": ticketsFixture, "/assets": assetsFixture });
    renderWithQuery(<TicketWorkspace />);

    expect(await screen.findAllByText("TCK-000041")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Tạo ticket (sắp kết nối)" })).toBeDisabled();
    expect(screen.getByText("Live API · chỉ đọc")).toBeInTheDocument();
  });

  it("renders anomaly events and recurring issues from the API", async () => {
    mockApi({
      "/assets/anomalies?limit=1000&only_anomalies=true": [anomalyFixture],
      "/maintenance/recurring-issues?recurrence_flag=true": [recurringFixture],
    });
    renderWithQuery(<AnomalyWorkspace />);

    expect(await screen.findAllByText("Điện năng tiêu thụ / Thời gian vận hành")).not.toHaveLength(0);
    expect(screen.getAllByText("Lỗi làm lạnh").length).toBeGreaterThan(0);
  });

  it("shows API health independently from RAG status", async () => {
    mockApi({ "/health": healthFixture, "/summary": summaryFixture });
    renderWithQuery(<AppShell><div>Nội dung</div></AppShell>);

    expect(await screen.findByText("API: đã kết nối")).toBeInTheDocument();
    expect(screen.getByText("RAG: chưa kết nối")).toBeInTheDocument();
    expect(screen.getByText("Dữ liệu synthetic")).toBeInTheDocument();
  });

  it("shows empty and safe 503 states", async () => {
    mockApi({ "/assets": [] });
    const empty = renderWithQuery(<AssetBrowser />);
    expect(await screen.findByText("Không tìm thấy thiết bị")).toBeInTheDocument();
    empty.unmount();

    mockApi({ "/assets": { status: 503, body: { detail: "D:\\secret\\risk.csv" } } });
    renderWithQuery(<AssetBrowser />);
    expect(await screen.findByText("Chưa tải được danh mục thiết bị")).toBeInTheDocument();
    expect(screen.getByText(/batch analytics/)).toBeInTheDocument();
    expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
  });
});
