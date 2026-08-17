# Handoff — OracleMessage: đã chốt lá 01–04, tiếp 05–07

Ngày: 2026-08-14 22:34, cập nhật 2026-08-15 (Asia/Saigon). Mục đích: tiếp tục công việc trên
device khác. Nguồn sự thật về concept/pipeline: `plans/260713-1530-oraclemessage-cardlist/plan.md`
(plans/ NAY ĐÃ track git → có sau `git pull`; phần cốt lõi vẫn được tóm ở đây).

## Trạng thái hiện tại

- Deck 30 lá BRD, art direction ĐÃ KHOÁ: tranh lụa VN full-bleed, palette xám-lục/ivory/chàm,
  accent tím-lavender, nửa trên là lụa trống, KHÔNG glow, không chữ. Khung mặt trước =
  overlay cắt từ back thật: `oraclemessage-deck/final/front/frame-overlay-wide.png` (ĐÃ track git).
  Art tối dùng overlay-softdark (chỉ có local, session 260814-1006).
- Batch 24/24 lá đã render xong (session local `260814-1006-batch-24-cards`); catalog master
  30 lá ở session local `260814-1047-30cards-brd-catalog/catalog.html`. CHƯA được thay ảnh
  mới vào catalog master cho đến khi user chốt xong vòng review.
- User đã đánh giá lá 1–7. Verdicts đến giờ:
  - **01 The Spark**: ✅ ĐÃ CHỐT (2026-08-14 23:45) — **bỏ hẳn đom đóm**, thay bằng
    **cọc rào tre khô nứt ra một chồi xanh**. Bản chốt đã promote:
    `oraclemessage-deck/final/front/cards/card-01-the-spark.png` (+ art + prompt).
    Session cuối: `260814-2345-spark-f1-polish` (bản G2). Hành trình loại trừ:
    đom đóm (không vẽ được vật phát sáng dưới luật no-glow) → nhang (u ám) →
    tia nắng giữ luật ivory (tia không giành được tiêu điểm vì nửa trên đã sáng sẵn) →
    tia nắng phá luật ivory (tia rõ nhưng lá lệch tông cả bộ) → **chồi non**.
    Chốt vì Ace of Wands trong Rider-Waite gốc là CÀNH GẬY NẢY CHỒI chứ không phải tia sáng,
    nên hướng này bám biểu tượng gốc và không cần chạm luật no-glow.
  - **02 The Veil**: ĐÃ GIỮ bản v2 (render từ ảnh thật Hạ Long — xem Refs dưới).
  - **03 The Compass**: ✅ ĐÃ CHỐT (2026-08-15) — **bỏ hẳn hình tượng người cầm la bàn** (user chê
    trông thô), thay bằng **tĩnh vật: la bàn đồng nắp mở tựa khối gỗ trên bàn, một dải nắng chéo**.
    Bản chốt: `final/front/cards/card-03-the-compass.png`, session `260815-0005-compass-flat-refine`
    (bản I1). Đánh đổi user đã biết và chấp nhận: bản này KHÔNG có ngã rẽ nên lá nghiêng về
    'định hướng nội tại' hơn là 'chọn đường' (Lenormand Ways) — bản I2 có ngã ba đường qua cửa sổ
    vẫn nằm trong session nếu sau này muốn đổi ý.
  - **04 The Mirror**: ✅ ĐÃ CHỐT (2026-08-15) — **bỏ hẳn art tái dùng từ 16 Nội Tâm**, thay bằng
    **thiếu nữ áo dài tím đứng nhỏ QUAY LƯNG bên mép ao, dưới nước là phản chiếu lật ngược dài hơn
    cả người**. Bản chốt: `final/front/cards/card-04-the-mirror.png` (bản M1), session cuối
    `260815-0055-mirror-posture-fix`.
    Lỗi gốc của bản cũ: luật chung của bộ có câu `water is one flat quiet wash with NO MIRROR
    REFLECTIONS`, tức là **lá Gương bị cấm vẽ đúng thứ làm nên nghĩa của nó** → mặt ao ra mảng gần
    đen, không có bóng. Lá 04 giờ là **ngoại lệ DUY NHẤT** được phép có phản chiếu (chi tiết cách
    viết ngoại lệ + các bài học prompt: `final/front/cards/README.md`).
    ĐÃ LOẠI trước khi render: tĩnh vật "gương đồng cổ trên bàn" — vì 03, 05 và 20 đều đã là
    vật-thể-trên-gỗ, thêm 04 nữa là ba lá liên tiếp trùng bố cục.
    Prompt lá 04 là **CHUỖI 1 render + 4 edit** (`prompt-04-the-mirror.txt`), không phải prompt đơn.
  - **05–07** (Key/Lantern/Tide): hướng sửa đã ghi nhận, duyệt TỪNG-LÁ-MỘT,
    CHỈ render sau khi user duyệt hướng của từng lá:
    05 khung cửa phải đọc rõ là cánh cửa ·
    06 đèn lồng trước người sau (có thể góc nhìn từ trên) · 07 dùng địa danh du lịch VN thật làm nền.

