# Aşama 6 — Pozisyon yönetimi ve sinyal çıktısı (MG-R001..R006, DECISIONS §5)

Hacim dağılımları TOPLAM hacmin yüzdesidir (config `target_allocation`):

| Sınıf | Dağılım |
|---|---|
| PRO (4H ve M15 işlem yönünde) | %20 @4R (risk kaldırma, **stop yerinde**) · %60 M15 zayıf swing · %20 4H zayıf swing |
| MIXED (4H yönde, M15 ters; Q-P6 kullanıcı kararı) | PRO ile aynı |
| COUNTER_HTF (4H'ye karşı) | %20 @4R · %80 ilk M15 hedefi (sonraki M15 S&D zonu / M15 swing) |
| RANGE | %20 @4R · kalanın tamamı range ucunda (yalnız `range_extremes` verilirse; otomatik sınıflama yok — Q-M2) |

## Kural → kod → test
| Kural | Kod | Test |
|---|---|---|
| MG-R001 4R'de %20, stop yerinde; T-MG-01 (stop'ta net 0R) | `execution/position.py::PositionManager.on_candle` | `test_t_mg_01_*`, `test_stop_without_risk_removal_*` |
| MG-R002 hedefler (PT/CT/RANGE) | `execution/management.py::build_plan` | `test_pro_trend_plan_*`, `test_mixed_*`, `test_counter_trend_plan_*`, `test_range_plan_*` |
| MG-R003 trailing yok, yalnız BE | stop hiç taşınmaz (PARTIAL yöntemi); BE yöntemi NotImplemented | `test_invalid_allocations_and_unsupported_methods_rejected` |
| MG-R004 scale-in yalnız risk kaldırıldıktan sonra; T-MG-02 | `PositionManager.request_scale_in` | `test_t_mg_02_*` |
| MG-R005 çıkış planı olmadan işlem yok | `build_plan` → `Rejected(NO_EXIT_PLAN)`; giriş modeli `_finalize` | `test_mg_r005_*` |
| D-26 swing hedefi tutma onayı = 4H CHoCH | `h4_choch_since`, `on_candle(h4_choch_confirmed)` | `test_d26_*`, `test_h4_choch_since_helper_d26` |
| MG-R006 (likidite süpürmesinde kısmi kâr, L4) | kodlanmadı (L4, kaynakta ölçüt yok) | — |
| Sinyal çıktısı (ekran + log, İstanbul saati) | `signals/output.py` | `test_signal_text_*`, `test_publisher_*` |

`StrategyRunner(publisher=SignalPublisher.from_config(cfg))` olayları (SIGNAL/CANCELLED ekrana+log, REJECTED yalnız log) yayımlar.

## Açık sorular

```text
ID: Q-M1  TÜR: AMBIGUOUS  İLGİLİ KURAL: D-26 (swing hedefi tutma onayı = 4H CHoCH)
AÇIKLAMA: "Tutma onayı"nı şöyle uyguladım: son %20, 4H zayıf swing'e kadar yalnızca M15 hedefi dolduğu anda GİRİŞTEN SONRA işlem
  yönünde bir 4H CHoCH oluşmuşsa tutulur; yoksa o %20 M15 hedefinde kapatılır (`NO_HOLD_CONFIRMATION`). Tutulduktan sonra ters 4H CHoCH
  çıkış tetiklemez (kaynakta yok). 4H hedefi M15 hedefinden daha yakınsa onay aranmadan kendi seviyesinde dolar.
ID: Q-M2  TÜR: UNDEFINED  İLGİLİ KURAL: MG-R002 RANGE — Bir işlemin "range" işlemi olduğunu belirleyen kural yok; planda yalnız
  `range_extremes` açıkça verilirse kullanılır (otomatik seçilmez).
ID: Q-M3  TÜR: UNDEFINED — Kısmi kapamada lot adımı/min lot: her bacak lot adımına AŞAĞI yuvarlanır, kalan son bacağa gider; min_lot'tan küçük
  bacaklar bir sonrakine eklenir (küçük pozisyonlarda yüzdeler kayar; toplam korunur).
ID: Q-M4  TÜR: UNDEFINED — Dolum fiyatları: hedefler limit fiyatından, stop stop fiyatından (kayma yok); long çıkışı bid, short çıkışı ask (= bid + 0,4 pip).
  Aynı mumda stop + hedef → stop (kalan hacmin tamamı); sayı `PositionManager.stats['same_candle_stop_first']`.
ID: Q-M5  TÜR: AMBIGUOUS — Bacaklar bağımsızdır, fiyat sırasıyla dolar; M15 swing'i 4R seviyesinden yakınsa M15 bacağı 4R'den önce dolabilir. 4H hedefi yoksa
  %20 M15 bacağına eklenir (plan notu); M15 hedefi (PRO) / ilk hedef (CT) yoksa MG-R005 gereği sinyal REDDEDİLİR (`NO_EXIT_PLAN`).
```
