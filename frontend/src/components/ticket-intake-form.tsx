"use client";

import Link from "next/link";
import { CheckCircle2, Loader2, TicketPlus } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  TicketOperationsPriorityBadge,
} from "@/components/ticket-operations-badges";
import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import { useAssetsQuery } from "@/hooks/use-api-queries";
import {
  useTicketingOptionsQuery,
  useTicketIntakeMutation,
  useTicketPriorityPreviewQuery,
} from "@/hooks/use-ticketing";
import { getApiErrorMessage, UserSafeApiError } from "@/lib/api/errors";
import type { AssetOverviewRecord } from "@/lib/api/schemas";
import {
  ticketIntakeRequestSchema,
  type TicketImpact,
  type TicketIntakeRequest,
  type TicketUrgency,
} from "@/lib/api/ticketing-schemas";
import { permissions } from "@/lib/auth";
import { zodFieldErrors } from "@/lib/workflow";

interface TicketIntakeFormProps {
  initialAssetId?: string;
}

const emptyForm: TicketIntakeRequest = {
  asset_id: "",
  issue_description: "",
  failure_category: "no_failure",
  reporter_name: null,
  reporter_email: null,
  reporter_phone: null,
  category_id: null,
  subcategory_id: null,
  impact: "medium",
  urgency: "medium",
  intake_source_id: null,
  support_group_id: null,
  assigned_user_id: null,
  manager_note: null,
};

