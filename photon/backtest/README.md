# Backtest (Aşama 7)

`python -m photon backtest --start 2021-09-01 --end 2021-09-30 [--source HISTDATA] [--balance 10000] [--out backtest_out]`

Veri: önbellekteki M1 (bid; ask = bid + `costs.spread_pips`). Warm-up: `warmup_period` en büyüğü kadar geriden başlar (veri 2021-01-03'te
başlıyorsa mevcut verinin tamamı, uyarı yazılır). Warm-up süresince sinyal üretilmez. Emir gönderilmez; emirler yalnızca simüle edilir.

## Dolum modeli (kullanıcı kararları)
| Durum | Kural |
|---|---|
| Giriş (limit) | long: ask ≤ giriş (bid low ≤ giriş − spread); short: bid high ≥ giriş. Fiyat = limit, slipaj yok. Emir sinyal mumunun KAPANIŞINDAN sonraki mumdan itibaren geçerli |
| Stop | long bid ≤ stop, short ask ≥ stop. Stop fiyatından; mum AÇILIŞI stop'un ötesindeyse (gap) açılış fiyatından (`stop_gap_fills`) |
| Hedefler | long bid ≥ hedef, short ask ≤ hedef; hedef fiyatından |
| Aynı mumda giriş + stop | giriş dolar, stop olur (`entry_and_stop_same_candle`) |
| Aynı mumda giriş + hedef | hedef yok sayılır (sıra bilinmiyor; `entry_and_target_same_candle_ignored`) |
| Aynı mumda stop + hedef | stop (`same_candle_stop_first`) |
| Dolmadan ilk hedefe ulaşma | iptal (DECISIONS §7); aynı mumda dolum + hedef ise dolum işlenir |
| Komisyon | `costs.commission` (IBKR %0.002, emir başı min 2 USD); her dolum ayrı emir. Config'de yoksa 0 ve rapor "komisyon dahil değil" |
| Bakiye | kapanışta net PnL ile güncellenir; sonraki sinyaller güncel bakiyeyle boyutlanır (bileşik). Kayıp sayacı (RK-R003) net PnL ile |
| Olay zamanı | olayın olduğu M1 mumunun açılış zamanı |

