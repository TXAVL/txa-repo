# Tích hợp TXA vào ứng dụng của bạn

Ứng dụng phát hành qua kho TXA có thể tự nhận ra mình được cài bằng `txapm`, và khi có bản mới thì gọi `txapm`
cập nhật thay vì dùng bộ cập nhật riêng.

English: [app-integration.en.md](app-integration.en.md)

## Biết mình có được cài bằng TXA không

```powershell
txapm which TXAVL.TDrop --json
```

Lệnh luôn thoát với mã 0 và in một dòng JSON:

```json
{"managed": true, "id": "TXAVL.TDrop", "version": "0.3.2", "newest": "0.3.3", "update_available": true, "pinned": false, "dir": null, "source": "txa"}
```

| Trường | Ý nghĩa |
|---|---|
| `managed` | `true` nếu gói có trong danh sách cài của `txapm` |
| `version` / `newest` | bản đang cài / bản mới nhất trong đúng kho gói được cài từ đó |
| `update_available` | có bản mới hay không |
| `pinned` | người dùng đã ghim phiên bản (`txapm pin add`) |
| `dir` | thư mục cài (chỉ có với gói portable) |
| `source` | kho mà gói được cài từ đó |

Gói không được cài bằng TXA thì `managed` là `false` và các trường còn lại là `null` / `false`.

## Cập nhật

Khi `update_available` là `true` và `pinned` là `false`, ứng dụng tự gọi lệnh dưới đây rồi thoát để bộ cài ghi đè file:

```powershell
txapm upgrade TXAVL.TDrop
```

## Chọn phiên bản khi cài

`--version` nhận số đầy đủ hoặc đầu số, và lấy bản mới nhất khớp:

```powershell
txapm install dotnet-sdk-8 --version 8        # bản 8.x.y mới nhất trong kho
txapm install vs2022 --version 17.10          # bản 17.10.x mới nhất
txapm install vs2022 --version 17.10.5        # đúng bản này
```

Không truyền `--version` thì luôn lấy bản mới nhất.

## Phím tắt ngoài desktop

Gói có thể khai báo `shortcut` (`name`, `exe`) trong card `build`. `txapm` không tự tạo shortcut; nó dùng `exe` để kiểm tra chương trình có tồn tại sau khi cài và cài lại một lần nếu bộ gỡ cũ xoá mất. Xem [manifest-schema.md](manifest-schema.md).
