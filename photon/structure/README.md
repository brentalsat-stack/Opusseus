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
| Q-S01 | KARAR | **Otomatik warm-up** (HistData verisi 3 Ocak 2021'de başlıyor → D1/H4 için 1 yıl YOK, mevcut verinin tamamı warm-up; CLI bunu uyarı olarak yazar): `config.warmup_period` (gün; D1/H4 365, M15 30, M1 7 — *kullanıcı kararı, kursta yok*). Trend ilk kapanışlı swing BOS'a kadar UNDEFINED; warm-up olayları `warmup=True` (sinyal üretmez, `StructureEvent.signal_capable`). **Elle seed (YAML) seçeneği duruyor** (`--seed`). |
| Q-S02 | KARAR | Zincirde en son inside bar (T-MIS @33:21). |
| Q-S03 | KARAR | Aday yoksa referans değişmez / CHoCH sonrası referans boş kalabilir (log uyarısı). |
| Q-S04 | KARAR | Outside bar sırası alt TF ile çözülür: `SubTfResolver` (M15→M1; aynı dakikada ikisi de → tick; M1→tick). HistData'da tick yok → aynı dakikada ikisi de kırılırsa çözülemez. Alt veri yoksa/çözülemezse **`OUTSIDE_BAR` olayı (sinyal yok)**; "CHoCH önce" varsayımı kaldırıldı. |
| Q-S05 | KARAR | Tek BOS. Çift BOS kodlanmadı (`NotImplementedError`). |
| Q-S06 | KARAR (**kullanıcı kararıyla GÜNCELLENDİ**, gerçek veri teşhisi: `range_filter` 25 elemenin 13'ü RANGE_UNKNOWN) | Range = swing aralığı. Trend yönündeki uç onaysızsa kutu kuralı (MS-R007): BULL strong low → BOS sonrası ulaşılan en yüksek high; BEAR simetrik. PD-R001 ve PD-R003 bunu kullanır (`pd.swing_range`, `MarketState.eq`). Swing hiç yoksa (warm-up başı/UNDEFINED) RANGE_UNKNOWN kalır. Testler: `test_pd_from_market_state_unconfirmed_extreme_*`, `test_unconfirmed_extreme_uses_box_rule_range_q_s06_update`, `test_range_unknown_only_without_any_swing_*`. |
| Q-S07 | KARAR (kullanıcı kararı) | MS-R008'in iki yönlü bootstrap uygulaması (aşağıda). |
| Q-S08 | KARAR | Çözülemeyen outside bar'da iç yapı değişmez, sinyal yok. |

Q-S07/Q-S08 onaylandı. **Q-S09 ONAYLANDI** (kırılış mumunun kendi ucu, sonraki mum kıramazsa referans; 1 mum gecikme, lookahead yok; kullanıcı kararı): `StructureEngine(defer_own_extreme=True)`, diagnostics `Q-S09-ok/fail`. Eski açık soru metni: (Q-S03 tanılaması: bkz. `photon/zones/README.md` sonu).

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


## Q-S11 — iç referans kilitlenmesi (HATA DÜZELTMESİ, çok yıllı gerçek koşuda bulundu)
**Belirti:** 2016–2023 sürekli koşuda V0/V9b'de 2017-07→2018-12 ve 2022-01→2023-12 boyunca icra (M1) CHoCH'u hiç yok (mitigasyon/izin normal); V8a/V9a'da 2019 işlemsiz.
**Kök neden (sentetik uzun koşuda birebir üretildi):** CHoCH sonrası yeni referans bulunamazsa (Q-S03b) ya da Q-S09 ertelemesi başarısız olursa `iref=None` kalıyordu. Bu durumda `ipend` (bekleyen aday uç) yalnızca `ipend=None` iken atanır; eski bir `ipend` fiyatın çok uzağında kaldıkça ne referans (iref) ne CHoCH üretilebiliyordu — fiyat bekleyen adayı kırana kadar (haftalar/aylar; sentetikte 224 000 mum ≈ 5 ay referanssız, bazı aylarda 0 CHoCH). Aynı iç-yapı mantığı HTF motorlarında ve M15 icra motorunda da vardı.
**Düzeltme (`StructureEngine._reacquire_ref`, `StructureParams.reacquire_ref`, config `internal_ref_reacquire: true`):** referans yokken her mumda Q-S09 mantığı sürer: önceki mumun karşı-yön ucu, bu mum onu ≥1 pipette kıramadıysa referans olur (MS-R003 'en yakın aday'; geleceğe bakış yok); referanstan önce kalan eski `ipend` atılır (sıra: referans → bekleyen). Sentetikte referanssız en uzun süre 224 000 → ≤14 mum; sağlıklı aylarda CHoCH sayıları aynı mertebede. **Davranış notu:** yalnızca referansın eksik olduğu durumlarda sonuç değişir (eskiden bu durumlarda olay üretilmiyordu) → tüm V* sonuçları değişir; eski davranış A/B için `V0L` varyantı (`internal_ref_reacquire: false`).
**Teşhis:** `limit_report`'ta `struct_<exec|D1|H4|M15>_iref_none_max_run` (ardışık referanssız en uzun süre; kilitlenmede binlerce mum) ve `_ref_reacquired`; ay bazında huni tablosunda `icra_choch_olay` (icra yapı motorunun o ay ürettiği CHoCH sayısı) — 0 ise neden satırı "icra yapı motoru bu ay HİÇ CHoCH üretmedi" yazar. Testler: `photon/tests/test_long_run.py`.
