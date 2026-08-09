"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryLocationsQuery,
  useInventoryMovementsQuery,
  useInventoryOptionsQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";

import {
  MovementTable,
} from "../components/inventory-common";
import {
  FilterSelect,
  Pagination,
  SectionHeading,
} from "../components/inventory-controls";

const all = "all";
const pageSize = 20;

export function MovementWorkspace() {
  const [type, setType] = useState(all);
  const [locationId, setLocationId] = useState(all);
  const [page, setPage] = useState(1);
  const options = useInventoryOptionsQuery();
  const locations = useInventoryLocationsQuery();
  const query = useInventoryMovementsQuery({
    movement_type: type === all ? undefined : type,
    stock_location_id: locationId === all ? undefined : locationId,
    page,
    page_size: pageSize,
  });
  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Loại biến động"
            value={type}
            onChange={(value) => {
              setType(value);
              setPage(1);
            }}
            options={options.data?.movement_types ?? []}
          />
          <FilterSelect
            label="Vị trí kho"
            value={locationId}
            onChange={(value) => {
              setLocationId(value);
              setPage(1);
            }}
            options={(locations.data ?? []).map((item) => ({
              code: item.id,
              display_name: `${item.code} · ${item.name}`,
            }))}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setType(all);
              setLocationId(all);
              setPage(1);
            }}
          >
            <RotateCcw aria-hidden="true" />
            Đặt lại
          </Button>
        </div>
      </section>
      <section className="rounded-lg border bg-white">
        <SectionHeading
          title="Lịch sử biến động"
          description={`${query.data?.total ?? 0} lần thay đổi; lịch sử không thể sửa hoặc xóa.`}
        />
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được lịch sử kho"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : (
          <>
            <MovementTable rows={query.data?.items ?? []} />
            <Pagination
              page={page}
              totalPages={query.data?.total_pages ?? 0}
              onPage={setPage}
            />
          </>
        )}
      </section>
    </div>
  );
}
