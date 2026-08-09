# Kiểm toán đơn giản hóa UI/UX

## Phạm vi và cách đọc

Tài liệu này đối chiếu giao diện frontend trước đợt đơn giản hóa với mã nguồn hiện tại. Phạm vi gồm các hành trình chính trong Next.js: đăng nhập, điều hướng, tổng quan, thiết bị, sự cố, bảo trì định kỳ, lệnh công việc, kho phụ tùng, Trợ lý bảo trì, thông báo, người dùng nội bộ, tác vụ nền và nhật ký hệ thống.

Mỗi mục tách rõ quyết định UX (`giữ`, `đơn giản`, `ẩn/bỏ`) và phần **đã triển khai thực tế**. Một đề xuất chưa có trong mã được ghi là giới hạn còn lại, không được mô tả như tính năng đã hoàn thành. Các thay đổi chỉ tác động lớp trình bày; quyền, trạng thái nghiệp vụ, giao dịch kho, xác nhận độc lập, audit và lịch phân tích theo đợt vẫn do backend kiểm soát.

## Vấn đề xuyên suốt đã phát hiện

- Điều hướng của tài khoản có nhiều quyền từng là một danh sách phẳng tối đa 14 đích; công việc hằng ngày và quản trị có cùng trọng lượng.
- Header từng hiển thị trạng thái API, Analytics, RAG và dữ liệu synthetic cho người dùng nghiệp vụ.
- Nhiều trang dùng lẫn tiếng Việt với `asset`, `ticket`, `work order`, `priority`, `SLA`, `reservation`, `movement`, `provider` hoặc mã trạng thái kỹ thuật.
- Dashboard, bộ lọc, bảng và biểu mẫu đặt quá nhiều chỉ số hoặc điều khiển ngang hàng ngay khi mở trang.
- Hành động hiếm, lịch sử và cấu hình kỹ thuật cạnh tranh với hành động tiếp theo của người dùng; một số thay đổi vòng đời từng dùng browser prompt để lấy lý do.
- Các badge trạng thái dùng nhiều map nhãn/màu cục bộ, làm cùng một trạng thái có nguy cơ được trình bày khác nhau.
- Copilot nhấn mạnh cơ chế RAG/Qdrant/truy xuất thay vì câu hỏi bảo trì, cảnh báo an toàn và nguồn tham khảo dễ hiểu.

## Điều hướng và khung ứng dụng

**Người dùng chính:** tất cả vai trò đã đăng nhập; thứ tự ưu tiên riêng cho kỹ thuật viên, thủ kho và helpdesk.

**Nhiệm vụ chính:** đi thẳng đến khu vực công việc được phép và nhận biết trang hiện tại.

**Vấn đề:** 14 đích tối đa nằm trong một danh sách phẳng; các mục quản trị lẫn với công việc; bốn badge kỹ thuật chiếm header; nhãn thương hiệu và trạng thái dùng thuật ngữ nội bộ.

**Giữ:** kiểm tra quyền ở frontend để định hướng sử dụng, trạng thái điều hướng hiện tại, trung tâm thông báo, thông tin vai trò và nút đăng xuất. Việc ẩn liên kết không thay thế kiểm tra quyền của FastAPI.

**Đơn giản:** tám khu vực vận hành có tên ngắn; sắp xếp theo vai trò; tách quản trị thành nhóm cấp hai; tăng vùng chạm và giữ trạng thái focus rõ ràng.

**Ẩn/bỏ khỏi giao diện thường:** API/Analytics/RAG/synthetic badges, thông tin batch trong header và các đích quản trị không được cấp quyền.

**Hành động chính:** chọn khu vực công việc tiếp theo.

**Đã triển khai:** `app-shell.tsx` có tám đích vận hành, nhóm “Thiết lập & quản trị” thu gọn, thứ tự theo vai trò, active state bằng `aria-current`, vùng chạm tối thiểu 44 px và cùng cấu trúc trong menu mobile. Sidebar navy, vùng nội dung trắng và header gọn tạo một hệ thị giác nhất quán; header chỉ còn tìm kiếm điều hướng, thông báo, danh tính và đăng xuất. Thông điệp “Hỗ trợ quyết định” giữ đúng ranh giới sản phẩm.

## Đăng nhập (`/login`)

**Người dùng chính:** tất cả người dùng nội bộ.

**Nhiệm vụ chính:** đăng nhập bằng tài khoản đã được quản trị viên cấp.

