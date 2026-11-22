# Dành cho người phát triển và quản trị kho

English: [maintainers.en.md](maintainers.en.md)

## Cấu trúc repo

- `manifests/t/TXAVL/<AppName>/<X.Y.Z>/` — mỗi phiên bản gồm `core.txa.yaml`, `build.txa.yaml`,
  `about.<lang>.txa.yaml`. Đặc tả từng trường: [manifest-schema.md](manifest-schema.md);
  mẫu có chú thích: [examples](../examples/manifests/t/TXAVL/HelloTool/1.4.2/build.txa.yaml).
- `tools/` — mã nguồn Python của `txapm`, `txacreate`, `txacli`, `txaci`
  (`cd tools && python -m pip install -e .`).
- `web/` — trang chỉ mục (Astro), dựng từ `api/txa/v1/index.json`.
- `scripts/` — `setup-github.ps1` (nhãn, CODEOWNERS, branch protection), `winget-import.ps1`.
- `policy.txa.yaml` — giới hạn dung lượng, namespace, vùng kiểm tra CDN.
- API công khai: `https://txavl.github.io/txa-repo/api/txa/v1/index.json`.

## Workflow trong `.github/workflows/`

| Workflow | Việc |
|---|---|
| `txa-validate`, `txa-gate`, `txa-agreement`, `txa-progress`, `txa-lifecycle`, `txa-review-signal` | bot kiểm định Pull Request: Contributor Agreement, 14 bước kiểm tra, phân loại (bước 15), gộp (bước 16), nhãn `txa:*` |
| `txa-auto-update` | tự cập nhật phiên bản mới của các gói từ nhà phát hành (WinGet, antigravity.google và bản phát hành GitHub của T-Drop, TXAWinSetup; gói viết tay hoặc ghi `auto-update: false` thì bỏ qua) |
| `txa-publish-api` | `txaci build-api`, dựng trang chỉ mục, lấy icon rồi đẩy lên GitHub Pages; chạy khi manifest đổi, mỗi 6 giờ và khi PR duyệt đổi |
| `txa-release` | dựng `txa-windows-x64.zip` / `arm64.zip`, `SHA256SUMS.txt`, `install.ps1` khi đẩy tag `vX.Y.Z` |
| `txa-pypi` | upload gói `txa` lên PyPI khi đẩy tag `vX.Y.Z` (tag phải khớp `txa.__version__`; cần secret `PYPI_API_TOKEN`) |
| `txa-tools-ci` | kiểm tra nhanh `tools/`: gói cài được, các lệnh khởi động được, mọi manifest trong repo vẫn qua kiểm tra offline |

Mỗi gói giữ **10 phiên bản mới nhất**: thêm bản mới thì bản cũ nhất bị xoá trong cùng PR (hoặc lần tự cập nhật).

## Phát hành phiên bản `txa` mới

1. Sửa `__version__` trong `tools/src/txa/__init__.py` và đưa lên `main`.
2. Đẩy tag cùng số phiên bản: `git tag vX.Y.Z` rồi `git push origin vX.Y.Z`.
3. `txa-release` đăng bản phát hành GitHub (dành cho cài bằng `install.ps1`) và `txa-pypi` đăng lên PyPI (dành cho `pipx`).

## Quản trị

- Bot hiện tên riêng (`txa-repo[bot]`) thay vì `github-actions`: [github-app.md](github-app.md).
- Điều khoản người đóng góp: [contributor-agreement.md](contributor-agreement.md).
- Nhập hàng loạt từ WinGet: [winget-import.md](winget-import.md).
- Dựng kho riêng cho tổ chức: [custom-source.md](custom-source.md).
