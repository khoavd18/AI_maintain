# Báo cáo đơn giản hóa UI/UX

## 1. Kết luận

Giao diện hiện tại giảm đáng kể tải nhận thức trên các đường đi thường dùng: khung ứng dụng navy/white tách công việc khỏi quản trị, dashboard giữ bốn chỉ số dẫn đến hành động cùng các thẻ tình trạng theo quyền, biểu mẫu sự cố/lệnh công việc/kế hoạch bảo trì dùng progressive disclosure, các bảng vận hành quan trọng chuyển thành card trên mobile, thao tác vòng đời và kho có form xác nhận rõ ràng, và Trợ lý bảo trì không còn trình bày như một công cụ debug RAG.

Đánh giá theo mục đích sử dụng:

- **Người dùng lần đầu:** dễ định hướng hơn theo cấu trúc và copy hiện tại, nhưng chưa có nghiên cứu usability với người dùng bảo trì thật nên chưa thể khẳng định mức “dễ học” bằng dữ liệu hành vi.
- **Người dùng thường xuyên:** ít điều khiển cạnh tranh hơn; đổi lại, bộ lọc/thiết lập hiếm cần mở thêm một disclosure và chọn queue không mặc định cần thêm một pointer action.
- **Trình diễn tốt nghiệp:** phạm vi giao diện phù hợp cho một buổi demo có kiểm soát trên dữ liệu seed; unit test, typecheck, lint và production build hiện đã đạt. Live browser suite vẫn phải chạy khi API loopback và biến môi trường kiểm thử được chuẩn bị.
- **Bàn giao kỹ thuật:** có catalog thuật ngữ tập trung, test UI tập trung và hai tài liệu truy vết quyết định. Frontend static/unit/build gate và repository Python gate đã xanh; coverage browser live cho các mutation xuyên suốt vẫn là phần bàn giao cần chốt.

Đây vẫn là lớp hỗ trợ quyết định theo đợt, không phải CMMS hoàn chỉnh, bộ điều khiển bảo trì tự động hay nền tảng production-ready. Chỉ số rủi ro là tín hiệu ưu tiên; Copilot không đưa ra quyết định tự động; quản lý và kỹ thuật viên vẫn chịu trách nhiệm kiểm tra hiện trường, an toàn và quyết định cuối cùng.

## 2. Phương pháp đo

- **Trước:** phiên bản frontend đã commit trước đợt UI/UX này (`HEAD` dùng làm baseline khi đối chiếu diff).
- **Sau:** mã frontend trong worktree tại thời điểm viết báo cáo.
- “Hiển thị mặc định” chỉ tính control/fact/action thấy ngay trước khi mở `details`, menu hoặc tab phụ.
- “Hành động chính” chỉ tính CTA có trọng lượng cao trong vùng nhiệm vụ, không tính liên kết điều hướng chung, phân trang hoặc thao tác admin.
- Số bước có ý nghĩa an toàn/audit được giữ nguyên; không coi việc bỏ bước xác nhận là một cải tiến.
- Các số tĩnh bên dưới được đếm từ component và test hiện có. Kết quả browser, build, thời gian hoàn thành và click thực tế chỉ được ghi cho đúng worktree khi lệnh tương ứng chạy xong; kết quả của một revision trước không được dùng để chứng minh revision hiện tại.

## 3. Giảm độ phức tạp quan sát được

### Khung ứng dụng và màn hình chính

