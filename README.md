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
| Bekleyen alandan bağımsız (hazır) | `data`, `structure` (D1/H4/M15), `risk`, `session`, `execution`, `journal` |
| Alan bekliyor | `structure_m1` (U-13), `risk_sizing` (broker bilgisi), `session_blackout` (C-09), `zones`, `liquidity`, `strategy`, `management`, `signals`, `backtest` |

Kaynakta/karar dosyasında olmayan hiçbir değere varsayılan atanmaz. Kendi değerlerinizi
`config.yaml` içinde `REQUIRED` yerine yazarak modülleri açarsınız.

### Tasarım ilkeleri

- Fiyatlar `Decimal` (YAML float'ları yüklerken `Decimal`'e çevrilir; `Candle` float reddeder).
- Zaman damgaları UTC saklanır; çeviri IANA ile (`Europe/London`, `Europe/Istanbul`), DST otomatik
  (`photon/data/tz.py`).
- Pariteler ve parite bazlı parametreler (`pair_params`, `swing_min_pullback_pips`) config'den; yeni
  parite eklemek config'e girdi eklemektir, kod değişmez.
- Logging: ekran + döner dosya (`logging.file`, UTC damgalı) — `photon.logging_setup.setup_from_config(cfg)`.

### Açık sorular

- `pair_params.*.pip_value_per_lot / lot_step / min_lot`: FM-02 girdileri, DECISIONS'ta değer yok → `REQUIRED`.
- `target_allocation.counter_trend / range` oranları, `costs.commission`, `news_filter.*`, `blackout.tz`: BEKLİYOR.
- `risk_pct` DECISIONS'a göre `0.01` (FINAL_SPEC §26 örneği `0.005`); tavan 0.01 olarak doğrulanır.
