"use client";

import { AlertTriangle, ClipboardPenLine } from "lucide-react";
import { FormEvent, useState } from "react";

import { MaintenanceBadge, RiskBadge } from "@/components/status-badges";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { assets } from "@/lib/mock-data";

interface MockTicketFormProps {
  assetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MockTicketForm({ assetId, open, onOpenChange }: MockTicketFormProps) {
  const asset = assets.find((item) => item.id === assetId) ?? assets[0];
  const [priority, setPriority] = useState(asset.riskLevel === "Cao" ? "Khẩn cấp" : "Cao");
  const [technician, setTechnician] = useState("Chưa phân công");
  const [submitted, setSubmitted] = useState(false);
  const suggestedDescription = `Kiểm tra ${asset.id}: risk ${asset.riskScore?.toFixed(2) ?? "chưa có dữ liệu"} (${asset.riskLevel ?? "chưa phân loại"}), ${(asset.maintenanceStatus ?? "chưa có lịch").toLocaleLowerCase("vi")}. ${asset.contributingFactors}`;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitted(true);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 p-0 data-[side=right]:w-full sm:max-w-xl">
        <SheetHeader className="border-b px-4 py-4 text-left sm:px-5">
          <SheetTitle>Tạo ticket kiểm tra</SheetTitle>
          <SheetDescription>Biểu mẫu prefilled từ ngữ cảnh rủi ro, chỉ lưu trong giao diện mock.</SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
          <section aria-labelledby="ticket-facts" className="rounded-lg border border-orange-200 bg-orange-50 p-3">
            <h3 id="ticket-facts" className="flex items-center gap-2 text-xs font-semibold uppercase text-orange-900">
              <AlertTriangle className="size-4" aria-hidden="true" />
              Dữ liệu quan sát
            </h3>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-xs text-orange-800">Thiết bị</p>
                <p className="mt-1 font-mono text-sm font-semibold">{asset.id}</p>
              </div>
              <div>
                <p className="text-xs text-orange-800">Risk</p>
                <div className="mt-1 flex items-center gap-2"><strong>{asset.riskScore?.toFixed(2) ?? "--"}</strong>{asset.riskLevel && <RiskBadge level={asset.riskLevel} />}</div>
              </div>
              <div>
                <p className="text-xs text-orange-800">Bảo trì</p>
                <div className="mt-1">{asset.maintenanceStatus ? <MaintenanceBadge status={asset.maintenanceStatus} /> : "Chưa có lịch"}</div>
              </div>
            </div>
          </section>

          {submitted && (
            <div role="status" className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-900">
              Bản nháp mock đã ghi nhận ý định tạo ticket. Chưa có dữ liệu nào được gửi hoặc lưu.
            </div>
          )}

          <form id="mock-ticket-form" onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="mock-asset-id">Asset ID</Label>
              <Input id="mock-asset-id" value={asset.id} readOnly />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mock-issue-description">Mô tả vấn đề</Label>
              <Textarea id="mock-issue-description" defaultValue={suggestedDescription} rows={4} />
              <p className="text-xs text-muted-foreground">Prefilled từ risk level, bảo trì và anomaly mới nhất.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="mock-priority">Mức ưu tiên</Label>
                <Select value={priority} onValueChange={setPriority}>
                  <SelectTrigger id="mock-priority" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Khẩn cấp">Khẩn cấp</SelectItem>
                    <SelectItem value="Cao">Cao</SelectItem>
                    <SelectItem value="Trung bình">Trung bình</SelectItem>
                    <SelectItem value="Thấp">Thấp</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="mock-failure-category">Nhóm vấn đề</Label>
                <Input id="mock-failure-category" defaultValue="Kiểm tra theo risk" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mock-technician">Phân công kỹ thuật viên</Label>
              <Select value={technician} onValueChange={setTechnician}>
                <SelectTrigger id="mock-technician" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Chưa phân công">Chưa phân công</SelectItem>
                  <SelectItem value="Lê Hoàng Nam">Lê Hoàng Nam</SelectItem>
                  <SelectItem value="Nguyễn Minh Tuấn">Nguyễn Minh Tuấn</SelectItem>
                  <SelectItem value="Trần Quốc Huy">Trần Quốc Huy</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mock-next-action">Hành động dự kiến</Label>
              <Textarea id="mock-next-action" defaultValue={asset.recommendedAction} rows={3} />
            </div>
          </form>
        </div>

        <SheetFooter className="border-t bg-white p-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Đóng</Button>
          <Button type="submit" form="mock-ticket-form">
            <ClipboardPenLine aria-hidden="true" />
            Ghi nhận bản nháp mock
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