| Hạng mục | Trước | Sau | Thay đổi có thể kiểm chứng |
| --- | ---: | ---: | --- |
| Liên kết điều hướng có thể cùng xuất hiện với tài khoản nhiều quyền | 14 liên kết phẳng | 8 liên kết vận hành + 1 disclosure; 6 liên kết quản trị nằm bên trong | Công việc hằng ngày tách khỏi quản trị nhưng không xóa đích hoặc quyền |
| Badge kỹ thuật trên header | 4 | 0 | Bỏ API, Analytics, RAG và synthetic khỏi normal header |
| Chiều cao tối thiểu của liên kết điều hướng | 40 px | 44 px | Tăng vùng chạm và focus target |
| Chỉ số cạnh tranh trên dashboard | 12 | 4 | Bốn vị trí KPI có liên kết; nội dung lệnh công việc, tồn thấp hoặc thiết bị thay đổi theo quyền thay vì hiển thị dữ liệu người dùng không được phép xem |
| Khối phân bố trên dashboard | 3 biểu đồ tổng hợp | Tối đa 3 thẻ tình trạng vận hành | Thay biểu đồ trang trí bằng tình trạng lệnh công việc, sự cố và phụ tùng; khi không có quyền kho, thẻ cuối dùng mức ưu tiên thiết bị |
| Hành động trên mỗi thiết bị ưu tiên ở dashboard | tối đa 3 | 1 | Chỉ “Báo sự cố” hoặc “Xem thiết bị” theo quyền |
| Bộ lọc thiết bị hiển thị mặc định | 9 | 3 | 6 bộ lọc ít dùng nằm trong “Bộ lọc thêm” |
| Cột bảng thiết bị | 7 | 6 | Gộp tình trạng hiện tại, bỏ cột kỹ thuật riêng |
| Hành động mỗi hàng thiết bị | 2 | 1 | Một nút “Xem thiết bị” có nhãn rõ |
| Control chọn queue sự cố cùng xuất hiện | 9 nút | 1 combobox | Vẫn giữ đủ 9 queue trong danh sách chọn |
| Bộ lọc sự cố hiển thị mặc định | 5 | 3 | Nhóm sự cố và nhóm xử lý chuyển vào disclosure |
| Fact chính ở chi tiết sự cố | 8 | 5 | Phân loại phụ, nguồn, phản hồi đầu và số lần mở lại được thu gọn |
| Bộ lọc lệnh công việc hiển thị mặc định | 10 | 5 | Năm bộ lọc ngày/nguồn nâng cao được thu gọn |
| Fact chính ở chi tiết lệnh công việc | 8 | 4 | Mốc thời gian thành disclosure; version/log ID không còn cạnh tranh |
| Trục định hướng lệnh công việc | 0 bước | 5 bước | Chuẩn bị, Thực hiện, Phụ tùng, Hoàn thành, Xác nhận |
| Tab kho cùng trọng lượng | 10 | 6 + 1 disclosure | Bốn nghiệp vụ hiếm hơn chỉ xuất hiện theo quyền trong “Nghiệp vụ kho” |
| Hành động trên mỗi thông báo ở danh sách đầy đủ | tối đa 3 nút ngang hàng | 1 CTA + 1 disclosure | “Mở chi tiết” giữ trọng lượng chính; đọc/chưa đọc và ẩn nằm trong “Thao tác khác” |
| Bảng vận hành trên màn hình nhỏ | Bảng rộng/cuộn ngang ở nhiều trang | Card có nhãn trường | Phiếu sự cố, người dùng, tác vụ định kỳ, lịch sử chạy, hộp sự kiện, đặt trước và biến động kho có bố cục mobile riêng |
| Nhãn cột audit tiếng Anh | 3 (`Action`, `Resource`, `Outcome`) | 0 | Header và bộ lọc được Việt hóa; mã hành động, loại tài nguyên và mã yêu cầu vẫn được giữ để điều tra |
| Nhóm màu badge trạng thái | 7 nhóm màu cục bộ | 5 tone ngữ nghĩa | Neutral, info, success, warning, danger; luôn kèm text, một số tone có icon |
| Nguồn định nghĩa label/style trạng thái trong ba component badge | 16 map cục bộ | 1 module thuật ngữ dùng chung | Business states không bị giảm hoặc đổi; chỉ hợp nhất cách trình bày |

### Biểu mẫu và giao dịch

