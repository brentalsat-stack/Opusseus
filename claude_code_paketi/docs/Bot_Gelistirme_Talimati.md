# Phantom SMC Tarama Botu: Geliştirme Talimatı

> **Bu belgeyi alan yapay zekaya:** Aşağıdaki şartlara göre, iOS'taki **a-Shell** uygulamasında çalışacak bir Python tarama botu yaz. Strateji kuralları, bu belgeyle birlikte gönderilen **`Phantom_1.0_Part2_Kural_Raporu.md`** dosyasından gelir. Bölüm 6 bu kuralların **koda çevrilmiş, ölçülebilir** hâlidir; ikisi çelişirse **Bölüm 6 geçerlidir.** Belirsiz kalan her parametreyi `config.py` içinde ayarlanabilir bırak.

---

## 1. Amaç
- Forex ve kripto piyasalarını Phantom Trading (Smart Money Concepts / Order Block / Likidite) kurallarına göre **tarayan** bir bot.
- Bot potansiyel **setup adaylarını** bulur ve puanlar, sonra her taramayı bir dosyaya yazar.
- Kullanıcı sonuçları **manuel** inceler ve işlem kararını kendisi verir.

## 2. Kesin Şartlar (kırmızı çizgiler)
1. **Otomatik alım-satım YOK.** Hiçbir borsa veya broker emir endpoint'i kullanılmaz, API anahtarlarıyla emir gönderilmez. Binance'te yalnızca **public (anahtarsız) piyasa verisi** endpoint'leri kullanılır.
2. **Bildirim YOK.** Telegram, e-posta, push, webhook, ses gibi hiçbir bildirim olmaz.
3. **Çalışma ortamı:** iOS'ta **a-Shell**. Script kullanıcı çalıştırdığında bir kez tarar, dosyaya yazar ve **kapanır**. Arka planda sürekli çalışan döngü, daemon veya zamanlayıcı yoktur (iOS arka plandaki uygulamayı askıya alır).
4. **Her tarama sonunda dosya kaydı** zorunludur (format Bölüm 7'de).
5. **Forex verisi:** Twelve Data. **Kripto verisi:** Binance public REST.
6. **Kripto evreni:** Binance'te **24 saatlik hacme göre** seçilen yaklaşık **30–40 coin**.

## 3. Çalışma Ortamı: a-Shell Kısıtları
- Yalnızca **Python 3 standart kütüphanesi** kullan: `urllib.request`, `json`, `csv`, `datetime`, `time`, `os`, `argparse`, `math`, `statistics`.
- `pandas`, `numpy`, `requests`, `ccxt`, `TA-Lib` gibi harici paketler **kullanılmaz.** a-Shell'de kurulamayabilir veya yavaş çalışabilir.
- **Zaman dilimi:** Tüm veriyi **UTC** olarak işle. New York saati gerekiyorsa `zoneinfo("America/New_York")` dene. iOS'ta tz veritabanı yoksa ABD yaz saati kuralıyla elle hesaplayan bir yedek fonksiyon yaz: Mart'ın 2. pazarı 07:00 UTC ile Kasım'ın 1. pazarı 06:00 UTC arası UTC−4, diğer zamanlar UTC−5.
- **Dosyalar:** Script ve çıktılar `~/Documents/phantom_bot/` altında olmalı. Bu klasör iOS "Dosyalar" uygulamasından görünür.
- **Çalıştırma örnekleri:**
  - `python3 phantom_scan.py --market all`
  - `python3 phantom_scan.py --market forex`
  - `python3 phantom_scan.py --market crypto --top 35`
- **Süre:** Tarama birkaç dakika sürebilir. Konsola ilerleme yaz (ör. `[12/40] BTCUSDT 1h OK`) ve kullanıcıyı a-Shell'i ön planda tutması için uyar.
- **Hata dayanıklılığı:** Bir sembol hata verirse logla ve devam et. Tarama tek bir hata yüzünden durmamalı.

## 4. Veri Kaynakları

### 4.1 Twelve Data (Forex ve altın)
- **Endpoint:** `https://api.twelvedata.com/time_series?symbol=EUR/USD&interval=1h&outputsize=500&timezone=UTC&apikey=KEY`
- **API anahtarı:** (anahtar config_local.py içinde; paylaşılmaz). `config.py` içinde `TWELVEDATA_API_KEY` sabitine koy. Kullanıcı birkaç harfi kendisi düzeltecek, koda gömme; sadece config'ten oku.
- **Semboller (varsayılan, config'ten değiştirilebilir):** `EUR/USD, GBP/USD, GBP/JPY, EUR/JPY, AUD/USD, NZD/USD, USD/CAD, EUR/GBP, XAU/USD`
- **Zaman dilimleri:** `1day, 4h, 1h, 15min, 5min`. 1min opsiyoneldir ve varsayılan olarak kapalıdır, çünkü kredi tüketir.
- **Ücretsiz plan limiti:** Dakikada ~8 istek, günde ~800 istek. Buna göre:
  - İstekler arasında **en az 8 saniye** bekle (`REQUEST_DELAY_TD` config'te).
  - **Önbellek:** `cache/` klasörüne JSON olarak kaydet. `1day` verisini 6 saatte, `4h` verisini 1 saatte bir yenile; `1h`, `15min` ve `5min` her taramada çekilsin. Böylece bir forex taraması yaklaşık 27–45 istek eder.
  - API yanıtında `"status":"error"` veya kredi limiti mesajı gelirse bekle ve bir kez tekrar dene. Yine olmazsa o sembolü atla ve logla.
- **Pip büyüklüğü:** JPY'li pariteler `0.01`, `XAU/USD` `0.1`, diğerleri `0.0001`.

### 4.2 Binance (Kripto, anahtarsız public API)
- **Hacim sıralaması:** `GET https://api.binance.com/api/v3/ticker/24hr`
  - Sadece `USDT` ile biten spot pariteleri al.
  - **Hariç tut:** Stablecoin/stable pariteler (USDC, FDUSD, TUSD, DAI, USDP, EUR, BUSD) ve kaldıraçlı tokenlar (`UP`, `DOWN`, `BULL`, `BEAR` içerenler).
  - `quoteVolume`'a göre sırala ve ilk **N** tanesini al (varsayılan **35**, `--top` ile 30–40 arası).
- **Mum verisi:** `GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=500`
  - Zaman dilimleri: `1d, 4h, 1h, 15m, 5m`.
- **Yedek alan adı:** `api.binance.com` bölgesel olarak engellenirse `https://data-api.binance.vision` dene (config'te liste olarak).
- İstekler arasında ~0,2–0,3 sn bekle. HTTP 429 veya 418 gelirse uzun bekle.
- **Kriptoda pip yok:** Mesafeleri **fiyat yüzdesi ve ATR** ile ifade et. Kripto piyasası 7/24 açıktır, günlük mum kapanışı **00:00 UTC**'dir.

## 5. Tarama Akışı (her sembol için)
1. **HTF bias:** 1day ve 4h üzerinde piyasa yapısını çıkar (Bölüm 6.1). Trend yönünü, son swing high/low'u, protected/targeted seviyeleri ve aktif swing aralığını belirle.
2. **POI tespiti:** 4h ve 1h'de, HTF bias yönünde, **mitigate edilmemiş** order block'ları bul (Bölüm 6.3). OB'leri 15min'e rafine et.
3. **Konfluens ve puan:** Bölüm 6.8'deki puanlama tablosunu uygula.
4. **LTF teyit durumu:** 15min ve 5min'de fiyatın POI'ye dokunup dokunmadığını, dokunduysa POI yönünde BOS oluşup oluşmadığını kontrol et. Durumu `STATUS` alanına yaz (Bölüm 6.7).
5. **Seviyeler:** Önerilen giriş, stop, TP1, TP2 ve R:R değerlerini hesapla (Bölüm 6.9).
6. **Filtre:** Puanı ve R:R'si eşiğin altında kalanları "izleme listesi"ne düşür, tamamen silme.

## 6. Stratejinin Koda Çevrilmiş Kuralları
Tüm eşikler `config.py` içinde olmalıdır. Aşağıdaki değerler **varsayılandır.**

### 6.1 Swing noktaları ve market structure
- **Swing high:** Solundaki ve sağındaki `SWING_N` mumun (varsayılan `2`) high değerlerinden büyük high'a sahip mum. Swing low bunun simetriğidir.
  - Swing noktası ancak sağındaki `SWING_N` mum kapandıktan sonra onaylanır. **Look-ahead yasak.**
- **Tip 2 haritalama:** Swing'ler **fitillerle** belirlenir, kırılım **gövde kapanışıyla** doğrulanır.
  - **Bullish BOS:** Bir mum, son onaylı swing high'ın **üzerinde kapanır.**
  - Sadece fitil geçip kapanış içeride kalırsa bu BOS değildir, `LIQUIDITY_SWEEP` olarak kaydedilir.
- **Trend durum makinesi:** `BULLISH / BEARISH / UNDEFINED`
  - Uptrend'de son HL'nin (protected low) altında **gövde kapanışı** = **CHoCH**. Trend henüz dönmüş sayılmaz, durum `CHOCH_BEARISH` olur.
  - CHoCH'tan sonra bir LH oluşur ve bir **ikinci bearish BOS** gelirse trend `BEARISH` olarak onaylanır. Tersi de geçerlidir.
- **Protected low:** Son bullish BOS'u yapan hareketin **başladığı en düşük nokta** (origin), yani BOS'tan önceki swing low. Protected high bunun simetriğidir.
- **Targeted:** Uptrend'de önceki swing high hedef (targeted) olarak işaretlenir. Downtrend'de önceki swing low.
- **Aktif aralık:** Protected seviye ile son swing uç noktası arası (uptrend'de protected low → son swing high).

### 6.2 Premium / Discount
- Aktif aralığın %50'si equilibrium'dur.
- **Alış adayları yalnızca discount'ta (fiyat < %50), satış adayları yalnızca premium'da (> %50)** geçerlidir.
- Hem 1day hem 4h aralığı için ayrı hesapla ve çıktıya yaz.

### 6.3 Order Block (OB)
- **Bullish OB:** Bullish BOS'a yol açan yükseliş bacağından önceki **son bearish mum.**
  - **Rafine:** OB mumundan sonraki mum OB'nin high'ının üzerinde kapanmıyorsa, OB'yi momentumun gerçekten başladığı mumun hemen öncesindeki mum(a) kaydır. Momentum mumu = gövdesi ≥ `DISPLACEMENT_ATR` × ATR(14) (varsayılan `1.2`).
- **Bearish OB:** Bunun simetriği.
- **Zone:** OB mumunun high–low aralığı (fitiller dahil).
  - Bullish'te **proximal = high**, **distal = low**.
  - **EQ** = (high + low) / 2.
- **Geçerlilik şartları:**
  - Hareket **yapı kırmış** olmalı (Bölüm 6.1 BOS).
  - Bacakta **en az bir FVG** olması puan artırır (zorunlu değil, config ile zorunlu yapılabilir).
- **Mitigation ve geçersizlik:**
  - Fiyat oluşumdan sonra zone'a hiç girmediyse `FRESH`.
  - Zone'a girdi ama EQ'ye ulaşmadıysa `TAPPED` (hâlâ geçerli).
  - EQ'ye veya ötesine ulaştıysa `MITIGATED` (artık kullanılmaz).
  - Distal seviyenin ötesinde **gövde kapanışı** olduysa `INVALID`.
  - Zone'a `MAX_TOUCHES` kez (varsayılan `2`) girildiyse `MITIGATED`.
- **Stacking:** Aynı yönde 1day, 4h ve 1h OB'leri fiyat olarak kesişiyorsa kaç TF'nin çakıştığını say (Bölüm 6.8).
- **Extreme vs decisional:** Swing yapısını kıran hareketin origin'indeki OB `EXTREME`, bacak içindeki diğerleri `DECISIONAL` olarak işaretlenir. Extreme'e ek puan verilir.

### 6.4 FVG / Imbalance
- **Bullish FVG:** `mum1.high < mum3.low`. Boşluk = `[mum1.high, mum3.low]`. Bearish simetriktir.
- Doluluk yüzdesini hesapla: `%0 / %50 / %100 dolu`.
- FVG'ler hedef ve teyit olarak kullanılır; **tek başına giriş sinyali değildir.**

### 6.5 Likidite
- **EQH/EQL:** İki veya daha fazla swing high/low arasındaki fark ≤ `EQ_TOL_ATR` × ATR(14) (varsayılan `0.1`).
- **Liquidity sweep:** Bir mum, bir swing/EQH/EQL seviyesini **fitille** aşar ama **seviyenin içinde kapanır.**
- **Inducement:** POI'nin hemen önünde (bullish OB'nin üstünde, POI ile fiyat arasında) duran EQL veya swing low likiditesi. Varsa puan artar.
- **IRL / ERL:**
  - **Internal (IRL):** Aktif aralık içindeki swing ve EQ seviyeleri.
  - **External (ERL):** Aralığın dışındaki önceki swing high/low.
- **Ek seviyeler:** Önceki gün high/low (PDH/PDL), önceki hafta high/low (PWH/PWL) ve Asya aralığı high/low/midline. Asya aralığı yalnızca forex için hesaplanır.

### 6.6 Seanslar (yalnızca forex; saatler config'te, New York saatiyle)
Varsayılan seanslar kullanıcının kendi TradingView seans ayarlarından alınmıştır. Saatler **New York saatidir (America/New_York)**; yaz saati geçişi otomatik hesaplanır. `config.py` içinde şu yapıyla tanımla:

```python
SESSIONS = [
    # ad,    başlangıç, bitiş,  aktif
    ("ASIA", "20:00", "00:00", True),
    ("LNDN", "02:00", "05:00", True),
    ("NYAM", "09:30", "11:00", True),
    ("NYL",  "12:00", "13:00", False),
    ("NYPM", "13:30", "16:00", True),
    ("RTH",  "09:30", "16:00", False),
]
SPREAD_HOUR = ("16:45", "18:15")   # rollover uyarısı
```

- **Etiketleme:**
  - Yalnızca **aktif** (`True`) seanslar etiketlenir ve puanlanır.
  - Pasif seanslar (`NYL`, `RTH`) config'te durur, kullanıcı `True` yaparak açabilir.
  - Bitişi başlangıçtan küçük olan seans (ASIA 20:00–00:00) gece yarısını geçen seans olarak ele alınır.
  - Bir zaman birden fazla aktif seansa denk gelirse hepsi etikete yazılır.
- **Asya aralığı** (high, low ve midline): Her gün için ASIA seansının (20:00–00:00 NY) mumlarından hesaplanır.
- **Spread/rollover:** 16:45–18:15 NY arasında `SPREAD_HOUR` uyarısı üretilir.
- **Kurallar:**
  - Asya içinde oluşan LTF teyitlerine `ASIA` etiketi koy ve puanını düşür.
  - Pazar açılışından sonraki ilk `SUNDAY_HOURS` saat (varsayılan `6`) içinde durum en fazla `CONFIRMATION_ONLY` olabilir; risk entry önerilmez.
- **Haber filtresi:** Kullanıcı isteğe bağlı olarak `news.csv` dosyası tutar (sütunlar: `datetime_utc, currency, impact`).
  - Yüksek etkili bir haberin ±`NEWS_WINDOW_MIN` dakikası (varsayılan `30`) içindeki setup'lara `NEWS` uyarısı yaz.
  - Bot haberi internetten **çekmez.**

### 6.7 LTF teyit durumu (`STATUS` alanı)
| Durum | Anlamı |
|---|---|
| `WAITING_TAP` | Fiyat POI'ye henüz dokunmadı |
| `TAPPED_NO_BOS` | POI'ye dokundu, 15min/5min'de POI yönünde BOS henüz yok |
| `ENTRY1_READY` | Dokunuş sonrası **ilk** LTF BOS geldi, bu BOS'un origin'inde yeni bir LTF OB var (confirmation entry) |
| `ENTRY2_READY` | **İkinci** LTF BOS geldi, yeni OB var (double confirmation entry) |
| `INVALIDATED` | POI'nin distal seviyesinin ötesinde gövde kapanışı oldu |
| `CONFIRMATION_ONLY` | Pazar açılışı, Asya veya haber nedeniyle sadece teyitli giriş öneriliyor |

**Hangi durumda "hazır" sayılır (konfluens sırasına göre):**
- 3 TF çakışıyorsa (1day + 4h + 1h) `ENTRY1_READY` yeterlidir.
- 2 TF çakışıyorsa `ENTRY2_READY` beklenir. Güçlü BOS (gövde ≥ 1,5 × ATR) varsa `ENTRY1_READY` de kabul edilir.
- Tek TF varsa sadece `ENTRY2_READY` veya likidite süpürmesi sonrası BOS kabul edilir.

### 6.8 Puanlama (0–100, ağırlıklar config'te)
| Kriter | Puan |
|---|---|
| HTF (1day ve 4h) trend yönü setup ile aynı | +20 |
| OB stacking: 3 TF / 2 TF / 1 TF | +20 / +12 / +5 |
| OB `FRESH` (hiç dokunulmamış) | +8 |
| OB `EXTREME` | +7 |
| OB oluşurken likidite süpürülmüş (sweep → BOS) | +10 |
| Oluşum sırasında soldaki bir S/D veya OB mitigate edilmiş | +4 |
| Displacement bacağında FVG var | +6 |
| Swing yapıyı kırmış (minor/sub değil) | +8 |
| POI önünde inducement (EQH/EQL) var | +5 |
| Doğru premium/discount tarafında | +7 |
| POI'ye dönüş **corrective** (V değil) | +5 |
| LNDN, NYAM veya NYPM seansı içinde teyit | +5 |
| **Cezalar** | |
| V dönüşü (dönüş bacağında ≤ 3 mum ve ortalama gövde > 1,5 × ATR) | −10 |
| Asya içinde teyit | −5 |
| Haber penceresinde | −10 |
| Karşı-trend (HTF'ye ters) | −15 |

- **Not:** A ≥ 75, B 60–74, C 45–59. 45 altı raporlanmaz.

### 6.9 Giriş, stop ve hedef hesabı (sadece bilgi amaçlı öneri)
- **Giriş seviyesi:**
  - **Risk entry (bilgi amaçlı):** 15min'e rafine edilmiş OB'nin proximal seviyesi.
  - **Confirmation entry:** LTF OB'ye göre hesaplanır. Stop mesafesi distal'den ≤ `DISTAL_ENTRY_MAX_PIPS` (forex varsayılan `5` pip, kripto varsayılan `0.35` × ATR) ise giriş distal'e yakın konur; değilse **EQ**'ye konur.
- **Stop:**
  - Distal seviyenin ötesi + tampon.
  - Tampon: forex'te `max(spread varsayımı, 0.5 pip)`, kriptoda `0.1 × ATR`.
  - OB'nin ötesinde bir fitil varsa stop o fitilin ötesine konur.
  - **Minimum stop:** Forex `3` pip, kripto fiyatın `%0.25`'i.
- **TP1:** Giriş yönündeki en yakın IRL (swing, EQH/EQL veya karşı OB).
- **TP2:** ERL, yani targeted swing high/low veya PDH/PDL / PWH/PWL.
- **R:R** = |TP − giriş| / |giriş − stop|.
  - `MIN_RR_TP2` (varsayılan `5`) altındakiler izleme listesine düşer.
- **Yönetim notu (çıktıya metin olarak):**
  - "TP1'de riske eşit kısmi kâr (1R), ilgili swing kırılınca BE."
  - "Hedefte %75–80 kapat."
  - Bot pozisyon **takip etmez.**
- **Risk hatırlatması (çıktıya sabit metin):**
  - İşlem başına en fazla %0.25–1.
  - Toplam açık risk en fazla %3.
  - Bot lot hesabı **yapmaz.** İsteğe bağlı olarak kullanıcının girdiği bakiye ve risk yüzdesiyle pozisyon büyüklüğünü **bilgi amaçlı** gösterebilir (`--balance`, `--risk`).

## 7. Çıktı Dosyaları (her taramada)
- **Klasör:** `~/Documents/phantom_bot/scans/`
- **Dosya adları:** `scan_YYYY-MM-DD_HHMM_UTC.md`, `.csv` ve `.json` (üçü birden).
- Ayrıca `latest.md`: son taramanın kopyası, hızlı açmak için.
- **CSV sütunları:**
  - `scan_time_utc, market, symbol, direction, htf_bias_d1, htf_bias_h4, poi_tf, poi_stack, poi_proximal, poi_distal, poi_eq, poi_state, status, entry_type, entry, stop, stop_pips_or_pct, tp1, tp2, rr_tp1, rr_tp2, score, grade, premium_discount, sweep, fvg, inducement, session_tag, warnings, last_price`
- **Markdown raporunun bölümleri:**
  1. Özet: taranan sembol sayısı, hatalar, süre.
  2. **A/B setup tablosu:** puana göre sıralı.
  3. İzleme listesi (C ve düşük R:R).
  4. Her sembol için kısa HTF durum satırı: trend, protected/targeted seviye, fiyatın premium/discount konumu.
  5. Hata ve uyarı logu.
- **Çıktı dili:** Türkçe.
- **Sabit uyarı metni:** "Bu çıktı otomatik teknik analiz taramasıdır, yatırım tavsiyesi değildir. İşlem kararı kullanıcıya aittir."
- **Log:** `~/Documents/phantom_bot/logs/run_YYYY-MM-DD.log`

## 8. Kod Yapısı (öneri)
```
phantom_bot/
  config.py            # tüm eşikler, semboller, API key, saatler
  phantom_scan.py      # giriş noktası (argparse)
  data_twelvedata.py   # forex veri + cache + rate limit
  data_binance.py      # hacim sıralaması + klines
  indicators.py        # ATR, swing noktaları, FVG, EQH/EQL
  structure.py         # BOS/CHoCH durum makinesi, protected/targeted, aralık
  orderblocks.py       # OB tespiti, rafine, mitigation, stacking
  liquidity.py         # sweep, inducement, IRL/ERL, PDH/PDL, Asya aralığı
  sessions.py          # UTC ↔ NY, killzone etiketleri, haber penceresi
  scoring.py           # puanlama ve not
  report.py            # MD / CSV / JSON yazımı
  cache/  scans/  logs/
```
- **Ortak mum formatı:** Tüm veri kaynakları şu formata normalize edilir: `{"t": epoch_utc, "o": float, "h": float, "l": float, "c": float, "v": float}`. Sıralama eskiden yeniye olmalı. Twelve Data yeniden eskiye döner, **ters çevir.**
- Tamamlanmamış (hâlâ açık olan) son mum, yapı hesaplarında **kullanılmaz.** Yalnızca `last_price` için kullanılır.

## 9. Kabul Kriterleri (geliştirici kendini bunlarla test etsin)
1. a-Shell'de `python3 phantom_scan.py --market crypto --top 30` harici paket kurmadan çalışıyor ve `scans/` altında `.md`, `.csv` ve `.json` üretiyor.
2. Forex taramasında Twelve Data kredi limiti aşılmıyor (istekler arası gecikme ve önbellek çalışıyor). Limit hatasında script çökmüyor.
3. Kodda hiçbir emir, alım-satım, Telegram veya bildirim çağrısı yok.
4. Swing ve BOS hesabında look-ahead yok: onaysız swing ve açık mum kullanılmıyor.
5. Aynı veriyle iki kez çalıştırılınca aynı sonucu veriyor (deterministik).
6. `indicators.py` ve `structure.py` için, elle kurulmuş küçük mum dizileriyle birim testleri var:
   - Bir FVG'yi tespit ediyor.
   - Fitille geçişi BOS saymıyor.
   - CHoCH sonrası ikinci BOS'ta trendi çeviriyor.

## 10. Kapsam Dışı
- Otomatik emir, pozisyon takibi, bildirimler, grafik çizimi. Grafik istenirse ileride sadece dosyaya PNG olarak eklenebilir; varsayılan kapalı.
- Wyckoff şema tespiti ve Supply/Demand "flip" modeli: ilk sürümde yok. Rapordaki Bölüm 4.7 ve 4.11 ileride eklenebilir.
- Canlı haber çekme: `news.csv` manuel tutulur.

## 11. Netleştirmeler (geliştiricinin sorularına verilen kararlar)
Bu bölüm Bölüm 5–7'deki ilgili maddelerin **yerine geçer.**

1. **45 puan altı:** Bu setup'lar Markdown raporunda **gösterilmez.** Sembolün HTF durum satırı (Bölüm 7, madde 4) yine yazılır.
   - `--show-all` bayrağı verilirse 45 altı adaylar da CSV ve JSON'a `grade = "-"` ile yazılır.
   - İzleme listesi şunlardan oluşur: **C notlular (45–59)** ve puanı ≥ 45 olup `MIN_RR_TP2` eşiğinin altında kalanlar.
2. **TAPPED / MITIGATED / INVALID:**
   - Fitil dahil zone'a her giriş `TAPPED` sayılır.
   - Fitil dahil **EQ'ye ulaşmak** `MITIGATED` sayılır.
   - **Yalnızca distal'in ötesinde gövde kapanışı** `INVALID` sayılır. Fitille distal'i aşmak geçersiz kılmaz.
   - **Dokunuş sayımı mum bazında değil, ziyaret bazındadır:** Fiyat zone'dan çıkıp tekrar girerse yeni bir dokunuş sayılır.
3. **Günlük OB:** POI adayı **değildir.** Sadece **stacking puanında** ve HTF bağlam satırında kullanılır. POI adayları **4h ve 1h** OB'lerdir.
4. **Birden fazla OB:**
   - Puanı ≥ 45 olan her geçerli OB, ayrı aday olarak CSV ve JSON'a yazılır. `poi_rank` sütunu eklenir: aynı sembol ve yönde puana göre, eşitlikte fiyata en yakın olan önce.
   - Markdown'daki A/B tablosunda **her sembol ve yön için yalnızca rank 1** gösterilir.
5. **LTF BOS sayımı:**
   - 15m ve 5m **ayrı ayrı** değerlendirilir. "İkinci BOS", aynı TF'de POI dokunuşundan sonra gelen ikinci aynı yönlü BOS'tur. İki TF'nin BOS'ları birbirine eklenmez.
   - Rapor iki TF'den **daha ileri** olan durumu alır ve hangi TF'den geldiğini yeni `ltf_tf` sütununa yazar.
   - **Güçlü BOS:** BOS mumunun gövdesi ≥ 1.5 × ATR(14). ATR, o mumun kendi TF'sindeki ATR'dir.
6. **Durum önceliği:**
   - `INVALIDATED` her şeyin üstündedir.
   - `CONFIRMATION_ONLY` bir durum değil, **ayrı bir kısıt bayrağıdır.** Yeni `entry_restriction` sütununa yazılır (değerler: `SUNDAY`, `ASIA`, `NEWS`; birden fazlası virgülle).
   - Bu bayrak varsa **risk entry önerilmez.** `STATUS` alanı normal değerini (`WAITING_TAP`, `ENTRY1_READY` vb.) korur.
7. **Hedef bulunamazsa:**
   - TP1 için IRL yoksa alan boş kalır.
   - TP2 için ERL yoksa sırayla PDH/PDL, sonra PWH/PWL denenir. Hiçbiri yoksa alan boş kalır.
   - R:R hesaplanamayan setup **izleme listesine** düşer, `warnings` alanına `NO_TARGET` yazılır.
8. **news.csv:**
   - `impact` alanı büyük/küçük harf duyarsızdır: `high`, `red` ve `3` yüksek etki kabul edilir.
   - `currency` alanı paritenin **iki para birimiyle de** eşleştirilir (XAU/USD için USD). `ALL` her pariteye uyar.
   - Kripto için yalnızca `USD` ve `ALL` haberleri dikkate alınır.
9. **Twelve Data anahtarı:** `config.py` içinde verildiği gibi yazılır (kullanıcı kendisi düzeltecek). Anahtar **hiçbir log'a, rapora veya ekran çıktısına yazılmaz**; URL loglanırken `apikey=***` olarak maskelenir.
10. **Pozisyon büyüklüğü (`--balance`, `--risk`):** İlk sürümde **yok.** Bölüm 6.9'daki ilgili cümle şimdilik geçersizdir; ileride ayrı bir adım olarak eklenecek.
11. **Adım planı:** Geliştirme `Bot_Adim_Adim_Promptlar.md` dosyasındaki adım sırasıyla yapılır. Veri adımları (Binance, Twelve Data) göstergelerden **önce** gelir; amaç, a-Shell'deki internet ve API erişim sorunlarını erken görmektir.
12. **CSV'ye eklenen sütunlar:** `poi_rank`, `ltf_tf`, `entry_restriction` (Bölüm 7'deki listeye eklenir).
13. **Test verisi:** Adım 4–10 testleri, elle oluşturulmuş **sentetik OHLC dizileriyle** yazılır. İnternet gerekmez.
14. **Spread:** Twelve Data spread vermediği için spread varsayımı `config.py` içinde parite bazında bir sözlük olur (değerler pip cinsinden, kullanıcı brokerına göre düzeltir):
    `FOREX_SPREAD_PIPS = {"EUR/USD": 0.8, "GBP/USD": 1.0, "AUD/USD": 1.0, "NZD/USD": 1.5, "USD/CAD": 1.5, "EUR/GBP": 1.2, "EUR/JPY": 1.5, "GBP/JPY": 2.5, "XAU/USD": 3.0, "DEFAULT": 1.5}`
15. **Aday sayısı:** `MAX_POI_PER_SYMBOL_DIR = 3`. Her sembol ve yön için puanı en yüksek ilk 3 aday CSV ve JSON'a yazılır. Markdown kuralı Bölüm 11, madde 4'teki gibi kalır.
16. **LTF:** İlk sürümde teyit yalnızca **15m ve 5m** üzerinde aranır. 1m/3m'e inilmez. Forex 1min verisi kapalıdır ama config'ten açılabilir (`ENABLE_1M = False`).
17. **Dosya planı:** Geliştirme, `Bot_Adim_Adim_Promptlar.md` dosyasındaki adımlarla yürür ve **her adım kendi test dosyasıyla** (`test_stepN.py`) teslim edilir. Testler sona bırakılmaz.
    - `utils.py` Adım 1'de yazılır.
    - Giriş/stop/hedef hesabı ve LTF durumu Adım 8'deki `signals.py` içindedir.
    - Sembol başına tarama akışı Adım 11'de `phantom_scan.py` içindedir. Ayrı `levels.py` ve `scanner.py` dosyaları açılmaz.

## 12. İlk Sürümden Öğrenilen Zorunlu Kurallar
İlk sürüm gerçek veriyle çalıştırıldığında aşağıdaki hatalar görüldü ve düzeltildi. Bu kurallar Bölüm 5–11'deki ilgili maddelerin **yerine geçer.** Yeni yazılan kod bunları baştan uygulamalıdır.

### 12.1 Veri ve zaman
1. **Açık mum:** Twelve Data'nın son mumu da açık olabilir. `t + TF süresi > şimdi` ise o mum açık sayılır; yalnızca `last_price` için kullanılır, hiçbir yapı, OB, seviye veya LTF hesabına girmez. Bu kural Binance için de aynıdır.
2. **OB durumu (mitigation):** OB mumundan değil, OB'yi doğrulayan **BOS mumundan sonraki** mumlarla değerlendirilir.
3. **LTF penceresi:**
   - 15m ve 5m teyidi yalnızca POI'yi doğrulayan HTF BOS mumu **kapandıktan sonraki** mumlarla aranır.
   - 15m ve 5m verisi kısaltılmaz, indirilen tüm mumlar kullanılır. HTF analizi son 160 mumla yapılabilir.
4. **HTF dokunuşu:** HTF'de OB durumu `TAPPED` ise ama LTF penceresinde dokunuş görünmüyorsa:
   - Durum `WAITING_TAP` değil `TAPPED_NO_BOS` olur.
   - BOS araması pencerenin ilk mumundan başlar.

### 12.2 Filtreler (LTF hesabı ve puanlamadan ÖNCE uygulanır)
5. **Aktif aralık 4h'ten:** Aktif aralık, protected ve targeted seviyeleri **tüm POI'ler için 4h yapısından** alınır, 1h POI'ler dahil. 4h trendi adayın yönüyle aynı değilse protected/targeted yerine `range_low` / `range_high` kullanılır.
6. **Premium/discount POI'ye göre:** Kontrol, POI'nin **EQ'suna göre** yapılır, mevcut fiyata göre değil. Alışta EQ aralığın %50'sinin altında, satışta üstünde olmalıdır. Bu bir **filtredir**; sağlamayan aday sonuçlara girmez.
7. **Aralık filtresi:** Alışta POI ≥ protected low (veya `range_low`), satışta POI ≤ protected high (veya `range_high`). Dışındakiler elenir.
8. **Mesafe filtresi:** |giriş − son fiyat| ≤ `MAX_POI_DISTANCE_ATR_D1` (3.0) × günlük ATR(14). Uzaktakiler elenir.
9. **Elenen adaylar:** `INVALIDATED` ve 6–8. maddelerde elenen adaylar sadece log dosyasına yazılır, **ekrana yazılmaz.** Ekrana yazılırsa gerçek taramada yüzlerce satır oluşuyor.
10. **Tekilleştirme:** Sembol + yön + POI TF + proximal + distal değerleri aynı olan adaylar tek kayda indirilir.

### 12.3 Hedefler
11. **TP2:** Aktif aralığın **targeted** seviyesidir (alışta aralık tepesi, satışta aralık dibi). Hem girişin hem **mevcut fiyatın** ötesinde olmalıdır. Bu sağlanmazsa sırayla PDH/PDL, sonra PWH/PWL denenir; hiçbiri uymazsa `NO_TARGET`.
    > Eski "girişten sonraki en yakın ERL" kuralı **kullanılmaz.** Bu kural, giriş fiyatın çok altında olduğunda hedefi girişin hemen yanına düşürüyordu (R:R 0,05–0,35).
12. **TP1:** Giriş ile TP2 arasında, girişten **en az 1R** uzaktaki en yakın IRL'dir. TP1 hiçbir zaman TP2'yi geçemez.

### 12.4 Puan kriterlerinin kesin tanımları
Kriterler `orderblocks.py`'de hesaplanır. `scoring.py` yalnızca doğru/yanlış değerleri puana çevirir.

13. **sweep_then_bos:** `origin_index − SWEEP_LOOKBACK (5)` ile `bos_index` arasında (BOS hariç), karşı taraftaki onaylı bir swing'in fitille alındığı bir `LIQUIDITY_SWEEP` olmalıdır. Bullish OB için alınan swing bir low, bearish OB için bir high olur.
14. **major_structure_break:** BOS'un kırdığı seviye, `SWING_N_MAJOR = 5` ile hesaplanan swing noktalarında da bir swing ise kırılım majördür ve puan alır. Sadece `SWING_N = 2` fraktalında olan kırılım minordur, puan almaz.
15. **Dönüş tipi:**
    - Dönüş bacağı, BOS'tan sonraki uç noktanın (extreme) **bir sonraki mumundan** başlar ve OB'ye ilk dokunan muma kadar sürer. OB'ye dokunulmadıysa son kapanmış muma kadar sürer.
    - **V-dönüş:** Bacak ≤ 3 mum ve ortalama gövde > 1.5 × ATR. Yalnızca OB'ye **gerçekten dokunulduysa** ceza verilir.
    - **Corrective:** Bacak ≥ 4 mum ve ortalama gövde ≤ 1.0 × ATR.
    - Bacak 0 mumsa ikisi de yanlıştır.
16. **mitigated_left_zone:** OB'nin oluşum bacağı (`origin_index` → `bos_index`), aynı yöndeki daha eski bir OB'nin zone'una girdiyse doğrudur.
17. **SPREAD_HOUR:** Rollover saatindeyse adayın `warnings` listesine eklenir.

### 12.5 Rapor
18. **A/B tablosu:** Bir adayın bu tabloya girmesi için not A/B olmalı, `rr_tp2 ≥ MIN_RR_TP2` olmalı ve `NO_TARGET` uyarısı olmamalıdır. Bir aday iki tabloda birden görünmez.
19. **Fiyat yuvarlama:** Forex 5 hane, JPY ve XAU 3 hane, kripto 6 anlamlı basamak.
20. **Ekrandaki A/B/C sayımı** rapora giren son listeden yapılır (`MAX_POI_PER_SYMBOL_DIR` uygulandıktan sonra).
21. **Testler gerçek rapor klasörüne yazmaz:** Testler geçici klasör kullanır (`tempfile.mkdtemp`). Gerçek `scans/` klasörüne ve `latest.md` dosyasına asla dokunmaz.

### 12.6 Doğrulama
- Her adımda, bir önceki sürümde sorun çıkaran senaryolar için sentetik testler yazılır. En az şunlar:
  - Fitille geçiş BOS değildir.
  - Açık mum hesaplara girmez.
  - OB'ye dokunulmadan son mum büyük bir itki mumuysa V cezası verilmez.
  - TP1 < TP2 olur ve TP2 fiyatın ötesindedir.
  - Aralık dışındaki POI elenir.
  - Uzaktaki POI elenir.
  - Testler gerçek `latest.md` dosyasına yazmaz.

---
**Ek:** Strateji kuralarının tam açıklaması için `Phantom_1.0_Part2_Kural_Raporu.md` dosyasına bak. Özellikle şu bölümler: Bölüm 2 (Model 0, 4, 5, 7, 8), Bölüm 4.1–4.4 ve 4.8–4.10.
