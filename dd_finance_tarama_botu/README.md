# DD Finance Price Action Tarama Botu

DD Finance "Public Video Notları" temel alınarak hazırlanan **FİNAL ŞARTNAME**'ye göre sıfırdan yazılmış,
tek dosyalık (`bot.py`) price action tarama botu. iOS **a-Shell** uyumludur.

> "%100 çalışan hiçbir şey yoktur. Price action özneldir. Tek bir konsepte bağlı kalma; en fazla
> konfirmasyonun olduğu işlemi ara. Market yapısı bütün konseptlerden önce gelir."

Bot **emir göndermez, bildirim atmaz**. Yalnızca ekrana yazar ve dosyaya kaydeder. İşlemleri kullanıcı
manuel açıp kapatır. Eğitim amaçlıdır; yatırım tavsiyesi değildir.

## a-Shell kurulum ve çalıştırma

1. a-Shell'i açın: `pip install requests`
2. `bot.py` dosyasını Dosyalar uygulamasıyla a-Shell klasörüne kopyalayın (veya `vim bot.py` ile yapıştırın).
3. `bot.py`'nin en üstündeki **AYARLAR** bölümünde `API_KEY` değerine Twelve Data anahtarınızı yazın.
   Anahtar daha önce paylaşıldıysa Twelve Data panelinden **yeni anahtar üretin**.
4. Sözdizimi kontrolü: `python3 -m py_compile bot.py`
5. Birim testleri (API isteği yapmaz): `python3 bot.py --test`
6. Çalıştırın: `python3 bot.py`
7. Sonuçlar: `cat sinyaller.csv`, `ls raporlar`, `cat raporlar/<dosya>.txt`

