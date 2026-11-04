# Thỏa thuận Người đóng góp TXA (Contributor Agreement)

**Phiên bản 1.0** · hiệu lực từ 2026-11-05 · áp dụng cho kho [`TXAVL/txa-repo`](https://github.com/TXAVL/txa-repo) và mọi kho khác chạy bot TXA mà khai báo kho này là kho tin cậy.

Đây là tài liệu bạn xác nhận khi trả lời bot bằng một comment `@txa-repo agree`. Nó ngắn gọn, viết cho người bình thường đọc được. Hãy đọc hết trước khi đồng ý. **Bot không chạy bất cứ bước kiểm tra nào cho tới khi bạn đồng ý và tick hết checklist trong mô tả PR**, nên bạn có thời gian đọc.

---

## 1. Kho này làm gì, để bạn hiểu mình đang đóng góp vào đâu

`txa-repo` là kho gói phần mềm Windows cho công cụ `txapm`. Mỗi gói là **ba thẻ manifest YAML** (`core`, `build`, `about`) nằm trong `manifests/t/TXAVL/<Tên>/<Phiên bản>/`. Manifest **không chứa phần mềm**: nó chỉ trỏ tới link tải chính thức của nhà phát hành, kèm mã SHA-256, dung lượng, kiến trúc CPU và tham số cài im lặng. Người dùng chạy `txapm install <gói>`; TXA tải bộ cài từ trang nhà phát hành, đối chiếu SHA-256, rồi cài. TXA không lưu và không phân phối bộ cài.

Mỗi gói giữ **10 phiên bản mới nhất**. Khi thêm bản mới, bản cũ nhất bị xoá khỏi kho (không bị xoá khỏi lịch sử git).

## 2. Bạn xác nhận điều gì khi comment `@txa-repo agree`

1. **Bạn có quyền gửi.** Bạn là tác giả của các file trong PR, hoặc bạn được phép đóng góp chúng, và việc gửi không vi phạm quyền của người khác (bản quyền, nhãn hiệu, thỏa thuận bảo mật, giấy phép của phần mềm).
2. **Bộ cài là bản chính thức.** Mọi `source.url` là đường dẫn **HTTPS** tới trang tải chính thức của nhà phát hành (hoặc kênh phát hành chính thức của họ, như GitHub Releases của dự án). Không trỏ tới bản đã sửa, bản đóng gói lại, bản crack, hay trang trung gian không phải nhà phát hành.
3. **Thông tin đúng sự thật.** Tên, nhà phát hành, giấy phép (mã SPDX), SHA-256, dung lượng, kiến trúc CPU, phiên bản Windows tối thiểu và tham số cài im lặng là chính xác theo hiểu biết của bạn. Bạn đã lấy SHA-256 và dung lượng từ chính file tải về, không đoán.
4. **Không gây hại.** Bạn không cố ý đưa vào mã độc, quảng cáo ngầm, thu thập dữ liệu trái phép, hay tham số cài đặt làm thay đổi hệ thống ngoài việc cài phần mềm. Bạn không dùng manifest để tấn công người dùng TXA hay hạ tầng của kho.
5. **Đúng chính sách của kho.** Gói phù hợp với [đặc tả manifest](manifest-schema.md) và `policy.txa.yaml`: phần mềm cho Windows 10 (1809) trở lên, bộ cài tối đa 2048 MB, namespace nằm trong danh sách cho phép (hiện là `TXAVL`), không phải phần mềm vi phạm pháp luật.
6. **Bạn đã tự làm các bước kiểm tra** ghi trong checklist của PR (không trùng PR khác, chỉ sửa một manifest, `txacreate validate`, thử `txapm install --manifest`, đúng schema) và tự tick từng ô.

## 3. Giấy phép cho phần bạn đóng góp

Phần bạn đóng góp (các file manifest, và nếu có là mã, tài liệu, bản dịch) được cấp theo **giấy phép MIT**, cùng giấy phép của kho (xem file [`LICENSE`](https://github.com/TXAVL/txa-repo/blob/main/LICENSE)). Bằng việc đồng ý, bạn cho phép mọi người dùng, sao chép, sửa, gộp và phân phối đóng góp đó theo các điều khoản MIT, và cho phép chủ kho đăng nó công khai trong kho, trong REST API `txa.v1` và trên trang chỉ mục.

Điều này **không** áp dụng cho phần mềm mà manifest mô tả: phần mềm, tên, logo và nhãn hiệu của nó vẫn thuộc chủ sở hữu của chúng. Kho chỉ dùng tên và logo để nhận diện phần mềm.

## 4. Điều người duy trì kho được làm

Người duy trì kho là các chủ mã trong `.github/CODEOWNERS` (hiện là `@TXAVL` và `@TXADEV`). Họ được:

- duyệt, yêu cầu sửa, từ chối hoặc đóng PR của bạn mà không cần nêu lý do dài dòng;
- sửa, dịch, định dạng lại hoặc gộp manifest của bạn để giữ kho nhất quán;
- cập nhật gói đã đăng bằng tay hoặc bằng công cụ tự động (bản mới, SHA-256 mới);
- **gỡ** một gói hoặc một phiên bản đã đăng nếu nó sai, nguy hiểm, vi phạm quyền của ai đó, hoặc nhà phát hành yêu cầu.

Nếu bạn là nhà phát hành và muốn gỡ hoặc sửa gói của mình, hoặc phát hiện một gói nguy hiểm, hãy mở một [issue](https://github.com/TXAVL/txa-repo/issues) hoặc báo riêng qua tính năng Security Advisory của GitHub trên kho. Người duy trì sẽ xử lý.

## 5. Thông tin bot ghi lại

Khi bạn đồng ý, bot ghi **tên tài khoản GitHub của bạn** và **số phiên bản của thỏa thuận** (`v=1.0`) vào một comment ẩn của PR (`signed=<tên> v=1.0`) và vào status `txa/agreement`. Nếu bạn gửi thay mặt công ty, tên công ty bạn nhập cũng được ghi. Bot **không** thu thập email, địa chỉ hay thông tin cá nhân nào khác. Dấu vết này nằm công khai trên GitHub như mọi comment trên PR công khai.

## 6. Cách đồng ý, và bot nhớ bạn thế nào

Luồng giống `winget-pkgs`: **đồng ý một lần, bot nhớ**.

1. Bạn mở PR. Bot comment ngay, gắn nhãn `txa:needs-agreement`, và **chưa chạy bước nào**.
2. Bạn trả lời đúng một comment `@txa-repo agree` (hoặc `@txa-repo agree company="Tên công ty"` nếu gửi thay mặt công ty, khi đó bạn xác nhận thêm là bạn có thẩm quyền ràng buộc công ty). Chỉ comment của chính người mở PR mới có hiệu lực. Bot xoá comment đó, gỡ `txa:needs-agreement`, gắn `txa:needs-confirmation`.
3. Bạn tick hết các ô trong mô tả PR. Chỉ khi đã đồng ý **và** tick hết, bot mới chạy 14 bước kiểm tra và 16 check; nhãn chuyển sang `txa:validating`.

**Lần sau:** nếu bạn đã đồng ý và có ít nhất một PR được gộp ở kho này hoặc ở bất kỳ kho nào trong danh sách kho tin cậy (mặc định gồm `TXAVL/txa-repo`), và thỏa thuận chưa đổi phiên bản, bot sẽ **ghi nhận sẵn**: PR mới vào thẳng bước `txa:needs-confirmation`, bạn không phải comment lại. Bạn **vẫn phải tick checklist** của từng PR trước khi bot chạy. Người duy trì không được miễn: họ cũng phải đã đồng ý một lần như mọi người.

Muốn bot không nhớ bạn nữa thì chỉ cần không tiếp tục đóng góp; muốn rút lại một đóng góp đã gộp, mở issue theo mục 4.

## 7. Khi thỏa thuận thay đổi

Thỏa thuận có số phiên bản. Khi người duy trì sửa nội dung quan trọng, họ tăng số phiên bản, ghi vào mục lịch sử bên dưới, và bot sẽ **yêu cầu bạn đồng ý lại** ở PR tiếp theo. Các đóng góp bạn đã gửi trước đó giữ nguyên theo phiên bản bạn đã đồng ý.

| Phiên bản | Ngày | Thay đổi |
|---|---|---|
| 1.0 | 2026-11-05 | Bản đầu tiên. |

## 8. Miễn trừ

Kho và đóng góp được cung cấp "nguyên trạng", không bảo đảm gì, như giấy phép MIT đã nêu. Người duy trì không chịu trách nhiệm về phần mềm của bên thứ ba mà manifest trỏ tới. Tài liệu này do người duy trì kho soạn để làm rõ quy tắc đóng góp, **không phải tư vấn pháp lý**. Nếu tổ chức của bạn cần bảo đảm pháp lý riêng, hãy liên hệ chủ kho qua issue trước khi gửi.
