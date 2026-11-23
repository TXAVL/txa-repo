# Đặc tả Cấu trúc Manifest TXA (TXA Manifest Specification)

Tài liệu hướng dẫn quy chuẩn kỹ thuật và các quy định cho từng trường trong bộ 3 thẻ manifest của gói phần mềm TXA (TXA v1).

---

## Tổng quan (Overview)

Mỗi bản phát hành phần mềm trong kho TXA được định nghĩa bằng một thư mục gồm **3 loại thẻ manifest YAML**:

```
manifests/
└── <ký_tự_đầu>/
    └── <Namespace>/
        └── <AppName>/
            └── <Phiên_bản_X.Y.Z>/
                ├── core.txa.yaml             # Thẻ định danh và metadata cốt lõi
                ├── build.txa.yaml            # Thẻ bộ cài, kiến trúc CPU và tham số
                ├── about.en-US.txa.yaml      # Thẻ mô tả (Tiếng Anh)
                └── about.vi-VN.txa.yaml      # Thẻ mô tả (Tiếng Việt - tuỳ chọn)
```

---

## 1. Thẻ cốt lõi: `core.txa.yaml`

Định nghĩa thông tin định danh duy nhất của gói trong toàn bộ hệ thống.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/core.schema.json
txa: 1
kind: core
package:
  id: TXAVL.Everything
  version: 1.4.1
  channel: stable
  alias: evt
  aliases:
    - everything
locale:
  default: en-US
tags:
  - search
  - file-search
  - filesystem
```

### Các trường quy định:
| Trường | Bắt buộc | Kiểu | Mô tả & Giới hạn |
| :--- | :---: | :--- | :--- |
| `txa` | Có | `int` | Phiên bản đặc tả schema TXA (hiện tại là `1`). |
| `kind` | Có | `string` | Phải là `core`. |
| `package.id` | Có | `string` | Định danh gói: dạng `<Namespace>.<AppName>` (PascalCase). Ví dụ: `TXAVL.Everything`. |
| `package.version`| Có | `string` | Phiên bản phần mềm: chuẩn SemVer nghiêm ngặt `X.Y.Z` (ví dụ `1.4.1`). |
| `package.channel`| Không | `string` | Nhánh phát hành: `stable` (mặc định) hoặc `beta`. |
| `package.alias` | Không | `string` | Tên lệnh tắt ngắn gọn để người dùng gõ `txapm install <alias>` (chữ thường, chữ số, dấu gạch ngang, 2-32 ký tự). |
| `locale.default` | Có | `string` | Mã ngôn ngữ chính của gói (mặc định: `en-US` hoặc `vi-VN`). |
| `tags` | Không | `array` | Danh sách từ khóa tìm kiếm (tối đa 16 tag, viết thường, không chứa ký tự đặc biệt). |

---

## 2. Thẻ bộ cài & nền tảng: `build.txa.yaml`

Quy định cấu hình thực thi bộ cài đặt cho từng kiến trúc CPU trên Windows.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/build.schema.json
txa: 1
kind: build
ref: TXAVL.Everything@1.4.1
platform:
  os: windows
  min_build: 10.0.17763
scope: machine
targets:
  - arch: x64
    engine: msi
    source:
      url: https://www.voidtools.com/Everything-1.4.1.1032.x64.msi
      sha256: 4E7A80885AAB8566B750C56A2A2B3E7C3C1F4920BCC53777E07F5EEB9E1F7485
      size: 2351104
    switches:
      silent: /qn /norestart
      progress: /qb! /norestart
  - arch: arm64
    engine: exe
    source:
      url: https://www.voidtools.com/Everything-1.4.1.1032.ARM64.zip
      sha256: 23DCA1A64574BF30C9988BBAF5F1D201A0EC7EE9A15E12270AE92A52183CCCC8
      size: 1933207
    switches:
      silent: /s
      progress: /s
```

