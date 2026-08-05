"use client";

import { Search, RotateCcw, RefreshCw } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ErrorState,
  LoadingSkeleton,
  RetryButton,
} from "@/components/ui-states";
import {
  useInventoryBalancesQuery,
  useInventoryLocationsQuery,
  useInventoryOptionsQuery,
  useLowStockQuery,
} from "@/hooks/use-inventory";
import { getApiErrorMessage } from "@/lib/api/errors";
import {
  resolveStatusPresentation,
  stockStateStatusCatalog,
} from "@/lib/status-terminology";

import {
  BalanceTable,
} from "../components/inventory-common";
import {
  FilterSelect,
  Pagination,
  SectionHeading,
} from "../components/inventory-controls";

const all = "all";
const pageSize = 20;

export function BalanceWorkspace({ lowStockOnly }: { lowStockOnly: boolean }) {
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [locationId, setLocationId] = useState(all);
  const [state, setState] = useState(all);
  const [page, setPage] = useState(1);
  const locations = useInventoryLocationsQuery();
  const options = useInventoryOptionsQuery();
  const filters = {
    search: deferredSearch || undefined,
    stock_location_id: locationId === all ? undefined : locationId,
    stock_state: !lowStockOnly && state !== all ? state : undefined,
    page,
    page_size: pageSize,
  };
  const lowStockQuery = useLowStockQuery(filters, lowStockOnly);
  const balanceQuery = useInventoryBalancesQuery(filters, !lowStockOnly);
  const query = lowStockOnly ? lowStockQuery : balanceQuery;

  function reset() {
    setSearch("");
    setLocationId(all);
    setState(all);
    setPage(1);
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-white p-3 sm:p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_220px_200px_auto] lg:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="inventory-balance-search">Tìm vật tư</Label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                id="inventory-balance-search"
                className="pl-8"
                value={search}
                placeholder="Mã hoặc tên vật tư"
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
              />
            </div>
          </div>
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
          {!lowStockOnly && (
            <FilterSelect
              label="Trạng thái tồn"
              value={state}
              onChange={(value) => {
                setState(value);
                setPage(1);
              }}
              options={(options.data?.stock_states ?? []).map((item) => ({
                ...item,
                display_name: resolveStatusPresentation(
                  stockStateStatusCatalog,
                  item.code,
                  item.display_name,
                ).label,
              }))}
            />
          )}
          <Button type="button" variant="outline" onClick={reset}>
            <RotateCcw aria-hidden="true" />
            Đặt lại
          </Button>
        </div>
      </section>
      <section className="rounded-lg border bg-white">
        <SectionHeading
          title={lowStockOnly ? "Mã cần bổ sung" : "Số lượng theo vị trí"}
          description={
            query.data ? `${query.data.total} vị trí tồn kho` : "Đang đọc dữ liệu"
          }
          action={
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void query.refetch()}
            >
              <RefreshCw aria-hidden="true" />
              Làm mới
            </Button>
          }
        />
        {query.isPending ? (
          <div className="p-4">
            <LoadingSkeleton />
          </div>
        ) : query.isError ? (
          <ErrorState
            title="Chưa tải được tồn kho"
            description={getApiErrorMessage(query.error)}
            action={<RetryButton onClick={() => void query.refetch()} />}
          />
        ) : (
          <>
            <BalanceTable rows={query.data?.items ?? []} />
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