export function TicketIntakeForm({ initialAssetId = "" }: TicketIntakeFormProps) {
  const auth = useAuth();
  const options = useTicketingOptionsQuery();
  const assets = useAssetsQuery({ limit: 1000 });
  const mutation = useTicketIntakeMutation();
  const submitting = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const [form, setForm] = useState<TicketIntakeRequest>({
    ...emptyForm,
    asset_id: initialAssetId,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const priority = useTicketPriorityPreviewQuery(form.impact, form.urgency);

  if (options.isPending || assets.isPending) return <LoadingSkeleton />;
  if (options.isError || assets.isError) {
    return (
      <ErrorState
        title="Chưa tải được cấu hình ticket"
        description={getApiErrorMessage(options.error ?? assets.error)}
        action={
          <RetryButton
            onClick={() => {
              void options.refetch();
              void assets.refetch();
            }}
          />
        }
      />
    );
  }

  const categorySubcategories = options.data.subcategories.filter(
    (item) => item.category_id === form.category_id,
  );
  const selectedAsset = assets.data.find((asset) => asset.asset_id === form.asset_id);
  const selectedAssignee = options.data.assignees.find(
    (item) => item.id === form.assigned_user_id,
  );
  const canAssign = auth.can(permissions.ticketsAssign);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending || submitting.current) return;
    const request = normalizeRequest(form, canAssign);
    const parsed = ticketIntakeRequestSchema.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(zodFieldErrors(parsed.error.issues));
      window.setTimeout(() => {
        formRef.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus();
      }, 0);
      return;
    }
    if (!selectedAsset) {
      setFieldErrors({
        asset_id: "Chọn một thiết bị đang có trong danh sách.",
      });
      window.setTimeout(() => {
        formRef.current?.querySelector<HTMLElement>("#ticket-asset")?.focus();
      }, 0);
      return;
    }
    submitting.current = true;
    setFieldErrors({});
    try {
      await mutation.mutateAsync(parsed.data);
    } catch (error) {
      submitting.current = false;
      if (error instanceof UserSafeApiError) setFieldErrors(error.fieldErrors);
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <form
        ref={formRef}
        onSubmit={submit}
        className="space-y-5 rounded-lg border bg-white p-4 sm:p-5"
      >
        <section aria-labelledby="ticket-context-heading">
          <h2 id="ticket-context-heading" className="text-sm font-semibold">
            Thiết bị và vấn đề
          </h2>
          <div className="mt-4">
            <Field
              id="ticket-asset"
              label="Thiết bị"
              error={fieldErrors.asset_id}
            >
              <Select
                value={form.asset_id || "none"}
                onValueChange={(asset_id) => {
                  setForm({ ...form, asset_id: asset_id === "none" ? "" : asset_id });
                  setFieldErrors((current) => {
                    const { asset_id: _assetError, ...remaining } = current;
                    return remaining;
                  });
                }}
              >
                <SelectTrigger id="ticket-asset" className="w-full" aria-invalid={Boolean(fieldErrors.asset_id)} aria-describedby={fieldErrors.asset_id ? "ticket-asset-error" : undefined}>
                  <SelectValue placeholder="Chọn thiết bị" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Chọn thiết bị</SelectItem>
                  {assets.data.map((asset) => (
                    <SelectItem key={asset.asset_id} value={asset.asset_id}>
                      {asset.asset_id} · {asset.asset_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          {selectedAsset && <SelectedAssetContext asset={selectedAsset} />}
          <div className="mt-4">
            <Field
              id="ticket-description"
              label="Mô tả sự cố"
              error={fieldErrors.issue_description}
            >
              <Textarea
                id="ticket-description"
                rows={5}
                aria-invalid={Boolean(fieldErrors.issue_description)}
                aria-describedby={fieldErrors.issue_description ? "ticket-description-error" : undefined}
                value={form.issue_description}
                onChange={(event) =>
                  setForm({ ...form, issue_description: event.target.value })
                }
                placeholder="Mô tả dấu hiệu, thời điểm và điều kiện quan sát được."
              />
            </Field>
          </div>
        </section>

        <section aria-labelledby="ticket-classification-heading" className="border-t pt-5">
          <h2 id="ticket-classification-heading" className="text-sm font-semibold">
            Mức độ ưu tiên
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">Chọn mức ảnh hưởng và độ khẩn cấp; hệ thống sẽ xác định mức ưu tiên.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <ClassificationSelect
              id="ticket-impact"
              label="Mức ảnh hưởng"
              value={form.impact}
              options={options.data.impacts}
              onChange={(impact) => setForm({ ...form, impact })}
            />
            <ClassificationSelect
              id="ticket-urgency"
              label="Độ khẩn cấp"
              value={form.urgency}
              options={options.data.urgencies}
              onChange={(urgency) => setForm({ ...form, urgency })}
            />
          </div>
          <div className="mt-4 flex items-center justify-between rounded-lg border bg-muted/40 p-3">
            <div>
              <p className="text-xs text-muted-foreground">
                Mức ưu tiên được hệ thống tính
              </p>
              <p className="mt-1 text-sm font-medium">
                {priority.isPending
                  ? "Đang tính..."
                  : priority.data
                    ? `${priority.data.impact_display} × ${priority.data.urgency_display}`
                    : "Chưa có kết quả"}
              </p>
            </div>
            {priority.data && (
              <TicketOperationsPriorityBadge
                priority={priority.data.priority}
                label={priority.data.priority_display}
              />
            )}
          </div>
        </section>

        <details className="group border-t pt-5">
          <summary className="w-fit cursor-pointer rounded-md text-sm font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Thông tin bổ sung
          </summary>
          <p className="mt-1 text-xs text-muted-foreground">Phân loại chi tiết, điều phối và thông tin người báo có thể bổ sung khi cần.</p>

          <section aria-labelledby="ticket-detail-classification-heading" className="mt-5">
            <h2 id="ticket-detail-classification-heading" className="text-sm font-semibold">Phân loại chi tiết</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field id="ticket-failure-category" label="Nhóm lỗi vận hành" error={fieldErrors.failure_category}>
                <Select
                  value={form.failure_category}
                  onValueChange={(failure_category) =>
                    setForm({
                      ...form,
                      failure_category: failure_category as TicketIntakeRequest["failure_category"],
                    })
                  }
                >
                  <SelectTrigger id="ticket-failure-category" className="w-full" aria-invalid={Boolean(fieldErrors.failure_category)}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {options.data.failure_categories.map((item) => (
                      <SelectItem key={item.code} value={item.code}>
                        {item.display_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field id="ticket-category" label="Nhóm sự cố" error={fieldErrors.category_id}>
                <Select value={form.category_id ?? "none"} onValueChange={(category_id) => setForm({ ...form, category_id: category_id === "none" ? null : category_id, subcategory_id: null })}>
                  <SelectTrigger id="ticket-category" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="none">Chưa phân loại</SelectItem>{options.data.categories.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
              <Field id="ticket-subcategory" label="Phân loại cụ thể" error={fieldErrors.subcategory_id}>
                <Select value={form.subcategory_id ?? "none"} onValueChange={(subcategory_id) => setForm({ ...form, subcategory_id: subcategory_id === "none" ? null : subcategory_id })}>
                  <SelectTrigger id="ticket-subcategory" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="none">Chưa chọn</SelectItem>{categorySubcategories.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
                </Select>
              </Field>
            </div>
          </section>

          <section aria-labelledby="ticket-routing-heading" className="mt-5 border-t pt-5">
            <h2 id="ticket-routing-heading" className="text-sm font-semibold">Tiếp nhận và phân công</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <ReferenceSelect id="ticket-source" label="Nguồn tiếp nhận" value={form.intake_source_id} items={options.data.intake_sources} onChange={(intake_source_id) => setForm({ ...form, intake_source_id })} />
              <ReferenceSelect id="ticket-group" label="Nhóm xử lý" value={form.support_group_id} items={options.data.support_groups} onChange={(support_group_id) => setForm({ ...form, support_group_id })} />
              {canAssign && (
                <div className="space-y-1.5">
                  <Field id="ticket-assignee" label="Người được phân công">
                    <Select
                      value={form.assigned_user_id ?? "none"}
                      onValueChange={(assigned_user_id) =>
                        setForm({
                          ...form,
                          assigned_user_id:
                            assigned_user_id === "none" ? null : assigned_user_id,
                        })
                      }
                    >
                      <SelectTrigger id="ticket-assignee" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Chưa phân công</SelectItem>
                        {options.data.assignees.map((item) => (
                          <SelectItem key={item.id} value={item.id}>
                            {item.display_name}
                            {item.technician_id ? ` · ${item.technician_id}` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  {selectedAssignee && (
                    <p className="text-xs text-muted-foreground">
                      Đã chọn: {selectedAssignee.display_name}
                      {selectedAssignee.technician_id
                        ? ` · ${selectedAssignee.technician_id}`
                        : ""}
                    </p>
                  )}
                </div>
              )}
              <Field id="ticket-manager-note" label="Ghi chú quản lý"><Textarea id="ticket-manager-note" rows={3} value={form.manager_note ?? ""} onChange={(event) => setForm({ ...form, manager_note: event.target.value })} /></Field>
            </div>
          </section>

          <section aria-labelledby="ticket-reporter-heading" className="mt-5 border-t pt-5">
            <h2 id="ticket-reporter-heading" className="text-sm font-semibold">Người báo sự cố</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <TextInput id="ticket-reporter-name" label="Họ tên" value={form.reporter_name} onChange={(reporter_name) => setForm({ ...form, reporter_name })} />
              <TextInput id="ticket-reporter-email" label="Email" type="email" value={form.reporter_email} error={fieldErrors.reporter_email} onChange={(reporter_email) => setForm({ ...form, reporter_email })} />
              <TextInput id="ticket-reporter-phone" label="Điện thoại" value={form.reporter_phone} onChange={(reporter_phone) => setForm({ ...form, reporter_phone })} />
            </div>
          </section>
        </details>

        {mutation.isError && (
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900"
          >
            {getApiErrorMessage(mutation.error)}
          </div>
        )}
        <div className="flex justify-end border-t pt-4">
          <Button type="submit" disabled={mutation.isPending || Boolean(mutation.data)}>
            {mutation.isPending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <TicketPlus aria-hidden="true" />
            )}
            {mutation.isPending ? "Đang lưu..." : "Lưu phiếu sự cố"}
          </Button>
        </div>
      </form>

      <aside className="space-y-4">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Quy tắc vận hành</h2>
          <dl className="mt-3 space-y-3 text-sm">
            <Fact label="Trạng thái ban đầu" value={canAssign ? "Mới hoặc đã phân công" : "Mới"} />
            <Fact label="Mức ưu tiên" value="Tính từ ảnh hưởng và độ khẩn cấp" />
            <Fact label="Thời hạn xử lý" value="Được giữ cố định khi tạo phiếu" />
            <Fact label="Chỉ số phân tích" value="Cập nhật ở đợt tiếp theo" />
          </dl>
        </section>
        {mutation.data && (
          <section
            role="status"
            className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-950"
          >
            <p className="flex items-center gap-2 text-sm font-semibold">
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Đã lưu phiếu sự cố
            </p>
            <p className="mt-2 text-xs leading-5">
              Mức ưu tiên: {mutation.data.priority_display}. Mã phiếu: {mutation.data.ticket_id}.
            </p>
            <Button asChild size="sm" className="mt-3">
              <Link href={`/tickets/${mutation.data.ticket_id}`}>Xem phiếu sự cố</Link>
            </Button>
          </section>
        )}
      </aside>
    </div>
  );
}

function SelectedAssetContext({ asset }: { asset: AssetOverviewRecord }) {
  return (
    <section
      aria-labelledby="ticket-asset-context"
      className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3"
    >
      <h3 id="ticket-asset-context" className="text-sm font-semibold text-blue-950">
        Ngữ cảnh thiết bị đã chọn
      </h3>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <p className="text-xs text-blue-800">Thiết bị</p>
          <p className="mt-1 font-mono text-sm font-semibold text-blue-950">{asset.asset_id}</p>
          <p className="mt-1 text-xs text-blue-900">{asset.asset_name} · {asset.location}</p>
        </div>
        <div>
          <p className="text-xs text-blue-800">Risk Score (batch gần nhất)</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm font-semibold text-blue-950">
            <span>{asset.risk_score?.toFixed(2) ?? "Chưa có dữ liệu"}</span>
            {asset.risk_level && <RiskBadge level={asset.risk_level} />}
          </div>
        </div>
        <div>
          <p className="text-xs text-blue-800">Bảo trì</p>
          <div className="mt-1">
            {asset.maintenance_status_display ? (
              <MaintenanceBadge status={asset.maintenance_status_display} />
            ) : (
              <span className="text-sm text-blue-950">Chưa có lịch</span>
            )}
          </div>
        </div>
      </div>
      {asset.contributing_factors && (
        <p className="mt-3 text-xs leading-5 text-blue-950">{asset.contributing_factors}</p>
      )}
      <p className="mt-3 text-xs leading-5 text-blue-900">
        Risk Score hỗ trợ ưu tiên kiểm tra; mức ưu tiên ticket vẫn do backend tính từ mức ảnh hưởng và độ khẩn cấp.
      </p>
    </section>
  );
}

function normalizeRequest(
  form: TicketIntakeRequest,
  canAssign: boolean,
): TicketIntakeRequest {
  return {
    ...form,
    reporter_name: form.reporter_name?.trim() || null,
    reporter_email: form.reporter_email?.trim() || null,
    reporter_phone: form.reporter_phone?.trim() || null,
    manager_note: form.manager_note?.trim() || null,
    assigned_user_id: canAssign ? form.assigned_user_id : null,
  };
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function TextInput({
  id,
  label,
  value,
  onChange,
  type = "text",
  error,
}: {
  id: string;
  label: string;
  value: string | null;
  onChange: (value: string) => void;
  type?: string;
  error?: string;
}) {
  return (
    <Field id={id} label={label} error={error}>
      <Input
        id={id}
        type={type}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

function ReferenceSelect({
  id,
  label,
  value,
  items,
  onChange,
}: {
  id: string;
  label: string;
  value: string | null;
  items: { id: string; name: string }[];
  onChange: (value: string | null) => void;
}) {
  return (
    <Field id={id} label={label}>
      <Select
        value={value ?? "none"}
        onValueChange={(selected) => onChange(selected === "none" ? null : selected)}
      >
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">Chưa chọn</SelectItem>
          {items.map((item) => (
            <SelectItem key={item.id} value={item.id}>
              {item.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function ClassificationSelect<T extends TicketImpact | TicketUrgency>({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: T;
  options: { code: string; display_name: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <Field id={id} label={label}>
      <Select value={value} onValueChange={(selected) => onChange(selected as T)}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((item) => (
            <SelectItem key={item.code} value={item.code}>
              {item.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-medium">{value}</dd>
    </div>
  );
}