### Các trường quy định:
| Trường | Bắt buộc | Kiểu | Mô tả & Giới hạn |
| :--- | :---: | :--- | :--- |
| `ref` | Có | `string` | Mã tham chiếu khớp chính xác: `<package.id>@<package.version>`. |
| `platform.min_build`| Có | `string` | Bản dựng Windows tối thiểu, ví dụ `10.0.17763` (Windows 10 1809+). |
| `scope` | Có | `string` | Phạm vi cài đặt: `machine` (toàn máy - yêu cầu quyền Admin) hoặc `user` (người dùng hiện tại). |
| `targets` | Có | `array` | Danh sách bộ cài theo CPU. **Mỗi kiến trúc (`x64`, `x86`, `arm64`) chỉ được khai báo tối đa 1 lần**. |
| `targets[].arch` | Có | `string` | Kiến trúc CPU: `x64`, `x86`, `arm64`, `arm`, hoặc `neutral`. |
| `targets[].engine` | Có | `string` | Công nghệ bộ cài: `inno`, `nsis`, `msi`, `wix`, `exe`, hoặc `portable`. |
| `targets[].source.url` | Có | `string` | Đường dẫn HTTPS tải bộ cài trực tiếp từ trang chính thức. |
| `targets[].source.sha256` | Có | `string` | Mã băm SHA-256 (64 ký tự hex viết hoa). |
| `targets[].switches.silent` | Tuỳ loại | `string` | Tham số cài đặt im lặng (với `exe` bắt buộc phải có, ví dụ `/S`, `/VERYSILENT`). |
| `targets[].shortcut` | Không | `object` | Phím tắt ngoài desktop mà `txapm` tạo sau khi cài, dành cho bộ cài chạy im lặng không tự tạo. Gồm `name` (tên file `.lnk`), `exe` (đường dẫn chương trình, cho phép biến như `%LOCALAPPDATA%`; với gói portable là đường dẫn trong thư mục đã giải nén) và `args` (tuỳ chọn). Đã có shortcut cùng tên thì bỏ qua; người dùng tắt bằng `--no-shortcut`. `exe` còn dùng để kiểm tra sau khi cài: nếu chương trình không có ở đó (bộ cài cũ xoá nhầm file mới khi nâng cấp) thì `txapm` cài lại một lần. |

---

## 3. Thẻ thông tin mô tả: `about.<lang>.txa.yaml`

Cung cấp thông tin hiển thị, giấy phép và mô tả cho người dùng. Hỗ trợ đa ngôn ngữ độc lập (`about.en-US.txa.yaml`, `about.vi-VN.txa.yaml`, v.v.).

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/TXAVL/txa-repo/main/tools/src/txa/schemas/about.schema.json
txa: 1
kind: about
ref: TXAVL.Everything@1.4.1
lang: en-US
name: Everything
publisher: voidtools
author: David Carpenter
summary: Everything is a search engine that locates files and folders by filename instantly for Windows.
homepage: https://www.voidtools.com/
license:
  name: MIT
  url: https://www.voidtools.com/License.txt
```

### Các trường quy định:
| Trường | Bắt buộc | Kiểu | Mô tả & Giới hạn |
| :--- | :---: | :--- | :--- |
| `lang` | Có | `string` | Mã ngôn ngữ định dạng BCP 47 (ví dụ `en-US`, `vi-VN`). Phải khớp với tên file. |
| `name` | Có | `string` | Tên hiển thị đầy đủ của phần mềm (ví dụ: `Everything`). |
| `publisher` | Có | `string` | Tên nhà phát hành hoặc tổ chức phát triển. |
| `summary` | Có | `string` | Mô tả ngắn gọn (từ 10 đến 160 ký tự), không được lặp lại nguyên văn tên phần mềm. |
| `description` | Không | `string` | Mô tả chi tiết chức năng phần mềm (tối đa 5000 ký tự). |
| `homepage` | Không | `string` | Trang chủ chính thức của phần mềm (phải bắt đầu bằng `https://`). |
| `license.name` | Có | `string` | Mã giấy phép chuẩn SPDX (ví dụ: `MIT`, `GPL-3.0-or-later`, `Apache-2.0`, `Proprietary`, `Freeware`). |
| `license.url` | Tuỳ loại | `string` | Đường dẫn điều khoản giấy phép (bắt buộc với giấy phép `Proprietary` hoặc phi SPDX). |

