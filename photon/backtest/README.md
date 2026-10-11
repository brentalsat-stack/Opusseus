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
