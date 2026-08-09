export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

export interface StatusPresentation {
  label: string;
  description: string;
  tone: StatusTone;
}

type StatusCatalog = Readonly<Record<string, StatusPresentation>>;

export const riskStatusCatalog = {
  "Thấp": status("Thấp", "Chỉ số ưu tiên rủi ro hiện ở mức thấp.", "success"),
  "Trung bình": status("Trung bình", "Chỉ số ưu tiên rủi ro cần được theo dõi.", "info"),
  Cao: status("Cao", "Thiết bị cần được ưu tiên kiểm tra.", "warning"),
  "Khẩn cấp": status("Khẩn cấp", "Thiết bị cần được đánh giá sớm bởi người có chuyên môn.", "danger"),
} satisfies StatusCatalog;

export const maintenanceDueStatusCatalog = {
  "Chưa đến hạn": status("Chưa đến hạn", "Chưa đến thời điểm bảo trì dự kiến.", "success"),
  "Sắp đến hạn": status("Sắp đến hạn", "Cần chuẩn bị cho kỳ bảo trì sắp tới.", "warning"),
  "Quá hạn": status("Quá hạn", "Ngày bảo trì dự kiến đã qua.", "danger"),
} satisfies StatusCatalog;

export const legacyTicketStatusCatalog = {
  new: status("Mới tạo", "Sự cố đã được ghi nhận và đang chờ xử lý.", "info"),
  in_progress: status("Đang xử lý", "Kỹ thuật viên đang xử lý sự cố.", "info"),
  resolved: status("Đã xử lý", "Sự cố đã có kết quả xử lý.", "success"),
} satisfies StatusCatalog;

export const ticketStatusCatalog = {
  open: status("Mới tiếp nhận", "Sự cố đã được ghi nhận và đang chờ phân công.", "info"),
  assigned: status("Đã phân công", "Sự cố đã có người phụ trách.", "info"),
  in_progress: status("Đang xử lý", "Người phụ trách đang xử lý sự cố.", "info"),
  waiting: status("Đang chờ", "Công việc đang chờ điều kiện cần thiết để tiếp tục.", "warning"),
  resolved: status("Đã giải quyết", "Sự cố đã được giải quyết và chờ đóng khi phù hợp.", "success"),
  closed: status("Đã đóng", "Quy trình xử lý sự cố đã kết thúc.", "neutral"),
  cancelled: status("Đã hủy", "Phiếu sự cố đã được hủy.", "neutral"),
  reopened: status("Đã mở lại", "Sự cố cần được xử lý lại.", "warning"),
} satisfies StatusCatalog;

export const priorityStatusCatalog = {
  low: status("Thấp", "Mức độ ưu tiên thấp.", "neutral"),
  medium: status("Trung bình", "Mức độ ưu tiên trung bình.", "info"),
  high: status("Cao", "Cần được ưu tiên xử lý.", "warning"),
  critical: status("Khẩn cấp", "Cần được xử lý sớm nhất.", "danger"),
} satisfies StatusCatalog;

export const legacyPriorityStatusCatalog = {
  "Thấp": priorityStatusCatalog.low,
  "Trung bình": priorityStatusCatalog.medium,
  Cao: priorityStatusCatalog.high,
  "Khẩn cấp": priorityStatusCatalog.critical,
} satisfies StatusCatalog;

export const anomalySeverityStatusCatalog = {
  "Theo dõi": status("Theo dõi", "Tín hiệu cần tiếp tục quan sát.", "info"),
  "Cảnh báo": status("Cảnh báo", "Tín hiệu bất thường cần được kiểm tra.", "warning"),
  "Ưu tiên": status("Ưu tiên", "Tín hiệu cần được ưu tiên đánh giá.", "danger"),
} satisfies StatusCatalog;

export const assetLifecycleStatusCatalog = {
  planned: status("Dự kiến", "Thiết bị đang trong giai đoạn chuẩn bị đưa vào sử dụng.", "info"),
  active: status("Đang sử dụng", "Thiết bị đang thuộc danh mục sử dụng.", "success"),
  inactive: status("Tạm ngưng", "Thiết bị tạm thời không được sử dụng.", "neutral"),
  retired: status("Đã ngừng khai thác", "Thiết bị đã kết thúc vòng đời khai thác.", "neutral"),
  archived: status("Đã lưu trữ", "Hồ sơ thiết bị được giữ lại để tra cứu lịch sử.", "neutral"),
} satisfies StatusCatalog;

export const assetOperationalStatusCatalog = {
  running: status("Đang vận hành", "Thiết bị đang vận hành bình thường.", "success"),
  warning: status("Cảnh báo", "Thiết bị có tín hiệu cần được theo dõi.", "warning"),
  fault: status("Có sự cố", "Thiết bị đang ghi nhận sự cố vận hành.", "danger"),
  under_maintenance: status("Đang bảo trì", "Thiết bị đang được bảo trì.", "info"),
  out_of_service: status("Ngừng hoạt động", "Thiết bị hiện không phục vụ vận hành.", "neutral"),
} satisfies StatusCatalog;

export const maintenancePlanStatusCatalog = {
  active: status("Đang áp dụng", "Kế hoạch đang được dùng để lập lịch bảo trì.", "success"),
  paused: status("Tạm dừng", "Kế hoạch tạm thời không phát sinh kỳ mới.", "warning"),
  archived: status("Đã lưu trữ", "Kế hoạch chỉ còn được dùng để tra cứu lịch sử.", "neutral"),
} satisfies StatusCatalog;

