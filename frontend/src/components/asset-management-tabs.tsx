"use client";

import { Download, FileText, Loader2, Pencil, Printer, QrCode, RefreshCcw, Trash2, Upload } from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import { AssetFormSheet } from "@/components/asset-form-sheet";
import { useAuth } from "@/components/auth-provider";
import { LifecycleBadge, OperationalBadge } from "@/components/status-badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState, LoadingSkeleton, RetryButton } from "@/components/ui-states";
import {
  useArchiveAsset,
  useChangeAssetOperationalStatus,
  useDeleteAssetAttachment,
  useRestoreAsset,
  useTransitionAssetLifecycle,
  useUploadAssetAttachment,
} from "@/hooks/use-api-mutations";
import {
  useAssetAttachmentsQuery,
  useAssetHistoryQuery,
  useAssetOptionsQuery,
  useAssetQrQuery,
} from "@/hooks/use-api-queries";
import { api } from "@/lib/api/endpoints";
import { getApiErrorMessage } from "@/lib/api/errors";
import type { AssetAttachment, AssetProfile } from "@/lib/api/schemas";
import { permissions } from "@/lib/auth";
import { formatDate, formatTimestamp } from "@/lib/formatters";

export function AssetManagementTabs({
  profile,
  onReload,
}: {
  profile: AssetProfile;
  onReload: () => void;
}) {
  const auth = useAuth();
  const [editOpen, setEditOpen] = useState(false);

  return (
    <section className="mt-5" aria-label="Quản lý vòng đời asset">
      <Tabs defaultValue="profile">
        <TabsList className="h-auto w-full justify-start overflow-x-auto">
          <TabsTrigger value="profile">Hồ sơ asset</TabsTrigger>
          {auth.can(permissions.attachmentsRead) && <TabsTrigger value="attachments">Tệp đính kèm</TabsTrigger>}
          <TabsTrigger value="qr">QR</TabsTrigger>
          <TabsTrigger value="history">Lịch sử</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-3 rounded-lg border bg-white p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b pb-4">
            <div><h2 className="font-semibold">Hồ sơ kỹ thuật và lifecycle</h2><p className="mt-1 text-xs text-muted-foreground">Version {profile.version} · cập nhật {formatTimestamp(profile.updated_at)}</p></div>
            {auth.can(permissions.assetsUpdate) && <Button type="button" variant="outline" size="sm" onClick={() => setEditOpen(true)} disabled={profile.lifecycle_status === "archived"}><Pencil aria-hidden="true" />Chỉnh sửa hồ sơ</Button>}
          </div>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(300px,0.8fr)]">
            <AssetFacts profile={profile} />
            <AssetLifecycleActions key={`${profile.asset_id}:${profile.version}`} profile={profile} onReload={onReload} />
          </div>
        </TabsContent>

        {auth.can(permissions.attachmentsRead) && <TabsContent value="attachments" className="mt-3"><AttachmentWorkspace profile={profile} /></TabsContent>}
        <TabsContent value="qr" className="mt-3"><QrWorkspace profile={profile} /></TabsContent>
        <TabsContent value="history" className="mt-3"><HistoryWorkspace profile={profile} /></TabsContent>
      </Tabs>

      {auth.can(permissions.assetsUpdate) && editOpen && <AssetFormSheet open onOpenChange={setEditOpen} profile={profile} onSaved={onReload} onReload={onReload} />}
    </section>
  );
}

function AssetFacts({ profile }: { profile: AssetProfile }) {
  const warranty = warrantyLabel(profile.warranty_end_date);
  return <div className="space-y-5">
    <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
      <Fact label="Loại / nhóm" value={`${profile.asset_type} · ${profile.asset_category_display}`} />
      <Fact label="Nhà sản xuất" value={profile.manufacturer} />
      <Fact label="Model" value={profile.model} />
      <Fact label="Serial number" value={profile.serial_number} mono />
      <Fact label="Năm sản xuất" value={profile.production_year?.toString()} />
      <Fact label="Sở hữu" value={profile.ownership_type_display} />
      <Fact label="Vị trí" value={profile.location_breadcrumb} />
      <Fact label="Lắp đặt" value={formatDate(profile.installed_at)} />
      <Fact label="Nghiệm thu" value={formatDate(profile.commissioned_at)} />
      <Fact label="Bảo hành" value={warranty} />
      <Fact label="Đơn vị bảo hành" value={profile.warranty_provider} />
      <Fact label="Tham chiếu bảo hành" value={profile.warranty_reference} mono />
      <Fact label="Chu kỳ bảo trì" value={`${profile.maintenance_interval_days} ngày`} />
      <Fact label="Bảo trì gần nhất" value={formatDate(profile.last_maintenance_date)} />
      <Fact label="Bảo trì kế tiếp" value={formatDate(profile.next_maintenance_date)} />
    </div>
    <div className="border-t pt-4"><p className="text-xs font-medium text-muted-foreground">Mô tả</p><p className="mt-1 text-sm leading-6">{profile.description || "Chưa cập nhật mô tả."}</p></div>
  </div>;
}

