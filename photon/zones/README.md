# Aşama 4 — Zon, likidite, POI puanlama (DECISIONS v2.0 §3)

Eşik puan yok: kapıları geçen her POI sinyal üretir; puan + kriter dökümü sinyale yazılır (`strategy/poi.py`).

## Kural → kod → test

| Kural | Kod | Test |
|---|---|---|
| SD-R002 pivot zon (STB/BTS) | `zones/detect.py::pivot_zone` | `test_zones.py::test_pivot_*` |
| SD-R001 range zon (≥3 mum inside-bar zinciri, kapanışla kopuş) | `zones/detect.py::range_zone` | `test_range_*` |
| SD-R003 tür / continuation-reversal | `zones/engine.py::_mk, _context` | `test_zone_type_and_context_*` |
| Çizim modu (4H tüm koşu, M15 tek mum) | `ZoneParams.draw_mode` | `test_pivot_demand_stb_whole_run_and_single_candle_modes` |
| SD-R005 geçerlilik + zon→BOS bağlama | `ZoneEngine._link`, `Zone.valid` | T-SD-01, `test_structural_zone_linked_*` |
| SD-R006 flip / failed reaction (≥2 pip) | `ZoneEngine._advance, _make_flip` | T-SD-02, T-SD-03, `test_flip_requires_reaction_of_at_least_2_pips` (1.9 / 2.0) |
| SD-R007 flip + CHoCH | `_link` (flip zonları aynı pencerede bağlanır) | `test_t_sd_03_*` |
| Mitigation / invalidation | `ZoneEngine.touches, _advance` | `test_mitigation_touch_and_invalidation_by_close` |
| LQ-R001 eşit tepe/dip (≤2 pip, sınır dahil) | `liquidity/levels.py` | `test_equal_highs_tolerance_boundary_inclusive_2_pip` |
| LQ-R002 sweep zone | `liquidity/sweeps.py::is_sweep_zone` (`ZoneEngine.sweep_flag`) | `test_demand_zone_that_swept_*` |
| LQ-R003 inducement | `liquidity/sweeps.py::has_inducement` | `test_inducement_*` |
| EN-R001/1 liquidation (zorunlu kapı) | `liquidity/liquidation.py::liquidation` | `test_liquidation_*` |
| PD-R003 range filtresi (zorunlu kapı) | `structure/pd.py::range_filter` | `test_range_filter_quarter_bands` |
| D-02 rafine M15 / iç içe zon | `zones/refine.py` | `test_nested_and_refined_geometry` |
| POI-R004#1 (≥M15) + 6 kapı + 10 kriter | `strategy/poi.py::evaluate_poi` | `test_poi.py` (T-EN-01 dahil) |

Doğrulama çıktısı: `python -m photon zones --tf M15 --start 2021-09-01 --end 2021-09-30` → `zones_out/*_zones.csv` + `.png`.

---
# ONAYINIZI BEKLEYEN ÜÇ ÖNERİ

## 1) Zon → BOS/CHoCH bağlama algoritması (SD-R005, Q-Z5)
Kaynak yalnızca "BOS'u yapan hareketin başladığı arz/talep" diyor. Önerim:

1. Yapı motoru her BOS/CHoCH olayına **kırılımı yapan hareketin başladığı ucun mum indeksini** (`origin_index`) yazar:
   BOS → kutu kuralındaki uç (yeni strong low/high); trend değişimi → karşı kutu ucu; CHoCH → pullback başlangıcı (aday internal high/low).
2. Olay E (yön d, kırılım mumu `t_b`) için **aday zonlar** = aynı yönlü (BULL→talep, BEAR→arz), `created_index` (kopuş mumu) ∈ `[origin_index, t_b]`.
3. **En erken doğan** aday E'nin nedenidir (eşitlikte pivot > range). Zon `caused_events`'e E'yi ekler; `valid = bool(caused_events) or is_flip`.
4. Aynı pencerede doğan **flip zonları** da E'ye bağlanır (SD-R007: flip + yapı kırılımı = A+).
5. Pencere dışında doğan zon bağlanmaz; swing BOS > internal (CHoCH) önem sırası `Zone.caused_event` ile korunur.

