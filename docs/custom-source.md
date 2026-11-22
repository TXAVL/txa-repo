# Kho nguồn riêng và tự dựng kho

Ngoài kho chính `txa`, bạn có thể thêm kho riêng: phần mềm nội bộ công ty, bản build riêng của nhóm…
Kho riêng chỉ cần phục vụ cùng REST API `txa.v1` (hai file JSON tĩnh), hoặc đơn giản là một thư mục chứa `manifests/`.

English: [custom-source.en.md](custom-source.en.md)

## Quản lý kho nguồn với `txapm source`

| Muốn làm gì | Lệnh |
|---|---|
| Xem các kho | `txapm source` |
| Thêm kho HTTPS | `txapm source add congty https://pkgs.congty.vn/api/txa/v1` |
| Thêm kho là thư mục (ổ mạng, máy cá nhân) | `txapm source add noibo \\server\share\txa` |
| Kho riêng tư cần token | `txapm source add congty <url> --token-env CONGTY_TOKEN` |
| Cho phép tải bộ cài từ máy chủ LAN | `txapm source add congty <url> --allow-lan` |
| Tắt / bật một kho | `txapm source disable txa` · `txapm source enable txa` |
| Xoá kho | `txapm source remove congty` |
| Làm mới / sao lưu cấu hình | `txapm source update` · `txapm source export` |
| Về mặc định (chỉ kho `txa`) | `txapm source reset` |
| Chỉ tìm / cài từ một kho | `txapm search app -s congty` · `txapm install App -s congty` |

- Kho được hỏi theo thứ tự: `txa` trước, rồi các kho thêm sau. Nếu cùng một Id có ở nhiều kho,
  TXA dừng và yêu cầu chọn bằng `-s <kho>` để tránh cài nhầm.
- Gói nhớ nó được cài từ kho nào, nên `txapm upgrade` luôn lấy bản mới từ đúng kho đó.
- Token không bao giờ được ghi vào file cấu hình: TXA chỉ lưu **tên biến môi trường**, và chỉ gửi
  token tới đúng máy chủ của kho đó.
- Kho phải dùng HTTPS (ngoại trừ `http://localhost` để thử nghiệm).

## Tự dựng một kho

1. Tạo thư mục có `manifests/<chữ-cái>/<Namespace>/<AppName>/<X.Y.Z>/` (soạn card bằng
   `txacreate new <url> --dry-run --out <thư-mục>` cho nhanh; cấu trúc card xem
   [manifest-schema.md](manifest-schema.md)).
2. Dùng ngay dạng thư mục: `txapm source add noibo D:\kho-txa`. Hoặc sinh REST API tĩnh:
   ```powershell
   txaci build-api --root D:\kho-txa --out D:\kho-txa-site
   ```
3. Đưa thư mục `D:\kho-txa-site` lên bất kỳ máy chủ HTTPS nào (IIS, nginx, GitHub Pages, S3…), rồi
   `txapm source add congty https://<máy-chủ>/api/txa/v1`.

## Có cả bot kiểm định 16 bước như kho chính

Fork repo `TXAVL/txa-repo`, thay namespace trong `policy.txa.yaml`, rồi chạy:

```powershell
scripts\setup-github.ps1 -Owner <tổ-chức>
```

Script cấu hình nhãn, `CODEOWNERS` và bảo vệ nhánh. Muốn bot hiện tên riêng thay vì `github-actions`
thì xem [github-app.md](github-app.md).