| Workflow | Chỉ số | Trước | Sau | Ý nghĩa |
| --- | --- | ---: | ---: | --- |
| Báo sự cố | Trường hiển thị ban đầu | 14 | 4 | Chỉ thiết bị, mô tả, ảnh hưởng và độ khẩn cấp; 10 trường còn lại ở “Thông tin bổ sung” |
| Báo sự cố | Giá trị người dùng bắt buộc phải tự nhập | 2 | 2 | Thiết bị và mô tả; các giá trị phân loại có default. Không giảm yêu cầu backend |
| Tạo lệnh công việc thủ công | Trường hiển thị ban đầu | 11 | 7 | Bốn thiết lập lịch/checklist có default được thu gọn |
| Tạo lệnh công việc thủ công | Giá trị người dùng bắt buộc phải tự cung cấp | 2 | 2 | Tiêu đề và thiết bị; ngày đến hạn và cấu hình khác có default |
| Tạo kế hoạch bảo trì định kỳ | Trường hiển thị ban đầu | 16 | 8 | Tám thiết lập phát hành/thực thi nằm trong “Thiết lập nâng cao”; chu kỳ, ngày bắt đầu/kết thúc và quy tắc cuối tháng vẫn hiển thị |
| Gửi hoàn thành lệnh công việc | Trường hiển thị ban đầu | 10 | 8 | Vật tư lịch sử và cờ theo dõi thêm chuyển vào disclosure |
| Gửi hoàn thành lệnh công việc | Nội dung bắt buộc người dùng phải nhập | 4 | 4 | Kết quả kiểm tra, hành động, ghi chú kỹ thuật viên và tóm tắt; không bỏ thông tin audit |
| Điều chỉnh kho | Fact preview trước commit | 0 | 5 | Tồn hiện tại, lượng điều chỉnh, tồn dự kiến, khả dụng dự kiến, người thực hiện |
| Xuất phụ tùng cho lệnh công việc | Fact preview trước commit | 0 | 5 | Tồn hiện tại, lượng xuất, tồn sau xuất, lệnh hiện tại, người thực hiện |
| Lưu trữ phụ tùng/vị trí kho và đóng đặt trước | Cách nhập lý do | Browser prompt | Form nội tuyến có nhãn, giới hạn và bước hủy/xác nhận | Không đổi named action, expected version hoặc kiểm tra/idempotency hiện có ở backend; loại bỏ prompt khó kiểm soát và khó truy cập |

### Trợ lý bảo trì

| Hạng mục | Trước | Sau | Ghi chú |
| --- | ---: | ---: | --- |
| Khái niệm kỹ thuật được nêu trực tiếp trong normal UI | 6 nhóm | 0 nhóm | Đã bỏ/đổi `RAG`, `Qdrant`, `retrieval`, `asset context/Stable ID`, `risk score` trong panel và raw document ID/source path trong source card |
| Nút gửi câu hỏi | 1 icon-only CTA | 1 CTA có icon + text | “Gửi câu hỏi” có accessible name nhìn thấy |
| Thứ tự phần trả lời chuẩn | Không cố định | 6 phần | Tóm tắt, an toàn, nguyên nhân, bước kiểm tra, chuyển chuyên gia, nguồn |
| Mức bằng chứng | Dễ bị hiểu như trạng thái kỹ thuật | 3 nhãn bằng chữ | “Bằng chứng tốt”, “Bằng chứng hạn chế”, “Không đủ bằng chứng”; không dùng phần trăm confidence |
| Source card | ID/path và metadata kỹ thuật mở sớm | Tiêu đề + phạm vi + trích dẫn; metadata nghiệp vụ thu gọn | Không hiển thị chunk ID, provider, model hoặc collection |

Sáu “nhóm” ở hàng đầu là tập khái niệm được liệt kê, không phải tổng số lần chuỗi xuất hiện. `SOP` và `checklist` được giữ vì là thuật ngữ bảo trì có ý nghĩa đối với công việc, không phải chi tiết hạ tầng.

## 4. Bước, màn hình và click trên đường đi thường dùng