## Chú ý khi làm trên device khác

- **CẬP NHẬT 2026-08-15: `oraclemessage-deck/sessions/` và `plans/` KHÔNG còn bị gitignore nữa** —
  đã track để làm cross-device, nên `git pull` là có đủ ảnh lẫn plan. (Repo vì thế nặng, ~1.2GB.)
- **Python 3.13 là bắt buộc** (`requires-python >=3.13`). Nếu `python3` mặc định là 3.12 thì
  `pip install -e ".[dev]"` sẽ fail. Đường vòng không cần cài, gọi thẳng interpreter 3.13:
  `PYTHONPATH=src /opt/homebrew/opt/python@3.13/bin/python3.13 -c 'import sys; from codex_imagegen.cli import main; sys.argv=["imagegen"]+sys.argv[1:]; main()' "<prompt>" -o out.png --size 1024x1536`
  (đổi `codex_imagegen.cli` → `codex_imagegen.edit_cli` cho `imagegen-edit`).
- Pipeline mỗi lá (cần `pip install -e ".[dev]"` + `codex login`):
  1. `imagegen "<prompt>" -o art-NN-<slug>.png --size 1024x1536 --quiet` — render TUẦN TỰ,
     tuyệt đối không parallel (race OAuth refresh → chết session Codex).
  2. Nếu dims lệch 1024x1536: `magick art.png -resize 1024x1536^ -gravity center -extent 1024x1536 art.png`
  3. `magick art.png oraclemessage-deck/final/front/frame-overlay-wide.png -compose Over -composite card.png`
- Mỗi request 1 session folder mới `oraclemessage-deck/sessions/<YYMMDD-HHMM>-<slug>/`;
  ≥3 ảnh thì build gallery: `python3 scripts/build_deck_session_index.py <session-dir>` (cần session.json).
- Lá 02 render với ref: tải https://commons.wikimedia.org/wiki/File:Halong_Bay_in_dense_fog.jpg
  (Vyacheslav Argenberg, 2008, CC BY 4.0) rồi truyền `-i <file>`.

## Prompts

**Nguồn duy nhất đúng cho lá ĐÃ CHỐT: `oraclemessage-deck/final/front/cards/prompt-NN-<slug>.txt`**
(đã track git, có sẵn sau `git pull`).

Prompt v3 của lá 01 (đom đóm) và lá 03 (tay cầm la bàn) ĐÃ GỠ khỏi tài liệu này — cả hai motif đều
đã bị LOẠI, để lại dưới cái tiêu đề "hiện hành" chỉ tổ khiến ai đó re-roll nhầm.

Lá 04 có prompt dạng **CHUỖI** (1 render + 4 edit nối tiếp) — phải chạy đúng thứ tự ghi trong file,
không phải một prompt đơn.

Các bài học prompt đã chứng minh ăn / không ăn (chống 3D, chống đen đặc, bẫy bóng đổ, bẫy bão hoà màu,
bẫy dáng ngồi xổm, ngoại lệ phản chiếu cho lá 04): xem `final/front/cards/README.md`.

