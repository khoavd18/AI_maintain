"use client";

import Link from "next/link";
import { CheckCircle2, Loader2, TicketPlus } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  TicketOperationsPriorityBadge,
} from "@/components/ticket-operations-badges";
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
  const canAssign = auth.can(permissions.ticketsAssign);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending || submitting.current) return;
    const request = normalizeRequest(form, canAssign);
    const parsed = ticketIntakeRequestSchema.safeParse(request);
    if (!parsed.success) {
      setFieldErrors(zodFieldErrors(parsed.error.issues));
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
        onSubmit={submit}
        className="space-y-5 rounded-lg border bg-white p-4 sm:p-5"
      >
        <section aria-labelledby="ticket-context-heading">
          <h2 id="ticket-context-heading" className="text-sm font-semibold">
            Thiết bị và vấn đề
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field
              id="ticket-asset"
              label="Thiết bị"
              error={fieldErrors.asset_id}
            >
              <Select
                value={form.asset_id || "none"}
                onValueChange={(asset_id) =>
                  setForm({ ...form, asset_id: asset_id === "none" ? "" : asset_id })
                }
              >
                <SelectTrigger id="ticket-asset" className="w-full">
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
            <Field
              id="ticket-failure-category"
              label="Nhóm lỗi vận hành"
              error={fieldErrors.failure_category}
            >
              <Select
                value={form.failure_category}
                onValueChange={(failure_category) =>
                  setForm({
                    ...form,
                    failure_category:
                      failure_category as TicketIntakeRequest["failure_category"],
                  })
                }
              >
                <SelectTrigger id="ticket-failure-category" className="w-full">
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
          </div>
          <div className="mt-4">
            <Field
              id="ticket-description"
              label="Mô tả sự cố"
              error={fieldErrors.issue_description}
            >
              <Textarea
                id="ticket-description"
                rows={5}
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
            Phân loại và ưu tiên
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field id="ticket-category" label="Category" error={fieldErrors.category_id}>
              <Select
                value={form.category_id ?? "none"}
                onValueChange={(category_id) =>
                  setForm({
                    ...form,
                    category_id: category_id === "none" ? null : category_id,
                    subcategory_id: null,
                  })
                }
              >
                <SelectTrigger id="ticket-category" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Chưa phân loại</SelectItem>
                  {options.data.categories.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              id="ticket-subcategory"
              label="Subcategory"
              error={fieldErrors.subcategory_id}
            >
              <Select
                value={form.subcategory_id ?? "none"}
                onValueChange={(subcategory_id) =>
                  setForm({
                    ...form,
                    subcategory_id:
                      subcategory_id === "none" ? null : subcategory_id,
                  })
                }
              >
                <SelectTrigger id="ticket-subcategory" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Chưa chọn</SelectItem>
                  {categorySubcategories.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <ClassificationSelect
              id="ticket-impact"
              label="Impact"
              value={form.impact}
              options={options.data.impacts}
              onChange={(impact) => setForm({ ...form, impact })}
            />
            <ClassificationSelect
              id="ticket-urgency"
              label="Urgency"
              value={form.urgency}
              options={options.data.urgencies}
              onChange={(urgency) => setForm({ ...form, urgency })}
            />
          </div>
          <div className="mt-4 flex items-center justify-between rounded-lg border bg-muted/40 p-3">
            <div>
              <p className="text-xs text-muted-foreground">
                Priority do backend tính từ impact × urgency
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

        <section aria-labelledby="ticket-routing-heading" className="border-t pt-5">
          <h2 id="ticket-routing-heading" className="text-sm font-semibold">
            Tiếp nhận và phân công
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <ReferenceSelect
              id="ticket-source"
              label="Nguồn tiếp nhận"
              value={form.intake_source_id}
              items={options.data.intake_sources}
              onChange={(intake_source_id) =>
                setForm({ ...form, intake_source_id })
              }
            />
            <ReferenceSelect
              id="ticket-group"
              label="Support group"
              value={form.support_group_id}
              items={options.data.support_groups}
              onChange={(support_group_id) =>
                setForm({ ...form, support_group_id })
              }
            />
            {canAssign && (
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
            )}
            <Field id="ticket-manager-note" label="Ghi chú quản lý">
              <Textarea
                id="ticket-manager-note"
                rows={3}
                value={form.manager_note ?? ""}
                onChange={(event) =>
                  setForm({ ...form, manager_note: event.target.value })
                }
              />
            </Field>
          </div>
        </section>

        <section aria-labelledby="ticket-reporter-heading" className="border-t pt-5">
          <h2 id="ticket-reporter-heading" className="text-sm font-semibold">
            Người báo sự cố
          </h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-3">
            <TextInput
              id="ticket-reporter-name"
              label="Họ tên"
              value={form.reporter_name}
              onChange={(reporter_name) => setForm({ ...form, reporter_name })}
            />
            <TextInput
              id="ticket-reporter-email"
              label="Email"
              type="email"
              value={form.reporter_email}
              error={fieldErrors.reporter_email}
              onChange={(reporter_email) => setForm({ ...form, reporter_email })}
            />
            <TextInput
              id="ticket-reporter-phone"
              label="Điện thoại"
              value={form.reporter_phone}
              onChange={(reporter_phone) => setForm({ ...form, reporter_phone })}
            />
          </div>
        </section>

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
            {mutation.isPending ? "Đang tạo..." : "Tạo ticket"}
          </Button>
        </div>
      </form>

      <aside className="space-y-4">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-semibold">Quy tắc vận hành</h2>
          <dl className="mt-3 space-y-3 text-sm">
            <Fact label="Trạng thái ban đầu" value={canAssign ? "Open hoặc Assigned" : "Open"} />
            <Fact label="Priority" value="Backend impact × urgency matrix" />
            <Fact label="SLA" value="Snapshot policy tại thời điểm tạo" />
            <Fact label="Risk/KPI" value="Cập nhật ở analytics batch kế tiếp" />
          </dl>
        </section>
        {mutation.data && (
          <section
            role="status"
            className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-950"
          >
            <p className="flex items-center gap-2 text-sm font-semibold">
              <CheckCircle2 className="size-4" aria-hidden="true" />
              Đã tạo {mutation.data.ticket_id}
            </p>
            <p className="mt-2 text-xs leading-5">
              Priority {mutation.data.priority_display}; SLA policy{" "}
              {mutation.data.sla?.policy_code ?? "chưa áp dụng"}.
            </p>
            <Button asChild size="sm" className="mt-3">
              <Link href={`/tickets/${mutation.data.ticket_id}`}>Mở ticket</Link>
            </Button>
          </section>
        )}
      </aside>
    </div>
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
        <p role="alert" className="text-xs text-destructive">
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