export const checklistTemplateStatusCatalog = {
  active: status("Đang áp dụng", "Mẫu kiểm tra có thể được chọn cho lệnh công việc mới.", "success"),
  archived: status("Đã lưu trữ", "Mẫu kiểm tra chỉ còn được dùng để tra cứu lịch sử.", "neutral"),
} satisfies StatusCatalog;

export const workOrderStatusCatalog = {
  planned: status("Đã lên kế hoạch", "Lệnh công việc đã được tạo và đang chờ phân công.", "neutral"),
  assigned: status("Đã phân công", "Lệnh công việc đã có kỹ thuật viên phụ trách.", "info"),
  in_progress: status("Đang thực hiện", "Kỹ thuật viên đang thực hiện công việc.", "info"),
  on_hold: status("Tạm dừng", "Công việc đang chờ điều kiện cần thiết để tiếp tục.", "warning"),
  completed: status("Chờ xác nhận", "Kỹ thuật viên đã gửi hoàn thành; cần người khác xác nhận.", "warning"),
  verified: status("Đã xác nhận", "Công việc đã được xác nhận độc lập.", "success"),
  cancelled: status("Đã hủy", "Lệnh công việc đã được hủy.", "neutral"),
} satisfies StatusCatalog;

export const slaStatusCatalog = {
  not_started: status("Chưa bắt đầu", "Thời hạn xử lý chưa bắt đầu tính.", "neutral"),
  active: status("Đang tính thời hạn", "Thời hạn xử lý đang được tính.", "info"),
  paused: status("Tạm dừng", "Thời hạn xử lý đang tạm dừng theo quy định.", "warning"),
  met: status("Đúng hạn", "Yêu cầu đã được hoàn thành trong thời hạn.", "success"),
  due_soon: status("Sắp đến hạn", "Thời hạn xử lý sắp kết thúc.", "warning"),
  breached: status("Đã quá hạn", "Thời hạn xử lý đã bị vượt quá.", "danger"),
  stopped: status("Đã dừng", "Thời hạn xử lý không còn được tính.", "neutral"),
} satisfies StatusCatalog;

export const stockStateStatusCatalog = {
  healthy: status("Còn hàng", "Số lượng khả dụng đang trên ngưỡng đặt lại.", "success"),
  low_stock: status("Sắp hết", "Số lượng khả dụng đang ở mức thấp.", "warning"),
  at_reorder_point: status("Sắp hết", "Số lượng khả dụng đã chạm ngưỡng đặt lại.", "warning"),
  out_of_stock: status("Hết hàng", "Hiện không còn số lượng khả dụng.", "danger"),
  overstock: status("Dư tồn kho", "Số lượng tồn đang vượt mức tối đa đã cấu hình.", "info"),
} satisfies StatusCatalog;

export const inventoryLifecycleStatusCatalog = {
  active: status("Đang hoạt động", "Mục này có thể được dùng cho giao dịch mới.", "success"),
  inactive: status("Ngừng hoạt động", "Mục này không dùng cho giao dịch mới.", "neutral"),
  archived: status("Đã lưu trữ", "Mục này chỉ còn được dùng để tra cứu lịch sử.", "neutral"),
} satisfies StatusCatalog;

export const inventoryStatusCatalog = {
  active: status("Đã đặt trước", "Phụ tùng đang được giữ cho công việc.", "info"),
  planned: status("Chưa đặt trước", "Nhu cầu phụ tùng đã được ghi nhận nhưng chưa giữ hàng.", "neutral"),
  partially_reserved: status("Đặt trước một phần", "Mới giữ được một phần số lượng cần thiết.", "warning"),
  reserved: status("Đã đặt trước", "Đã giữ đủ số lượng cần thiết.", "info"),
  partially_issued: status("Đã xuất một phần", "Mới xuất một phần số lượng đã yêu cầu.", "warning"),
  issued: status("Đã xuất kho", "Đã xuất đủ số lượng đã yêu cầu.", "success"),
  partially_consumed: status("Đã dùng một phần", "Mới sử dụng một phần số lượng đã xuất.", "warning"),
  fulfilled: status("Đã hoàn tất", "Nhu cầu hoặc đặt trước đã được xử lý đủ.", "success"),
  released: status("Đã hủy đặt trước", "Số lượng giữ trước đã được trả về kho khả dụng.", "neutral"),
  expired: status("Đã hết hạn", "Đặt trước đã hết hiệu lực.", "neutral"),
  replaced: status("Đã thay thế", "Đặt trước này đã được thay bằng bản ghi mới.", "neutral"),
  cancelled: status("Đã hủy", "Nhu cầu phụ tùng đã được hủy.", "neutral"),
} satisfies StatusCatalog;

export function resolveStatusPresentation(
  catalog: StatusCatalog,
  code: string,
  fallbackLabel?: string,
): StatusPresentation {
  const known = catalog[code];
  if (known) return known;

  const candidate = fallbackLabel?.trim();
  const looksTechnical =
    !candidate ||
    candidate === code ||
    /^[a-zA-Z0-9]+(?:_[a-zA-Z0-9]+)+$/.test(candidate);
  const label = looksTechnical ? "Chưa xác định" : candidate;
  return status(label, `Trạng thái hiện tại: ${label}.`, "neutral");
}

function status(
  label: string,
  description: string,
  tone: StatusTone,
): StatusPresentation {
  return { label, description, tone };
}