**Vấn đề:** tiêu đề cũ là một `div` trình bày như tiêu đề thay vì `h1`; nhãn “Username hoặc email” trộn tiếng Anh; trang chưa tạo được mối liên hệ thị giác với khung ứng dụng sau đăng nhập.

**Giữ:** hai trường định danh và mật khẩu, trạng thái đang xử lý, lỗi an toàn và điều hướng về trang phù hợp với vai trò.

**Đơn giản:** dùng một tiêu đề nhiệm vụ và nhãn tiếng Việt trực tiếp; tách vùng giới thiệu khỏi form mà không đưa chi tiết kỹ thuật hoặc tài khoản mẫu vào trang.

**Ẩn/bỏ:** chi tiết kiến trúc AI và thông tin tài khoản mẫu.

**Hành động chính:** “Đăng nhập”.

**Đã triển khai:** bố cục responsive dùng vùng giới thiệu navy và card đăng nhập trắng, thu gọn phần giới thiệu trên màn hình nhỏ; thêm `h1` “Đăng nhập hệ thống bảo trì” và đổi nhãn thành “Tên đăng nhập hoặc email”. Trang nêu rõ đây là lớp hỗ trợ quyết định, không thêm thông tin đăng nhập hoặc bí mật vào giao diện.

## Tổng quan (`/`)

**Người dùng chính:** quản lý bảo trì và kỹ sư phụ trách có quyền xem analytics.

**Nhiệm vụ chính:** biết việc nào cần chú ý ngay và mở đúng hồ sơ để xử lý.

**Vấn đề:** 12 chỉ số ở nhiều khối cùng ba biểu đồ phân bố khiến ưu tiên bị loãng; copy nhấn mạnh batch/transactional view; mỗi thiết bị ưu tiên có nhiều hành động ngang hàng.

**Giữ:** sự cố đang mở, bảo trì quá hạn, thiết bị có chỉ số ưu tiên cao, lệnh công việc quá hạn, tình trạng phụ tùng theo quyền, danh sách thiết bị cần kiểm tra và sự cố mới cập nhật.

**Đơn giản:** bốn chỉ số có liên kết và thay đổi theo quyền; một danh sách ưu tiên; một hành động phù hợp quyền trên mỗi thiết bị; tối đa ba thẻ tình trạng vận hành; diễn giải chỉ số rủi ro là hỗ trợ ưu tiên, không phải xác suất hỏng.

**Ẩn/bỏ:** bốn chỉ số hỗ trợ ít dẫn đến hành động, bốn KPI lệnh công việc lặp lại, ba biểu đồ tổng hợp cũ và diễn giải kỹ thuật về nguồn dữ liệu. Dữ liệu trạng thái cần thiết được trình bày lại trong các thẻ vận hành có liên kết.

**Hành động chính:** “Báo sự cố” nếu có quyền; nếu không, “Xem thiết bị”.

**Đã triển khai:** vùng đầu trang còn bốn KPI có thể bấm; vị trí KPI thứ ba và thứ tư dùng dữ liệu lệnh công việc, tồn thấp hoặc thiết bị theo quyền. Khối ưu tiên đổi thành “Thiết bị cần ưu tiên kiểm tra”; mỗi hàng/thẻ còn một hành động; mã thiết bị và mã phiếu là liên kết trực tiếp. Cột bên phải có tình trạng lệnh công việc, sự cố và phụ tùng, hoặc mức ưu tiên thiết bị khi người dùng không có quyền kho. Risk score được ghi “chỉ số ưu tiên” và có cảnh báo không phải xác suất hỏng trong phần chi tiết.

**Giới hạn còn lại:** dashboard chưa có biến thể riêng cho quản lý theo ca hoặc “công việc được giao cho tôi”. Tồn thấp đã có trong KPI theo quyền kho; mọi số liệu vẫn theo hợp đồng batch/transactional hiện có, không phải cập nhật thời gian thực.

## Danh sách thiết bị (`/assets`)

**Người dùng chính:** quản lý, kỹ sư, kỹ thuật viên; thủ kho chỉ khi quyền cho phép.

**Nhiệm vụ chính:** tìm thiết bị theo tình trạng hiện tại và mở hồ sơ.

**Vấn đề:** chín đầu vào lọc được mở đồng thời; bảy cột pha trộn lifecycle, vận hành, kỹ thuật và batch; mỗi hàng có hai hành động; nhiều nhãn `asset`, `lifecycle`, `risk batch`.