| Workflow | Màn hình trước → sau | Hành động commit/chuyển trạng thái trước → sau | Kết luận |
| --- | ---: | ---: | --- |
| Báo sự cố | 1 → 1 | 1 → 1 | Giảm quyết định nhìn thấy, không thêm wizard |
| Hỏi Trợ lý bảo trì | 1 → 1 | 1 → 1 | Luồng hỏi không dài hơn; câu trả lời dễ quét hơn |
| Tạo lệnh công việc thủ công | 1 → 1 | 1 → 1 | Giữ form inline; cấu hình hiếm thu gọn |
| Đặt trước phụ tùng | 1 → 1 | 1 → 1 | Không gộp đặt trước với xuất kho |
| Xuất phụ tùng | 1 → 1 | 1 → 1 | Thêm preview nhưng transaction vẫn cần xác nhận riêng |
| Hoàn thành rồi xác nhận lệnh công việc | 2 hành động người dùng → 2 | 2 → 2 | Cố ý giữ người hoàn thành và người xác nhận độc lập |
| Giải quyết sự cố nguồn | 1 hành động riêng → 1 | 1 → 1 | Không tự giải quyết khi lệnh công việc hoàn thành/xác nhận |

Không có bằng chứng cho thấy tổng số click của toàn hành trình đã giảm. Các trade-off cụ thể:

- Chọn một queue sự cố không mặc định đổi từ một lần bấm nút sang mở combobox rồi chọn option, tức tăng từ một lên hai pointer action để đổi lấy việc giảm chín lựa chọn cạnh tranh.
- Dùng bộ lọc/thiết lập hiếm cần thêm một lần mở disclosure.
- Đường đi chính và số lần commit không tăng; các bước an toàn, authorization và audit không bị rút ngắn.

Thời gian hoàn thành, lỗi thao tác và tổng click từ đăng nhập đến hoàn tất công việc chưa được đo bằng một nghiên cứu task-based. Không sử dụng các con số giả cho các chỉ số này.

## 5. Bảo toàn quy tắc sản phẩm và an toàn

| Ranh giới | Trạng thái sau thay đổi |
| --- | --- |
| Risk/KPI | Vẫn là analytics theo đợt; UI gọi là chỉ số ưu tiên, không phải xác suất hỏng hoặc cập nhật thời gian thực |
| Copilot | Vẫn là hỗ trợ quyết định; cảnh báo an toàn và insufficient-evidence được ưu tiên, không tự tạo quyết định bảo trì |
| Phiếu sự cố | Vẫn dùng named transitions; tạo/hoàn thành/xác nhận lệnh công việc không tự giải quyết hoặc đóng phiếu |
| Lệnh công việc | State machine backend không đổi; hoàn thành và xác nhận độc lập vẫn là hai bước |
| Bảo trì định kỳ | Không thêm scheduler/startup generation; recurrence và generation vẫn qua service/canonical worker |
| Kho | Đặt trước, xuất, sử dụng, trả và điều chỉnh vẫn tách riêng; preview frontend không phải balance authoritative |
| Audit/RBAC | FastAPI vẫn là security boundary; trang/CTA chỉ ẩn theo quyền để hỗ trợ sử dụng, không thay kiểm tra backend |
| Thông báo | Vẫn in-app only; không thêm email, SMS, push hoặc webhook |

## 6. Các màn hình và file quan trọng đã thay đổi