### 02 The Veil — v2 (ĐÃ GIỮ — chỉ dùng lại nếu cần render biến thể; nhớ -i ref Hạ Long)

```
TALL VERTICAL hanging-scroll format, portrait orientation, the image is MUCH taller than wide (2:3 width-to-height, like a tarot card). FULL-BLEED painting with NO border, NO frame, NO keyline, NO margin — the painted scene runs to all four edges of the image. Traditional Vietnamese silk painting (tranh lua), matte mineral pigment stained into raw silk, visible silk weave texture throughout, flat uneven hand-brushed washes, museum piece by a mid-century Vietnamese silk master. STRICT RULES: the upper half of the picture is mostly empty unpainted pale-ivory silk sky; no glow, no luminous effects; water is one smooth continuous quiet pale grey-green wash fading evenly to the bottom edge, with absolutely no dark patches, no blocky stains, no hard-edged shapes in the water and no mirror reflections; faces are small, stylized, minimal brush features. Restrained muted palette of grey-green, warm ivory and dusty indigo; if a garment is present it is soft violet-lavender as the main accent. Scene: use the supplied real photograph of Ha Long Bay in dense fog as the geographic and compositional foundation. Preserve its distinctive spatial arrangement: one isolated sheer-sided limestone tower half-dissolved in fog on the left, a darker cluster of steep vertical limestone karst islands on the right, and a broad quiet channel of mist and water opening between them. The karst must read as sheer vertical limestone cliffs rising straight from the sea, with only sparse vegetation clinging to their tops — not soft rounded forested hills. Recompose the horizontal view naturally into a tall 2:3 hanging-scroll crop, karst confined mainly to the lower third and lower sides, with a vast veil of pale morning mist above; the fog reads as soft layered translucent horizontal veils that reveal only part of the scene. Add one very small traditional Vietnamese wooden rowboat with a single tiny stylized rower low in the channel, half-hidden behind a translucent band of fog, clearly secondary to the landscape. Transform the photograph completely into restrained silk painting; do not retain photographic lighting, sharpness, reflections or color. No cruise ships, no buildings, no fantasy mountains. No text, no words, no signature.
```

## Việc tiếp theo (theo thứ tự)

1. ~~Chốt 01, 03, 04~~ ✅ xong. Lá đã chốt gom ở `oraclemessage-deck/final/front/cards/`
   (01, 02, 03, 04 — kèm README bảng tiến độ + index.html; hiện **4/30**).
2. Tiếp: duyệt hướng **05 Chìa Khoá** → render sau khi duyệt → lặp cho 06, 07.
   Hướng đã ghi nhận cho 05: khung cửa phải đọc rõ là CÁNH CỬA.
   Quy trình bắt buộc: TRÌNH HƯỚNG TRƯỚC, chỉ render sau khi user duyệt hướng của từng lá.
3. Sau khi vòng review khép: user quyết định mới được ghi verdict + thay ảnh vào catalog master
   (`sessions/260814-1047-30cards-brd-catalog/catalog.html` — đến giờ vẫn CHƯA đụng vào, cố ý).
4. Quyết định mở cấp deck còn treo: 21 Crown (khăn vành dây chưa rõ), 25 Mountain (persistence),
   27 Sanctuary (đổi tên "Chốn An Yên"?), 23 Scale (cầu khỉ thay cán cân).
5. Câu hỏi còn treo từ vòng gom thư mục chốt: có đưa 4 lá đã duyệt theo danh sách 24 lá cũ
   (Kẻ Lữ Hành, Buông Bỏ, Hy Vọng, Tĩnh Lặng — session `260814-0922`) vào thư mục chốt dưới
   tên BRD mới hay không.
6. Cụm cần soi CẠNH NHAU trước khi khoá cả bộ: 03 La Bàn, 05 Chìa Khoá, 20 Bản Đồ đều là
   tĩnh vật vật-thể-trên-gỗ — dễ trùng bố cục.