Prompttaki ifadeden ("kırılım mumundan geriye, kırılan seviyeden sonraki ilk karşı yönlü zon") fark: pencerenin başını *kırılan seviyenin
oluştuğu an* yerine *hareketin başladığı uç* aldım — çünkü kırılan seviyeden sonra pullback sırasında doğan küçük bir talep (kırılımı
başlatmayan) "ilk" sayılırdı. Alternatif (B): kırılım mumundan geriye bakıp ilk karşılaşılan zon (kırılımı hemen öncesinde doğan).
`ZoneEngine._link` tek yerde; değiştirmek kolay. **Onay veya B/başka seçim?**

## 2) V-shape ölçüt önerisi (Q-Z8; POI puanı #10, ağırlık 1)
Kaynak: EN-R001 adım 3 (POI'den **agresif çıkış** olumlu, C-08) ve LQ-R006 (zona **yavaş/düzeltici** dönüş tercih). İki ayrı bağlam;
puan #10 ikisini birden anıyor. Öneri (tek, basit ölçüt — yeni indikatör yok):

- **V-shape çıkış** = POI'ye ilk dokunuştan (mitigation, M1) **M1 CHoCH'a kadar geçen M1 mum sayısı ≤ N** → puan.
  Kod: `liquidity/liquidation.py::v_shape_exit(touch_index, choch_index, max_candles)`.
- N kaynakta yok → **sizin kararınız**; öneri: önce N=10 ile başla, Aşama 7 backtest'inde (MS-R010 mantığıyla) N ∈ {5, 10, 15, 20} karşılaştır.
- LQ-R006'nın "düzeltici yaklaşma" yarısı için ölçülebilir bir tanım yok → **kodlanmadı**; puan #10 yalnızca V-shape çıkışla verilir.

Config karşılığı (onayınızda eklenecek): `v_shape_metric: {type: CANDLES_TO_CHOCH, max_candles: N}`. Şu an `REQUIRED` (strategy kapısı kapalı).
**N değeri + yalnız V-shape-çıkış yorumu onayı?**

## 3) PD-R003'ün uygulanacağı range (Q-Z9)
Varsayılan **M15 swing range** (`range_extreme_filter.range_tf: M15`, config'te). Uygulama ayrıntıları:
- Ölçülen nokta: **zonun EQ'su** ((top+bottom)/2). (Alternatif: distal kenar — daha katı.)
- Long yalnız range'in alt %25'inde (`pct ≤ 25`, dahil), short yalnız üst %25'inde (`pct ≥ 75`, dahil); %25–%75 arası → `MIDDLE_OF_RANGE`, ters tarafta → `WRONG_SIDE_OF_RANGE`.
- Range dışına taşan zonlar (pct < 0 veya > 100) uygun tarafta geçer.
- Range **onaysız/bilinmiyorsa kapı KAPALI** (sinyal yok): onaysız uçta aralık değişebilir (Q-S06).
**Onay veya farklı range (4H) / ölçüm noktası?**

---
# Diğer açık sorular

```text
ID: Q-Z1  TÜR: AMBIGUOUS  İLGİLİ KURAL: SD-R002
AÇIKLAMA: "Yutma" = kopuş mumunun KAPANIŞI, karşı yönlü koşunun en uç wick'inin ≥1 pipette ötesinde. Koşu = kopuş mumundan geriye ardışık
  karşı yönlü mumların bu şartı sağlayan en uzunu. Zon wick'li (SD-R002 DERIVED). 4H "tüm range" = tüm koşu; M15 "tek mum" = koşunun
  kopuşa en yakın mumu (son sell-to-buy mumu).
ID: Q-Z2  FRACTAL_WICK çizim modu kodlanmadı (NotImplementedError); config'te kullanılmıyor.
ID: Q-Z3  TÜR: IMPLEMENTATION DECISION REQUIRED — D1 zon çizim modu config'te yok (puan #3 "4H/D zonu içinde" D1'i anıyor).
  Öneri: D1 = RANGE (4H gibi). Verilene kadar D1 zon motoru ValueError verir.
ID: Q-Z4  TÜR: AMBIGUOUS  İLGİLİ KURAL: U-08 — Mitigation = mumun zonla kesişmesi (talepte low ≤ top; eşitlik dahil). Invalidation =
  mumun zonun KARŞI ucundan KAPANIŞLA ≥1 pipette geçmesi.
ID: Q-Z10 TÜR: UNDEFINED  İLGİLİ KURAL: SD-R006 — Flip ayrıntıları: "hedef" = zon doğduktan dokunuşa kadarki en yüksek (talepte) uç;
  tepki = dokunuştan sonra tepki başlangıcından (en derin uç) sonraki en yüksek uç, ≥ reaction_min (2 pip); FR = tepki başlangıcının ≥1 pipette
  ötesi. Tepki ≥2 pip olmadan derinleşme "düz geçiş" (flip değil, başlangıç derinleşir). Hedef ≥1 pipette kırılırsa zon 'fulfilled' (artık flip
  izlenmez). Dokunuş ve yeni-uç mumlarının kendi tepkisi sayılmaz (mum içi sıra bilinmiyor). Flip zonu = [tepki tabanı, tepki ucu] (EN-R009),
  ön koşul: Z geçerli (SD-R005). Flip zonu REVERSAL bağlamlı, origin=FLIP.
ID: Q-Z11 TÜR: AMBIGUOUS  İLGİLİ KURAL: SD-R003 — "Zondan önceki fiyat yönü" = zon doğmadan önceki mum sonu TF swing trendi.
ID: Q-Z6  TÜR: UNDEFINED  İLGİLİ KURAL: LQ-R002 — Sweep zone: zon oluşurken (first_index..created_index) wick'in geçtiği likidite =
  zon öncesi bilinen, süpürülmemiş [TF'nin son onaylı swing ucu + son karşı swing'den bu yana eşit tepe/dipler]; kopuş mumu seviyenin
  geri tarafında kapanmalı. Hesap tembel (yalnız POI adayları).
ID: Q-Z7  TÜR: UNDEFINED  İLGİLİ KURAL: LQ-R003 — Inducement: zonun fiyat tarafında, zon doğduktan sonra oluşmuş, süpürülmemiş minor dip/tepe
  veya eşit dip/tepe. "Hemen önünde" mesafe sınırı yok. ALARM anında (fiyat henüz zon dışındayken) hesaplanıp POIContext'e verilir.
ID: Q-L1  TÜR: UNDEFINED  İLGİLİ KURAL: EN-R001 adım 1 — Liquidation penceresi = fiyatın zonu son terk ettiği andan mevcut dokunuşa
  kadar; seviye = pencerede oluşmuş, zon dışındaki minor dip/tepe veya eşit dip/tepe, ilk wick geçişi dokunuş mumundan sonra olamaz.
  ⚠ BULGU: zonun dışında oluşmuş her seviye, fiyat zona inerken zaten geçilir → tek-minor seviyelerle kapı neredeyse HER ZAMAN geçer
  (anlamlı ayırt edici yalnızca eşit dip/tepe). `LiquidationResult.level.source` EQ/MINOR ayırır. Seçenekler: (a) literal (bugünkü), (b) yalnız EQ
  havuzları, (c) EQ + M1 internal referans seviyesi. Backtest'te (Aşama 7) a/b karşılaştırılabilir. **Kararınız?**
ID: Q-L2  Eşit tepe/dip havuz seviyesi = iki uçtan DIŞ olanı (en düşük dip / en yüksek tepe); süpürme eşiği o.
```

## Q-S03 tanılaması (M15 uyarıları) — neden oluşuyor
Gerçek veri sonuçlarınızı (M15'te çok sayıda) kendi makinenizde aynı komutla ölçebilirsiniz: `python -m photon structure --tf M15 ...`
artık `Q-S03 tanılama: toplam N (a=…, b=…)` + ilk 3 örnek (zaman + açıklama) yazar ve `*_diagnostics.csv` üretir.
Mekanizma (kod incelemesi + sentetik üretim): iki durum da **"kırılış mumu, bir önceki muma göre ters uçta da yeni uç yapıyor"**
(V-dönüş / dış mum benzeri) ve önceki bacak mum mum tek yönlü olduğunda oluşur:
- **a** (aday internal low yok): bullish iç yapıda internal high kırılırken pullback boyunca her mum yeni dip yapmış ve kırılış mumu da bir
  öncekinden düşük dip yapmış → "sonraki mum dibi kıramadı" şartını sağlayan mum yok → referans DEĞİŞMEZ (eski referans bayatlar).
- **b** (CHoCH sonrası referans yok): referans kırılırken kırılış mumu da bir öncekinden yüksek high yapmış, aralıkta her mum yeni high → aday yok →
  referans boş; bir sonraki geçerli kırılıma kadar CHoCH üretilmez.
Öneri (davranışı değiştirir, onayınız gerek — **Q-S09**): kırılış mumunun KENDİ ucunu, bir sonraki mum onu kıramazsa aday say
(referansı bir mum geciktirerek belirle; geleceğe bakış yok). Bu iki durumu da kapatır; a'da referansı güncel tutar, b'de referans boş kalmaz.
