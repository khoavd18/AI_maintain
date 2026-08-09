import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { vi } from "vitest";

import OverviewPage from "@/app/page";
import { AnomalyWorkspace } from "@/components/anomaly-workspace";
import { AppShell } from "@/components/app-shell";
import { AssetBrowser } from "@/components/asset-browser";
import { AssetDetailView } from "@/components/asset-detail-view";
import { TicketWorkspace } from "@/components/ticket-workspace";
import { permissions } from "@/lib/auth";
import {
  anomalyFixture,
  assetCatalogFixture,
  assetDetailsFixture,
  assetOptionsFixture,
  assetProfileFixture,
  assetsFixture,
  kpiFixture,
  logFixture,
  locationFixture,
  preventiveFixture,
  recurringFixture,
  ticketsFixture,
} from "@/test/fixtures";
import {
  administratorTestUser,
  mockApi,
  renderWithQuery,
} from "@/test/test-utils";

const pushRoute = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushRoute, replace: vi.fn() }),
  usePathname: () => "/assets",
  useSearchParams: () => new URLSearchParams(),
}));

const assetManagementMocks = {
  "/assets/catalog": assetCatalogFixture,
  "/assets/options": assetOptionsFixture,
  "/locations": [locationFixture],
  "/assets": assetsFixture,
};