İsteğe bağlı: `python3 bot.py --demo` yapay veriyle (API'siz) uçtan uca bir tarama yapar. Çıktılar
`demo/` klasörüne yazılır; gerçek dosyalarınıza dokunulmaz.

**Uyarı (iOS):** a-Shell arka plana alınınca işlem durabilir. `DONGU_DAKIKA > 0` ile uzun döngüde
çalıştırırken ekranı açık tutun.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `bot.py` | Botun tamamı (AYARLAR en üstte) |
| `sinyaller.csv` | Yeni sinyaller (yalnızca ekleme yapılır; aynı sembol+yön+giriş bölgesi 24 saat içinde tekrar yazılmaz) |
| `kurulumlar.json` | Bekleyen kurulumlar (`aktif`) ve `arsiv` (sinyal / iptal / kaçtı; silinmez) |
| `gunluk_sayac.json` | Günlük API istek sayacı (UTC gün değişince sıfırlanır) |
| `istatistik.csv` | Konsept bazında dönüş ve 2R başarı oranları (ek API isteği yapmaz) |
| `raporlar/rapor_YYYY-MM-DD_HH-MM.txt` | Tarama raporu (eski rapor asla ezilmez) |
| `cache/` | Kısa süreli mum önbelleği (aynı veriyi tekrar çekmemek için) |
| `plan_disi_semboller.json` | Twelve Data planınızda olmayan semboller (ör. ücretsiz planda XAG/USD); `PLAN_DISI_BEKLEME_GUN` gün atlanır |
| `kripto_listesi.json` | Hacme göre seçilen kripto çiftleri ve 24s hacimleri (günlük yenilenir) |

## Kripto listesi (hacme göre otomatik)

Kripto çiftleri günde bir kez (`KRIPTO_LISTE_YENILEME_SAAT`) **24 saatlik hacme göre** otomatik seçilir:

1. Binance USDT spot çiftleri hacme göre sıralanır (`data-api.binance.vision`, erişilemezse `api.binance.com`,
   o da olmazsa CoinGecko).
2. Stablecoin, wrapped/staked, altın tokenları ve kaldıraçlı tokenlar elenir (`KRIPTO_HARIC`).
3. Twelve Data'da `X/USD` karşılığı olmayanlar elenir, böylece kredi boşa harcanmaz.
4. `KRIPTO` listesindekiler (BTC, ETH, SOL, BNB, XRP) her zaman dahildir; toplam `KRIPTO_SAYISI` (30) çift.

Bu adımlar Twelve Data kredisi **harcamaz**. Seçilen liste ve hacimler (milyon $) `kripto_listesi.json`'a
yazılır. Hiçbir kaynağa ulaşılamazsa önceki liste, o da yoksa `KRIPTO_SABIT` kullanılır.
`KRIPTO_OTOMATIK = False` ile sabit listeye dönülür.

## İstek bütçesi

Sembol başına 3 istek (`1day`, `4h`, `1h`). 30 kripto + 7 forex + 2 metal = 39 sembol → **117 istek/tarama**.
8 sn aralıkla bir tarama ≈ **16 dakika** sürer; 800'lük günlük limitle günde en fazla **≈ 6 tarama** yapılabilir.
Limit yaklaşırsa kalan semboller atlanır (sıra: hacme göre kripto, sonra forex, sonra metal).
Daha sık tarama için `KRIPTO_SAYISI`'nı düşürün (ör. 20 → 87 istek, ≈ 9 tarama/gün).
`12h`, `2day` ve `2h` dilimleri çekilen verilerden birleştirilir, ek istek yapmaz. `1h→15min` eşleşmesi
açılırsa sembol başına 4 istek olur; bütçe yetmezse 15min yalnızca aday çıkan sembollerde ikinci turda çalışır.

## Uygulama notları (şartnamenin yorumlandığı yerler)

- **Forex/metal hafta sonu:** Twelve Data hafta sonu da (likit olmayan) forex kotasyonu verebilir. Cuma
  `FOREX_KAPANIS_SAAT` – Pazar `FOREX_ACILIS_SAAT` (UTC) arası piyasa kapalı sayılır: tarama yapılmaz (istek
  harcanmaz) ve bu aralığa düşen mumlar analizden çıkarılır. Kış saatinde her ikisini 22 yapın.

- **İki yön tek kural:** Short kurulumlar, fiyat ekseni ters çevrilmiş (ayna) mumlarda long kurallarıyla
  aranır ve sonuçlar geri çevrilir. Böylece long ve short için birebir aynı kurallar geçerlidir.
- **Durum makinesi yeniden oynatılır:** Her taramada POI → temas → CHoCH/MSB → re-test akışı mevcut mumlar
  üzerinde baştan hesaplanır. `kurulumlar.json` kurulumların kimliğini, aşama geçmişini ve arşivi tutar.
  Böylece a-Shell kapansa bile durum kaybolmaz.
- **Yeni sinyal** = tetik (re-test) mumu son `SINYAL_TAZELIK_MUM` kapanmış onay mumu içindedir ve kapanışından
  bu yana en fazla `SINYAL_MAX_YAS_SAAT` (6) saat geçmiştir. Ardından **canlı giriş kontrolü** yapılır (1h ham veri,
  kapanmamış mum dahil):
  - `[LİMİT]`: giriş henüz dolmadı (limit emir). Fiyat girişten `LIMIT_MAX_UZAKLIK_R` (3R) fazla uzaklaştıysa
    ya da giriş gelmeden TP1'e gittiyse **kaçtı** sayılır.
  - `[AKTİF]`: giriş doldu ve güncel fiyattan R/R hâlâ `MIN_RR` üstünde.
  - **Giriş kaçtı**: giriş doldu ama fiyat uzaklaştı (güncel R/R < `MIN_RR`) → yeni sinyal yazılmaz, rapordaki
    "İptal / kaçan" bölümünde gösterilir. Stop veya TP1 görüldüyse yalnızca istatistiğe girer.
  - **İptal (yapı)**: tetikten sonra onay diliminde stop referansının (yapı seviyesi) ötesinde kapanış olduysa
    veya ters yönde CHoCH/MSB geldiyse, fiyat girişe yakın olsa bile kurulum geçersizdir (şartname 6.5 hedef
    iptali, 8.1 SFP seviyesi ötesinde kapanış).
  - Geç kalmış ama girişi hâlâ geçerli kurulumlar "GEÇ SİNYAL" notuyla izleme listesinde gösterilir.
  Her sinyal satırında tetik mumunun saati (UTC), notlarda güncel fiyat ve dolum saati yazar.
- **POI tabanı:** S&D temeldir. DD'ye göre her konsept kendi içinde bir S&D olduğundan geçerli HTF
  OB'leri ve breaker bölgeleri de POI tabanı olabilir. Her durumda `POI_MIN_PUAN` şartı aranır.
- **2h** (OB çoklu dilim teyidi) ek istek yapılmadan 1h'den türetilir (`TURETILMIS_DILIMLER`).
- **Ana swing:** Yapı analizi `ANA_SWING_UZUNLUK` fraktal adaylarıyla yürür. Stop, fib ve likidite
  için ana swing filtresi (S&D içinde oluşmuş veya BOS/MSB üretmiş) kullanılır.
- `sys` modülü yalnızca `--test` / `--demo` komut satırı argümanlarını okumak için içe aktarılır.
  Diğer izinli kütüphaneler: `requests, json, csv, datetime, time, os, math`.

## Testler (`python3 bot.py --test`)

Şartname 19.5'teki DD fib değerleri (retracement ve uzatma) ile 19.6'daki yapay mum dizileri test edilir:
geçerli/geçersiz imbalance, SFP (geçerli ve pencere içinde iptal), CHoCH sayılmayan kırılım, MSB ve
sonrasında BOS etiketi, bullish OB (ve yutmayan mum), PO3 tam dizi ve erken kırılım, QM tam dizi,
Reversal Fractal renk kuralı, tek temaslı S/R, çift sayım önleme ve mum birleştirme.
