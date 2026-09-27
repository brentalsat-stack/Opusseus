#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  DD Finance Price Action Tarama Botu
#  Kaynak: DD Finance "Public Video Notları" – FİNAL ŞARTNAME (Part 1–17 birleşik)
#
#  "%100 çalışan hiçbir şey yoktur. Price action özneldir. Tek bir konsepte
#   bağlı kalma; en fazla konfirmasyonun olduğu işlemi ara. Market yapısı bütün
#   konseptlerden önce gelir."
#
#  Kullanım:
#     python3 bot.py            -> tarama (DONGU_DAKIKA > 0 ise döngü)
#     python3 bot.py --test     -> birim testleri (API isteği yapmaz)
#     python3 bot.py --demo     -> yapay veriyle uçtan uca deneme (API yok,
#                                  çıktılar demo/ klasörüne yazılır)
#
#  Bot emir göndermez, bildirim atmaz. Sadece ekrana yazar ve dosyaya kaydeder.
#  Eğitim amaçlıdır; yatırım tavsiyesi değildir.
# =============================================================================

import json
import csv
import datetime
import time
import os
import math
import sys  # yalnızca komut satırı argümanlarını (--test / --demo) okumak için

try:
    import requests
except ImportError:  # a-Shell'de: pip install requests
    requests = None


# =============================================================================
#                                   AYARLAR
# =============================================================================

# --- API VE LİMİTLER ---------------------------------------------------------
# Güvenlik: Anahtar daha önce paylaşıldıysa Twelve Data panelinden YENİ anahtar
# üretip buraya yazın. (İsterseniz TWELVE_DATA_API_KEY ortam değişkeni de olur.)
API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "BURAYA_TWELVE_DATA_ANAHTARINIZI_YAZIN")
API_URL = "https://api.twelvedata.com/time_series"
ISTEK_ARASI_SN = 8          # Dakikada 8 istek limiti için bekleme
GUNLUK_LIMIT = 800          # Aşılırsa tarama durur
TEKRAR_DENEME = 3           # Limit / geçici hata için deneme sayısı
LIMIT_BEKLEME_SN = 65       # Limit hatasında bekleme
DONGU_DAKIKA = 0            # 0 = tek tarama; >0 = belirtilen aralıkla tekrar
ISTEK_ZAMAN_ASIMI_SN = 30   # HTTP zaman aşımı

# --- SEMBOLLER ---------------------------------------------------------------
# Kripto listesi günde bir kez 24 saatlik hacme göre otomatik belirlenir
# (Binance USDT çiftleri -> Twelve Data'da X/USD karşılığı olanlar). Bu işlem
# Twelve Data kredisi HARCAMAZ. KRIPTO her zaman listede tutulur.
KRIPTO = ["BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD", "XRP/USD"]
KRIPTO_OTOMATIK = True          # False -> yalnızca KRIPTO + KRIPTO_SABIT kullanılır
KRIPTO_SAYISI = 30              # Taranacak toplam kripto çifti
KRIPTO_LISTE_YENILEME_SAAT = 24 # Hacim listesi bu aralıkla yenilenir
# Otomatik liste alınamazsa kullanılacak yedek liste (hacmi yüksek çiftler)
KRIPTO_SABIT = ["BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD", "XRP/USD", "DOGE/USD", "ADA/USD",
                "TRX/USD", "AVAX/USD", "LINK/USD", "SUI/USD", "LTC/USD", "DOT/USD", "NEAR/USD",
                "UNI/USD", "AAVE/USD", "BCH/USD", "PEPE/USD", "TON/USD", "APT/USD", "ARB/USD",
                "FIL/USD", "ENA/USD", "WLD/USD", "TAO/USD", "OP/USD", "INJ/USD", "ETC/USD",
                "HBAR/USD", "ZEC/USD"]
# Hacim listesinden çıkarılanlar: stablecoin, wrapped/staked, altın tokenları
KRIPTO_HARIC = ["USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDP", "BUSD", "USDE", "USD1", "PYUSD",
                "RLUSD", "USDD", "EUR", "EURI", "AEUR", "TRY", "BRL", "GBP", "JPY",
                "WBTC", "WETH", "WBETH", "STETH", "BETH", "BFUSD", "XUSD", "PAXG", "XAUT"]
FOREX = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "USD/CAD", "GBP/JPY"]
METALLER = ["XAU/USD", "XAG/USD"]
# Forex/metal hafta sonu kapanışı (UTC). Twelve Data hafta sonu da mum verebilir;
# bu aralıktaki mumlar analizden çıkarılır ve piyasa kapalı sayılır.
FOREX_KAPANIS_SAAT = 21     # Cuma (kış saatinde 22)
FOREX_ACILIS_SAAT = 21      # Pazar (kış saatinde 22)
PLAN_DISI_BEKLEME_GUN = 7   # Planınızda olmayan sembol bu kadar gün atlanır (kredi harcamaz)

# --- ZAMAN DİLİMLERİ ---------------------------------------------------------
ZAMAN_DILIMI_ESLEME = {"1day": "4h", "4h": "1h", "1h": "15min"}   # POI dilimi -> onay dilimi
AKTIF_ESLEMELER = ["1day→4h", "4h→1h"]
MUM_SAYISI = {"1day": 300, "4h": 900, "1h": 500, "15min": 300}      # outputsize
# Ek istek yapılmadan birleştirilen dilimler: hedef -> (kaynak, kat)
# (2h, OB çoklu dilim teyidi için 1h'den türetilir; ek istek gerektirmez.)
TURETILMIS_DILIMLER = {"12h": ("4h", 3), "2day": ("1day", 2), "2h": ("1h", 2)}
MIN_MUM = 100               # Bundan az mum -> o dilim atlanır

# --- SWING VE YAPI -----------------------------------------------------------
IC_SWING_UZUNLUK = 2        # İç (micro) swing fraktalı
ANA_SWING_UZUNLUK = 5       # Ana swing fraktalı
ATR_PERIYOT = 14
DISPLACEMENT_ATR = 1.5      # Güçlü mum eşiği (gövde / ATR)
STOP_TAMPON_ATR = 0.2       # Tüm stoplara eklenen pay

# --- SİNYAL VE RİSK ----------------------------------------------------------
MIN_SKOR = 3
MIN_RR = 1.5
POI_MIN_PUAN = 1.5
ONAY_MAX_MUM = 20
RETEST_MAX_MUM = 15
SINYAL_TAZELIK_MUM = 1      # Tetik mumu son kaç kapanmış onay mumu içindeyse "yeni sinyal"
SINYAL_MAX_YAS_SAAT = 6     # Tetik mumunun kapanışından bu yana en fazla geçen süre (saat)
LIMIT_MAX_UZAKLIK_R = 3.0   # Dolmamış limit girişten bu kadar R uzaklaştıysa "kaçtı" sayılır
# Canlı giriş kontrolü (1h ham veri, kapanmamış mum dahil):
#  - Giriş dolmadıysa sinyal "LİMİT" olarak raporlanır (fiyat TP1'e girişsiz gittiyse kaçtı).
#  - Giriş dolduysa güncel fiyattan R/R hesaplanır; MIN_RR altındaysa "giriş kaçtı".
TEKRAR_YAZMA_SAAT = 24      # Aynı sembol+yön+giriş bölgesi bu süre içinde tekrar yazılmaz
BOLGE_MAX_YAS_MUM = 400     # POI olarak değerlendirilecek bölgenin en fazla yaşı (mum)

# --- LİKİDİTE ----------------------------------------------------------------
LIK_EQUAL_TOLERANS_ATR = 0.1
LIK_RELATIVE_TOLERANS_ATR = 0.5
LIK_RELATIVE_MAX_MUM = 30
LIK_MIN_TEMAS = 2
LIK_MAX_HAVUZ = 5           # Yön başına

# --- SUPPLY & DEMAND ---------------------------------------------------------
SD_HAREKET_ATR = 1.5
SD_BAZ_GOVDE_ATR = 0.6
SD_BAZ_MIN_MUM = 1
SD_BAZ_MAX_MUM = 8
SD_DEVAM_BAZ_MIN_MUM = 4
SD_DEVAM_BAZ_MAX_MUM = 40
SD_DEVAM_BAZ_MAX_YUKSEKLIK_ATR = 2.0
SD_DEVAM_AYKIRI_FITIL_ATR = 0.5
SD_CIZGI_GRAFIK = True
SD_MAX_TEMAS = 1

# --- ORDER BLOCK -------------------------------------------------------------
OB_BOLGE_MODU = "son_mum_fitil"     # son_mum_govde / son_mum_fitil / grup_govde / grup_fitil
OB_YUTMA_REFERANS = "kapanis"       # kapanis / uc
OB_SWING_MESAFE_ATR = 0.5
OB_LIKIDITE_MESAFE_ATR = 0.5
OB_TEYIT_ZAMAN_DILIMLERI = ["1day", "4h", "2h", "1h"]
OB_GIRIS_TIK_ATR = 0.05             # OB_GIRIS_TIK = ATR x 0.05
KULLANILMIS_OB_PUAN = 0.5
OB_KIRILIM_MAX_MUM = 30             # OB'den sonra yapı kırılımı için bakılan mum

# --- IMBALANCE / GAP ---------------------------------------------------------
IMB_BUYUK_MUM_ATR = 1.5
IMB_BUYUK_MUM_ORAN = 2.0
IMB_MIN_ATR = 0.3
IMB_FITIL_MAX_ORAN = 0.4
IMB_ON_TEPKI_ATR = 0.2
CME_KAPANIS_SAAT = 21               # Cuma (UTC) – kış saatinde 22 yapın
CME_ACILIS_SAAT = 22                # Pazar (UTC) – kış saatinde 23 yapın
GAP_MIN_ATR = 0.1

# --- BREAKER -----------------------------------------------------------------
BREAKER_BOLGE_MODU = "govde"        # govde / son_fitil / cizgi
BREAKER_ZAMAN_DILIMLERI = ["4h", "12h", "1day"]
BREAKER_RETEST_TOLERANS_ATR = 0.3

# --- S/R FLIP ----------------------------------------------------------------
SR_MIN_TEMAS = 3
SR_TEMAS_ARASI_MIN_MUM = 5
SR_TOLERANS_ATR = 0.25
SR_MAX_SEVIYE = 3

# --- RANGE / DEVİASYON -------------------------------------------------------
RANGE_MIN_MUM = 20
RANGE_MIN_TEMAS = 2
RANGE_ONCEKI_HAREKET_KAT = 1.0      # Range'den önceki hareket >= range yüksekliği x bu kat (DD: "büyük göreceli hareketten sonra")
RANGE_ONCEKI_MUM = 30               # Önceki hareket için range başlangıcından geriye bakılan mum
FITIL_DAHIL = False                 # Range ve PO3 kutuları gövdeden çizilir
MANIPULASYON_MAX_MUM = 10

# --- SFP ---------------------------------------------------------------------
SFP_GECERLILIK_MUM = 5
SFP_MAX_DERINLIK_ATR = 1.5
SFP_SWING_YASI_MIN_MUM = 5
SFP_GIRIS_MODU = "ikisi"            # SFP_AGRESIF / SFP_KIRILIM / ikisi

# --- MITIGATION --------------------------------------------------------------
MITIGATION_MIN_FARK_ATR = 0.2
MITIGATION_RETEST_TOLERANS_ATR = 0.3
SFP_MITIGATION_MAX_MUM = 30

# --- POWER OF 3 --------------------------------------------------------------
PO3_AKTIF = True
PO3_ONCEKI_TREND_MIN_ATR = 3.0

# --- QUASIMODO ---------------------------------------------------------------
QM_OMUZ_TOLERANS_ATR = 0.3
QM_MIN_BAS_FARK_ATR = 0.3
QM_MAX_MUM = 60

# --- INDUCEMENT --------------------------------------------------------------
IND_MAX_MUM = 60
IND_SUPURME_BEKLE = True
IND_GAP_ONCELIK = "koken"           # koken / ilk

# --- REVERSAL FRACTAL --------------------------------------------------------
RF_RENK_KURALI = True
RF_BOLGE_MODU = "govde"             # govde / tam
RF_MAX_MUM = 40

# --- FİBONACCİ ---------------------------------------------------------------
FIB_OTE_SEVIYELER = [0.618, 0.705, 0.786]
FIB_UZATMA_SEVIYELER = [1.0, 1.618]
FIB_BACAK_MIN_ATR = 2.0
FIB_CAKISMA_TOLERANS_ATR = 0.3

# --- İSTATİSTİK --------------------------------------------------------------
ISTATISTIK_AKTIF = True
ISTATISTIK_HEDEF_R = 2.0
ISTATISTIK_MAX_MUM = 60             # Dönüş/başarı için bakılan en fazla mum
OTOMATIK_MOD_SECIMI = False
OTOMATIK_MIN_ORNEK = 30
OTOMATIK_MIN_BASARI = 0.40

# --- ÖNBELLEK ----------------------------------------------------------------
CACHE_AKTIF = True                  # Aynı mum verisini kısa sürede tekrar çekmez

# =============================================================================
#                          SABİTLER / DOSYA YOLLARI
# =============================================================================

FELSEFE = ("%100 çalışan hiçbir şey yoktur. Price action özneldir. Tek bir konsepte "
           "bağlı kalma; en fazla konfirmasyonun olduğu işlemi ara. Market yapısı "
           "bütün konseptlerden önce gelir.")

DILIM_DAKIKA = {"15min": 15, "1h": 60, "2h": 120, "4h": 240, "12h": 720,
                "1day": 1440, "2day": 2880}

TEMEL_DIZIN = os.path.dirname(os.path.abspath(__file__))
YOLLAR = {}


def yollari_ayarla(dizin):
    """Tüm çıktı dosyalarının yollarını verilen dizine göre ayarlar."""
    YOLLAR["dizin"] = dizin
    YOLLAR["sinyaller"] = os.path.join(dizin, "sinyaller.csv")
    YOLLAR["kurulumlar"] = os.path.join(dizin, "kurulumlar.json")
    YOLLAR["sayac"] = os.path.join(dizin, "gunluk_sayac.json")
    YOLLAR["istatistik"] = os.path.join(dizin, "istatistik.csv")
    YOLLAR["raporlar"] = os.path.join(dizin, "raporlar")
    YOLLAR["cache"] = os.path.join(dizin, "cache")
    YOLLAR["kripto_listesi"] = os.path.join(dizin, "kripto_listesi.json")
    YOLLAR["plan_disi"] = os.path.join(dizin, "plan_disi_semboller.json")


yollari_ayarla(TEMEL_DIZIN)

SINYAL_KOLONLARI = ["tarih_saat_utc", "sembol", "poi_zaman_dilimi", "onay_zaman_dilimi",
                    "kurulum_tipi", "yon", "giris_alt", "giris_ust", "giris_oneri", "stop",
                    "tp1", "tp2", "tp3", "tp_etiketleri", "rr1", "rr2", "rr3", "ham_puan",
                    "skor", "temas_no", "po3_asama", "ote_seviye", "ob_zaman_dilimleri",
                    "konseptler", "notlar"]

ISTATISTIK_KOLONLARI = ["tarih", "sembol", "zaman_dilimi", "konsept", "kategori_mod",
                        "donus_orani", "basari_orani", "ornek_sayisi"]

# Tarama boyunca biriken uyarılar (rapora yazılır)
UYARILAR = []


def uyari(metin):
    """Rapora yazılacak genel uyarı ekler ve ekrana basar."""
    UYARILAR.append(metin)
    print("  ! " + metin)


# =============================================================================
#                              YARDIMCI FONKSİYONLAR
# =============================================================================

def simdi_utc():
    """Şu anki UTC zamanı (saat dilimi bilgisi olmadan)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def zaman_coz(metin):
    """Twelve Data tarih metnini datetime'a çevirir."""
    for bicim in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(metin, bicim)
        except ValueError:
            continue
    raise ValueError("Tarih çözülemedi: %s" % metin)