describe("live API screens", () => {
  it("renders overview values from mocked API responses", async () => {
    mockApi({
      "/assets": assetsFixture,
      "/tickets?limit=3": ticketsFixture,
      "/maintenance/kpis": kpiFixture,
      "/maintenance/preventive": preventiveFixture,
      "/work-orders/metrics": {
        as_of_date: "2026-04-30",
        total_work_orders: 5,
        by_status: {
          planned: 1,
          assigned: 1,
          in_progress: 1,
          on_hold: 0,
          completed: 1,
          verified: 1,
          cancelled: 0,
        },
        overdue_count: 2,
        upcoming_preventive_count: 1,
        completed_count: 1,
        verified_count: 1,
        completed_on_time_count: 1,
        technician_workload: [],
        data_notice: "Dữ liệu giao dịch hiện tại.",
      },
      "/inventory/metrics": {
        total_active_parts: 10,
        total_on_hand_units: 80,
        total_reserved_units: 12,
        total_available_units: 68,
        low_stock_parts: 2,
        out_of_stock_parts: 1,
        open_shortages: 1,
        work_orders_waiting_for_parts: 1,
        movements_by_type: {},
        data_notice: "Số dư kho hiện tại.",
      },
    });
    renderWithQuery(<OverviewPage />);

    expect(await screen.findAllByText("GENERATOR_002")).not.toHaveLength(0);
    expect(screen.getByText("63.89")).toBeInTheDocument();
    expect(screen.getByText("Sự cố cần xử lý")).toBeInTheDocument();
    expect(screen.getByText("Lệnh công việc quá hạn")).toBeInTheDocument();
    expect(screen.getByText("Phụ tùng sắp hết hoặc hết")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tình trạng lệnh công việc" })).toBeInTheDocument();
  });

  it("renders and filters the live asset list", async () => {
    mockApi({
      ...assetManagementMocks,
      "/assets/catalog": (input: string | URL | Request) => {
        const query = new URL(input instanceof Request ? input.url : String(input)).searchParams.get("search");
        const items = query
          ? assetCatalogFixture.items.filter((asset) => `${asset.asset_id} ${asset.asset_name}`.includes(query))
          : assetCatalogFixture.items;
        return { ...assetCatalogFixture, items, total: items.length };
      },
    });
    renderWithQuery(<AssetBrowser />);

    expect(await screen.findAllByText("GENERATOR_002")).not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Tìm thiết bị"), { target: { value: "HVAC_001" } });
    await waitFor(() => expect(screen.queryByText("Máy phát điện dự phòng 002")).not.toBeInTheDocument());
    expect(screen.getAllByText("HVAC_001").length).toBeGreaterThan(0);
  });

  it("keeps missing optional analytics visibly empty", async () => {
    mockApi({
      ...assetManagementMocks,
      "/assets/catalog": { ...assetCatalogFixture, items: [assetCatalogFixture.items[1]], total: 1 },
      "/assets": [{ ...assetsFixture[1], risk_score: null, risk_level_code: null, risk_level: null, maintenance_status: null, maintenance_status_display: null }],
    });
    renderWithQuery(<AssetBrowser />);

    expect((await screen.findAllByText("Chưa có chỉ số")).length).toBeGreaterThan(0);
    expect(screen.queryByText("2026-07-02")).not.toBeInTheDocument();
  });

  it("renders live asset details and handles an unknown asset", async () => {
    mockApi({
      "/assets/GENERATOR_002/details?limit=20": assetDetailsFixture,
      "/assets/GENERATOR_002/profile": assetProfileFixture,
      "/assets/options": assetOptionsFixture,
    });
    const first = renderWithQuery(<AssetDetailView assetId="GENERATOR_002" />);
    expect(await screen.findByText("Máy phát điện dự phòng 002")).toBeInTheDocument();
    expect(screen.getByText("63.89")).toBeInTheDocument();
    expect(screen.getByText("Điều cần chú ý")).toBeInTheDocument();
    first.unmount();

    mockApi({
      "/assets/UNKNOWN_999/details?limit=20": { status: 404, body: { detail: "missing" } },
      "/assets/UNKNOWN_999/profile": { status: 404, body: { detail: "missing" } },
    });
    renderWithQuery(<AssetDetailView assetId="UNKNOWN_999" />);
    expect(await screen.findByText("Không tìm thấy UNKNOWN_999")).toBeInTheDocument();
  });

  it("keeps transactional asset management available when analytics is unavailable", async () => {
    mockApi({
      "/assets/GENERATOR_002/profile": assetProfileFixture,
      "/assets/GENERATOR_002/details?limit=20": { status: 503, body: { detail: "analytics unavailable" } },
      "/assets/options": assetOptionsFixture,
    });
    renderWithQuery(<AssetDetailView assetId="GENERATOR_002" />);

    expect(await screen.findByText("Hồ sơ kỹ thuật và lifecycle")).toBeInTheDocument();
    expect(await screen.findByText("Kết quả phân tích chưa sẵn sàng")).toBeInTheDocument();
    expect(screen.getByText("Cummins")).toBeInTheDocument();
  });

  it("renders tickets from the API with the live workflow entry point", async () => {
    mockApi({
      "/tickets?limit=1000": ticketsFixture,
      "/assets": assetsFixture,
      "/maintenance/logs?limit=1000": [logFixture],
    });
    renderWithQuery(<TicketWorkspace />);

    expect(await screen.findAllByText("TCK-000041")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Tạo ticket" })).toBeEnabled();
    expect(screen.getByText(/ticket phù hợp/)).toBeInTheDocument();
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

  it("keeps technical service diagnostics out of the everyday shell", () => {
    renderWithQuery(
      <AppShell><div>Nội dung</div></AppShell>,
      {
        ...administratorTestUser,
        permissions: administratorTestUser.permissions.filter(
          (permission) => permission !== permissions.notificationsRead,
        ),
      },
    );

    expect(screen.getAllByText("Bảo trì thiết bị").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Công việc").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Thiết lập & quản trị").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Tìm nhanh chức năng")).toBeInTheDocument();
    expect(screen.getAllByText("Thêm nhanh").length).toBeGreaterThan(0);
    expect(screen.queryByText(/API:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/RAG:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/synthetic/i)).not.toBeInTheDocument();
  });

  it("shows empty and safe 503 states", async () => {
    mockApi({ ...assetManagementMocks, "/assets/catalog": { ...assetCatalogFixture, items: [], total: 0, total_pages: 0 }, "/assets": [] });
    const empty = renderWithQuery(<AssetBrowser />);
    expect(await screen.findByText("Không tìm thấy thiết bị")).toBeInTheDocument();
    empty.unmount();

    mockApi({ ...assetManagementMocks, "/assets/catalog": { status: 503, body: { detail: "D:\\secret\\risk.csv" } } });
    renderWithQuery(<AssetBrowser />);
    expect(await screen.findByText("Chưa tải được danh sách thiết bị")).toBeInTheDocument();
    expect(screen.queryByText(/FastAPI/)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret/)).not.toBeInTheDocument();
  });
});