## Rapor (`FINAL_SPEC §22`)
Strike rate, ortalama R, expectancy (FM-04), max drawdown (FM-10; bakiye ve R), toplam R, % getiri (+ profit factor, komisyonlu/komisyonsuz R);
VALID/INVALID × WIN/LOSS günlüğü; POI kriterlerinin isabete katkısı (var/yok win oranı, Δpp); trend sınıfı kırılımı; çıkış dolumu dağılımı;
sinyal/ret/iptal sayıları; dolum modeli sayaçları; **Q-M5** (M15/ilk hedefi 4R'den yakın işlem sayısı + listesi, yalnız rapor); **Q-L3** sınır sayaçları.

Çıktılar (`--out`): `<PAIR>_report.txt`, `_trades.csv`, `_fills.csv`, `_journal.csv`, `_signals.csv`, `_criteria.csv`,
`_diag.txt` (teşhis örnekleri), `_setups.csv` (her kurulumun aşama izi).

**Kurulum hunisi** (raporda): POI tespit → mitigasyon → izin → M1 CHoCH → giriş zonu → kapılar → sinyal → dolum; olay sayıları,
PRO / MIXED / COUNTER_HTF kırılımıyla. Kurulum izi (`Setup.trace`) yalnızca kayıt tutar, karar vermez. `_diag.txt`: `range_filter`
elemelerinde M15 range low/high (+zaman), zon EQ ve yüzde; `NO_ENTRY_ZONE`'da CHoCH bacak uzunluğu (`leg_len`) ve penceredeki zonlar.

**Zaman damgaları:** `signal_time` = sinyali üreten M1 mumunun KAPANIŞI (mum açılışı + 1 dk). Dolum en erken bir sonraki mumdadır ve
`fill_candle_open` = o mumun AÇILIŞIDIR; bu yüzden `signal_time == fill_candle_open` (örn. 07:42 = 07:42) lookahead değildir: CHoCH mumu
07:41'de açılıp 07:42'de kapanır, emir 07:42 mumunda dolar (`fill_after_signal_min` ≥ 0; test: `test_signal_candle_itself_never_fills_its_own_order`).

## Kural → kod → test
| Konu | Kod | Test |
|---|---|---|
| Dolum + stop gap | `engine._fill_entry/_manage`, `execution/position.py` | `test_backtest.py::test_limit_fills_*`, `test_stop_gap_*`, `test_entry_and_stop_*` |
| D-26 tutma onayı | `engine._manage` (`h4_choch_since`) | `test_full_winner_*`, `test_h4_choch_after_entry_*` |
| MG-R001/R004 durum | `engine._manage → mark_risk_free` | `test_risk_removal_marks_*` |
| Komisyon | `CommissionModel` | `test_commission_*` |
| §22 metrikler, journal, kriter katkısı, Q-M5 | `report.py` | `test_metrics_*`, `test_q_m5_*`, `test_write_outputs_*` |
| CLI | `__main__._backtest_cmd` | `test_backtest_cli_*` |

## Açık sorular (varsayımlar — onay bekliyor)
- **Q-B1** Başlangıç bakiyesi kaynakta yok: `config backtest.initial_balance: 10000` (USD, VARSAYIM); `--balance` ile değişir. Yalnızca lot ölçeği ve % getiriyi etkiler.
- **Q-B2** Komisyon her dolum için ayrı emir (giriş + her çıkış bacağı) ve min 2 USD uygulanıyor. 5 lotluk işlemde bu, 2 pip stoplu işlemde ~12 USD/emir → kısmi kapanışlar komisyonu artırır. Tek emir/işlem istenirse değiştirilir.
- **Q-B3** Journal: backtest yalnızca kapıları geçmiş işlem açtığı için hepsi VALID. INVALID işlem tanımı (örn. reddedilen sinyallerin varsayımsal sonucu) kaynakta yok → eklenmedi. Ret nedenleri sayı olarak raporlanır.
- **Q-B4** Dönem sonunda açık kalan pozisyonlar istatistiğe dahil edilmez, ayrıca sayılır. Bakiye/drawdown yalnızca kapanışlarda ölçülür (açık işlem dalgalanması yok).
- Kapsam dışı (henüz yapılmadı): config varyantı karşılaştırma modu, MS-R010 M1 swing eşik kalibrasyonu, eğitmen videosu ile referans karşılaştırması.

## Gerçek veri teşhisi sonrası değişiklikler (Eylül 2021, kullanıcı kararları)
- **Q-Z11** M1 giriş kutusu zon algılamasından bağımsız V tepki kutusu (bkz. `photon/strategy/README.md`). Bu, önceki backtest sonuçlarını DEĞİŞTİRİR (NO_ENTRY_ZONE elemeleri artık sinyale ilerler).
- **Q-S06 güncellemesi** onaysız uçta MS-R007 kutu aralığı → `RANGE_UNKNOWN` yalnız swing yokken. Bu da `range_filter`/`pd_alignment` sonuçlarını değiştirir.
- Lookahead şüphesi: kabul edildi (sinyal = mum kapanışı, dolum sonraki mum).

## Varyant karşılaştırma (`backtest-compare`)
`python -m photon backtest-compare --start 2021-02-01 --end 2021-12-31 --variants variants.yaml [--jobs N] [--out backtest_compare]`

- `variants.yaml`: her varyant config.yaml üzerine **override** (noktalı yol → değer); varsayılan config değişmez. Var olmayan yol hata verir (yazım hatası koruması).
  V0 mevcut · V1 `entry_price_mode: DISTAL` · V2 `EQ` · V3/V4 `fixed_sl_pips` 3/5 · V5 = V1 + `entry_zone_choice: EXTREME_ALWAYS` · V6 `range_extreme_filter.enabled: false` (yalnız etki ölçümü).
- `entry_zone_choice` (FLIP_FIRST | EXTREME_ALWAYS) config.yaml'da YOKTUR; kodda varsayılan FLIP_FIRST (= mevcut davranış). Yalnızca varyant override'ı olarak kullanılır (EN-R008 C-11 seçeneği: flip yerine hep V tepki kutusu).
- V7 (`vshape_report`): işlemleri etkilemez; taban varyantın işlemleri için `corrective_or_vshape` kriteri N ∈ {config, 5, 15, 20} ile yeniden hesaplanır (kazanan sayısı, win%, ortalama/medyan POI puanı, puanı değişen işlem). N için "POI'ye dokunuştan CHoCH'a mum sayısı" sinyal anında `OrderIntent.choch_gap`'e yazılır (kurulum kapandıktan sonra yeniden kullanıldığı için sonradan okunamaz).
- Tablo sütunları: işlem, strike%, ort R net, toplam R net (+brüt), getiri%, maxDD%, en uzun kayıp serisi, komisyon/risk% (Σkomisyon/Σhedef risk), ≤5 dk stop (kaybedenlerden dolumdan ≤5 dk'da kapananlar), giriş+stop aynı mum. Ayrıca varyant × trend sınıfı kırılımı ve huni toplamları. Çıktı: `compare.txt`, `compare.csv`, `<ad>/` altında her varyantın tam raporu.
- Paralel: varyant başına bir süreç (spawn), `--jobs 0` = min(CPU, varyant sayısı). Her süreç veriyi önbellekten kendisi okur; bellek ~ varyant sayısı × tek koşu.
- Ay bazında huni artık her raporda (`*_report.txt` "Ay bazında huni"): dolum=0 olan ay için tıkandığı aşama yazılır.

## V8 — M15 icra modeli (T-M15BT, kullanıcı kararı; ayrı profil, varsayılan config DEĞİŞMEDİ)
Kaynak: "Trading The M15 – Soft4FX Backtest" (EURUSD Eylül 2021). Videodaki model M1 icra modelinden farklı. `variants.yaml`: **V8a** (haber yok), **V8b** (haber CSV'si), **V8c** (%25 distal'dan; alternatif yorum). Hepsi override; yeni config anahtarları (kodda varsayılanlı, `config.yaml`'da YOK): `execution_profile` (M1 | M15), `session_gate`, `min_refine_pips`, `fib_entry_pct`, `news_blackout`.

| Q | Konu | Uygulama |
|---|---|---|
| **Q-V8-1** | TF eşlemesi [00:02:36] | `strategy/profile.py` rol kayması: rol "4H"→D1, rol "M15"→H4, icra→M15 (M1 modelindeki "M1" rolü). Strateji/POI/yönetim kodu ROL anahtarlarıyla çalışır; runner rol sözlüklerini gerçek TF'lerle doldurur. EN-R006 izni D1/H4 trendiyle; "M15 CHoCH" yerine H4 CHoCH (Q-P1); M1 CHoCH yerine M15 CHoCH; giriş kutusu = M15 flip, yoksa M15 V tepki kutusu (Q-Z11). POI'ler H4 ve D1 zonları (M15 zonu POI değil); POI TF tabanı ≥H4; D-02 rafine: D1 POI → içindeki H4 zonu; "iç içe zon" = H4 zonu D1 zonunda. Giriş modeli yalnız M15 mumu kapanınca adımlanır; dolum/iptal M1 ile simüle edilir. |
| **Q-V8-2** | "%25 kuralı" [00:10:42, 00:11:07, 00:12:54] — **AMBIGUOUS** | `entry_price_mode: FIB25_FROM_PROXIMAL`: long giriş = proximal(üst) − 0.25×(üst−alt); short simetrik. Stop = zon ucunun 1 pipette ötesi (zon sınırları fitil dahil; "wick varsa ötesi" ayrı kod gerektirmez). Alternatif `FIB25_FROM_DISTAL` (V8c): distal uçtan %25 yukarı/aşağı. SL-R003 (min 2 pip) geçerli: ~2.7 pipten küçük zonlarda giriş-stop mesafesi 2 pipin altında kalıp reddedilir. Kaynak "top 25%" der; hangi uçtan ölçüldüğü videoda net değil. |
| **Q-V8-3** | Küçük POI [00:34:45] | `min_refine_pips: 3`: yüksekliği 3 pipten küçük "üst TF" POI'si rafine edilmez (POI'nin kendisi hedef). |
| **Q-V8-4** | Seans/spread [00:04:31, 00:33:18–00:33:50] | `session_gate: false` → seans penceresi kapısı yok (hem mitigasyon izlemesi hem POI kapısı); rollover 21:00–23:00 UTC'de yeni emir **ve dolum** yok (V8'de dolum ertelenir, emir bekler; sayaç `blackout_fill_blocked`). |
| **Q-V8-5** (kullanıcı kararıyla GÜNCELLENDİ) | Yönetim [00:16:31–00:25:13, 00:43:46] | V8 hedefleri **H4'te** (D1'e kaymaz): %20 @4R risk kaldırma (stop yerinde), **%60 ilk H4 zayıf swing**, **%20 sonraki H4 hedefi**, tutma onayı **H4 CHoCH** (`Profile.hold_role`). CT: %20@4R + %80 ilk hedef (sonraki H4 S&D zonu / H4 swing). **Varsayım:** "sonraki H4 hedefi" = ilk hedefin ötesindeki en yakın geçerli+kullanılabilir karşı yönlü H4 S&D zonunun yakın kenarı (`management_second_target: NEXT_MID_ZONE`; yoksa %20 ilk hedefe eklenir). Videodaki %50/%80/M15-karşıt-CHoCH tam kapanış kuralları kodlanmadı. |
| **Q-V8-6** | Haber (V8b) [00:25:48, 01:03:01, 01:45:57] | `news_blackout: {file, window_min: 30}`; CSV `date,time_utc,event` (`#` yorum satırı). Olay ±30 dk: yeni emir yok (SessionClock `NEWS_WINDOW`), dolum yok, bekleyen emir iptal (`CANCELLED/NEWS_WINDOW`), açık pozisyon pencere başında mumun AÇILIŞINDAN piyasadan kapanır (long bid / short ask; bacak `NEWS_EXIT`). Takvim depoda/kaynakta YOK ve uydurulmadı: `data_samples/news_2021.csv` yoksa V8b "ATLANDI" olarak raporlanır. Şablon: `data_samples/news_2021.template.csv`. |
| **Q-V8-7** | Risk | %1 ve günlük 3 kayıp aynı. |

