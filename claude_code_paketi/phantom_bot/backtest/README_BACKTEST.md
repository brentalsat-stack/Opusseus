# Phantom SMC Backtest (Binance USDⓈ-M perpetual)

180 günlük geçmiş vadeli (perpetual) veriyle, mevcut tarama mantığını (`phantom_scan._scan_symbol`) **değiştirmeden**
adım adım yeniden oynatır, işlemleri 5 dakikalık mumlarla simüle eder ve R cinsinden rapor üretir.
Emir göndermez, API anahtarı gerektirmez (yalnızca public piyasa verisi).

> **Neden Windows bilgisayarında?** `fapi.binance.com` bazı bulut/sunucu konumlarından HTTP 451 ile engellenir.
> Veri indirme ve backtest evinizdeki bilgisayarda çalıştırılmak üzere hazırlandı.

## 1) Python kurulumu (Windows)
1. https://www.python.org/downloads/windows/ adresinden Python 3.14 (veya 3.11+) yükleyicisini indirin.
2. Yükleyicinin ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin, ardından "Install Now".
3. **Komut İstemi**'ni açın (Başlat → `cmd`) ve kontrol edin:
   ```
   python --version
   ```
   `python` tanınmazsa `py --version` deneyin ve aşağıdaki komutlarda `python` yerine `py` yazın.
4. Harici paket (pandas, requests vb.) **gerekmez**; yalnızca Python standart kütüphanesi kullanılır.

## 2) Kodu indirin
GitHub'dan ZIP indirip açın (veya `git clone`). Komut İstemi'nde `phantom_bot` klasörüne gidin, örneğin:
```
cd C:\phantom\Opusseus\claude_code_paketi\phantom_bot
```
Testler (ağ gerekmez, isteğe bağlı):
```
python backtest\run_tests.py
```

## 3) İlk deneme: `--smoke` (yaklaşık 3–5 dakika)
```
python backtest\run_backtest.py --smoke
```
2 sembol (BTCUSDT, ETHUSDT) ve 7 gün çalıştırır. Başında ekrana ve `backtest\results\schema_log.txt` dosyasına
fapi yanıtlarının **alan adlarını** (değerleri değil) yazar:
```
ŞEMA exchangeInfo: ...
ŞEMA klines: list of list, sütun sayısı=12
ŞEMA fundingRate: ...
```
Bu dosyayı geliştiriciye gösterin: gerçek yanıt şeması beklenenle aynı mı diye doğrulanır.
`HATA: ... HTTP 451` görürseniz bölgesel engel var demektir (VPN/farklı ağ deneyin).

## 4) Tam backtest
```
python backtest\run_backtest.py --days 180 --step 4
```
| Aşama | Tahmini süre |
|---|---|
| Veri indirme (20 sembol × 5 zaman dilimi + funding, ~1100 istek) | 12–25 dk (ilk çalıştırma) |
| Replay (1080 adım × 20 sembol) | 20–45 dk (çok çekirdekli) |
| Simülasyon + rapor | 5–20 dk |

* Kesintiye uğrarsa (Ctrl+C, bağlantı kopması) aynı komutu tekrar çalıştırın: indirilen CSV'ler ve biten sembollerin
  replay sonuçları önbellekten kullanılır; yalnızca eksik kısım yeniden yapılır.
* Disk: yaklaşık 100 MB (`backtest\data`), sonuçlar `backtest\results`.
* Tekrarlanabilir koşu için veri bitişini sabitleyebilirsiniz: `--end-ts <epoch_saniye>`.

### Seçenekler
| Seçenek | Anlamı |
|---|---|
| `--days N` | Replay edilen gün (varsayılan 180, `BT_DAYS`) |
| `--step H` | Replay adımı, saat (varsayılan 4, `BT_STEP_HOURS`) |
| `--symbols A,B` | Sembol listesi (varsayılan `config.BACKTEST_SYMBOLS`, 20 perpetual) |
| `--smoke` | 2 sembol, 7 gün, şema günlüğü |
| `--workers N` | Paralel süreç (varsayılan: çekirdek − 1) |
| `--skip-fetch` | İndirmeyi atla, yalnızca CSV önbelleğini kullan |
| `--force-replay` | Replay önbelleğini yok say |

