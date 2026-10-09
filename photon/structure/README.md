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

## Kararlar ve açık sorular

| ID | Durum | Uygulama |
|---|---|---|
| Q-S01 | KARAR | **Otomatik warm-up:** `config.warmup_period` (gün; D1/H4 365, M15 30, M1 7 — *kullanıcı kararı, kursta yok*). Trend ilk kapanışlı swing BOS'a kadar UNDEFINED; warm-up olayları `warmup=True` (sinyal üretmez, `StructureEvent.signal_capable`). **Elle seed (YAML) seçeneği duruyor** (`--seed`). |
| Q-S02 | KARAR | Zincirde en son inside bar (T-MIS @33:21). |
| Q-S03 | KARAR | Aday yoksa referans değişmez / CHoCH sonrası referans boş kalabilir (log uyarısı). |
| Q-S04 | KARAR | Outside bar sırası alt TF ile çözülür: `SubTfResolver` (M15→M1; aynı dakikada ikisi de → tick; M1→tick). Alt veri yoksa/çözülemezse **`OUTSIDE_BAR` olayı (sinyal yok)**; "CHoCH önce" varsayımı kaldırıldı. |
| Q-S05 | KARAR | Tek BOS. Çift BOS kodlanmadı (`NotImplementedError`). |
| Q-S06 | Aşama 3 | P/D aralığı. |

Yeni açık sorular (aşağıda): Q-S07, Q-S08.

```text
ID: Q-S07  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: MS-R006/R008 (cold start, U-15)
KONUM: StructureEngine._bootstrap
AÇIKLAMA: Warm-up'ta "ilk kapanışlı swing BOS" için önce bir swing high/low gerekir; kaynak bunu tanımlamıyor. Uygulanan
  (MS-R008'in iki yönlü uygulanması): baştan itibaren en yüksek tepe / en düşük dip izlenir; geri çekilme eşiği (≥/>
  config) sağlanınca "onaylı" olur; onaylı tepenin üstünde KAPANIŞ → bullish BOS (altındaki onaylı dip → bearish BOS).
  Kutu kuralı (MS-R007) ile strong low/high belirlenir. Bu BOS'ta iç yapı BOS yönünde başlar; internal referans =
  kırılım öncesi en yakın aday (MS-R003), yoksa boş. Onaylı uç sabit kalır (wick aşımı = sweep). Onay beklenirken
  min_swing_candles (C-05) uygulanmaz.
ETKİ: warm-up sonunda kurulan ilk yapı (özellikle ilk trend yönü). Warm-up ≥ 1 yıl olduğundan ilk kararın etkisi sinyal
  döneminde sönümlenir ama sıfır değildir.  SEÇENEKLER: kaynakta seçenek yok. Onayınız gerekir.

ID: Q-S08  TÜR: UNDEFINED  İLGİLİ KURAL: MS-R005 (Q-S04 devamı)
AÇIKLAMA: Outside bar çözülemediğinde iç yapı durumu DEĞİŞTİRİLMEZ (CHoCH ve yeni referans uygulanmaz); aynı mum
  sinyal üretmez. Gerçekte CHoCH olmuşsa yapı bir sonraki kırılıma kadar geride kalabilir. Alternatif (yeniden
  senkronizasyon) kaynakta yok.
ETKİ: nadir; yalnız alt veri eksik/aynı tick'te çözülemeyen mumlar.  SEÇENEKLER: kaynakta seçenek yok.
```
Ek varsayımlar (belgelenmiş): aynı mumdaki geri çekilme/yeni uç sırası bilinmediğinden, yeni uç yapan mumun kendi dibi
geri çekilme sayılmaz; eşit fiyatlı dipte/tepede ilk (en erken) mum alınır; `min_swing_candles` (C-05) swing
aralığının [strong .. uç] mum sayısı olarak uygulanır (nadiren bağlayıcı); outside bar'da önce yüksek kırılıp sonra
alçak da yeni referansı kırarsa ikisi de üretilir (sıra bilinen durumda).

## Doğrulama çıktısı

```bash
# otomatik warm-up (önce `photon fetch` ile warm-up dönemi dahil M1 verisi indirilmiş olmalı: start - warmup_period)
python -m photon structure --tf M15 --start 2021-09-01 --end 2021-09-30 --out structure_out
# elle seed
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
