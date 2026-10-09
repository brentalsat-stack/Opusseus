# Aşama 3 — P/D, risk, seans, izin matrisi

## Kural → kod → test

| Kural | Kod | Test |
|---|---|---|
| PD-R001 / FM-08 EQ, premium/discount | `structure/pd.py` (`eq`, `classify`, `classify_state`, `aligned`) | `test_stage3_permission_pd_news.py::test_pd_*` |
| RK-R001 (≤ %1), RK-R004 (aşağı yuvarla), FM-02 | `risk/sizing.py` (`position_size`, `SizingParams`) | `test_stage3_risk.py` T-RK-01, `test_lots_always_rounded_down_*`, `test_risk_pct_above_one_percent_*` |
| RK-R002/R003b (sabit risk) | `risk_pct` config'den, tek değer | `test_one_percent_risk_default_config_values` |
| RK-R003 (3 kayıp/gün, İstanbul 00:00 sıfırlama) | `risk/limits.py` (`DayLossTracker`) | T-RK-02, `test_reset_at_istanbul_midnight` |
| SL-R001 (zon arkası, +1 pipette), SL-R002, SL-R003 (min 2 pip) | `risk/stops.py` (`stop_price`, `plan_entry`, `Rejected`) | T-EN-06, `test_stop_is_one_pipette_*` |
| SD-R008 / EN-R009 (DISTAL, EQ, FIXED_SL; zon < 2 pip → distal) | `risk/stops.py::plan_entry` | `test_fixed_sl_*`, `test_distal_and_eq_*` |
| SS-R001 (07–10, 12–15 Europe/London, IANA) | `risk/session.py::in_session`, `windows_display` | T-SS-01, `test_window_edges_*`, `test_dst_transition_days_*`, `test_istanbul_display_*` |
| SS-R002 (21:00–23:00 UTC sabit) | `risk/session.py::in_blackout`, `may_open` | T-SS-02 |
| SS-R004 (haber: engelleme yok, uyarı notu) | `signals/news.py` (`NewsCalendar`, `parse_forexfactory`) | `test_all_signals_of_the_day_*`, `test_only_high_impact_*` |
| EN-R006 izin matrisi + pro/karşı trend sınıfı | `strategy/permission.py` | T-EN-02/03/04, `test_trend_classification_*` |

Config kapıları: `risk`, `risk_sizing`, `risk_stops`, `session`, `session_blackout`, `news` (hepsi hazır; `strategy` hâlâ `v_shape_metric` bekliyor).

## Q-S06 — çözüm önerisi (onay gerekir)
P/D, TF'nin **onaylı swing aralığı** [swing_low, swing_high] üzerinden hesaplanır (POI puanı #9 ve PD-R003 "M15 swing range"
ile tutarlı). Uç henüz onaylı değilse (BOS sonrası yeni high/low) P/D **bilinmez** (`None`); internal aralık üretilmez.
`price == EQ` → ne premium ne discount.

## Açık sorular

```text
ID: Q-P1  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: EN-R006 ("M15 CHoCH")
KONUM: strategy/permission.py::check_permission(m15_choch_toward_dir)
AÇIKLAMA: Matris "önce M15 CHoCH bekle" diyor; CHoCH'un hangi andan beri/nasıl türetileceği (ör. M15 internal trend == işlem
  yönü; hangi POI temasından sonra) kaynakta yok. Fonksiyon bayrağı çağırandan alır; türetme Aşama 5'te karara bağlanacak.
SEÇENEKLER: kaynakta seçenek yok (öneri: M15 `MarketState.internal_trend == dir`).

ID: Q-P2  TÜR: UNDEFINED  İLGİLİ KURAL: SS-R001 / SS-R002
AÇIKLAMA: Pencere sınırları: başlangıç dahil, bitiş HARİÇ ([07:00,10:00), [21:00,23:00)). Kaynak sınır davranışını vermiyor.

ID: Q-P3  TÜR: UNDEFINED  İLGİLİ KURAL: RK-R003
AÇIKLAMA: "Kayıp" = net PnL < 0 ile kapanan işlem. 4R'de %20 kapatıp BE'de çıkan (net ≈ 0) işlem kayıp sayılmaz; maliyetle net
  hafif negatife düşerse sayılır.

ID: Q-P4  TÜR: AMBIGUOUS  İLGİLİ KURAL: SL-R001 / DECISIONS §4
AÇIKLAMA: "ek pay 0, 1 pipette ötesi" = stop zonun uç fiyatından 1 pipette (0,1 pip) ötede (sl_buffer_pips=0 + 1 pipette).
  FIXED_SL: giriş = stop ± 2 pip; zon yüksekliği < 2 pip ise giriş = distal, stop = giriş ∓ 2 pip (zon arkasında, 1 pipette
  şartı bu durumda uygulanmaz). EQ girişi pipette çözünürlüğüne yuvarlanır.

ID: Q-P5  TÜR: UNDEFINED  İLGİLİ KURAL: SS-R004 / DECISIONS §6
AÇIKLAMA: (a) "O gün" saat dilimi kaynakta yok → `day_reset.tz` (Europe/Istanbul) günü kullanıldı. (b) ForexFactory'nin resmi
  dışa aktarımı yalnızca BU HAFTAYI verir (forexfactory.com doğrudan 403). Geçmiş (ör. Eylül 2021) takvimi yok → backtest'te
  haber notu `UNKNOWN` (ayrı bir tarihçe kaynağı gerekir; karar sizde).

ID: Q-P6  TÜR: UNDEFINED  İLGİLİ KURAL: DECISIONS §5 (pro/karşı trend), MG-R002
AÇIKLAMA: Pro-trend = 4H ve M15 yönde; karşı trend = 4H'ye karşı. 4H yönde ama M15 karşı olan durum (EN-R006 PRO/COUNTER,
  4H POI mitigasyonuyla izinli) için yönetim sınıfı tanımsız → `TrendClass.MIXED`. Aşama 6'da hangi hacim dağılımının
  uygulanacağını belirtmeniz gerekir.

ID: Q-P7  TÜR: AMBIGUOUS  İLGİLİ KURAL: EN-R006 ek notu
AÇIKLAMA: "4H pullback'i oynamak için 4H veya üstü zon gerekir ('generally')" ile tablo satırı "(M15 POI)" çelişiyor.
  Tablo uygulandı (≥M15 POI); 4H şartı eklenmedi.
```
