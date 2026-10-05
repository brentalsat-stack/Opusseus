# Phantom Trading 1.0 (Part 2): Kural Raporu

**Kaynak:** `phantom 1.0.part2` klasörü: 102 dosya. İçlerinde 49 video/ses dosyası, `.txt`, `.docx` ve `.rtf` notlar, Discord PDF'leri (FAQ, top-tips, psychology) ve şema görselleri var.

**Klasör kontrolü (detaylı, bayt bazında):**
- Part 2'deki 102 dosya Part 1'deki karşılıklarıyla **bayt bayt** (`cmp`) karşılaştırıldı: 77 küçük dosya (PDF, görsel, not ve kısa videolar) ve 25 büyük video. Aşağıdaki boş dosya dışında 101 dosyanın hepsi **birebir aynı**. Part 2, Part 1'in bir **alt kümesidir**; **Part 1'de olmayan yeni bir video veya belge yok.**
  - İlk taramada bazı dosyalar "farklı" çıktı. Tekrar okununca hepsinin aynı olduğu görüldü; farkı disk/senkron okuma hatası yaratmıştı, dosyaların içeriği değil.
- `1 [Phantom] - Market Structure/NEW/4.1 - Application - Understanding Change in Trend.mp4` Part 2'de **0 bayt, yani bozuk/boş** (Part 1'deki sağlam kopya 842 MB, 31,6 dk). İçeriği Part 1'deki sağlam kopyadan alındı. Bu klasör için dosyanın yeniden indirilmesi önerilir.
- Part 2'de Market Structure NEW 1.0–4.0 dersleri yok. Bu derslerdeki kurallar (HH/HL, BOS, CHoCH, swing/sub/minor yapı) Part 2'deki `OLD/0`, `OLD/1`, 5.0/5.1 ve Knowledge Bombs videolarında da işleniyor.

**Yöntem:**
- Videoların hiçbirinde altyazı yoktu. Ses kayıtları çevrimdışı bir konuşma tanıma modeliyle metne çevrildi.
- **İkinci (detaylı) kontrolde**, ilk raporda sadece taranan içerikler de **tamamen okundu**: tüm Market Commentary videoları (Eylül 2020 ve Şubat 2021), "Putting it All Together – GBPJPY", tüm Trade Recap'ler (EURUSD, GBPJPY, AUDUSD, EURGBP), Albert NZDUSD, uygulama videoları, psikoloji kayıtları ve Discord PDF'leri (team-trades, phantom-charts, phantom-resources).
- Bu kontrolden çıkan **ek kurallar Bölüm 4'te** toplandı.

> Not: Otomatik transkripsiyon bazı rakamları veya kelimeleri yanlış duymuş olabilir. Kritik sayısal kurallar (risk %, pip, R) mümkün olduğunda FAQ PDF'i ile çapraz kontrol edildi.

---

## 1. Genel Yöntem ve Metodoloji Özeti

### 1.1 Temel yaklaşım
Phantom stratejisi, **Smart Money Concepts (SMC) ve kurumsal Supply & Demand**'e dayanan bir price action sistemidir. Birbirine bağlı 5 ana bileşeni vardır:

| Bileşen | İşlevi |
|---|---|
| **Market Structure** (Swing / Sub / Minor yapı, BOS, CHoCH, Protected/Targeted High-Low) | Yön ve trend (bias) belirler. "Structure is king." |
| **Supply & Demand / Order Block (OB)** | İşlem yapılacak bölgeyi (POI / AOI) verir. Kurumların "ayak izi" olarak görülür. |
| **Liquidity** (EQH/EQL, swing likiditesi, trendline, range, inducement, internal vs external) | Fiyatın nereye çekileceğini (hedef) ve hangi bölgenin gerçek olduğunu gösterir. |
| **Inefficiency / Imbalance** (3 mum FVG) | Fiyatın dönüp dolduracağı alanlar. Hedef ve ek teyit olarak kullanılır, **tek başına işlem sebebi değildir.** |
| **Mitigation / Order Flow** | Kurumların zarar eden pozisyonlarını kapatıp yeniden yüklemesi. Trendin devam niyetini ve ileride hedeflenecek "üretilmiş likiditeyi" gösterir. |

Ek teyit araçları: **Wyckoff** birikim/dağıtım şemaları (Spring, UTAD, SOS, LPS/LPSY) ve **Expectational Order Flow** (Blackwatch).

Temel felsefe:
- Fiyat bir likidite havuzundan diğerine hareket eder. Bunu yaparken supply/demand bölgeleri arasında dengesizliği giderir.
- "Trend is your friend." Continuation (trend yönlü) işlemler, reversal işlemlerinden daha kolay ve daha olasıdır.
- İlk giren olmak zorunda değilsin. Piyasa elini göstersin, sonra gir.

### 1.2 Zaman dilimleri (top-down)
| Katman | Zaman dilimi | Amaç |
|---|---|---|
| Bağlam | Aylık / Haftalık | Büyük trend, HTF inefficiency ve likidite hedefleri |
| Bias | **Günlük, 4H** | Swing yapı, beklenen order flow |
| POI | **1H (ve 4H)** | Order block / supply-demand bölgesinin tespiti |
| Rafine | **15M** | POI'yi daraltma (daha iyi R:R) |
| Yürütme | **5M / 3M / 1M** | Confirmation entry (LTF BOS ve yeni OB) |
| Yönetim | **1H** (scalp için 15M) | Stop'u swing dip/tepelerin altına/üstüne taşıma |

- Anlatıcının kendi seti: **Günlük, 4H, 15M, 1M**. Haftalık ve aylık yalnızca bağlam için.
- Kural: Birkaç zaman dilimi seç ve sadık kal. Aradığını bulmak için zaman dilimleri arasında atlama.
- Yeni başlayanlar için: **1H OB ve 15M rafine** ile başla. HTF'ye güven oluşunca 5M/1M girişlere geç.
- Önerilen pariteler: **EURUSD ve GBPJPY** (dar spread, yüksek likidite).