| Khu vực | File chính | Mục đích |
| --- | --- | --- |
| Điều hướng | `frontend/src/components/app-shell.tsx`, `frontend/src/app/globals.css` | Khung navy/white nhất quán, nhóm công việc/quản trị, thứ tự theo vai trò, bỏ badge kỹ thuật, menu mobile |
| Dashboard | `frontend/src/app/page.tsx`, `frontend/src/components/kpi-card.tsx`, `frontend/src/components/overview-status-card.tsx` | Bốn KPI có liên kết và theo quyền, một CTA theo thiết bị, tối đa ba thẻ tình trạng vận hành |
| Thuật ngữ | `frontend/src/lib/status-terminology.ts`, `frontend/src/components/status-badges.tsx`, `frontend/src/components/ticket-operations-badges.tsx`, `frontend/src/components/inventory-badges.tsx` | Một nguồn nhãn/mô tả/tone tiếng Việt và fallback không lộ enum |
| Thiết bị | `frontend/src/components/asset-browser.tsx`, `frontend/src/components/asset-detail-view.tsx`, `frontend/src/components/asset-detail-tabs.tsx` | Bộ lọc/table gọn, task-first tabs, quản trị kỹ thuật thu gọn |
| Sự cố | `frontend/src/components/ticket-inbox.tsx`, `frontend/src/components/ticket-intake-form.tsx`, `frontend/src/components/ticket-operations-detail.tsx` | Một queue selector, form bốn trường, action theo trạng thái, thông tin phụ thu gọn, danh sách dạng card trên mobile |
| Bảo trì định kỳ | `frontend/src/components/maintenance-plan-workspace.tsx`, `frontend/src/app/maintenance/plans/**` | Việt hóa tên trang/bảng/CTA và thu tám thiết lập nâng cao mà không đổi recurrence/generation |
| Lệnh công việc | `frontend/src/components/work-order-workspace.tsx`, `frontend/src/components/work-order-detail.tsx`, `frontend/src/components/work-order-parts-panel.tsx` | Filter/form progressive disclosure, tiến trình năm bước, completion/verification rõ ràng, preview xuất kho |
| Kho phụ tùng | `frontend/src/components/inventory-section-nav.tsx`, `frontend/src/components/inventory-workspace.tsx`, `frontend/src/components/inventory-action-form.tsx`, `frontend/src/components/part-detail.tsx` | Sáu tab chính, menu theo quyền, preview giao dịch, mobile card và form lý do có kiểm soát cho vòng đời/đặt trước |
| Trợ lý bảo trì | `frontend/src/components/copilot-workspace.tsx`, `frontend/src/components/source-card.tsx`, `frontend/src/lib/copilot.ts` | Ẩn internals, sắp thứ tự câu trả lời, bằng chứng/cảnh báo/nguồn dễ hiểu |
| Thông báo | `frontend/src/components/notification-center.tsx`, `frontend/src/components/notification-workspace.tsx` | Nội dung catalog tiếng Việt, CTA chính nổi trội, thao tác đọc/ẩn thu vào disclosure |
| Quản trị | `frontend/src/components/user-management.tsx`, `frontend/src/components/job-operations-workspace.tsx`, `frontend/src/components/audit-log-workspace.tsx` | Việt hóa nhãn và mobile card cho người dùng/tác vụ/lần chạy/hộp sự kiện; audit giữ mã điều tra |
| Đăng nhập | `frontend/src/app/login/page.tsx` | Bố cục navy/white responsive, semantic `h1`, nhãn tài khoản và ranh giới hỗ trợ quyết định bằng tiếng Việt |
| Browser tests | `frontend/playwright.config.ts`, `frontend/e2e/**` | `_test` attestation, ba vai trò, desktop/mobile, axe, keyboard, overflow và console checks |

## 7. Browser evidence

Playwright hiện định nghĩa **7 test**: 5 desktop Chromium ở `1366 × 768` và 2 mobile Chromium ở `390 × 844`. Test được thiết kế để dùng manager, technician và storekeeper thật trên API loopback đã chứng thực database PostgreSQL có tên kết thúc `_test`.

Coverage đã mã hóa trong suite:

- `/login`, `/`, `/assets`, chi tiết thiết bị và trạng thái not-found an toàn.
- `/tickets`, chi tiết sự cố, `/work-orders` và chi tiết lệnh công việc.
- `/copilot` với câu trả lời có nguồn, cảnh báo an toàn, mismatch và insufficient evidence.
- điều hướng/forbidden theo vai trò; `/inventory`; menu mobile.
- login và mở trang thiết bị bằng bàn phím; `:focus-visible`.
- axe WCAG A/AA cho serious/critical violations tại các điểm kiểm tra.
- heading order, document-level horizontal overflow, `console.error` và page errors.

