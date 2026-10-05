"""Phantom SMC tarama botu ayarları. Tüm eşikler burada tutulur."""
import os

# Ana klasör ve çıktı klasörleri
BASE_DIR = os.path.expanduser("~/Documents/phantom_bot")  # Bot ve çıktılar için ana klasör
CACHE_DIR = os.path.join(BASE_DIR, "cache")  # API mum önbelleği
SCANS_DIR = os.path.join(BASE_DIR, "scans")  # Tarama raporları
LOGS_DIR = os.path.join(BASE_DIR, "logs")  # Çalışma günlükleri
NEWS_CSV = os.path.join(BASE_DIR, "news.csv")  # Kullanıcının elle tuttuğu haber takvimi

# Twelve Data
TWELVEDATA_API_KEY = "BURAYA_ANAHTAR"  # Gerçek anahtar config_local.py içinde tutulur  # Kullanıcı bu anahtarı kendisi düzeltebilir
TWELVEDATA_BASE_URL = "https://api.twelvedata.com"  # Forex ve altın veri alan adı
TWELVEDATA_TIME_SERIES_PATH = "/time_series"  # Mum verisi uç noktası
FOREX_SYMBOLS = ["EUR/USD", "GBP/USD", "GBP/JPY", "EUR/JPY", "AUD/USD", "NZD/USD", "USD/CAD", "EUR/GBP", "XAU/USD"]  # Varsayılan forex ve altın evreni
ENABLE_1M = False  # Ayrılmış ayar (Bölüm 11.16): 1 dakikalık veri ilk sürümde kullanılmaz
TWELVEDATA_OUTPUTSIZE = 500  # İstek başına istenen mum sayısı
REQUEST_DELAY_TD = 8.0  # Twelve Data istekleri arasındaki asgari bekleme saniyesi
TD_CACHE_TTL_SECONDS = {"1day": 21600, "4h": 3600}  # Günlük 6 saat, 4 saatlik 1 saat önbellek süresi
TD_TIMEOUT_SECONDS = 20  # HTTP bağlantı zaman aşımı

# Binance public spot API
BINANCE_BASE_URLS = ["https://api.binance.com", "https://data-api.binance.vision"]  # Ana ve yedek alan adları
BINANCE_TICKER_24HR_PATH = "/api/v3/ticker/24hr"  # 24 saatlik spot hacimleri
BINANCE_KLINES_PATH = "/api/v3/klines"  # Mum verisi uç noktası
BINANCE_KLINE_LIMIT = 500  # İstek başına mum sayısı
CRYPTO_TOP_DEFAULT = 35  # Hacme göre varsayılan seçilecek coin sayısı
CRYPTO_TOP_MIN = 30  # İzin verilen en düşük coin sayısı
CRYPTO_TOP_MAX = 40  # İzin verilen en yüksek coin sayısı
BINANCE_REQUEST_DELAY = 0.25  # Binance istekleri arasındaki bekleme saniyesi
BINANCE_RATE_LIMIT_WAIT = 60  # HTTP 418/429 için uzun bekleme saniyesi
BINANCE_TIMEOUT_SECONDS = 20  # HTTP bağlantı zaman aşımı
BINANCE_QUOTE_ASSET = "USDT"  # Evrene alınacak spot quote varlığı
BINANCE_EXCLUDED_BASES = ["USDC", "FDUSD", "TUSD", "DAI", "USDP", "EUR", "BUSD", "USD1", "RLUSD"]  # Hariç tutulan stablecoin tabanları
BINANCE_LEVERAGED_MARKERS = ["UP", "DOWN", "BULL", "BEAR"]  # Kaldıraçlı token SONEKLERİ (BTCUP, ETHDOWN); ana varlığı da USDT'de listeliyse elenir
EXCLUDED_SYMBOLS = ["UUSDT", "USD1USDT", "RLUSDUSDT",  # Stable benzeri varlıklar
                    "XAUTUSDT", "PAXGUSDT",  # Altın tokenları
                    "CRCLBUSDT", "SPCXBUSDT", "SNDKBUSDT"]  # Tokenize hisseler (sonu B); yenileri elle ekleyin

# Piyasa yapısı ve indikatör eşikleri
SWING_N = 2  # Swing onayı için her iki taraftaki mum sayısı
SWING_N_MAJOR = 5  # Majör yapı kırılımı için swing onayı mum sayısı
SWEEP_LOOKBACK = 5  # BOS öncesi sweep aranacak ek mum sayısı
ATR_PERIOD = 14  # ATR hesaplama periyodu
V_MAX_CANDLES = 3  # V dönüşü için dönüş bacağının en fazla mum sayısı
V_BODY_ATR = 1.5  # V dönüşünde ortalama gövdenin ATR katsayısı
CORRECTIVE_MIN_CANDLES = 4  # Corrective dönüş için en az mum sayısı
CORRECTIVE_BODY_ATR = 1.0  # Corrective dönüşte ortalama gövdenin ATR üst sınırı
DISPLACEMENT_ATR = 1.2  # OB rafinesinde momentum gövdesinin ATR katsayısı
STRONG_BOS_ATR = 1.5  # Güçlü BOS için gövde/ATR alt sınırı
EQ_TOL_ATR = 0.1  # EQH/EQL eşleşme toleransı
MAX_TOUCHES = 2  # OB bu sayıda ziyarette mitigate kabul edilir
REQUIRE_FVG_FOR_OB = False  # OB bacağında FVG bulunmasını zorunlu kıl