def zaman_yaz(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def govde(m):
    return abs(m["kapanis"] - m["acilis"])


def govde_ust(m):
    return max(m["acilis"], m["kapanis"])


def govde_alt(m):
    return min(m["acilis"], m["kapanis"])


def yesil(m):
    return m["kapanis"] > m["acilis"]


def kirmizi(m):
    return m["kapanis"] < m["acilis"]


def yuvarla(x, ref=None):
    """Fiyatı okunur basamakla yuvarlar (JPY / metal / kripto farkı için)."""
    if x is None:
        return None
    r = abs(ref if ref is not None else x)
    if r >= 1000:
        return round(x, 1)
    if r >= 100:
        return round(x, 2)
    if r >= 10:
        return round(x, 3)
    return round(x, 5)


def json_oku(yol, varsayilan):
    """JSON okur; dosya yoksa veya bozuksa varsayılanı döner (bot durmaz)."""
    if not os.path.exists(yol):
        return varsayilan
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        uyari("%s okunamadı (bozuk olabilir); boş yapıyla devam edildi." % os.path.basename(yol))
        return varsayilan


def json_yaz(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)


def forex_hafta_sonu_mu(dt):
    """Forex/metal piyasası bu anda kapalı mı? (Cuma FOREX_KAPANIS_SAAT - Pazar FOREX_ACILIS_SAAT, UTC)"""
    g = dt.weekday()
    return g == 5 or (g == 4 and dt.hour >= FOREX_KAPANIS_SAAT) or (g == 6 and dt.hour < FOREX_ACILIS_SAAT)


def hafta_sonu_mumlarini_ayikla(mumlar, dilim):
    """Tamamı hafta sonu kapanışına düşen forex/metal mumlarını çıkarır
    (hafta sonu kotasyonları likit değildir; sahte SFP/swing üretir)."""
    dk = DILIM_DAKIKA.get(dilim, 60)
    sonuc = []
    for m in mumlar:
        if dk >= 1440:
            if m["dt"].weekday() == 5:
                continue
        elif forex_hafta_sonu_mu(m["dt"]) and forex_hafta_sonu_mu(m["dt"] + datetime.timedelta(minutes=dk - 1)):
            continue
        sonuc.append(m)
    return sonuc


def kripto_mu(sembol):
    """Forex ve metal listesinde olmayan her sembol kripto kabul edilir (7/24 piyasa)."""
    return sembol not in FOREX and sembol not in METALLER


# --- Hacme göre kripto listesi (Twelve Data kredisi harcamaz) -----------------

HACIM_KAYNAKLARI = ["https://data-api.binance.vision/api/v3/ticker/24hr",
                    "https://api.binance.com/api/v3/ticker/24hr"]
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
TD_KRIPTO_URL = "https://api.twelvedata.com/cryptocurrencies"


def _dis_json(url, params=None):
    """Harici (Twelve Data sayacına girmeyen) JSON isteği; hata -> None."""
    if requests is None:
        return None
    try:
        r = requests.get(url, params=params, timeout=ISTEK_ZAMAN_ASIMI_SN)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _haric_mi(baz):
    b = baz.upper()
    if b in KRIPTO_HARIC:
        return True
    # Kaldıraçlı tokenlar (BTCUP, ETHDOWN, BULL/BEAR)
    return any(b.endswith(s) and len(b) > len(s) + 1 for s in ("UP", "DOWN", "BULL", "BEAR"))


def binance_hacim_sirasi():
    """Binance USDT spot çiftleri, 24s USD hacmine göre azalan: [(baz, hacim)]."""
    for url in HACIM_KAYNAKLARI:
        veri = _dis_json(url)
        if not isinstance(veri, list):
            continue
        sonuc = []
        for x in veri:
            try:
                s = x["symbol"]
                if not s.endswith("USDT"):
                    continue
                baz = s[:-4]
                fiyat = float(x["lastPrice"])
                hacim = float(x["quoteVolume"])
            except (KeyError, ValueError, TypeError):
                continue
            if not baz or _haric_mi(baz) or fiyat <= 0:
                continue
            # Stablecoin sezgisi: fiyat ~1$ ve gün içi oynaklık çok düşük
            try:
                if abs(fiyat - 1) < 0.02 and (float(x["highPrice"]) - float(x["lowPrice"])) / fiyat < 0.01:
                    continue
            except (KeyError, ValueError, TypeError):
                pass
            sonuc.append((baz, hacim))
        if sonuc:
            sonuc.sort(key=lambda t: -t[1])
            return sonuc, "Binance"
    return None, None


def coingecko_hacim_sirasi():
    veri = _dis_json(COINGECKO_URL, {"vs_currency": "usd", "order": "volume_desc", "per_page": 150, "page": 1})
    if not isinstance(veri, list):
        return None, None
    sonuc = []
    for x in veri:
        try:
            baz = str(x["symbol"]).upper()
            hacim = float(x.get("total_volume") or 0)
            fiyat = float(x.get("current_price") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if _haric_mi(baz) or abs(fiyat - 1) < 0.02:
            continue
        sonuc.append((baz, hacim))
    return (sonuc, "CoinGecko") if sonuc else (None, None)


def twelvedata_kripto_seti():
    """Twelve Data'da bulunan X/USD kripto sembolleri (referans verisi, kredi harcamaz)."""
    veri = _dis_json(TD_KRIPTO_URL)
    if not isinstance(veri, dict) or not isinstance(veri.get("data"), list):
        return None
    return set(x.get("symbol") for x in veri["data"] if str(x.get("symbol", "")).endswith("/USD"))


def kripto_listesi(simdi, cevrimdisi=False):
    """Taranacak kripto çiftleri: KRIPTO (zorunlu) + 24s hacme göre en yüksekler,
    toplam KRIPTO_SAYISI. Liste günde bir kez yenilenir ve kripto_listesi.json'da tutulur."""
    zorunlu = list(dict.fromkeys(KRIPTO))
    if not KRIPTO_OTOMATIK or cevrimdisi:
        return list(dict.fromkeys(zorunlu + KRIPTO_SABIT))[:max(KRIPTO_SAYISI, len(zorunlu))]
    kayit = json_oku(YOLLAR["kripto_listesi"], {})
    if isinstance(kayit, dict) and kayit.get("semboller") and kayit.get("sayi") == KRIPTO_SAYISI:
        try:
            yas = simdi - datetime.datetime.strptime(kayit["zaman"], "%Y-%m-%d %H:%M")
            if yas < datetime.timedelta(hours=KRIPTO_LISTE_YENILEME_SAAT):
                return list(dict.fromkeys(zorunlu + kayit["semboller"]))[:max(KRIPTO_SAYISI, len(zorunlu))]
        except (KeyError, ValueError):
            pass
    sira, kaynak = binance_hacim_sirasi()
    if not sira:
        sira, kaynak = coingecko_hacim_sirasi()
    if not sira:
        eski = kayit.get("semboller") if isinstance(kayit, dict) else None
        uyari("Hacim listesi alınamadı; %s kullanıldı." % ("önceki liste" if eski else "KRIPTO_SABIT"))
        return list(dict.fromkeys(zorunlu + (eski or KRIPTO_SABIT)))[:max(KRIPTO_SAYISI, len(zorunlu))]
    td = twelvedata_kripto_seti()
    secilen, hacimler = list(zorunlu), {}
    for baz, hacim in sira:
        s = baz + "/USD"
        if s in secilen:
            hacimler[s] = hacim
            continue
        if td is not None and s not in td:
            continue  # Twelve Data'da yok -> kredi boşa harcanmasın
        if len(secilen) >= KRIPTO_SAYISI:
            break
        secilen.append(s)
        hacimler[s] = hacim
    try:
        json_yaz(YOLLAR["kripto_listesi"], {"zaman": zaman_yaz(simdi), "kaynak": kaynak, "sayi": KRIPTO_SAYISI,
                                            "semboller": secilen,
                                            "hacim_musd": {s: round(h / 1e6, 1) for s, h in hacimler.items()}})
    except Exception:
        pass
    print("Kripto listesi (%s, 24s hacim): %s" % (kaynak, ", ".join(secilen)))
    return secilen


def ortust(a1, a2, b1, b2, tol=0.0):
    """[a1,a2] ile [b1,b2] aralıkları (tolerans dahil) çakışıyor mu?"""
    return a1 <= b2 + tol and b1 <= a2 + tol


# =============================================================================
#                                 VERİ KATMANI
# =============================================================================

class LimitAsildi(Exception):
    """Günlük istek limiti doldu."""
    pass


def gunluk_sayac_yukle():
    """gunluk_sayac.json; UTC gün değişince sıfırlanır."""
    bugun = simdi_utc().strftime("%Y-%m-%d")
    s = json_oku(YOLLAR["sayac"], {})
    if not isinstance(s, dict) or s.get("tarih") != bugun:
        s = {"tarih": bugun, "adet": 0}
    s.setdefault("adet", 0)
    return s


def gunluk_sayac_kaydet(sayac):
    try:
        json_yaz(YOLLAR["sayac"], sayac)
    except Exception as e:
        print("  Sayaç kaydedilemedi: %s" % e)


class IstekYoneticisi:
    """Dakika ve günlük limitleri koruyarak istek atar."""

    def __init__(self, sayac):
        self.sayac = sayac
        self.son_istek = 0.0
        self.bu_tarama = 0
        self.hatalar = []
        self.plan_disi = set()

    def kalan(self):
        return max(0, GUNLUK_LIMIT - self.sayac["adet"])

    def getir(self, params):
        if requests is None:
            raise RuntimeError("requests kütüphanesi yok. a-Shell'de: pip install requests")
        for deneme in range(TEKRAR_DENEME):
            if self.sayac["adet"] >= GUNLUK_LIMIT:
                raise LimitAsildi()
            bekle = ISTEK_ARASI_SN - (time.time() - self.son_istek)
            if bekle > 0:
                time.sleep(bekle)
            self.son_istek = time.time()
            self.sayac["adet"] += 1
            self.bu_tarama += 1
            gunluk_sayac_kaydet(self.sayac)
            try:
                yanit = requests.get(API_URL, params=params, timeout=ISTEK_ZAMAN_ASIMI_SN)
                veri = yanit.json()
            except Exception as e:
                print("  Bağlantı hatası (%s), deneme %d/%d" % (e, deneme + 1, TEKRAR_DENEME))
                time.sleep(5)
                continue
            if isinstance(veri, dict) and (veri.get("status") == "error" or "code" in veri):
                kod = veri.get("code")
                mesaj = str(veri.get("message", ""))
                if kod == 429 or "API credits" in mesaj:
                    print("  API limiti: %d sn bekleniyor..." % LIMIT_BEKLEME_SN)
                    time.sleep(LIMIT_BEKLEME_SN)
                    continue
                self.hatalar.append("%s %s: %s" % (params.get("symbol"), params.get("interval"), mesaj))
                if "plan" in mesaj.lower() or "upgrad" in mesaj.lower():
                    self.plan_disi.add(params.get("symbol"))
                print("  API hatası: %s" % mesaj)
                return None
            return veri
        self.hatalar.append("%s %s: tekrar denemeler başarısız" % (params.get("symbol"), params.get("interval")))
        return None


def _cache_yolu(sembol, aralik):
    return os.path.join(YOLLAR["cache"], "%s_%s.json" % (sembol.replace("/", ""), aralik))


def veri_cek(sembol, aralik, adet, yonetici):
    """Twelve Data /time_series; eski -> yeni sıralı mum listesi döner (hata: None)."""
    if CACHE_AKTIF:
        c = json_oku(_cache_yolu(sembol, aralik), None)
        if isinstance(c, dict) and c.get("mumlar"):
            gecen = (time.time() - c.get("cekilme", 0)) / 60.0
            if gecen < min(DILIM_DAKIKA.get(aralik, 60) / 4.0, 60) and c.get("adet") == adet:
                mumlar = c["mumlar"]
                for m in mumlar:
                    m["dt"] = zaman_coz(m["zaman"])
                return mumlar
    params = {"symbol": sembol, "interval": aralik, "outputsize": adet,
              "timezone": "UTC", "apikey": API_KEY, "order": "ASC"}
    veri = yonetici.getir(params)
    if not veri or "values" not in veri:
        return None
    mumlar = []
    for v in veri["values"]:
        try:
            mumlar.append({"zaman": v["datetime"], "acilis": float(v["open"]),
                           "yuksek": float(v["high"]), "dusuk": float(v["low"]),
                           "kapanis": float(v["close"])})
        except (KeyError, ValueError, TypeError):
            continue
    for m in mumlar:
        m["dt"] = zaman_coz(m["zaman"])
    mumlar.sort(key=lambda x: x["dt"])
    if CACHE_AKTIF and mumlar:
        try:
            kayit = [{k: m[k] for k in ("zaman", "acilis", "yuksek", "dusuk", "kapanis")} for m in mumlar]
            json_yaz(_cache_yolu(sembol, aralik), {"cekilme": time.time(), "adet": adet, "mumlar": kayit})
        except Exception:
            pass
    return mumlar


def mum_birlestir(mumlar, kat, kaynak_dakika):
    """Ardışık `kat` mumu tek muma çevirir; gruplar UTC gün sınırına hizalanır."""
    hedef_dk = kaynak_dakika * kat
    gruplar = []
    anahtar_onceki = None
    for m in mumlar:
        dt = m["dt"]
        if hedef_dk < 1440:
            dakika = dt.hour * 60 + dt.minute
            anahtar = (dt.date(), dakika // hedef_dk)
            bas = datetime.datetime(dt.year, dt.month, dt.day) + datetime.timedelta(minutes=(dakika // hedef_dk) * hedef_dk)
        else:
            gun_no = (dt.date() - datetime.date(1970, 1, 1)).days
            gun_kat = hedef_dk // 1440
            anahtar = gun_no // gun_kat
            bas = datetime.datetime(1970, 1, 1) + datetime.timedelta(days=(gun_no // gun_kat) * gun_kat)
        if anahtar != anahtar_onceki:
            gruplar.append({"zaman": zaman_yaz(bas), "dt": bas, "acilis": m["acilis"],
                            "yuksek": m["yuksek"], "dusuk": m["dusuk"], "kapanis": m["kapanis"]})
            anahtar_onceki = anahtar
        else:
            g = gruplar[-1]
            g["yuksek"] = max(g["yuksek"], m["yuksek"])
            g["dusuk"] = min(g["dusuk"], m["dusuk"])
            g["kapanis"] = m["kapanis"]
    return gruplar


def kapali_mumlar(mumlar, dilim, simdi):
    """Kapanmamış son mum(lar)ı çıkarır (kırılım kararı için kullanılmaz)."""
    dk = DILIM_DAKIKA.get(dilim, 60)
    sonuc = list(mumlar)
    while sonuc and sonuc[-1]["dt"] + datetime.timedelta(minutes=dk) > simdi:
        sonuc.pop()
    return sonuc


def ayna(mumlar):
    """Fiyat eksenini ters çevirir (-fiyat). Short kurulumlar long mantığıyla
    aranır, sonuçlar tekrar ters çevrilir. Böylece iki yönde aynı kural geçerli."""
    return [{"zaman": m["zaman"], "dt": m["dt"], "acilis": -m["acilis"], "yuksek": -m["dusuk"],
             "dusuk": -m["yuksek"], "kapanis": -m["kapanis"]} for m in mumlar]


# =============================================================================
#                                TEMEL HESAPLAR
# =============================================================================

def atr_listesi(mumlar, periyot=None):
    """Her mum için Wilder ATR değeri (ilk mumlarda basit ortalama)."""
    periyot = periyot or ATR_PERIYOT
    tr_list, sonuc = [], []
    for i, m in enumerate(mumlar):
        if i == 0:
            tr = m["yuksek"] - m["dusuk"]
        else:
            ok = mumlar[i - 1]["kapanis"]
            tr = max(m["yuksek"] - m["dusuk"], abs(m["yuksek"] - ok), abs(m["dusuk"] - ok))
        tr_list.append(tr)
        if i < periyot:
            a = sum(tr_list) / len(tr_list)
        else:
            a = (sonuc[-1] * (periyot - 1) + tr) / periyot
        sonuc.append(a if a > 0 else 1e-9)
    return sonuc


def atr(mumlar, periyot=None):
    """Son mumun ATR değeri."""
    liste = atr_listesi(mumlar, periyot)
    return liste[-1] if liste else 0.0


def swing_noktalari(mumlar, n):
    """Fraktal swing tespiti: solunda n mum daha düşük (sağında n mum daha düşük
    veya eşit) tepe = swing high; tersi = swing low. Son n mum onaysızdır."""
    sonuc = []
    N = len(mumlar)
    for i in range(n, N - n):
        h = mumlar[i]["yuksek"]
        l = mumlar[i]["dusuk"]
        if all(h > mumlar[j]["yuksek"] for j in range(i - n, i)) and \
           all(h >= mumlar[j]["yuksek"] for j in range(i + 1, i + n + 1)):
            sonuc.append({"i": i, "tip": "H", "fiyat": h})
        if all(l < mumlar[j]["dusuk"] for j in range(i - n, i)) and \
           all(l <= mumlar[j]["dusuk"] for j in range(i + 1, i + n + 1)):
            sonuc.append({"i": i, "tip": "L", "fiyat": l})
    sonuc.sort(key=lambda s: (s["i"], s["tip"]))
    return sonuc


def swing_etiketle(swingler):
    """HH/HL/LH/LL etiketleri."""
    son = {"H": None, "L": None}
    for s in swingler:
        onceki = son[s["tip"]]
        if s["tip"] == "H":
            s["etiket"] = "HH" if onceki is None or s["fiyat"] > onceki["fiyat"] else "LH"
        else:
            s["etiket"] = "LL" if onceki is None or s["fiyat"] < onceki["fiyat"] else "HL"
        son[s["tip"]] = s
    return swingler


def alterne(swingler):
    """Ardışık aynı tip swing'lerden en uç olanı tutarak H-L-H-L dizisi üretir."""
    dizi = []
    for s in swingler:
        if dizi and dizi[-1]["tip"] == s["tip"]:
            if (s["tip"] == "H" and s["fiyat"] >= dizi[-1]["fiyat"]) or \
               (s["tip"] == "L" and s["fiyat"] <= dizi[-1]["fiyat"]):
                dizi[-1] = s
        else:
            dizi.append(s)
    return dizi


def _min_dusuk(mumlar, bas, bit):
    """[bas, bit] aralığındaki en düşük dip (indeks, fiyat)."""
    j = min(range(bas, bit + 1), key=lambda k: (mumlar[k]["dusuk"], -k))
    return j, mumlar[j]["dusuk"]


def _max_yuksek(mumlar, bas, bit):
    j = max(range(bas, bit + 1), key=lambda k: (mumlar[k]["yuksek"], k))
    return j, mumlar[j]["yuksek"]


# =============================================================================
#                      MARKET YAPISI MODÜLÜ (ÇEKİRDEK)
# =============================================================================
# Önem sırası: MSB (Breaker) > BOS > CHoCH. Kırılım = kapanış (fitil kırılım değildir).

def yapi_analiz(mumlar, atrs, adaylar, n):
    """Ana yapı: BOS / MSB / korunan seviye. `adaylar` = ana swing adayları (fraktal n)."""
    N = len(mumlar)
    sira = sorted(adaylar, key=lambda s: s["i"])
    ptr = 0
    onayli = []                 # onaylanmış swing'ler (i + n <= mevcut mum)
    trend = None
    korunan = None
    hedef_h = hedef_l = None
    ref_h = ref_l = -1          # bu indeksten sonraki swing'ler hedef adayı
    olaylar = []
    trend_dizi = [None] * N
    kapanislar = [m["kapanis"] for m in mumlar]

    ilk_kirilim = {}

    def kirilmamis(s, i):
        """Swing, i'ye kadar kapanışla aşılmamış mı? (ilk kırılım indeksi önbellekli)"""
        anahtar = (s["i"], s["tip"])
        if anahtar not in ilk_kirilim:
            k = s["i"] + 1
            if s["tip"] == "H":
                while k < N and kapanislar[k] <= s["fiyat"]:
                    k += 1
            else:
                while k < N and kapanislar[k] >= s["fiyat"]:
                    k += 1
            ilk_kirilim[anahtar] = k
        return ilk_kirilim[anahtar] > i

    def hedef_guncelle(i):
        nonlocal hedef_h, hedef_l
        if trend in (None, "bull"):
            adaylar_h = [s for s in onayli if s["tip"] == "H" and s["i"] > ref_h and kirilmamis(s, i)]
            if trend is None:
                hedef_h = adaylar_h[-1] if adaylar_h else None
            else:
                hedef_h = max(adaylar_h, key=lambda s: s["fiyat"]) if adaylar_h else None
        if trend in (None, "bear"):
            adaylar_l = [s for s in onayli if s["tip"] == "L" and s["i"] > ref_l and kirilmamis(s, i)]
            if trend is None:
                hedef_l = adaylar_l[-1] if adaylar_l else None
            else:
                hedef_l = min(adaylar_l, key=lambda s: s["fiyat"]) if adaylar_l else None

    def yapi_tipi_bul(ekstrem_i, ekstrem_fiyat, i, tip):
        """Kırılım öncesi son swing yeni uç yapamadıysa MITIGATION, yaptıysa BREAKER."""
        a = atrs[i]
        sonrakiler = [s for s in onayli if s["tip"] == tip and ekstrem_i < s["i"] < i]
        if sonrakiler:
            s = sonrakiler[-1]
            fark = (ekstrem_fiyat - s["fiyat"]) if tip == "H" else (s["fiyat"] - ekstrem_fiyat)
            if fark >= MITIGATION_MIN_FARK_ATR * a:
                return "MITIGATION"
        return "BREAKER"

    for i in range(N):
        yeni = False
        while ptr < len(sira) and sira[ptr]["i"] + n <= i:
            onayli.append(sira[ptr])
            ptr += 1
            yeni = True
        if yeni:
            hedef_guncelle(i)
        c = kapanislar[i]
        if trend is None:
            if hedef_h is not None and c > hedef_h["fiyat"]:
                j, p = _min_dusuk(mumlar, hedef_h["i"], i)
                korunan = {"i": j, "fiyat": p, "tip": "L"}
                olaylar.append({"tip": "BOS", "yon": "bull", "i": i, "seviye": hedef_h["fiyat"],
                                "kirilan_i": hedef_h["i"], "korunan": dict(korunan), "ilk": True})
                trend = "bull"
                ref_h = hedef_h["i"]
                hedef_h = None
                hedef_guncelle(i)
            elif hedef_l is not None and c < hedef_l["fiyat"]:
                j, p = _max_yuksek(mumlar, hedef_l["i"], i)
                korunan = {"i": j, "fiyat": p, "tip": "H"}
                olaylar.append({"tip": "BOS", "yon": "bear", "i": i, "seviye": hedef_l["fiyat"],
                                "kirilan_i": hedef_l["i"], "korunan": dict(korunan), "ilk": True})
                trend = "bear"
                ref_l = hedef_l["i"]
                hedef_l = None
                hedef_guncelle(i)
        elif trend == "bull":
            if korunan is not None and c < korunan["fiyat"]:
                # MSB: korunan dip kapanışla kırıldı -> market yapısı bear
                ej, ep = _max_yuksek(mumlar, korunan["i"], i)
                tip = yapi_tipi_bul(ej, ep, i, "H")
                olaylar.append({"tip": "MSB", "yon": "bear", "i": i, "seviye": korunan["fiyat"],
                                "kirilan_i": korunan["i"], "stop_ref": ep, "stop_ref_i": ej,
                                "yapi_tipi": tip})
                korunan = {"i": ej, "fiyat": ep, "tip": "H"}
                olaylar[-1]["korunan"] = dict(korunan)
                trend = "bear"
                ref_l = i - 1
                hedef_l = None
                hedef_guncelle(i)
            elif hedef_h is not None and c > hedef_h["fiyat"]:
                j, p = _min_dusuk(mumlar, hedef_h["i"], i)
                korunan = {"i": j, "fiyat": p, "tip": "L"}
                olaylar.append({"tip": "BOS", "yon": "bull", "i": i, "seviye": hedef_h["fiyat"],
                                "kirilan_i": hedef_h["i"], "korunan": dict(korunan)})
                ref_h = hedef_h["i"]
                hedef_h = None
                hedef_guncelle(i)
        else:  # bear
            if korunan is not None and c > korunan["fiyat"]:
                ej, ep = _min_dusuk(mumlar, korunan["i"], i)
                tip = yapi_tipi_bul(ej, ep, i, "L")
                olaylar.append({"tip": "MSB", "yon": "bull", "i": i, "seviye": korunan["fiyat"],
                                "kirilan_i": korunan["i"], "stop_ref": ep, "stop_ref_i": ej,
                                "yapi_tipi": tip})
                korunan = {"i": ej, "fiyat": ep, "tip": "L"}
                olaylar[-1]["korunan"] = dict(korunan)
                trend = "bull"
                ref_h = i - 1
                hedef_h = None
                hedef_guncelle(i)
            elif hedef_l is not None and c < hedef_l["fiyat"]:
                j, p = _max_yuksek(mumlar, hedef_l["i"], i)
                korunan = {"i": j, "fiyat": p, "tip": "H"}
                olaylar.append({"tip": "BOS", "yon": "bear", "i": i, "seviye": hedef_l["fiyat"],
                                "kirilan_i": hedef_l["i"], "korunan": dict(korunan)})
                ref_l = hedef_l["i"]
                hedef_l = None
                hedef_guncelle(i)
        trend_dizi[i] = trend

    # İşlem aralığı (dealing range): korunan seviye -> o tarafın ekstremi
    aralik = None
    if korunan is not None and N:
        if trend == "bull":
            _, ust = _max_yuksek(mumlar, korunan["i"], N - 1)
            aralik = (korunan["fiyat"], ust)
        elif trend == "bear":
            _, alt = _min_dusuk(mumlar, korunan["i"], N - 1)
            aralik = (alt, korunan["fiyat"])
    son_bos = next((o for o in reversed(olaylar) if o["tip"] == "BOS"), None)
    son_msb = next((o for o in reversed(olaylar) if o["tip"] == "MSB"), None)
    return {"trend": trend or "belirsiz", "olaylar": olaylar, "trend_dizi": trend_dizi,
            "korunan": korunan, "son_bos": son_bos, "son_msb": son_msb,
            "son_olay": olaylar[-1] if olaylar else None, "aralik": aralik,
            "hedef_h": hedef_h, "hedef_l": hedef_l}


def mikro_yapi(mumlar, atrs, ic_swingler, n_ic, trend_dizi):
    """İç (micro) yapı ve CHoCH tespiti.
    CHoCH = fiyata yeni uç yaptırmış olan iç swing'in kapanışla kırılması.
    Yeni uç yaptırmamış swing'in kırılması CHoCH değildir (yok sayılır)."""
    N = len(mumlar)
    dipler = [s for s in ic_swingler if s["tip"] == "L"]
    tepeler = [s for s in ic_swingler if s["tip"] == "H"]
    yon = None
    gecerli = None           # kırılırsa CHoCH olacak swing
    eks_i, eks_p = None, None
    olaylar = []
    mikro_dizi = [None] * N

    def onayli_swingler(liste, bas, bit, i):
        return [s for s in liste if bas < s["i"] < bit and s["i"] + n_ic <= i]

    for i in range(N):
        m = mumlar[i]
        c = m["kapanis"]
        if yon is None:
            # İlk yön: son onaylı iç tepe/dip kapanışla aşılınca belirlenir
            t = [s for s in tepeler if s["i"] + n_ic <= i]
            d = [s for s in dipler if s["i"] + n_ic <= i]
            if t and c > t[-1]["fiyat"]:
                yon = "bull"
                eks_i, eks_p = _max_yuksek(mumlar, t[-1]["i"], i)
                gecerli = d[-1] if d else None
            elif d and c < d[-1]["fiyat"]:
                yon = "bear"
                eks_i, eks_p = _min_dusuk(mumlar, d[-1]["i"], i)
                gecerli = t[-1] if t else None
            mikro_dizi[i] = yon
            continue
        if yon == "bull":
            if gecerli is not None and c < gecerli["fiyat"]:
                a = atrs[i]
                sonraki_tepeler = onayli_swingler(tepeler, eks_i, i, i)
                tip = "BREAKER"
                if sonraki_tepeler and eks_p - sonraki_tepeler[-1]["fiyat"] >= MITIGATION_MIN_FARK_ATR * a:
                    tip = "MITIGATION"
                olaylar.append({"tip": "CHOCH", "yon": "bear", "i": i, "seviye": gecerli["fiyat"],
                                "kaynak_i": gecerli["i"], "ekstrem": eks_p, "ekstrem_i": eks_i,
                                "ana_trend": trend_dizi[i], "yapi_tipi": tip})
                yon = "bear"
                gecerli = {"i": eks_i, "fiyat": eks_p, "tip": "H"}
                eks_i, eks_p = _min_dusuk(mumlar, gecerli["i"], i)
            elif m["yuksek"] > eks_p:
                aday = onayli_swingler(dipler, eks_i, i, i)
                if aday:
                    gecerli = min(aday, key=lambda s: s["fiyat"])
                eks_i, eks_p = i, m["yuksek"]
        else:
            if gecerli is not None and c > gecerli["fiyat"]:
                a = atrs[i]
                sonraki_dipler = onayli_swingler(dipler, eks_i, i, i)
                tip = "BREAKER"
                if sonraki_dipler and sonraki_dipler[-1]["fiyat"] - eks_p >= MITIGATION_MIN_FARK_ATR * a:
                    tip = "MITIGATION"
                olaylar.append({"tip": "CHOCH", "yon": "bull", "i": i, "seviye": gecerli["fiyat"],
                                "kaynak_i": gecerli["i"], "ekstrem": eks_p, "ekstrem_i": eks_i,
                                "ana_trend": trend_dizi[i], "yapi_tipi": tip})
                yon = "bull"
                gecerli = {"i": eks_i, "fiyat": eks_p, "tip": "L"}
                eks_i, eks_p = _max_yuksek(mumlar, gecerli["i"], i)
            elif m["dusuk"] < eks_p:
                aday = onayli_swingler(tepeler, eks_i, i, i)
                if aday:
                    gecerli = max(aday, key=lambda s: s["fiyat"])
                eks_i, eks_p = i, m["dusuk"]
        mikro_dizi[i] = yon
    return {"olaylar": olaylar, "yon": yon, "mikro_dizi": mikro_dizi, "gecerli": gecerli}


def ana_swing_filtre(adaylar, sd_bolgeler, yapi, atrs):
    """Ana swing: ANA_SWING_UZUNLUK fraktalı VE (bir S&D bölgesi içinde oluşmuş
    VEYA bir BOS/MSB üretmiş/yapı seviyesi olmuş). Son iki aday (henüz test
    edilmemiş olabilir) de korunur."""
    yapi_indeksleri = set()
    for o in yapi["olaylar"]:
        yapi_indeksleri.add(o.get("kirilan_i"))
        if o.get("korunan"):
            yapi_indeksleri.add(o["korunan"]["i"])
        if o.get("stop_ref_i") is not None:
            yapi_indeksleri.add(o["stop_ref_i"])
    sonuc = []
    son_h = [s for s in adaylar if s["tip"] == "H"][-2:]
    son_l = [s for s in adaylar if s["tip"] == "L"][-2:]
    for s in adaylar:
        tut = s["i"] in yapi_indeksleri or s in son_h or s in son_l
        if not tut:
            a = atrs[s["i"]]
            for z in sd_bolgeler:
                if z["bas_i"] - 2 <= s["i"] <= z["bit_i"] + 3 and z["alt"] - 0.2 * a <= s["fiyat"] <= z["ust"] + 0.2 * a:
                    tut = True
                    break
        if tut:
            sonuc.append(dict(s))
    return swing_etiketle(sonuc)


# =============================================================================
#                               LİKİDİTE MODÜLÜ
# =============================================================================
# Likidite hedeftir, giriş noktası değildir. Her swing high'ın üstü ve her swing
# low'un altı likiditedir. Her likiditenin alınacağına dair kural yoktur.

def likidite_havuzu_bul(swingler, mumlar, atrs):
    """Equal / Relative / Tekil likidite havuzlarını bulur ve durumlarını günceller."""
    havuzlar = []
    if not mumlar:
        return havuzlar
    for tip in ("H", "L"):
        liste = [s for s in swingler if s["tip"] == tip]
        kullanildi = set()
        # 1) Equal: aynı seviyeye tekrar tekrar temas (zaman sınırı yok)
        for k, s in enumerate(liste):
            if k in kullanildi:
                continue
            tol = LIK_EQUAL_TOLERANS_ATR * atrs[s["i"]]
            grup = [k] + [j for j in range(k + 1, len(liste))
                          if j not in kullanildi and abs(liste[j]["fiyat"] - s["fiyat"]) <= tol]
            if len(grup) >= LIK_MIN_TEMAS:
                kullanildi.update(grup)
                fiyatlar = [liste[j]["fiyat"] for j in grup]
                havuzlar.append({"tip": "equal", "yon": tip, "temas": len(grup),
                                 "seviye": max(fiyatlar) if tip == "H" else min(fiyatlar),
                                 "alt": min(fiyatlar), "ust": max(fiyatlar),
                                 "son_i": max(liste[j]["i"] for j in grup),
                                 "ilk_i": min(liste[j]["i"] for j in grup)})
        # 2) Relative: yakın fiyatlı ve yakın zamanlı swing'ler
        for k, s in enumerate(liste):
            if k in kullanildi:
                continue
            tol = LIK_RELATIVE_TOLERANS_ATR * atrs[s["i"]]
            grup = [k]
            for j in range(k + 1, len(liste)):
                if j in kullanildi:
                    continue
                if liste[j]["i"] - liste[grup[-1]]["i"] > LIK_RELATIVE_MAX_MUM:
                    break
                if abs(liste[j]["fiyat"] - s["fiyat"]) <= tol:
                    grup.append(j)
            if len(grup) >= LIK_MIN_TEMAS:
                kullanildi.update(grup)
                fiyatlar = [liste[j]["fiyat"] for j in grup]
                havuzlar.append({"tip": "relative", "yon": tip, "temas": len(grup),
                                 "seviye": max(fiyatlar) if tip == "H" else min(fiyatlar),
                                 "alt": min(fiyatlar), "ust": max(fiyatlar),
                                 "son_i": max(liste[j]["i"] for j in grup),
                                 "ilk_i": min(liste[j]["i"] for j in grup)})
        # 3) Tekil: gruba girmeyen ana swing'ler
        for k, s in enumerate(liste):
            if k not in kullanildi:
                havuzlar.append({"tip": "tekil", "yon": tip, "temas": 1, "seviye": s["fiyat"],
                                 "alt": s["fiyat"], "ust": s["fiyat"], "son_i": s["i"], "ilk_i": s["i"]})
    for h in havuzlar:
        likidite_durum_guncelle(h, mumlar)
    return havuzlar


def likidite_durum_guncelle(h, mumlar):
    """açık / süpürüldü (fitil öte, kapanış beri = SFP) / kırıldı (kapanış öte)."""
    h["durum"], h["durum_i"], h["supurme_i"] = "açık", None, None
    for i in range(h["son_i"] + 1, len(mumlar)):
        m = mumlar[i]
        if h["yon"] == "H":
            if m["kapanis"] > h["seviye"]:
                h["durum"], h["durum_i"] = "kırıldı", i
                return
            if m["yuksek"] > h["seviye"] and h["supurme_i"] is None:
                h["durum"], h["supurme_i"] = "süpürüldü", i
        else:
            if m["kapanis"] < h["seviye"]:
                h["durum"], h["durum_i"] = "kırıldı", i
                return
            if m["dusuk"] < h["seviye"] and h["supurme_i"] is None:
                h["durum"], h["supurme_i"] = "süpürüldü", i


def havuz_durum_at(h, t):
    """Havuzun t anındaki durumu."""
    if h["durum_i"] is not None and h["durum_i"] <= t:
        return "kırıldı"
    if h["supurme_i"] is not None and h["supurme_i"] <= t:
        return "süpürüldü"
    return "açık"


def havuz_guc(h):
    return {"relative": 3, "equal": 2, "tekil": 1}[h["tip"]] + (0.5 if h.get("htf") else 0)


# =============================================================================
#                       BÖLGE TAKİBİ (ortak yardımcı)
# =============================================================================

def bolge_takip(z, mumlar, atrs, bas):
    """Bölgeye temasları ve kırılımı kaydeder.
    z['yon'] == 'long' -> talep bölgesi (fiyat yukarıdan gelir); 'short' -> arz."""
    temaslar, derinlikler = [], []
    icerde = False
    z["kirilim_i"], z["kirilim_istekli"] = None, False
    yukseklik = max(z["ust"] - z["alt"], 1e-12)
    for i in range(bas, len(mumlar)):
        m = mumlar[i]
        a = atrs[i]
        tol = IMB_ON_TEPKI_ATR * a
        if z["yon"] == "long":
            if m["kapanis"] < z["alt"]:
                z["kirilim_i"] = i
                z["kirilim_istekli"] = govde(m) >= DISPLACEMENT_ATR * a
                break
            dokundu = m["dusuk"] <= z["ust"] + tol
            derinlik = (z["ust"] - m["dusuk"]) / yukseklik
            uzak = m["dusuk"] > z["ust"] + a
        else:
            if m["kapanis"] > z["ust"]:
                z["kirilim_i"] = i
                z["kirilim_istekli"] = govde(m) >= DISPLACEMENT_ATR * a
                break
            dokundu = m["yuksek"] >= z["alt"] - tol
            derinlik = (m["yuksek"] - z["alt"]) / yukseklik
            uzak = m["yuksek"] < z["alt"] - a
        if dokundu and not icerde:
            temaslar.append(i)
            derinlikler.append(derinlik)
            icerde = True
        elif dokundu and icerde:
            derinlikler[-1] = max(derinlikler[-1], derinlik)
        elif uzak:
            icerde = False
    z["temaslar"] = temaslar
    z["tepki_derinlik"] = [("ön" if d < 0 else "sınır" if d < 0.25 else "orta" if d < 0.75 else "derin")
                           for d in derinlikler]
    return z


def bolge_temas_sayisi(z, t):
    """t anından ÖNCEKİ temas sayısı."""
    return sum(1 for x in z.get("temaslar", []) if x < t)


def bolge_gecerli_mi(z, t):
    return z.get("kirilim_i") is None or z["kirilim_i"] > t


# =============================================================================
#                         SUPPLY & DEMAND (RBD/DBR/RBR/DBD)
# =============================================================================

def _ref(m):
    """Çizgi grafik modunda kapanış, değilse kapanış (hareket kapanışlarla ölçülür)."""
    return m["kapanis"]


def sd_bolgeleri(mumlar, atrs):
    """Dört tip S&D bölgesi. Dönüş: RBD (supply), DBR (demand). Devam: DBD, RBR."""
    N = len(mumlar)
    bolgeler = []
    if N < 10:
        return bolgeler
    kucuk = [govde(mumlar[i]) <= SD_BAZ_GOVDE_ATR * atrs[i] for i in range(N)]

    def hareket_once(s):
        b = max(0, s - 4)
        if SD_CIZGI_GRAFIK:
            return _ref(mumlar[s - 1]) - _ref(mumlar[b])
        return mumlar[s - 1]["kapanis"] - mumlar[b]["acilis"]

    def hareket_sonra(e):
        degerler = [_ref(mumlar[e + k]) - _ref(mumlar[e]) for k in (1, 2, 3) if e + k < N]
        if not degerler:
            return 0.0, 0.0, None, None
        yuk = max(degerler)
        dus = min(degerler)
        k_yuk = next(k for k in (1, 2, 3) if e + k < N and _ref(mumlar[e + k]) - _ref(mumlar[e]) == yuk)
        k_dus = next(k for k in (1, 2, 3) if e + k < N and _ref(mumlar[e + k]) - _ref(mumlar[e]) == dus)
        return yuk, dus, e + k_yuk, e + k_dus

    # --- Dönüş tipi: küçük gövdeli base (1-8 mum) ---
    i = 4
    while i < N - 1:
        if not kucuk[i]:
            i += 1
            continue
        s = e = i
        while e + 1 < N and kucuk[e + 1] and e - s + 1 < SD_BAZ_MAX_MUM:
            e += 1
        L = e - s + 1
        a = atrs[s]
        if SD_BAZ_MIN_MUM <= L <= SD_BAZ_MAX_MUM and e + 1 < N:
            once = hareket_once(s)
            yuk, dus, i_yuk, i_dus = hareket_sonra(e)
            bas_uc = max(s - 1, 0)
            son_uc = min(e + 1, N - 1)
            if once >= SD_HAREKET_ATR * a and dus <= -SD_HAREKET_ATR * a:
                alt = min(govde_alt(mumlar[k]) for k in range(s, e + 1))
                ust = max(mumlar[k]["yuksek"] for k in range(bas_uc, son_uc + 1))
                bolgeler.append({"tur": "SD", "tip": "RBD", "yon": "short", "alt": alt, "ust": ust,
                                 "giris": alt, "stop_ref": ust, "bas_i": s, "bit_i": e,
                                 "olusum_i": i_dus, "guc": abs(dus) / a, "ic_sfp": False})
            elif once <= -SD_HAREKET_ATR * a and yuk >= SD_HAREKET_ATR * a:
                ust = max(govde_ust(mumlar[k]) for k in range(s, e + 1))
                alt = min(mumlar[k]["dusuk"] for k in range(bas_uc, son_uc + 1))
                bolgeler.append({"tur": "SD", "tip": "DBR", "yon": "long", "alt": alt, "ust": ust,
                                 "giris": ust, "stop_ref": alt, "bas_i": s, "bit_i": e,
                                 "olusum_i": i_yuk, "guc": yuk / a, "ic_sfp": False})
        i = e + 1

    # --- Devam tipi: çok swing'li mini range (4-40 mum) ---
    s = 4
    while s < N - 2:
        a = atrs[s]
        once = hareket_once(s)
        if abs(once) < SD_HAREKET_ATR * a:
            s += 1
            continue
        yon = 1 if once > 0 else -1
        bulundu = None
        g_ust, g_alt = govde_ust(mumlar[s]), govde_alt(mumlar[s])
        for e in range(s, min(N - 2, s + SD_DEVAM_BAZ_MAX_MUM)):
            g_ust = max(g_ust, govde_ust(mumlar[e]))
            g_alt = min(g_alt, govde_alt(mumlar[e]))
            if g_ust - g_alt > SD_DEVAM_BAZ_MAX_YUKSEKLIK_ATR * a:
                break
            L = e - s + 1
            if L < SD_DEVAM_BAZ_MIN_MUM:
                continue
            sonraki = mumlar[e + 1]
            yuk, dus, i_yuk, i_dus = hareket_sonra(e)
            if yon > 0 and sonraki["kapanis"] > g_ust and yuk >= SD_HAREKET_ATR * a:
                bulundu = (e, i_yuk)
                break
            if yon < 0 and sonraki["kapanis"] < g_alt and dus <= -SD_HAREKET_ATR * a:
                bulundu = (e, i_dus)
                break
        if not bulundu:
            s += 1
            continue
        e, olusum = bulundu
        yuksekler = sorted(((mumlar[k]["yuksek"], k) for k in range(s, e + 1)), reverse=True)
        dusukler = sorted((mumlar[k]["dusuk"], k) for k in range(s, e + 1))
        esik = SD_DEVAM_AYKIRI_FITIL_ATR * a
        ust, alt = yuksekler[0][0], dusukler[0][0]
        aykiri_ust = aykiri_alt = None
        if len(yuksekler) > 1 and yuksekler[0][0] - yuksekler[1][0] > esik:
            ust, aykiri_ust = yuksekler[1][0], yuksekler[0]
        if len(dusukler) > 1 and dusukler[1][0] - dusukler[0][0] > esik:
            alt, aykiri_alt = dusukler[1][0], dusukler[0]
        if yon > 0:
            ic_sfp = aykiri_alt is not None
            bolgeler.append({"tur": "SD", "tip": "RBR", "yon": "long", "alt": alt, "ust": ust,
                             "giris": ust, "stop_ref": aykiri_alt[0] if ic_sfp else alt,
                             "bas_i": s, "bit_i": e, "olusum_i": olusum, "guc": 0, "ic_sfp": ic_sfp})
        else:
            ic_sfp = aykiri_ust is not None
            bolgeler.append({"tur": "SD", "tip": "DBD", "yon": "short", "alt": alt, "ust": ust,
                             "giris": alt, "stop_ref": aykiri_ust[0] if ic_sfp else ust,
                             "bas_i": s, "bit_i": e, "olusum_i": olusum, "guc": 0, "ic_sfp": ic_sfp})
        s = e + 1

    # Aynı yönde üst üste binen bölgelerden güçlü olanı tut
    bolgeler.sort(key=lambda z: z["bas_i"])
    temiz = []
    for z in bolgeler:
        cakisan = next((t for t in temiz if t["yon"] == z["yon"] and ortust(t["alt"], t["ust"], z["alt"], z["ust"])
                        and abs(t["bas_i"] - z["bas_i"]) <= SD_BAZ_MAX_MUM), None)
        if cakisan is None:
            temiz.append(z)
    for z in temiz:
        bolge_takip(z, mumlar, atrs, z["olusum_i"] + 1)
    return temiz


# =============================================================================
#                                ORDER BLOCK
# =============================================================================

def ob_bolge(mumlar, g, k, mod):
    """OB bölgesini seçilen moda göre hesaplar: (alt, ust)."""
    if mod == "son_mum_govde":
        return govde_alt(mumlar[k]), govde_ust(mumlar[k])
    if mod == "grup_govde":
        return min(govde_alt(mumlar[j]) for j in range(g, k + 1)), max(govde_ust(mumlar[j]) for j in range(g, k + 1))
    if mod == "grup_fitil":
        return min(mumlar[j]["dusuk"] for j in range(g, k + 1)), max(mumlar[j]["yuksek"] for j in range(g, k + 1))
    return mumlar[k]["dusuk"], mumlar[k]["yuksek"]  # son_mum_fitil


def ob_bul(mumlar, atrs, olaylar, ic_swingler, havuzlar, mod=None):
    """Order Block: (1) DD mum kuralı, (2) önceki hareketi kapatma, (3) yapı değişimi."""
    mod = mod or OB_BOLGE_MODU
    N = len(mumlar)
    adaylar = {}
    for k in range(1, N - 1):
        a = atrs[k]
        for yon in ("long", "short"):
            m0, m1 = mumlar[k], mumlar[k + 1]
            if yon == "long":
                if not (kirmizi(m0) and yesil(m1)):
                    continue
                ref = m1["kapanis"] if OB_YUTMA_REFERANS == "kapanis" else m1["yuksek"]
                if ref < m0["yuksek"]:
                    continue
                renk = kirmizi
            else:
                if not (yesil(m0) and kirmizi(m1)):
                    continue
                ref = m1["kapanis"] if OB_YUTMA_REFERANS == "kapanis" else m1["dusuk"]
                if ref > m0["dusuk"]:
                    continue
                renk = yesil
            g = k
            while g - 1 >= 0 and renk(mumlar[g - 1]) and k - g < 5:
                g -= 1
            # (2) önceki bacağın ucu: OB'den önceki son ters swing
            tip = "H" if yon == "long" else "L"
            onceki = [s for s in ic_swingler if s["tip"] == tip and s["i"] < g]
            if not onceki:
                continue
            uc = onceki[-1]
            son = min(N - 1, k + OB_KIRILIM_MAX_MUM)
            kapatti = None
            for j in range(k + 1, son + 1):
                if (yon == "long" and mumlar[j]["kapanis"] > uc["fiyat"]) or \
                   (yon == "short" and mumlar[j]["kapanis"] < uc["fiyat"]):
                    kapatti = j
                    break
            if kapatti is None:
                continue
            # (3) yapı değişimi: işlem yönünde BOS / CHoCH / MSB
            olay_yon = "bull" if yon == "long" else "bear"
            olay = next((o for o in olaylar if o["yon"] == olay_yon and k < o["i"] <= son), None)
            if olay is None:
                continue
            displacement = any(govde(mumlar[j]) >= DISPLACEMENT_ATR * atrs[j] for j in range(k + 1, olay["i"] + 1))
            alt, ust = ob_bolge(mumlar, g, k, mod)
            anahtar = (yon, olay["i"])
            # Aynı kırılım için bacağın başlangıcındaki (en uçtaki) OB tutulur
            uc_fiyat = min(mumlar[j]["dusuk"] for j in range(g, k + 1)) if yon == "long" else \
                max(mumlar[j]["yuksek"] for j in range(g, k + 1))
            onceki_aday = adaylar.get(anahtar)
            if onceki_aday is not None:
                if (yon == "long" and uc_fiyat > onceki_aday["_uc"]) or (yon == "short" and uc_fiyat < onceki_aday["_uc"]):
                    continue
            adaylar[anahtar] = {"tur": "OB", "yon": yon, "g": g, "k": k, "alt": alt, "ust": ust,
                                "giris": ust + OB_GIRIS_TIK_ATR * a if yon == "long" else alt - OB_GIRIS_TIK_ATR * a,
                                "stop_ref": alt if yon == "long" else ust, "olay_tip": olay["tip"],
                                "olay_i": olay["i"], "displacement": displacement, "olusum_i": olay["i"],
                                "bas_i": g, "bit_i": k, "_uc": uc_fiyat}
    sonuc = sorted(adaylar.values(), key=lambda z: z["k"])
    for z in sonuc:
        a = atrs[z["k"]]
        # Swing noktasında mı?
        tip = "L" if z["yon"] == "long" else "H"
        z["swingde"] = any(s["tip"] == tip and z["g"] - 2 <= s["i"] <= z["k"] + 2 and
                           abs(s["fiyat"] - z["_uc"]) <= OB_SWING_MESAFE_ATR * a for s in ic_swingler)
        # Likidite tuzağı: hemen ötesinde açık havuz
        z["likidite_riski"] = None
        for h in havuzlar:
            if z["yon"] == "long" and h["yon"] == "L" and z["alt"] - OB_LIKIDITE_MESAFE_ATR * a <= h["seviye"] < z["alt"]:
                z["likidite_riski"] = h
            if z["yon"] == "short" and h["yon"] == "H" and z["ust"] < h["seviye"] <= z["ust"] + OB_LIKIDITE_MESAFE_ATR * a:
                z["likidite_riski"] = h
        bolge_takip(z, mumlar, atrs, z["k"] + 2)
    return sonuc


# =============================================================================
#                              IMBALANCE (GAP)
# =============================================================================

def imbalance_bul(mumlar, atrs):
    """DD yöntemi; her zaman fitille hesaplanır. Bearish: üst = önceki mumun
    dibi (giriş çizgisi), alt = sonraki mumun tepesi. Bullish tersi."""
    N = len(mumlar)
    sonuc = []
    for i in range(1, N):
        m = mumlar[i]
        a = atrs[i]
        g = govde(m)
        onceki_govdeler = [govde(mumlar[j]) for j in range(max(0, i - 10), i)]
        ort = sum(onceki_govdeler) / len(onceki_govdeler) if onceki_govdeler else g
        if g < IMB_BUYUK_MUM_ATR * a or g < IMB_BUYUK_MUM_ORAN * ort:
            continue
        fitil = (m["yuksek"] - m["dusuk"]) - g
        zayif = fitil > IMB_FITIL_MAX_ORAN * g
        if kirmizi(m):
            ust = mumlar[i - 1]["dusuk"]
            alt = mumlar[i + 1]["yuksek"] if i + 1 < N else m["kapanis"]
            yon, giris = "short", ust
        elif yesil(m):
            alt = mumlar[i - 1]["yuksek"]
            ust = mumlar[i + 1]["dusuk"] if i + 1 < N else m["kapanis"]
            yon, giris = "long", alt
        else:
            continue
        if ust - alt < IMB_MIN_ATR * a:
            continue  # önceki iğne kapatmış veya boşluk çok küçük
        z = {"tur": "IMB", "yon": yon, "i": i, "alt": alt, "ust": ust, "giris": giris,
             "zayif": zayif, "olusum_i": i + 1 if i + 1 < N else i, "bas_i": i - 1, "bit_i": min(i + 1, N - 1)}
        imbalance_takip(z, mumlar, atrs)
        sonuc.append(z)
    return sonuc


def imbalance_takip(z, mumlar, atrs):
    """açık / ön tepki / dolduruldu (giriş çizgisine fitil) / onarıldı / kırıldı."""
    z["on_tepki_i"] = z["dolum_i"] = z["kirilim_i"] = None
    for j in range(z["i"] + 2, len(mumlar)):
        m = mumlar[j]
        tol = IMB_ON_TEPKI_ATR * atrs[j]
        if z["yon"] == "long":
            if m["kapanis"] < z["alt"]:
                z["kirilim_i"] = j
                break
            if z["on_tepki_i"] is None and m["dusuk"] <= z["ust"] + tol:
                z["on_tepki_i"] = j
            if z["dolum_i"] is None and m["dusuk"] <= z["giris"]:
                z["dolum_i"] = j
        else:
            if m["kapanis"] > z["ust"]:
                z["kirilim_i"] = j
                break
            if z["on_tepki_i"] is None and m["yuksek"] >= z["alt"] - tol:
                z["on_tepki_i"] = j
            if z["dolum_i"] is None and m["yuksek"] >= z["giris"]:
                z["dolum_i"] = j
    return z


def imbalance_durum_at(z, t):
    if z["kirilim_i"] is not None and z["kirilim_i"] <= t:
        return "kırıldı"
    if z["dolum_i"] is not None:
        if z["dolum_i"] < t:
            return "onarıldı"
        if z["dolum_i"] == t:
            return "dolduruldu"
    if z["on_tepki_i"] is not None and z["on_tepki_i"] <= t:
        return "ön tepki"
    return "açık"


def gap_bul(mumlar, atrs, dilim):
    """Mumlar arası açılış boşlukları (forex/metal hafta sonu, günlük GAP)."""
    sonuc = []
    for i in range(1, len(mumlar)):
        fark = mumlar[i]["acilis"] - mumlar[i - 1]["kapanis"]
        if abs(fark) < GAP_MIN_ATR * atrs[i]:
            continue
        alt, ust = sorted((mumlar[i]["acilis"], mumlar[i - 1]["kapanis"]))
        z = {"tur": "GAP", "dilim": dilim, "i": i, "alt": alt, "ust": ust,
             "yon": "long" if fark < 0 else "short", "hedef": mumlar[i - 1]["kapanis"], "dolum_i": None,
             "tahmini": False}
        gap_takip(z, mumlar)
        sonuc.append(z)
    return sonuc[-20:]


def gap_takip(z, mumlar):
    for j in range(z["i"], len(mumlar)):
        if mumlar[j]["dusuk"] <= z["hedef"] <= mumlar[j]["yuksek"]:
            z["dolum_i"] = j
            return


def hafta_sonu_gap_bul(sembol, mumlar_1h, atrs_1h):
    """Kripto: Cuma CME_KAPANIS_SAAT ve Pazar CME_ACILIS_SAAT (UTC) spot fiyatları
    arasındaki fark = spot veriden tahmini CME GAP. Forex/metal: hafta sonu boşluğu."""
    if not mumlar_1h:
        return []
    if not kripto_mu(sembol):
        return [g for g in gap_bul(mumlar_1h, atrs_1h, "1h")
                if (mumlar_1h[g["i"]]["dt"] - mumlar_1h[g["i"] - 1]["dt"]).total_seconds() > 24 * 3600]
    sonuc = []
    cuma = {}
    for i, m in enumerate(mumlar_1h):
        dt = m["dt"]
        # Cuma saat CME_KAPANIS_SAAT'te biten mum -> kapanışı
        if dt.weekday() == 4 and dt.hour == CME_KAPANIS_SAAT - 1:
            cuma = {"fiyat": m["kapanis"], "i": i}
        if dt.weekday() == 6 and dt.hour == CME_ACILIS_SAAT and cuma:
            fark = m["acilis"] - cuma["fiyat"]
            if abs(fark) >= GAP_MIN_ATR * atrs_1h[i]:
                alt, ust = sorted((m["acilis"], cuma["fiyat"]))
                z = {"tur": "GAP", "dilim": "1h", "i": i, "alt": alt, "ust": ust,
                     "yon": "long" if fark < 0 else "short", "hedef": cuma["fiyat"], "dolum_i": None,
                     "tahmini": True}
                gap_takip(z, mumlar_1h)
                sonuc.append(z)
            cuma = {}
    return sonuc


# =============================================================================
#                            BREAKER / MSB BÖLGESİ
# =============================================================================

def breaker_bul(mumlar, atrs, yapi, sd_bolgeler, mod=None):
    """Bearish: yeni tepe yapıldıktan sonra son HL'nin kapanışla kırılması (MSB).
    Kırılan HL mum(lar)ı = breaker bölgesi, alttan re-test -> short. Bullish tersi."""
    mod = mod or BREAKER_BOLGE_MODU
    N = len(mumlar)
    sonuc = []
    for o in yapi["olaylar"]:
        if o["tip"] != "MSB":
            continue
        k = o["kirilan_i"]
        m = mumlar[k]
        a = atrs[o["i"]]
        yon = "short" if o["yon"] == "bear" else "long"
        if mod == "cizgi":
            seviye = m["dusuk"] if yon == "short" else m["yuksek"]
            alt, ust = seviye - 0.1 * a, seviye + 0.1 * a
        elif mod == "son_fitil":
            alt, ust = m["dusuk"], m["yuksek"]
        else:
            alt, ust = govde_alt(m), govde_ust(m)
        sonuc.append({"tur": "BREAKER", "kaynak": "MSB", "yon": yon, "alt": alt, "ust": ust,
                      "giris": alt if yon == "short" else ust, "stop_ref": o["stop_ref"],
                      "msb_i": o["i"], "olusum_i": o["i"], "bas_i": k, "bit_i": k,
                      "yapi_tipi": o.get("yapi_tipi", "BREAKER")})
    for z in sd_bolgeler:
        if z.get("kirilim_i") is None:
            continue
        ki = z["kirilim_i"]
        yon = "long" if z["yon"] == "short" else "short"
        if yon == "long":
            _, stop_ref = _min_dusuk(mumlar, max(0, ki - 10), ki)
        else:
            _, stop_ref = _max_yuksek(mumlar, max(0, ki - 10), ki)
        sonuc.append({"tur": "BREAKER", "kaynak": "SD", "yon": yon, "alt": z["alt"], "ust": z["ust"],
                      "giris": z["ust"] if yon == "long" else z["alt"], "stop_ref": stop_ref,
                      "msb_i": ki, "olusum_i": ki, "bas_i": z["bas_i"], "bit_i": z["bit_i"],
                      "yapi_tipi": "BREAKER"})
    for z in sonuc:
        breaker_retest(z, mumlar, atrs)
    return sonuc


def breaker_retest(z, mumlar, atrs):
    """İlk re-test: tam (bölgeye değdi) / yakın (tolerans içinde döndü)."""
    z["retest_i"], z["retest_tip"], z["iptal_i"] = None, None, None
    for j in range(z["msb_i"] + 1, len(mumlar)):
        m = mumlar[j]
        tol = BREAKER_RETEST_TOLERANS_ATR * atrs[j]
        if z["yon"] == "short":
            if m["kapanis"] > z["stop_ref"] or m["kapanis"] > z["ust"] + tol:
                z["iptal_i"] = j
                return z
            if m["yuksek"] >= z["alt"] - tol:
                z["retest_i"] = j
                z["retest_tip"] = "tam" if m["yuksek"] >= z["alt"] else "yakın"
                return z
        else:
            if m["kapanis"] < z["stop_ref"] or m["kapanis"] < z["alt"] - tol:
                z["iptal_i"] = j
                return z
            if m["dusuk"] <= z["ust"] + tol:
                z["retest_i"] = j
                z["retest_tip"] = "tam" if m["dusuk"] <= z["ust"] else "yakın"
                return z
    return z


# =============================================================================
#                          SUPPORT / RESISTANCE FLIP
# =============================================================================

def sr_seviyeleri(mumlar, atrs, swingler):
    """Çok temaslı yatay seviyeler ve flip durumu. Tek temaslı seviye S/R değildir."""
    N = len(mumlar)
    if N == 0 or not swingler:
        return []
    a_son = atrs[-1]
    tol = SR_TOLERANS_ATR * a_son
    sirali = sorted(swingler, key=lambda s: s["fiyat"])
    kumeler, mevcut = [], [sirali[0]]
    for s in sirali[1:]:
        if s["fiyat"] - mevcut[0]["fiyat"] <= 2 * tol:
            mevcut.append(s)
        else:
            kumeler.append(mevcut)
            mevcut = [s]
    kumeler.append(mevcut)
    seviyeler = []
    for kume in kumeler:
        kume.sort(key=lambda s: s["i"])
        temaslar = []
        for s in kume:
            if not temaslar or s["i"] - temaslar[-1]["i"] >= SR_TEMAS_ARASI_MIN_MUM:
                temaslar.append(s)
        if len(temaslar) < SR_MIN_TEMAS:
            continue
        seviye = sum(s["fiyat"] for s in temaslar) / len(temaslar)
        alttan = sum(1 for s in temaslar if s["tip"] == "H")
        rol = "direnç" if alttan * 2 >= len(temaslar) else "destek"
        yayilma = (temaslar[-1]["i"] - temaslar[0]["i"]) / max(N, 1)
        seviyeler.append({"tur": "SR", "seviye": seviye, "alt": seviye - tol, "ust": seviye + tol,
                          "temas": len(temaslar), "rol": rol, "guc": len(temaslar) * max(yayilma, 0.01),
                          "son_temas_i": temaslar[-1]["i"], "ilk_temas_i": temaslar[0]["i"]})
    seviyeler.sort(key=lambda z: -z["guc"])
    seviyeler = seviyeler[:SR_MAX_SEVIYE]
    for z in seviyeler:
        sr_flip_kontrol(z, mumlar, atrs)
    return seviyeler


def sr_flip_kontrol(z, mumlar, atrs):
    """Geçerli seviye -> kapanışla kırılım -> karşı taraftan re-test -> uzaklaşma."""
    z["flip"], z["flip_i"], z["kirilim_i"], z["retest_i"], z["yon"] = None, None, None, None, None
    asama = 0
    for j in range(z["son_temas_i"] + 1, len(mumlar)):
        m = mumlar[j]
        a = atrs[j]
        if asama == 0:
            if z["rol"] == "direnç" and m["kapanis"] > z["ust"]:
                asama, z["kirilim_i"], z["yon"] = 1, j, "long"
            elif z["rol"] == "destek" and m["kapanis"] < z["alt"]:
                asama, z["kirilim_i"], z["yon"] = 1, j, "short"
        elif asama == 1:
            if z["yon"] == "long":
                if m["kapanis"] < z["alt"]:
                    z["flip"] = "kararsız"
                    return z
                if m["dusuk"] <= z["ust"]:
                    asama, z["retest_i"] = 2, j
            else:
                if m["kapanis"] > z["ust"]:
                    z["flip"] = "kararsız"
                    return z
                if m["yuksek"] >= z["alt"]:
                    asama, z["retest_i"] = 2, j
        elif asama == 2:
            if z["yon"] == "long":
                if m["kapanis"] < z["alt"]:
                    z["flip"] = "kararsız"
                    return z
                if m["kapanis"] > z["seviye"] + a:
                    z["flip"], z["flip_i"] = "teyitli", j
                    return z
            else:
                if m["kapanis"] > z["ust"]:
                    z["flip"] = "kararsız"
                    return z
                if m["kapanis"] < z["seviye"] - a:
                    z["flip"], z["flip_i"] = "teyitli", j
                    return z
    if asama >= 1 and z["flip"] is None:
        z["flip"] = "retest bekleniyor" if asama == 1 else "retest sürüyor"
    return z


# =============================================================================
#                         RANGE, EQ VE DEVİASYON
# =============================================================================

def _range_ust(m):
    return m["yuksek"] if FITIL_DAHIL else govde_ust(m)


def _range_alt(m):
    return m["dusuk"] if FITIL_DAHIL else govde_alt(m)


def range_izle(mumlar, atrs, rh, rl, bas, son_rh, son_rl):
    """Range'i bas indeksinden itibaren izler: deviasyonlar (kapanışla / fitille),
    MANIPULASYON_MAX_MUM içinde geri dönmeyen kapanış = kırılım, RH/RL temasları."""
    N = len(mumlar)
    rh_temas = rl_temas = 1
    devs, dis, kirilim = [], None, None
    for i in range(bas, N):
        m = mumlar[i]
        c = m["kapanis"]
        tol = 0.3 * atrs[i]
        if dis is not None:
            if rl <= c <= rh:
                dis["reentry_i"] = i
                dis["reentry_istekli"] = govde(m) >= DISPLACEMENT_ATR * atrs[i]
                devs.append(dis)
                dis = None
            elif i - dis["bas_i"] >= MANIPULASYON_MAX_MUM:
                kirilim = dis
                break
            else:
                if dis["yon"] == "yukari":
                    dis["uc"] = max(dis["uc"], m["yuksek"])
                else:
                    dis["uc"] = min(dis["uc"], m["dusuk"])
            continue
        if c > rh:
            dis = {"yon": "yukari", "bas_i": i, "uc": m["yuksek"], "fitil": False,
                   "istekli": govde(m) >= DISPLACEMENT_ATR * atrs[i]}
            continue
        if c < rl:
            dis = {"yon": "asagi", "bas_i": i, "uc": m["dusuk"], "fitil": False,
                   "istekli": govde(m) >= DISPLACEMENT_ATR * atrs[i]}
            continue
        if m["yuksek"] > rh + 0.1 * atrs[i]:
            devs.append({"yon": "yukari", "bas_i": i, "uc": m["yuksek"], "fitil": True,
                         "reentry_i": i, "reentry_istekli": False, "istekli": False})
        if m["dusuk"] < rl - 0.1 * atrs[i]:
            devs.append({"yon": "asagi", "bas_i": i, "uc": m["dusuk"], "fitil": True,
                         "reentry_i": i, "reentry_istekli": False, "istekli": False})
        if (_range_ust(m) >= rh - tol or m["yuksek"] > rh) and i - son_rh >= 3:
            rh_temas += 1
            son_rh = i
        if (_range_alt(m) <= rl + tol or m["dusuk"] < rl) and i - son_rl >= 3:
            rl_temas += 1
            son_rl = i
    return devs, dis, kirilim, rh_temas, rl_temas


def monday_araligi(mumlar_1d, simdi):
    """Bu haftanın tamamlanmış Pazartesi mumu: (başlangıç, high, low) veya None."""
    if not mumlar_1d:
        return None
    bugun = mumlar_1d[-1]["dt"].date()
    hafta_bas = bugun - datetime.timedelta(days=bugun.weekday())
    pzt = [m for m in mumlar_1d if m["dt"].date() == hafta_bas]
    bas = datetime.datetime.combine(hafta_bas, datetime.time())
    if not pzt or simdi < bas + datetime.timedelta(days=1):
        return None
    return bas, pzt[0]["yuksek"], pzt[0]["dusuk"]


def monday_range(an, pzt, ayna_mi):
    """Şartname 7.7 / DD not 2: Monday High / Low düşük dilimlerde range görevi görür.
    RH = Monday High, RL = Monday Low (ayna çerçevede ters), izleme Salı'dan başlar."""
    bas_dt, yuksek, dusuk = pzt
    rh, rl = (-dusuk, -yuksek) if ayna_mi else (yuksek, dusuk)
    if rh <= rl:
        return None
    m, atrs = an["m"], an["atrs"]
    bas_i = indeks_bul(an["dts"], bas_dt)
    izle = indeks_bul(an["dts"], bas_dt + datetime.timedelta(days=1))
    if bas_i >= len(m) or izle >= len(m):
        return None
    devs, dis, kirilim, rh_t, rl_t = range_izle(m, atrs, rh, rl, izle, izle - 1, izle - 1)
    durum = "aktif"
    if kirilim:
        durum = "kırıldı_yukarı" if kirilim["yon"] == "yukari" else "kırıldı_aşağı"
    elif dis is not None:
        durum = "deviasyonda"
        devs.append(dict(dis, reentry_i=None, reentry_istekli=False))
    r = {"tur": "MONDAY", "rh": rh, "rl": rl, "eq": (rh + rl) / 2.0, "bas_i": bas_i,
         "bit_i": kirilim["bas_i"] if kirilim else len(m) - 1, "durum": durum, "kirilim": kirilim,
         "devs": devs, "rh_temas": rh_t, "rl_temas": rl_t, "h_i": bas_i, "l_i": bas_i}
    r["devs_detay"] = deviasyon_tespit(r, m, atrs, an["mikro"]["olaylar"])
    return r


def range_tespit(mumlar, atrs, ana_swingler):
    """Ana swing çiftlerinden range (RH/RL/EQ) ve deviasyonları çıkarır.
    En yeni en başta olmak üzere en fazla 3 range döner (kırılmış olanlar dahil)."""
    N = len(mumlar)
    dizi = alterne(ana_swingler)
    sonuc = []
    dolu_bas = N
    for idx in range(len(dizi) - 1, 0, -1):
        a_s, b_s = dizi[idx - 1], dizi[idx]
        if max(a_s["i"], b_s["i"]) >= dolu_bas:
            continue
        h = a_s if a_s["tip"] == "H" else b_s
        l = b_s if h is a_s else a_s
        rh = max(_range_ust(mumlar[k]) for k in range(max(0, h["i"] - 1), min(N, h["i"] + 2)))
        rl = min(_range_alt(mumlar[k]) for k in range(max(0, l["i"] - 1), min(N, l["i"] + 2)))
        a = atrs[max(h["i"], l["i"])]
        if rh - rl < a:
            continue
        # DD not 3: range, büyük göreceli hareketten sonra oluşan yatay bölgedir
        b0 = max(0, min(h["i"], l["i"]) - RANGE_ONCEKI_MUM)
        onceki = mumlar[b0:min(h["i"], l["i"])]
        if not onceki:
            continue
        hareket = max(max(m["yuksek"] for m in onceki) - rh, rl - min(m["dusuk"] for m in onceki))
        if hareket < RANGE_ONCEKI_HAREKET_KAT * (rh - rl):
            continue
        bas = min(h["i"], l["i"])
        devs, dis, kirilim, rh_temas, rl_temas = range_izle(mumlar, atrs, rh, rl, max(h["i"], l["i"]) + 1, h["i"], l["i"])
        bit = kirilim["bas_i"] if kirilim else N - 1
        if bit - bas < RANGE_MIN_MUM or rh_temas < RANGE_MIN_TEMAS or rl_temas < RANGE_MIN_TEMAS:
            continue
        durum = "aktif"
        if kirilim:
            durum = "kırıldı_yukarı" if kirilim["yon"] == "yukari" else "kırıldı_aşağı"
        elif dis is not None:
            durum = "deviasyonda"
            devs.append(dict(dis, reentry_i=None, reentry_istekli=False))
        r = {"rh": rh, "rl": rl, "eq": (rh + rl) / 2.0, "bas_i": bas, "bit_i": bit, "durum": durum,
             "kirilim": kirilim, "devs": devs, "rh_temas": rh_temas, "rl_temas": rl_temas,
             "h_i": h["i"], "l_i": l["i"]}
        sonuc.append(r)
        dolu_bas = bas
        if len(sonuc) >= 3:
            break
    return sonuc


def range_konum(r, fiyat):
    """0 = RL, 0.5 = EQ, 1 = RH."""
    if r is None or r["rh"] == r["rl"]:
        return None
    return (fiyat - r["rl"]) / (r["rh"] - r["rl"])


def deviasyon_tespit(r, mumlar, atrs, mikro_olaylar):
    """Deviasyon + re-entry. Deviasyonun deviasyonu ve istekli breakout ('kaçtı')."""
    sonuc = []
    for d in r["devs"]:
        if d.get("reentry_i") is None:
            continue
        ri = d["reentry_i"]
        kacti = False
        if d.get("reentry_istekli"):
            sinir = r["rl"] if d["yon"] == "asagi" else r["rh"]
            geri = False
            for j in range(ri + 1, min(len(mumlar), ri + 4)):
                tol = 0.3 * atrs[j]
                if (d["yon"] == "asagi" and mumlar[j]["dusuk"] <= sinir + tol) or \
                   (d["yon"] == "yukari" and mumlar[j]["yuksek"] >= sinir - tol):
                    geri = True
            kacti = not geri
        # Deviasyonun deviasyonu: re-entry sonrası yapı ters döndüyse (LH+LL) yeni işlem yok
        ters = "bear" if d["yon"] == "asagi" else "bull"
        dev_dev_i = next((o["i"] for o in mikro_olaylar if o["yon"] == ters and o["i"] > ri), None)
        sonuc.append(dict(d, kacti=kacti, dev_dev_i=dev_dev_i))
    return sonuc


def dev_dev_aktif(d, mumlar, t):
    """t anında 'deviasyonun deviasyonu' geçerli mi? Yapı re-entry sonrası ters
    döndüyse, deviasyon ucunun likiditesi alınana kadar o yönde yeni işlem yok."""
    j = d.get("dev_dev_i")
    if j is None or j > t:
        return False
    for k in range(j, min(t, len(mumlar) - 1) + 1):
        if (d["yon"] == "asagi" and mumlar[k]["dusuk"] < d["uc"]) or \
           (d["yon"] == "yukari" and mumlar[k]["yuksek"] > d["uc"]):
            return False
    return True


# =============================================================================
#                          ANAHTAR ZAMAN SEVİYELERİ
# =============================================================================

def anahtar_seviyeler(mumlar_1d, simdi):
    """Daily / Weekly / Monthly / Yearly Open, Monday High / Low (1day veriden)."""
    if not mumlar_1d:
        return []
    son = mumlar_1d[-1]
    bugun = son["dt"].date()
    sonuc = [{"ad": "DO", "seviye": son["acilis"]}]
    hafta_bas = bugun - datetime.timedelta(days=bugun.weekday())
    hafta = [m for m in mumlar_1d if m["dt"].date() >= hafta_bas]
    if hafta:
        sonuc.append({"ad": "WO", "seviye": hafta[0]["acilis"]})
        pzt = [m for m in hafta if m["dt"].date() == hafta_bas]
        # Pazartesi tamamlanmadıysa Monday H/L kullanılmaz
        if pzt and simdi >= datetime.datetime.combine(hafta_bas, datetime.time()) + datetime.timedelta(days=1):
            sonuc.append({"ad": "MondayHigh", "seviye": pzt[0]["yuksek"]})
            sonuc.append({"ad": "MondayLow", "seviye": pzt[0]["dusuk"]})
    ay = [m for m in mumlar_1d if m["dt"].year == bugun.year and m["dt"].month == bugun.month]
    if ay:
        sonuc.append({"ad": "MO", "seviye": ay[0]["acilis"]})
    yil = [m for m in mumlar_1d if m["dt"].year == bugun.year]
    if yil and yil[0]["dt"].date() <= datetime.date(bugun.year, 1, 7):
        sonuc.append({"ad": "YO", "seviye": yil[0]["acilis"]})
    return sonuc


# =============================================================================
#                                FİBONACCİ / OTE
# =============================================================================

def fib_retracement(swing_1, swing_2, yon):
    """Long: swing low (1) -> swing high (0): seviye(k) = high - k*(high-low).
    Short: swing high (1) -> swing low (0): seviye(k) = low + k*(high-low).
    Dönüş: {k: fiyat} (0, 0.5, OTE seviyeleri, 1)."""
    if yon == "long":
        low, high = swing_1, swing_2
        f = lambda k: high - k * (high - low)
    else:
        high, low = swing_1, swing_2
        f = lambda k: low + k * (high - low)
    seviyeler = sorted(set([0.0, 0.5, 1.0] + list(FIB_OTE_SEVIYELER)))
    return {k: f(k) for k in seviyeler}


def fib_uzatma(p1, p2, p3, yon):
    """Trend temelli uzatma. Long: P3 + k*(P2-P1). Short: P3 - k*(P1-P2)."""
    if yon == "long":
        return {k: p3 + k * (p2 - p1) for k in FIB_UZATMA_SEVIYELER}
    return {k: p3 - k * (p1 - p2) for k in FIB_UZATMA_SEVIYELER}


def ote_bolgesi(low, high):
    """Long OTE bölgesi (alt, ust, öneri 0.705)."""
    f = fib_retracement(low, high, "long")
    return f[max(FIB_OTE_SEVIYELER)], f[min(FIB_OTE_SEVIYELER)], f[0.705] if 0.705 in f else f[FIB_OTE_SEVIYELER[1]]


# =============================================================================
#                               DESEN MODÜLLERİ
# =============================================================================
# Desenler LONG yönde yazılmıştır; short desenler aynı fonksiyonların ters
# çevrilmiş (ayna) mumlar üzerinde çalıştırılmasıyla bulunur. İçerdikleri SFP,
# MSB, OB, imbalance puanları tekrar sayılmaz (bölüm 12.3).

def sfp_bul(mumlar, atrs, swingler, onemli_seviyeler, ic_swingler):
    """Bullish SFP: son dibin altına FİTİL atıp berisinde kapanış. Pencere içinde
    (SFP_GECERLILIK_MUM) hiçbir mum seviyenin altında kapanmamalı."""
    N = len(mumlar)
    sonuc = []
    dipler = [s for s in swingler if s["tip"] == "L"]
    for s in dipler:
        for j in range(s["i"] + 1, N):
            m = mumlar[j]
            if m["kapanis"] < s["fiyat"]:
                break  # seviye kapanışla kırıldı; SFP yok
            if m["dusuk"] < s["fiyat"]:
                if j - s["i"] < SFP_SWING_YASI_MIN_MUM:
                    break
                a = atrs[j]
                durum = "onaylı"
                pencere_son = j + SFP_GECERLILIK_MUM
                iptal_i = None
                for k in range(j + 1, min(N, pencere_son + 1)):
                    if mumlar[k]["kapanis"] < s["fiyat"]:
                        durum, iptal_i = "iptal", k
                        break
                if durum == "onaylı" and pencere_son > N - 1:
                    durum = "aday"
                uc = m["dusuk"]
                # Pencere içindeki daha derin fitiller de süpürmenin parçası
                for k in range(j + 1, min(N, pencere_son + 1)):
                    if iptal_i is not None and k >= iptal_i:
                        break
                    uc = min(uc, mumlar[k]["dusuk"])
                onemli = any(abs(o - s["fiyat"]) <= FIB_CAKISMA_TOLERANS_ATR * a for o in onemli_seviyeler)
                # SFP_KIRILIM kutusu: SFP öncesi son LH
                lh = [x for x in ic_swingler if x["tip"] == "H" and s["i"] < x["i"] < j]
                if not lh:
                    lh = [x for x in ic_swingler if x["tip"] == "H" and x["i"] < j]
                kutu = lh[-1]["fiyat"] if lh else None
                kirilim_i = None
                if kutu is not None and durum != "iptal":
                    for k in range(j + 1, N):
                        if mumlar[k]["kapanis"] < uc:
                            break
                        if mumlar[k]["kapanis"] > kutu:
                            kirilim_i = k
                            break
                sonuc.append({"desen": "SFP", "seviye": s["fiyat"], "swing_i": s["i"], "i": j,
                              "uc": uc, "durum": durum, "iptal_i": iptal_i,
                              "onay_i": min(pencere_son, N - 1), "onemli": onemli,
                              "derin": (s["fiyat"] - uc) > SFP_MAX_DERINLIK_ATR * a,
                              "kutu": kutu, "kirilim_i": kirilim_i})
                break
    return sonuc


def mitigation_bul(mumlar, atrs, ic_swingler, sfplar):
    """Bullish mitigation: L1 -> H1 (mitigation çizgisi) -> L1'i geçemeyen HL ->
    H1 üstünde kapanış -> üstten H1 re-testi -> long."""
    N = len(mumlar)
    dizi = alterne(ic_swingler)
    sonuc = []
    for x in range(len(dizi) - 2):
        l1, h1, hl = dizi[x], dizi[x + 1], dizi[x + 2]
        if l1["tip"] != "L" or h1["tip"] != "H" or hl["tip"] != "L":
            continue
        if not (h1["fiyat"] > hl["fiyat"] > l1["fiyat"]):
            continue  # swing sırası tutarsız: mitigation yapısı yok
        a = atrs[hl["i"]]
        if hl["fiyat"] - l1["fiyat"] < MITIGATION_MIN_FARK_ATR * a:
            continue  # eşit dip = likidite havuzu, mitigation değil
        kirilim_i = None
        for j in range(hl["i"] + 1, min(N, hl["i"] + SFP_MITIGATION_MAX_MUM + 1)):
            if mumlar[j]["kapanis"] < hl["fiyat"]:
                break
            if mumlar[j]["kapanis"] > h1["fiyat"]:
                kirilim_i = j
                break
        if kirilim_i is None:
            continue
        retest_i = iptal_i = None
        for j in range(kirilim_i + 1, min(N, kirilim_i + RETEST_MAX_MUM + 1)):
            tol = MITIGATION_RETEST_TOLERANS_ATR * atrs[j]
            if mumlar[j]["kapanis"] < hl["fiyat"]:
                iptal_i = j
                break
            if mumlar[j]["dusuk"] <= h1["fiyat"] + tol:
                retest_i = j
                break
        sfp_var = any(abs(s["i"] - l1["i"]) <= 2 and s["durum"] != "iptal" for s in sfplar)
        sonuc.append({"desen": "MITIGATION", "l1": l1, "h1": h1, "hl": hl, "kirilim_i": kirilim_i,
                      "retest_i": retest_i, "iptal_i": iptal_i, "sfp": sfp_var})
    return sonuc


def po3_tara(mumlar, atrs, rangeler, ic_swingler, obs):
    """Bullish Power of 3 durum makinesi (aşama 0-5)."""
    N = len(mumlar)
    sonuc = []
    if not PO3_AKTIF:
        return sonuc
    for r in rangeler:
        a = atrs[min(r["bit_i"], N - 1)]
        # Aşama 0: önceki düşüş bacağı; tepesi = nihai hedef
        b0 = max(0, r["bas_i"] - 40)
        if r["bas_i"] - b0 < 2:
            continue
        tj, tepe = _max_yuksek(mumlar, b0, r["bas_i"])
        if tepe - r["rl"] < PO3_ONCEKI_TREND_MIN_ATR * a:
            continue
        for d in r["devs"]:
            if d["yon"] != "asagi" or d.get("reentry_i") is None:
                continue
            p = {"desen": "PO3", "asama": 2, "rh": r["rh"], "rl": r["rl"], "eq": r["eq"],
                 "nihai_hedef": tepe, "manip_dip": d["uc"], "manip_i": d["bas_i"],
                 "notlar": [], "durum": "izleme"}
            ri = d["reentry_i"]
            # Aşama 3: range içindeki son SH'nin kapanışla kırılması + HL
            sh = [s for s in ic_swingler if s["tip"] == "H" and r["bas_i"] <= s["i"] < d["bas_i"]
                  and s["fiyat"] <= r["rh"] + 0.3 * a]
            if not sh:
                sonuc.append(p)
                continue
            sh = sh[-1]
            j3 = None
            for j in range(ri, N):
                if mumlar[j]["dusuk"] < d["uc"]:
                    break
                if mumlar[j]["kapanis"] > sh["fiyat"]:
                    j3 = j
                    break
            if j3 is None:
                sonuc.append(p)
                continue
            p["asama"] = 3
            hl_i, hl = _min_dusuk(mumlar, ri, j3)
            if hl <= d["uc"]:
                continue
            # Aşama 4: RH'nin displacement mumuyla kırılması
            j4 = erken = None
            for j in range(j3, N):
                if mumlar[j]["kapanis"] < hl:
                    p["durum"], p["iptal_i"] = "iptal", j
                    break
                if j > j3:
                    hl_i2, hl2 = _min_dusuk(mumlar, j3, j)
                    if hl2 > d["uc"] and hl2 < hl and mumlar[j]["kapanis"] > hl2:
                        hl_i, hl = hl_i2, hl2
                if mumlar[j]["kapanis"] > r["rh"]:
                    if govde(mumlar[j]) >= DISPLACEMENT_ATR * atrs[j]:
                        j4 = j
                        break
                    if erken is None:
                        erken = j
            p["hl"], p["hl_i"] = hl, hl_i
            if p["durum"] == "iptal":
                sonuc.append(p)
                continue
            if j4 is None:
                if erken is not None:
                    p["notlar"].append("erken kırılım: bekle (RH istekli mumla kırılmadı)")
                sonuc.append(p)
                continue
            p["asama"] = 4
            p["kirilim_i"] = j4
            p["erken"] = erken is not None
            # Aşama 5: RH re-testi
            tepe_i, dag_tepe = j4, mumlar[j4]["yuksek"]
            for j in range(j4 + 1, N):
                tol = 0.3 * atrs[j]
                if mumlar[j]["kapanis"] < hl:
                    p["durum"], p["iptal_i"] = "iptal", j
                    break
                if mumlar[j]["dusuk"] <= r["rh"] + tol:
                    p["asama"] = 5
                    p["retest_i"] = j
                    p["durum"] = "sinyal"
                    break
                if mumlar[j]["yuksek"] > dag_tepe:
                    tepe_i, dag_tepe = j, mumlar[j]["yuksek"]
            p["dagitim_tepe"] = dag_tepe
            ote_alt, ote_ust, ote_oneri = ote_bolgesi(d["uc"], dag_tepe)
            p["ote"] = (ote_alt, ote_ust, ote_oneri)
            ob = next((o for o in obs if o["yon"] == "long" and j3 <= o["olay_i"] <= j4 + 3
                       and o["alt"] >= hl), None)
            p["ob"] = ob
            sonuc.append(p)
    return sonuc


def qm_bul(mumlar, atrs, ana_swingler):
    """Bullish Quasimodo: LL1 -> LH (neckline) -> LL2 (baş) -> LH üstünde
    kapanış -> LL1 seviyesine re-test -> long. Stop (pain level) LL2 altı."""
    N = len(mumlar)
    dizi = alterne(ana_swingler)
    sonuc = []
    for x in range(len(dizi) - 2):
        ll1, lh, ll2 = dizi[x], dizi[x + 1], dizi[x + 2]
        if ll1["tip"] != "L" or lh["tip"] != "H" or ll2["tip"] != "L":
            continue
        a = atrs[ll2["i"]]
        if ll1["fiyat"] - ll2["fiyat"] < QM_MIN_BAS_FARK_ATR * a:
            continue  # LL2 ≈ LL1 -> QM değil, likidite havuzu
        kirilim_i = None
        for j in range(ll2["i"] + 1, min(N, ll1["i"] + QM_MAX_MUM + 1)):
            if mumlar[j]["kapanis"] < ll2["fiyat"]:
                break
            if mumlar[j]["kapanis"] > lh["fiyat"]:
                kirilim_i = j
                break
        if kirilim_i is None:
            continue
        tepe_i, tepe = kirilim_i, mumlar[kirilim_i]["yuksek"]
        retest_i = iptal_i = None
        for j in range(kirilim_i + 1, min(N, kirilim_i + QM_MAX_MUM + 1)):
            tol = QM_OMUZ_TOLERANS_ATR * atrs[j]
            if mumlar[j]["kapanis"] < ll2["fiyat"]:
                iptal_i = j
                break
            if mumlar[j]["dusuk"] <= ll1["fiyat"] + tol:
                retest_i = j
                break
            if mumlar[j]["yuksek"] > tepe:
                tepe_i, tepe = j, mumlar[j]["yuksek"]
        f = fib_retracement(ll2["fiyat"], tepe, "long")
        ote_ok = f[max(FIB_OTE_SEVIYELER)] - QM_OMUZ_TOLERANS_ATR * a <= ll1["fiyat"] <= f[min(FIB_OTE_SEVIYELER)] + QM_OMUZ_TOLERANS_ATR * a
        sonuc.append({"desen": "QM", "ll1": ll1, "lh": lh, "ll2": ll2, "kirilim_i": kirilim_i,
                      "tepe": tepe, "retest_i": retest_i, "iptal_i": iptal_i, "ote": ote_ok,
                      "breaker_bolge": (govde_alt(mumlar[lh["i"]]), govde_ust(mumlar[lh["i"]]))})
    return sonuc


def inducement_bul(mumlar, atrs, ic_swingler, sfplar, imbalancelar):
    """Bullish Inducement Level: likidite alımı -> imbalance bırakan dönüş -> MSB ->
    ilk küçük geri çekilme (tuzak swing) -> tuzak süpürülür -> gap'e (IL) ulaşım -> long."""
    N = len(mumlar)
    sonuc = []
    tepeler = [s for s in ic_swingler if s["tip"] == "H"]
    dipler = [s for s in ic_swingler if s["tip"] == "L"]
    for sfp in sfplar:
        if sfp["durum"] == "iptal":
            continue
        j0 = sfp["i"]
        # 4) MSB: süpürme öncesi son LH üstünde kapanış
        lh = [t for t in tepeler if t["i"] < j0]
        if not lh:
            continue
        lh = lh[-1]
        b = None
        for j in range(j0, min(N, j0 + IND_MAX_MUM)):
            if mumlar[j]["kapanis"] < sfp["uc"]:
                break
            if mumlar[j]["kapanis"] > lh["fiyat"]:
                b = j
                break
        if b is None:
            continue
        # 3) Dönüş hareketi en az bir imbalance bırakmalı
        imbs = [z for z in imbalancelar if z["yon"] == "long" and j0 <= z["i"] <= b + 2]
        if not imbs:
            continue
        gap = imbs[0] if IND_GAP_ONCELIK == "koken" else max(imbs, key=lambda z: z["ust"])
        # 5) İlk küçük geri çekilme = inducement swing (gap'in üstünde)
        ind = next((d for d in dipler if d["i"] > gap["i"] and d["fiyat"] > gap["ust"]), None)
        if ind is None:
            continue
        p = {"desen": "INDUCEMENT", "sfp": sfp, "msb_i": b, "gap": gap, "ind": ind,
             "supurme_i": None, "giris_i": None, "iptal_i": None, "notlar": []}
        for j in range(ind["i"] + 1, min(N, ind["i"] + IND_MAX_MUM)):
            m = mumlar[j]
            if m["kapanis"] < sfp["uc"]:
                p["iptal_i"] = j
                break
            if p["supurme_i"] is None and m["dusuk"] < ind["fiyat"]:
                p["supurme_i"] = j
            if m["dusuk"] <= gap["giris"]:
                if p["supurme_i"] is None and IND_SUPURME_BEKLE:
                    p["notlar"].append("inducement alanı, likidite henüz alınmadı")
                    break
                p["giris_i"] = j
                break
        sonuc.append(p)
    return sonuc


def reversal_fractal_bul(mumlar, atrs, ic_swingler, poi_bolgeleri, renk_kurali=None):
    """Bullish Reversal Fractal: HTF POI içinde son dibin likiditesi temizlenir
    (temizleyen mum yeşil kapanmalı), yeni tepe (MSB), süpürme ile MSB arasındaki
    son yeşil muma dönüş -> long."""
    renk_kurali = RF_RENK_KURALI if renk_kurali is None else renk_kurali
    N = len(mumlar)
    sonuc = []
    dipler = [s for s in ic_swingler if s["tip"] == "L"]
    tepeler = [s for s in ic_swingler if s["tip"] == "H"]
    for d in dipler:
        j = None
        for k in range(d["i"] + 1, min(N, d["i"] + RF_MAX_MUM)):
            if mumlar[k]["kapanis"] < d["fiyat"]:
                break
            if mumlar[k]["dusuk"] < d["fiyat"]:
                j = k
                break
        if j is None:
            continue
        sm = mumlar[j]
        poi = next((z for z in poi_bolgeleri if z["alt"] - 0.3 * atrs[j] <= sm["dusuk"] <= z["ust"] + 0.3 * atrs[j]), None)
        if poi is None:
            continue
        if renk_kurali and not yesil(sm):
            continue
        lh = [t for t in tepeler if t["i"] < j]
        if not lh:
            continue
        lh = lh[-1]
        b = None
        for k in range(j, min(N, j + RF_MAX_MUM)):
            if mumlar[k]["kapanis"] < sm["dusuk"]:
                break
            if mumlar[k]["kapanis"] > lh["fiyat"]:
                b = k
                break
        if b is None:
            continue
        yesiller = [k for k in range(j, b) if yesil(mumlar[k])] or [j]
        sy = yesiller[-1]
        if RF_BOLGE_MODU == "tam":
            alt, ust = mumlar[sy]["dusuk"], mumlar[sy]["yuksek"]
        else:
            alt, ust = govde_alt(mumlar[sy]), govde_ust(mumlar[sy])
        engulf = j + 1 < N and yesil(mumlar[j + 1]) and mumlar[j + 1]["kapanis"] >= sm["yuksek"]
        p = {"desen": "REVERSAL_FRACTAL", "supurme_i": j, "supurme_dip": sm["dusuk"], "msb_i": b,
             "mum_i": sy, "alt": alt, "ust": ust, "poi": poi, "engulfing": engulf,
             "giris_i": None, "iptal_i": None, "zayifladi": False, "renk": yesil(sm)}
        for k in range(b + 1, min(N, b + RETEST_MAX_MUM + 1)):
            if mumlar[k]["kapanis"] < sm["dusuk"]:
                p["iptal_i"] = k
                break
            if mumlar[k]["kapanis"] < alt:
                p["zayifladi"] = True
            if mumlar[k]["dusuk"] <= ust:
                p["giris_i"] = k
                break
        sonuc.append(p)
    return sonuc


# =============================================================================
#                          DİLİM ANALİZİ (tüm modüller)
# =============================================================================

def dilim_analiz(mumlar, dilim, ob_mod=None, breaker_mod=None):
    """Bir zaman dilimi için: ATR -> swing -> yapı -> likidite -> bölgeler.
    Desenler kuruluma özgü bağlam gerektirdiğinden sinyal motorunda aranır."""
    atrs = atr_listesi(mumlar)
    ic = swing_etiketle(swing_noktalari(mumlar, IC_SWING_UZUNLUK))
    adaylar = swing_noktalari(mumlar, ANA_SWING_UZUNLUK)
    yapi = yapi_analiz(mumlar, atrs, adaylar, ANA_SWING_UZUNLUK)
    mikro = mikro_yapi(mumlar, atrs, ic, IC_SWING_UZUNLUK, yapi["trend_dizi"])
    sd = sd_bolgeleri(mumlar, atrs)
    ana = ana_swing_filtre(adaylar, sd, yapi, atrs)
    havuzlar = likidite_havuzu_bul(ana, mumlar, atrs)
    olaylar = sorted(yapi["olaylar"] + mikro["olaylar"], key=lambda o: (o["i"], o["tip"]))
    obs = ob_bul(mumlar, atrs, olaylar, ic, havuzlar, ob_mod)
    imbs = imbalance_bul(mumlar, atrs)
    breakers = breaker_bul(mumlar, atrs, yapi, sd, breaker_mod)
    srs = sr_seviyeleri(mumlar, atrs, ic)
    rangeler = range_tespit(mumlar, atrs, ana)
    for r in rangeler:
        r["devs_detay"] = deviasyon_tespit(r, mumlar, atrs, mikro["olaylar"])
    gaps = gap_bul(mumlar, atrs, dilim)
    return {"dilim": dilim, "m": mumlar, "atrs": atrs, "ic": ic, "adaylar": adaylar, "ana": ana,
            "yapi": yapi, "mikro": mikro, "olaylar": olaylar, "sd": sd, "havuzlar": havuzlar,
            "obs": obs, "imbs": imbs, "breakers": breakers, "srs": srs, "rangeler": rangeler,
            "gaps": gaps, "dts": [m["dt"] for m in mumlar]}


def indeks_bul(dts, dt):
    """dts içinde dt'ye eşit/sonraki ilk indeks (ikili arama). Yoksa len(dts)."""
    lo, hi = 0, len(dts)
    while lo < hi:
        mid = (lo + hi) // 2
        if dts[mid] < dt:
            lo = mid + 1
        else:
            hi = mid
    return lo


def kapanis_zamani(an, i):
    return an["dts"][i] + datetime.timedelta(minutes=DILIM_DAKIKA[an["dilim"]])


def dealing_konum(an, fiyat):
    """Premium/discount konumu: aktif range varsa range, yoksa yapı aralığı."""
    for r in an["rangeler"]:
        if r["durum"] in ("aktif", "deviasyonda") and r["rl"] <= fiyat <= r["rh"]:
            return range_konum(r, fiyat), "range"
    ar = an["yapi"]["aralik"]
    if ar and ar[1] > ar[0]:
        return (fiyat - ar[0]) / (ar[1] - ar[0]), "swing"
    return None, None


def aktif_range(an):
    for r in an["rangeler"]:
        if r["durum"] in ("aktif", "deviasyonda"):
            return r
    return None


# =============================================================================
#                                   PUANLAMA
# =============================================================================

def madde(ad, puan, tur="diger", alt=None, ust=None, grup=None, anahtar=None):
    """Puan maddesi. tur: 'bolge' (çakışma kuralı), 'olay' (bir kez), 'diger'."""
    return {"ad": ad, "puan": puan, "tur": tur, "alt": alt, "ust": ust, "grup": grup or ad,
            "anahtar": anahtar or ad}


def puan_hesapla(maddeler, a, katsayilar=None):
    """Çift sayım önleme ile ham puan ve bağımsız konfirmasyon sayısı."""
    katsayilar = katsayilar or {}
    toplam = 0.0
    bagimsiz = 0
    gorulen = {}
    for x in maddeler:
        if x["tur"] == "bolge":
            continue
        p = x["puan"] * katsayilar.get(x["grup"], 1.0)
        k = x["anahtar"]
        if k in gorulen:
            if p > gorulen[k]:
                toplam += p - gorulen[k]
                gorulen[k] = p
            continue
        gorulen[k] = p
        toplam += p
        if p > 0 and x["grup"] not in ("HTF_TREND", "LIK_HEDEF", "FIB_UZATMA", "PD"):
            bagimsiz += 1
    bolgeler = [x for x in maddeler if x["tur"] == "bolge"]
    tol = FIB_CAKISMA_TOLERANS_ATR * a
    kumeler = []
    for x in bolgeler:
        hedef = None
        for k in kumeler:
            if any(ortust(x["alt"], x["ust"], y["alt"], y["ust"], tol) for y in k):
                hedef = k
                break
        if hedef is None:
            kumeler.append([x])
        else:
            hedef.append(x)
    for k in kumeler:
        k.sort(key=lambda y: -(y["puan"] * katsayilar.get(y["grup"], 1.0)))
        en = k[0]
        toplam += en["puan"] * katsayilar.get(en["grup"], 1.0)
        sd_ob = False
        for y in k[1:]:
            if not sd_ob and {en["grup"], y["grup"]} == {"SD", "OB"}:
                toplam += 0.5 * katsayilar.get(y["grup"], 1.0)
                sd_ob = True
            else:
                toplam += 0.25 * katsayilar.get(y["grup"], 1.0)
        if en["puan"] > 0:
            bagimsiz += 1
    return round(toplam, 2), bagimsiz


def skor_bul(ham):
    if ham < 2:
        return 1
    if ham < 3:
        return 2
    if ham < 4.5:
        return 3
    if ham < 6:
        return 4
    return 5


def ob_puan_maddesi(z, dilim, ob_dilimleri, t):
    """OB puanı: taze/kullanılmış + swing + 1h+ + ≥2 dilim."""
    temas = bolge_temas_sayisi(z, t)
    p = 1.0 if temas == 0 else KULLANILMIS_OB_PUAN
    etiket = []
    if z.get("swingde"):
        p += 0.5
        etiket.append("swing")
    if DILIM_DAKIKA.get(dilim, 0) >= 60:
        p += 0.5
    if len(ob_dilimleri) >= 2:
        p += 0.5
    ad = "OB(%s)" % ",".join(d.upper().replace("DAY", "D") for d in (ob_dilimleri or [dilim]))
    return madde(ad, p, "bolge", z["alt"], z["ust"], "OB")


# =============================================================================
#                               RİSK YÖNETİMİ
# =============================================================================
# Tüm motor LONG çerçevede çalışır; short kurulumlar ayna çerçevede bulunur.

def stop_ayarla(ctx, stop_ref, giris, notlar):
    """Stop daima ilgili swing'in ötesine + STOP_TAMPON_ATR x ATR. İmbalance
    sınırına, EQ altına veya açık likidite havuzunun içine konmaz."""
    ltf = ctx["ltf"]
    a = ltf["atrs"][-1]
    tampon = STOP_TAMPON_ATR * a
    stop = stop_ref - tampon
    for _ in range(3):
        degisti = False
        for an in (ltf, ctx["htf"]):
            for h in an["havuzlar"]:
                if h["yon"] == "L" and havuz_durum_at(h, len(an["m"]) - 1) == "açık" and \
                   h["alt"] - tampon <= stop <= h["ust"] + tampon and h["alt"] - tampon < stop:
                    stop = h["alt"] - tampon
                    degisti = True
                    notlar.append("stop likidite havuzunun ötesine taşındı")
            for z in an["imbs"]:
                # Stop imbalance sınırına konmaz: sınıra çok yakınsa sınırın bir tampon ötesine
                for sinir in (z["alt"], z["ust"]):
                    if z["kirilim_i"] is None and sinir - 0.1 * a < stop <= sinir + 0.1 * a:
                        stop = sinir - tampon
                        degisti = True
        if not degisti:
            break
    r = aktif_range(ctx["htf"]) or aktif_range(ltf)
    if r and r["eq"] - 0.3 * a <= stop <= r["eq"]:
        stop = r["eq"] - 0.3 * a - tampon
        notlar.append("stop EQ'nun hemen altından uzaklaştırıldı")
    if stop >= giris:
        return None
    return stop


def hedef_sec(ctx, k):
    """TP: işlem yönündeki AÇIK likidite havuzları (mesafeye göre), yetmezse
    yapısal hedefler. Fib 1.618 bilgi amaçlı TP3 adayıdır."""
    ltf, htf = ctx["ltf"], ctx["htf"]
    giris = k["giris"]
    a = ltf["atrs"][-1]
    tol = LIK_EQUAL_TOLERANS_ATR * htf["atrs"][-1]
    adaylar = []
    for an, htf_mi in ((ltf, False), (htf, True)):
        son = len(an["m"]) - 1
        acik = [h for h in an["havuzlar"] if h["yon"] == "H" and havuz_durum_at(h, son) == "açık"
                and h["seviye"] > giris + 0.1 * a]
        acik.sort(key=lambda h: h["seviye"])
        for h in acik[:LIK_MAX_HAVUZ]:
            etiket = h["tip"] if h["tip"] != "equal" else "equal(%d)" % h["temas"]
            if htf_mi:
                etiket += "+HTF"
            adaylar.append({"fiyat": h["seviye"], "etiket": etiket, "havuz": True, "htf": htf_mi,
                            "guc": havuz_guc(dict(h, htf=htf_mi))})
    adaylar.sort(key=lambda x: x["fiyat"])
    temiz = []
    for x in adaylar:
        if temiz and abs(x["fiyat"] - temiz[-1]["fiyat"]) <= max(tol, 0.1 * a):
            if x["guc"] > temiz[-1]["guc"]:
                temiz[-1] = x
            continue
        temiz.append(x)
    # Yapısal hedefler
    yapisal = list(k.get("yapisal_hedefler", []))
    r = aktif_range(htf)
    if r and r["rh"] > giris:
        yapisal.append((r["rh"], "RH"))
    for z in htf["sd"]:
        if z["yon"] == "short" and z["kirilim_i"] is None and z["alt"] > giris:
            yapisal.append((z["alt"], "karşı POI"))
    for z in htf["breakers"]:
        if z["yon"] == "short" and z["iptal_i"] is None and z["alt"] > giris:
            yapisal.append((z["alt"], "breaker"))
    for z in htf["obs"]:
        if z["yon"] == "short" and z["kirilim_i"] is None and z["alt"] > giris:
            yapisal.append((z["alt"], "karşı OB"))
    fib1 = fib16 = None
    if k.get("bacak"):
        lo, hi = k["bacak"]
        if hi - lo >= FIB_BACAK_MIN_ATR * a * 0.5:
            # DD fib notu / şartname 9.2: P1 = dip, P2 = tepe, P3 = 0.705 noktası
            # (geri çekilme bu noktadan daha derin döndüyse gerçekleşen dönüş = giriş)
            p3 = min(fib_retracement(lo, hi, "long")[0.705], max(giris, lo))
            u = fib_uzatma(lo, hi, p3, "long")
            fib1, fib16 = u.get(1.0), u.get(1.618)
            if fib1 and fib1 > giris:
                yapisal.append((fib1, "FIB1"))
    yapisal = sorted(set((p, e) for p, e in yapisal if p > giris + 0.1 * a))
    # Fib 1.0 bir havuz/OB ile çakışıyor mu?
    if fib1:
        tol_f = FIB_CAKISMA_TOLERANS_ATR * a
        for x in temiz:
            if abs(x["fiyat"] - fib1) <= tol_f:
                x["etiket"] = "FIB1+LIK"
                k["maddeler"].append(madde("FIB1+LIK", 0.5, "diger", grup="FIB_UZATMA"))
                break
        else:
            # DD: 1.0 noktasındaki direnç bölgesinde OB vb. varsa ekstra onay (şartname 12.1)
            for an in (ltf, htf):
                if any(z["yon"] == "short" and z["kirilim_i"] is None and z["alt"] - tol_f <= fib1 <= z["ust"] + tol_f
                       for z in an["obs"]):
                    k["maddeler"].append(madde("FIB1+OB", 0.5, "diger", grup="FIB_UZATMA"))
                    break
    tps = [(x["fiyat"], x["etiket"]) for x in temiz[:3]]
    if any(x["htf"] for x in temiz[:3]):
        k["maddeler"].append(madde("LIK:HTF_hedef", 0.5, grup="LIK_HEDEF"))
    if not temiz:
        k["maddeler"].append(madde("havuz_yok", -0.5, grup="HAVUZ_YOK"))
    if len(tps) < 3:
        for p, e in yapisal:
            if len(tps) >= 3:
                break
            if all(abs(p - q) > 0.2 * a for q, _ in tps):
                tps.append((p, "yapısal:" + e))
        tps.sort(key=lambda x: x[0])
        if len(tps) < 3 and fib16 and fib16 > max([giris] + [q for q, _ in tps]) + 0.2 * a:
            tps.append((fib16, "FIB1.618(bilgi)"))
        if any(e.startswith("yapısal") for _, e in tps):
            k["notlar"].append("yapısal hedef")
    k["tps"] = tps[:3]
    # Yolda açık imbalance var mı?
    if k["tps"]:
        tp1 = k["tps"][0][0]
        for an in (ltf, htf):
            son = len(an["m"]) - 1
            for z in an["imbs"]:
                if imbalance_durum_at(z, son) in ("açık", "ön tepki") and giris < z["alt"] < tp1:
                    k["notlar"].append("yolda açık imbalance: fiyat önce onu doldurabilir, hedef aşılabilir")
                    return


def rr_hesapla(k):
    risk = k["giris"] - k["stop"]
    k["rr"] = [round((tp - k["giris"]) / risk, 2) if risk > 0 else 0 for tp, _ in k["tps"]]


def sonuc_degerlendir(m, r, k):
    """Sinyal sonrası: stop / TP1-2-3 / açık (long çerçeve). Sayım giriş dolduktan sonra başlar."""
    ulasilan = 0
    dolum = next((j for j in range(r, len(m)) if m[j]["dusuk"] <= k["giris"]), None)
    if dolum is None:
        return "dolmadı", None
    for j in range(dolum, len(m)):
        if m[j]["dusuk"] <= k["stop"]:
            return ("stop" if ulasilan == 0 else "tp%d" % ulasilan), j
        for n, (tp, _) in enumerate(k["tps"], 1):
            if m[j]["yuksek"] >= tp and n > ulasilan:
                ulasilan = n
        if ulasilan == len(k["tps"]) and ulasilan > 0:
            return "tp%d" % ulasilan, j
    return ("açık" if ulasilan == 0 else "tp%d" % ulasilan), None


# =============================================================================
#                                SİNYAL MOTORU
# =============================================================================

def yeni_kurulum(ctx, tip, dilim, **ek):
    k = {"tip": tip, "sembol": ctx["sembol"], "eslesme": ctx["eslesme"], "ayna": ctx["ayna"],
         "poi_dilim": ctx["htf"]["dilim"], "onay_dilim": ctx["ltf"]["dilim"], "dilim": dilim,
         "asama": "izleme", "tetik_i": None, "giris_alt": None, "giris_ust": None, "giris": None,
         "stop_ref": None, "stop": None, "tps": [], "rr": [], "maddeler": [], "notlar": [],
         "temas_no": 1, "po3_asama": "", "ote_seviye": "", "ob_dilimleri": [], "mikro": False,
         "anahtar_dt": "", "poi": None, "yapisal_hedefler": [], "bacak": None, "ham_puan": 0,
         "skor": 0, "gecmis": []}
    k.update(ek)
    return k


def ob_dilimleri(ctx, alt, ust):
    """Aynı bölgenin OB_TEYIT_ZAMAN_DILIMLERI'ndeki OB teyitleri."""
    sonuc = []
    for d in OB_TEYIT_ZAMAN_DILIMLERI:
        an = ctx["an"].get(d)
        if not an:
            continue
        a = an["atrs"][-1]
        if any(z["yon"] == "long" and z["kirilim_i"] is None and ortust(z["alt"], z["ust"], alt, ust, 0.2 * a)
               for z in an["obs"]):
            sonuc.append(d)
    return sonuc


def trend_durumu(ctx):
    return ctx["htf"]["yapi"]["trend"]


def ortak_maddeler(ctx, k):
    """Trend uyumu, MICRO, premium/discount, anahtar seviye."""
    trend = trend_durumu(ctx)
    if trend == "bull":
        k["maddeler"].append(madde("HTF_BULL" if not ctx["ayna"] else "HTF_BEAR", 1, grup="HTF_TREND"))
    if k.get("mikro"):
        k["maddeler"].append(madde("MICRO", -0.5, grup="MICRO"))
    konum, kaynak = dealing_konum(ctx["htf"], k["giris"])
    if konum is not None and konum < 0.5:
        k["maddeler"].append(madde("DISCOUNT" if not ctx["ayna"] else "PREMIUM", 0.5, grup="PD"))
    a = ctx["ltf"]["atrs"][-1]
    tol = FIB_CAKISMA_TOLERANS_ATR * a
    lo = min(k["giris_alt"], k["giris"]) - tol
    hi = max(k["giris_ust"], k["giris"]) + tol
    if k.get("poi"):
        lo, hi = min(lo, k["poi"][0]), max(hi, k["poi"][1])
    for s in ctx["anahtar"]:
        if lo <= s["seviye"] <= hi:
            k["maddeler"].append(madde(s["ad"], 1, grup="ANAHTAR", anahtar="ANAHTAR"))
            break


def ana_supply_icinde(ctx, fiyat):
    """HTF ana arz bölgesinin (çerçevede short S&D) içinde mi?"""
    htf = ctx["htf"]
    for z in htf["sd"]:
        if z["yon"] == "short" and z["kirilim_i"] is None and z["alt"] <= fiyat <= z["ust"]:
            return True
    return False


def kurulum_tamamla(ctx, k):
    """Risk + puan + veto. k['asama'] sinyal/retest_bekliyor ise tam hesap yapılır."""
    if k["giris"] is None or k["stop_ref"] is None:
        return k
    if k["stop_ref"] >= k["giris"]:
        k["veto"] = "geçersiz yapı: stop referansı girişin ötesinde değil"
        if k["asama"] == "sinyal":
            k["asama"] = "izleme"
        k["notlar"].append("veto: " + k["veto"])
        return k
    ltf = ctx["ltf"]
    a = ltf["atrs"][-1]
    # Giriş hiçbir zaman bir likidite seviyesi değildir
    for an in (ltf, ctx["htf"]):
        son = len(an["m"]) - 1
        for h in an["havuzlar"]:
            tol = LIK_EQUAL_TOLERANS_ATR * a
            if h["yon"] == "L" and abs(h["seviye"] - k["giris"]) <= tol and havuz_durum_at(h, son) == "açık":
                yeni = h["alt"] - tol
                if yeni > k["stop_ref"]:
                    k["giris"] = yeni
                    k["notlar"].append("giriş likidite seviyesinden kaydırıldı")
    k["giris_alt"] = min(k["giris_alt"], k["giris"])
    k["giris_ust"] = max(k["giris_ust"], k["giris"])
    k["stop"] = stop_ayarla(ctx, k["stop_ref"], k["giris"], k["notlar"])
    if k["stop"] is None:
        k["veto"] = "stop girişin ötesine konamıyor"
        return k
    ortak_maddeler(ctx, k)
    hedef_sec(ctx, k)
    rr_hesapla(k)
    k["ham_puan"], k["bagimsiz"] = puan_hesapla(k["maddeler"], a, ctx.get("katsayilar"))
    k["skor"] = skor_bul(k["ham_puan"])
    # --- Vetolar ---
    veto = k.get("veto")
    if not k["tps"]:
        veto = veto or "hedef bulunamadı"
    elif k["rr"][0] < MIN_RR:
        veto = veto or ("stop çok uzak (R/R %.2f)" % k["rr"][0] if (k["giris"] - k["stop"]) > 2 * a
                        else "R/R yetersiz (%.2f)" % k["rr"][0])
    if ana_supply_icinde(ctx, k["giris"]) or ana_supply_icinde(ctx, ltf["m"][-1]["kapanis"]):
        veto = veto or ("ana supply bölgesinde long yok" if not ctx["ayna"] else "ana demand bölgesinde short yok")
    if k.get("bagimsiz", 0) < 2:
        veto = veto or "en az iki bağımsız konfirmasyon yok"
    k["veto"] = veto
    if k["asama"] == "sinyal":
        if veto:
            k["asama"] = "izleme"
            k["notlar"].append("veto: " + veto)
        elif k["skor"] < MIN_SKOR:
            k["asama"] = "izleme"
            k["notlar"].append("skor MIN_SKOR altında")
    return k


def poi_bul(ctx):
    """HTF'de S&D temel alınır (OB ve breaker da DD'ye göre birer S&D'dir);
    içindeki/üstündeki OB, imbalance, range ucu/deviasyon, anahtar seviye, S/R
    flip puanlanır. POI_MIN_PUAN altı POI değildir."""
    htf = ctx["htf"]
    N = len(htf["m"])
    a = htf["atrs"][-1]
    trend = htf["yapi"]["trend"]
    tabanlar = [z for z in htf["sd"] if z["yon"] == "long"] + \
               [z for z in htf["obs"] if z["yon"] == "long"] + \
               [z for z in htf["breakers"] if z["yon"] == "long" and z["iptal_i"] is None]
    pois = []
    for z in tabanlar:
        if z["olusum_i"] < N - BOLGE_MAX_YAS_MUM:
            continue
        if z.get("kirilim_i") is not None and z["kirilim_i"] < N - 3:
            continue  # bozulmuş bölge (son 3 mumda bozulanlar iptal olarak raporlanır)
        # Bölge oluştuktan sonra HTF yapısı ters döndüyse (MSB) POI değildir
        if any(o["tip"] == "MSB" and o["yon"] == "bear" and o["i"] > z["olusum_i"] for o in htf["yapi"]["olaylar"]):
            continue
        mikro = False
        if trend == "bear":
            konum, _ = dealing_konum(htf, z["ust"])
            if konum is None or konum >= 0.5:
                continue  # trende ters bölge POI olmaz (sadece TP adayı)
            mikro = True
        maddeler = []
        if z["tur"] == "SD":
            maddeler.append(madde("SD:" + z["tip"], 1.0, "bolge", z["alt"], z["ust"], "SD"))
            if z.get("ic_sfp"):
                maddeler.append(madde("base_ici_SFP", 0.5, "olay", anahtar="BASE_SFP"))
        elif z["tur"] == "OB":
            maddeler.append(ob_puan_maddesi(z, htf["dilim"], ob_dilimleri(ctx, z["alt"], z["ust"]), z["k"] + 2))
        else:
            maddeler.append(madde("BREAKER", 1.0, "bolge", z["alt"], z["ust"], "BREAKER"))
        tol = FIB_CAKISMA_TOLERANS_ATR * a
        for o in htf["obs"]:
            if o is not z and o["yon"] == "long" and o["kirilim_i"] is None and ortust(o["alt"], o["ust"], z["alt"], z["ust"], tol):
                maddeler.append(ob_puan_maddesi(o, htf["dilim"], ob_dilimleri(ctx, o["alt"], o["ust"]), o["k"] + 2))
                break
        for im in htf["imbs"]:
            if im["yon"] == "long" and im["kirilim_i"] is None and ortust(im["alt"], im["ust"], z["alt"], z["ust"], tol):
                maddeler.append(madde("IMB(%s)" % htf["dilim"], 0.25 if im["zayif"] else 0.5, "bolge", im["alt"], im["ust"], "IMB"))
                break
        for sr in htf["srs"]:
            if sr.get("yon") == "long" and sr["flip"] == "teyitli" and ortust(sr["alt"], sr["ust"], z["alt"], z["ust"], tol):
                maddeler.append(madde("SR_FLIP", 0.5 + (0.5 if sr["temas"] >= 5 else 0), "bolge", sr["alt"], sr["ust"], "SR"))
                break
        for r in htf["rangeler"]:
            if r["durum"] in ("aktif", "deviasyonda") and z["alt"] - tol <= r["rl"] <= z["ust"] + tol:
                maddeler.append(madde("RANGE_UCU(RL)", 0.5, grup="RANGE_UCU", anahtar="RANGE_UCU"))
                break
        for r in htf["rangeler"]:
            for d in r.get("devs_detay", []):
                if d["yon"] == "asagi" and z["alt"] - tol <= d["uc"] <= z["ust"] + tol and not dev_dev_aktif(d, htf["m"], N - 1):
                    maddeler.append(madde("DEVIASYON", 1.0, "olay", anahtar="DEV_%d" % d["bas_i"]))
                    break
        for s in ctx["anahtar"]:
            if z["alt"] - tol <= s["seviye"] <= z["ust"] + tol:
                maddeler.append(madde(s["ad"], 1.0, grup="ANAHTAR", anahtar="ANAHTAR"))
                break
        konum, _ = dealing_konum(htf, z["ust"])
        if konum is not None and konum < 0.5:
            maddeler.append(madde("DISCOUNT", 0.5, grup="PD"))
        puan, _ = puan_hesapla(maddeler, a)
        if puan < POI_MIN_PUAN:
            continue
        pois.append({"z": z, "alt": z["alt"], "ust": z["ust"], "puan": puan, "maddeler": maddeler,
                     "mikro": mikro, "olusum_dt": kapanis_zamani(htf, z["olusum_i"])})
    pois.sort(key=lambda p: -p["puan"])
    temiz = []
    for p in pois:
        if any(ortust(p["alt"], p["ust"], q["alt"], q["ust"]) for q in temiz):
            continue
        temiz.append(p)
    return temiz


def poi_motoru(ctx, poi):
    """POI -> bölgede onay bekleniyor -> kırılım (CHoCH/MSB) -> re-test -> sinyal."""
    htf, ltf = ctx["htf"], ctx["ltf"]
    m = ltf["m"]
    N = len(m)
    atrs = ltf["atrs"]
    z = poi["z"]
    k = yeni_kurulum(ctx, "POI", ltf["dilim"], poi=(poi["alt"], poi["ust"]), mikro=poi["mikro"],
                     anahtar_dt=zaman_yaz(htf["dts"][z["bas_i"]]), asama="poi_bekliyor")
    k["notlar"] = []
    bas = indeks_bul(ltf["dts"], poi["olusum_dt"])
    iptal_lt = N
    if z.get("kirilim_i") is not None:
        iptal_lt = indeks_bul(ltf["dts"], kapanis_zamani(htf, z["kirilim_i"]))
    onaylar = [o for o in ltf["olaylar"] if o["yon"] == "bull" and o["tip"] in ("CHOCH", "MSB")]
    htf_a = htf["atrs"][-1]
    # Temasları bul
    temaslar = []
    icerde = False
    for i in range(bas, min(N, iptal_lt)):
        dokundu = m[i]["dusuk"] <= poi["ust"] + IMB_ON_TEPKI_ATR * htf_a
        if dokundu and not icerde:
            temaslar.append(i)
            icerde = True
        elif m[i]["dusuk"] > poi["ust"] + 0.5 * htf_a:
            icerde = False
    onceki_tepki_dip = None
    son_durum = None
    for no, t in enumerate(temaslar, 1):
        k["temas_no"] = no
        ev = next((o for o in onaylar if t <= o["i"] <= t + ONAY_MAX_MUM and o["i"] < iptal_lt), None)
        if ev is None:
            if N - 1 - t < ONAY_MAX_MUM and iptal_lt >= N:
                if m[-1]["kapanis"] <= poi["ust"] + htf_a:
                    son_durum = ("onay_bekliyor", t, None)
                else:
                    son_durum = None  # fiyat CHoCH olmadan bölgeden uzaklaştı; POI bekleniyor
                break
            k["gecmis"].append({"durum": "iptal", "sebep": "onay gelmedi", "i": t})
            son_durum = ("iptal", t, "onay gelmedi (ONAY_MAX_MUM doldu)")
            continue
        b = ev["i"]
        lo_i, lo = _min_dusuk(m, t, b)
        ikinci = onceki_tepki_dip is not None and lo < onceki_tepki_dip
        onceki_tepki_dip = lo
        # Kırılımın bıraktığı yapı: OB > imbalance > kırılan seviye
        ob = next((o for o in ltf["obs"] if o["yon"] == "long" and o["olay_i"] == b and o["k"] >= lo_i - 1), None) or \
            next((o for o in ltf["obs"] if o["yon"] == "long" and lo_i - 1 <= o["k"] <= b), None)
        imbs = [x for x in ltf["imbs"] if x["yon"] == "long" and lo_i <= x["i"] <= b + 1]
        imb = max(imbs, key=lambda x: x["giris"]) if imbs else None
        a = atrs[b]
        if ob:
            giris, g_alt, g_ust, yapi_ad = ob["giris"], ob["alt"], ob["ust"], "OB"
        elif imb:
            giris, g_alt, g_ust, yapi_ad = imb["giris"], imb["alt"], imb["ust"], "IMB"
        else:
            giris, g_alt, g_ust, yapi_ad = ev["seviye"], ev["seviye"] - 0.1 * a, ev["seviye"] + 0.1 * a, None
        r = None
        iptal = None
        tepe = m[b]["yuksek"]
        for j in range(b + 1, min(N, b + RETEST_MAX_MUM + 1)):
            if m[j]["kapanis"] < lo or (yapi_ad == "IMB" and m[j]["kapanis"] < imb["alt"]):
                iptal = j
                break
            # DD imbalance notu: trend yönünde fiyat imbalance'ın tam içine gelmeden bir tık
            # yukarısından tepki alabilir -> IMB_ON_TEPKI_ATR içinde gelmek re-test sayılır
            tetik_seviye = giris + (IMB_ON_TEPKI_ATR * atrs[j] if yapi_ad == "IMB" else 0.0)
            if m[j]["dusuk"] <= tetik_seviye:
                r = j
                break
            tepe = max(tepe, m[j]["yuksek"])
        k.update({"giris": giris, "giris_alt": g_alt, "giris_ust": g_ust, "stop_ref": lo,
                  "bacak": (lo, tepe), "onay": ev, "yapi_ad": yapi_ad, "ob": ob, "imb": imb,
                  "temas_i": t, "ikinci": ikinci, "lo_i": lo_i})
        if iptal is not None:
            k["gecmis"].append({"durum": "iptal", "sebep": "re-test öncesi dip kırıldı", "i": iptal})
            son_durum = ("iptal", iptal, "imbalance kırıldı; bias ters" if m[iptal]["kapanis"] >= lo
                         else "re-test öncesi kırılım dibi kapanışla kırıldı")
            continue
        if r is None:
            if N - 1 - b < RETEST_MAX_MUM:
                son_durum = ("retest_bekliyor", b, None)
                break
            k["gecmis"].append({"durum": "kaçtı", "i": b})
            son_durum = ("kacti", b, "re-test gelmedi (RETEST_MAX_MUM doldu)")
            continue
        son_durum = ("sinyal", r, None)
        # Sinyal sonrası stop olduysa ikinci temas kurulumu otomatik takibe alınır
        stop_oldu = any(m[j]["kapanis"] < lo for j in range(r + 1, N))
        if stop_oldu and no < len(temaslar):
            k["gecmis"].append({"durum": "sinyal", "i": r, "giris": giris, "stop_ref": lo})
            continue
        break
    if iptal_lt < N and (son_durum is None or son_durum[0] != "sinyal"):
        son_durum = ("iptal", min(iptal_lt, N - 1), "POI'nin öbür tarafında HTF kapanışı")
    if son_durum is None:
        return k
    durum, idx, sebep = son_durum
    k["asama"] = durum
    k["tetik_i"] = idx
    if sebep:
        k["notlar"].append(sebep)
    if durum in ("onay_bekliyor",):
        return k
    if k.get("onay") is None:
        return k
    # --- Puan maddeleri ---
    k["maddeler"] = [dict(x) for x in poi["maddeler"] if x["grup"] not in ("ANAHTAR", "PD")]
    htf_t = max(0, indeks_bul(htf["dts"], ltf["dts"][k["temas_i"]] + datetime.timedelta(seconds=1)) - 1)
    if z["tur"] == "SD" and bolge_temas_sayisi(z, htf_t) >= SD_MAX_TEMAS:
        k["maddeler"][0]["puan"] = 0.5  # kullanılmış S&D
    elif z["tur"] == "OB":
        k["maddeler"][0] = ob_puan_maddesi(z, htf["dilim"], ob_dilimleri(ctx, z["alt"], z["ust"]), htf_t)
    ev = k["onay"]
    etiket = "MITIGATION" if ev.get("yapi_tipi") == "MITIGATION" else ev["tip"]
    if ev["tip"] == "MSB":
        k["maddeler"].append(madde("LTF_MSB" if etiket == "MSB" else "MSB/" + etiket, 1.5, "olay", anahtar="LTF_ONAY"))
    else:
        k["maddeler"].append(madde("CHOCH" if etiket == "CHOCH" else "CHOCH/" + etiket, 1, "olay", anahtar="LTF_ONAY"))
    son_olay = htf["yapi"]["son_olay"]
    if son_olay and son_olay["yon"] == "bull":
        if son_olay["tip"] == "MSB":
            k["maddeler"].append(madde("MSB", 1.5, "olay", anahtar="HTF_MSB"))
        else:
            k["maddeler"].append(madde("BOS", 1, "olay", anahtar="HTF_BOS"))
    ltf_maddeleri(ctx, k)
    if k["ikinci"]:
        k["maddeler"].append(madde("ikinci_temas", 1, "olay", anahtar="IKINCI"))
    if k["yapi_ad"] is None:
        k["maddeler"].append(madde("yapi_birakmadi", -0.5, grup="YAPI_YOK"))
        k["notlar"].append("kırılım yapı bırakmadı; re-test kırılan seviyede")
    return kurulum_tamamla(ctx, k)


def ltf_maddeleri(ctx, k):
    """Giriş bölgesi çevresindeki LTF konfirmasyonları (OB, IMB, OTE, SFP, S/R, breaker)."""
    ltf = ctx["ltf"]
    m = ltf["m"]
    a = ltf["atrs"][-1]
    tol = FIB_CAKISMA_TOLERANS_ATR * a
    t = k.get("temas_i") or 0
    b = k["onay"]["i"] if k.get("onay") else (k.get("tetik_i") or len(m) - 1)
    son = k["tetik_i"] if k.get("tetik_i") is not None else len(m) - 1
    if k.get("ob"):
        ob = k["ob"]
        k["ob_dilimleri"] = ob_dilimleri(ctx, ob["alt"], ob["ust"])
        om = ob_puan_maddesi(ob, ltf["dilim"], k["ob_dilimleri"], son)
        # Karşı OB uyarısı: fiyat ile OB arasında ters yönde taze OB (+ CHoCH -> puan 0)
        for x in ltf["obs"]:
            if x["yon"] == "short" and x["k"] > ob["k"] and x["alt"] > ob["ust"] and bolge_temas_sayisi(x, son) == 0 \
               and x["kirilim_i"] is None and x["k"] < son:
                choch = any(o["tip"] == "CHOCH" and o["yon"] == "bear" and x["k"] < o["i"] <= son for o in ltf["olaylar"])
                om["puan"] = 0 if choch else om["puan"] / 2
                k["notlar"].append("risk: karakter değişimi (karşı OB)" if choch else "karşı taze OB var")
                break
        if DILIM_DAKIKA.get(ltf["dilim"], 60) < 60:
            htf_bolgeler = [(z["alt"], z["ust"]) for z in ctx["htf"]["sd"] + ctx["htf"]["obs"] if z["yon"] == "long"]
            if k.get("poi"):
                htf_bolgeler.append(k["poi"])
            if not any(ortust(ob["alt"], ob["ust"], lo, hi) for lo, hi in htf_bolgeler):
                om["puan"] = 0
                k["notlar"].append("LTF OB HTF bölge dışında (puan yok)")
        if ob.get("likidite_riski"):
            k["notlar"].append("likidite riski: OB altında açık havuz; stop havuzun ötesine taşındı veya süpürme beklenmeli")
        k["maddeler"].append(om)
    for im in ltf["imbs"]:
        if im["yon"] == "long" and ortust(im["alt"], im["ust"], k["giris_alt"], k["giris_ust"], tol) and \
           imbalance_durum_at(im, max(son - 1, 0)) in ("açık", "ön tepki", "dolduruldu"):
            k["maddeler"].append(madde("IMB(%s)" % ltf["dilim"], 0.25 if im["zayif"] else 0.5, "bolge", im["alt"], im["ust"], "IMB"))
            for g in ctx["gaps"]:
                if ortust(g["alt"], g["ust"], im["alt"], im["ust"], tol):
                    k["maddeler"].append(madde("IMB+GAP", 0.5, grup="GAP", anahtar="GAP"))
                    if g["dilim"] in ("1day", "2day"):
                        k["maddeler"].append(madde("GUNLUK_GAP", 0.5, grup="GAP_G", anahtar="GAP_G"))
                    break
            break
    # OTE (kırılım bacağı): giriş 0.618-0.786 içinde mi?
    if k.get("bacak"):
        lo, hi = k["bacak"]
        if hi - lo >= FIB_BACAK_MIN_ATR * a * 0.5:
            f = fib_retracement(lo, hi, "long")
            o_alt, o_ust = f[max(FIB_OTE_SEVIYELER)], f[min(FIB_OTE_SEVIYELER)]
            if o_alt <= k["giris"] <= o_ust:
                seviye = min(FIB_OTE_SEVIYELER, key=lambda x: abs(f[x] - k["giris"]))
                k["ote_seviye"] = "OTE%s" % seviye
                k["maddeler"].append(madde(k["ote_seviye"], 0.5, "bolge", o_alt, o_ust, "OTE"))
                if k.get("ob") or k.get("imb") or k["tip"] == "BREAKER":
                    k["maddeler"].append(madde("OTE+YAPI", 0.5, grup="OTE_CAKISMA"))
    # SFP / süpürme (olay bir kez)
    for s in ctx["ltf_sfp"]:
        if s["durum"] == "onaylı" and t - 2 <= s["i"] <= b:
            k["maddeler"].append(madde("SFP", 0.5 if s["derin"] else 1, "olay", anahtar="SUPURME"))
            if s["onemli"]:
                k["maddeler"].append(madde("SFP_onemli_seviye", 0.5, "olay", anahtar="SFP_ONEMLI"))
            break
    for h in ltf["havuzlar"]:
        if h["yon"] == "L" and h["tip"] == "relative" and h["supurme_i"] is not None and t - 2 <= h["supurme_i"] <= b:
            k["maddeler"].append(madde("LIK:relative", 0.5, "olay", anahtar="LIK_REL"))
            break
    for r in ltf["rangeler"]:
        for d in r.get("devs_detay", []):
            aralikta = r["rl"] - 0.5 * (r["rh"] - r["rl"]) <= k["giris"] <= r["eq"]
            if d["yon"] == "asagi" and aralikta and d["reentry_i"] <= b + 1 and dev_dev_aktif(d, m, b):
                k["veto"] = "deviasyonun deviasyonu"
            elif d["yon"] == "asagi" and t - 2 <= d["reentry_i"] <= b + 1:
                if not d["kacti"]:
                    k["maddeler"].append(madde("DEVIASYON", 1, "olay", anahtar="SUPURME"))
    # S/R flip ve EQ flip
    for an in (ltf, ctx["htf"]):
        for sr in an["srs"]:
            if sr.get("yon") == "long" and sr["flip"] == "teyitli" and ortust(sr["alt"], sr["ust"], k["giris_alt"], k["giris_ust"], tol):
                p = 0.5 + (0.5 if sr["temas"] >= 5 else 0)
                r = aktif_range(an)
                if r and abs(sr["seviye"] - r["eq"]) <= tol:
                    p += 0.5
                    k["notlar"].append("EQ_FLIP")
                k["maddeler"].append(madde("SR_FLIP", p, "bolge", sr["alt"], sr["ust"], "SR"))
                break
    # Breaker re-test
    if k["tip"] != "BREAKER":
        for an in (ltf, ctx["htf"]):
            for z in an["breakers"]:
                if z["yon"] == "long" and z["retest_i"] is not None and ortust(z["alt"], z["ust"], k["giris_alt"], k["giris_ust"], tol):
                    p = 1 if z["retest_tip"] == "tam" else 0.5
                    if an["dilim"] in BREAKER_ZAMAN_DILIMLERI:
                        p += 0.5
                    k["maddeler"].append(madde("BREAKER(%s)" % an["dilim"], p, "bolge", z["alt"], z["ust"], "BREAKER"))
                    break


def kondisyon_var(ctx, alt, ust):
    """Breaker / mitigation kondisyon şartı: S/R flip, range EQ, OB/IMB, S&D, anahtar seviye."""
    ltf, htf = ctx["ltf"], ctx["htf"]
    a = ltf["atrs"][-1]
    tol = FIB_CAKISMA_TOLERANS_ATR * a
    bulunan = []
    for an in (ltf, htf):
        if any(sr["flip"] == "teyitli" and ortust(sr["alt"], sr["ust"], alt, ust, tol) for sr in an["srs"]):
            bulunan.append("SR_FLIP")
        r = aktif_range(an)
        if r and alt - tol <= r["eq"] <= ust + tol:
            bulunan.append("EQ")
        if any(o["yon"] == "long" and ortust(o["alt"], o["ust"], alt, ust, tol) for o in an["obs"]):
            bulunan.append("OB")
        if any(x["yon"] == "long" and ortust(x["alt"], x["ust"], alt, ust, tol) for x in an["imbs"]):
            bulunan.append("IMB")
        if any(z["yon"] == "long" and ortust(z["alt"], z["ust"], alt, ust, tol) for z in an["sd"]):
            bulunan.append("SD")
    if any(alt - tol <= s["seviye"] <= ust + tol for s in ctx["anahtar"]):
        bulunan.append("ANAHTAR")
    return sorted(set(bulunan))


def ters_trend_izni(ctx, k, onemli_sfp=False, msb=False):
    """Ana trende ters sinyal: MSB sonrası, önemli seviye SFP'si veya MICRO şartı."""
    if trend_durumu(ctx) != "bear":
        return True
    if msb or onemli_sfp:
        return True
    konum, _ = dealing_konum(ctx["htf"], k["giris"])
    talepte = any(z["yon"] == "long" and z["kirilim_i"] is None and z["alt"] - 0.3 * ctx["htf"]["atrs"][-1] <= k["giris"] <= z["ust"] + 0.3 * ctx["htf"]["atrs"][-1]
                  for z in ctx["htf"]["sd"] + ctx["htf"]["obs"])
    if konum is not None and konum < 0.5 and talepte:
        k["mikro"] = True
        return True
    return False


def desen_kurulumlari(ctx, pois):
    """SFP, Mitigation, Breaker, PO3, QM, Inducement, Reversal Fractal kurulumları."""
    ltf, htf = ctx["ltf"], ctx["htf"]
    m = ltf["m"]
    N = len(m)
    atrs = ltf["atrs"]
    sonuc = []
    dts = ltf["dts"]

    # --- SFP ---
    for s in ctx["ltf_sfp"]:
        if s["durum"] != "onaylı" or s["onay_i"] < N - 60:
            continue
        a = atrs[s["i"]]
        maddeler_temel = [madde("SFP", 0.5 if s["derin"] else 1, "olay", anahtar="SUPURME")]
        if s["onemli"]:
            maddeler_temel.append(madde("SFP_onemli_seviye", 0.5, "olay", anahtar="SFP_ONEMLI"))
        modlar = ["SFP_AGRESIF", "SFP_KIRILIM"] if SFP_GIRIS_MODU == "ikisi" else [SFP_GIRIS_MODU]
        for mod in modlar:
            k = yeni_kurulum(ctx, "SFP", ltf["dilim"], anahtar_dt=zaman_yaz(dts[s["i"]]) + mod)
            k["maddeler"] = [dict(x) for x in maddeler_temel]
            k["stop_ref"] = s["uc"]
            k["bacak"] = None
            if mod == "SFP_AGRESIF":
                k["giris"] = s["seviye"] + OB_GIRIS_TIK_ATR * a
                k["giris_alt"], k["giris_ust"] = s["seviye"], k["giris"]
                k["tetik_i"] = s["onay_i"]
                k["asama"] = "sinyal"
            else:
                if s["kirilim_i"] is None or s["kutu"] is None:
                    continue
                k["maddeler"].append(madde("SFP_KIRILIM", 0.5, "olay", anahtar="SFP_KIRILIM"))
                k["giris"] = s["kutu"]
                k["giris_alt"], k["giris_ust"] = s["kutu"] - 0.1 * a, s["kutu"] + 0.1 * a
                r = None
                for j in range(s["kirilim_i"] + 1, min(N, s["kirilim_i"] + RETEST_MAX_MUM + 1)):
                    if m[j]["kapanis"] < s["uc"]:
                        break
                    if m[j]["dusuk"] <= s["kutu"] + MITIGATION_RETEST_TOLERANS_ATR * atrs[j]:
                        r = j
                        break
                if r is None:
                    k["asama"] = "retest_bekliyor" if N - 1 - s["kirilim_i"] < RETEST_MAX_MUM else "kacti"
                    k["tetik_i"] = s["kirilim_i"]
                else:
                    k["asama"], k["tetik_i"] = "sinyal", r
                _, tepe = _max_yuksek(m, s["i"], k["tetik_i"])
                k["bacak"] = (s["uc"], tepe)
            if not ters_trend_izni(ctx, k, onemli_sfp=s["onemli"]):
                k["asama"] = "izleme"
                k["notlar"].append("trende ters SFP sıradan seviyede (izleme)")
            kurulum_tamamla(ctx, k)
            if mod == "SFP_AGRESIF" and k["rr"] and k["rr"][0] < MIN_RR and "SFP_KIRILIM" in modlar:
                continue  # agresif R/R yetersiz -> sadece kırılım girişi raporlanır
            sonuc.append(k)

    # --- Mitigation ---
    for p in mitigation_bul(m, atrs, ltf["ic"], ctx["ltf_sfp"]):
        if p["kirilim_i"] < N - 60:
            continue
        a = atrs[p["kirilim_i"]]

        def mitigation_kur(stop_ref, sfp_stop):
            k = yeni_kurulum(ctx, "MITIGATION", ltf["dilim"], anahtar_dt=zaman_yaz(dts[p["h1"]["i"]]))
            k["giris"] = p["h1"]["fiyat"]
            k["giris_alt"], k["giris_ust"] = p["h1"]["fiyat"] - 0.1 * a, p["h1"]["fiyat"] + 0.1 * a
            k["stop_ref"] = stop_ref
            _, tepe = _max_yuksek(m, p["kirilim_i"], p["retest_i"] or N - 1)
            k["bacak"] = (p["hl"]["fiyat"], tepe)
            k["maddeler"] = [madde("MITIGATION", 1, "olay", anahtar="LTF_ONAY")]
            if p["sfp"]:
                k["maddeler"].append(madde("SFP+MITIGATION", 0.5, "olay", anahtar="SFP_MIT"))
                if sfp_stop:
                    k["notlar"].append("stop SFP dibinin ötesinde")
            if p["iptal_i"] is not None:
                k["asama"], k["tetik_i"] = "iptal", p["iptal_i"]
            elif p["retest_i"] is None:
                k["asama"] = "retest_bekliyor" if N - 1 - p["kirilim_i"] < RETEST_MAX_MUM else "kacti"
                k["tetik_i"] = p["kirilim_i"]
            else:
                k["asama"], k["tetik_i"] = "sinyal", p["retest_i"]
            if not kondisyon_var(ctx, k["giris_alt"], k["giris_ust"]):
                k["notlar"].append("kondisyon yok (S/R flip, EQ, OB/IMB, S&D, anahtar seviye)")
                if k["asama"] == "sinyal":
                    k["asama"] = "izleme"
            if not ters_trend_izni(ctx, k):
                k["asama"] = "izleme" if k["asama"] == "sinyal" else k["asama"]
                k["notlar"].append("büyük trendin micro yapısında mitigation (izleme)")
            ltf_maddeleri(ctx, k)
            return kurulum_tamamla(ctx, k)

        # Stop: başarısız swing'in ötesi; SFP varsa ve R/R izin veriyorsa SFP dibinin ötesi
        k = None
        if p["sfp"] and p["l1"]["fiyat"] < p["hl"]["fiyat"]:
            k = mitigation_kur(p["l1"]["fiyat"], True)
            if not k["rr"] or k["rr"][0] < MIN_RR:
                k = None
        sonuc.append(k or mitigation_kur(p["hl"]["fiyat"], False))

    # --- Breaker (HTF ve LTF) ---
    for an in (htf, ltf):
        for z in an["breakers"]:
            if z["yon"] != "long" or z["retest_i"] is None or z["kaynak"] != "MSB":
                continue
            ti = z["retest_i"]
            if an is htf:
                ti = min(N - 1, indeks_bul(dts, kapanis_zamani(htf, ti)))
            if ti < N - 60:
                continue
            a = an["atrs"][z["retest_i"]]
            k = yeni_kurulum(ctx, "BREAKER", an["dilim"], anahtar_dt=zaman_yaz(an["dts"][z["bas_i"]]) + an["dilim"])
            k["giris"] = z["giris"]
            k["giris_alt"], k["giris_ust"] = z["alt"], z["ust"]
            k["stop_ref"] = z["stop_ref"]  # MSB öncesi son swing (mutlaka)
            k["asama"], k["tetik_i"] = "sinyal", ti
            k["bacak"] = (z["stop_ref"], max(x["yuksek"] for x in an["m"][z["msb_i"]:z["retest_i"] + 1]))
            p = 1 if z["retest_tip"] == "tam" else 0.5
            if an["dilim"] in BREAKER_ZAMAN_DILIMLERI:
                p += 0.5
            k["maddeler"] = [madde("BREAKER(%s)" % an["dilim"], p, "bolge", z["alt"], z["ust"], "BREAKER"),
                             madde("MSB" if z["yapi_tipi"] == "BREAKER" else "MSB/MITIGATION", 1.5, "olay",
                                   anahtar="%s_MSB" % an["dilim"])]
            kond = kondisyon_var(ctx, z["alt"], z["ust"])
            if not ters_trend_izni(ctx, k, msb=(an is htf)):
                k["asama"] = "izleme"
                k["notlar"].append("ana trende ters LTF breaker (izleme)")
            if not kond:
                k["asama"] = "izleme"
                k["notlar"].append("kondisyon yok: breaker tek başına sinyal değildir")
            else:
                r = aktif_range(an) or aktif_range(htf)
                sr_ok = any(sr["flip"] == "teyitli" and ortust(sr["alt"], sr["ust"], z["alt"], z["ust"], 0.3 * a)
                            for sr in an["srs"] + htf["srs"])
                if sr_ok and r and z["alt"] - 0.3 * a <= r["eq"] <= z["ust"] + 0.3 * a:
                    k["maddeler"].append(madde("ALTIN_KURULUM", 1, grup="ALTIN"))
            ltf_maddeleri(ctx, k)
            sonuc.append(kurulum_tamamla(ctx, k))

    # --- Power of 3 ---
    for p in po3_tara(m, atrs, ltf["rangeler"], ltf["ic"], ltf["obs"]):
        if p["asama"] < 3 or p.get("manip_i", 0) < N - 150:
            continue
        a = atrs[-1]
        k = yeni_kurulum(ctx, "PO3", ltf["dilim"], anahtar_dt=zaman_yaz(dts[p["manip_i"]]), po3_asama=str(p["asama"]))
        k["notlar"] = list(p["notlar"])
        k["stop_ref"] = p.get("hl", p["manip_dip"])
        if p.get("ote"):
            o_alt, o_ust, o_oneri = p["ote"]
            if p.get("ob"):
                k["giris"] = p["ob"]["giris"]
            else:
                k["giris"] = max(p["rh"], o_oneri)
            k["giris_alt"], k["giris_ust"] = min(o_alt, k["giris"]), max(p["rh"], o_ust, k["giris"])
            k["bacak"] = (p["manip_dip"], p["dagitim_tepe"])
            k["ote_seviye"] = "OTE0.705"
        else:
            k["giris"] = p["rh"]
            k["giris_alt"], k["giris_ust"] = p["eq"], p["rh"]
        k["yapisal_hedefler"] = [(p["nihai_hedef"], "PO3_nihai")]
        k["maddeler"] = [madde("PO3", 1.5 if p["asama"] == 5 else 0, "olay", anahtar="PO3")]
        if p["durum"] == "iptal":
            k["asama"], k["tetik_i"] = "iptal", p.get("iptal_i")
            k["notlar"].append("son HL altında kapanış")
        elif p["asama"] == 5:
            k["asama"], k["tetik_i"] = "sinyal", p["retest_i"]
        else:
            k["asama"] = "izleme"
            k["tetik_i"] = p.get("kirilim_i") or N - 1
            k["notlar"].append("PO3 aşama %d" % p["asama"])
        if p["asama"] >= 4 or p["durum"] == "iptal":
            kurulum_tamamla(ctx, k)
        sonuc.append(k)

    # --- Quasimodo ---
    for p in qm_bul(m, atrs, ltf["ana"]):
        if p["kirilim_i"] < N - 80:
            continue
        a = atrs[p["kirilim_i"]]
        k = yeni_kurulum(ctx, "QM", ltf["dilim"], anahtar_dt=zaman_yaz(dts[p["ll1"]["i"]]))
        k["giris"] = p["ll1"]["fiyat"]
        k["giris_alt"], k["giris_ust"] = p["ll1"]["fiyat"] - QM_OMUZ_TOLERANS_ATR * a, p["ll1"]["fiyat"] + QM_OMUZ_TOLERANS_ATR * a
        k["stop_ref"] = p["ll2"]["fiyat"]  # pain level
        k["bacak"] = (p["ll2"]["fiyat"], p["tepe"])
        k["maddeler"] = [madde("QM", 1, "olay", anahtar="QM")]
        k["notlar"].append("ikinci giriş: breaker bloğu %s-%s" % (yuvarla(p["breaker_bolge"][0]), yuvarla(p["breaker_bolge"][1]))
                           if not ctx["ayna"] else "ikinci giriş: breaker bloğu")
        onay4 = 0
        if any(o["tip"] == "MSB" and o["yon"] == "bull" and abs(o["i"] - p["kirilim_i"]) <= 1 for o in ltf["yapi"]["olaylar"]):
            onay4 += 1
        if any(abs(r["rl"] - p["ll1"]["fiyat"]) <= 0.5 * a for r in ltf["rangeler"]):
            onay4 += 1
        if any(ortust(o["alt"], o["ust"], k["giris_alt"], k["giris_ust"]) for o in ltf["obs"] + ltf["imbs"] if o["yon"] == "long"):
            onay4 += 1
        if any(k["giris_alt"] <= s["seviye"] <= k["giris_ust"] for s in ctx["anahtar"]):
            onay4 += 1
        if onay4 == 4:
            k["maddeler"].append(madde("QM_TAM", 0.5, "olay", anahtar="QM_TAM"))
        if p["ote"]:
            k["ote_seviye"] = "OTE(sol omuz)"
        if p["iptal_i"] is not None:
            k["asama"], k["tetik_i"] = "iptal", p["iptal_i"]
            k["notlar"].append("baş (pain level) ötesinde kapanış")
        elif p["retest_i"] is None:
            k["asama"] = "retest_bekliyor" if N - 1 - p["kirilim_i"] < QM_MAX_MUM else "kacti"
            k["tetik_i"] = p["kirilim_i"]
        else:
            k["asama"], k["tetik_i"] = "sinyal", p["retest_i"]
        sonuc.append(kurulum_tamamla(ctx, k))

    # --- Inducement ---
    for p in inducement_bul(m, atrs, ltf["ic"], ctx["ltf_sfp"], ltf["imbs"]):
        if p["msb_i"] < N - 80:
            continue
        g = p["gap"]
        k = yeni_kurulum(ctx, "INDUCEMENT", ltf["dilim"], anahtar_dt=zaman_yaz(dts[p["sfp"]["i"]]))
        k["giris"] = g["giris"]
        k["giris_alt"], k["giris_ust"] = g["alt"], g["ust"]
        k["stop_ref"] = p["sfp"]["uc"]
        _, tepe = _max_yuksek(m, p["msb_i"], N - 1)
        k["bacak"] = (p["sfp"]["uc"], tepe)
        k["maddeler"] = [madde("INDUCEMENT", 1, "olay", anahtar="IND")]
        k["notlar"] = list(p["notlar"])
        if p["iptal_i"] is not None:
            k["asama"], k["tetik_i"] = "iptal", p["iptal_i"]
        elif p["giris_i"] is not None:
            k["maddeler"].append(madde("IND_supurme_sonrasi", 0.5, "olay", anahtar="IND_S"))
            k["asama"], k["tetik_i"] = "sinyal", p["giris_i"]
        else:
            k["asama"] = "izleme"
            k["tetik_i"] = p["msb_i"]
            if not p["notlar"]:
                k["notlar"].append("inducement swing süpürülmesi / gap'e dönüş bekleniyor")
        sonuc.append(kurulum_tamamla(ctx, k))

    # --- Reversal Fractal (sadece HTF POI içinde) ---
    for p in reversal_fractal_bul(m, atrs, ltf["ic"], [{"alt": q["alt"], "ust": q["ust"]} for q in pois]):
        if p["msb_i"] < N - 80:
            continue
        k = yeni_kurulum(ctx, "REVERSAL_FRACTAL", ltf["dilim"], anahtar_dt=zaman_yaz(dts[p["supurme_i"]]),
                         poi=(p["poi"]["alt"], p["poi"]["ust"]))
        k["giris"] = p["ust"]
        k["giris_alt"], k["giris_ust"] = p["alt"], p["ust"]
        k["stop_ref"] = p["supurme_dip"]
        _, tepe = _max_yuksek(m, p["msb_i"], N - 1)
        k["bacak"] = (p["supurme_dip"], tepe)
        k["maddeler"] = [madde("REVERSAL_FRACTAL", 1 if p["renk"] else 0.5, "olay", anahtar="RF")]
        if p["engulfing"]:
            k["maddeler"].append(madde("engulfing", 0.25, "olay", anahtar="RF_ENG"))
        if p["zayifladi"]:
            k["notlar"].append("zayıfladı: son yeşil mumun altında kapanış")
        if p["iptal_i"] is not None:
            k["asama"], k["tetik_i"] = "iptal", p["iptal_i"]
        elif p["giris_i"] is not None:
            k["asama"], k["tetik_i"] = "sinyal", p["giris_i"]
        else:
            k["asama"] = "retest_bekliyor" if N - 1 - p["msb_i"] < RETEST_MAX_MUM else "kacti"
            k["tetik_i"] = p["msb_i"]
        sonuc.append(kurulum_tamamla(ctx, k))
    return sonuc


def giris_durumu(ctx, k):
    """Canlı kontrol (long çerçeve, 1h ham veri, kapanmamış mum dahil):
    giriş doldu mu, stop/TP1 görüldü mü, güncel fiyattan R/R ne?"""
    m = ctx.get("m1h_ham") or []
    if not m or not k["tps"] or k.get("stop") is None or k.get("tetik_i") is None:
        return None
    tp1 = k["tps"][0][0]
    t0 = ctx["ltf"]["dts"][k["tetik_i"]]
    bas = indeks_bul([x["dt"] for x in m], t0)
    dolum = None
    for j in range(bas, len(m)):
        x = m[j]
        if dolum is None:
            if x["dusuk"] <= k["giris"]:
                dolum = j
            elif x["yuksek"] >= tp1:
                return {"durum": "hedef_girissiz", "zaman": zaman_yaz(x["dt"])}
            else:
                continue
        if x["dusuk"] <= k["stop"]:
            return {"durum": "stop", "zaman": zaman_yaz(x["dt"])}
        if j > dolum and x["yuksek"] >= tp1:
            return {"durum": "tp1", "zaman": zaman_yaz(x["dt"])}
    # Yapı kontrolü (onay dilimi, kapanmış mumlar): stop referansının ötesinde kapanış veya
    # tetikten sonra ters yönde CHoCH/MSB -> fikir geçersiz, hedefler iptal edilmiş hedef
    ltf = ctx["ltf"]
    for j in range(k["tetik_i"] + 1, len(ltf["m"])):
        if ltf["m"][j]["kapanis"] < k["stop_ref"]:
            return {"durum": "yapi_bozuldu", "zaman": zaman_yaz(ltf["dts"][j])}
    ters = next((o for o in ltf["olaylar"] if o["yon"] == "bear" and o["tip"] in ("CHOCH", "MSB")
                 and o["i"] > k["tetik_i"]), None)
    if ters is not None:
        return {"durum": "ters_yapi", "zaman": zaman_yaz(ltf["dts"][ters["i"]]), "olay": ters["tip"]}
    p = m[-1]["kapanis"]
    sonuc = {"fiyat": p, "fiyat_zaman": zaman_yaz(m[-1]["dt"]),
             "dolum": zaman_yaz(m[dolum]["dt"]) if dolum is not None else None}
    if dolum is None:
        sonuc["uzaklik_r"] = round((p - k["giris"]) / (k["giris"] - k["stop"]), 2)
        sonuc["durum"] = "limit" if sonuc["uzaklik_r"] <= LIMIT_MAX_UZAKLIK_R else "limit_uzak"
    else:
        sonuc["guncel_rr"] = round((tp1 - p) / (p - k["stop"]), 2) if p > k["stop"] else 0.0
        sonuc["durum"] = "aktif" if sonuc["guncel_rr"] >= MIN_RR else "kacti"
    return sonuc


def cerceve_tara(ctx):
    """Bir eşleşme + yön (çerçeve) için tüm kurulumlar."""
    ltf, htf = ctx["ltf"], ctx["htf"]
    onemli = [s["fiyat"] for s in htf["ana"] if s["tip"] == "L"]
    for an in (ltf, htf):
        for r in an["rangeler"]:
            onemli.append(r["rl"])
        onemli += [h["seviye"] for h in an["havuzlar"] if h["yon"] == "L" and h["tip"] != "tekil"]
    ctx["ltf_sfp"] = sfp_bul(ltf["m"], ltf["atrs"], ltf["ic"], onemli, ltf["ic"])
    pois = poi_bul(ctx)
    kurulumlar = []
    for poi in pois:
        kurulumlar.append(poi_motoru(ctx, poi))
    kurulumlar += desen_kurulumlari(ctx, pois)
    N = len(ltf["m"])
    for k in kurulumlar:
        k["zaman"] = zaman_yaz(ltf["dts"][k["tetik_i"]]) if k.get("tetik_i") is not None and k["tetik_i"] < N else ""
        # Tazelik: tetik son SINYAL_TAZELIK_MUM mum ve SINYAL_MAX_YAS_SAAT içinde olmalı;
        # ardından canlı fiyatla giriş kontrolü (doldu mu / kaçtı mı / stop-TP1 görüldü mü)
        if k["asama"] == "sinyal":
            k["sonuc"], _ = sonuc_degerlendir(ltf["m"], k["tetik_i"], k) if k.get("stop") else ("?", None)
            yas = 0.0
            if ctx.get("simdi"):
                yas = (ctx["simdi"] - kapanis_zamani(ltf, k["tetik_i"])).total_seconds() / 3600.0
            gec = k["tetik_i"] < N - 1 - SINYAL_TAZELIK_MUM or yas > SINYAL_MAX_YAS_SAAT
            if k["sonuc"] not in ("açık", "dolmadı") or k["tetik_i"] < N - 1 - RETEST_MAX_MUM:
                k["asama"] = "eski"
                continue
            gd = giris_durumu(ctx, k)
            k["giris_durum"] = gd
            if gd is None:
                if gec:
                    k["asama"] = "eski"
                continue
            if gd["durum"] in ("stop", "tp1"):
                k["asama"] = "eski"
            elif gd["durum"] in ("yapi_bozuldu", "ters_yapi"):
                k["asama"] = "iptal"
            elif gd["durum"] in ("hedef_girissiz", "kacti", "limit_uzak"):
                k["asama"] = "kacti"
            elif gec:
                # Geç kalmış ama girişi hâlâ geçerli: yeni sinyal yazılmaz, izleme listesinde gösterilir
                k["asama"] = "izleme"
                k["gec_saat"] = round(yas, 1)
        elif k["asama"] in ("izleme", "iptal", "kacti") and (k.get("tetik_i") is None or k["tetik_i"] < N - 1 - RETEST_MAX_MUM):
            k["asama"] = "eski_" + k["asama"]  # raporlanmaz (yalnızca istatistik)
    return kurulumlar, pois


# =============================================================================
#                        AYNA ÇERÇEVEDEN GERİ ÇEVİRME
# =============================================================================

TIP_AYNA = {"DBR": "RBD", "RBD": "DBR", "RBR": "DBD", "DBD": "RBR"}


def _ters(x):
    return None if x is None else -x


def kurulum_geri_cevir(k):
    """Ayna çerçevede bulunan (short) kurulumun fiyatlarını gerçek eksene çevirir."""
    if not k["ayna"]:
        k["yon"] = "LONG"
        giris_notu_ekle(k)
        return k
    k["yon"] = "SHORT"
    gd = k.get("giris_durum")
    if gd and gd.get("fiyat") is not None:
        gd["fiyat"] = -gd["fiyat"]
    k["giris"], k["stop_ref"], k["stop"] = _ters(k["giris"]), _ters(k["stop_ref"]), _ters(k["stop"])
    if k["giris_alt"] is not None:
        k["giris_alt"], k["giris_ust"] = -k["giris_ust"], -k["giris_alt"]
    if k.get("poi"):
        k["poi"] = (-k["poi"][1], -k["poi"][0])
    k["tps"] = [(-p, e) for p, e in k["tps"]]
    for x in k["maddeler"]:
        for eski, yeni in TIP_AYNA.items():
            if x["ad"] == "SD:" + eski:
                x["ad"] = "SD:" + yeni
                break
    giris_notu_ekle(k)
    return k


def giris_notu_ekle(k):
    """Canlı giriş durumunu (gerçek fiyatlarla) nota yazar."""
    gd = k.get("giris_durum")
    if not gd:
        return
    ref = k.get("giris")
    d = gd["durum"]
    if d == "limit":
        k["giris_etiketi"] = "LİMİT"
        k["notlar"].insert(0, "GİRİŞ DOLMADI: limit emir; güncel fiyat %s (%s UTC), girişten %+.2fR" % (
            yuvarla(gd["fiyat"], ref), gd["fiyat_zaman"], gd["uzaklik_r"]))
    elif d == "aktif":
        k["giris_etiketi"] = "AKTİF"
        k["notlar"].insert(0, "GİRİŞ DOLDU (%s UTC); güncel fiyat %s, güncel fiyattan R/R %s" % (
            gd["dolum"], yuvarla(gd["fiyat"], ref), gd["guncel_rr"]))
    elif d == "kacti":
        k["notlar"].insert(0, "GİRİŞ KAÇTI: doldu (%s UTC) ama güncel fiyat %s, güncel R/R %s < %s; fiyat girişe dönerse geçerli" % (
            gd["dolum"], yuvarla(gd["fiyat"], ref), gd["guncel_rr"], MIN_RR))
    elif d == "yapi_bozuldu":
        k["notlar"].insert(0, "İPTAL: %s UTC mumu stop referansının (yapı seviyesi) ötesinde kapandı; fiyat girişe yakın olsa da fikir geçersiz" % gd["zaman"])
    elif d == "ters_yapi":
        k["notlar"].insert(0, "İPTAL: tetikten sonra ters yönde %s (%s UTC); hedefler 'iptal edilmiş hedef', yeni giriş yok" % (gd["olay"], gd["zaman"]))
    elif d == "limit_uzak":
        k["notlar"].insert(0, "KAÇTI: giriş dolmadı, fiyat girişten %+.2fR uzaklaştı (> LIMIT_MAX_UZAKLIK_R=%s); güncel fiyat %s" % (
            gd["uzaklik_r"], LIMIT_MAX_UZAKLIK_R, yuvarla(gd["fiyat"], ref)))
    elif d == "hedef_girissiz":
        k["notlar"].insert(0, "KAÇTI: giriş gelmeden fiyat TP1'e ulaştı (%s UTC)" % gd["zaman"])
    if k.get("gec_saat") is not None:
        k["notlar"].insert(0, "GEÇ SİNYAL: tetik mumu %s saat önce kapandı (SINYAL_MAX_YAS_SAAT=%s); yeni sinyal olarak yazılmadı" % (
            k["gec_saat"], SINYAL_MAX_YAS_SAAT))


def konsept_etiketi(k):
    """CSV konsept etiketi, ';' ile ayrılmış."""
    parcalar = []
    for x in k["maddeler"]:
        if x["puan"] > 0 and x["ad"] not in parcalar:
            parcalar.append(x["ad"])
    if k["tps"]:
        parcalar.append("LIK:" + k["tps"][0][1])
    return ";".join(parcalar)


def kurulum_id(k):
    bolge = "%s-%s" % (yuvarla(k["poi"][0]), yuvarla(k["poi"][1])) if k.get("poi") else ""
    return "|".join([k["sembol"], k["eslesme"], k["tip"], k["yon"], k.get("dilim", ""), k.get("anahtar_dt", ""), bolge])


def kurulum_kayit(k):
    """JSON'a yazılabilir özet."""
    ref = k["giris"] if k.get("giris") is not None else None
    return {"id": kurulum_id(k), "sembol": k["sembol"], "eslesme": k["eslesme"], "tip": k["tip"],
            "yon": k["yon"], "asama": k["asama"], "zaman": k.get("zaman", ""), "temas_no": k.get("temas_no", 1),
            "poi": [yuvarla(x, ref) for x in k["poi"]] if k.get("poi") else None,
            "giris_bolge": [yuvarla(k["giris_alt"], ref), yuvarla(k["giris_ust"], ref)] if k.get("giris_alt") is not None else None,
            "giris": yuvarla(k.get("giris"), ref), "stop_ref": yuvarla(k.get("stop_ref"), ref),
            "stop": yuvarla(k.get("stop"), ref), "tps": [yuvarla(p, ref) for p, _ in k.get("tps", [])],
            "skor": k.get("skor", 0), "ham_puan": k.get("ham_puan", 0), "notlar": k.get("notlar", []),
            "po3_asama": k.get("po3_asama", "")}


# =============================================================================
#                          İSTATİSTİK (BACKTEST) MODÜLÜ
# =============================================================================
# Ek API isteği yapmaz; zaten çekilmiş mumlar üzerinde çalışır.

def bolge_testi_kontrol(mumlar, bas, yon, giris, stop, hedef_r=None, max_mum=None):
    """Fiyat bölgeye döndü mü; döndükten sonra stop'a değmeden hedef_r kadar yol
    aldı mı; kaç mumda? Dönüş: (dondu, basarili, mum_sayisi)."""
    hedef_r = hedef_r or ISTATISTIK_HEDEF_R
    max_mum = max_mum or ISTATISTIK_MAX_MUM
    N = len(mumlar)
    risk = (giris - stop) if yon == "long" else (stop - giris)
    if risk <= 0:
        return False, False, None
    hedef = giris + hedef_r * risk if yon == "long" else giris - hedef_r * risk
    for j in range(bas, N):
        m = mumlar[j]
        if (yon == "long" and m["dusuk"] <= giris) or (yon == "short" and m["yuksek"] >= giris):
            for k in range(j, min(N, j + max_mum)):
                x = mumlar[k]
                if (yon == "long" and x["dusuk"] <= stop) or (yon == "short" and x["yuksek"] >= stop):
                    return True, False, k - j
                if k > j and ((yon == "long" and x["yuksek"] >= hedef) or (yon == "short" and x["dusuk"] <= hedef)):
                    return True, True, k - j
            return True, False, None
    return False, False, None


class IstatistikToplayici:
    def __init__(self):
        self.veri = {}

    def ekle(self, sembol, dilim, konsept, kategori, sonuc):
        anahtar = (sembol, dilim, konsept, kategori)
        d = self.veri.setdefault(anahtar, [0, 0, 0])
        d[0] += 1
        if sonuc[0]:
            d[1] += 1
        if sonuc[1]:
            d[2] += 1

    def satirlar(self, tarih):
        sonuc = []
        for (sembol, dilim, konsept, kategori), (n, dondu, basarili) in sorted(self.veri.items()):
            sonuc.append({"tarih": tarih, "sembol": sembol, "zaman_dilimi": dilim, "konsept": konsept,
                          "kategori_mod": kategori, "donus_orani": round(dondu / n, 3) if n else 0,
                          "basari_orani": round(basarili / dondu, 3) if dondu else 0, "ornek_sayisi": n})
        return sonuc

    def en_iyi(self, sembol, dilim, konsept, onek):
        """Örnek >= OTOMATIK_MIN_ORNEK olan en başarılı mod."""
        en, en_oran = None, -1
        for (s, d, k, kat), (n, dondu, bas) in self.veri.items():
            if s == sembol and d == dilim and k == konsept and kat.startswith(onek) and n >= OTOMATIK_MIN_ORNEK and dondu:
                if bas / dondu > en_oran:
                    en, en_oran = kat[len(onek):], bas / dondu
        return en

    def zayif_konseptler(self, sembol, dilim):
        """Başarı oranı OTOMATIK_MIN_BASARI altındaki konseptler -> puan 0."""
        toplam = {}
        for (s, d, k, kat), (n, dondu, bas) in self.veri.items():
            if s == sembol and d == dilim and kat == "tümü":
                toplam[k] = (n, dondu, bas)
        return {k: 0.0 for k, (n, dondu, bas) in toplam.items()
                if n >= OTOMATIK_MIN_ORNEK and dondu and bas / dondu < OTOMATIK_MIN_BASARI}


def istatistik_hesapla(top, sembol, an, an_ayna, gecmis_kurulumlar):
    """Konsept başına geçmiş örnekler: dönüş oranı, 2R başarı oranı."""
    m, atrs, dilim = an["m"], an["atrs"], an["dilim"]
    tampon = STOP_TAMPON_ATR
    htf_mi = "HTF" if DILIM_DAKIKA[dilim] >= 240 else "LTF"
    # --- OB: 4 bölge modu ---
    for mod in ("son_mum_govde", "son_mum_fitil", "grup_govde", "grup_fitil"):
        obs = an["obs"] if mod == OB_BOLGE_MODU else ob_bul(m, atrs, an["olaylar"], an["ic"], an["havuzlar"], mod)
        for z in obs:
            stop = z["stop_ref"] - tampon * atrs[z["k"]] if z["yon"] == "long" else z["stop_ref"] + tampon * atrs[z["k"]]
            s = bolge_testi_kontrol(m, z["k"] + 2, z["yon"], z["giris"], stop)
            top.ekle(sembol, dilim, "OB", "mod=" + mod, s)
            if mod != OB_BOLGE_MODU:
                continue
            top.ekle(sembol, dilim, "OB", "tümü", s)
            top.ekle(sembol, dilim, "OB", "swing" if z["swingde"] else "swing_dışı", s)
            trend = an["yapi"]["trend_dizi"][z["k"]]
            uyum = (trend == "bull" and z["yon"] == "long") or (trend == "bear" and z["yon"] == "short")
            top.ekle(sembol, dilim, "OB", "trend_yönü" if uyum else "trend_ters", s)
            top.ekle(sembol, dilim, "OB", "likidite_riskli" if z["likidite_riski"] else "likidite_risksiz", s)
            top.ekle(sembol, dilim, "OB", htf_mi, s)
    # --- Imbalance ---
    for z in an["imbs"]:
        i = z["i"]
        if z["yon"] == "long":
            stop = min(m[j]["dusuk"] for j in range(max(0, i - 1), min(len(m), i + 2))) - tampon * atrs[i]
        else:
            stop = max(m[j]["yuksek"] for j in range(max(0, i - 1), min(len(m), i + 2))) + tampon * atrs[i]
        s = bolge_testi_kontrol(m, i + 2, z["yon"], z["giris"], stop)
        top.ekle(sembol, dilim, "IMB", "tümü", s)
        top.ekle(sembol, dilim, "IMB", "zayıf" if z["zayif"] else "normal", s)
        if any(o["yon"] == z["yon"] and ortust(o["alt"], o["ust"], z["alt"], z["ust"]) for o in an["obs"]):
            top.ekle(sembol, dilim, "IMB", "OB_çakışmalı", s)
        if any(ortust(r["alt"], r["ust"], z["alt"], z["ust"]) for r in an["srs"]):
            top.ekle(sembol, dilim, "IMB", "SR_çakışmalı", s)
        if any(ortust(g["alt"], g["ust"], z["alt"], z["ust"]) for g in an["gaps"]):
            top.ekle(sembol, dilim, "IMB", "GAP_çakışmalı", s)
        if z["on_tepki_i"] is not None:
            tam = z["dolum_i"] is not None
            top.ekle(sembol, dilim, "IMB", "tam_temas" if tam else "ön_tepki", (True, s[1] if tam else False))
    # --- Breaker: 3 bölge modu ---
    for mod in ("govde", "son_fitil", "cizgi"):
        bl = an["breakers"] if mod == BREAKER_BOLGE_MODU else breaker_bul(m, atrs, an["yapi"], an["sd"], mod)
        for z in bl:
            a = atrs[z["msb_i"]]
            stop = z["stop_ref"] - tampon * a if z["yon"] == "long" else z["stop_ref"] + tampon * a
            s = bolge_testi_kontrol(m, z["msb_i"] + 1, z["yon"], z["giris"], stop)
            top.ekle(sembol, dilim, "BREAKER", "mod=" + mod, s)
            if mod != BREAKER_BOLGE_MODU:
                continue
            top.ekle(sembol, dilim, "BREAKER", "tümü", s)
            if z["retest_tip"]:
                top.ekle(sembol, dilim, "BREAKER", z["retest_tip"] + "_retest", s)
            kond = any(ortust(x["alt"], x["ust"], z["alt"], z["ust"], 0.3 * a) for x in an["srs"] + an["obs"] + an["imbs"] + an["sd"]
                       if x is not z)
            top.ekle(sembol, dilim, "BREAKER", "kondisyonlu" if kond else "kondisyonsuz", s)
    # --- S&D ---
    for z in an["sd"]:
        a = atrs[z["olusum_i"]]
        stop = z["stop_ref"] - tampon * a if z["yon"] == "long" else z["stop_ref"] + tampon * a
        s = bolge_testi_kontrol(m, z["olusum_i"] + 1, z["yon"], z["giris"], stop)
        top.ekle(sembol, dilim, "SD", "tümü", s)
        top.ekle(sembol, dilim, "SD", z["tip"], s)
        if z.get("tepki_derinlik"):
            top.ekle(sembol, dilim, "SD", "tepki=" + z["tepki_derinlik"][0], s)
        top.ekle(sembol, dilim, "SD", "base_içi_SFP_var" if z.get("ic_sfp") else "base_içi_SFP_yok", s)
    # --- Mitigation ve Reversal Fractal (iki yön: normal + ayna) ---
    for cer in (an, an_ayna):
        if cer is None:
            continue
        mm, aa = cer["m"], cer["atrs"]
        sfplar = sfp_bul(mm, aa, cer["ic"], [], cer["ic"])
        for p in mitigation_bul(mm, aa, cer["ic"], sfplar):
            if p["retest_i"] is None:
                continue
            stop = p["hl"]["fiyat"] - tampon * aa[p["kirilim_i"]]
            s = bolge_testi_kontrol(mm, p["retest_i"], "long", p["h1"]["fiyat"], stop)
            top.ekle(sembol, dilim, "MITIGATION", "tümü", s)
            top.ekle(sembol, dilim, "MITIGATION", "SFP'li" if p["sfp"] else "SFP'siz", s)
        poiler = [z for z in cer["sd"] if z["yon"] == "long"]
        for renk in (True, False):
            for p in reversal_fractal_bul(mm, aa, cer["ic"], poiler, renk_kurali=renk):
                stop = p["supurme_dip"] - tampon * aa[p["supurme_i"]]
                s = bolge_testi_kontrol(mm, p["msb_i"] + 1, "long", p["ust"], stop)
                top.ekle(sembol, dilim, "REVERSAL_FRACTAL", "renk_kuralı_" + ("açık" if renk else "kapalı"), s)
    # --- Likidite ---
    for h in an["havuzlar"]:
        alindi = h["durum"] != "açık"
        donus = False
        if h["supurme_i"] is not None:
            j0 = h["supurme_i"]
            a = atrs[j0]
            for j in range(j0 + 1, min(len(m), j0 + 11)):
                if (h["yon"] == "H" and m[j]["kapanis"] < h["seviye"] - a) or (h["yon"] == "L" and m[j]["kapanis"] > h["seviye"] + a):
                    donus = True
                    break
            top.ekle(sembol, dilim, "LIKIDITE", "süpürme_sonrası_dönüş:" + h["tip"], (True, donus))
        top.ekle(sembol, dilim, "LIKIDITE", "alınma:" + h["tip"], (True, alindi))
    # --- TP ulaşma oranları (geçmiş kurulumlardan) ---
    for k in gecmis_kurulumlar:
        if k.get("sonuc") and k["sonuc"] not in ("açık", "?") and k.get("onay_dilim") == dilim:
            for n in (1, 2, 3):
                top.ekle(sembol, dilim, "LIKIDITE", "TP%d_ulaşma" % n, (True, k["sonuc"].startswith("tp") and int(k["sonuc"][2]) >= n))


# =============================================================================
#                          TARAMALAR ARASI HAFIZA
# =============================================================================

def hafiza_guncelle(hafiza, kurulumlar, taranan_semboller, simdi):
    """Bekleyen kurulumlar 'aktif'te tutulur; sinyal/iptal/kaçtı 'arsiv'e taşınır
    (silinmez). Taramada görülmeyen eski aktifler 7 gün sonra arşivlenir."""
    aktif = hafiza.setdefault("aktif", {})
    arsiv = hafiza.setdefault("arsiv", [])
    arsiv_idler = set((x.get("id"), x.get("asama")) for x in arsiv[-2000:])
    simdi_s = zaman_yaz(simdi)
    gorulen = set()
    for k in kurulumlar:
        if k["asama"] in ("eski", "poi_bekliyor") or k["asama"].startswith("eski_"):
            continue
        kid = kurulum_id(k)
        gorulen.add(kid)
        kayit = kurulum_kayit(k)
        if k["asama"] in ("sinyal", "iptal", "kacti"):
            if (kid, k["asama"]) not in arsiv_idler:
                kayit["arsiv_zamani"] = simdi_s
                arsiv.append(kayit)
                arsiv_idler.add((kid, k["asama"]))
            aktif.pop(kid, None)
        else:
            onceki = aktif.get(kid)
            if onceki and onceki.get("asama") == k["asama"]:
                kayit["asama_giris"] = onceki.get("asama_giris", simdi_s)
            else:
                kayit["asama_giris"] = simdi_s
            kayit["son_gorulme"] = simdi_s
            aktif[kid] = kayit
    for kid in list(aktif.keys()):
        kayit = aktif[kid]
        if kid in gorulen or kayit.get("sembol") not in taranan_semboller:
            continue
        try:
            son = datetime.datetime.strptime(kayit.get("son_gorulme", simdi_s), "%Y-%m-%d %H:%M")
        except ValueError:
            son = simdi
        if (simdi - son).days >= 7:
            kayit["asama"] = "iptal"
            kayit["notlar"] = kayit.get("notlar", []) + ["7 gündür görülmedi (veri dışı)"]
            kayit["arsiv_zamani"] = simdi_s
            arsiv.append(kayit)
            del aktif[kid]
    return hafiza


# =============================================================================
#                                  ÇIKTILAR
# =============================================================================

def csv_hazirla(yol, kolonlar):
    if not os.path.exists(yol):
        with open(yol, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(kolonlar)


def son_sinyaller(saat):
    """Son `saat` içinde yazılmış sinyaller (tekrar yazmayı önlemek için)."""
    sonuc = []
    if not os.path.exists(YOLLAR["sinyaller"]):
        return sonuc
    sinir = simdi_utc() - datetime.timedelta(hours=saat)
    try:
        with open(YOLLAR["sinyaller"], "r", encoding="utf-8") as f:
            for satir in csv.DictReader(f):
                try:
                    t = datetime.datetime.strptime(satir["tarih_saat_utc"], "%Y-%m-%d %H:%M")
                    if t >= sinir:
                        sonuc.append(satir)
                except (ValueError, KeyError, TypeError):
                    continue
    except Exception:
        uyari("sinyaller.csv okunamadı; tekrar kontrolü atlandı.")
    return sonuc


def tekrar_mi(k, onceki):
    for s in onceki:
        try:
            if s["sembol"] == k["sembol"] and s["yon"] == k["yon"] and \
               ortust(float(s["giris_alt"]), float(s["giris_ust"]), k["giris_alt"], k["giris_ust"]):
                return True
        except (ValueError, KeyError, TypeError):
            continue
    return False


def sinyal_satiri(k, simdi):
    ref = k["giris"]
    tps = [yuvarla(p, ref) for p, _ in k["tps"]] + [""] * (3 - len(k["tps"]))
    rr = list(k["rr"]) + [""] * (3 - len(k["rr"]))
    return {"tarih_saat_utc": zaman_yaz(simdi), "sembol": k["sembol"], "poi_zaman_dilimi": k["poi_dilim"],
            "onay_zaman_dilimi": k["onay_dilim"], "kurulum_tipi": k["tip"], "yon": k["yon"],
            "giris_alt": yuvarla(k["giris_alt"], ref), "giris_ust": yuvarla(k["giris_ust"], ref),
            "giris_oneri": yuvarla(k["giris"], ref), "stop": yuvarla(k["stop"], ref),
            "tp1": tps[0], "tp2": tps[1], "tp3": tps[2],
            "tp_etiketleri": "/".join(e for _, e in k["tps"]), "rr1": rr[0], "rr2": rr[1], "rr3": rr[2],
            "ham_puan": k["ham_puan"], "skor": k["skor"], "temas_no": k.get("temas_no", 1),
            "po3_asama": k.get("po3_asama", ""), "ote_seviye": k.get("ote_seviye", ""),
            "ob_zaman_dilimleri": ",".join(k.get("ob_dilimleri", [])), "konseptler": konsept_etiketi(k),
            "notlar": " | ".join(k["notlar"])}


def ekran_satiri(k):
    ref = k["giris"]
    tp = "/".join(str(yuvarla(p, ref)) for p, _ in k["tps"]) or "-"
    rr = "/".join(str(x) for x in k["rr"]) or "-"
    return "%s %s→%s %s skor %s%s%s | tetik %s UTC | giriş %s-%s (öneri %s) | SL %s | TP %s | R/R %s" % (
        k["sembol"], k["poi_dilim"], k["onay_dilim"], k["yon"], k["skor"],
        " [%s]" % k["tip"] if k["tip"] != "POI" else "",
        " [%s]" % k["giris_etiketi"] if k.get("giris_etiketi") else "", k.get("zaman", "?"), yuvarla(k["giris_alt"], ref), yuvarla(k["giris_ust"], ref), yuvarla(k["giris"], ref),
        yuvarla(k["stop"], ref), tp, rr)


def sinyalleri_yaz(sinyaller, simdi):
    csv_hazirla(YOLLAR["sinyaller"], SINYAL_KOLONLARI)
    onceki = son_sinyaller(TEKRAR_YAZMA_SAAT)
    yazilan = []
    with open(YOLLAR["sinyaller"], "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SINYAL_KOLONLARI)
        for k in sinyaller:
            if tekrar_mi(k, onceki):
                k["notlar"].append("son %d saatte zaten yazıldı" % TEKRAR_YAZMA_SAAT)
                continue
            satir = sinyal_satiri(k, simdi)
            w.writerow(satir)
            onceki.append(satir)
            yazilan.append(k)
    return yazilan


def istatistik_yaz(satirlar):
    csv_hazirla(YOLLAR["istatistik"], ISTATISTIK_KOLONLARI)
    with open(YOLLAR["istatistik"], "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ISTATISTIK_KOLONLARI)
        for s in satirlar:
            w.writerow(s)


YONETIM_NOTU = ("Yönetim: Stop'u erken girişe çekme. Stop, yapıyı bozacak seviyededir; oraya kadar "
                "yapı geçerlidir. TP1'de (hedef/karşı OB/POI'ye yaklaşıldığında) kısmi kâr al; kâr alındıktan "
                "sonra stop giriş seviyesine çekilebilir (DD PO3 notu).")


def kurulum_detay(k):
    ref = k["giris"]
    satirlar = [ekran_satiri(k)]
    satirlar.append("    Ham puan %s | Konseptler: %s" % (k["ham_puan"], konsept_etiketi(k)))
    if k["tps"]:
        satirlar.append("    TP etiketleri: %s" % " / ".join(e for _, e in k["tps"]))
    if k.get("poi"):
        satirlar.append("    POI: %s - %s | temas no: %s" % (yuvarla(k["poi"][0], ref), yuvarla(k["poi"][1], ref), k.get("temas_no", 1)))
    if k.get("po3_asama"):
        satirlar.append("    PO3 aşama: %s" % k["po3_asama"])
    if k["notlar"]:
        satirlar.append("    Notlar: " + " | ".join(k["notlar"]))
    return satirlar


def kisa_satir(k):
    ref = k["giris"] if k.get("giris") is not None else (k["poi"][0] if k.get("poi") else None)
    parca = ["%s %s→%s %s %s" % (k["sembol"], k["poi_dilim"], k["onay_dilim"], k["yon"], k["tip"])]
    if k.get("poi"):
        parca.append("POI %s-%s" % (yuvarla(k["poi"][0], ref), yuvarla(k["poi"][1], ref)))
    if k.get("giris") is not None and k.get("giris_alt") is not None:
        parca.append("bekleme bölgesi %s-%s" % (yuvarla(k["giris_alt"], ref), yuvarla(k["giris_ust"], ref)))
    if k.get("stop") is not None:
        parca.append("SL %s" % yuvarla(k["stop"], ref))
    if k.get("skor"):
        parca.append("skor %s" % k["skor"])
    if k.get("zaman"):
        parca.append(k["zaman"] + " UTC")
    if k["notlar"]:
        parca.append("; ".join(k["notlar"]))
    return " | ".join(parca)


def yapi_ozeti(sembol, analizler, anahtar):
    """Sinyal olmasa da sembol bazında yapı özeti."""
    satirlar = ["[%s]" % sembol]
    for d in ("1day", "4h", "1h"):
        an = analizler.get(d)
        if not an:
            continue
        y = an["yapi"]
        fiyat = an["m"][-1]["kapanis"]
        s = "  %s: trend %s" % (d, y["trend"])
        if y["son_olay"]:
            o = y["son_olay"]
            s += " | son %s %s @ %s (%s)" % (o["tip"], o["yon"], yuvarla(o["seviye"], fiyat), zaman_yaz(an["dts"][o["i"]]))
        if y["korunan"]:
            s += " | korunan seviye %s (kapanışla kırılırsa yapı döner)" % yuvarla(y["korunan"]["fiyat"], fiyat)
        satirlar.append(s)
        r = aktif_range(an)
        if r:
            satirlar.append("      %s RL %s / EQ %s / RH %s, konum %.2f (%s)" % ("Monday range" if r.get("tur") == "MONDAY" else "range",
                yuvarla(r["rl"], fiyat), yuvarla(r["eq"], fiyat), yuvarla(r["rh"], fiyat),
                range_konum(r, fiyat) or 0, r["durum"]))
        son = len(an["m"]) - 1
        ust = sorted([h for h in an["havuzlar"] if h["yon"] == "H" and havuz_durum_at(h, son) == "açık" and h["seviye"] > fiyat],
                     key=lambda h: h["seviye"])[:2]
        alt = sorted([h for h in an["havuzlar"] if h["yon"] == "L" and havuz_durum_at(h, son) == "açık" and h["seviye"] < fiyat],
                     key=lambda h: -h["seviye"])[:2]
        if ust or alt:
            satirlar.append("      likidite üst: %s | alt: %s" % (
                ", ".join("%s(%s)" % (yuvarla(h["seviye"], fiyat), h["tip"]) for h in ust) or "-",
                ", ".join("%s(%s)" % (yuvarla(h["seviye"], fiyat), h["tip"]) for h in alt) or "-"))
        acik = [z for z in an["imbs"] if imbalance_durum_at(z, son) in ("açık", "ön tepki")][-2:]
        if acik:
            satirlar.append("      açık imbalance: %s" % ", ".join(
                "%s %s-%s" % (z["yon"], yuvarla(z["alt"], fiyat), yuvarla(z["ust"], fiyat)) for z in acik))
        kirik = [z for z in an["sd"] if z.get("kirilim_istekli") and z["kirilim_i"] is not None and z["kirilim_i"] > son - 20]
        for z in kirik[-1:]:
            satirlar.append("      uyarı: %s bölgesi breakout mumuyla ihlal edildi; yapı değişebilir" %
                            ("supply" if z["yon"] == "short" else "demand"))
    if anahtar:
        fiyat = analizler["1day"]["m"][-1]["kapanis"] if analizler.get("1day") else None
        satirlar.append("  anahtar seviyeler: " + ", ".join("%s %s" % (s["ad"], yuvarla(s["seviye"], fiyat)) for s in anahtar))
    return satirlar


def rapor_yaz(simdi, bilgi, sinyaller, kurulumlar, ozetler, oto_ayarlar, yonetici, arsiv_uyarilari):
    os.makedirs(YOLLAR["raporlar"], exist_ok=True)
    yol = os.path.join(YOLLAR["raporlar"], "rapor_%s.txt" % simdi.strftime("%Y-%m-%d_%H-%M"))
    ek = 2
    while os.path.exists(yol):  # eski rapor asla ezilmez
        yol = os.path.join(YOLLAR["raporlar"], "rapor_%s_%d.txt" % (simdi.strftime("%Y-%m-%d_%H-%M"), ek))
        ek += 1
    s = []
    s.append("DD FINANCE PRICE ACTION TARAMA RAPORU")
    s.append("=" * 60)
    s.append("1) FELSEFE")
    s.append("  " + FELSEFE)
    s.append("  Eğitim amaçlıdır, yatırım tavsiyesi değildir. İşlem kararları kullanıcıya aittir.")
    s.append("")
    s.append("2) TARAMA BİLGİSİ")
    s.append("  Saat: %s UTC (tüm zamanlar UTC)" % zaman_yaz(simdi))
    s.append("  Taranan semboller: %s" % ", ".join(bilgi["taranan"]))
    s.append("  Kullanılan istek (bu tarama): %d | Bugün toplam: %d | Kalan: %d" % (
        yonetici.bu_tarama, yonetici.sayac["adet"], yonetici.kalan()))
    if bilgi["atlanan"]:
        s.append("  Atlanan/hatalı semboller:")
        for sem, neden in bilgi["atlanan"]:
            s.append("    - %s: %s" % (sem, neden))
    for h in yonetici.hatalar:
        s.append("    - API: %s" % h)
    for u in UYARILAR:
        s.append("    - uyarı: %s" % u)
    s.append("")
    s.append("3) YENİ SİNYALLER")
    if not sinyaller:
        s.append("  Yeni sinyal yok.")
    for k in sinyaller:
        s += ["  " + x for x in kurulum_detay(k)]
        s.append("    " + YONETIM_NOTU)
        s.append("")
    gruplar = [("4) ONAY BEKLEYENLER (fiyat POI'de, LTF kırılım bekleniyor)", ("onay_bekliyor",)),
               ("5) RE-TEST BEKLEYENLER", ("retest_bekliyor",)),
               ("6) İZLEME LİSTESİ", ("izleme",)),
               ("7) İPTAL / KAÇAN KURULUMLAR", ("iptal", "kacti"))]
    for baslik, asamalar in gruplar:
        s.append("")
        s.append(baslik)
        liste = [k for k in kurulumlar if k["asama"] in asamalar]
        if not liste:
            s.append("  -")
        for k in liste:
            s.append("  " + ("[%s] " % k["asama"] if baslik.startswith("7") else "") + kisa_satir(k))
    if arsiv_uyarilari:
        s.append("")
        s.append("  Açık sinyal uyarıları:")
        for u in arsiv_uyarilari:
            s.append("   - " + u)
    s.append("")
    s.append("8) SEMBOL BAZINDA YAPI ÖZETİ")
    for oz in ozetler:
        s += oz
    s.append("")
    s.append("9) UYGULANAN OTOMATİK İSTATİSTİK AYARLARI")
    s += ["  " + x for x in oto_ayarlar] if oto_ayarlar else ["  - (OTOMATIK_MOD_SECIMI kapalı veya yeterli örnek yok)"]
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")
    return yol


# =============================================================================
#                                  ANA AKIŞ
# =============================================================================

def eslesmeleri_coz():
    """AKTIF_ESLEMELER -> [(poi_dilimi, onay_dilimi)]."""
    sonuc = []
    for e in AKTIF_ESLEMELER:
        parca = e.replace("->", "→").split("→")
        if len(parca) != 2:
            uyari("Geçersiz eşleşme: %s" % e)
            continue
        poi, onay = parca[0].strip(), parca[1].strip()
        if ZAMAN_DILIMI_ESLEME.get(poi) != onay:
            uyari("%s eşleşmesi ZAMAN_DILIMI_ESLEME ile uyuşmuyor; yine de kullanıldı." % e)
        sonuc.append((poi, onay))
    return sonuc


def kaynak_dilim(d):
    return TURETILMIS_DILIMLER[d][0] if d in TURETILMIS_DILIMLER else d


def istek_dilimleri(eslesmeler):
    """API'den çekilecek dilimler (türetilmişler ek istek yapmaz)."""
    d = {"1day", "1h"}  # anahtar seviyeler ve GAP için
    for poi, onay in eslesmeler:
        d.add(kaynak_dilim(poi))
        d.add(kaynak_dilim(onay))
    return sorted(d, key=lambda x: -DILIM_DAKIKA[x])


def analiz_dilimleri(eslesmeler):
    d = set()
    for poi, onay in eslesmeler:
        d.update([poi, onay])
    d.update(OB_TEYIT_ZAMAN_DILIMLERI)
    d.update(BREAKER_ZAMAN_DILIMLERI)
    return d


def sembol_tara(sembol, eslesmeler, kaynak, simdi, top, oto_notlar, ham):
    """Bir sembol için veri -> analiz -> kurulumlar -> istatistik -> özet."""
    if not kripto_mu(sembol) and forex_hafta_sonu_mu(simdi):
        return {"hata": "piyasa kapalı (hafta sonu)"}
    for d in istek_dilimleri(eslesmeler):
        if d in ham:
            continue
        v = kaynak(sembol, d, MUM_SAYISI.get(d, 300))
        if not v:
            return {"hata": "%s verisi alınamadı" % d}
        ham[d] = v
    if not kripto_mu(sembol) and simdi - ham["1h"][-1]["dt"] > datetime.timedelta(hours=3):
        return {"hata": "piyasa kapalı (son mum %s)" % zaman_yaz(ham["1h"][-1]["dt"])}
    if not kripto_mu(sembol):
        ham = {d: hafta_sonu_mumlarini_ayikla(v, d) for d, v in ham.items()}
    kapali = {d: kapali_mumlar(v, d, simdi) for d, v in ham.items()}
    for hedef, (kd, kat) in TURETILMIS_DILIMLER.items():
        if kd in ham:
            kapali[hedef] = kapali_mumlar(mum_birlestir(ham[kd], kat, DILIM_DAKIKA[kd]), hedef, simdi)
    an = {False: {}, True: {}}
    notlar = []
    for d in analiz_dilimleri(eslesmeler):
        m = kapali.get(d)
        if not m:
            continue
        if len(m) < MIN_MUM:
            notlar.append("%s yetersiz veri (%d mum)" % (d, len(m)))
            continue
        an[False][d] = dilim_analiz(m, d)
        an[True][d] = dilim_analiz(ayna(m), d)
    # İstatistik (ek istek yok) ve isteğe bağlı otomatik ayar
    katsayilar = {}
    if ISTATISTIK_AKTIF:
        for d in sorted(set(x for e in eslesmeler for x in e)):
            if d in an[False]:
                istatistik_hesapla(top, sembol, an[False][d], an[True].get(d), [])
        if OTOMATIK_MOD_SECIMI:
            for d in list(an[False].keys()):
                ob_mod = top.en_iyi(sembol, d, "OB", "mod=")
                br_mod = top.en_iyi(sembol, d, "BREAKER", "mod=")
                if (ob_mod and ob_mod != OB_BOLGE_MODU) or (br_mod and br_mod != BREAKER_BOLGE_MODU):
                    m = kapali[d]
                    an[False][d] = dilim_analiz(m, d, ob_mod, br_mod)
                    an[True][d] = dilim_analiz(ayna(m), d, ob_mod, br_mod)
                    oto_notlar.append("%s %s: OB modu=%s, breaker modu=%s" % (sembol, d, ob_mod or OB_BOLGE_MODU,
                                                                           br_mod or BREAKER_BOLGE_MODU))
                zayif = top.zayif_konseptler(sembol, d)
                if zayif:
                    katsayilar[d] = zayif
                    oto_notlar.append("%s %s: başarı < %%%d olan konsept puanı 0: %s" % (
                        sembol, d, OTOMATIK_MIN_BASARI * 100, ", ".join(sorted(zayif))))
    anahtar = anahtar_seviyeler(ham["1day"], simdi)
    # Monday High/Low düşük dilimlerde (<= 2h) range görevi görür (şartname 7.7)
    pzt = monday_araligi(ham["1day"], simdi)
    for ay in (False, True):
        for d, an_d in an[ay].items():
            an_d["rangeler"] = [r for r in an_d["rangeler"] if r.get("tur") != "MONDAY"]
            if pzt and DILIM_DAKIKA.get(d, 0) <= 120:
                r = monday_range(an_d, pzt, ay)
                if r:
                    an_d["rangeler"].insert(0, r)
    kurulumlar = []
    for poi_d, onay_d in eslesmeler:
        for ay in (False, True):
            if poi_d not in an[ay] or onay_d not in an[ay]:
                if not ay:
                    notlar.append("%s→%s atlandı (veri yok)" % (poi_d, onay_d))
                continue
            m1h = kapali.get("1h") or []
            m1h = ayna(m1h) if ay else m1h
            gaps = hafta_sonu_gap_bul(sembol, m1h, atr_listesi(m1h)) if m1h else []
            if "1day" in an[ay]:
                gaps += an[ay]["1day"]["gaps"]
            ctx = {"sembol": sembol, "eslesme": "%s→%s" % (poi_d, onay_d), "ayna": ay,
                   "htf": an[ay][poi_d], "ltf": an[ay][onay_d], "an": an[ay],
                   "anahtar": [{"ad": s["ad"], "seviye": -s["seviye"] if ay else s["seviye"]} for s in anahtar],
                   "gaps": gaps, "katsayilar": katsayilar.get(onay_d, {}), "simdi": simdi,
                   "m1h_ham": ayna(ham["1h"]) if ay else ham["1h"]}
            ks, _ = cerceve_tara(ctx)
            for k in ks:
                kurulumlar.append(kurulum_geri_cevir(k))
    if ISTATISTIK_AKTIF:
        for d in set(x for e in eslesmeler for x in e):
            if d in an[False]:
                for k in kurulumlar:
                    if k.get("onay_dilim") == d and k.get("sonuc") and k["sonuc"] not in ("açık", "?"):
                        for n in (1, 2, 3):
                            top.ekle(sembol, d, "LIKIDITE", "TP%d_ulaşma" % n,
                                     (True, k["sonuc"].startswith("tp") and int(k["sonuc"][2]) >= n))
    kurulumlar = kurulum_tekillestir(kurulumlar)
    ozet = yapi_ozeti(sembol, an[False], anahtar)
    for n in notlar:
        ozet.append("  not: " + n)
    return {"kurulumlar": kurulumlar, "ozet": ozet, "an": an[False]}


def kurulum_tekillestir(kurulumlar):
    """Aynı yön + çakışan giriş bölgesi + aynı tetik zamanı -> en yüksek skor kalır."""
    sonuc = []
    for k in sorted(kurulumlar, key=lambda x: (-x.get("skor", 0), -x.get("ham_puan", 0))):
        if k["asama"] in ("sinyal", "izleme", "retest_bekliyor") and k.get("giris_alt") is not None:
            ayni = next((x for x in sonuc if x["yon"] == k["yon"] and x["asama"] == k["asama"] and x.get("giris_alt") is not None
                         and x.get("zaman") == k.get("zaman") and ortust(x["giris_alt"], x["giris_ust"], k["giris_alt"], k["giris_ust"])), None)
            if ayni is not None:
                if k["tip"] != ayni["tip"] and k["tip"] not in ayni.setdefault("birlesen", []):
                    ayni["birlesen"].append(k["tip"])
                    ayni["notlar"].append("aynı bölgede ayrıca: %s" % k["tip"])
                continue
        sonuc.append(k)
    return sonuc


def acik_sinyal_kontrol(hafiza, sembol, an):
    """Arşivdeki açık sinyaller: stop/TP ve ters yapı (hedef iptali) uyarıları."""
    uyarilar = []
    for kayit in hafiza.get("arsiv", [])[-500:]:
        if kayit.get("sembol") != sembol or kayit.get("asama") != "sinyal" or kayit.get("takip_sonuc"):
            continue
        onay_d = (kayit.get("eslesme") or "→").split("→")[-1]
        a = an.get(onay_d)
        if not a or not kayit.get("zaman") or kayit.get("stop") is None:
            continue
        try:
            t = datetime.datetime.strptime(kayit["zaman"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        i0 = indeks_bul(a["dts"], t) + 1
        long_mu = kayit["yon"] == "LONG"
        tps = kayit.get("tps") or []
        ulasilan = 0
        doldu = False
        for j in range(i0 - 1, len(a["m"])):
            m = a["m"][j]
            if not doldu:
                g = kayit.get("giris")
                if g is None or (long_mu and m["dusuk"] <= g) or (not long_mu and m["yuksek"] >= g):
                    doldu = True
                elif tps and ((long_mu and m["yuksek"] >= tps[0]) or (not long_mu and m["dusuk"] <= tps[0])):
                    kayit["takip_sonuc"] = "giriş dolmadan TP1'e gitti"
                    break
                else:
                    continue
            if (long_mu and m["dusuk"] <= kayit["stop"]) or (not long_mu and m["yuksek"] >= kayit["stop"]):
                kayit["takip_sonuc"] = "stop" if ulasilan == 0 else "tp%d" % ulasilan
                break
            for n, tp in enumerate(tps, 1):
                if n > ulasilan and ((long_mu and m["yuksek"] >= tp) or (not long_mu and m["dusuk"] <= tp)):
                    ulasilan = n
            if tps and ulasilan == len(tps):
                kayit["takip_sonuc"] = "tp%d" % ulasilan
                break
        if kayit.get("takip_sonuc"):
            uyarilar.append("%s %s %s (%s): sonuç %s" % (sembol, kayit["yon"], kayit["tip"], kayit["zaman"], kayit["takip_sonuc"]))
            continue
        ters = "bear" if long_mu else "bull"
        if any(o["yon"] == ters and o["tip"] in ("CHOCH", "MSB") and o["i"] >= i0 for o in a["olaylar"]):
            uyarilar.append("%s %s %s (%s): yapı ters yönde CHoCH/MSB yaptı -> hedef havuzlar 'iptal edilmiş hedef'. "
                            "Likidite alınmadan dönüş normal sonuçtur." % (sembol, kayit["yon"], kayit["tip"], kayit["zaman"]))
    return uyarilar


def butce_yaz(semboller, eslesmeler, yonetici):
    dilimler = istek_dilimleri(eslesmeler)
    istek = len(semboller) * len(dilimler)
    kalan = yonetici.kalan()
    print("İstek bütçesi: sembol başına %d istek (%s) x %d sembol = %d istek/tarama" % (
        len(dilimler), ", ".join(dilimler), len(semboller), istek))
    print("  %d sn aralıkla ≈ %.1f dakika. Bugün kalan: %d -> en fazla ≈ %d tarama." % (
        ISTEK_ARASI_SN, istek * ISTEK_ARASI_SN / 60.0, kalan, kalan // max(istek, 1)))
    if istek > kalan:
        uyari("Günlük bütçe bu tarama için yetmiyor (%d > %d)." % (istek, kalan))
    return istek


def tarama(kaynak=None):
    """Tek tarama: veri -> analiz -> sinyal -> çıktılar."""
    del UYARILAR[:]
    simdi = simdi_utc()
    for k in ("raporlar", "cache"):
        os.makedirs(YOLLAR[k], exist_ok=True)
    sayac = gunluk_sayac_yukle()
    yonetici = IstekYoneticisi(sayac)
    hafiza = json_oku(YOLLAR["kurulumlar"], {})
    if not isinstance(hafiza, dict):
        hafiza = {}
    semboller = kripto_listesi(simdi, cevrimdisi=kaynak is not None) + FOREX + METALLER
    # Planınızda olmayan semboller (ör. ücretsiz planda XAG/USD) bir süre atlanır; kredi harcanmaz
    plan_disi = json_oku(YOLLAR["plan_disi"], {})
    if not isinstance(plan_disi, dict):
        plan_disi = {}
    plan_atlanan = []
    for s, tarih in list(plan_disi.items()):
        try:
            gecen = (simdi - datetime.datetime.strptime(tarih, "%Y-%m-%d")).days
        except (TypeError, ValueError):
            gecen = PLAN_DISI_BEKLEME_GUN
        if gecen >= PLAN_DISI_BEKLEME_GUN:
            del plan_disi[s]
        elif s in semboller:
            semboller.remove(s)
            plan_atlanan.append(s)
    eslesmeler = eslesmeleri_coz()
    print("=" * 60)
    print("DD Finance PA Tarama | %s UTC" % zaman_yaz(simdi))
    print(FELSEFE)
    api_modu = kaynak is None
    if kaynak is None:
        if not API_KEY or API_KEY.startswith("BURAYA"):
            print("HATA: AYARLAR bölümünde API_KEY girilmemiş.")
            return
        kaynak = lambda s, d, n: veri_cek(s, d, n, yonetici)
    # Düşük öncelikli (15min) eşleşmeler bütçe yetmezse ikinci turda sadece aday sembollerde
    yuksek = [e for e in eslesmeler if "15min" not in e]
    dusuk = [e for e in eslesmeler if "15min" in e]
    ihtiyac = butce_yaz(semboller, eslesmeler, yonetici)
    iki_tur = bool(dusuk) and ihtiyac > yonetici.kalan() and bool(yuksek)
    if iki_tur:
        print("  Bütçe kısıtlı: 15min eşleşmesi yalnızca aday çıkan semboller için ikinci turda.")
    top = IstatistikToplayici()
    oto_notlar, tum, ozetler, atlanan, taranan, uyarilar = [], [], [], [], [], []
    ham_veri = {}
    turlar = [(yuksek if iki_tur else eslesmeler, semboller)]
    for s in plan_atlanan:
        atlanan.append((s, "Twelve Data planınızda yok (%d gün atlanıyor)" % PLAN_DISI_BEKLEME_GUN))
    limit_doldu = False
    for tur_no in range(2):
        if tur_no == 1:
            if not iki_tur or limit_doldu:
                break
            adaylar = sorted(set(k["sembol"] for k in tum if k["asama"] in ("onay_bekliyor", "retest_bekliyor", "sinyal", "izleme")))
            turlar.append((dusuk, adaylar))
        ess, liste = turlar[tur_no]
        for sembol in liste:
            if limit_doldu:
                atlanan.append((sembol, "günlük limit doldu"))
                continue
            if api_modu and yonetici.kalan() < len(istek_dilimleri(ess)):
                limit_doldu = True
                atlanan.append((sembol, "günlük limit yaklaştı"))
                uyari("Günlük istek limitine yaklaşıldı; kalan semboller atlandı.")
                continue
            print("- %s taranıyor..." % sembol)
            try:
                sonuc = sembol_tara(sembol, ess, kaynak, simdi, top, oto_notlar, ham_veri.setdefault(sembol, {}))
            except LimitAsildi:
                limit_doldu = True
                atlanan.append((sembol, "günlük limit doldu"))
                uyari("Günlük istek limiti doldu; kalan semboller atlandı.")
                continue
            except Exception as e:
                atlanan.append((sembol, "hata: %s" % e))
                print("  Hata: %s" % e)
                continue
            if sonuc.get("hata"):
                atlanan.append((sembol, sonuc["hata"]))
                print("  Atlandı: %s" % sonuc["hata"])
                continue
            if sembol not in taranan:
                taranan.append(sembol)
            tum += sonuc["kurulumlar"]
            ozetler.append(sonuc["ozet"])
            uyarilar += acik_sinyal_kontrol(hafiza, sembol, sonuc["an"])
    yeni = [k for k in tum if k["asama"] == "sinyal"]
    yeni.sort(key=lambda k: (-k["skor"], -k["ham_puan"]))
    yazilan = sinyalleri_yaz(yeni, simdi)
    if ISTATISTIK_AKTIF:
        istatistik_yaz(top.satirlar(simdi.strftime("%Y-%m-%d")))
    hafiza_guncelle(hafiza, tum, taranan, simdi)
    try:
        json_yaz(YOLLAR["kurulumlar"], hafiza)
    except Exception as e:
        print("kurulumlar.json yazılamadı: %s" % e)
    gunluk_sayac_kaydet(sayac)
    if yonetici.plan_disi:
        for s in yonetici.plan_disi:
            plan_disi[s] = simdi.strftime("%Y-%m-%d")
        try:
            json_yaz(YOLLAR["plan_disi"], plan_disi)
        except Exception:
            pass
    rapor = rapor_yaz(simdi, {"taranan": taranan, "atlanan": atlanan}, yazilan, tum, ozetler, oto_notlar,
                      yonetici, uyarilar)
    # --- Ekran özeti ---
    print("")
    print("YENİ SİNYALLER (%d)" % len(yazilan))
    for k in yazilan:
        print(ekran_satiri(k))
    print("Onay bekleyen: %d | Re-test bekleyen: %d | İzleme: %d" % (
        sum(1 for k in tum if k["asama"] == "onay_bekliyor"), sum(1 for k in tum if k["asama"] == "retest_bekliyor"),
        sum(1 for k in tum if k["asama"] == "izleme")))
    print("Kullanılan istek: %d (bugün %d/%d)" % (yonetici.bu_tarama, sayac["adet"], GUNLUK_LIMIT))
    if atlanan:
        print("Atlanan: " + ", ".join("%s (%s)" % x for x in atlanan))
    print("Rapor: %s" % rapor)


def main(kaynak=None):
    while True:
        tarama(kaynak)
        if DONGU_DAKIKA <= 0:
            break
        print("%d dakika sonra tekrar taranacak (ekranı açık tutun)..." % DONGU_DAKIKA)
        time.sleep(DONGU_DAKIKA * 60)


# =============================================================================
#                          DEMO (yapay veri, API yok)
# =============================================================================

class _Rastgele:
    """Basit doğrusal eşlik üreteci (random modülü izinli listede değil)."""

    def __init__(self, tohum):
        self.x = tohum % 2147483647 or 1

    def sayi(self):
        self.x = (self.x * 48271) % 2147483647
        return self.x / 2147483647.0

    def normal(self):
        return sum(self.sayi() for _ in range(12)) - 6.0


def demo_seri(sembol, simdi, gun=300):
    """Rejim değiştiren rastgele yürüyüşle 1h mumlar üretir."""
    baz = {"BTC/USD": 60000, "ETH/USD": 3000, "SOL/USD": 150, "BNB/USD": 550, "XRP/USD": 0.6,
           "XAU/USD": 2400, "XAG/USD": 29, "USD/JPY": 150, "GBP/JPY": 190}.get(sembol, 1.1)
    r = _Rastgele(sum(ord(c) * (i + 7) for i, c in enumerate(sembol)))
    bitis = simdi.replace(minute=0, second=0, microsecond=0)
    t = bitis - datetime.timedelta(hours=gun * 24)
    fiyat, egim, kalan, oyna = baz, 0.0, 0, (0.004 if kripto_mu(sembol) else 0.0015)
    mumlar = []
    while t <= bitis:
        if not kripto_mu(sembol) and ((t.weekday() == 4 and t.hour >= 21) or t.weekday() == 5 or (t.weekday() == 6 and t.hour < 22)):
            t += datetime.timedelta(hours=1)
            continue
        if kalan <= 0:
            egim = oyna * [-0.12, -0.05, 0.0, 0.0, 0.05, 0.12][int(r.sayi() * 6)]
            kalan = int(80 + r.sayi() * 300)
        kalan -= 1
        hareket = egim + oyna * 0.35 * r.normal()
        if r.sayi() < 0.01:
            hareket += (1 if r.sayi() < 0.5 else -1) * oyna * 4
        acilis = fiyat
        kapanis = fiyat * (1 + hareket)
        yuksek = max(acilis, kapanis) * (1 + abs(r.normal()) * oyna * 0.25)
        dusuk = min(acilis, kapanis) * (1 - abs(r.normal()) * oyna * 0.25)
        mumlar.append({"zaman": zaman_yaz(t), "dt": t, "acilis": acilis, "yuksek": yuksek, "dusuk": dusuk, "kapanis": kapanis})
        fiyat = kapanis
        t += datetime.timedelta(hours=1)
    return mumlar


def demo_kaynak(simdi):
    onbellek = {}

    def kaynak(sembol, aralik, adet):
        if sembol not in onbellek:
            onbellek[sembol] = demo_seri(sembol, simdi)
        s = onbellek[sembol]
        if aralik == "1h":
            m = s
        elif aralik == "4h":
            m = mum_birlestir(s, 4, 60)
        elif aralik == "1day":
            m = mum_birlestir(s, 24, 60)
        else:  # 15min: her 1h mum 4 parçaya bölünür
            m = []
            for x in s[-(adet // 4 + 2):]:
                fiyatlar = [x["acilis"], (x["acilis"] + x["kapanis"]) / 2 + (x["yuksek"] - x["dusuk"]) * 0.1,
                            (x["acilis"] + x["kapanis"]) / 2 - (x["yuksek"] - x["dusuk"]) * 0.1, x["kapanis"]]
                onceki = x["acilis"]
                for q, p in enumerate(fiyatlar):
                    dt = x["dt"] + datetime.timedelta(minutes=15 * q)
                    m.append({"zaman": zaman_yaz(dt), "dt": dt, "acilis": onceki, "kapanis": p,
                              "yuksek": max(onceki, p), "dusuk": min(onceki, p)})
                    onceki = p
        return [dict(x) for x in m[-adet:]]
    return kaynak


# =============================================================================
#                          BİRİM TESTLERİ (--test)
# =============================================================================

def _mum(i, o, h, l, c):
    dt = datetime.datetime(2025, 1, 6) + datetime.timedelta(hours=i)
    return {"zaman": zaman_yaz(dt), "dt": dt, "acilis": float(o), "yuksek": float(h), "dusuk": float(l), "kapanis": float(c)}


def _yol(noktalar, fitil=0.3):
    """(indeks, kapanış) noktaları arasında doğrusal kapanış yolu -> mumlar."""
    kapanislar = []
    for (i1, p1), (i2, p2) in zip(noktalar, noktalar[1:]):
        for i in range(i1, i2):
            kapanislar.append(p1 + (p2 - p1) * (i - i1) / float(i2 - i1))
    kapanislar.append(noktalar[-1][1])
    mumlar = []
    onceki = kapanislar[0]
    for i, c in enumerate(kapanislar):
        o = onceki if i else c + 0.1
        mumlar.append(_mum(i, o, max(o, c) + fitil, min(o, c) - fitil, c))
        onceki = c
    return mumlar


def testleri_calistir():
    sonuclar = []

    def kontrol(ad, kosul, detay=""):
        sonuclar.append(bool(kosul))
        print("%s  %s%s" % ("GEÇTİ " if kosul else "KALDI ", ad, ("  -> " + detay) if (detay and not kosul) else ""))

    def yakin(x, y, tol):
        return x is not None and abs(x - y) <= tol

    print("DD Finance PA botu – birim testleri")
    print("-" * 60)
    # --- 19.5 Fibonacci (DD notlarındaki gerçek değerler) ---
    f = fib_retracement(41689.1, 42105.4, "long")
    kontrol("Fib long retracement 0.618/0.705/0.786",
            yakin(f[0.618], 41848.1, 0.1) and yakin(f[0.705], 41811.9, 0.1) and yakin(f[0.786], 41778.2, 0.1),
            str([round(f[k], 1) for k in (0.618, 0.705, 0.786)]))
    f = fib_retracement(42148.6, 41825.2, "short")
    kontrol("Fib short retracement 0.618/0.705/0.786",
            yakin(f[0.618], 42025.1, 0.1) and yakin(f[0.705], 42053.2, 0.1) and yakin(f[0.786], 42079.4, 0.1),
            str([round(f[k], 1) for k in (0.618, 0.705, 0.786)]))
    u = fib_uzatma(41689.1, 42105.4, 41812.4, "long")
    kontrol("Fib long uzatma 1.0 ≈ 42228.7 (grafik 42230.3, ±5)", yakin(u[1.0], 42228.7, 0.1) and yakin(u[1.0], 42230.3, 5), str(u))
    u = fib_uzatma(42148.6, 41825.2, 42054.2, "short")
    kontrol("Fib short uzatma 1.0 ≈ 41730.8 / 1.618 ≈ 41530.9 (±5)",
            yakin(u[1.0], 41730.8, 0.1) and yakin(u[1.618], 41530.9, 0.1) and yakin(u[1.0], 41732.4, 5) and yakin(u[1.618], 41533.5, 5),
            str(u))

    # --- Imbalance: geçerli / önceki iğneyle kapanmış ---
    taban = [_mum(i, 100 + (0.5 if i % 2 else 0), 100.8, 99.7, 100 + (0 if i % 2 else 0.5)) for i in range(15)]
    buyuk = _mum(15, 100.5, 106.2, 100.4, 106.0)
    m_gec = taban + [buyuk, _mum(16, 106.0, 107.0, 104.5, 106.8), _mum(17, 106.8, 107.2, 106.0, 107.0)]
    imb = [z for z in imbalance_bul(m_gec, atr_listesi(m_gec)) if z["i"] == 15]
    kontrol("Imbalance geçerli (fitille: alt = önceki mumun tepesi, üst = sonraki mumun dibi)",
            imb and imb[0]["yon"] == "long" and yakin(imb[0]["alt"], 100.8, 1e-9) and yakin(imb[0]["ust"], 104.5, 1e-9)
            and imb[0]["giris"] == imb[0]["alt"])
    m_gec2 = taban + [buyuk, _mum(16, 106.0, 107.0, 100.6, 106.8), _mum(17, 106.8, 107.2, 106.0, 107.0)]
    imb2 = [z for z in imbalance_bul(m_gec2, atr_listesi(m_gec2)) if z["i"] == 15]
    kontrol("Imbalance: iğneyle kapanmış boşluk imbalance sayılmıyor", not imb2)

    # --- SFP: geçerli ve pencere içinde iptal ---
    def sfp_dizisi(iptal):
        m = _yol([(0, 104), (5, 95.3), (15, 104), (18, 100)])
        m.append(_mum(len(m), 100, 100.2, 94.0, 96.0))       # fitil 95'in altına, kapanış berisinde
        for q in range(SFP_GECERLILIK_MUM):
            c = 94.5 if (iptal and q == 2) else 97 + q
            m.append(_mum(len(m), m[-1]["kapanis"], max(m[-1]["kapanis"], c) + 0.2, min(m[-1]["kapanis"], c) - 0.2, c))
        m.append(_mum(len(m), m[-1]["kapanis"], 103, 100, 102))
        return m
    m = sfp_dizisi(False)
    sw = [{"i": 5, "tip": "L", "fiyat": m[5]["dusuk"]}]
    s = sfp_bul(m, atr_listesi(m), sw, [], swing_noktalari(m, 2))
    kontrol("SFP geçerli (fitil + berisinde kapanış + pencere temiz)", s and s[0]["durum"] == "onaylı" and s[0]["i"] == 19,
            str([(x["i"], x["durum"]) for x in s]))
    m = sfp_dizisi(True)
    s = sfp_bul(m, atr_listesi(m), sw, [], swing_noktalari(m, 2))
    kontrol("SFP pencere içinde tek ötede kapanış -> iptal", s and s[0]["durum"] == "iptal",
            str([(x["i"], x["durum"]) for x in s]))

    # --- CHoCH: yeni uç yaptırmamış dibin kırılması CHoCH değildir ---
    m = _yol([(0, 100), (4, 104), (7, 101), (12, 110), (15, 106), (18, 109), (22, 105), (25, 107), (29, 100), (33, 102)])
    ic = swing_noktalari(m, 2)
    mk = mikro_yapi(m, atr_listesi(m), ic, 2, [None] * len(m))
    dip_106 = next(x for x in ic if x["tip"] == "L" and 14 <= x["i"] <= 16)
    dip_101 = next(x for x in ic if x["tip"] == "L" and 6 <= x["i"] <= 8)
    kirilim_106 = next(i for i in range(17, len(m)) if m[i]["kapanis"] < dip_106["fiyat"])
    kirilim_101 = next(i for i in range(17, len(m)) if m[i]["kapanis"] < dip_101["fiyat"])
    ayi = [o for o in mk["olaylar"] if o["yon"] == "bear"]
    kontrol("CHoCH: yeni tepe yaptırmamış dibin (106) kırılması CHoCH sayılmıyor",
            not any(o["i"] == kirilim_106 for o in ayi), str([(o["i"], o["seviye"]) for o in ayi]))
    kontrol("CHoCH: yeni tepe yaptıran dibin (101) kırılması CHoCH",
            any(o["i"] == kirilim_101 and o["kaynak_i"] == dip_101["i"] for o in ayi), str([(o["i"], o["kaynak_i"]) for o in ayi]))

    # --- MSB: korunan seviyenin kapanışla kırılması; sonrası BOS ---
    m = _yol([(0, 100), (5, 110), (10, 104), (16, 116), (22, 109), (28, 120), (34, 112), (40, 118), (47, 106),
              (52, 110), (58, 100), (64, 104)])
    atrs = atr_listesi(m)
    y = yapi_analiz(m, atrs, swing_noktalari(m, 2), 2)
    msb = [o for o in y["olaylar"] if o["tip"] == "MSB"]
    bos_once = [o for o in y["olaylar"] if o["tip"] == "BOS" and o["yon"] == "bull"]
    kontrol("MSB: bull BOS'lar sonrası korunan dip kapanışla kırılınca MSB (bear)",
            bos_once and msb and msb[0]["yon"] == "bear" and yakin(msb[0]["seviye"], bos_once[-1]["korunan"]["fiyat"], 1e-9),
            str([(o["tip"], o["yon"], o["i"]) for o in y["olaylar"]]))
    sonraki = [o for o in y["olaylar"] if msb and o["i"] > msb[0]["i"]]
    kontrol("MSB sonrası aynı yöndeki kırılım BOS olarak etiketleniyor",
            sonraki and sonraki[0]["tip"] == "BOS" and sonraki[0]["yon"] == "bear",
            str([(o["tip"], o["yon"], o["i"]) for o in sonraki]))

    # --- Order Block (bullish) ---
    m = _yol([(0, 110), (6, 104), (9, 107), (14, 100)])
    kirmizi_i = len(m)
    m.append(_mum(kirmizi_i, 100.0, 100.4, 98.5, 99.0))          # OB mumu (kırmızı)
    m.append(_mum(kirmizi_i + 1, 99.0, 101.6, 98.9, 101.5))     # yeşil, kapanış >= kırmızının tepesi
    for q, c in enumerate([104, 108, 110, 109, 111]):
        o = m[-1]["kapanis"]
        m.append(_mum(len(m), o, max(o, c) + 0.3, min(o, c) - 0.3, c))
    atrs = atr_listesi(m)
    ic = swing_noktalari(m, 2)
    y = yapi_analiz(m, atrs, ic, 2)
    mk = mikro_yapi(m, atrs, ic, 2, y["trend_dizi"])
    olaylar = sorted(y["olaylar"] + mk["olaylar"], key=lambda o: o["i"])
    obs = ob_bul(m, atrs, olaylar, ic, [], "son_mum_fitil")
    kontrol("OB bullish: mum kuralı + önceki hareketi kapatma + yapı kırılımı",
            any(z["yon"] == "long" and z["k"] == kirmizi_i for z in obs), str([(z["yon"], z["k"]) for z in obs]))
    m2 = [dict(x) for x in m]
    m2[kirmizi_i + 1] = _mum(kirmizi_i + 1, 99.0, 100.3, 98.9, 100.2)  # yutmuyor
    obs2 = ob_bul(m2, atr_listesi(m2), olaylar, ic, [], "son_mum_fitil")
    kontrol("OB: yeşil mum kırmızının tepesini geçmezse OB yok", not any(z["k"] == kirmizi_i for z in obs2))

    # --- PO3 tam dizi ve erken kırılım ---
    def po3_dizisi(istekli):
        m = _yol([(0, 135), (10, 104), (13, 108), (16, 102), (19, 109), (22, 101), (26, 108.5), (29, 103)], fitil=0.4)
        n0 = len(m)
        ekler = [(103, 103.2, 95.0, 99.0),       # manipülasyon: RL altı kapanış
                 (99.0, 102.6, 98.8, 102.5),      # range içine dönüş (re-entry)
                 (102.5, 105.2, 102.0, 105.0),
                 (105.0, 109.4, 104.8, 109.2),    # range içi son SH kırılımı
                 (109.2, 109.5, 106.2, 106.5)]    # HL
        if istekli:
            ekler += [(106.5, 118.5, 106.3, 118.0),   # RH displacement kırılımı
                      (118.0, 120.0, 117.0, 119.5), (119.5, 120.5, 116.0, 116.5),
                      (116.5, 117.0, 109.9, 111.0)]   # RH re-test
        else:
            ekler += [(106.5, 110.8, 106.3, 110.6), (110.6, 111.2, 109.8, 110.9), (110.9, 111.3, 110.1, 110.4)]
        for q, (o, h, l, c) in enumerate(ekler):
            m.append(_mum(n0 + q, o, h, l, c))
        return m, n0
    for istekli in (True, False):
        m, n0 = po3_dizisi(istekli)
        atrs = atr_listesi(m)
        rh = max(govde_ust(m[k]) for k in range(10, n0))
        rl = min(govde_alt(m[k]) for k in range(10, n0))
        r = {"rh": rh, "rl": rl, "eq": (rh + rl) / 2, "bas_i": 10, "bit_i": len(m) - 1,
             "devs": [{"yon": "asagi", "bas_i": n0, "uc": 95.0, "reentry_i": n0 + 1}]}
        ic = [s for s in swing_noktalari(m, 2) if s["i"] < n0]
        p = po3_tara(m, atrs, [r], ic, [])
        if istekli:
            kontrol("PO3 tam dizi: aşama 0-5 sırayla, RH re-testinde sinyal",
                    p and p[0]["asama"] == 5 and p[0]["durum"] == "sinyal" and p[0]["retest_i"] == n0 + 8
                    and p[0]["nihai_hedef"] >= 130, str([(x["asama"], x["durum"], x.get("retest_i")) for x in p]))
        else:
            kontrol("PO3 erken kırılım (displacement yok): sinyal yok, 'bekle' notu",
                    p and p[0]["asama"] < 5 and p[0]["durum"] != "sinyal" and any("erken" in n for n in p[0]["notlar"]),
                    str([(x["asama"], x["durum"], x["notlar"]) for x in p]))

    # --- Quasimodo tam dizi ---
    m = _yol([(0, 112), (6, 100), (11, 110), (17, 96), (23, 113), (26, 115), (31, 100.4), (35, 108)])
    atrs = atr_listesi(m)
    sw = swing_noktalari(m, 2)
    q = qm_bul(m, atrs, sw)
    kontrol("QM tam dizi: LL1-LH-LL2 -> neckline kırılımı -> sol omuz re-testi",
            q and q[0]["retest_i"] is not None and q[0]["iptal_i"] is None and abs(q[0]["retest_i"] - 31) <= 1,
            str([(x["ll1"]["i"], x["ll2"]["i"], x["kirilim_i"], x["retest_i"]) for x in q]))

    # --- Reversal Fractal renk kuralı ---
    m = _yol([(0, 110), (6, 102), (9, 105), (14, 102.6)])
    n0 = len(m)
    m.append(_mum(n0, 102.6, 102.8, 99.0, 102.0))    # süpürme mumu KIRMIZI kapanır (dip 101.7 altına fitil)
    for q2, c in enumerate([103, 106, 108, 106, 104.5, 105]):
        o = m[-1]["kapanis"]
        m.append(_mum(len(m), o, max(o, c) + 0.3, min(o, c) - 0.3, c))
    atrs = atr_listesi(m)
    ic = swing_noktalari(m, 2)
    poi = [{"alt": 98.5, "ust": 102.0}]
    kontrol("Reversal Fractal: renk kuralı açıkken kırmızı süpürme mumu kabul edilmiyor",
            not reversal_fractal_bul(m, atrs, ic, poi, renk_kurali=True))
    kontrol("Reversal Fractal: renk kuralı kapatılabiliyor (aynı dizide desen bulunuyor)",
            bool(reversal_fractal_bul(m, atrs, ic, poi, renk_kurali=False)))

    # --- S/R: tek temaslı seviye S/R değildir ---
    m = _yol([(0, 100), (10, 110), (20, 100), (30, 120)])
    kontrol("S/R: tek temaslı seviye flip adayı değil",
            not sr_seviyeleri(m, atr_listesi(m), [{"i": 10, "tip": "H", "fiyat": 110.3}]))

    # --- Puanlama: çift sayım önleme ---
    ms = [madde("SD:DBR", 1, "bolge", 100, 102, "SD"), madde("OB", 1.5, "bolge", 100.5, 101.5, "OB"),
          madde("IMB", 0.5, "bolge", 101, 102, "IMB"), madde("SFP", 1, "olay", anahtar="S"),
          madde("DEVIASYON", 1, "olay", anahtar="S")]
    ham, bag = puan_hesapla(ms, 1.0)
    kontrol("Puanlama: aynı bölgede en yüksek + S&D/OB +0.5 + diğer +0.25; aynı olay bir kez",
            yakin(ham, 1.5 + 0.5 + 0.25 + 1, 1e-9) and bag == 2, "ham=%s bağımsız=%s" % (ham, bag))

    # --- Mum birleştirme (12h = 4h x 3, UTC hizalı) ---
    m4 = [_mum(i * 4, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(6)]
    b = mum_birlestir(m4, 3, 240)
    kontrol("Mum birleştirme: 4h x3 -> 12h (açılış ilk, kapanış son, max/min)",
            len(b) == 2 and b[0]["acilis"] == 100 and b[0]["kapanis"] == 102.5 and b[0]["yuksek"] == 103 and b[0]["dusuk"] == 99)

    # --- Canlı giriş kontrolü (doldu / kaçtı / limit) ---
    base = datetime.datetime(2026, 9, 27, 0, 0)
    def _h(i, o, h, l, c):
        return {"dt": base + datetime.timedelta(hours=i), "acilis": o, "yuksek": h, "dusuk": l, "kapanis": c}
    ltf_s = {"dts": [base], "dilim": "1h"}
    kk = {"giris": 100.0, "stop": 98.0, "tps": [(106.0, "x")], "tetik_i": 0}
    ltf_s.update({"m": [_h(0, 101, 101.5, 100.5, 101)], "olaylar": []})
    kk["stop_ref"] = 98.5

    def gdurum(seri, ltf=None):
        return giris_durumu({"m1h_ham": seri, "ltf": ltf or ltf_s}, dict(kk))["durum"]
    kontrol("Giriş kontrolü: dolmadı -> LİMİT", gdurum([_h(0, 101, 101.5, 100.5, 101), _h(1, 101, 101.2, 100.6, 101)]) == "limit")
    kontrol("Giriş kontrolü: doldu, fiyat girişe yakın -> AKTİF", gdurum([_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.6, 100, 100.4)]) == "aktif")
    kontrol("Giriş kontrolü: doldu, fiyat uzaklaştı (güncel R/R < MIN_RR) -> KAÇTI",
            gdurum([_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 103.6, 100.1, 103.5)]) == "kacti")
    kontrol("Giriş kontrolü: giriş gelmeden TP1 -> KAÇTI", gdurum([_h(0, 101, 106.5, 100.5, 106)]) == "hedef_girissiz")
    ltf_ters = {"dts": [base, base + datetime.timedelta(hours=1)], "dilim": "1h",
                "m": [_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.6, 99.9, 100.1)],
                "olaylar": [{"tip": "CHOCH", "yon": "bear", "i": 1}]}
    kontrol("Giriş kontrolü: tetikten sonra ters CHoCH -> İPTAL (hedef iptali, fiyat girişe yakın olsa da)",
            gdurum([_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.6, 99.9, 100.1)], ltf_ters) == "ters_yapi")
    ltf_boz = {"dts": ltf_ters["dts"], "dilim": "1h", "olaylar": [],
               "m": [_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.3, 98.2, 98.4)]}
    kontrol("Giriş kontrolü: stop referansı ötesinde kapanış (stop değmeden) -> İPTAL",
            gdurum([_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.3, 98.2, 98.4)], ltf_boz) == "yapi_bozuldu")
    kontrol("Giriş kontrolü: doldu sonra stop -> eski", gdurum([_h(0, 101, 101.5, 99.8, 100.2), _h(1, 100.2, 100.3, 97.5, 98)]) == "stop")

    # --- Backtest: TP1 sonrası stop girişe (DD PO3 notu) ---
    bm = [_h(0, 100, 100.2, 99.9, 100), _h(1, 100, 104.2, 99.9, 104), _h(2, 104, 104.1, 99.5, 99.6)]
    isl = bt_islem_simule({"yon": "LONG", "giris": 100.0, "stop": 98.0, "tps": [104.0, 110.0], "giris_turu": "PİYASA",
                           "dolum_zamani": "", "cikis_zamani": "", "sonuc": "", "R_tp1": 0.0, "R_kademeli": 0.0}, bm, 0)
    isl2 = bt_islem_simule({"yon": "LONG", "giris": 100.0, "stop": 98.0, "tps": [104.0], "giris_turu": "PİYASA",
                            "dolum_zamani": "", "cikis_zamani": "", "sonuc": "", "R_tp1": 0.0, "R_kademeli": 0.0}, bm, len(bm))
    kontrol("Backtest: dönemin son saatindeki sinyal çökmüyor (veri bitti)", isl2["sonuc"] == "bekliyor (veri bitti)")
    kontrol("Backtest: TP1'de %50 kâr, sonra girişte stop -> +1R (2R x %50)",
            isl["sonuc"] == "TP1 + girişte stop" and abs(isl["R_kademeli"] - 1.0) < 1e-9, str((isl["sonuc"], isl["R_kademeli"])))

    # --- Range: büyük göreceli hareketten sonra (DD not 3) ---
    ry = _yol([(0, 130), (10, 108), (15, 100.5), (20, 109.5), (25, 100.5), (30, 109.5), (35, 100.5), (40, 109.5), (45, 104)])
    ry_sw = swing_noktalari(ry, 2)
    kontrol("Range: sert düşüşten sonraki yatay bölge range olarak bulunuyor", bool(range_tespit(ry, atr_listesi(ry), ry_sw)))
    rd = _yol([(0, 106), (10, 104), (15, 100.5), (20, 109.5), (25, 100.5), (30, 109.5), (35, 100.5), (40, 109.5), (45, 104)])
    kontrol("Range: öncesinde büyük hareket yoksa range sayılmıyor",
            not any(r["bas_i"] >= 12 for r in range_tespit(rd, atr_listesi(rd), swing_noktalari(rd, 2))))

    # --- Monday range (şartname 7.7) ---
    pzt_bas = datetime.datetime(2026, 9, 21)
    mm = []
    for i in range(72):
        dt = pzt_bas + datetime.timedelta(hours=i)
        c = 105 + (4.5 if i % 6 == 0 else -4.5 if i % 6 == 3 else 0)
        if i == 40:
            c, lo = 100.5, 98.0          # Salı-Çarşamba: RL altına fitil (deviasyon)
        mm.append({"zaman": zaman_yaz(dt), "dt": dt, "acilis": 105.0, "yuksek": max(105.0, c) + 0.2,
                   "dusuk": (lo if i == 40 else min(105.0, c) - 0.2), "kapanis": c})
    an_t = {"m": mm, "atrs": atr_listesi(mm), "dts": [x["dt"] for x in mm], "mikro": {"olaylar": []}}
    mr = monday_range(an_t, (pzt_bas, 110.0, 100.0), False)
    kontrol("Monday range: RH/RL = Monday High/Low, EQ ve fitil deviasyonu",
            mr and mr["rh"] == 110.0 and mr["rl"] == 100.0 and mr["eq"] == 105.0
            and any(d["yon"] == "asagi" and d["uc"] == 98.0 for d in mr["devs"]),
            str(mr and (mr["rh"], mr["rl"], [(d["yon"], d["uc"]) for d in mr["devs"]])))
    kontrol("Monday range: Pazartesi bitmeden kullanılmaz",
            monday_araligi([{"dt": pzt_bas, "yuksek": 110, "dusuk": 100}], pzt_bas + datetime.timedelta(hours=10)) is None)

    # --- Forex hafta sonu ---
    cmt = datetime.datetime(2026, 9, 26, 5, 0)
    kontrol("Forex hafta sonu: Cumartesi kapalı, Pazartesi açık, Cuma 21:00 kapalı",
            forex_hafta_sonu_mu(cmt) and not forex_hafta_sonu_mu(datetime.datetime(2026, 9, 28, 9, 0))
            and forex_hafta_sonu_mu(datetime.datetime(2026, 9, 25, 21, 0)))
    hm = [{"dt": datetime.datetime(2026, 9, 25, 20, 0)}, {"dt": cmt}, {"dt": datetime.datetime(2026, 9, 27, 21, 0)}]
    kontrol("Forex hafta sonu mumları analizden çıkarılıyor",
            [x["dt"] for x in hafta_sonu_mumlarini_ayikla(hm, "1h")] == [hm[0]["dt"], hm[2]["dt"]])

    print("-" * 60)
    print("%d/%d test geçti." % (sum(sonuclar), len(sonuclar)))
    return all(sonuclar)


# =============================================================================
#                 GERİYE DÖNÜK TEST (--backtest) – Binance gerçek verisi
# =============================================================================
# Bot, geçmişte her BACKTEST_ADIM_SAAT saatte bir tarama yapıyormuş gibi adım adım
# ilerletilir (yalnızca o ana kadar KAPANMIŞ mumları görür; geleceğe bakmaz).
# Bir kurulum ilk kez "sinyal" olduğunda otomatik bir bot gibi emir açılır:
#   AGRESİF : SFP_AGRESIF girişi (seviyenin hemen berisine limit emir)
#   LİMİT   : giriş henüz dolmamış -> giriş fiyatına limit emir
#   PİYASA  : giriş zaten dolmuş ve güncel fiyattan R/R hâlâ MIN_RR üstünde -> güncel fiyattan
# Çıkış: stop -> -1R; TP1'de %50, TP2'de %50 (stop girişe çekilmez; şartname 11.5).
# Aynı mumda hem stop hem hedef görülürse muhafazakâr varsayım: önce stop.
# Binance herkese açık verisi kullanılır; Twelve Data kredisi HARCANMAZ.

BACKTEST_GUN = 30                # Test edilecek geçmiş gün sayısı
BACKTEST_SEMBOL_SAYISI = 20      # 24s hacme göre ilk N kripto çifti
BACKTEST_SEMBOLLER = []          # Boş değilse bu liste kullanılır (ör. ["BTC/USD", "SOL/USD"])
BACKTEST_ADIM_SAAT = 1           # Botun kaç saatte bir tarama yaptığı varsayılır
BACKTEST_LIMIT_MAX_SAAT = 24     # Dolmayan limit/agresif emir bu süre sonra iptal
BACKTEST_MAX_ISLEM_SAAT = 168    # Açık işlem bu süre sonra piyasadan kapatılır (7 gün)
BACKTEST_TP1_SONRA_GIRISE = True # TP1'de kâr alındıktan sonra stop girişe çekilir (DD PO3 notu)
BACKTEST_ESLESME_HARIC = []      # örn. ["1day→4h"] -- bu eşlemeden gelen kurulumlar emir açmaz (--no-1d4h)
BACKTEST_GIRIS_TURU_HARIC = []   # örn. ["PİYASA"] -- bu giriş türleri emir açmaz (--no-piyasa)
BACKTEST_MIN_SKOR = None         # örn. 4 -- bu skorun altındaki kurulumlar emir açmaz (--min-skor=4)
BACKTEST_KLINE_URL = ["https://data-api.binance.vision/api/v3/klines",
                      "https://api.binance.com/api/v3/klines"]
BT_ARALIK = {"1day": ("1d", 1440), "4h": ("4h", 240), "1h": ("1h", 60), "15min": ("15m", 15)}


def bt_kline_cek(sembol, aralik, bas, bit):
    """Binance kline'ları [bas, bit) aralığında sayfalı çeker (1000'er)."""
    kod, dk = BT_ARALIK[aralik]
    simge = sembol.replace("/USD", "USDT")
    sonuc = []
    t = bas
    while t < bit:
        ms = int(t.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
        veri = None
        for url in BACKTEST_KLINE_URL:
            veri = _dis_json(url, {"symbol": simge, "interval": kod, "startTime": ms, "limit": 1000})
            if isinstance(veri, list):
                break
        if not isinstance(veri, list) or not veri:
            break
        for x in veri:
            dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=x[0])
            if dt >= bit:
                break
            sonuc.append({"zaman": zaman_yaz(dt), "dt": dt, "acilis": float(x[1]), "yuksek": float(x[2]),
                          "dusuk": float(x[3]), "kapanis": float(x[4])})
        son = datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=veri[-1][0])
        t = son + datetime.timedelta(minutes=dk)
        if len(veri) < 1000:
            break
        time.sleep(0.2)
    return sonuc


def bt_veri_hazirla(sembol, bas, bit, dizin):
    """Isınma + test dönemi verisi (önbellekli)."""
    yol = os.path.join(dizin, "%s_%s_%s.json" % (sembol.replace("/", ""), bas.strftime("%Y%m%d%H"), bit.strftime("%Y%m%d%H")))
    kayit = json_oku(yol, None)
    if isinstance(kayit, dict) and kayit.get("1h"):
        for d in kayit:
            for m in kayit[d]:
                m["dt"] = zaman_coz(m["zaman"])
        return kayit
    veri = {}
    for d, isinma_gun in (("1day", MUM_SAYISI["1day"] + 5), ("4h", MUM_SAYISI["4h"] // 6 + 3), ("1h", MUM_SAYISI["1h"] // 24 + 2)):
        veri[d] = bt_kline_cek(sembol, d, bas - datetime.timedelta(days=isinma_gun), bit)
        if not veri[d]:
            return None
    try:
        json_yaz(yol, {d: [{k: m[k] for k in ("zaman", "acilis", "yuksek", "dusuk", "kapanis")} for m in v]
                       for d, v in veri.items()})
    except Exception:
        pass
    return veri


def bt_kaynak(veri, t):
    """t anında botun göreceği veri: yalnızca kapanmış mumlar (+ 1day için bugünün
    1h mumlarından oluşan oluşum hâlindeki günlük mum, anahtar seviyeler için)."""
    dts = {d: [m["dt"] for m in v] for d, v in veri.items()}

    def kaynak(sembol, aralik, adet):
        dk = BT_ARALIK[aralik][1]
        v = veri[aralik]
        son = indeks_bul(dts[aralik], t - datetime.timedelta(minutes=dk) + datetime.timedelta(seconds=1))
        sonuc = v[max(0, son - adet):son]
        if aralik == "1day":
            gun = datetime.datetime(t.year, t.month, t.day)
            bugun = [m for m in veri["1h"][indeks_bul(dts["1h"], gun):indeks_bul(dts["1h"], t - datetime.timedelta(minutes=59))]]
            if bugun:
                sonuc = sonuc + [{"zaman": zaman_yaz(gun), "dt": gun, "acilis": bugun[0]["acilis"],
                                  "yuksek": max(m["yuksek"] for m in bugun), "dusuk": min(m["dusuk"] for m in bugun),
                                  "kapanis": bugun[-1]["kapanis"]}]
        return [dict(m) for m in sonuc]
    return kaynak


def bt_islem_simule(islem, m1h, bas_i):
    """1h mumlarla emir/işlem simülasyonu (long/short)."""
    long_mu = islem["yon"] == "LONG"
    g, sl, tps = islem["giris"], islem["stop"], islem["tps"]
    tp1 = tps[0]
    tp2 = tps[1] if len(tps) > 1 else tps[0]
    ters = (lambda a, b: a <= b) if long_mu else (lambda a, b: a >= b)   # fiyat a, seviye b'ye "aşağı" ulaştı mı
    ileri = (lambda a, b: a >= b) if long_mu else (lambda a, b: a <= b)
    dus = (lambda m: m["dusuk"]) if long_mu else (lambda m: m["yuksek"])
    yuk = (lambda m: m["yuksek"]) if long_mu else (lambda m: m["dusuk"])
    if bas_i >= len(m1h):
        # Sinyal test döneminin son saatinde: sonrası için mum yok
        islem["sonuc"] = "bekliyor (veri bitti)"
        return islem
    dolum_i = bas_i if islem["giris_turu"] == "PİYASA" else None
    if dolum_i is None:
        for j in range(bas_i, len(m1h)):
            if (m1h[j]["dt"] - m1h[bas_i]["dt"]).total_seconds() > BACKTEST_LIMIT_MAX_SAAT * 3600:
                islem["sonuc"] = "iptal (limit zaman aşımı)"
                return islem
            if ters(dus(m1h[j]), g):
                dolum_i = j
                break
            if ileri(yuk(m1h[j]), tp1):
                islem["sonuc"] = "iptal (giriş gelmeden TP1)"
                return islem
        if dolum_i is None:
            islem["sonuc"] = "bekliyor (veri bitti)"
            return islem
    islem["dolum_zamani"] = zaman_yaz(m1h[dolum_i]["dt"])
    risk = abs(g - sl)
    r_tp1 = abs(tp1 - g) / risk
    r_tp2 = abs(tp2 - g) / risk
    tp1_alindi = False
    aktif_sl = sl
    for j in range(dolum_i, len(m1h)):
        m = m1h[j]
        if ters(dus(m), aktif_sl):
            islem["cikis_zamani"] = zaman_yaz(m["dt"])
            if tp1_alindi:
                kalan = 0.0 if aktif_sl == g else -0.5
                islem["sonuc"] = "TP1 + girişte stop" if aktif_sl == g else "TP1 + stop"
                islem["R_tp1"], islem["R_kademeli"] = r_tp1, 0.5 * r_tp1 + kalan
            else:
                islem["sonuc"], islem["R_tp1"], islem["R_kademeli"] = "stop", -1.0, -1.0
            return islem
        if j > dolum_i:  # dolum mumunda hedef sayılmaz (sıra bilinmez; muhafazakâr)
            if not tp1_alindi and ileri(yuk(m), tp1):
                tp1_alindi = True
                islem["R_tp1"] = r_tp1
                if BACKTEST_TP1_SONRA_GIRISE:
                    aktif_sl = g
            if tp1_alindi and ileri(yuk(m), tp2):
                islem["cikis_zamani"] = zaman_yaz(m["dt"])
                islem["sonuc"], islem["R_kademeli"] = "TP1 + TP2", 0.5 * r_tp1 + 0.5 * r_tp2
                return islem
        if (m["dt"] - m1h[dolum_i]["dt"]).total_seconds() > BACKTEST_MAX_ISLEM_SAAT * 3600:
            r_son = (m["kapanis"] - g) / risk * (1 if long_mu else -1)
            islem["cikis_zamani"] = zaman_yaz(m["dt"])
            islem["sonuc"] = "zaman aşımı (piyasadan kapatıldı)"
            islem["R_tp1"] = r_tp1 if tp1_alindi else r_son
            islem["R_kademeli"] = 0.5 * r_tp1 + 0.5 * r_son if tp1_alindi else r_son
            return islem
    r_son = (m1h[-1]["kapanis"] - g) / risk * (1 if long_mu else -1)
    islem["sonuc"] = "açık (veri bitti)"
    islem["R_tp1"] = r_tp1 if tp1_alindi else round(r_son, 2)
    islem["R_kademeli"] = 0.5 * r_tp1 + 0.5 * r_son if tp1_alindi else round(r_son, 2)
    return islem


def backtest_calistir(gun=None, sembol_sayisi=None):
    global ISTATISTIK_AKTIF, dilim_analiz
    gun = gun or BACKTEST_GUN
    sembol_sayisi = sembol_sayisi or BACKTEST_SEMBOL_SAYISI
    dizin = os.path.join(TEMEL_DIZIN, "backtest")
    veri_dizin = os.path.join(dizin, "veri")
    os.makedirs(veri_dizin, exist_ok=True)
    yollari_ayarla(dizin)
    ISTATISTIK_AKTIF = False
    simdi = simdi_utc().replace(minute=0, second=0, microsecond=0)
    bit = simdi
    bas = bit - datetime.timedelta(days=gun)
    if BACKTEST_SEMBOLLER:
        semboller = list(BACKTEST_SEMBOLLER)
    else:
        # Canlı taramayla aynı evren: Twelve Data'da X/USD karşılığı olan hacimli çiftler
        sira, _ = binance_hacim_sirasi()
        td = twelvedata_kripto_seti()
        semboller = [b + "/USD" for b, _ in (sira or []) if td is None or (b + "/USD") in td][:sembol_sayisi]
        semboller = semboller or KRIPTO_SABIT[:sembol_sayisi]
    eslesmeler = [e for e in eslesmeleri_coz() if "15min" not in e]
    print("=" * 60)
    print("GERİYE DÖNÜK TEST | %s -> %s UTC | %d gün | %d sembol | adım %d saat" % (
        zaman_yaz(bas), zaman_yaz(bit), gun, len(semboller), BACKTEST_ADIM_SAAT))
    print("Semboller: " + ", ".join(semboller))
    if BACKTEST_ESLESME_HARIC or BACKTEST_GIRIS_TURU_HARIC or BACKTEST_MIN_SKOR is not None:
        print("Filtre: eşleme_haric=%s giris_haric=%s min_skor=%s" %
              (BACKTEST_ESLESME_HARIC or "-", BACKTEST_GIRIS_TURU_HARIC or "-", BACKTEST_MIN_SKOR))
    print("Uyarı: bugünkü hacim listesi geçmişe uygulanır (hayatta kalma yanlılığı olabilir).")
    orijinal_analiz = dilim_analiz
    tum_islemler, kacan = [], []
    baslangic = time.time()
    for sn, sembol in enumerate(semboller, 1):
        print("[%d/%d] %s verisi çekiliyor..." % (sn, len(semboller), sembol))
        veri = bt_veri_hazirla(sembol, bas, bit, veri_dizin)
        if not veri:
            print("  veri alınamadı, atlandı")
            continue
        onbellek = {}

        def analiz_onbellekli(mumlar, dilim, ob_mod=None, breaker_mod=None):
            anahtar = (dilim, len(mumlar), mumlar[0]["dt"], mumlar[-1]["dt"], mumlar[-1]["kapanis"], ob_mod, breaker_mod)
            if anahtar not in onbellek:
                if len(onbellek) > 40:
                    onbellek.clear()
                onbellek[anahtar] = orijinal_analiz(mumlar, dilim, ob_mod, breaker_mod)
            return onbellek[anahtar]
        dilim_analiz = analiz_onbellekli
        m1h = veri["1h"]
        dts1h = [m["dt"] for m in m1h]
        gorulen = {}
        t = bas
        while t <= bit:
            try:
                sonuc = sembol_tara(sembol, eslesmeler, bt_kaynak(veri, t), t, IstatistikToplayici(), [], {})
            except Exception as e:
                print("  %s hata: %s" % (zaman_yaz(t), e))
                t += datetime.timedelta(hours=BACKTEST_ADIM_SAAT)
                continue
            for k in sonuc.get("kurulumlar", []):
                if k["asama"] not in ("sinyal", "kacti") or not k.get("tps") or k.get("stop") is None:
                    continue
                kid = kurulum_id(k)
                if kid in gorulen:
                    continue
                gorulen[kid] = t
                gd = k.get("giris_durum") or {}
                if k["asama"] == "kacti":
                    kacan.append({"sembol": sembol, "zaman": zaman_yaz(t), "tip": k["tip"], "yon": k["yon"],
                                  "neden": (k["notlar"] or [""])[0][:120]})
                    continue
                # 24 saat içinde aynı sembol+yön+bölge tekrarı alınmaz (CSV kuralı)
                if any(x["sembol"] == sembol and x["yon"] == k["yon"] and
                       ortust(x["giris_alt"], x["giris_ust"], k["giris_alt"], k["giris_ust"]) and
                       (t - zaman_coz(x["sinyal_zamani"])).total_seconds() < TEKRAR_YAZMA_SAAT * 3600
                       for x in tum_islemler):
                    continue
                agresif = "SFP_AGRESIF" in k.get("anahtar_dt", "")
                if gd.get("durum") == "aktif":
                    tur, giris = "PİYASA", gd["fiyat"]
                else:
                    tur, giris = ("AGRESİF" if agresif else "LİMİT"), k["giris"]
                if k["eslesme"] in BACKTEST_ESLESME_HARIC or tur in BACKTEST_GIRIS_TURU_HARIC or \
                        (BACKTEST_MIN_SKOR is not None and k["skor"] < BACKTEST_MIN_SKOR):
                    continue
                islem = {"sembol": sembol, "eslesme": k["eslesme"], "tip": k["tip"], "yon": k["yon"],
                         "giris_turu": tur, "sinyal_zamani": zaman_yaz(t), "tetik": k.get("zaman", ""),
                         "giris": giris, "oneri_giris": k["giris"], "giris_alt": k["giris_alt"], "giris_ust": k["giris_ust"],
                         "stop": k["stop"], "tps": [p for p, _ in k["tps"]][:2], "skor": k["skor"],
                         "ham_puan": k["ham_puan"], "konseptler": konsept_etiketi(k), "sonuc": "", "dolum_zamani": "",
                         "cikis_zamani": "", "R_tp1": 0.0, "R_kademeli": 0.0}
                bas_i = indeks_bul(dts1h, t)
                try:
                    bt_islem_simule(islem, m1h, bas_i)
                except Exception as e:  # tek bir emirdeki hata tüm testi durdurmasın
                    print("  %s simülasyon hatası: %s" % (zaman_yaz(t), e))
                    continue
                tum_islemler.append(islem)
            t += datetime.timedelta(hours=BACKTEST_ADIM_SAAT)
        n = sum(1 for x in tum_islemler if x["sembol"] == sembol)
        print("  %d emir (%.0f sn)" % (n, time.time() - baslangic))
    dilim_analiz = orijinal_analiz
    bt_rapor_yaz(dizin, tum_islemler, kacan, bas, bit, semboller)


def bt_ozet(liste):
    dolan = [x for x in liste if x["dolum_zamani"]]
    kapanan = [x for x in dolan if x["cikis_zamani"] or x["sonuc"].startswith("zaman")]
    kazanan = [x for x in kapanan if x["R_kademeli"] > 0]
    toplam = sum(x["R_kademeli"] for x in dolan)
    return {"emir": len(liste), "dolan": len(dolan), "kapanan": len(kapanan),
            "isabet": (100.0 * len(kazanan) / len(kapanan)) if kapanan else 0.0,
            "toplam_R": toplam, "ort_R": toplam / len(dolan) if dolan else 0.0,
            "toplam_R_tp1": sum(x["R_tp1"] for x in dolan)}


def bt_rapor_yaz(dizin, islemler, kacan, bas, bit, semboller):
    yol_csv = os.path.join(dizin, "islemler_%s.csv" % bit.strftime("%Y-%m-%d_%H-%M"))
    kolonlar = ["sembol", "eslesme", "tip", "yon", "giris_turu", "sinyal_zamani", "tetik", "giris", "oneri_giris",
                "stop", "tp1", "tp2", "skor", "ham_puan", "dolum_zamani", "cikis_zamani", "sonuc", "R_tp1",
                "R_kademeli", "konseptler"]
    with open(yol_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(kolonlar)
        for x in sorted(islemler, key=lambda x: x["sinyal_zamani"]):
            ref = x["giris"]
            w.writerow([x["sembol"], x["eslesme"], x["tip"], x["yon"], x["giris_turu"], x["sinyal_zamani"], x["tetik"],
                        yuvarla(x["giris"], ref), yuvarla(x["oneri_giris"], ref), yuvarla(x["stop"], ref),
                        yuvarla(x["tps"][0], ref), yuvarla(x["tps"][-1], ref), x["skor"], x["ham_puan"],
                        x["dolum_zamani"], x["cikis_zamani"], x["sonuc"], round(x["R_tp1"], 2),
                        round(x["R_kademeli"], 2), x["konseptler"]])
    s = ["DD FINANCE PA BOTU – GERİYE DÖNÜK TEST (Binance gerçek verisi)", "=" * 60,
         "Dönem: %s -> %s UTC | Semboller (%d): %s" % (zaman_yaz(bas), zaman_yaz(bit), len(semboller), ", ".join(semboller)),
         "Tarama sıklığı: %d saat | Limit emir ömrü: %d saat | Çıkış: TP1 %%50 + TP2 %%50, TP1 sonrası stop %s" % (
             BACKTEST_ADIM_SAAT, BACKTEST_LIMIT_MAX_SAAT, "girişe" if BACKTEST_TP1_SONRA_GIRISE else "sabit"),
         "Giriş türleri: AGRESİF = SFP_AGRESIF limit | LİMİT = dolmamış girişe limit | PİYASA = dolmuş ama geçerli, güncel fiyattan",
         "Not: geçmiş sonuç geleceği garanti etmez; komisyon/kayma dahil değildir."]
    if BACKTEST_ESLESME_HARIC or BACKTEST_GIRIS_TURU_HARIC or BACKTEST_MIN_SKOR is not None:
        s.append("Filtre: eşleme_haric=%s giris_haric=%s min_skor=%s" %
                 (BACKTEST_ESLESME_HARIC or "-", BACKTEST_GIRIS_TURU_HARIC or "-", BACKTEST_MIN_SKOR))
    s.append("")

    def satir(ad, o):
        return "  %-26s emir %4d | dolan %4d | isabet %5.1f%% | toplam %+7.2fR | ort %+5.2fR/işlem | (hepsi TP1: %+7.2fR)" % (
            ad, o["emir"], o["dolan"], o["isabet"], o["toplam_R"], o["ort_R"], o["toplam_R_tp1"])
    s.append("GENEL")
    s.append(satir("Tümü", bt_ozet(islemler)))
    for baslik, anahtar in (("GİRİŞ TÜRÜNE GÖRE", "giris_turu"), ("KURULUM TİPİNE GÖRE", "tip"),
                            ("EŞLEŞMEYE GÖRE", "eslesme"), ("SKORA GÖRE", "skor"), ("YÖNE GÖRE", "yon")):
        s.append("")
        s.append(baslik)
        for deger in sorted(set(str(x[anahtar]) for x in islemler)):
            s.append(satir(deger, bt_ozet([x for x in islemler if str(x[anahtar]) == deger])))
    s.append("")
    s.append("SEMBOLE GÖRE")
    for sem in semboller:
        alt = [x for x in islemler if x["sembol"] == sem]
        if alt:
            s.append(satir(sem, bt_ozet(alt)))
    # En büyük düşüş (R, kümülatif)
    egri, tepe, dd = 0.0, 0.0, 0.0
    for x in sorted([x for x in islemler if x["cikis_zamani"]], key=lambda x: x["cikis_zamani"]):
        egri += x["R_kademeli"]
        tepe = max(tepe, egri)
        dd = min(dd, egri - tepe)
    s.append("")
    s.append("En büyük düşüş (kümülatif, kademeli çıkış): %.2fR" % dd)
    sonuc_say = {}
    for x in islemler:
        sonuc_say[x["sonuc"]] = sonuc_say.get(x["sonuc"], 0) + 1
    s.append("Sonuç dağılımı: " + ", ".join("%s: %d" % kv for kv in sorted(sonuc_say.items())))
    s.append("Sinyal anında girişi zaten kaçmış (emir açılmayan) kurulum: %d" % len(kacan))
    yol_txt = os.path.join(dizin, "ozet_%s.txt" % bit.strftime("%Y-%m-%d_%H-%M"))
    with open(yol_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")
    print("\n".join(s))
    print("\nİşlem listesi: %s\nÖzet: %s" % (yol_csv, yol_txt))


# =============================================================================
#                                 GİRİŞ NOKTASI
# =============================================================================

if __name__ == "__main__":
    argumanlar = sys.argv[1:]
    if "--test" in argumanlar:
        sys.exit(0 if testleri_calistir() else 1)
    elif "--backtest" in argumanlar:
        sayilar = [int(x) for x in argumanlar if x.isdigit()]
        if "--no-1d4h" in argumanlar:
            BACKTEST_ESLESME_HARIC.append("1day→4h")
        if "--no-piyasa" in argumanlar:
            BACKTEST_GIRIS_TURU_HARIC.append("PİYASA")
        for a in argumanlar:
            if a.startswith("--min-skor="):
                BACKTEST_MIN_SKOR = int(a.split("=")[1])
        backtest_calistir(sayilar[0] if sayilar else None, sayilar[1] if len(sayilar) > 1 else None)
    elif "--demo" in argumanlar:
        yollari_ayarla(os.path.join(TEMEL_DIZIN, "demo"))
        os.makedirs(YOLLAR["dizin"], exist_ok=True)
        CACHE_AKTIF = False
        tarama(demo_kaynak(simdi_utc()))
    else:
        main()
