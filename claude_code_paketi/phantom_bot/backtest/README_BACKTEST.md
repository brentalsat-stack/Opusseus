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
python backtest\run_backtest.py --days 365 --step 4
```
| Aşama | 180 gün | 365 gün |
|---|---|---|
| Veri indirme (20 sembol × 5 zaman dilimi + funding) | 12–25 dk (ilk çalıştırma) | +12–25 dk (eksik geri kısım; 180 günlük CSV'ler korunur) |
| Replay | 20–45 dk (çok çekirdekli) | 40–90 dk |
| Simülasyon + rapor | 5–25 dk | 10–30 dk |

* Kesintiye uğrarsa (Ctrl+C, bağlantı kopması) aynı komutu tekrar çalıştırın: indirilen CSV'ler ve biten sembollerin
  replay sonuçları önbellekten kullanılır; yalnızca eksik kısım yeniden yapılır.
* Replay önbellek şeması değiştiyse (`REPLAY_VERSION`) eski önbellek otomatik reddedilir: bu sürümde puan kriterleri
  kaydedildiği için **180 günlük replay'in bir kez yenilenmesi gerekir** (veri yeniden indirilmez).
* Disk: 365 gün için yaklaşık 200 MB (`backtest\data`), sonuçlar `backtest\results`.
* Tekrarlanabilir koşu için veri bitişini sabitleyebilirsiniz: `--end-ts <epoch_saniye>` (180 ve 365 koşusunda aynı değeri kullanın).
* Bir sembolün geçmişi istenenden kısaysa indirme sırasında `UYARI` yazılır ve replay o sembolde veri başlayana kadar olan adımları atlar.

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
Dosya adlarında pencere etiketi bulunur (`d180`, `d365`, deneme için `smoke`); farklı pencereler birbirini ezmez.
* `bt_report_<etiket>_*.md` (ve son raporun kopyası `bt_latest_<etiket>.md`):
  * Başta **önceden kayıtlı başarı ölçütü** (aşağıda) ve 365 günden kısa pencerelerde "nihai karar 365 gün raporundadır" notu.
  * Mod (risk / confirmation) × varyant (A: TP2, B: TP1 %50 + BE) tabloları: win%, ortalama R (net ve brüt), gün bazlı küme
    bootstrap %90 aralığı, P(ort>0), en iyi 5 işlem hariç ortalama, max DD, kayıp serisi, TIMEOUT; dolmayan/iptal sayıları;
    kırılımlar (not, POI TF, yön, sembol, R:R aralığı, stop genişliği); ilk %60 / son %40 tabloları.
  * **Hipotez analizleri**: minimum stop (confirmation: a = giriş × %0.5, b = 1h ATR(14)), sabit 3R hedef; her biri ilk %60,
    son %40 ve tüm dönem için; mekanik "geçti / geçmedi" işareti.
  * **Puan kriterlerinin katkısı**: her kriter için var/yok grupları (n, win%, ort. R, bootstrap aralığı, P), fark ve
    iki dönemde işaret tutarlılığı.
* `bt_trades_<etiket>_*.csv`: her dolan işlem (mod × hipotez × varyant) bir satır; puan kriterleri `crit_*` 0/1 sütunlarıdır.
* `bt_summary_<etiket>_*.csv`: dönem (tümü / ilk %60 / son %40) özeti. `bt_hypotheses_<etiket>_*.csv`: hipotez özeti ve kararlar.
* `replay_<etiket>\replay_<SEMBOL>.json`: replay önbelleği (tekil setup'lar). Önbellek şeması sürümlüdür; sürüm değişince
  otomatik olarak yeniden hesaplanır.

### Önceden kayıtlı başarı ölçütü
> Bir hipotez ancak 365 günlük veride, maliyetli net ortalama R hem ilk %60 hem son %40 döneminde > 0 VE gün bazlı küme
> bootstrap ile her iki dönemde P(ort>0) ≥ 0.90 ise 'geçti' sayılır. Aksi halde 'geçmedi'.

Rapor bu ölçütü her hipotez satırına mekanik olarak uygular (taban stratejiler karşılaştırma için aynı işareti alır).
180 günlük raporda işaretler `†` ile gösterilir; **nihai karar 365 gün raporundadır**. Izgara/eşik araması yoktur.
Çoklu karşılaştırma: kriter tablolarında yaklaşık 100 aralık vardır; yüzde 90 düzeyinde ~10'u tesadüfen sıfırı dışlar.

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
