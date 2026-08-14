# Handoff — OracleMessage: duyệt rerender lá 01–03, tiếp 04–07

Ngày: 2026-08-14 22:34 (Asia/Saigon). Mục đích: tiếp tục công việc trên device khác.
Nguồn sự thật về concept/pipeline: `plans/260713-1530-oraclemessage-cardlist/plan.md` trên
MacBook gốc (plans/ bị gitignore — KHÔNG có trên device khác; phần cốt lõi được tóm ở đây).

## Trạng thái hiện tại

- Deck 30 lá BRD, art direction ĐÃ KHOÁ: tranh lụa VN full-bleed, palette xám-lục/ivory/chàm,
  accent tím-lavender, nửa trên là lụa trống, KHÔNG glow, không chữ. Khung mặt trước =
  overlay cắt từ back thật: `oraclemessage-deck/final/front/frame-overlay-wide.png` (ĐÃ track git).
  Art tối dùng overlay-softdark (chỉ có local, session 260814-1006).
- Batch 24/24 lá đã render xong (session local `260814-1006-batch-24-cards`); catalog master
  30 lá ở session local `260814-1047-30cards-brd-catalog/catalog.html`. CHƯA được thay ảnh
  mới vào catalog master cho đến khi user chốt xong vòng review.
- User đã đánh giá lá 1–7. Verdicts đến giờ:
  - **01 The Spark**: v2 rồi v3 đều CHƯA ƯNG (v3 đã sửa đom đóm thành vệt mực mềm, vẫn chưa đạt).
    Đang chờ user nói cụ thể chưa ưng ở đâu (đom đóm? cụm lá chuối quá đậm? bố cục?).
  - **02 The Veil**: ĐÃ GIỮ bản v2 (render từ ảnh thật Hạ Long — xem Refs dưới).
  - **03 The Compass**: v3 CHƯA ƯNG. Cũng chờ user chỉ điểm (tay? la bàn? chất lụa?).
  - **04–07** (Mirror/Key/Lantern/Tide): hướng sửa đã ghi nhận, duyệt TỪNG-LÁ-MỘT,
    CHỈ render sau khi user duyệt hướng của từng lá:
    04 phản chiếu nước phải rõ nghĩa Mirror hơn · 05 khung cửa phải đọc rõ là cánh cửa ·
    06 đèn lồng trước người sau (có thể góc nhìn từ trên) · 07 dùng địa danh du lịch VN thật làm nền.
- Xem 3 lá hiện hành (02 v2 + 01/03 v3) không cần file local:
  https://claude.ai/code/artifact/5f0cbb30-188a-484d-8d9d-9913592e4ce6

## Chú ý khi làm trên device khác

- `oraclemessage-deck/sessions/` (606MB) và `plans/` bị gitignore → KHÔNG có trên device khác.
  Ảnh cũ xem qua artifact URL trên; prompts đầy đủ nhúng bên dưới — đủ để re-roll.
- Pipeline mỗi lá (cần `pip install -e ".[dev]"` + `codex login`):
  1. `imagegen "<prompt>" -o art-NN-<slug>.png --size 1024x1536 --quiet` — render TUẦN TỰ,
     tuyệt đối không parallel (race OAuth refresh → chết session Codex).
  2. Nếu dims lệch 1024x1536: `magick art.png -resize 1024x1536^ -gravity center -extent 1024x1536 art.png`
  3. `magick art.png oraclemessage-deck/final/front/frame-overlay-wide.png -compose Over -composite card.png`
- Mỗi request 1 session folder mới `oraclemessage-deck/sessions/<YYMMDD-HHMM>-<slug>/`;
  ≥3 ảnh thì build gallery: `python3 scripts/build_deck_session_index.py <session-dir>` (cần session.json).
- Lá 02 render với ref: tải https://commons.wikimedia.org/wiki/File:Halong_Bay_in_dense_fog.jpg
  (Vyacheslav Argenberg, 2008, CC BY 4.0) rồi truyền `-i <file>`.

## Prompts hiện hành (verbatim — đơn vị để re-roll tiếp)

### 01 The Spark — v3 (chưa ưng, chờ feedback cụ thể trước khi roll tiếp)

```
TALL VERTICAL hanging-scroll format, portrait orientation, the image is MUCH taller than wide (2:3 width-to-height, like a tarot card). FULL-BLEED painting with NO border, NO frame, NO keyline, NO margin — the painted scene runs to all four edges of the image. Traditional Vietnamese silk painting (tranh lua), matte mineral pigment stained into raw silk, visible silk weave texture throughout, flat uneven hand-brushed washes, museum piece by a mid-century Vietnamese silk master. STRICT RULES: the upper half of the picture is mostly empty unpainted pale-ivory silk sky; no glow, no luminous effects; faces are never present. Restrained muted palette of grey-green, warm ivory and dusty indigo. Subject in the lower third. Scene: a quiet Vietnamese village garden at deep blue dusk, painted only as a close cluster of broad banana leaves and two slender bamboo stems in soft dark grey-green and dusty-indigo washes, with a very soft dusty-indigo evening wash low along the bottom edge; no person, no houses, no mountains. Above the leaves, seven to nine FIREFLIES drift upward in one gentle rising curve. Each firefly is a graceful, poetic brush motif, its body a soft-edged ink dab that melts slightly into the silk weave, never a hard crisp silhouette: a tiny elongated dusty-indigo body, a small flat matte warm-ochre mark at the tail tip, and at most one faint short pale stroke suggesting a folded wing. They must read instantly as fireflies at dusk, NOT as flies, bees, wasps, moths or dragonflies — no spread fly wings, no detailed legs, no antennae, no entomological specimen illustration. ONE principal firefly near the lower-third focal point is modestly larger than the rest, still small and elegant, its warm-ochre tail the strongest warm note of the painting, completely matte, never luminous. One small firefly rises higher than the group, like a first idea taking flight. Clear focal hierarchy: principal firefly first, rising curve of fireflies second, garden leaves third. Generous uncluttered negative space. Absolutely no halo, no bloom, no radiance, no emitted light, no illuminated surroundings. No text, no words, no signature.
```