### 1.3 Piyasa koşulları ve seanslar
- **Trend:** HTF'de trend yönünde, pullback sonundaki higher low / lower high bölgelerinden işlem aranır.
- **Range / complex pullback:** Swing high ile swing low arasındaki her şey "complex pullback" sayılır. Aralığın **discount** yarısında alış, **premium** yarısında satış aranır. "**Don't diddle in the middle**": ortada işlem yapma.
- **Seanslar:**
  - **London Open / London Killzone** en çok hacim ve yön verir (Blackwatch'ın tercihi). **New York açılışı** da kullanılır.
  - **Asya seansı** düşük hacimlidir ve range/likidite (EQH/EQL) oluşturur. Tipik model: London açılışında Asya high/low'unun süpürülmesi.
  - Asya'da POI'ye gelen fiyat genellikle önce Asya tepesini/dibini süpürüp stop'ları alır. Anlatıcı "Asya'da işlem yapmayı sevmem" der.
- **Spread saatleri (rollover):** Bu saatlere açık bekleyen emirle girilecekse emir **iptal edilir**, çünkü 3–5 pip'lik stoplar kolayca tetiklenir.
- **Haberler:** Her pazar haftanın yüksek etkili haberleri takvime işlenir. Temel analiz işlem sebebi değildir, sadece risk farkındalığı için kullanılır.

---

## 2. Strateji ve Setup Detayları

> Tüm modellerde ortak ön şart **HTF bias'tır**: Günlük/4H swing yapısı hangi yöndeyse o yönde işlem aranır. Karşı-trend işlemler sadece HTF POI içinde, daha agresif yönetim ve düşük riskle yapılır.

---

### Model 0 – Market Structure Haritalama (tüm modellerin temeli)

**Tanım:** Tepe/dipleri ve kırılımları tutarlı bir kuralla işaretlemek.

**3 haritalama tipi** (birini seç, backtest et, sadık kal):
1. **Tip 1 (en muhafazakâr):** Yapı mum gövdeleriyle çizilir. BOS için önceki gövdenin üstünde/altında **gövde kapanışı** gerekir.
2. **Tip 2 (en yaygın, anlatıcının kullandığı):** Yapı **fitillerle** çizilir. BOS için fitilin üstünde/altında **gövde kapanışı** gerekir. Sadece fitille geçmek = likidite süpürmesi, BOS değil.
3. **Tip 3 (en agresif):** Fitille çizilir, fitille kırılım BOS sayılır. Daha çok sahte sinyal üretir.

**Kurallar:**
- **Uptrend:** HH + HL. Bir **HL ancak önceki tepe kırılınca onaylanır.** O ana kadar aradaki her şey complex pullback'tir.
- **Swing low (HL) olarak seçilecek nokta:** Tepeyi kıran hareketin **başladığı en düşük nokta** (origin). Emin olamazsan **line chart**'ta belirgin salınımlara bak.
- **BOS:** Trend yönünde yapı kırılımı (devam).
- **CHoCH (Change of Character):** Trendi değiştiren kırılım, yani uptrend'de HL'nin kırılması. **Tek CHoCH trend değişimini kanıtlamaz.** Yeni trend, **ikinci BOS** ile onaylanır (yeni LH oluşup LL kırılmalı).
- **3 yapı türü:**
  - **Swing structure:** Ana trend.
  - **Substructure:** Swing aralığı içindeki karşı-trend düzeltme. HL/LH'nin nerede oluşacağını gösterir.
  - **Minor structure:** Substructure'da CHoCH sonrası başlayan, trend yönlü yapı. Swing high/low'u hedefler.
- **Protected / Targeted:**
  - Bir dip, tepeyi almayı başarırsa → **protected low**.
  - Bir tepe, dibi almayı başaramazsa → **targeted high** (hedef).
  - Uptrend = protected lows + targeted highs. Downtrend = protected highs + targeted lows.
  - Uptrend'de demand respekte edilir, supply başarısız olur. Downtrend'de tersi geçerlidir.
- **Expectational Order Flow (Blackwatch):** HH oluştu → beklenti HL. HL onaylandı → beklenti HH. Beklenti, **swing low gövde kapanışıyla kırılana** kadar geçerlidir. Anlatıcının iddiası: yaklaşık %80 doğruluk.
- **Minimum pullback:** 1M grafikte en az yaklaşık **5 pip**'lik geri çekilme olmadan onu yapı sayma.

---

### Model 1 – Supply & Demand Bölge Oluşumu ve Haritalama

**Tanım:** Kurumsal emirlerin ayak izi olan bölgeleri çizmek.

**Bölge türleri:**
- **Range-created S/D:** Yatay konsolidasyon (en fazla **4–6 mum**; **8+ mum ise bir üst TF'ye geç**), ardından **hızlı genişleme** (expansion). Bölge = range'in en yüksek ile en düşük noktası.
- **Pivot-created S/D:** Keskin hareket, ardından ters yönde hızlı genişleme. Bölge = genişlemeden önceki son karşıt mum(lar).
- **Continuation modeli:** Yükseliş → range/pivot → yükseliş (Demand). Düşüş → range/pivot → düşüş (Supply).
- **Reversal modeli:** Yükseliş → range/pivot → düşüş (Supply). Düşüş → range/pivot → yükseliş (Demand). **Reversal modelleri istatistiksel olarak daha olasıdır.** Trend ilerledikçe continuation bölgelerinin tutma ihtimali azalır.

**Rafine teknikleri (LTF'ye inmeden):**
- **Inside bar:** Alt TF'de bir range'dir, bölge olarak kullanılır.
- **Uzun fitil:** Fitil içinde alt TF'de bir supply/demand vardır. Bölge yalnızca fitile daraltılabilir.
- Range içindeki **son karşıt mum(lar)**a daraltma yapılabilir.

**Geçerlilik ön şartı:** Bölgeden **güçlü ve hızlı bir kaçış** (displacement) olmalı. Yavaş sızarak çıkış = düşük hacim = bölge yok. Kaçış anında geri dönüyorsa da zayıf bölgedir.

**Asla:** Range'den ilk kırılımı/ilk tepkiyi trade etme. **Fiyatın bölgeye geri dönmesini bekle.**

---

### Model 2 – Return-to-Zone (Bölgeye Dönüş Filtresi)

**Dönüş tipleri ve olasılıkları:**
| Dönüş | Görünüm | Olasılık |
|---|---|---|
| **Rounded return** | Yavaşça kıvrılarak geri gelir, altında/üstünde likidite biriktirir | **Yüksek** |
| **Corrective return** | Merdiven gibi, karşı bölgeleri tüketerek gelir | **Yüksek** |
| **V-reversal return** | Bölge oluşur oluşmaz sert V ile geri gelir | **Düşük.** Order flow değişmiş olabilir; kaçın veya ek teyit iste |

- **Olumlu istisna:** Rounded veya corrective dönüşün **son bacağı** bölgeye impulsif girerse ("sucker's rally") ters yöndeki hareket daha sert olur.
- Continuation modeli + V-dönüş kombinasyonu çoğu zaman bölgenin tutmayacağını gösterir.

---

### Model 3 – Olasılık Artırıcılarla Rafine POI (Refined Supply & Demand)

**Tanım:** Birden fazla aday bölge varken en yüksek olasılıklıyı seçmek.

**Giriş şartları (sırasıyla kontrol listesi):**
1. **Break of Structure:** Bölge yapı kırmış mı? Önem sırası **Swing > Minor > Substructure** kırılımı. Kırılımın gücü de önemlidir (tam gövde, birkaç pip ötesine kapanış).
2. **Liquidity sweep:** Bölge oluşurken EQH/EQL, swing high/low veya trendline likiditesi süpürülmüş mü?
3. **Mitigation:** Bölge oluşurken soldaki eski bir S/D bölgesine dokunulmuş mu? Bu kriter en seyrek görülenidir ve tek başına yeterli değildir.
4. **Extreme mi?** Swing yapıyı kıran hareketin **origin'i** (en uç bölge), aradaki "decisional" bölgelere göre daha güvenilirdir. Fiyat genellikle extreme'e kadar gider.
5. **Inducement var mı?** Bölgenin hemen önünde (demand'in üstünde EQL, supply'ın altında EQH) likidite birikmiş olmalı. Fiyat bunu alıp bölgeye girer.
6. **HTF POI içinde mi?** "Sweep + CHoCH" tek başına ve boş bir alanda gerçekleşirse karşı-trend risklidir. Ancak HTF POI içindeyse geçerlidir.

**Kural:** Kriterler "kısmen" karşılanıyorsa (kısmen BOS, kısmen sweep) **girme.** Bölgeyi izle ve bir sonraki fırsatı teyit olarak kullan.
**Sıkça görülen tuzak:** Extreme'den önceki bölgeler çoğunlukla **internal range liquidity** olarak kullanılır ve kırılır.

---

### Model 4 – Order Block (OB) Kurulumu

**Tanım:**
- **Bullish OB:** Yapıyı **impulsif** kıran yükselişten önceki **son bearish mum**.
- **Bearish OB:** Yapıyı kıran düşüşten önceki son bullish mum.
- OB geçerliliği için hareket **yapıyı kırmalı** ve tercihen **imbalance** bırakmalıdır.

**Giriş şartları (sırasıyla):**
1. HTF (Günlük/4H) yön belirlenir.
2. 1H'de yapıyı impulsif kıran hareket ve imbalance bulunur. OB, bu hareketten önceki son karşıt mumdur.
3. **Rafine:** Sonraki mum OB'yi yutmuyor/kırmıyorsa ("price doesn't know time") OB'yi, **momentumun gerçekten başladığı** mumun hemen önündeki mum(a) taşı. Genellikle bu, güçlü engulfing mumdan önceki mumdur.
4. 15M'ye inilir. 1H OB'nin içinde, yapıyı kıran daha küçük bir 15M OB varsa kullanılır. R:R yaklaşık iki katına çıkabilir (örnek: 1:2.8 yerine 1:5.9).
5. Yakında daha iyi bir OB varsa (bir üst TF OB'ye yakın olan), trendle uyumlu olanı seç.
6. **Mitigate edilmemiş (henüz dokunulmamış) OB** olmalı. Tüketilmiş OB geçersizdir.

**Giriş noktası:**
- Bullish OB: OB'nin **tepesinden** limit alış veya **%50 (equilibrium)** seviyesinden.
- Bearish OB: OB'nin **dibinden** veya %50 seviyesinden limit satış.
- %50 daha az drawdown sağlar ama fiyat sadece dokunup kaçarsa kaçırılabilir.

**Stop:** Bullish OB'nin **altı**, bearish OB'nin **üstü**. OB'nin altında/üstünde fitil varsa **fitil de stop'a dahil edilir**, çünkü orada likidite vardır ve spike gelebilir.

**İki OB arasında kararsızlık:** Riski böl (ör. %0.5 + %0.5) veya ilk dokunuşu bekleyip ikinci teste gir.

**Geçersizlik:** OB'den gövde kapanışıyla çıkış (bullish OB için altına kapanış) ve LTF'de karşı yönde yapı kırılımı.

---

### Model 5 – Risk Entry vs Confirmation Entry (ana yürütme modeli)

> **Terminoloji notu:** Şubat 2021'den itibaren "risk entry" yalnızca HTF OB'ye doğrudan limit emir anlamına gelir. LTF'deki ilk BOS girişine "confirmation entry", ikinci BOS girişine "double confirmation entry" denir. Ayrıntılar Bölüm 4.1'de.

**Risk Entry (set & forget):**
- **Şartlar:** HTF POI (1H) → LTF (15M/5M) rafine OB → **limit emir.** LTF kırılımı beklenmez.
- **Ne zaman kullanılır:** İşlem **trend yönünde** ise, LTF OB HTF POI'nin **içinde** ise, fiyat POI'ye **düzeltmeli (corrective)** geliyorsa ve ekran başında olunamıyorsa.
- **Artısı:** Dokunup kaçan işlemleri yakalar, yüksek R:R verir.
- **Eksisi:** Teyit azdır, stop olma olasılığı yüksektir.
- **Kural:** Risk entry'de stop, confirmation entry'ye göre **biraz daha geniş** tutulur.

**Confirmation Entry (teyitli giriş):**
1. HTF POI (4H/1H, 15M ile rafine) belirlenir.
2. Fiyat **POI'ye dokunur** (dokunmadan bakılmaz).
3. Execution TF'ye (15M/5M/1M) inilir.
4. LTF'de POI yönünde **BOS/CHoCH** beklenir. Tip 2 kuralıyla **gövde kapanışı** gerekir. Sadece fitille geçiş likidite süpürmesidir.
5. Bu kırılımı yapan hareketin origin'indeki **yeni LTF OB**'ye limit emir konur. En güncel OB tercih edilir.
6. **Entry 1:** İlk BOS'tan sonra girilen OB. Daha risklidir, çünkü ilk kırılım bir likidite süpürmesi olabilir.
7. **Entry 2 (Double Confirmation):** **İkinci BOS**'tan sonra oluşan OB. Trend LTF'de teyitlidir. Daha güvenlidir ve isabet oranını artırır, ama bazen hiç gelmez.
8. **Varyasyon:** İlk BOS'un OB'si hiç mitigate edilmeden ikinci BOS gelirse ve imbalance ile likidite kalmışsa, fiyat geri dönüp ilk OB'ye dokunabilir. Bu da geçerli bir Entry 2'dir.

**Confirmation entry ne zaman tercih edilir:** Fiyat POI'ye **agresif/impulsif** geliyorsa ("düşen bıçak"), karşı-trend işlemlerde, HTF POI ile LTF rafine arasında büyük mesafe varsa ve birden fazla POI adayı varsa.

**1M uyarısı (Albert):** 1M yapısı çok gürültülüdür. **5M'de gerçek yapı kırılmadan** 1M OB'lerine art arda limit koymak, arka arkaya kayıp üretir. Önce 5M BOS, sonra 1M/3M'de rafine yapılmalı.

**Geçersizlik:**
- Fiyat POI'nin içinden gövdeyle kapanarak geçerse ve LTF'de karşı yönde yeni yapı oluşursa bölge iptal edilir.
- LTF BOS gelmezse **işlem yoktur** (kaçırılan işlem kabul edilir).
- POI'den uzaklaşarak yeni tepe/dip oluşmuşsa işlemi bırak.
- POI içinde sert kırılımla yeni bir OB oluşursa yeni OB'yi kullan. Kırılım zayıfsa ve arkada EQL bırakıyorsa orijinal OB'yi koru.

---

### Model 6 – Mr. Sketchy'nin 3 POI'si (ileri seviye giriş mumları)

1. **Sponsored Candle (en çok tercih edilen):**
   - Karşı yönden önceki son mum (buy-before-sell / sell-before-buy) ve **tam gövdeli**.
   - Likidite alır (EQH/EQL süpürür), ideal olarak soldaki bir bölgeyi mitigate eder, ardından **BOS** gelir.
   - **Giriş:** Mumun **%50'si** (equilibrium).
   - **Stop:** Mumun altı/üstü + spread payı. Mum "son savunma hattı" olduğu için fazla tampon gerekmez.
2. **Wick candle (fitilli mum):** Çoğunlukla fitil, az gövde. Likidite alır, BOS yapar, imbalance bırakır. **Giriş: mumun açılışı** (50% kullanılmaz).
3. **Refined OB:** Mitigate edilmemiş, imbalance bırakmış son OB. En az tercih edilenidir, çünkü hangi OB'nin tutacağı belirsiz olabilir.

**Ek kural:**
- Son "swing high"ı kıran hareketin başladığı dip = **protected low**. Bu kırılmadan alış yapılmaz.
- Büyük momentumla kırılım, fiyatın "decisional OB"ye dönme ihtimalini artırır.

---

### Model 7 – Liquidity Sweep + Reversal / Seans Likiditesi

**Giriş şartları:**
1. Belirgin likidite tespit edilir: **EQH/EQL**, double top/bottom, trendline (momentum-shift swing'leri), range üst/alt sınırı, **Asya high/low**.
2. Fiyat bu likiditeyi **fitille süpürür** ama gövdeyle kapanmaz ve kapanıp geri döner.
3. Süpürme, bir **HTF POI (OB/S&D)** içine denk gelmelidir. Bu en yüksek olasılıklı kurulumdur: "EQL süpürülür + OB'ye dokunulur".
4. LTF'de **CHoCH/BOS** oluşur. Süpürmeyi yapan mum (genelde sponsored candle) veya OB'den girilir.
5. Klasik seans modeli: Asya range'i oluşur → London açılışında Asya high/low'u süpürülür → HTF bias yönünde devam edilir.

**Stop:** Süpürme fitilinin ötesi.
**Hedef:** Karşı taraftaki likidite (range'in diğer ucu, karşı EQH/EQL).
**Kural:** Süpürmeden **sonra**, süpürmenin **tersi** yönde işlem yapılır ("trade away from the liquidity").

---

### Model 8 – Internal / External Range Liquidity (IRL → ERL döngüsü)

- **Uptrend'de:** Fiyat HH yaptıktan sonra geri çekilirken swing bacağının içindeki **internal liquidity**'yi (EQL, yapısal dipler, yükselen trendline) alır. Ardından bir demand bölgesinden **external liquidity**'ye, yani swing high'ın üstüne gider.
- **İşlem mantığı:** Pullback sırasında, internal likidite alındıktan ve extreme demand'e dokunulduktan sonra alış yapılır. Hedef **ERL** (önceki swing high'ın hemen üstü).
- Fiyat ERL'yi genelde **1 pip kadar** kırıp geri çekilir. Bu, yeni pullback başlangıcıdır ve kısmi kâr için mantıklı bir noktadır.
- Başarısız tepki: Supply'dan tepki gelir ama devam gelmezse o tepe **targeted** olur ve kırılacağı beklenir.
- **Inducement** = bölgeye girmek için bilerek bırakılan internal likidite.

---

### Model 9 – Mitigation Series / "Follow the Money" (Eli)

**Döngü:** **Range → Initiation (kırılım) → Mitigation (range'e geri dönüş) → Continuation.**
- Fiyat bir range'den çıkar, geri dönüp o range'i mitigate eder, sonra devam eder. Bu kurumların pozisyon yüklediğini gösterir.
- Range'ler için range'in **üst yarısı / equilibrium'u**, sponsored candle için mumun %50'si mitigation seviyesi olarak kabul edilir.
- **Mitigate edilmeden bırakılan range'ler** ya ileride devam noktası olur ya da **likidite çekim alanı** olarak kırılıp geçilir. Hangisi olacağına HTF bias karar verir.
- Art arda mitigation serileri (ör. LTF'de sürekli sell-to-buy) diplerin **protected** olduğunu gösterir. HTF POI'ye varıldığında bu diplerin oluşturduğu trendline likiditesi **ters yöndeki hedef** olur.
- Düşük momentumla kırılan range = zayıf dip/tepe.

---

### Model 10 – Supply/Demand Break Theory (Alex)

**Tanım:** Rastgele her yapı kırılımı değil, **bir supply veya demand bölgesinin kırılması** işlem tetikleyicisidir.

**Giriş şartları:**
1. HTF niyeti belirlenir (ör. 4H'de HL beklentisi ve altında likidite).
2. 15M/5M'de supply bölgeleri önceden çizilir. Hazırlıklı olmak için Frankfurt/London öncesinde yapılır.
3. LTF'de bir **supply (veya demand) kırıldığında** şu sorulur: "**Kırılımı ne yaptı?**" Cevap genelde **bir fitil veya inside bar**'dır ("the answer is always in the wicks").
4. Kırılıma sebep olan bu mum/fitil yeni demand (veya supply) kabul edilir → **limit emir.**
5. **Reaction point:** Fiyat ters bölgeden tepki alır ama o tepki karşı bölgeyi kıramazsa, başarısızlığa sebep olan mum yeni giriş bölgesidir.
6. **Emir disiplini:** Fiyat bir supply içindeyken demand'e limit konmaz (tersi de geçerlidir). Önce tepkinin başarısız olması beklenir.

**Stop:** Bölgenin hemen ötesi ve 1–2 pip spread payı. Bölge tamamen kapsanmalıdır.
**Hedef:**
- Karşı-trend işlemde **en yakın karşı bölge** (hızlı kâr al).
- Trend yönlü işlemde en az **önceki dip/tepe (ERL)**. HTF niyeti gerçekleşene kadar tut.

---

### Model 11 – Wyckoff Birikim / Dağıtım (teyit aracı)

- **Birikim:** PS → SC → AR → ST → (Spring / test) → **SOS** → **LPS** → Creek'in üstüne çıkış (JAC / back-up).
  - Giriş: Spring veya LPS bölgesindeki 1H/15M OB'den, rafine LTF OB ile.
- **Re-accumulation:** Spring olmayabilir. Önceki SOS'tan sonra doğrudan LPS gelebilir.
- **Dağıtım:** PSY → BC → AR → ST → **UT / UTAD** (EQH likiditesi alınır) → SOW → LPSY.
  - Giriş: UTAD testi veya LPSY bölgesindeki OB.
- Wyckoff işlemin **gerekçesi değil, ek teyididir.** Ana tetikleyici her zaman 1H/15M OB'dir.

---

### Model 12 – Inefficiency (Imbalance / FVG)

- **Tanım:** 3 mumlu dizide 1. mumun fitili ile 3. mumun fitili arasında örtüşmeyen boşluk.
- Tek taraflı alım/satım olduğunu gösterir ve fiyat bu boşluğu doldurmaya döner.
- **1H ve üzeri** TF'lerde kullanılır. Alt TF'lerde çok küçük kalır.
- **Kullanımı:** Kâr hedefi ve OB geçerliliği için ek teyit. **Doğrudan işlem yapılmaz.**
- Ters yönde güçlü momentumla OB'ye dönen fiyat, önündeki imbalance'ı çoktan doldurmuşsa OB genelde **tutmaz.**

---

### 2.x Ortak Stop, Hedef ve Zaman Kuralları (tüm modeller)

**Stop yerleşimi:**
- OB/POI'nin tamamının ötesine, varsa **fitil dahil.**
- Minimum stop: **2–3 pip.** Trade recap'lerde "3 pip'ten dar stop kullanmayın" denir.
- **Spread** hesaba katılır: Alışta spread giriş fiyatına eklenir. Satışta stop'a ve TP'ye eklenir, çünkü grafik bid fiyatını gösterir.
- Risk entry'de stop confirmation entry'ye göre daha geniştir.

**Yapısal geçersizlik:** İşlem yönündeki **protected low/high'ın gövde kapanışıyla** kırılması. Uptrend'de HL altına kapanış olursa bias değişir.

**Hedef / TP:**
- Tercih edilen R:R: **en az 1:5** ("personally I like 1:5s at least"). Tipik işlemler 5R–30R arasında hedeflenir.
- TP'nin 3 yolu (FAQ):
  1. **Karşı Order Block** / S&D bölgesi.
  2. HTF'deki **son swing high/low**'un test edilmesi veya kırılması (targeted high/low, ERL, EQH/EQL likiditesi).
  3. **HTF yapıyla trailing stop** (1H'de dip/tepelerin altına/üstüne).
- HTF **inefficiency** alanları uzun vadeli hedeftir.
- Karşı-trend işlemde hedef **ilk karşı bölge veya önceki swing**'dir. "Swing for the fences" yapılmaz.

**Kısmi kâr ve break-even:**
- "**Pay yourself.**" İlk tepkide riske eşit miktar (1R) kapatılır, gerisi koşmaya bırakılır.
- Hedefe varıldığında pozisyonun yaklaşık **%80'i kapatılır**, kalanı BE'ye çekilip bırakılır.
- **BE'ye erken çekme:** Anlatıcı, stop'u ancak **ilgili swing high kırıldıktan sonra** BE'ye taşır. Albert ise BE yerine **1R'lik kısmi kâr** alıp stop'u yerinde bırakır, çünkü fiyat girişe dönüp mitigation yapabilir.
- Kademeli partial: Önce 15M yapı hedeflerinde küçük, sonra 1H/4H hedeflerinde büyük kısımlar.
- Ölçekleme (scaling-in): Trend içinde yeni 15M BOS'lardan ek pozisyon açılır ve ana işlemin stop'u yapı altına taşınır.

**Zaman kuralları:**
- Belirli bir saat şartı zorunlu değildir. Ancak **London ve New York seansları** tercih edilir. London killzone en hacimlidir.
- Asya'da POI'ye gelen işlemlerde dikkatli olunur. London açılışında Asya likiditesi süpürülebilir.
- Açık emirler **spread saatlerinden önce iptal** edilir.
- **Cuma** günü hafta sonu riski nedeniyle kâr kilitlenir veya pozisyon küçültülür.
- **Mum kapanışı:** BOS için **gövde kapanışı** gerekir (Tip 1/2). Fitil geçişi likidite süpürmesidir. Backtest'te üst TF mumunun kapanış saatine (4H, günlük 17:00/18:00 NY) dikkat edilir.

---

## 3. Önemli İpuçları ve Risk Yönetimi Kuralları

### 3.1 Risk yönetimi (sayısal kurallar)
- **İşlem başına risk: %0.5 – %1 maksimum.** Anlatıcı çoğunlukla **%0.25–0.5** kullanır.
- **Toplam açık risk (exposure): en fazla %3.** Korelasyon dikkate alınır; en çok DXY'ye bakılır.
- **Emin olunmayan OB'de** risk düşürülür (%0.25–0.5). "Profit is profit."
- İki POI adayında risk **bölünür** (ör. %0.5 + %0.5).
- **Aylık hedef yaklaşımı:** Ayda yaklaşık **%4** hedeflenir.
  - Hedefe ulaşınca risk aynı kalır veya **düşürülür** (ör. %0.25 → %0.1).
  - Asla hedefi aşmak için risk artırılmaz ("gambling mindset").
- **Düşük isabet, yüksek R:R:** Strateji düşük win rate ile çalışır. Örnek olarak bir üyenin haftası: 13 işlem, 1 kazanç, **+16R**. Tek bir 10–26R işlem çok sayıda kaybı kapatır.
- Kararlar **pip'e değil % ve R'ye** göre verilir ("pips don't make profit, % makes prizes").

### 3.2 "Asla yapma" listesi
1. **HTF bias olmadan LTF'de işlem arama.** Pullback'te mi yoksa pro-trend bacakta mı olduğunu bil.
2. **Aralığın ortasında işlem açma** ("don't diddle in the middle"). Discount'ta al, premium'da sat.
3. **Range/pivot'tan ilk kırılımı veya ilk tepkiyi trade etme.** Bölgeye dönüşü bekle.
4. **V-dönüşlü bölgelere** ve yapı kırmamış bölgelere körü körüne limit koyma.
5. **Düşen bıçağı tutma:** POI'ye çok impulsif gelen fiyata risk entry ile girme; confirmation bekle.
6. **Karşı-trend reversal kovalamak:** Gerçek reversal noktası her bacakta sadece bir tanedir, geri kalan her şey continuation'dır.
7. **1M gürültüsüyle işlem:** 5M'de yapı kırılmadan 1M OB'lerine art arda girme.
8. **Fitille geçişi BOS sayma** (Tip 1/2 kullanıyorsan).
9. **Stop'u "mantıklı" yerlere koyma:** EQH/EQL'nin hemen ötesi, double top/bottom'un hemen dışı gibi yerler likidite avının hedefidir. Stop'u OB veya fitilin ötesine koy.
10. **Yüksek etkili haberlere ve spread saatlerine** açık emirle girme.
11. **FOMO:** Analiz kanallarına veya başkalarının işlemlerine bakıp plan dışı işlem açma. Başkasının stilini kopyalama.
12. **Planı esnetme:** Kriterleri "kısmen" karşılayan setup'a girme. "Kind of BOS, kind of sweep" = işlem yok.
13. **İlk giren olma çabası:** 2. veya 3. fırsatı (continuation) almak yeterlidir.
14. Kârı gereksiz yere geri verme: Hedefe yakın/önemli OB'ye yaklaşırken kâr al veya stop'u sıkılaştır.

### 3.3 Püf noktaları
- **"Structure is king."** Önce yapı, sonra bölge, sonra likidite.
- Supply/demand bölgelerinin neredeyse hepsi **tepki** verir. Önemli olan **devam (follow-through)**'dır. Kararlarını buna göre ver.
- **Likidite olan yerde gerçek OB yakındadır.** EQH/EQL, bir bölgenin hemen önündeki inducement olabilir.
- Aynı bacakta birden fazla bölge varsa **momentumu karşılaştır:** Hangi kırılım daha güçlü, hangisi daha fazla pip ötesine kapandı?
- Line chart, gerçek swing'leri görmek için kullanılır.
- Her kurulumda şunu sor: Bu bölge **order flow için mi** oluşturuldu, yoksa **likidite/inducement için mi**?
- **Always look left:** Grafikte basılmış her mumun bir hikâyesi vardır.
- Pullback'lerde **premium/discount** (range'in %50'si) kullanılır. Alışlar discount OB'den yapılır.

### 3.4 Süreç, backtest ve psikoloji
- **Backtest:**
  - Yılın **tamamı** test edilir (çeyrek çeyrek değil), çünkü mevsimsellik önemlidir.
  - Kazanan ve kaybeden işlemler ayrı ayrı karşılaştırılır, ortak özellikler bulunur.
  - Değişiklikler tek tek yapılır ve her birinin etkisi ölçülür.
- **Gerçekçi backtest:** Canlıda uyuyacağın saatlerde (ör. 03:00) işlem yapmış gibi sayma. Canlıda seçtiğin seansa (ör. yalnızca NY) odaklan.
- Backtest ile canlı sonuç arasında **fark olacağını** kabul et (duygu, zaman baskısı, aşırı düşünme).
- Mümkünse günlük **roadmap** hazırla: Seans bittikten sonra tüm setup'ları işaretle.
- **Journal** tut. Her işlemde "neden?" sorusunu sor, kayıpları plan açığı olarak incele.
- Kayıp serileri normaldir. Beklentiyi (expectancy), ortalama kayıp serisini ve drawdown'u verinle bil.
- Güven veriden gelir. Ego güven değildir, sosyal medya ise sadece "highlight reel"dir.
- Günde birkaç R ile yetin. Sürekli ekranda olmak zorunda değilsin; ayda 4–10 kaliteli işlem yeterlidir.

---

## 4. Detaylı Kontrolde Eklenen Kurallar (Commentary, Trade Recap ve Uygulama Videoları)

Bu bölüm, ilk raporda sadece taranan ancak ikinci kontrolde tamamen okunan videolardan çıkan **ek ve daha net kuralları** içerir. Bölüm 1–3'teki kuralları geçersiz kılmaz, onları tamamlar.

### 4.1 Güncellenmiş giriş terminolojisi (Şubat 2021 commentary)
Anlatıcı (Brad) giriş isimlerini karışıklığı gidermek için yeniden tanımladı:

| Terim | Anlamı |
|---|---|
| **Risk Entry** | Sadece HTF OB'ye (veya LTF'ye rafine edilmiş hâline) **limit emir**. LTF kırılımı beklenmez ("set & forget"). |
| **Confirmation Entry (Entry 1)** | Fiyat HTF OB'ye dokunduktan sonra LTF'de **ilk BOS** ile oluşan OB'den giriş. |
| **Double Confirmation Entry (Entry 2)** | LTF'de **ikinci BOS** ile oluşan OB'den giriş. En güvenli olanı. |
| **Varyasyon** | İlk BOS'un OB'si mitigate edilmeden ikinci BOS gelir, sonra fiyat geri dönüp ilk OB'ye dokunur. Ardında EQH ve imbalance kalmışsa bu da geçerli bir Entry 2'dir. |

**Gerçek reversal (CHoCH) tanımı (Phantom):** Tek bir BOS trendi değiştirmez. Önce **BOS**, ardından likiditeyi alan **anlamlı bir geri çekilme**, ardından **ikinci BOS** gelmelidir. Ancak o zaman trend dönmüş kabul edilir ve karşı yönde işlem aranır.

### 4.2 Phantom'un kişisel giriş modeli (4H → 15M → 5M/1M)
1. **4H OB/POI** belirlenir. Bu bir Günlük/Haftalık POI içinde olursa daha iyidir.
2. Fiyat 4H POI'ye girer. Hemen işlem açılmaz, piyasanın yön göstermesi beklenir.
3. **15M'de BOS** beklenir (POI yönünde).
4. BOS'u yaratan hareketin origin'indeki OB **5M / 3M / 1M**'de rafine edilir. Anlatıcı gürültü az olduğu için en çok **5M** kullanır.
5. **Emir yeri, stop mesafesine göre:**
   - Stop OB'nin distal ucundan **≤ 5 pip** ise giriş OB'nin **distal (uzak) ucuna** yakın konur, stop OB'nin hemen ötesine.
   - Stop **> 5 pip** ise giriş OB'nin **equilibrium (%50)** seviyesine konur.
   - OB'nin **proximal (yakın) ucundan** nadiren girilir. Tek istisna, OB'nin hemen önünde süpürülecek EQH/EQL olmasıdır.
6. Aşırı rafine etme (30 saniye gibi) işlemi kaçırtabilir: "Don't be a prick for a tick." Girebilmek, en iyi fiyattan daha önemlidir.

### 4.3 OB konfluens sıralaması (Ranking system)
Aynı yöndeki POI'ler, kaç zaman diliminin üst üste çakıştığına göre sıralanır:

| Sıra | Konfluens | Kabul edilen giriş |
|---|---|---|
| **1. (en iyi)** | Günlük + 4H + 1H OB çakışıyor | Confirmation (Entry 1) bile alınabilir |
| **2.** | 4H + 1H OB | Tercihen Double Confirmation. Çok güçlü BOS varsa Entry 1 |
| **3.** | Sadece 1H OB | Sadece Double Confirmation veya likidite süpürmesi sonrası giriş |

- Haftalık > Günlük > 4H > 1H OB'lerin iç içe geçmesi (stacking) tepki olasılığını artırır.
- **"Okay / Good / Great" giriş seviyeleri:** HTF OB içinde LTF'de henüz dokunulmamış (unmitigated) imbalance/OB'ler çizgiyle işaretlenir.
  - Fiyat HTF OB'nin sadece **üst kısmına** dokunursa Double Confirmation beklenir.
  - Fiyat derindeki, LTF'de imbalance bırakmış bölgelere girerse Entry 1 kabul edilebilir.

### 4.4 OB geçerliliği için ek kurallar
- **Fitil dokunuşu OB'yi bozmaz.** Klasik S&D'de fitil değen bölge "kullanılmış" sayılır, OB'de sayılmaz, çünkü kurumlar emirlerini katmanlar hâlinde (layering) koyar.
- **OB geçersiz olur**, eğer: fiyat üzerinde uzun süre oturduysa veya OB defalarca test edildiyse (emirler dolmuştur), ya da gövdeyle içinden geçildiyse.
- Albert: Bir POI'ye fiyat **%50'sine kadar girdiyse** o bölge mitigate edilmiş sayılır, ondan bir daha işlem beklenmez.
- **Uzak kırılım zayıflığı:** Fiyat POI'den yapı kırmak için çok uzağa gitmek zorunda kalıp (ör. 70+ pip) hemen aynı hızla geri dönüyorsa o OB'nin tutma olasılığı düşüktür.
- **İmpulsif geri dönüş:** OB'ye büyük, güçlü mumlarla (momentumla) geri geliniyorsa, özellikle haber varken, anlatıcı emir koymaktan çekinir.
- **İki aday OB varsa:** Önündeki imbalance'ı hâlâ doldurulmamış olan tercih edilir. Imbalance'ı dolmuş OB'nin tekrar ziyaret edilme ihtimali düşüktür.
- **Tuzak POI (Discord):** Tepkisi küçük bir impulstan öteye geçemeyen, hiçbir yapıyı kıramayan bölge güvenli POI değildir. Büyük ihtimalle üstünde/altında likidite biriktiren bir tuzaktır.
- **Başarısız OB'lerin sebebi:** Her büyük emir spekülatif değildir. Kurumsal döviz dönüşümleri ve hedge işlemleri tek seferde dolar ve geri dönüş gerektirmez. Bu yüzden her OB tutmaz.
- **Hidden / wick OB:** 1H'de kümelenmiş uzun fitiller, alt TF'de (5M/1M/saniye) mitigate edilmemiş bir OB veya imbalance barındırır. Hedef ve kısmi kâr noktası olarak dikkate alınır.
- **Kurumsal doluş mantığı:** Kurumlar ilk seferde emirlerinin yalnızca bir kısmını (örneğin %25) doldurur. Kalanı (%75) için fiyatın bölgeye geri dönmesini bekler. Bu, "bölgeye dönüşü bekle" kuralının gerekçesidir.

### 4.5 Premium / Discount (Fibonacci ile)
- Aktif swing aralığına (swing low → swing high) Fibonacci 0–50–100 çizilir.
- **Alış yalnızca %50'nin altında (discount), satış yalnızca üstünde (premium)** aranır. Günlük aralık ve 4H aralık için ayrı ayrı kontrol edilir.
- Premium bölgede alış veya aralığın uzamış (extended) kısmında ölçekleme (scale-in) yapılmaz.

### 4.6 Ek likidite türleri
- **Önceki gün / hafta / 4H yüksek-düşükleri** (PDH/PDL, PWH/PWL): Algoritmaların hedeflediği likiditedir.
- **Yuvarlak sayılar / psikolojik seviyeler** (ör. .7000, 1.3000, "even handle"): Hem kurumsal emir hem de duyarlılık (sentiment) bölgesidir. OB içinde olmaları ek teyittir, hedefte ise tepki beklenir.
- **Asya aralığı orta noktası (midline):** Başarısız midline testi veya başarısız likidite süpürmesi, S/D flip oluşturabilir.
- **Swing high tanımı (3 mum fraktali):** Yüksek, daha yüksek, sonra daha düşük tepe. Ortadaki mum swing high'dır. Swing low bunun tersidir.

### 4.7 Supply ↔ Demand Flip
- Bir demand bölgesi tepki verip sonra kırılırsa **supply'a dönüşür** (tersi de geçerlidir).
- Kırılan bölgenin tersine dönmesi ve likidite süpürmesi sonrası oluşan flip bölgeleri, özellikle **1M/5M continuation girişleri** için kullanılır.
- Bu konu ekip tarafından "2.0" içeriği olarak işaretlenmiş; bu klasörde sadece giriş seviyesinde anlatılıyor.

### 4.8 Haber, seans ve zamanlama kuralları (commentary'lerden)
- **Kırmızı klasör (red folder) haberler** (CPI, NFP, FOMC):
  - Haber mumu ve hemen sonrasındaki hareketten **işlem alınmaz**. Bu hareketler manipülasyon (EQH/EQL süpürmesi) ve spread genişlemesi içerir.
  - Açık işlem varsa haberden önce BE'ye çekilir veya kısmi kâr alınır.
  - FOMC haftasında dalgalı ve manipülatif fiyat beklenir.
- **Pazar açılışı:**
  - Pazar gecesi ve gap'li açılışta risk entry yerine **confirmation entry** kullanılır.
  - Piyasa yönünü belirledikten sonra (Pazartesi/Salı) risk entry'ye izin verilir.
- **Asya seansı:**
  - Anlatıcının kuralı "Asya'da işlem yapmam". Asya'da POI'ye gelen fiyat çoğunlukla bir tepe/dip yapar, sonra onu süpürüp stop'u alır.
  - Asya'da açılmış işlem genelde London açılışına kadar konsolide olur.
  - **London açılışında Asya high/low süpürmesi** en güçlü gün içi modeldir.
- **Spread / rollover saatleri** (NY kapanışı civarı): İşlem yapılmaz, bekleyen emirler çekilir.
- **Günlük mum kapanışı** NY 17:00'dir. 4H mumlar da bu saate göre kapanır; backtest'te buna dikkat edilir.

### 4.9 Emir girişi ve spread detayları
- **Alış limitinde** spread kadar önden gidilir (front-run). Örnek: GBPJPY'de yaklaşık 0,5–0,7 pip. Grafik bid fiyatını gösterir, alış ise ask fiyatından tetiklenir.
- **Satışta** spread stop ve TP'ye eklenir.
- **Minimum stop:**
  - Trade recap'lerde **3 pip'ten dar stop** önerilmez.
  - Albert'in kişisel kuralı **en az 2 pip**.
  - Volatil paritelerde (GBPJPY) ~4–5 pip normal kabul edilir. Risk entry'de stop biraz daha geniş tutulur.
- Stop, OB'nin altında/üstünde bir fitil varsa **o fitilin ötesine** konur.

### 4.10 Yönetim ve kâr alma (örnek işlemlerden somut oranlar)
- **Putting it All Together (GBPJPY):**
  - Stop **BE'ye**, 1M'de EQH ve ilgili swing high **kırıldıktan sonra** çekildi.
  - 1H yapı noktasında pozisyonun **~%25**'i kapatıldı.
  - Hedefte (4H OB) **%75–80** kapatıldı.
  - Kalan kısım günlük swing high'a bırakıldı.
  - Sonuç: 2 kayıp (%0,5'er risk), ardından **46,9R ve 41,5R**.
- **EURUSD Trade Recap:**
  - 1M OB'nin %50'sinden, **3 pip stop** ile giriş.
  - 1H yüksekte (1H OB hedefi) çoğunluk kapatıldı: **~20R ve ~30R**.
  - Hedefte pozisyonun **%90**'ı kapatıldı.
- **Albert (NZDUSD):**
  - BE'ye çekmek yerine **1R'lik kısmi kâr** alınır, stop yerinde bırakılır. Fiyat girişe dönüp mitigation yapabilir.
  - Haftalık yüksek hedefinde **%80** kapatılır.
- **Karşı-trend işlemler:** Daha agresif yönetilir.
  - İlk karşı POI'de kısmi kâr.
  - Stop, son majör dip/tepenin arkasına taşınır.
- **Kısmi kâr yerleri:** Swing low/high'lar, EQL/EQH, karşı OB, imbalance'ın **%25–50**'si.
- **Ölçekleme:** Trend devam ederken yeni 5M/1M BOS OB'lerinden ek pozisyon açılır. Ek pozisyonun stop'u ya ilk işlemin stop'uyla aynı yere ya da 1M fitilinin altına konur. İlk işlemde riske eşit kısmi kâr alınarak toplam risk sıfırlanır.

### 4.11 Wyckoff ile LTF birleşimi
- HTF POI'ye (ör. 1H OB + imbalance + 4H HL) gelindiğinde **1M'de birikim şeması** aranır: SC → AR → ST → (Spring) → yapı kırılımı.
- **Spring'siz birikim de geçerlidir:** Fiyat SC dibini korur, bu durumda limit emir SC dibine yakın konur. Spring gelirse retest'inde yeniden girilir.
- Phantom, Wyckoff'un **Faz C, D ve E**'sinin giriş modellerine zaten gömülü olduğunu söyler:
  - **UTAD / Spring** = likidite süpürmesi.
  - **LPS / LPSY** = double confirmation OB'si.
- Dağıtım içinde de alış (karşı-trend) yapılabilir. Şema değişirse (dağıtım sanılan şey birikime dönerse) bias esnetilir.

### 4.12 Makro ve duyarlılık bağlamı (yardımcı, işlem sebebi değil)
- **Risk-on / risk-off döngüsü:**
  - Risk-on'da EUR, GBP, AUD, NZD ve CAD güçlenir.
  - Risk-off'ta USD, JPY ve CHF (güvenli limanlar) güçlenir. Pariteler bu çerçevede okunur.
- **Retail sentiment göstergeleri:** Örneğin yatırımcıların %97'si long ise beklenir. Karşı taraftaki likidite hedeflenebilir.
- Heikin Ashi ve 50 EMA bir dönem "test aşamasında ek teyit" olarak anıldı. Stratejinin çekirdeğinde **yer almaz.**

### 4.13 Süreç ve psikoloji (commentary ve psikoloji kayıtları)
- **Az parite:** 3–5 parite izle ve onlarda uzmanlaş. Her paritenin karakteri farklıdır: kimi EQH/EQL süpürür, kimi uzun mitigation serileri yapar.
  - Ekip izleme listesi: GBPUSD, NZDUSD, AUDUSD, EURUSD, EURGBP, EURJPY, GBPJPY, USDCAD. Ek olarak altın ve petrol.
- **Neden %0,25 risk:** %0,25 risk ile 4 kayıp, klasik %1 risk ile tek kayba eşittir. Düşük isabet ve yüksek R:R ancak böyle psikolojik olarak taşınabilir.
- **Tereddüt ve kaybetme korkusu:** Lot küçült veya demoya dön. Güveni vaka çalışmasıyla yeniden inşa et (en az 5, tercihen **10–20 case study**).
- **Kaçan işlem:** "9 kez 10'unda piyasa ikinci fırsat verir." Panikle kovalamak yok; plan dışı (ör. Asya'da) konmuş emir iptal edilir.
- **Bias'ı tek LTF kırılımıyla çevirme.** HTF anlatı ile LTF kırılımı çelişirse, en mantıklı anlatı seçilir.
- **Kişisel beklenti:** Haftada/ayda birkaç kaliteli işlem yeterlidir (Albert: ayda ~4–6, bazen 10). Aylık %4 hedef yaklaşımı Bölüm 3.1'de.
- Her günün London ve New York seansı sonradan işaretlenir ("her gün markup yap, işlem almasan da").

---

## 5. Hızlı Uygulama Kontrol Listesi (grafik üzerinde)
1. **Günlük/4H:** Swing yapı yönü nedir? Protected dip/tepe hangisi, targeted hangisi?
2. Fiyat aralığın **discount** tarafında mı (alış için)?
3. **1H POI:** Yapı kırmış, imbalance bırakmış, **mitigate edilmemiş** OB/S&D var mı? Sweep, mitigation ve extreme kriterleri sağlanıyor mu?
4. POI'nin önünde **inducement (EQL/EQH)** var mı?
5. Dönüş **corrective/rounded** mı, yoksa V mi?
6. **15M rafine**, ardından ya limit (risk entry) ya da POI'ye dokunuşu bekle ve **5M/1M BOS + yeni OB** (Entry 1 / Entry 2).
7. **Stop:** OB/fitil ötesi, en az 2–3 pip, spread dahil. **Risk:** %0.25–1, toplamda en fazla %3.
8. **TP:** Önce IRL veya karşı OB'de 1R partial. Ana hedef ERL (swing high/low, EQH/EQL). R:R en az 1:5.
9. **Yönetim:** 1H'de yeni swing oluştukça stop'u taşı. BE'ye ancak yapı kırıldıktan sonra geç.
10. **Seans / haber / spread saati** kontrolü.
11. **Konfluens sıralaması:** Kaç TF'nin OB'si çakışıyor? Buna göre Entry 1 mi, Double Confirmation mı? (Bölüm 4.3)
12. **Emir yeri:** Stop ≤ 5 pip ise distal uca, > 5 pip ise OB'nin %50'sine. Alışta spread kadar önden git. (Bölüm 4.2, 4.9)
13. **Kırmızı klasör haber / Pazar açılışı / Asya** kontrolü. Gerekiyorsa confirmation entry'ye geç veya işlem alma. (Bölüm 4.8)