Sınırlar / bilinen farklar: V-shape (N=10) sayacı V8'de **M15 mum sayısıdır** (2.5 saat), M1'deki 10 dk ile aynı anlam değil (yalnız puan). Q-L3 pencereleri (liquidation 2880 mum, icra zon emekliliği 1440 mum) V8'de M15 mumu sayar (30 / 15 gün). Çıktıdaki "4H/M15 trend" etiketleri V8'de rol adıdır (D1 / H4 trendi).

**Eylül 2021 işlem listesi:** `variants.yaml` `detail: {from, to}` → her varyantın klasörüne `EURUSD_trades_detail.csv` (sinyal/dolum/kapanış UTC + Istanbul, giriş, stop, hedefler, çıkışlar, R). Yalnız V8 için: `python -m photon backtest-compare --start 2021-09-01 --end 2021-09-30 --variants variants.yaml --only V8a,V8c`.

## Q-E5 düzeltmesi, işlem numarası, dönem teşhisi (V8 gerçek veri sonrası)
- **Mükerrer id kök nedeni:** raporlama değil, strateji: `SignalBook` yalnızca *eşzamanlı aktif* ikinci sinyali engelliyordu; kurulum (POI+yön) kapanınca/iptal olunca WATCHING'e dönüp aynı POI'den yeniden sinyal verebiliyordu. Artık `REJECT` = POI başına ömür boyu en fazla bir sinyal (`Setup.n_signals`; ikinci deneme `DUPLICATE_POI` olarak bir kez kaydedilir ve kurulum izlenmez). `REJECT_WHILE_ACTIVE` eski davranış. V0 da aynı düzeltmeden etkilenir → önceki V0 sayılarıyla karşılaştırılamaz.
- Her işlemin dolum sırası `trade_no` (trades/fills/journal/detail CSV'leri); motor aynı kurulum için ikinci açık pozisyonda `RuntimeError` verir.
- `*_diag_period.txt` (`variants.yaml detail` aralığı için, her varyantın klasöründe): dönem içi huni (trend sınıfı kırılımlı), **gün gün D1/H4(/M15) trend** (00/08/16 UTC, swing aralığı, `*` = uç onaysız), dönemde yaşayan POI'lerin akıbeti (mitigasyon yok / son aşama), kurulum izleri (aşama aşama ayrıntı).

## Eylül V8a bulguları sonrası düzeltmeler
- **Q-Z11 (kutu penceresi):** CHoCH bacağı `[origin_index, break_index]`; Q-E8 beklemesinde mitigasyon başlangıcı kutuyu belirlemez. V0 (M1) ve V8 (M15) aynı kural. Test: `test_q_z11_box_comes_from_the_choch_leg_only_*`.
- **PD-R003 rol bağı:** kod zaten rol anahtarıyla çalışıyordu (`range_extreme_filter.range_tf: M15` = ORTA rol; V8'de orta rol H4), yani V8'de filtre H4 swing aralığını kullanıyordu; yalnızca teşhis etiketi yanlış okunuyordu. Etiket artık `range_tf=M15(rol→H4 swing aralığı)`; testler (`test_v8_range_filter_state_is_the_h4_swing_range_and_diag_says_so`, V0 karşılığı) bağı doğrular. V0'da M15 swing aralığı kullanılır (karar değişmedi).
- **Zon→BOS izleme:** `python -m photon trace-bos --tf H4 --start 2021-09-01 --end 2021-09-03 --type BOS --dir BULL [--out iz.txt]` (V0 için `--tf M15`). Her olay için: kırılış/origin mumu, pencere mumları (renk), pencere içindeki HER kopuş mumunda pivot ve range algılamasının sonucu **ve nedeni** (örn. "hemen önceki mum karşı yönlü değil", "kapanış koşuyu yutmuyor", "inside-bar zinciri yok"), pencerenin çevresindeki tüm zonlar (aday / elendi: yön, pencereden önce/sonra) ve sonuç (bağlı zon yok → POI oluşmaz). Algılamayı değiştirmez; `run_zones` ile aynı motorlar.

## Çok yıllı test altyapısı (kural değişikliği YOK)
**1) Veri:** HistData yıllık dosyalarını `data_samples/histdata/DAT_ASCII_EURUSD_M1_YYYY.csv` olarak koyun.
```
python -m photon import-histdata --path data_samples/histdata [--years 2016-2023]
```
`--path` dosya, dizin (yalnız `DAT_ASCII_<PAIR>_M1_*.csv`) veya glob olabilir; yıllar tek önbellekte (`HISTDATA`) birleşir. Her dosya için satır/tekrar/sırasız/geçersiz sayıları; **yıl sınırlarında süreklilik**: önceki dosyanın son mumu ile sonrakinin ilk mumu arasındaki boşluk (hafta sonu + yılbaşı normal; >4 gün `UZUN_BOŞLUK`, çakışma `ÇAKIŞMA`); dosya adlarında atlanan yıl `EKSİK YIL`. **Tekrar kontrolü:** önbellekte zaten bulunan zaman damgaları sayılır (`önbellekte zaten vardı`) ve değeri farklı olanlar ayrıca (`farklı`) raporlanır — sessiz üzerine yazma yok (yeniden içe aktarma aynı değerlerle güvenli ve idempotent). Saat dönüşümü eskisi gibi sabit EST→UTC (yıl dosyaları EST gece yarısında kesilir; çakışma beklenmez).

**2) Yıl kırılımı:**
```
python -m photon backtest-compare --periods 2016..2023 --variants variants.yaml [--only V0,V8a,V9a,V9b] [--jobs 2] [--out backtest_2016_2023]
python -m photon backtest-compare --start 2016-01-01 --end 2023-12-31 --periods year ...   # eşdeğer
```
**Tek sürekli koşu**: motor `--start`ta açılır, veri başından itibaren warm-up kesintisiz sürer (her yıl başında sıfırlanmaz), bakiye yıllar arası bileşik taşınır. Yıl satırları bu koşunun dilimleridir (`report.slice_result`): işlem **kapanış yılına** yazılır; yıl başlangıç bakiyesi = önceki yılın son kapanış bakiyesi; getiri% yıl başı bakiyeye göre; max DD yıl içi tepe-dip. Çıktı: her varyant için yıl × metrik tablosu (+TOPLAM) ve varyantlar arası yıl × {toplam R net, getiri%, işlem sayısı, max DD%} matrisleri (`compare.txt`). Uyarı: veri başındaki ilk yıl (cold start, D1/H4 yapısı olgunlaşmadan) diğer yıllarla aynı güvenilirlikte değildir.