**Giữ:** tìm kiếm, trạng thái vận hành, mức ưu tiên, loại, vị trí, lịch bảo trì, phân trang và khả năng xem thiết bị lưu trữ khi cần.

**Đơn giản:** tìm kiếm + hai bộ lọc hay dùng ở mức đầu; sáu bộ lọc còn lại trong “Bộ lọc thêm”; sáu cột tập trung vào nhận dạng, vị trí, trạng thái và tình trạng.

**Ẩn/bỏ:** nút icon báo sự cố khỏi từng hàng, lifecycle badge của thiết bị đang hoạt động bình thường và chi tiết hãng/model thành một dòng phụ.

**Hành động chính:** “Xem thiết bị”.

**Đã triển khai:** ba đầu vào lọc mặc định, disclosure báo số bộ lọc đang dùng, đặt lại một lần, bảng sáu cột, một nút theo hàng, card riêng cho mobile và label đầy đủ liên kết với control.

## Chi tiết thiết bị (`/assets/[assetId]`)

**Người dùng chính:** kỹ sư và kỹ thuật viên; quản lý khi đánh giá ưu tiên.

**Nhiệm vụ chính:** hiểu trạng thái thiết bị, xem sự cố hiện có và báo sự cố khi cần.

**Vấn đề:** tab Risk là mặc định; thuật ngữ analytics xuất hiện sớm; các tab quản lý hồ sơ, QR, tệp và lịch sử luôn mở cạnh nội dung vận hành; “Tạo ticket kiểm tra” không phải cách gọi quen thuộc.

**Giữ:** nhận dạng thiết bị, trạng thái, chỉ số ưu tiên, lịch bảo trì, số sự cố đang mở, cảnh báo quan sát được, hướng xử lý tham khảo, sự cố, bảo trì, bất thường và lịch sử.

**Đơn giản:** ưu tiên sự cố và lịch sử bảo trì trước analytics; đổi tên tab và mô tả sang tiếng Việt nghiệp vụ; chỉ hiển thị lifecycle khi khác “đang sử dụng”.

**Ẩn/bỏ:** hồ sơ quản trị, tệp, QR và lịch sử quản lý sau disclosure “Thông tin kỹ thuật và quản lý”.

**Hành động chính:** “Báo sự cố”; “Hỏi trợ lý bảo trì” là hành động phụ.

**Đã triển khai:** tab “Sự cố” là mặc định; thứ tự tab theo công việc; thông tin quản lý được thu gọn; copy `Risk/Anomaly/Ticket/Asset ID` được thay bằng “Chỉ số ưu tiên/Tín hiệu bất thường/Sự cố/Mã thiết bị”. Không tạo lệnh công việc hoặc thay đổi asset trực tiếp ngoài service hiện có.

## Danh sách sự cố (`/tickets`)

**Người dùng chính:** helpdesk, quản lý, kỹ sư và kỹ thuật viên có phạm vi đọc tương ứng.

**Nhiệm vụ chính:** chọn đúng nhóm cần xử lý, nhận biết mức ưu tiên/thời hạn và mở phiếu.

**Vấn đề:** chín nút queue cùng xuất hiện; năm bộ lọc ngang hàng; thuật ngữ `ticket`, `priority`, `category`, `support group`, `SLA`; cột cập nhật làm bảng rộng nhưng không chỉ ra hành động.

**Giữ:** toàn bộ chín queue nghiệp vụ, tìm kiếm, trạng thái, mức ưu tiên, nhóm sự cố, nhóm xử lý, phân công và thời hạn do backend tính.

**Đơn giản:** một selector “Nhóm cần xử lý”; ba bộ lọc chính; hai bộ lọc phụ và reset trong disclosure; sáu cột nghiệp vụ dễ quét.

**Ẩn/bỏ:** chín nút cạnh tranh, cột “Cập nhật” khỏi bảng chính và các enum/mã trạng thái khỏi nhãn hiển thị.

**Hành động chính:** “Báo sự cố”; trong mỗi hàng là “Xem phiếu”.

**Đã triển khai:** queue chuyển từ chín nút sang một combobox nhưng vẫn giữ đủ lựa chọn; filter/category/group được Việt hóa và progressive disclosure; status/priority dùng catalog tập trung; empty/error state hướng dẫn điều chỉnh danh sách thay vì nói về queue kỹ thuật. Bảng desktop chuyển thành card có nhãn trường và CTA toàn chiều rộng trên mobile.

