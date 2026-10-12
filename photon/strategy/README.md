# Aşama 5 — Giriş modeli ve durum makinesi (EN-R001, FINAL_SPEC §17)

Akış (CONFIRMATION, DECISIONS §4): `WATCHING → POI_MITIGATED → CONFIRMATION_PENDING → ENTRY_READY → ORDER_PENDING`.

1. **WATCHING** — geçerli (SD-R005) ≥M15 POI için kurulum (`EntryModel.watch`; alarm anında sweep ve inducement bayrakları hesaplanır).
   Mitigation: M1 mumu POI'yi (4H POI'de içindeki **rafine M15 zonunu**, D-02) keser. Seans (SS-R001/R002) ve gün kilidi (RK-R003) yoksa ilerlemez.
   Mitigasyon anında **liquidation** (eşit tepe/dip veya M1 iç referans; Q-L1) hesaplanır.
2. **POI_MITIGATED** — EN-R006 izni; Q-P1: "M15 CHoCH" = 4H POI mitigasyonundan SONRA M15'te işlem yönünde oluşan CHoCH.
   4H'ye karşı işlemde ayrıca **M15 çift BOS** (EN-R007/D-15). İzin yoksa → WATCHING (neden `Setup.rejections`'ta).
3. **CONFIRMATION_PENDING** — M1 CHoCH (işlem yönünde, mitigasyon sonrası, warm-up değil) beklenir; fiyatın POI'de kalması şart değil.
4. **ENTRY_READY** — giriş zonu: CHoCH'a neden olan **flip zonu** (en son doğan); yoksa **extreme** (bacağı başlatan yapısal zon).
   Kapılar (`evaluate_poi`): ≥M15, SD-R005, PD-R003, EN-R006, seans, liquidation; sonra SL (min 2 pip, sabit 2 pip stop), FM-02 boyut, tekrar/karşıt sinyal politikası.
5. **ORDER_PENDING** — limit sinyal (`OrderIntent`: giriş, stop, lot+birim, ilk hedef, POI puanı + döküm, aynı olaya bağlı zonlar, haber notu).
   Dolmadan **ilk hedefe ulaşılırsa iptal** → WATCHING (DECISIONS §7). Aynı mumda hem giriş hem hedef → belirsiz: iptal edilmez, `notes`'a düşer (Aşama 7 çözer).
6. POSITION_OPEN / RISK_FREE / CLOSED / DAY_LOCKED: durum makinesi + `mark_filled` / `mark_closed` / `new_day` hazır; pozisyon yönetimi Aşama 6, fill modeli Aşama 7.

`StrategyRunner` (runner.py): M1 bid/ask akışı → D1/H4/M15 mumları (HTF→LTF sırası) → yapı + zon motorları → POI kurulumları → giriş modeli.
Warm-up (`live_from` öncesi) kurulumlar ilerlemez ve sinyal üretilmez.

## Kural → kod → test

| Kural | Kod | Test |
|---|---|---|
| EN-R001 akış (liquidation → mitigation → CHoCH → flip/extreme → limit) | `strategy/entry_model.py` | `test_entry_model.py::test_confirmation_flow_*` |
| EN-R008/EN-R009 flip vs extreme (T-EN-05) | `choose_entry_zone` | `test_t_en_05_*`, `test_flip_requires_sweep_*`, `test_choose_entry_zone_*` |
| SL-R003 (T-EN-06) | `_finalize` + `risk/stops.py` | `test_t_en_06_*` |
| POI-R004#1 (T-EN-01) | `strategy/poi.py` | `test_t_en_01_*` |
| EN-R006 + Q-P1 | `_permission`, `permission.py` | `test_t_en_02_*`, `test_q_p1_*` |
| EN-R007 çift BOS | `double_bos` | `test_counter_htf_requires_double_bos_*`, `test_double_bos_helper` |
| T-DUP-01 / karşıt sinyal | `SignalBook` | `test_t_dup_01_*`, `test_duplicate_policy_*`, `test_opposite_signal_policy_*` |
| İptal (ilk hedef) | `_pending`, `first_target`, `fill_touch` | `test_pending_limit_cancelled_*`, `test_first_target_*` |
| D-02 rafine M15 | `_targets` | `test_h4_poi_waits_for_refined_m15_zone_touch` |
| §17 durum makinesi | `state_machine.py` | `test_transition_table_*`, `test_position_lifecycle_*`, `test_global_state_helper` |
| RISK girişi (EN-R002) | `_risk_entry` | `test_risk_entry_places_limit_*` |
| MTF toplayıcı, runner | `runner.py` | `test_runner.py` |

---
# KARARLAR (kullanıcı onaylı) ve kalan açık sorular

