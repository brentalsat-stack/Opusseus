# Opusseus

Bu depoda iki ayrı proje bulunur: `claude_code_paketi/`, `dd_finance_tarama_botu/` (mevcut) ve
**Photon Trade** iskeleti (`photon/`, `config.yaml`, aşağıda).

## Photon Trade — iskelet

Sinyal + backtest (otomatik emir yok). Kaynak belgeler: `FINAL_SPEC.md`, `RULE_DATABASE.md`,
`IMPLEMENTATION_BLOCKERS.md`, `DECISIONS.md`. **Bu aşamada strateji mantığı yoktur**; yalnızca
yapı, config + fail-fast doğrulayıcı, zaman/veri temelleri ve logging vardır.

### Kurulum

```bash
python3 --version                 # 3.11+ gerekir
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # PyYAML, tzdata, pytest
pytest                            # 50 test
python -m photon check            # modül durumları + bekleyen (REQUIRED) alanlar
python -m photon check --module structure --module risk   # hazır değilse çıkış kodu 2
```

### Yapı (FINAL_SPEC §23)

`photon/{config,data,structure,zones,liquidity,strategy,risk,execution,signals,backtest,journal,tests}`.
Yalnızca `config`, `data` (tz + `Candle`) ve `logging_setup` içeriklidir; diğerleri docstring'li iskelettir.

### Config ve fail-fast

`config.yaml`: DECISIONS.md'de **KARAR** olanlar yazılı, **BEKLİYOR** olanlar `REQUIRED`.
Her modül `photon/config/schema.py` içinde kendi zorunlu alanlarını tanımlar:

```python
from photon.config import load_config
cfg = load_config()
cfg.require("structure")   # eksik/REQUIRED/geçersiz varsa ConfigError — tüm eksikler listelenir
```

| Durum | Modüller |
|---|---|
| Hazır (DECISIONS v2.0 sonrası) | `data`, `structure` (D1/H4/M15), `risk`, `risk_sizing`, `session`, `session_blackout`, `zones`, `management`, `execution`, `journal` |
| Alan bekliyor | `structure_m1` (M1 swing eşiği, MS-R010 kalibrasyonu), `liquidity` (`v_shape_metric`, Aşama 4 önerisi) ve bunlara bağlı `strategy`, `signals`, `backtest` |

Kaynakta/karar dosyasında olmayan hiçbir değere varsayılan atanmaz. Kendi değerlerinizi
`config.yaml` içinde `REQUIRED` yerine yazarak modülleri açarsınız.

### Tasarım ilkeleri

- Fiyatlar `Decimal` (YAML float'ları yüklerken `Decimal`'e çevrilir; `Candle` float reddeder).
- Zaman damgaları UTC saklanır; çeviri IANA ile (`Europe/London`, `Europe/Istanbul`), DST otomatik
  (`photon/data/tz.py`).
- Pariteler ve parite bazlı parametreler (`pair_params`, `swing_min_pullback_pips`) config'den; yeni
  parite eklemek config'e girdi eklemektir, kod değişmez.
- Logging: ekran + döner dosya (`logging.file`, UTC damgalı) — `photon.logging_setup.setup_from_config(cfg)`.

### Veri katmanı (Aşama 1)

```bash
# Dukascopy (hesap gerekmez) veya OANDA practice (export OANDA_API_TOKEN=...)
python -m photon fetch --source DUKASCOPY --start 2021-09-01 --end 2021-09-30 --csv data_samples/EURUSD_M1_2021-09.csv
python -m photon data-check --source DUKASCOPY --start 2021-09-01 --end 2021-09-30   # düzeltmeden raporlar
```

- `photon/data/sources/`: `dukascopy.py` (saatlik .bi5 tick → M1, ham dosyalar diskte önbellekte, 429'da bekleyip yeniden dener),
  `oanda.py` (v20 practice, `price=BA`, yalnızca okuma uç noktası, jeton ortam değişkeninde), `ibkr.py` (ib_async, `readonly=True`, emir kodu yok).
- `resample.py`: tick→M1→M15→H4→D1 (bid ve ask ayrı OHLC); eksik dakikalar doldurulmaz, sırasız girdi hata verir.
- `validate.py`: tekrar / sırasız / eksik / hafta sonu boşluğu raporu (asla sessizce düzeltmez; T-DATA-01).
- `cache.py`: SQLite (fiyatlar TEXT=Decimal birebir); indirme parça parça, kesintide devam eder.
- Kaynak seçimi: `--source`, verilmezse `data.backtest.primary`.

**IMPLEMENTATION DECISION REQUIRED**
- **Q-D01 — H4/D1 mum sınırları:** kaynakta tanımsız. `candle_boundaries.{tz,d1_open,h4_anchor}` `REQUIRED`; H4/D1 üretimi karar gelene kadar başlamaz (M1/M15 etkilenmez).
  Seçenek örneği (kaynakta yok): NY 17:00 kapanışı. Uygulanan kural: D1 = `d1_open`'dan sonraki `d1_open`'a (DST günleri 23/25 sa); H4 = `h4_anchor`'dan 4 saatlik adımlar, her `h4_anchor`'da sıfırlanır.
- **Q-D02 — Yapı hangi fiyatla:** `candle_price_side` (BID|ASK) `REQUIRED`; mid üretilmez. Spread/maliyet için bid+ask birlikte saklanır.
- **Q-D03 — Hafta sonu etiketi:** raporlamada, Cuma (UTC) başlayıp Pazar/Pzt biten ve Cumartesi'yi tamamen kapsayan boşluk `WEEKEND_GAP`; diğer boşluklar `MISSING`. Yalnızca etiket, veri değişmez.
- **Q-D04 — OANDA S5/tick:** uygulanmadı (OANDA tick sunmuyor; S5 için `Timeframe` kaynakta yok). Intrabar çözümü Aşama 7'de Dukascopy tick ile.

### Açık sorular

- Kalan `REQUIRED`: `swing_min_pullback_pips.EURUSD.M1` (kalibrasyon sonucu), `v_shape_metric` (Aşama 4'te önerilip onaylanacak).
- `zone_draw_mode.M15: CANDLE` ve `range_extreme_filter.range_tf: M15` onaylandı.
- `pair_params.EURUSD.units_per_lot: 100000` standart lot varsayımıdır (sinyalde birim göstermek için).