## Báo sự cố (`/tickets/new`)

**Người dùng chính:** helpdesk, quản lý, kỹ sư hoặc người được cấp quyền tạo phiếu.

**Nhiệm vụ chính:** ghi nhận nhanh thiết bị, mô tả và mức cần ưu tiên.

**Vấn đề:** tối đa 14 trường lộ ra ngay, gồm phân loại, điều phối và PII người báo; tên trường lẫn tiếng Anh; lỗi validation chưa tự đưa focus tới trường đầu tiên.

**Giữ:** thiết bị, mô tả, ảnh hưởng, độ khẩn cấp; ma trận ưu tiên ở backend; tất cả trường tùy chọn vẫn gửi qua hợp đồng API hiện có khi người dùng mở và điền.

**Đơn giản:** bốn trường ban đầu; hệ thống hiển thị preview mức ưu tiên; nhóm lỗi, phân loại, điều phối, ghi chú và người báo trong “Thông tin bổ sung”.

**Ẩn/bỏ:** thông tin PII và routing khỏi luồng mặc định; không hiển thị mã SLA policy sau khi tạo.

**Hành động chính:** “Lưu phiếu sự cố”.

**Đã triển khai:** 14 trường tối đa xuống bốn trường nhìn thấy ban đầu; asset từ đường dẫn được điền sẵn; submit chống lặp; giá trị form được giữ khi lỗi; lỗi gắn `aria-describedby` và focus trường không hợp lệ đầu tiên; thông báo thành công dùng tên nghiệp vụ.

**Giới hạn còn lại:** API hiện không có trường tiêu đề sự cố độc lập, nên frontend không thể thêm trường này mà vẫn giữ nguyên hợp đồng.

## Chi tiết sự cố (`/tickets/[ticketId]`)

**Người dùng chính:** người được giao, helpdesk và quản lý điều phối.

**Nhiệm vụ chính:** hiểu điều gì xảy ra, ai phụ trách, thời hạn nào đang chạy và hành động hợp lệ tiếp theo.

**Vấn đề:** tám fact kỹ thuật luôn hiển thị trước phần người báo; SLA dùng mã policy/calendar/timezone; assignment, priority và policy override cạnh tranh với transition chính; timeline dùng rule code.

**Giữ:** vòng đời đầy đủ tám trạng thái, ảnh hưởng/khẩn cấp, người phụ trách, đồng hồ thời hạn, trao đổi, liên kết lệnh công việc và lịch sử append-only.

**Đơn giản:** năm fact chính; thời hạn bằng lời; nút transition được đặt dưới “Hành động tiếp theo”; tên hành động mô tả rõ trạng thái đích.

**Ẩn/bỏ:** phân loại chi tiết, nguồn tiếp nhận, phản hồi đầu tiên, số lần mở lại và người báo trong disclosure; assignment/đổi ưu tiên/đổi chính sách trong khu “Điều phối và thiết lập bổ sung”; rule code được đổi thành nhãn người dùng.

**Hành động chính:** hành động hợp lệ theo trạng thái, ví dụ “Bắt đầu xử lý”, “Đánh dấu đã xử lý”, “Đóng phiếu” hoặc “Mở lại”.

**Đã triển khai:** thông tin chính giảm từ tám xuống năm fact; nội dung phụ và quản trị thu gọn; lý do/confirm có nhãn theo hành động; timeline đổi thành “Lịch sử cập nhật”; SLA đổi thành “Thời hạn phản hồi và xử lý”. Việc tạo/hoàn tất/xác nhận lệnh công việc vẫn không tự giải quyết phiếu.

## Bảo trì định kỳ (`/maintenance/plans`, `/maintenance/plans/[planId]`)

**Người dùng chính:** quản lý bảo trì và kỹ sư có quyền quản lý kế hoạch.

**Nhiệm vụ chính:** xem kỳ sắp đến, tạo/chỉnh kế hoạch và phát hành lệnh đến hạn bằng thao tác được bảo vệ.

**Vấn đề:** tên trang và bảng dùng `preventive plan`, `assignee`, `checklist template`; phần phát hành dùng `Dry run`, `occurrence`; ghi chú cuối trang lộ API/CLI/worker; form tạo kế hoạch dài và nhiều trường lịch kỹ thuật cùng xuất hiện.

