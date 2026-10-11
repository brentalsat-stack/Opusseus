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
# BU AŞAMADA SİZE SORULANLAR (kodlanmadı / karar bekliyor)

```text
ID: Q-E5  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: FINAL_SPEC §19, T-DUP-01
KONUM: config `duplicate_signal_policy` (REQUIRED) — strateji kapısı kapalı
AÇIKLAMA: Aynı POI için ikinci sinyal (aktif = ORDER_PENDING/POSITION_OPEN/RISK_FREE kurulum varken).
SEÇENEKLER (kodlu): REJECT (ikinciyi reddet, raporla — FINAL_SPEC T-DUP-01 varsayılanı) | REPLACE (bekleyen eskiyi iptal et, yenisini ver;
  açık pozisyon varsa reddedilir) | ALLOW (ikisi de). Önerim: REJECT.

ID: Q-E6  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: FINAL_SPEC §19
KONUM: config `opposite_signal_policy` (REQUIRED)
AÇIKLAMA: Açık/bekleyen bir sinyal varken karşıt yönlü yeni sinyal (hedge yalnız EXAMPLE_ONLY).
SEÇENEKLER: REJECT | ALLOW. Önerim: REJECT.

ID: Q-E8  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: EN-R006 + Q-P1 (kullanıcı kararı)
AÇIKLAMA: İzin yoksa kurulum WATCHING'e döner (§17) ve izin YALNIZCA fiyat POI içindeyken (aynı dokunuşun sonraki mumlarında) yeniden
  değerlendirilir. Q-P1 gereği M15 CHoCH mitigasyondan SONRA gelir; çoğu zaman fiyat POI'yi terk ettikten sonra oluşur → o ziyaret için
  sinyal kaçırılır, kurulum yeni dokunuşu bekler.
SEÇENEKLER: (a) bugünkü (yeni dokunuş) | (b) izin reddi sonrası kurulum "POI_MITIGATED bekleme" durumunda kalsın; M15 CHoCH gelince (POI
  geçersiz olmadıkça, seans içinde) CONFIRMATION_PENDING'e geçsin. Önerim: (b), ama §17 tablosundaki "izin yok → WATCHING" satırını değiştirir.

ID: Q-E1  TÜR: AMBIGUOUS  İLGİLİ KURAL: EN-R007 / D-15 — "M15'te çift BOS (HH+HL)": işlem yönünde ARDIŞIK ≥2 M15 BOS, karşı yönlü son
  BOS'tan beri (zaman bağı yok; warm-up BOS'ları da yapıdır ve sayılır).
ID: Q-E2  TÜR: UNDEFINED  İLGİLİ KURAL: DECISIONS §7 "ilk hedef" — İptal kuralı için ilk hedef: PRO/MIXED → M15 swing ucu (trend yönünde, girişin ötesinde);
  COUNTER_HTF → bir sonraki M15 S&D zonunun yakın kenarı veya M15 swing ucundan girişe en yakın olan. Hedef yoksa iptal kuralı uygulanmaz.
  (Aşama 6 hedef listesiyle birleşecek.)
ID: Q-E3  TÜR: UNDEFINED  İLGİLİ KURAL: EN-R002 RISK girişi — HTF POI'ye doğrudan limit; liquidation kapısı uygulanamaz (kapalı), EN-R006 izni
  "fiyat POI'de" varsayımıyla değerlendirilir, fiyat girişe zaten ulaşmışsa yerleştirilmez. İleride test (DECISIONS §4).
ID: Q-E4  TÜR: IMPLEMENTATION DECISION REQUIRED  İLGİLİ KURAL: EN-R002 DOUBLE_CONFIRMATION — ikinci M1 BOS gerekir; M1 swing eşiği henüz yok
  (DECISIONS §2: M1 swing yalnız double-confirmation testinde, kalibrasyondan sonra). Seçilirse NotImplementedError.
ID: Q-E7  TÜR: AMBIGUOUS  İLGİLİ KURAL: EN-R008 — Birden çok flip zonu aynı CHoCH'a bağlıysa EN SON doğan; extreme = bağlı yapısal zonlardan en erken doğan.
ID: Q-E9  TÜR: UNDEFINED — Zamanlama: sinyal/karar M1 mumunun KAPANIŞINDA verilir; seans/kilit kontrolü kapanış anına göre (10:00'da kapanan 09:59 mumu
  seans dışı). Mitigasyon, mumun POI/rafine zonla kesişmesidir (eşitlik dahil).
ID: Q-L3  TÜR: IMPLEMENTATION LIMITS (strateji parametresi değil): liquidation seviye penceresi en fazla 2880 M1 (48 sa); M1 zonları 1440 mumdan
  eskiyse izlenmez; range zincir araması geriye en fazla 60 mum (önceki 200). Hız için; davranış etkisi yalnızca bu eşiklerin ötesinde.
ID: Q-S10  TÜR: UNDEFINED — M1 iç-yapı motoru (internal_only) için cold start: MS-R002 adayları iki yönde izlenir, ilk wick kırılımı yönü ve
  referansı belirler (MS-R003). Swing/BOS yok.
```
