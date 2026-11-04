# Bot riêng cho kho: GitHub App `txa-repo`

Mặc định bot comment bằng `github-actions[bot]`. Tạo một **GitHub App** thì comment, nhãn và status
hiện dưới tên riêng (`txa-repo[bot]`) với logo riêng.
Không bắt buộc: chưa cài App thì workflow tự dùng token mặc định, mọi thứ vẫn chạy.

## 1. Tạo App

1. Mở <https://github.com/settings/apps/new> (đang đăng nhập bằng tài khoản `TXAVL`).
2. Điền:
   - **GitHub App name**: `txa-repo` (tên toàn cầu, nếu bị trùng thì dùng `txa-repo-bot`).
   - **Homepage URL**: `https://github.com/TXAVL/txa-repo`
   - **Webhook**: bỏ chọn **Active** (App này không cần nhận webhook).
3. **Repository permissions** (để mọi thứ khác là *No access*):

   | Quyền | Mức | Dùng để |
   |---|---|---|
   | Actions | Read and write | chạy lại kiểm tra sau khi chấp nhận agreement |
   | Checks | Read and write | 16 check đánh số trong khung merge |
   | Commit statuses | Read and write | `txa/verified`, `txa/agreement` |
   | Contents | Read and write | bật tự gộp (auto-merge) |
   | Issues | Read and write | comment, nhãn, xoá comment `@txa-repo agree` |
   | Pull requests | Read and write | đọc PR, tự gộp |
   | Metadata | Read-only | (tự có) |

4. **Where can this GitHub App be installed?** → *Only on this account*. Bấm **Create GitHub App**.
5. Trang App mới mở: ghi lại **App ID**; kéo xuống **Private keys** → **Generate a private key**
   (tải về file `.pem`). Ở mục **Display information** tải logo lên.

## 2. Cài App vào kho

Trang App → **Install App** → `TXAVL` → **Only select repositories** → chọn `txa-repo` → Install.

## 3. Đưa khoá vào secret (không để lộ khoá)

```powershell
.\scripts\setup-app.ps1 -AppId 1234567 -KeyFile C:\Users\admin\Downloads\txa-repo.2026-10-27.private-key.pem
```

Script chỉ chạy `gh secret set TXA_APP_ID` và `gh secret set TXA_APP_PRIVATE_KEY` (đọc khoá từ file, không in ra
màn hình). Xong hãy xoá file `.pem` khỏi máy.

## 4. Kiểm tra

Mở một PR mới: comment của bot phải hiện tên `txa-repo` kèm nhãn **bot**. Nếu vẫn hiện `github-actions`,
kiểm tra hai secret đã có chưa (`gh secret list`) và App đã được cài vào `txa-repo`.

Bonus: vì App gộp PR bằng quyền của nó, lần gộp đó tính như một push thật và tự kích hoạt `TXA Publish API`.

## 5. Kho mới, nhớ người đã đồng ý ở kho khác

Kho chạy bot TXA mà bạn dựng (fork) có thể **nhớ người đã đồng ý Thỏa thuận Người đóng góp ở kho khác**, giống cách `winget-pkgs` làm với CLA. Trong kho đó, tạo biến repository `TXA_AGREEMENT_REPOS` (Settings → Secrets and variables → Actions → Variables) với danh sách kho tin cậy, cách nhau bằng dấu phẩy, ví dụ `TXAVL/txa-repo`. Để trống thì bot chỉ tin `TXAVL/txa-repo` (và chính kho đó).

Ai đã có PR được gộp, có comment đồng ý đúng phiên bản thỏa thuận hiện hành ở một kho trong danh sách, sẽ không bị hỏi lại; PR của họ vào thẳng bước tick checklist. Muốn bắt mọi người comment lại thì đặt `RECOGNISE_RETURNING = False` trong `tools/src/txa/ci/agreement.py`.
