// Sections of the main docs page, in reading order.
export const groups = [
  { vi: "Dùng TXA", en: "Using TXA", items: [
    ["bat-dau", "Bắt đầu", "Get started"],
    ["txapm", "Dùng txapm", "Using txapm"],
    ["cai-dat-lam-gi", "Khi cài, TXA làm gì", "What an install does"],
    ["phien-ban", "Phiên bản và ngôn ngữ", "Versions and languages"],
  ] },
  { vi: "Mở rộng", en: "Go further", items: [
    ["kho-nguon", "Kho nguồn riêng", "Your own sources"],
    ["dong-gop", "Đóng góp một gói", "Contribute a package"],
  ] },
  { vi: "Tham chiếu", en: "Reference", items: [
    ["manifest", "Cấu trúc manifest", "Manifest format"],
    ["api", "API công khai", "Public API"],
    ["faq", "Hỏi đáp và gỡ cài đặt", "FAQ and uninstall"],
  ] },
];

export const order = groups.flatMap((g) => g.items);