function AssetLifecycleActions({ profile, onReload }: { profile: AssetProfile; onReload: () => void }) {
  const auth = useAuth();
  const options = useAssetOptionsQuery();
  const changeStatus = useChangeAssetOperationalStatus(profile.asset_id);
  const transition = useTransitionAssetLifecycle(profile.asset_id);
  const archive = useArchiveAsset(profile.asset_id);
  const restore = useRestoreAsset(profile.asset_id);
  const [operational, setOperational] = useState(profile.operational_status);
  const [lifecycle, setLifecycle] = useState<"planned" | "active" | "inactive" | "retired">("inactive");
  const [archiveReason, setArchiveReason] = useState("");

  const error = changeStatus.error ?? transition.error ?? archive.error ?? restore.error;
  const busy = changeStatus.isPending || transition.isPending || archive.isPending || restore.isPending;
  const lifecycleManager = auth.user?.role === "administrator" || auth.user?.role === "property_manager";

  async function applyOperational() {
    try { await changeStatus.mutateAsync({ operational_status: operational, expected_version: profile.version }); } catch { /* rendered below */ }
  }

  async function applyLifecycle() {
    if (!window.confirm(`Chuyển lifecycle sang ${lifecycle}?`)) return;
    try { await transition.mutateAsync({ lifecycle_status: lifecycle, expected_version: profile.version }); } catch { /* rendered below */ }
  }

  async function archiveAsset() {
    if (!window.confirm("Archive asset sẽ chặn ticket mới nhưng vẫn giữ toàn bộ lịch sử. Tiếp tục?")) return;
    try { await archive.mutateAsync({ archive_reason: archiveReason, expected_version: profile.version }); setArchiveReason(""); } catch { /* rendered below */ }
  }

  async function restoreAsset() {
    if (!window.confirm("Khôi phục asset về lifecycle trước đó?")) return;
    try { await restore.mutateAsync({ expected_version: profile.version }); } catch { /* rendered below */ }
  }

  return <aside className="space-y-4 rounded-lg border bg-muted/30 p-4">
    <div><p className="text-xs font-medium text-muted-foreground">Lifecycle</p><div className="mt-2"><LifecycleBadge status={profile.lifecycle_status} label={profile.lifecycle_status_display} /></div></div>
    <div><p className="text-xs font-medium text-muted-foreground">Trạng thái vận hành</p><div className="mt-2"><OperationalBadge status={profile.operational_status} label={profile.operational_status_display} /></div></div>

    {auth.can(permissions.assetsChangeStatus) && profile.lifecycle_status !== "archived" && <div className="space-y-2 border-t pt-4"><Label>Đổi trạng thái vận hành</Label><Select value={operational} onValueChange={(value) => setOperational(value as typeof operational)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent>{(options.data?.operational_statuses ?? []).map((item) => <SelectItem key={item.code} value={item.code}>{item.display_name}</SelectItem>)}</SelectContent></Select><Button type="button" size="sm" className="w-full" onClick={() => void applyOperational()} disabled={busy || operational === profile.operational_status}>Cập nhật trạng thái</Button></div>}

    {lifecycleManager && auth.can(permissions.assetsUpdate) && profile.lifecycle_status !== "archived" && <div className="space-y-2 border-t pt-4"><Label>Chuyển lifecycle</Label><Select value={lifecycle} onValueChange={(value) => setLifecycle(value as typeof lifecycle)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent>{(options.data?.lifecycle_statuses ?? []).filter((item) => item.code !== "archived").map((item) => <SelectItem key={item.code} value={item.code}>{item.display_name}</SelectItem>)}</SelectContent></Select><Button type="button" size="sm" variant="outline" className="w-full" onClick={() => void applyLifecycle()} disabled={busy || lifecycle === profile.lifecycle_status}>Áp dụng lifecycle</Button></div>}

    {auth.can(permissions.assetsArchive) && profile.lifecycle_status !== "archived" && <div className="space-y-2 border-t pt-4"><Label htmlFor="archive-reason">Lý do archive</Label><Input id="archive-reason" value={archiveReason} onChange={(event) => setArchiveReason(event.target.value)} placeholder="Lý do ngừng quản lý chủ động" /><Button type="button" variant="destructive" size="sm" className="w-full" disabled={busy || archiveReason.trim().length < 5} onClick={() => void archiveAsset()}>Archive asset</Button></div>}
    {auth.can(permissions.assetsRestore) && profile.lifecycle_status === "archived" && <Button type="button" className="w-full" onClick={() => void restoreAsset()} disabled={busy}><RefreshCcw aria-hidden="true" />Restore asset</Button>}
    {error && <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"><p>{getApiErrorMessage(error)}</p><Button type="button" variant="outline" size="sm" className="mt-2" onClick={onReload}>Tải version mới nhất</Button></div>}
  </aside>;
}

function AttachmentWorkspace({ profile }: { profile: AssetProfile }) {
  const auth = useAuth();
  const attachments = useAssetAttachmentsQuery(profile.asset_id);
  const options = useAssetOptionsQuery();
  const upload = useUploadAssetAttachment(profile.asset_id);
  const remove = useDeleteAssetAttachment(profile.asset_id);
  const [category, setCategory] = useState("technical_manual");
  const [file, setFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function chooseFile(selected: File | null) {
    setValidationError(null);
    if (!selected) { setFile(null); return; }
    const extension = selected.name.split(".").pop()?.toLowerCase();
    if (!extension || !["pdf", "png", "jpg", "jpeg"].includes(extension)) {
      setValidationError("Chỉ chấp nhận PDF, PNG, JPG hoặc JPEG.");
      setFile(null);
      return;
    }
    if (selected.size > 10 * 1024 * 1024) {
      setValidationError("Tệp vượt quá giới hạn 10 MB.");
      setFile(null);
      return;
    }
    setFile(selected);
  }

  async function submitUpload() {
    if (!file) return;
    try { await upload.mutateAsync({ category, file }); setFile(null); if (inputRef.current) inputRef.current.value = ""; } catch { /* rendered below */ }
  }

  async function download(attachment: AssetAttachment) {
    try {
      const blob = await api.downloadAssetAttachment(profile.asset_id, attachment.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = attachment.original_filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) { setValidationError(getApiErrorMessage(error)); }
  }

  async function deleteAttachment(attachment: AssetAttachment) {
    if (!window.confirm(`Xóa tệp ${attachment.original_filename}? Metadata audit vẫn được giữ.`)) return;
    try { await remove.mutateAsync(attachment.id); } catch { /* rendered below */ }
  }

  return <div className="rounded-lg border bg-white">
    {auth.can(permissions.attachmentsCreate) && profile.lifecycle_status !== "archived" && <div className="grid gap-3 border-b p-4 md:grid-cols-[180px_minmax(0,1fr)_auto] md:items-end"><div className="space-y-1.5"><Label>Loại tài liệu</Label><Select value={category} onValueChange={setCategory}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent>{(options.data?.attachment_categories ?? []).map((item) => <SelectItem key={item.code} value={item.code}>{item.display_name}</SelectItem>)}</SelectContent></Select></div><div className="space-y-1.5"><Label htmlFor="asset-attachment">Chọn tệp</Label><Input ref={inputRef} id="asset-attachment" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} /></div><Button type="button" onClick={() => void submitUpload()} disabled={!file || upload.isPending}>{upload.isPending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Upload aria-hidden="true" />}Tải lên</Button></div>}
    {(validationError || upload.isError || remove.isError) && <div role="alert" className="border-b border-red-200 bg-red-50 p-3 text-sm text-red-800">{validationError || getApiErrorMessage(upload.error ?? remove.error)}</div>}
    {attachments.isPending ? <div className="p-4"><LoadingSkeleton /></div> : attachments.isError ? <ErrorState title="Chưa tải được tệp đính kèm" description={getApiErrorMessage(attachments.error)} action={<RetryButton onClick={() => void attachments.refetch()} />} /> : !attachments.data?.length ? <EmptyState title="Chưa có tệp đính kèm" description="Tài liệu kỹ thuật, bảo hành và ảnh asset sẽ xuất hiện tại đây." /> : <ul className="divide-y">{attachments.data.map((attachment) => <li key={attachment.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center"><div className="flex min-w-0 flex-1 items-center gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><FileText className="size-4" aria-hidden="true" /></span><div className="min-w-0"><p className="truncate text-sm font-medium">{attachment.original_filename}</p><p className="mt-1 text-xs text-muted-foreground">{attachment.category_display} · {formatBytes(attachment.size_bytes)} · {formatTimestamp(attachment.created_at)}</p></div></div><div className="flex gap-2"><Button type="button" variant="outline" size="sm" onClick={() => void download(attachment)}><Download aria-hidden="true" />Tải xuống</Button>{auth.can(permissions.attachmentsDelete) && <Button type="button" variant="ghost" size="icon-sm" onClick={() => void deleteAttachment(attachment)} aria-label={`Xóa ${attachment.original_filename}`}><Trash2 aria-hidden="true" /></Button>}</div></li>)}</ul>}
  </div>;
}

function QrWorkspace({ profile }: { profile: AssetProfile }) {
  const qr = useAssetQrQuery(profile.asset_id);
  const [copied, setCopied] = useState(false);
  if (qr.isPending) return <div className="rounded-lg border bg-white p-4"><LoadingSkeleton /></div>;
  if (qr.isError) return <ErrorState title="Chưa tạo được QR" description={getApiErrorMessage(qr.error)} action={<RetryButton onClick={() => void qr.refetch()} />} />;
  const src = `data:image/svg+xml;base64,${qr.data.svg_base64}`;
  return <div className="qr-print-label grid gap-5 rounded-lg border bg-white p-4 md:grid-cols-[260px_minmax(0,1fr)]"><div className="flex aspect-square items-center justify-center rounded-lg border bg-white p-3"><Image src={src} alt={`QR tra cứu ${profile.asset_id}`} width={240} height={240} unoptimized className="size-full" /></div><div className="flex flex-col justify-center"><QrCode className="size-5 text-primary" aria-hidden="true" /><h2 className="mt-3 text-lg font-semibold">{profile.asset_id}</h2><p className="mt-1 text-sm">{profile.asset_name}</p><p className="mt-3 break-all text-xs text-muted-foreground">{qr.data.lookup_url}</p><p className="mt-3 text-xs text-muted-foreground">QR chỉ chứa lookup token công khai. Người mở vẫn phải đăng nhập để xem hồ sơ.</p><div className="mt-4 flex flex-wrap gap-2"><Button asChild variant="outline" size="sm"><a href={src} download={`${profile.asset_id}-qr.svg`}><Download aria-hidden="true" />Tải QR</a></Button><Button type="button" variant="outline" size="sm" onClick={() => window.print()}><Printer aria-hidden="true" />In nhãn</Button><Button type="button" variant="ghost" size="sm" onClick={async () => { await navigator.clipboard.writeText(qr.data.lookup_url); setCopied(true); }}>{copied ? "Đã sao chép" : "Sao chép URL"}</Button></div></div></div>;
}

function HistoryWorkspace({ profile }: { profile: AssetProfile }) {
  const [page, setPage] = useState(1);
  const history = useAssetHistoryQuery(profile.asset_id, { page, page_size: 15 });
  if (history.isPending) return <div className="rounded-lg border bg-white p-4"><LoadingSkeleton /></div>;
  if (history.isError) return <ErrorState title="Chưa tải được lịch sử asset" description={getApiErrorMessage(history.error)} action={<RetryButton onClick={() => void history.refetch()} />} />;
  if (!history.data.items.length) return <EmptyState title="Chưa có lịch sử" description="Các thay đổi asset, ticket và maintenance log sẽ xuất hiện tại đây." />;
  return <div className="rounded-lg border bg-white"><ol className="divide-y">{history.data.items.map((event) => <li key={event.id} className="grid gap-2 p-4 sm:grid-cols-[150px_minmax(0,1fr)_auto]"><time className="text-xs text-muted-foreground">{formatTimestamp(event.occurred_at)}</time><div><p className="text-sm font-medium">{event.summary}</p><p className="mt-1 text-xs text-muted-foreground">{event.actor_display_name || "System import"}{event.changed_fields.length ? ` · ${event.changed_fields.join(", ")}` : ""}</p></div><Badge variant="outline" className="w-fit">{event.event_type}</Badge></li>)}</ol>{history.data.total_pages > 1 && <div className="flex items-center justify-between border-t p-3"><p className="text-xs text-muted-foreground">Trang {page} / {history.data.total_pages}</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Trước</Button><Button variant="outline" size="sm" disabled={page >= history.data.total_pages} onClick={() => setPage((value) => value + 1)}>Sau</Button></div></div>}</div>;
}

function Fact({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return <div><p className="text-xs font-medium text-muted-foreground">{label}</p><p className={`mt-1 text-sm ${mono ? "font-mono text-xs" : ""}`}>{value || "Chưa cập nhật"}</p></div>;
}

function warrantyLabel(endDate: string | null): string {
  if (!endDate) return "Chưa có thông tin";
  return endDate >= new Date().toISOString().slice(0, 10) ? `Còn hiệu lực đến ${formatDate(endDate)}` : `Đã hết hạn ${formatDate(endDate)}`;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