**3) Süre:** bkz. aşağıdaki tahmin tablosu (sentetik ölçüm; gerçek veri olay yoğunluğu nedeniyle ~1.3–1.6× daha yavaş olabilir).

### Performans çalışması (sonuç DEĞİŞMEDİ — eski/yeni sürümde aynı işlem+olay özeti)
Çok yıllı koşuyu mümkün kılmak için ikinci dereceden büyüyen yerler giderildi: zon→olay bağlamada tüm zon listesi yerine ikili arama (`ZoneEngine._link`), mum zonun güvenli tarafındayken `_advance` atlanır, `Timeframe.delta` sözlük araması, `refined_zones`/`nested_parents` ucuz testler önce + kurulum başına artımlı ebeveyn/CHoCH önbelleği (`_parents`, `_choch_after`), `range_zone` için ucuz ön koşul, liquidation'da `born` indeksi ikili arama, sinyal hakkını kullanmış (Q-E5 REJECT) kurulumların izleme döngüsünden çıkarılması.

### Süre ve bellek tahmini (8 yıl ≈ 2.96 M M1 mumu; sentetik ölçüm, bu sandbox)
| Profil | ms/mum (100 gün → 400 gün) | 8 yıl / varyant (tahmin) |
|---|---|---|
| M1 icra (V0, V1–V6, V9b) | 0.11 → 0.18 (≈ +%25 / her 2× uzunlukta) | ≈ 12 dk (gerçek veri olay yoğunluğuyla ≈ 15–25 dk) |
| M15 icra (V8a/b/c, V9a) | 0.023 (400 gün) | ≈ 1–2 dk |
2 çekirdekle 12 varyant (7 M1-profil + 5 M15-profil): ≈ (7×~20 + 5×~2) / 2 ≈ **75–90 dk** (yalnız `--only V0,V8a,V9a,V9b`: ≈ 25–30 dk). Her süreç veriyi önbellekten kendisi yükler (+≈0.5–1 dk). **Bellek:** süreç başına ≈ 1.6 KB/mum → 8 yılda **≈ 4–5 GB**; `--jobs 2` ≈ 10 GB RAM ister — RAM yetersizse `--jobs 1` kullanın (süre ≈ 2×).