Kết quả `7/7` và probe 25 tổ hợp route/viewport từng được ghi cho revision trước đợt chỉnh login, dashboard, mobile table, thông báo, audit và form lý do. Các kết quả đó không được dùng làm bằng chứng cho worktree hiện tại. Kiểm tra trực quan mới đã xác nhận riêng trang đăng nhập ở desktop `1366 × 768` và mobile `390 × 844` hiển thị đúng, không tràn ngang. Live `npm run test:e2e` chưa chạy vì chưa có API loopback cùng `PLAYWRIGHT_TEST_DATABASE_URL` và `PLAYWRIGHT_DEMO_PASSWORD`; Docker có sẵn nhưng các tiền điều kiện này chưa được dựng/cấp cho lần chạy hiện tại.

| Bằng chứng cần chốt | Trạng thái worktree hiện tại |
| --- | --- |
| Desktop Chromium `1366 × 768` | Trang đăng nhập đã kiểm tra trực quan: hiển thị đúng, không tràn; 5 live test desktop vẫn chờ |
| Mobile Chromium `390 × 844` | Trang đăng nhập đã kiểm tra trực quan: hiển thị đúng, không tràn; 2 live test mobile vẫn chờ |
| Desktop `1280 × 720`, `1440 × 900` và tablet `768 × 1024` | Chờ chạy lại probe route/viewport |
| Manager / technician / storekeeper / administrator | Chờ xác minh lại landing, điều hướng, quyền từ chối và audit admin |
| Keyboard-only login và đi đến thiết bị | Chờ chạy lại trên bố cục đăng nhập mới |
| Axe serious/critical | Chờ chạy lại trên worktree hiện tại |
| Horizontal overflow | Login đạt ở hai viewport đã xem; dashboard, bảng quản trị và kho vẫn chờ live browser suite/probe |
| Unexpected browser console/page errors | Chờ chạy lại browser suite |
| `_test` database attestation | Guard vẫn có trong cấu hình; chưa thực thi vì thiếu API loopback và biến môi trường database/demo password |

## 8. Quality gates

Không ghi “pass” từ một lần chạy cũ hoặc từ test discovery. Bảng dưới đây ghi đúng các kết quả đã chạy trên worktree sau khi edit giao diện dừng.

| Gate | Command | Trạng thái hiện tại |
| --- | --- | --- |
| Notification regression | `cd frontend; npm test -- src/components/operations-ui.test.tsx` | Pass: 7/7; xác nhận lỗi thông báo của lần chạy song song không tái hiện khi chạy riêng |
| Frontend focused regressions | các suite component liên quan | Pass: nhóm tích hợp 32/32 và nhóm kho 8/8 |
| Frontend unit tests | `cd frontend; npm test -- --maxWorkers=1` | Pass: 23 file, 136 test; 0 fail. Kết quả này thay thế lần chạy song song trước có timeout/lỗi không tái hiện |
| ESLint | `cd frontend; npm run lint` | Pass; exit 0 |
| TypeScript | `cd frontend; npm run typecheck` | Pass; exit 0 |
| Production build | `cd frontend; npm run build` | Pass; exit 0, tạo 32 page |
| Playwright desktop + mobile | `cd frontend; npm run test:e2e` | Chưa chạy: thiếu API loopback, `PLAYWRIGHT_TEST_DATABASE_URL` và `PLAYWRIGHT_DEMO_PASSWORD` |
| Accessibility / keyboard / overflow / console | assertions trong Playwright suite | Chờ kết quả Playwright hiện tại |
| Python repository tests | `.venv\\Scripts\\python.exe -m pytest` | Pass: 347 passed, 73 skipped theo điều kiện tích hợp PostgreSQL, 1 cảnh báo deprecation |
| Ruff | `.venv\\Scripts\\python.exe -m ruff check .` | Pass; exit 0 |
| Whitespace/diff check | `git diff --check` | Pass; không có output |