### 02 The Veil — v2 (ĐÃ GIỮ — chỉ dùng lại nếu cần render biến thể; nhớ -i ref Hạ Long)

```
TALL VERTICAL hanging-scroll format, portrait orientation, the image is MUCH taller than wide (2:3 width-to-height, like a tarot card). FULL-BLEED painting with NO border, NO frame, NO keyline, NO margin — the painted scene runs to all four edges of the image. Traditional Vietnamese silk painting (tranh lua), matte mineral pigment stained into raw silk, visible silk weave texture throughout, flat uneven hand-brushed washes, museum piece by a mid-century Vietnamese silk master. STRICT RULES: the upper half of the picture is mostly empty unpainted pale-ivory silk sky; no glow, no luminous effects; water is one smooth continuous quiet pale grey-green wash fading evenly to the bottom edge, with absolutely no dark patches, no blocky stains, no hard-edged shapes in the water and no mirror reflections; faces are small, stylized, minimal brush features. Restrained muted palette of grey-green, warm ivory and dusty indigo; if a garment is present it is soft violet-lavender as the main accent. Scene: use the supplied real photograph of Ha Long Bay in dense fog as the geographic and compositional foundation. Preserve its distinctive spatial arrangement: one isolated sheer-sided limestone tower half-dissolved in fog on the left, a darker cluster of steep vertical limestone karst islands on the right, and a broad quiet channel of mist and water opening between them. The karst must read as sheer vertical limestone cliffs rising straight from the sea, with only sparse vegetation clinging to their tops — not soft rounded forested hills. Recompose the horizontal view naturally into a tall 2:3 hanging-scroll crop, karst confined mainly to the lower third and lower sides, with a vast veil of pale morning mist above; the fog reads as soft layered translucent horizontal veils that reveal only part of the scene. Add one very small traditional Vietnamese wooden rowboat with a single tiny stylized rower low in the channel, half-hidden behind a translucent band of fog, clearly secondary to the landscape. Transform the photograph completely into restrained silk painting; do not retain photographic lighting, sharpness, reflections or color. No cruise ships, no buildings, no fantasy mountains. No text, no words, no signature.
```

### 03 The Compass — v3 = v2 (chưa ưng, chờ feedback cụ thể)

```
TALL VERTICAL hanging-scroll format, portrait orientation, the image is MUCH taller than wide (2:3 width-to-height, like a tarot card). FULL-BLEED painting with NO border, NO frame, NO keyline, NO margin — the painted scene runs to all four edges of the image. Traditional Vietnamese silk painting (tranh lua), matte mineral pigment stained into raw silk, visible silk weave texture throughout, flat uneven hand-brushed washes, museum piece by a mid-century Vietnamese silk master. EVERY element of this painting, including the hand and the compass, is rendered in the same flat stylized silk-painting manner: a few flat matte washes bounded by one delicate dark outline, minimal shading, no volume modeling, no realistic skin texture, no photographic or western realistic rendering, no colored-pencil look. STRICT RULES: the upper half of the picture is mostly empty unpainted pale-ivory silk sky; no glow, no luminous effects; water is one flat quiet wash with no reflections. Restrained muted palette of grey-green, warm ivory and dusty indigo; the sleeve is soft violet-lavender as the main accent. Scene: a close first-person view looking slightly downward over a quiet Vietnamese rice-field landscape. In the lower-center foreground, one slender stylized hand emerging from a flowing soft violet-lavender sleeve holds a large antique round bronze compass, about one quarter of the image width, the unmistakable primary focal point. The hand is elegant and simplified in the silk-painting tradition: long graceful fingers drawn with a single fine outline and one flat pale-ivory wash, like hands in classic Vietnamese silk paintings of women — never a realistic fleshy Western hand. The compass is flat matte aged bronze, drawn with delicate linework: a simple eight-pointed compass rose, a clear central pivot and ONE strong dark needle, with absolutely no letters, no numbers, no written cardinal directions. The needle points clearly toward the right-hand branch of an earthen dike path. Beyond the hand, the dike splits into TWO clearly separate raised earthen paths through quiet grey-green rice paddies — a real fork, the secondary focal point. A few distant village trees and extremely faint low hills sit on a low horizon, leaving the upper half mostly bare ivory silk. No map, no scroll, no signs, no extra objects, no other person or body part. Clear focal hierarchy: compass first, pointing needle second, forked path third. All surfaces matte, no metallic shine, no reflections, no cast shadows. No text, no words, no signature.
```

## Việc tiếp theo (theo thứ tự)

1. Hỏi user chưa ưng 01 và 03 ở điểm nào → chỉnh prompt trúng đích → re-roll vào session mới.
2. Khi 01–03 chốt xong: duyệt hướng 04 → render sau khi duyệt → lặp cho 05, 06, 07.
3. Sau khi vòng review khép: user quyết định mới được ghi verdict + thay ảnh vào catalog master,
   rồi promote lá đạt vào `oraclemessage-deck/final/front/cards/`.
4. Quyết định mở cấp deck còn treo: 21 Crown (khăn vành dây chưa rõ), 25 Mountain (persistence),
   27 Sanctuary (đổi tên "Chốn An Yên"?), 23 Scale (cầu khỉ thay cán cân).