| ID | Karar | Uygulama |
|---|---|---|
| **Q-E8** | **(b) — KULLANICI KARARI** | İzin reddinde kurulum `POI_MITIGATED`'da BEKLER (WATCHING'e dönmez). POI geçersizleşene (invalidation) kadar her M1 mumunda izin (EN-R006 + Q-P1 M15 CHoCH, EN-R007 çift BOS) yeniden değerlendirilir; açılınca `CONFIRMATION_PENDING` → M1 giriş araması sürer. Bekleme süresince limit sinyal YOK. **§17 tablosunda "izin yok → WATCHING" satırı bu karara göre değişti** (`state_machine.py` yorumu + `Setup.wait_reason`). Testler: `test_q_e8_*`. |
| Q-E5 | REJECT (**kullanıcı düzeltmesi, V8 gerçek veri teşhisi**) | `duplicate_signal_policy: REJECT` — bir POI (kurulum = POI+yön) **ömür boyu en fazla bir sinyal** üretir (iptal/kapanış sonrası yeniden sinyal yok). Önceki uygulama yalnızca eşzamanlı AKTİF ikinci sinyali engelliyordu; kurulum kapanınca/iptal olunca WATCHING'e dönüp aynı POI'den tekrar sinyal veriyordu → trades.csv'de aynı `id` tekrarlı satırlar (V0'da da). Eski davranış `REJECT_WHILE_ACTIVE` olarak korunur. Test: `test_reject_policy_gives_at_most_one_signal_and_one_trade_per_poi`, `test_v0_profile_also_has_unique_trade_ids_under_reject`. |
| Q-E6 | REJECT | `opposite_signal_policy: REJECT`. |
| Q-E1/Q-E2/Q-E7/Q-E9 | kabul | Aşağıdaki metinler aynen geçerli. |
| Q-E3 | kabul | RISK girişinde liquidation kapısı yok (varsayılan giriş CONFIRMATION). |
| Q-E4 | kabul | DOUBLE_CONFIRMATION (ve `BE_AT_FIRST_EXEC_BOS`) M1 swing eşiği kalibre edilene kadar devre dışı (`NotImplementedError`). |
| Q-L3 | kabul | 48 saat / 1 gün / 60 mum sınırları; **elenen durum sayıları** `StrategyRunner.limit_report()` ile raporlanır (backtest raporuna girecek): `liquidation_window_capped(_no_sweep)`, `zones_*_retired(_valid)`, `zones_*_range_lookback_exhausted`. |

```text
Q-E1  Çift BOS = M15'te işlem yönünde ARDIŞIK ≥2 BOS, karşı yönlü son BOS'tan beri (warm-up BOS'ları da sayılır).
Q-E2  İlk hedef (iptal kuralı): PRO/MIXED → M15 swing ucu; COUNTER_HTF → sonraki M15 S&D zonu yakın kenarı veya M15 swing'den girişe yakın olan.
      (Aşama 6 ile birleşti: iptal fiyatı = `TargetPlan.first_target`.)
Q-E7  Birden çok flip: en son doğan; extreme = bağlı yapısal zonlardan en erken doğan.
Q-E9  Karar M1 mum KAPANIŞINDA; seans/kilit kapanış anına göre; mitigasyon = mumun zonla kesişmesi (eşitlik dahil).
Q-S10 M1 iç-yapı motoru cold start: MS-R002 adayları iki yönde izlenir, ilk wick kırılımı yönü + referansı belirler.
```


## Q-Z11 — M1 giriş kutusu (kullanıcı kararı, gerçek veri teşhisi sonrası)
Sapma: DECISIONS §3 "M1 giriş kutusu = reaksiyon tabanı→tepesi" (T-QA); önceki kod M1'de SD-R001/R002 zon algılamasına bağlıydı → `NO_ENTRY_ZONE` 23/23 (CHoCH bacağı medyan 1 mum, pencerede zon yok).
Şimdi: CHoCH'a neden olan **flip** zonu varsa öncelik (EN-R008, `decisional_flip_requires_sweep` kuralı aynı); yoksa `reaction_box()` doğrudan V tepkiden çizer — zon algılaması şartı YOK:
- **DÜZELTME (V8 Eylül teşhisi):** pencere mitigasyondan değil, CHoCH'u yapan **bacaktan** alınır: `[origin_index, break_index]` (Q-E8 beklemesi ve mitigasyon başlangıcı pencereyi belirlemez; önceki tanım 16 gün bekleyen bir kurulumda 43 pipetlik kutu üretiyordu). Long: V tabanı = penceredeki en düşük low (ilk yapan mum); alt = o low; üst = taban mumu + onu doğrudan öncesindeki kesintisiz bearish mumların (pencere dışına taşabilir) en yüksek high'ı. Short simetrik. Kutu yüksekliği `ENTRY_ZONE_OK` izinde (`height_pips`) yazılır.
- `entry_zone_kind` hâlâ `EXTREME`; zon kimliği `M1-V<break_index>-D|S`, `Origin.V_REACTION`.
- `NO_ENTRY_ZONE` yalnız geçersiz pencerede (başlangıç > bitiş) oluşabilir.
**Açık (Q-Z11a):** "tabanı oluşturan ardışık karşı yönlü mumlar" kaynakta ölçülemez; uygulanan: taban mumu (rengi önemsiz) + doğrudan öncesindeki kesintisiz karşı renkli mumlar, pencere (mitigasyon) başında kesilir. Taban mumu CHoCH mumunun kendisiyse (1 mumluk bacak) kutu o mumun (+öncesi bearish'ler) aralığıdır; bu geniş olabilir (stop buna göre uzar). Test: `test_q_z11_*`.
