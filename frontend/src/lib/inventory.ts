export function createInventoryIdempotencyKey(action: string): string {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `inventory-${action}-${suffix}`.slice(0, 100);
}

export function formatQuantity(
  value: number,
  symbol: string,
  precision = 3,
): string {
  return `${new Intl.NumberFormat("vi-VN", {
    maximumFractionDigits: precision,
  }).format(value)} ${symbol}`;
}

export function formatInventoryCost(
  value: number | null,
  currency: string | null,
): string {
  if (value === null || !currency) return "Không hiển thị";
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency,
    maximumFractionDigits: currency === "VND" ? 0 : 2,
  }).format(value);
}