# Seanslar (New York yerel saati)
SESSIONS = [  # Ad, başlangıç, bitiş, aktiflik
    ("ASIA", "20:00", "00:00", True),  # Asya seansı ve günlük Asya aralığı
    ("LNDN", "02:00", "05:00", True),  # London seansı
    ("NYAM", "09:30", "11:00", True),  # New York sabah seansı
    ("NYL", "12:00", "13:00", False),  # Pasif New York öğle seansı
    ("NYPM", "13:30", "16:00", True),  # New York öğleden sonra seansı
    ("RTH", "09:30", "16:00", False),  # Pasif normal işlem saatleri
]
SPREAD_HOUR = ("16:45", "18:15")  # New York saatiyle rollover uyarı aralığı
SUNDAY_HOURS = 6  # Pazar açılışından sonra kısıt uygulanan saat sayısı
NEWS_WINDOW_MIN = 30  # Yüksek etkili haber öncesi/sonrası filtre dakikası

# Spread ve pip değerleri
FOREX_SPREAD_PIPS = {"EUR/USD": 0.8, "GBP/USD": 1.0, "AUD/USD": 1.0, "NZD/USD": 1.5, "USD/CAD": 1.5, "EUR/GBP": 1.2, "EUR/JPY": 1.5, "GBP/JPY": 2.5, "XAU/USD": 3.0, "DEFAULT": 1.5}  # Sembol bazlı varsayılan spread pipleri
PIP_SIZE_JPY = 0.01  # JPY paritelerinin pip büyüklüğü
PIP_SIZE_XAU = 0.1  # Altının pip büyüklüğü
PIP_SIZE_DEFAULT = 0.0001  # Diğer forex paritelerinin pip büyüklüğü

# Setup puan ağırlıkları (Bölüm 6.8)
SCORE_WEIGHTS = {  # Kriter başına puan
    "htf_alignment": 20, "stack_3tf": 20, "stack_2tf": 12, "stack_1tf": 5,
    "fresh_ob": 8, "extreme_ob": 7, "sweep_then_bos": 10, "mitigated_left_zone": 4,
    "fvg": 6, "major_structure_break": 8, "inducement": 5, "premium_discount": 7,
    "corrective_return": 5, "preferred_session": 5, "v_reversal_penalty": -10,
    "asia_confirmation_penalty": -5, "news_penalty": -10, "counter_trend_penalty": -15,
}  # Pozitif ve negatif puanlar
SCORE_MIN_REPORT = 45  # Altındaki adaylar varsayılan raporda gösterilmez
SCORE_GRADE_A = 75  # A notunun alt sınırı
SCORE_GRADE_B = 60  # B notunun alt sınırı
SCORE_GRADE_C = 45  # C notunun alt sınırı
SCORE_MAX = 100  # Puan üst sınırı
MIN_RR_TP2 = 5.0  # TP2 için minimum risk/getiri oranı

# POI ve giriş/stop kuralları
MAX_POI_PER_SYMBOL_DIR = 3  # Her sembol+yön için CSV/JSON'daki en yüksek puanlı aday sayısı
DISTAL_ENTRY_MAX_PIPS = 5.0  # Forex confirmation girişinde distal'e yakınlık üst sınırı
CRYPTO_DISTAL_ENTRY_MAX_ATR = 0.35  # Kripto confirmation girişinde distal mesafesi ATR katsayısı
FOREX_STOP_BUFFER_MIN_PIPS = 0.5  # Forex stop tamponunun asgari pip değeri
FOREX_MIN_STOP_PIPS = 3.0  # Forex minimum stop mesafesi
CRYPTO_STOP_BUFFER_ATR = 0.1  # Kripto stop tamponu ATR katsayısı
CRYPTO_MIN_STOP_PCT = 0.25  # Kripto minimum stop yüzdesi
MAX_POI_DISTANCE_ATR_D1 = 3.0  # POI girişinin son fiyata azami günlük ATR mesafesi
ACTIONABLE_DISTANCE_PCT = {"crypto": 10.0, "forex": 1.0}  # Girişin son fiyata azami yüzde uzaklığı; aşanlar yalnızca "Uzak POI'ler" bölümünde görünür

# Yerel zaman dilimi
NEW_YORK_TIMEZONE = "America/New_York"  # New York saat dilimi adı

# Yerel geçersiz kılmalar (API anahtarı vb.); config_local.py yoksa sessizce atlanır
try:
    import config_local as _config_local  # git'e eklenmez
    for _name in dir(_config_local):
        if _name.isupper():
            globals()[_name] = getattr(_config_local, _name)
    del _config_local
except ImportError:
    pass
