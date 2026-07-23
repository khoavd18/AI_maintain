import { afterEach, describe, expect, it, vi } from "vitest";

import { inventoryApi } from "@/lib/api/inventory-endpoints";
import {
  inventoryBalanceSchema,
  stockOperationRequestSchema,
} from "@/lib/api/inventory-schemas";
import {
  balanceFixture,
  inventoryIds,
  movementFixture,
} from "@/test/inventory-fixtures";

describe("inventory API contract", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the caller-stable Idempotency-Key on stock writes", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn(async () => jsonResponse(movementFixture, 201));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      inventoryApi.receive(
        {
          part_id: inventoryIds.part,
          stock_location_id: inventoryIds.location,
          quantity: 3,
          business_reference: "DEMO-RECEIPT-001",
          occurred_at: null,
          reason: "Nhập kho phục vụ bảo trì",
          unit_cost_snapshot: 250000,
        },
        "inventory-receipt-stable-key",
      ),
    ).resolves.toMatchObject({ movement_number: "MOV-2026-000001" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/inventory/receipts",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Idempotency-Key": "inventory-receipt-stable-key",
        }),
      }),
    );
  });

  it("coerces PostgreSQL Decimal strings at the response boundary", () => {
    const parsed = inventoryBalanceSchema.parse({
      ...balanceFixture,
      on_hand_quantity: "3.000",
      reserved_quantity: "1.000",
      available_quantity: "2.000",
    });
    expect(parsed.on_hand_quantity).toBe(3);
    expect(parsed.available_quantity).toBe(2);
  });

  it("rejects zero and negative stock mutations before fetch", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      inventoryApi.receive(
        {
          part_id: inventoryIds.part,
          stock_location_id: inventoryIds.location,
          quantity: 0,
          business_reference: "DEMO-RECEIPT-002",
          occurred_at: null,
          reason: "Số lượng không hợp lệ",
          unit_cost_snapshot: null,
        },
        "inventory-invalid-quantity",
      ),
    ).rejects.toMatchObject({ code: "validation" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(
      stockOperationRequestSchema.safeParse({
        part_id: inventoryIds.part,
        stock_location_id: inventoryIds.location,
        quantity: -1,
        business_reference: "DEMO-RECEIPT-003",
        reason: "Số lượng không hợp lệ",
      }).success,
    ).toBe(false);
  });

  it("uses named atomic transfer and controlled adjustment endpoints", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000";
    const transferOut = {
      ...movementFixture,
      movement_type: "transfer_out",
      movement_type_display: "Chuyển kho ra",
      destination_location_id: inventoryIds.destination,
      destination_location_code: "KHO-DICH",
      transfer_group_id: "20000000-0000-4000-8000-000000000010",
    };
    const transferIn = {
      ...movementFixture,
      id: "20000000-0000-4000-8000-000000000011",
      movement_type: "transfer_in",
      movement_type_display: "Chuyển kho vào",
      stock_location_id: inventoryIds.destination,
      stock_location_code: "KHO-DICH",
      stock_location_name: "Kho đích",
      source_location_id: inventoryIds.location,
      source_location_code: "KHO-KT",
      transfer_group_id: transferOut.transfer_group_id,
    };
    const adjusted = {
      ...movementFixture,
      id: "20000000-0000-4000-8000-000000000012",
      movement_type: "adjustment_decrease",
      movement_type_display: "Điều chỉnh giảm",
    };
    const fetchMock = vi.fn(
      async (input: string | URL | Request) =>
        String(input).includes("/inventory/transfers")
          ? jsonResponse({
              transfer_group_id: transferOut.transfer_group_id,
              transfer_out: transferOut,
              transfer_in: transferIn,
            })
          : jsonResponse(adjusted),
    );
    vi.stubGlobal("fetch", fetchMock);

    await inventoryApi.transfer(
      {
        part_id: inventoryIds.part,
        source_stock_location_id: inventoryIds.location,
        destination_stock_location_id: inventoryIds.destination,
        quantity: 1,
        business_reference: "TRANSFER-TEST-001",
        occurred_at: null,
        reason: "Chuyển vật tư sang kho kỹ thuật",
      },
      "inventory-transfer-test",
    );
    await inventoryApi.adjust(
      {
        part_id: inventoryIds.part,
        stock_location_id: inventoryIds.location,
        quantity: 1,
        adjustment_type: "decrease",
        business_reference: "ADJUST-TEST-001",
        occurred_at: null,
        reason: "Điều chỉnh sau kiểm kê",
        supporting_note: "Đã đối chiếu biên bản kiểm kê",
        unit_cost_snapshot: null,
      },
      "inventory-adjust-test",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/inventory/transfers",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "inventory-transfer-test",
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/inventory/adjustments",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Idempotency-Key": "inventory-adjust-test",
        }),
      }),
    );
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
