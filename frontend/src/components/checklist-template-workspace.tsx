"use client";

import { Archive, CopyPlus, Plus, ShieldAlert, Trash2 } from "lucide-react";
import { useState } from "react";

import { PermissionDeniedNotice, useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useArchiveChecklistTemplate,
  useCreateChecklistTemplate,
  useVersionChecklistTemplate,
} from "@/hooks/use-api-mutations";
import { useChecklistTemplatesQuery } from "@/hooks/use-api-queries";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { ChecklistTemplate, ChecklistTemplateCreateRequest } from "@/lib/api/maintenance-schemas";
import { permissions } from "@/lib/auth";
import { formatTimestamp } from "@/lib/formatters";
import { cn } from "@/lib/utils";

type DraftItem = ChecklistTemplateCreateRequest["items"][number];

const emptyItem = (sequence: number): DraftItem => ({
  sequence,
  instruction: "",
  response_type: "checkbox",
  is_required: true,
  safety_critical: false,
  allow_not_applicable: false,
  expected_unit: null,
  minimum_value: null,
  maximum_value: null,
  guidance: null,
});

export function ChecklistTemplateWorkspace() {
  const auth = useAuth();
  const templates = useChecklistTemplatesQuery({ page_size: 200 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const selected = templates.data?.items.find((template) => template.id === selectedId) ?? templates.data?.items[0] ?? null;

  if (templates.isPending) return <LoadingSkeleton />;
  if (templates.isError) return <ErrorState title="Chưa tải được checklist template" description={getApiErrorMessage(templates.error)} action={<RetryButton onClick={() => void templates.refetch()} />} />;

  return (
    <div className="space-y-5">
      <section className="flex flex-col justify-between gap-3 rounded-lg border bg-white p-4 sm:flex-row sm:items-center">
        <div><p className="font-semibold">{templates.data?.total ?? 0} template version</p><p className="mt-1 text-xs text-muted-foreground">Work order lưu snapshot; chỉnh template không thay đổi checklist lịch sử.</p></div>
        {auth.can(permissions.checklistTemplatesCreate) && <Button type="button" onClick={() => setShowCreate((value) => !value)}><Plus aria-hidden="true" />{showCreate ? "Đóng biểu mẫu" : "Tạo template"}</Button>}
      </section>
      {showCreate && <ChecklistTemplateForm onCreated={(id) => { setSelectedId(id); setShowCreate(false); }} />}
      <div className="grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <section className="rounded-lg border bg-white p-2" aria-label="Danh sách template">
          {templates.data?.items.length ? <div className="space-y-1">{templates.data.items.map((template) => <button key={template.id} type="button" onClick={() => setSelectedId(template.id)} className={cn("w-full rounded-md px-3 py-3 text-left transition-colors", selected?.id === template.id ? "bg-blue-50 ring-1 ring-blue-200" : "hover:bg-muted")}><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs font-semibold text-primary">{template.code}</span><Badge variant={template.status === "active" ? "outline" : "secondary"}>v{template.version_number} · {template.status_display}</Badge></div><p className="mt-1 text-sm font-medium">{template.name}</p><p className="mt-1 text-xs text-muted-foreground">{template.item_count} bước</p></button>)}</div> : <EmptyState title="Chưa có template" description="Tạo một checklist có ít nhất một bước." />}
        </section>
        {selected ? <ChecklistTemplateDetail template={selected} /> : <div className="rounded-lg border bg-white"><EmptyState title="Chọn template" description="Chọn một template để xem các bước." /></div>}
      </div>
    </div>
  );
}

function ChecklistTemplateDetail({ template }: { template: ChecklistTemplate }) {
  const auth = useAuth();
  const version = useVersionChecklistTemplate(template.id);
  const archive = useArchiveChecklistTemplate(template.id);
  const [message, setMessage] = useState<string | null>(null);

  async function cloneVersion() {
    if (!window.confirm(`Tạo version ${template.version_number + 1} từ snapshot hiện tại?`)) return;
    try {
      const created = await version.mutateAsync({
        name: template.name,
        asset_type: template.asset_type as "hvac" | "pump" | "generator" | null,
        description: template.description,
        items: template.items.map((item) => ({ sequence: item.sequence, instruction: item.instruction, response_type: item.response_type as DraftItem["response_type"], is_required: item.is_required, safety_critical: item.safety_critical, allow_not_applicable: item.allow_not_applicable, expected_unit: item.expected_unit, minimum_value: item.minimum_value, maximum_value: item.maximum_value, guidance: item.guidance })),
      });
      setMessage(`Đã tạo ${created.code} version ${created.version_number}.`);
    } catch (error) { setMessage(getApiErrorMessage(error)); }
  }

  async function archiveTemplate() {
    if (!window.confirm("Lưu trữ version này? Work order lịch sử vẫn đọc được.")) return;
    try { await archive.mutateAsync(template.version); setMessage("Đã lưu trữ template version."); } catch (error) { setMessage(getApiErrorMessage(error)); }
  }

  return <section className="rounded-lg border bg-white p-4 sm:p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-semibold text-primary">{template.code}</span><Badge variant="outline">Version {template.version_number}</Badge><Badge variant={template.status === "active" ? "outline" : "secondary"}>{template.status_display}</Badge></div><h2 className="mt-2 text-lg font-semibold">{template.name}</h2><p className="mt-1 text-sm text-muted-foreground">Áp dụng: {template.asset_type ?? "Mọi loại thiết bị"}</p></div><div className="flex flex-wrap gap-2">{auth.can(permissions.checklistTemplatesUpdate) && <Button type="button" variant="outline" onClick={() => void cloneVersion()} disabled={version.isPending}><CopyPlus aria-hidden="true" />Tạo version mới</Button>}{auth.can(permissions.checklistTemplatesUpdate) && template.status === "active" && <Button type="button" variant="outline" onClick={() => void archiveTemplate()} disabled={archive.isPending}><Archive aria-hidden="true" />Lưu trữ</Button>}</div></div>{template.description && <p className="mt-4 text-sm leading-6">{template.description}</p>}{message && <p role="status" className="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{message}</p>}<ol className="mt-5 space-y-3">{template.items.map((item) => <li key={item.id} className={cn("rounded-md border p-3", item.safety_critical && "border-red-200 bg-red-50/50")}><div className="flex items-start gap-3"><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-neutral-100 text-xs font-semibold">{item.sequence}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-medium">{item.instruction}</p>{item.is_required && <Badge variant="outline">Bắt buộc</Badge>}{item.safety_critical && <Badge className="bg-red-50 text-red-700 ring-1 ring-red-200"><ShieldAlert aria-hidden="true" />An toàn</Badge>}</div><p className="mt-1 text-xs text-muted-foreground">{item.response_type_display}{item.expected_unit ? ` · ${item.expected_unit}` : ""}{item.minimum_value != null || item.maximum_value != null ? ` · giới hạn ${item.minimum_value ?? "−∞"} đến ${item.maximum_value ?? "+∞"}` : ""}</p>{item.guidance && <p className="mt-2 text-sm text-muted-foreground">{item.guidance}</p>}</div></div></li>)}</ol><p className="mt-4 border-t pt-3 text-xs text-muted-foreground">Tạo {formatTimestamp(template.created_at)} · cập nhật {formatTimestamp(template.updated_at)}</p></section>;
}

function ChecklistTemplateForm({ onCreated }: { onCreated: (id: string) => void }) {
  const auth = useAuth();
  const create = useCreateChecklistTemplate();
  const [form, setForm] = useState({ code: "", name: "", asset_type: "all", description: "" });
  const [items, setItems] = useState<DraftItem[]>([emptyItem(1)]);
  if (!auth.can(permissions.checklistTemplatesCreate)) return <PermissionDeniedNotice message="Vai trò hiện tại không có permission tạo checklist template." />;

  function updateItem(index: number, updates: Partial<DraftItem>) { setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...updates } : item)); }
  function removeItem(index: number) { setItems((current) => current.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sequence: itemIndex + 1 }))); }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      const created = await create.mutateAsync({ code: form.code.trim().toUpperCase(), name: form.name.trim(), asset_type: form.asset_type === "all" ? null : form.asset_type as "hvac" | "pump" | "generator", description: form.description.trim() || null, items });
      onCreated(created.id);
    } catch { /* Render safe error. */ }
  }

  return <form onSubmit={submit} className="rounded-lg border bg-white p-4 sm:p-5"><h2 className="font-semibold">Template mới</h2><div className="mt-4 grid gap-4 md:grid-cols-3"><Field id="template-code" label="Mã template"><Input id="template-code" required value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} placeholder="CHK-GENERATOR" /></Field><Field id="template-name" label="Tên"><Input id="template-name" required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Field><Field id="template-asset-type" label="Loại thiết bị"><Select value={form.asset_type} onValueChange={(value) => setForm({ ...form, asset_type: value })}><SelectTrigger id="template-asset-type" className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">Mọi loại</SelectItem><SelectItem value="hvac">HVAC</SelectItem><SelectItem value="pump">Bơm</SelectItem><SelectItem value="generator">Máy phát điện</SelectItem></SelectContent></Select></Field><div className="md:col-span-3"><Field id="template-description" label="Mô tả"><Textarea id="template-description" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field></div></div><div className="mt-5 flex items-center justify-between border-t pt-4"><div><h3 className="font-medium">Các bước checklist</h3><p className="text-xs text-muted-foreground">Thứ tự được lưu cố định trong snapshot.</p></div><Button type="button" variant="outline" size="sm" onClick={() => setItems((current) => [...current, emptyItem(current.length + 1)])}><Plus aria-hidden="true" />Thêm bước</Button></div><div className="mt-3 space-y-3">{items.map((item, index) => <div key={item.sequence} className="rounded-md border p-3"><div className="grid gap-3 md:grid-cols-[56px_minmax(240px,1fr)_180px_auto]"><Field id={`sequence-${index}`} label="STT"><Input id={`sequence-${index}`} type="number" min={1} value={item.sequence} readOnly /></Field><Field id={`instruction-${index}`} label="Hướng dẫn"><Input id={`instruction-${index}`} required value={item.instruction} onChange={(event) => updateItem(index, { instruction: event.target.value })} /></Field><Field id={`response-${index}`} label="Kiểu phản hồi"><Select value={item.response_type} onValueChange={(value) => updateItem(index, { response_type: value as DraftItem["response_type"] })}><SelectTrigger id={`response-${index}`} className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="checkbox">Checkbox</SelectItem><SelectItem value="pass_fail">Đạt / Không đạt</SelectItem><SelectItem value="numeric">Số đo</SelectItem><SelectItem value="text">Nội dung</SelectItem></SelectContent></Select></Field><div className="flex items-end"><Button type="button" variant="ghost" size="icon" title="Xóa bước" aria-label={`Xóa bước ${index + 1}`} disabled={items.length === 1} onClick={() => removeItem(index)}><Trash2 aria-hidden="true" /></Button></div></div><div className="mt-3 flex flex-wrap gap-4 text-sm"><Check label="Bắt buộc" checked={item.is_required} onChange={(checked) => updateItem(index, { is_required: checked })} /><Check label="An toàn quan trọng" checked={item.safety_critical} onChange={(checked) => updateItem(index, { safety_critical: checked })} /><Check label="Cho phép N/A" checked={item.allow_not_applicable} onChange={(checked) => updateItem(index, { allow_not_applicable: checked })} /></div>{item.response_type === "numeric" && <div className="mt-3 grid gap-3 sm:grid-cols-3"><Field id={`unit-${index}`} label="Đơn vị"><Input id={`unit-${index}`} value={item.expected_unit ?? ""} onChange={(event) => updateItem(index, { expected_unit: event.target.value || null })} /></Field><Field id={`min-${index}`} label="Tối thiểu"><Input id={`min-${index}`} type="number" value={item.minimum_value ?? ""} onChange={(event) => updateItem(index, { minimum_value: event.target.value === "" ? null : Number(event.target.value) })} /></Field><Field id={`max-${index}`} label="Tối đa"><Input id={`max-${index}`} type="number" value={item.maximum_value ?? ""} onChange={(event) => updateItem(index, { maximum_value: event.target.value === "" ? null : Number(event.target.value) })} /></Field></div>}</div>)}</div>{create.error && <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{getApiErrorMessage(create.error)}</p>}<div className="mt-4 flex justify-end"><Button type="submit" disabled={create.isPending}>{create.isPending ? "Đang tạo…" : "Tạo template"}</Button></div></form>;
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>; }
function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) { return <label className="flex items-center gap-2"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="size-4 rounded border-neutral-300" />{label}</label>; }
