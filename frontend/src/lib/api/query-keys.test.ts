import { describe, expect, it } from "vitest";

import { queryKeys, serializeFilters, withQuery } from "@/lib/api/query-keys";

describe("query keys and filters", () => {
  it("serializes filters deterministically and keeps false values", () => {
    expect(serializeFilters({ status: "Mới tạo", limit: 50, only_anomalies: false })).toBe(
      "limit=50&only_anomalies=false&status=M%E1%BB%9Bi+t%E1%BA%A1o",
    );
    expect(serializeFilters({ only_anomalies: false, limit: 50, status: "Mới tạo" })).toBe(
      "limit=50&only_anomalies=false&status=M%E1%BB%9Bi+t%E1%BA%A1o",
    );
  });

  it("includes filter values in stable query keys", () => {
    expect(queryKeys.tickets({ priority: "Cao", status: "Mới tạo" })).toEqual(
      queryKeys.tickets({ status: "Mới tạo", priority: "Cao" }),
    );
    expect(queryKeys.tickets({ status: "Mới tạo" })).not.toEqual(
      queryKeys.tickets({ status: "Đã xử lý" }),
    );
  });

  it("builds query strings without empty values", () => {
    expect(withQuery("/assets", { asset_type: "", location: undefined })).toBe("/assets");
  });
});