**Giữ:** chu kỳ bounded, timezone IANA, lead time, grace period, người phụ trách, checklist version, dry-run và xác nhận trước phát hành. Không được che thông tin làm thay đổi lịch hoặc chính sách backlog.

**Đơn giản:** gọi thống nhất “Bảo trì định kỳ”, “Kế hoạch”, “Người phụ trách”, “Mẫu kiểm tra”; giữ thông tin kế hoạch và lịch chính mở sẵn, đưa cấu hình phát hành/thực thi ít dùng vào vùng nâng cao.

**Ẩn/bỏ:** giải thích API/CLI/worker và thuật ngữ occurrence khỏi giao diện nghiệp vụ; không bỏ timezone hoặc quy tắc tháng cuối vì ảnh hưởng lịch.

**Hành động chính:** “Tạo kế hoạch bảo trì” trên danh sách; “Lưu thay đổi” hoặc hành động trạng thái phù hợp trên chi tiết.

**Đã triển khai:** page title, mô tả, KPI, header bảng, nút tạo và trường form đã Việt hóa; chi tiết nhấn mạnh lịch sắp tới và kỳ chưa phát hành. Form tạo giảm từ 16 xuống tám trường mở sẵn; lead time, grace period, thời lượng, múi giờ, ưu tiên/người phụ trách mặc định, mẫu kiểm tra và hướng dẫn nằm trong “Thiết lập nâng cao”. Nếu validation của trường bắt buộc trong disclosure thất bại, vùng này được mở để người dùng sửa. Không thay recurrence service hoặc cơ chế generation.

**Giới hạn còn lại:** múi giờ và các giá trị phát hành vẫn phải có trong vùng cấu hình vì chúng ảnh hưởng trực tiếp đến ngày đến hạn. Quy tắc cuối tháng vẫn hiển thị cạnh lịch chính; disclosure không được hiểu là hệ thống tự chọn lịch thay người quản lý.

## Danh sách và tạo lệnh công việc (`/work-orders`)

**Người dùng chính:** quản lý, kỹ sư và kỹ thuật viên; quyền tạo/phân công tùy vai trò.

**Nhiệm vụ chính:** tìm công việc theo trạng thái/hạn/người phụ trách và tạo lệnh thủ công khi thực sự cần.

**Vấn đề:** mười bộ lọc lộ ra cùng lúc; nút lịch và tạo nằm sau các filter; tên gọi `work order`, `asset ID`, `source ticket`, UUID; form tạo có 11 trường cùng trọng lượng.

**Giữ:** toàn bộ bộ lọc server-side, ngày đến hạn + grace, loại, ưu tiên, người phụ trách, nguồn sự cố/kế hoạch và checklist snapshot.

**Đơn giản:** năm bộ lọc chính; năm bộ lọc còn lại trong “Bộ lọc thêm”; nút tạo ở đầu panel; bảy trường tạo lệnh thường dùng và bốn thiết lập có default trong disclosure.

**Ẩn/bỏ:** timezone, grace, thời lượng và mẫu kiểm tra khỏi trạng thái ban đầu; không hiển thị UUID như nhãn hướng dẫn.

**Hành động chính:** “Tạo lệnh công việc”.

**Đã triển khai:** mười xuống năm bộ lọc mặc định; form 11 xuống bảy trường mặc định, bốn trường trong “Thiết lập bổ sung”; thuật ngữ và empty/error states được Việt hóa; mobile dùng card thay cho bảng rộng.

## Chi tiết lệnh công việc (`/work-orders/[workOrderId]`)

**Người dùng chính:** kỹ thuật viên thực hiện, quản lý/kỹ sư phân công và người xác nhận độc lập.

**Nhiệm vụ chính:** nhận biết bước hiện tại, thực hiện checklist/phụ tùng, gửi hoàn thành và xác nhận đúng thẩm quyền.

**Vấn đề:** tám fact trong summary, version và ID nguồn cạnh tranh với nhiệm vụ; lịch sử/evidence luôn mở; copy “workflow/backend/maintenance log”; các hành động chưa có trục tiến trình rõ.

**Giữ:** state machine backend, checklist an toàn, cảnh báo phụ tùng, hoàn thành tạo hoặc liên kết đúng một maintenance log, xác nhận bởi người khác, tệp minh chứng được bảo vệ và lịch sử append-only.

