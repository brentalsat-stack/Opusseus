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

## Varsayılan istek bütçesi

Sembol başına 3 istek (`1day`, `4h`, `1h`) × 14 sembol = 42 istek/tarama. 8 sn aralıkla ≈ 6 dakika sürer,
800'lük günlük limitle en fazla ≈ 19 tarama yapılabilir. `12h`, `2day` ve `2h` dilimleri çekilen verilerden
birleştirilir, ek istek yapmaz. `1h→15min` eşleşmesi açılırsa istek/tarama 56'ya çıkar. Bütçe yetmezse
15min eşleşmesi ikinci turda yalnızca aday çıkan sembollerde çalışır.

## Uygulama notları (şartnamenin yorumlandığı yerler)

- **İki yön tek kural:** Short kurulumlar, fiyat ekseni ters çevrilmiş (ayna) mumlarda long kurallarıyla
  aranır ve sonuçlar geri çevrilir. Böylece long ve short için birebir aynı kurallar geçerlidir.
- **Durum makinesi yeniden oynatılır:** Her taramada POI → temas → CHoCH/MSB → re-test akışı mevcut mumlar
  üzerinde baştan hesaplanır. `kurulumlar.json` kurulumların kimliğini, aşama geçmişini ve arşivi tutar.
  Böylece a-Shell kapansa bile durum kaybolmaz.
- **Yeni sinyal** = re-test (tetik) mumu son `SINYAL_TAZELIK_MUM` onay mumu içindedir ve o zamandan beri
  stop ya da TP1 görülmemiştir. Daha eski sinyaller yalnızca istatistiğe girer.
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