Parametreler `config.py` içindeki `BT_*` ayarlarındadır (ücretler, süreler, funding vb.).

## 5) Çıktılar (`backtest\results\`)
* `bt_report_*.md` (ve son raporun kopyası `bt_latest.md`): mod (risk / confirmation) × varyant (A: TP2, B: TP1 %50 + BE)
  tabloları; dolmayan/iptal sayıları; kırılımlar (not, POI TF, yön, sembol, R:R aralığı, stop genişliği);
  maliyetli (net) ve maliyetsiz (brüt) sonuçlar yan yana; ilk %60 / son %40 doğrulama ve yalnızca ilk döneme
  dayanan eşik önerileri (son dönemde kontrol edilir).
* `bt_trades_*.csv`: her dolan işlem (mod × varyant) bir satır.
* `bt_summary_*.csv`: dönem (tümü / ilk %60 / son %40) bazında özet.
* `replay\replay_<SEMBOL>.json`: replay önbelleği (tekil setup'lar).

## 6) Varsayımlar ve sınırlar
* **1R sabit risk, kaldıraç yok.** Likidasyon modellenmez (stop'un likidasyondan önce çalıştığı varsayılır).
* Limit emir giriş seviyesinde dolar (iyileşme yok). Dolum mumunda yalnızca STOP kontrol edilir; TP/BE sonraki mumdan.
* Aynı 5m mumunda stop ve hedef birlikte → **STOP**.
* Ücret: giriş ve TP çıkışı **maker** (%0.02); STOP, BE ve TIMEOUT çıkışı **taker** (%0.05) + kayma (%0.02).
  Funding, pozisyon açıkken geçen her funding anında `yön × oran × açık oran × giriş / stop mesafesi` R olarak uygulanır.
* Süreler: risk limit emri ve POI dokunuşu ilk görülmeden itibaren `BT_TOUCH_EXPIRY_HOURS` (72) içinde; teyitten sonra
  LTF OB girişi `BT_CONFIRM_FILL_HOURS` (24) içinde dolmalı; dokunuştan sonra teyit için `BT_CONFIRM_WAIT_HOURS` (72,
  varsayım) beklenir. Açık pozisyon `BT_MAX_HOLD_DAYS` (14) sonunda piyasadan kapatılır (**TIMEOUT**, ayrı raporlanır).
* Dar stoplarda (örn. %0.25) ücret + kayma R cinsinden büyüktür; bu yüzden maliyetli/maliyetsiz sonuçlar yan yanadır.
* Risk modu, setup'ın ilk görüldüğü andaki **risk** seviyelerini kullanır; ilk görüldüğünde zaten teyitli (ENTRY_READY)
  çıkan setup'lar risk modunda `NO_RISK_LEVELS` olarak sayılır.
* Confirmation modu her 15m kapanışında `signals.ltf_status` ve `evaluate_ob_state`'i yalnızca o ana kadar kapanmış
  mumlarla çalıştırır (look-ahead yok); canlı taramadaki gibi tap sırasında EQ'ya ulaşan (MITIGATED) POI'lerde teyit aranmaz.
* Veri sonunda açık kalan pozisyonlar son kapanıştan kapatılır (TIMEOUT).

## 7) Canlı taramada vadeli veri
```
python phantom_scan.py --market crypto --source futures
```
veya `config.py` içinde `CRYPTO_DATA_SOURCE = "futures"`. Evren: `contractType == PERPETUAL`, `USDT`, `TRADING`,
`underlyingType == COIN` (alan yoksa sembol atılmaz, `EXCLUDED_SYMBOLS` ile elenir). Rapor ve log'da kaynak yazılır.

## Sorun giderme
* `HTTP 451` / "erişime kapalı": fapi bölgesel engeli; VPN veya farklı ağ.
* `HTTP 418/429`: hız sınırı; araç otomatik uzun bekler. Daha yavaş istersen `config.BT_REQUEST_DELAY` değerini artırın.
* Yavaş replay: `--workers` değerini artırın (çekirdek sayınıza göre).
* Bellek: her işçi yalnızca bir sembolün verisini yükler.