**Đơn giản:** tiến trình năm nhãn định hướng; bốn fact chính; hành động hợp lệ theo trạng thái; form hoàn thành tập trung vào kết quả thực thi.

**Ẩn/bỏ:** mốc thời gian, ảnh/tài liệu và timeline sau disclosure; version và maintenance-log ID khỏi summary; hai trường bổ sung khỏi form hoàn thành ban đầu.

**Hành động chính:** tùy trạng thái: “Bắt đầu công việc”, “Tiếp tục công việc”, “Gửi hoàn thành” hoặc “Xác nhận công việc”. Hủy được tách bằng kiểu destructive và vẫn yêu cầu xác nhận/lý do ở backend hoặc UI hiện có.

**Đã triển khai:** thêm trục “Chuẩn bị → Thực hiện → Phụ tùng → Hoàn thành → Xác nhận”; summary tám xuống bốn fact; hai disclosure cho minh chứng/lịch sử; form hoàn thành mười xuống tám trường mặc định và hai trường bổ sung thu gọn; copy nhấn mạnh xác nhận độc lập. Hoàn thành/xác nhận không tự xử lý phiếu nguồn và không tự động xuất/tiêu thụ/trả phụ tùng.

**Giới hạn còn lại:** bước “Phụ tùng” chỉ là định hướng trình bày, không phải trạng thái mới và không được dùng như bằng chứng phụ tùng đã xử lý.

## Kho phụ tùng (`/inventory/**` và phần phụ tùng của lệnh công việc)

**Người dùng chính:** thủ kho; kỹ sư/kỹ thuật viên chỉ thấy thao tác được cấp quyền trong ngữ cảnh lệnh công việc.

**Nhiệm vụ chính:** biết lượng khả dụng, xử lý đặt trước/xuất/trả/điều chuyển/điều chỉnh và xem lịch sử.

**Vấn đề:** mười tab cùng trọng lượng; nhiều nhãn `on-hand`, `reserved`, `available`, `movement`, `reservation`, `stock location`; thao tác xuất/điều chỉnh thiếu preview số lượng sau giao dịch; lưu trữ phụ tùng/vị trí kho và đóng đặt trước từng dùng browser prompt để lấy lý do.

**Giữ:** `khả dụng = tồn thực tế - đã đặt trước`, lịch sử append-only, named actions, idempotency key, row locks/backend constraints, tách nhu cầu/đặt trước/xuất/sử dụng/trả và cảnh báo tồn thấp.

**Đơn giản:** sáu khu hằng ngày; bốn nghiệp vụ hiếm hơn trong menu theo quyền; tên số lượng và trạng thái bằng tiếng Việt; copy tập trung vào quyết định kho; form nội tuyến nêu rõ tác động và lý do trước hành động vòng đời.

**Ẩn/bỏ:** nghiệp vụ không được cấp quyền; giải thích transaction/ledger/backend khỏi normal copy; không cho client gửi balance tính sẵn.

**Hành động chính:** theo trang, ví dụ “Xác nhận nhập kho”, “Xác nhận điều chuyển”, “Xác nhận điều chỉnh”, “Đặt trước” hoặc “Xác nhận xuất kho”.

**Đã triển khai:** mười tab xuống sáu tab chính + disclosure “Nghiệp vụ kho” có tối đa bốn liên kết theo quyền; thuật ngữ tồn kho được chuẩn hóa; điều chỉnh và xuất kho thêm preview tồn hiện tại, số lượng thao tác, tồn dự kiến, ngữ cảnh công việc/người thực hiện. Danh sách đặt trước và biến động kho có card mobile. Giải phóng/hết hạn đặt trước, lưu trữ vị trí kho và thay đổi vòng đời mã phụ tùng dùng form có nhãn, hủy/xác nhận và lý do tối thiểu thay cho browser prompt; CTA vòng đời được Việt hóa. Backend vẫn kiểm tra lại số lượng, version và idempotency trong transaction; không có tự động mua hàng.

**Giới hạn còn lại:** mô tả phụ của danh sách đặt trước vẫn còn câu kỹ thuật về `release`, `expire`, named action và hidden scheduler; nên Việt hóa ở vòng copy tiếp theo nhưng không đổi tên action trong API/domain.

## Trợ lý bảo trì (`/copilot`)

**Người dùng chính:** kỹ sư, kỹ thuật viên và quản lý có quyền sử dụng Copilot.

**Nhiệm vụ chính:** chọn đúng thiết bị/sự cố, hỏi một câu bảo trì, đọc cảnh báo và kiểm tra nguồn.

