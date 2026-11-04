# TXA

Cài phần mềm Windows bằng một dòng lệnh. TXA tải bộ cài từ trang chính thức của nhà phát hành,
kiểm tra chữ ký số và mã SHA-256, rồi cài **im lặng**, không phải bấm Next.

```powershell
txapm install TXAVL.HelloTool
```

[![PyPI](https://img.shields.io/pypi/v/txa)](https://pypi.org/project/txa/)
[![Release](https://img.shields.io/github/v/release/TXAVL/txa-repo)](https://github.com/TXAVL/txa-repo/releases)

---

## Cài đặt

Yêu cầu: Windows 10 (1809) trở lên, x64 hoặc ARM64.

### Cách 1 — PowerShell (không cần Python)

Mở PowerShell (không cần quyền admin) và chạy:

```powershell
irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1 | iex
```

Script tải bản mới nhất, kiểm tra SHA-256, cài vào `%LOCALAPPDATA%\TXA` và tự thêm vào PATH.
Mở cửa sổ terminal mới là dùng được.

Script **hỏi ngôn ngữ trước khi bắt đầu cài** (English / Tiếng Việt, Enter = theo ngôn ngữ Windows) và in mọi
thông báo, bảng lệnh bằng ngôn ngữ đã chọn. Bỏ qua câu hỏi (cài tự động) bằng `-Lang en` / `-Lang vi` hoặc biến `TXA_LANG`:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1))) -Lang vi
```

### Cách 2 — pipx (nếu đã có Python 3.10+)

```powershell
pipx install txa
```

Chưa có pipx thì chạy `python -m pip install --user pipx` rồi `python -m pipx ensurepath`, sau đó mở terminal mới.

Kiểm tra:

```powershell
txapm --version
```

---

## Dùng `txapm`

| Muốn làm gì | Lệnh |
|---|---|
| Tìm phần mềm | `txapm search notepad` |
| Xem thông tin một gói | `txapm show TXAVL.HelloTool` |
| Xem kho đang có những phiên bản nào | `txapm show TXAVL.HelloTool --versions` (kèm CPU/ngôn ngữ, đánh dấu bản mới nhất và bản đã cài) |
| Cài bản mới nhất | `txapm install TXAVL.HelloTool` |
| Cài một phiên bản cụ thể | `txapm install TXAVL.HelloTool --version 1.4.2` |
| Chọn phiên bản từ danh sách trong kho | `txapm install TXAVL.HelloTool --choose` |
| Cài nhưng vẫn xem tiến trình | `txapm install TXAVL.HelloTool --progress` |
| Cài với giao diện gốc của bộ cài | `txapm install TXAVL.HelloTool --interactive` |
| Chỉ tải về, không cài | `txapm install TXAVL.HelloTool --download-only` |
| Thử một manifest trên máy trước khi gửi | `txapm install --manifest <thư-mục>` |
| Xem gói đã cài | `txapm list` |
| Xem gói có bản mới | `txapm list --upgrade-available` |
| Nâng cấp một gói | `txapm upgrade TXAVL.HelloTool` |
| Nâng cấp tất cả | `txapm upgrade --all` |
| Gỡ cài đặt | `txapm uninstall TXAVL.HelloTool` |
| Sao lưu danh sách gói | `txapm export pkgs.json` |
| Cài lại cả bộ trên máy mới | `txapm import pkgs.json` |
| Xem **mọi** phần mềm trên máy, đánh dấu cái nào có trong TXA | `txapm list --all` |
| Giữ nguyên phiên bản, không cho `upgrade --all` đụng vào | `txapm pin add TXAVL.HelloTool` |
| Bỏ giữ / xem danh sách đang giữ | `txapm pin remove TXAVL.HelloTool` · `txapm pin list` |
| Tải bộ cài + manifest về thư mục (mặc định Downloads) | `txapm download TXAVL.HelloTool -d D:\setup` |
| Xem các kho nguồn | `txapm source` (xem mục [Kho nguồn riêng](#kho-nguồn-riêng)) |
| Tìm kiếm / cài trực tiếp gói từ WinGet qua `txapm` | `txapm wg search <từ-khóa>` · `txapm wg install <id>` |
| Kiểm tra sức khỏe hệ thống, kho nguồn, WinGet & cache | `txapm doctor` |
| Dọn dẹp bộ cài tải tạm và file log cài đặt | `txapm clean` · `txapm clean --all` |
| Xem danh sách hoặc đọc nội dung log cài đặt | `txapm log` · `txapm log <tên-gói>` |
| Xem chi tiết vị trí cài đặt, PATH và nguồn của một gói | `txapm which <tên-gói>` |
| Thông tin cài đặt, đường dẫn, tài khoản | `txapm --info` |

Gói nào có tên ngắn (alias) thì gõ tên ngắn cũng được, ví dụ `txapm install hellotool`.
Một số lệnh có tên viết tắt: `add` = install, `rm` = uninstall, `ls` = list, `find` = search.

### Phần mềm có sẵn trong kho

| Gói (`txapm install …`) | Tên ngắn | Phần mềm | Phiên bản |
|---|---|---|---|
| `TXAVL.NotepadPlusPlus` | `notepadpp` | Notepad++ — trình soạn thảo mã nguồn | 8.9.8 |
| `TXAVL.SevenZip` | `7zip` | 7-Zip — nén và giải nén | 26.5.0 |
| `TXAVL.VLC` | `vlc` | VLC media player | 3.0.24 |
| `TXAVL.Firefox` | `firefox` | Mozilla Firefox | 158.0.1 |
| `TXAVL.Git` | `git` | Git cho Windows | 2.56.0 |
| `TXAVL.Python` | `python` | Python | 3.14.10 |
| `TXAVL.NodeJS` | `nodejs`, `node`, `npm`, `npx` | Node.js (đã kèm npm) | 24.22.1 |
| `TXAVL.NVM` | `nvm` | NVM for Windows — quản lý nhiều bản Node.js | 2.0.1 |
| `TXAVL.FFmpeg` | `ffmpeg`, `ffprobe`, `ffplay` | FFmpeg — xử lý video và âm thanh (gói portable) | 9.0.2 |
| `TXAVL.OBSStudio` | `obs` | OBS Studio — quay và phát trực tiếp | 33.0.0 |
| `TXAVL.ShareX` | `sharex` | ShareX — chụp và quay màn hình | 21.0.0 |
| `TXAVL.Audacity` | `audacity` | Audacity — chỉnh sửa âm thanh | 4.0.1 |
| `TXAVL.Obsidian` | `obsidian` | Obsidian — ghi chú Markdown | 1.14.5 |
| `TXAVL.Chrome` | `chrome` | Google Chrome — trình duyệt web | 156.0.8078 |
| `TXAVL.VisualStudioCode` | `vscode` | Visual Studio Code — trình soạn thảo mã nguồn | 1.142.0 |
| `TXAVL.Brave` | `brave` | Brave Browser — trình duyệt web bảo mật | 155.1.97 |
| `TXAVL.Spotify` | `spotify` | Spotify — nghe nhạc trực tuyến | 1.3.6 |
| `TXAVL.Discord` | `discord` | Discord — trò chuyện và giao tiếp | 1.0.9266 |
| `TXAVL.TelegramDesktop` | `telegram` | Telegram — nhắn tin bảo mật | 7.3.3 |
| `TXAVL.PuTTY` | `putty` | PuTTY — SSH và telnet client | 0.85.0 |
| `TXAVL.Rustup` | `rustup` | Rustup — bộ cài đặt và quản lý Rust | 1.29.1 |
| `TXAVL.GIMP` | `gimp` | GIMP — phần mềm chỉnh sửa ảnh mã nguồn mở | 3.2.6 |
| `TXAVL.OhMyPosh` | `ohmyposh` | Oh My Posh — tùy biến giao diện terminal | 31.9.1 |
| `TXAVL.WinSCP` | `winscp` | WinSCP — SFTP, FTP, WebDAV client | 6.7.0 |
| `TXAVL.PowerToys` | `powertoys` | Microsoft PowerToys — bộ công cụ tiện ích nâng cao cho Windows | 0.101.2362 |
| `TXAVL.Postman` | `postman` | Postman — nền tảng phát triển và kiểm thử API | 12.34.2 |
| `TXAVL.GitHubCLI` | `gh` | GitHub CLI — làm việc với GitHub từ dòng lệnh | 2.101.0 |
| `TXAVL.GitHubDesktop` | `githubdesktop` | GitHub Desktop — quản lý Git trực quan | 3.6.7 |
| `TXAVL.DockerDesktop` | `docker` | Docker Desktop — quản lý container trên Windows | 4.80.0 |
| `TXAVL.CMake` | `cmake` | CMake — hệ thống quản lý build đa nền tảng | 4.4.2 |
| `TXAVL.Blender` | `blender` | Blender — dựng hình và hoạt hình 3D mã nguồn mở | 5.2.0 |
| `TXAVL.Steam` | `steam` | Steam — nền tảng quản lý và chơi game | 2.10.91 |
| `TXAVL.UnityHub` | `unityhub` | Unity Hub — quản lý các phiên bản Unity Editor và dự án | 3.22.2 |
| `TXAVL.Cloudflared` | `cloudflared` | Cloudflare Tunnel client | 2026.10.1 |
| `TXAVL.VietTelex` | `viettelex` | VietTelex — bộ gõ tiếng Việt gọn nhẹ | 1.3.2 |

Ví dụ: `txapm install vlc` hoặc `txapm install TXAVL.VLC`. Danh sách đầy đủ và mới nhất: `txapm search "" `
hoặc xem [trang chỉ mục](https://txavl.github.io/txa-repo/). Mỗi gói chỉ trỏ tới link tải **chính thức** của nhà
phát hành; TXA không lưu lại bộ cài, và luôn đối chiếu SHA-256 trước khi chạy.

`npm` không có bộ cài riêng, nó đi kèm Node.js: `txapm install npm` sẽ cài Node.js (có sẵn `node`, `npm`, `npx`).
Cần đổi giữa nhiều bản Node.js thì dùng thêm `txapm install nvm`.

### Kho giữ bao nhiêu phiên bản?

Mỗi gói giữ **10 phiên bản mới nhất** (bản mới nhất trừ đi 9 bản). Thêm một bản mới thì bản cũ nhất bị xoá
trong cùng Pull Request (hoặc lần tự cập nhật). Cài bản cũ hơn bất kỳ lúc nào miễn bản đó còn trong kho:
`txapm install <gói> --version <bản>`.

Một số gói (ví dụ Cốc Cốc) có bộ cài riêng cho từng **ngôn ngữ**: `txapm` tự chọn bản đúng với ngôn ngữ hiển thị
của Windows (trong manifest: `locale: vi-VN` / `en-US` trên từng target; ngôn ngữ khác dùng bản tiếng Anh).

### Khi cài, TXA làm gì?

Mỗi lần cài, màn hình báo từng bước `[1/5]` … `[5/5]` kèm thanh tiến trình có tốc độ và thời gian còn lại:

1. **Resolve** — lấy thông tin gói từ kho `txa-repo` (đã được kiểm định 16 bước và có người duyệt), chọn đúng bộ cài cho máy bạn (ARM64 → x64 → x86), kiểm tra phiên bản Windows tối thiểu.
2. **Download** — tải về `%TEMP%\txa\…`.
3. **Verify** — so mã SHA-256. Sai một byte là **xoá file và dừng**.
4. **Install** — cài im lặng (gói cài cho toàn máy sẽ hiện hộp thoại UAC xin quyền admin). Log nằm ở `%LOCALAPPDATA%\TXA\logs`.
5. **Record** — ghi vào danh sách đã cài để `upgrade`, `uninstall`, `export` dùng.

**Gói portable** (như FFmpeg) không có bộ cài: TXA giải nén vào `%LOCALAPPDATA%\TXA\apps\<Id>\<phiên-bản>`,
thêm thư mục chương trình vào PATH của **riêng bạn** (không cần quyền admin) rồi nhắc mở terminal mới.
`upgrade` thay bản cũ, `uninstall` xoá thư mục và gỡ khỏi PATH.

---

## Kho nguồn riêng

Ngoài kho chính `txa`, bạn có thể thêm kho riêng: phần mềm nội bộ công ty, bản build riêng của nhóm…
Kho riêng chỉ cần phục vụ cùng REST API `txa.v1` (hai file JSON tĩnh), hoặc đơn giản là một thư mục chứa `manifests/`.

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

### Tự dựng một kho

1. Tạo thư mục có `manifests/<chữ-cái>/<Namespace>/<AppName>/<X.Y.Z>/` (soạn card bằng
   `txacreate new <url> --dry-run --out <thư-mục>` cho nhanh).
2. Dùng ngay dạng thư mục: `txapm source add noibo D:\kho-txa`. Hoặc sinh REST API tĩnh:
   ```powershell
   txaci build-api --root D:\kho-txa --out D:\kho-txa-site
   ```
3. Đưa thư mục `D:\kho-txa-site` lên bất kỳ máy chủ HTTPS nào (IIS, nginx, GitHub Pages, S3…), rồi
   `txapm source add congty https://<máy-chủ>/api/txa/v1`.

Muốn có cả bot kiểm định 16 bước như kho chính: fork repo này, thay namespace trong `policy.txa.yaml`,
chạy `scripts/setup-github.ps1 -Owner <tổ-chức>`.

---

## Đóng góp một phần mềm vào kho — `txacreate`

Ai có tài khoản GitHub cũng gửi được, không cần biết viết YAML.

**1. Gửi bộ cài** (link tải `.exe`/`.msi` chính thức, phải là HTTPS) — không cần đăng nhập trước:

```powershell
txacreate new https://vendor.example/app-2.1.0-x64.exe
```

`txacreate` hỏi từng câu như một trình hướng dẫn: mỗi câu có ví dụ và **giá trị gợi ý** (bấm Enter để nhận,
gõ để thay thế). Link GitHub Releases được tự điền tên, nhà phát hành, giấy phép, mô tả.

```
For additional information about the restrictions for each field, visit https://github.com/TXAVL/txa-repo#readme
Press ENTER to submit the value for each question including accepting the (default) value.
Please enter values for the following fields:

The package unique identifier |e.g. TXAVL.HelloTool| [id] value is: TXAVL.HelloTool
The package version |e.g. 1.2.3| [version] value is: 2.1.0
Select architecture (use ↑/↓, Enter to accept): x64
```

Giấy phép **chọn bằng mũi tên hoặc gõ số / tên** (`MIT`, `Apache 2.0`…), mỗi loại có giải thích bên cạnh.
Sau đó TXA hỏi có muốn sửa các trường tuỳ chọn không, tạo **bản xem trước 3 file YAML**, kiểm tra nhanh
(`Manifest validation succeeded: True`) rồi hỏi `Would you like to make changes to this manifest? (y/n)`
(`y` = nhập lại, `n` = tiếp tục). File được lưu ở `%USERPROFILE%\manifests\...` và TXA hỏi
`Would you like to submit your manifest to the TXA repository? (y/n)`.
14 bước kiểm tra đầy đủ do bot chạy trên Pull Request; muốn tự chạy trước thì thêm `--check`.

**2. Cấp quyền GitHub — chỉ ở bước cuối.** Khi sắp fork kho và mở Pull Request, TXA mới hiện:

```
GitHub access is needed to fork the repository and open the pull request:
  1. Open   https://github.com/login/device
  2. Enter  XXXX-XXXX
```

Trình duyệt tự mở, bạn nhập mã 8 ký tự rồi bấm **Authorize**. Lệnh chờ bạn duyệt xong rồi tự fork, tạo
branch, commit và **mở Pull Request**. Quyền được mã hoá và nhớ trên máy, lần sau không hỏi lại.

Có bản cho nhiều kiến trúc thì đưa nhiều link: `txacreate new <link-x64> <link-arm64>`.

**3. Phần mềm đã có trong kho, giờ có bản mới:**

```powershell
txacreate update TXAVL.HelloTool https://vendor.example/app-2.2.0-x64.exe
```

Mọi thông tin cũ được giữ nguyên, chỉ thay link và phiên bản.

**Lệnh tiện ích:**

| Lệnh | Việc |
|---|---|
| `txacreate new <link> --dry-run` | chỉ tạo file vào `./txa-out` để xem trước, không gửi gì |
| `txacreate hash setup.exe` | xem SHA-256, kiến trúc, loại bộ cài của một file |
| `txacreate submit <thư-mục>` | gửi PR cho thư mục gói, thư mục kho gốc (`C:\my-txa-repo`) hoặc thư mục API (`C:\my-txa-api`) |
| `txacreate show TXAVL.HelloTool` | in nội dung manifest đang có trong kho |
| `txacreate new <link> --check` | chạy thử cả 14 bước của bot ngay trên máy (chậm hơn: tải, CDN, chữ ký số) |
| `txacreate validate <thư-mục>` | chạy 14 bước kiểm tra cho thư mục gói hoặc cả kho |
| `txacreate token` | xem tài khoản GitHub đang dùng (không bắt buộc) |
| `txacreate token --store` | cấp quyền GitHub trước, không đợi tới lúc gửi |
| `txacreate token --clear` | quên quyền đã lưu (đăng xuất) |
| `txacreate new <link> -t <PAT>` | dùng Personal Access Token cho lần này, không lưu (hoặc đặt biến `TXA_TOKEN`) |
| `txacli <tên-hoặc-id>` | tìm kiếm, quét máy (`txacli -i`) & nhập gói từ WinGet vào TXA cực nhanh (xem [docs/winget-import.md](docs/winget-import.md)) |

Chủ kho muốn bot hiện tên riêng (`txa-repo[bot]`) thay vì `github-actions` thì làm theo [docs/github-app.md](docs/github-app.md).

### Sau khi gửi Pull Request

**Việc đầu tiên sau khi tạo PR là đọc và chấp nhận [Thỏa thuận Người đóng góp (Contributor Agreement)](docs/contributor-agreement.md).** Bot comment ngay và gắn nhãn `txa:needs-agreement`. Bạn trả lời đúng một comment:

```
@txa-repo agree
```

Bot tự **xoá comment đó**, gỡ nhãn `txa:needs-agreement` và gắn nhãn `txa:needs-confirmation` (đang chờ bạn tick checklist). **Bot chưa chạy bất cứ bước nào cho tới khi bạn vừa đồng ý vừa tick hết các ô** trong mô tả PR: 14 bước kiểm tra, bảng tiến trình và 16 check chỉ bắt đầu khi đủ hai điều kiện đó, lúc ấy nhãn chuyển sang `txa:validating`. Chưa đủ thì PR không thể gộp. Chỉ comment của chính người mở PR mới có hiệu lực. Thay mặt công ty thì ghi `@txa-repo agree company="Tên công ty"`.
Giống `winget-pkgs`: **đồng ý một lần, bot nhớ**. Lần sau, nếu bạn đã có PR được gộp ở kho này hoặc ở một kho trong danh sách tin cậy (mặc định `TXAVL/txa-repo`) và thỏa thuận chưa đổi phiên bản, bot ghi nhận sẵn và PR vào thẳng nhãn `txa:needs-confirmation`: không phải comment lại, nhưng **vẫn phải tick hết checklist** của từng PR trước khi bot chạy. Maintainer không được miễn, cũng phải đồng ý một lần như mọi người. Khi thỏa thuận đổi phiên bản, bot sẽ hỏi lại. Bước này hiện thành status `txa/agreement` trong khung merge.

Mô tả của PR có một **checklist bạn tự tick**: đã đọc hướng dẫn, không có PR trùng, chỉ sửa một manifest,
đã chạy `txacreate validate <thư-mục>`, đã thử `txapm install --manifest <thư-mục>`, đúng schema.
Bot đăng huy hiệu sức khoẻ (Validation Pipeline / Publish Pipeline), liệt kê **16 check đánh số**
(`01. …` → `16. …`, từng cái chuyển từ *Queued* sang xong) và giữ PR ở trạng thái chờ cho tới khi mọi ô được tick
(nhãn `txa:needs-confirmation`). Sau khi qua kiểm tra, bot báo cần một Contributor/moderator duyệt.

Khi bạn đã đồng ý và tick hết các ô, bot đăng một **bảng tiến trình** và tự cập nhật từng bước ngay trong PR
(⏳ chờ → 🔄 đang chạy → ✅ xong / ❌ lỗi, kèm thời gian mỗi bước):

```
🤖 TXA Bot · Validating…
████████░░░░░░  8/14 checks done
🔄 Running step 09 · Binary Stream Integrity & Download Verification
```

Bot kiểm tra tự động **16 bước**: mã hoá file, cú pháp, tên gói, phiên bản, giấy phép, HTTPS,
dung lượng, CDN ở 6 khu vực, tải về, chữ ký số, SHA-256, kiến trúc, phiên bản Windows, tham số cài im lặng,
rồi gắn nhãn và bật tự gộp. Xong, bình luận được thay bằng **báo cáo đầy đủ**: bảng thông tin bộ cài
(loại, CPU, dung lượng, chữ ký, SHA-256), kết quả và thời gian từng bước, và mục "Full output of every check"
liệt kê chi tiết từng bước như khi chạy bằng dòng lệnh.

| Nhãn | Nghĩa |
|---|---|
| `txa:validating` | bot đang chạy các bước kiểm tra |
| `txa:verified-build` | qua hết kiểm tra tự động |
| `txa:awaiting-review` | qua kiểm tra, chờ moderator duyệt |
| `txa:approved` | moderator đã duyệt, sẽ tự gộp |
| `txa:published` | **đã gộp** — gói đã nằm trong kho |
| `txa:needs-agreement` | bạn chưa chấp nhận Contributor Agreement — comment `@txa-repo agree` |
| `txa:needs-confirmation` | checklist trong mô tả PR chưa tick đủ |
| `txa:fix-required` | có lỗi — đọc comment của bot, sửa rồi push lại, bot tự chạy lại |
| `txa:new-app` / `txa:new-version` | gói mới / phiên bản mới |

Nhãn đi theo đúng vòng đời, không còn nhãn cũ nằm lại: duyệt xong thì `awaiting-review` đổi thành `approved`,
gộp xong đổi thành `published` và bot ghi sẵn lệnh `txapm install` vào bình luận. Khoảng hai phút sau mọi người
cài được gói đó.

**Gói đang chờ duyệt vẫn hiện trong kho** (`pending.json`) kèm trạng thái, nhưng **chưa cài được**:

```
txapm search hello   →  bảng "Waiting for review - cannot be installed yet"
txapm install hello →  cannot be installed yet - waiting for a Contributor/moderator to review and approve it
```

Chỉ khi Contributor duyệt và PR được gộp thì `txapm install` mới cài được.

`txacreate` tự mở trang PR trên trình duyệt ngay khi tạo xong (thêm `--no-browser` nếu không muốn).

---

## Câu hỏi thường gặp

**Gõ `txapm` báo "not recognized"?** Mở cửa sổ terminal mới để PATH được nạp lại.

**Cài báo "SHA-256 mismatch"?** File trên máy chủ nhà phát hành đã thay đổi so với lúc duyệt.
TXA đã xoá file đó để bảo vệ bạn. Hãy báo lỗi ở [Issues](https://github.com/TXAVL/txa-repo/issues).

**Cài báo mã thoát 1618?** Windows đang cài một phần mềm khác, đợi xong rồi chạy lại.

**Cài báo mã thoát 3010?** Cài thành công, chỉ cần khởi động lại máy.

**Gỡ TXA khỏi máy?**

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/TXAVL/txa-repo/main/install.ps1))) -Uninstall
```

Cài bằng pipx thì gỡ bằng `pipx uninstall txa`.

---

<details>
<summary>Dành cho người phát triển / quản trị kho</summary>

- `manifests/t/TXAVL/<AppName>/<X.Y.Z>/` — mỗi phiên bản gồm `core.txa.yaml`, `build.txa.yaml`,
  `about.<lang>.txa.yaml` (mẫu có chú thích: [examples](examples/manifests/t/TXAVL/HelloTool/1.4.2/build.txa.yaml)).
- `tools/` — mã nguồn Python của `txapm`, `txacreate`, `txaci`
  (`cd tools && python -m pip install -e .`).
- `.github/workflows/` — bot kiểm định (`txa-validate`, `txa-gate`), API (`txa-publish-api`),
  phát hành (`txa-release`, `txa-pypi` — chạy khi push tag `vX.Y.Z`).
- `policy.txa.yaml` — giới hạn dung lượng, namespace, vùng kiểm tra CDN.
- `scripts/setup-github.ps1` — cấu hình nhãn, CODEOWNERS, branch protection.
- API công khai: `https://txavl.github.io/txa-repo/api/txa/v1/index.json`.

</details>