## 9. Giới hạn UI/UX còn lại

| Mức độ | Giới hạn thực tế | Ảnh hưởng / bước tiếp theo hợp lý |
| --- | --- | --- |
| Cao | Browser suite chưa được chạy lại sau đợt chỉnh giao diện cuối vì thiếu API loopback và biến môi trường kiểm thử; E2E hiện cũng chỉ mở phiếu/lệnh mà chưa thực hiện live các mutation tạo phiếu, tạo lệnh, đặt trước, xuất kho, hoàn thành và xác nhận | Dựng API trên database `_test`, cấp biến môi trường rồi chạy lại suite hiện có; sau đó bổ sung một happy-path có cleanup hoặc seed riêng trong `_test`, không dùng database demo |
| Cao | Chưa có test usability với quản lý, kỹ thuật viên và thủ kho thật | Automated pass không chứng minh dễ hiểu/dễ học; chạy task-based session, ghi thời gian, lỗi và điểm dừng |
| Thấp | Browser evidence hiện chỉ dùng Chromium | Chưa có kiểm tra Firefox/WebKit; bổ sung khi phạm vi trình duyệt triển khai được chủ dự án xác định |
| Trung bình | Dashboard bốn KPI chưa theo cá nhân/ca và chưa có “công việc được giao cho tôi” | Tồn thấp đã xuất hiện theo quyền kho; chỉ cá nhân hóa thêm nếu API hiện có cung cấp dữ liệu chính xác, không tạo analytics tức thời giả |
| Trung bình | Hợp đồng ticket intake không có trường tiêu đề sự cố độc lập | Người dùng chỉ nhập mô tả; cần thay đổi API additive riêng nếu chủ repo cho phép, không tự suy diễn từ frontend |
| Trung bình | Source card chưa hiển thị excerpt hỗ trợ ngắn | Khó đối chiếu nhanh nguồn; bổ sung chỉ khi API có excerpt đã kiểm soát và không lộ nội dung/ID kỹ thuật |
| Trung bình | Bảng audit vẫn ưu tiên desktop và dùng cuộn ngang trên màn hình nhỏ | Header/bộ lọc đã Việt hóa; có thể bổ sung card/detail mobile nhưng phải giữ action code, loại tài nguyên và request ID phục vụ điều tra |
| Thấp | Mô tả phụ của danh sách đặt trước còn câu kỹ thuật về `release`, `expire`, named action và hidden scheduler | Việt hóa copy ở vòng tiếp theo nhưng giữ nguyên tên action trong API/domain và không thêm scheduler khác |
| Thấp | Một số component tương thích cũ ngoài route chính vẫn dùng lẫn `ticket`/`asset` trong copy | Việt hóa khi component đó được đưa lại vào hành trình chính; không tạo entrypoint tương thích mới |
| Thấp | Trục năm bước ở chi tiết lệnh công việc là định hướng, không phải state machine năm trạng thái | Không dùng thanh này để suy ra checklist/phụ tùng đã hoàn tất; nếu cần độ chính xác cao hơn phải tính từ dữ liệu domain hiện có, không thêm trạng thái frontend |

## 10. Tóm tắt trung thực

Đợt thay đổi đã giảm độ phức tạp nhìn thấy mà không rút ngắn các bước bảo vệ dữ liệu, kho, audit hoặc xác nhận độc lập. Mức giảm lớn nhất có số đo rõ là dashboard `12 → 4`, intake sự cố `14 → 4`, queue `9 → 1`, filter lệnh công việc `10 → 5`, kế hoạch bảo trì `16 → 8` trường mở sẵn, kho `10 → 6 + disclosure`, notification `3 → 1 + disclosure`, và technical header `4 → 0`.

Chưa nên tuyên bố UX “đã tốt” chỉ dựa trên các con số này. Unit/typecheck/lint/build và repository Python gate đã đạt, login đã được xem ở hai viewport, nhưng kết luận cuối vẫn phải kết hợp live browser gate, workflow mutation coverage và quan sát người dùng thật.