**Vấn đề:** giao diện nói về “RAG”, “Qdrant”, retrieval, asset context, stable ID và risk score; câu trả lời không có thứ tự quét nhất quán; source card lộ ID/path kỹ thuật; nút gửi chỉ có icon; câu gợi ý gây cuộn ngang.

**Giữ:** thiết bị và sự cố liên quan, câu hỏi tự do, gợi ý, trạng thái có nguồn/dự phòng, mức bằng chứng, mismatch, insufficient evidence, cảnh báo an toàn, escalation và nguồn tham khảo.

**Đơn giản:** “Trợ lý bảo trì”; selector hiển thị tên/vị trí thay vì bắt đầu bằng ID; câu trả lời theo “Tóm tắt → Cảnh báo an toàn → Nguyên nhân có thể → Các bước nên kiểm tra → Khi nào cần chuyển chuyên gia → Nguồn tham khảo”.

**Ẩn/bỏ:** provider/model/embedding/Qdrant/chunk/raw retrieval/fallback code, document ID/path và chi tiết prompt khỏi normal view; không hiển thị phần trăm confidence.

**Hành động chính:** “Gửi câu hỏi”.

**Đã triển khai:** header và loading copy chỉ mô tả việc đối chiếu tài liệu; nút gửi có text; IME composition không gửi nhầm; output sắp thứ tự, loại trùng cảnh báo, có nhãn nguồn/dự phòng và ba mức bằng chứng bằng chữ; mismatch/insufficient evidence/prompt injection/unavailable có thông báo an toàn; source card chỉ còn tiêu đề, loại/phạm vi, trích dẫn được dùng và metadata nghiệp vụ trong disclosure. Câu hỏi được giữ khi lỗi để thử lại.

**Giới hạn còn lại:** nguồn hiện không có excerpt hỗ trợ ngắn trong card; chất lượng câu trả lời vẫn phụ thuộc tài liệu đã index và không thay thế kiểm tra hiện trường.

## Thông báo (`/notifications` và panel header)

**Người dùng chính:** mọi vai trò có quyền đọc thông báo, với dữ liệu owner-isolated.

**Nhiệm vụ chính:** biết sự kiện nào cần chú ý và mở đúng hồ sơ liên quan.

**Vấn đề:** trang đầy đủ cho mỗi dòng từng hiển thị đến ba hành động ngang hàng; mức độ, đã đọc/chưa đọc và màu cùng lặp lại.

**Giữ:** in-app only, unread count, severity bằng chữ, lọc, đọc/chưa đọc/ẩn và deep link chỉ khi có quyền đối với entity.

**Đơn giản:** ưu tiên “Mở chi tiết”, giảm trọng lượng thao tác đọc/ẩn và giữ một bộ lọc ngắn.

**Ẩn/bỏ:** không thêm email, SMS, push, webhook hoặc payload kỹ thuật.

**Hành động chính:** “Mở chi tiết” khi thông báo có đích được phép; thao tác đọc/chưa đọc/ẩn là hành động phụ.

**Đã triển khai:** khung ứng dụng chỉ giữ chuông thông báo thay vì bốn badge kỹ thuật; panel có accessible name, unread count, empty/error state và permission-aware link. Tiêu đề/nội dung theo catalog được Việt hóa tại lớp hiển thị mà không đổi payload API. Trên trang đầy đủ, “Mở chi tiết” là CTA nổi trội và chiếm toàn chiều rộng trên mobile; đọc/chưa đọc/ẩn nằm trong “Thao tác khác”; bộ lọc mức độ dùng select có label rõ.

## Nhật ký hệ thống (`/admin/audit`)

**Người dùng chính:** quản trị viên có quyền đọc audit.

**Nhiệm vụ chính:** tra cứu ai đã làm gì, lúc nào, với kết quả nào và thay đổi an toàn nào được ghi nhận.

**Vấn đề:** bảng dày, nhãn `Action/Resource/Outcome`, request ID và action code phù hợp kỹ thuật nhưng chưa thân thiện; không phải màn hình cho người dùng bảo trì thường.

**Giữ:** tính append-only, actor, thời gian, resource, outcome, before/after summary, request ID phục vụ điều tra và phân trang. Không hiển thị token, cookie, Authorization header, password hoặc file body.

