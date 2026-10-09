# structure — MS-R001..R009, R014 (Aşama 2)

Yapı yalnızca kapanmış mumlarla güncellenir. Bearish mantık, bullish mantığın aynalanmış halidir (tek kod yolu;
`test_mirror_symmetry` aynalanmış veride aynalanmış olay üretildiğini kanıtlar).

## Kural → kod → test

| Kural | Kod (`engine.py`) | Test (`tests/test_structure.py`) |
|---|---|---|
| MS-R001 kırılım ≥ 1 pipette, eşitlik değil | `_step_swing`/`_step_internal` (`>= pipette`) | `test_ms_r001_equality_is_not_a_break`, T-MS-02 |
| MS-R002 aday internal high/low | `_step_internal` (son blok) | T-MS-01 |
| MS-R003 en yakın low/high, inside bar | `_step_internal` (`broke_pend`/`broke_ref` taraması) | `test_ms_r003_nearest_low_not_lowest`, `test_inside_bar_chain_*` |
| MS-R004 geçersiz low referans olamaz | referans yalnız bir high kırılınca değişir | T-MS-08 |
| MS-R005 CHoCH (wick, yalnız ilk kırılım) | `_step_internal` `broke_ref` | T-MS-03, `test_choch_only_first_break_*` |
| MS-R006 BOS (kapanış) | `_step_swing` | T-MS-04, T-MS-05 |
| MS-R007 box rule | `_step_swing` (BOS dalı) | T-MS-05, `test_ms_r007_*` |
| MS-R008 swing onayı (≥/> config) | `_step_swing` (onay bloğu) | T-MS-06, T-MS-07, `test_c06_*`, `test_min_swing_candles_*` |
| MS-R009 trend değişimi, spike | `_step_swing` (ilk dal) | `test_ms_r009_*` |
| MS-R014 tek BOS | varsayılan; DOUBLE_BOS → `NotImplementedError` (Q-S05) | `test_double_bos_not_coded_q_s05` |
| MS-R012 strong/weak | `state()` (`Strength`) | `test_t_ms_05_*` |
| MS-R010 kalibrasyon | Aşama 7 | — |
| MS-R011, R013, R015 | L6/yorum; kodlanmadı (R013: swing=kapanış, internal=wick uygulandı) | — |

## Açık sorular (kodlanmadı / varsayım gerektirdi — yanıt bekleniyor)

```text
ID: Q-S01  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: U-15 (cold start)
KONUM: StructureEngine.start / Seed
AÇIKLAMA: Başlangıç yapısı kaynakta tanımsız. Motor Seed olmadan olay üretmez. Seed: trend, swing high/low mum
  zamanı, uç onaylı mı, internal trend + referans mumu (YAML, `photon structure --seed`). Tutarsız seed hata verir.
ETKİ: İlk swing/internal durumu.  SEÇENEKLER: kaynakta seçenek yok (FINAL_SPEC §6 önerisi: ilk BOS'a kadar UNDEFINED).

ID: Q-S02  TÜR: UNDEFINED  İLGİLİ KURAL: MS-R003 (inside-bar zinciri, AMBIGUOUS)
AÇIKLAMA: Ardışık inside bar'larda "pullback" mumu yalnızca örnekle anlatılmış. Uygulanan: kırılımdan geriye ilk aday
  (sonraki mum low'unu 1 pipette kıramamış) → zincirde EN SON inside bar.
ETKİ: internal CHoCH referans seviyesi.  SEÇENEKLER: kaynakta seçenek yok.

ID: Q-S03  TÜR: UNDEFINED  İLGİLİ KURAL: MS-R003/R004
AÇIKLAMA: (a) Aday low taraması pullback başlangıcıyla (aday high) sınırlı; aday yoksa referans DEĞİŞMEZ.
  (b) CHoCH sonrası aday high bulunamazsa referans boş kalır (bir sonraki geçerli kırılıma kadar CHoCH yok). Log uyarısı verilir.
ETKİ: nadir köşe durumlar.  SEÇENEKLER: kaynakta seçenek yok.

ID: Q-S04  TÜR: UNDEFINED  İLGİLİ KURAL: MS-R005
AÇIKLAMA: Tek mum hem internal high'ı hem low'u kırarsa (outside bar) mum içi sıra bilinmiyor. Uygulanan: CHoCH önce
  değerlendirilir ve olay `note="OUTSIDE_BAR"` ile işaretlenir.
ETKİ: o mumdaki CHoCH.  SEÇENEKLER: kaynakta seçenek yok.

ID: Q-S05  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: MS-R014 (alternatif çift BOS)
AÇIKLAMA: "HL ancak ikinci BOS ile kesinleşir" mekanik olarak tanımlı değil. Config SINGLE_BOS (karar) → kodlandı;
  DOUBLE_BOS seçilirse NotImplementedError. Karşı-HTF çift BOS (EN-R007) Aşama 5'te stratejide ele alınacak.

ID: Q-S06  TÜR: AMBIGUOUS  İLGİLİ KURAL: PD-R001
AÇIKLAMA: P/D aralığı swing mi internal mi? `MarketState.eq` yalnızca ONAYLI swing aralığında verilir
  (onaysız uçta aralık değişebilir); internal EQ üretilmez. Karar Aşama 3'te.
```
Ek varsayımlar (belgelenmiş): aynı mumdaki geri çekilme/yeni uç sırası bilinmediğinden, yeni uç yapan mumun kendi dibi
geri çekilme sayılmaz; eşit fiyatlı dipte/tepede ilk (en erken) mum alınır; `min_swing_candles` (C-05) swing
aralığının [strong .. uç] mum sayısı olarak uygulanır (nadiren bağlayıcı).

## Doğrulama çıktısı

```bash
python -m photon structure --tf M15 --start 2021-09-01 --end 2021-09-30 --seed seed.yaml --out structure_out
```
`seed.yaml` örneği:
```yaml
swing_trend: BULL
swing_high_time: "2021-09-01T10:15:00Z"   # mum açılış zamanı (UTC)
swing_low_time:  "2021-09-01T07:30:00Z"
swing_high_confirmed: true
internal_trend: BULL
internal_ref_time: "2021-09-01T09:45:00Z"
```
Çıktı: `structure_out/EURUSD_M15_structure.csv` (olay listesi) ve `.png` (işaretli grafik). Veri: önbellekteki M1 (BID),
H4/D1 NY-17:00 sınırlarıyla resample.