**Đơn giản:** giới hạn trang trong nhóm quản trị; Việt hóa bộ lọc, header và kết quả nhưng giữ mã thô cần cho điều tra.

**Ẩn/bỏ:** toàn bộ trang khỏi điều hướng vai trò không được cấp quyền; không đưa audit payload thô vào màn hình nghiệp vụ.

**Hành động chính:** lọc và tra cứu sự kiện.

**Đã triển khai:** “Nhật ký hệ thống” nằm trong nhóm quản trị thu gọn và chỉ xuất hiện khi có quyền. `Action/Resource/Outcome` được đổi thành “Hành động/Tài nguyên/Kết quả”; option kết quả và loại tài nguyên có nhãn tiếng Việt. Action code, resource type/id và request ID vẫn hiện dưới dạng mã để không làm mất dữ liệu điều tra; before/after chỉ được tóm tắt, không đưa bí mật hoặc file body vào giao diện.

**Giới hạn còn lại:** bảng audit vẫn dùng cuộn ngang trên màn hình nhỏ; chưa có card/detail mobile riêng vì cần bảo toàn mật độ dữ liệu điều tra.

## Người dùng và tác vụ nền (`/admin/users`, `/admin/jobs`)

**Người dùng chính:** quản trị viên có quyền quản lý tài khoản nội bộ hoặc vận hành worker.

**Nhiệm vụ chính:** cập nhật vai trò/trạng thái người dùng; quan sát worker, bốn tác vụ PM7 cho phép, lịch sử chạy và hộp sự kiện; chỉ kích hoạt lại hoặc chạy thủ công qua hành động được cấp quyền.

**Giữ:** RBAC của FastAPI, không tự tạo người dùng lúc startup, catalog đóng gồm preventive generation, SLA/escalation evaluation, batch analytics refresh và inventory reorder detection, trạng thái/lease/retry/dead-letter bền vững trong PostgreSQL và lỗi an toàn cho người vận hành.

**Đơn giản:** Việt hóa nhãn tài khoản/kỹ thuật viên và trình bày người dùng, tác vụ định kỳ, lịch sử chạy, hộp sự kiện dưới dạng card có nhãn trên mobile; desktop vẫn giữ bảng để quét nhanh.

**Ẩn/bỏ:** không thêm cron tùy ý, shell/Python/SQL/module/function/workflow, queue trong bộ nhớ hoặc kênh thông báo bên ngoài.

**Hành động chính:** “Lưu” thay đổi người dùng; với tác vụ nền là hành động trạng thái hoặc kích hoạt thủ công hợp lệ theo quyền và trạng thái hiện tại.

**Đã triển khai:** bảng người dùng và ba bảng tác vụ/lần chạy/hộp sự kiện chuyển thành card ở viewport nhỏ, CTA mở toàn chiều rộng khi cần và label kỹ thuật thường gặp được Việt hóa. Các khóa tác vụ/event ID vẫn được giữ ở phần mã phục vụ đối chiếu; không mở rộng catalog worker.

## Kết luận kiểm toán

Luồng thường dùng đã chuyển rõ từ “hiển thị toàn bộ khả năng hệ thống” sang “hiển thị việc cần làm và mở rộng khi cần”, đặc biệt ở tổng quan, thiết bị, sự cố, kế hoạch/lệnh công việc, kho, thông báo và Trợ lý bảo trì. Các bảng quản trị quan trọng cũng có đường đọc trên mobile. Các bước an toàn hoặc có ý nghĩa audit không bị gộp: giải quyết phiếu vẫn là hành động riêng; hoàn thành và xác nhận lệnh công việc vẫn tách biệt; mọi giao dịch kho vẫn là named action; worker vẫn chỉ có bốn tác vụ cho phép; analytics vẫn cập nhật theo đợt; mọi khuyến nghị vẫn là hỗ trợ quyết định của con người.

Các khoản nợ UX rõ nhất còn lại là bảng audit trên mobile, một số copy kỹ thuật ở trang đặt trước, thiếu excerpt ngắn trong nguồn Copilot và chưa có usability study với người dùng thật. Form kế hoạch và trang thông báo đã được xử lý trong vòng hiện tại. Unit test tuần tự, typecheck, lint, production build, Python repository tests và Ruff đã đạt; login đã được xem ở desktop/mobile. Live Playwright vẫn chờ API loopback cùng URL PostgreSQL `_test` và demo credential bắt buộc; trạng thái chi tiết nằm trong báo cáo đo lường.
