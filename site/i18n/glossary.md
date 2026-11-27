# Glossary: English to Turkish

Fixed term pairs that every translator must use. Confirmed by the owner (a native speaker) on 2026-11-23, as drafted, including the "Already used in drafts" terms and the `4,13 $/kg` format; updated with the owner's review decisions of 2026-11-25 (hasat, yüzdelik, ilişki, TL, N/A, the Turkish brand). Not a page: `site/_quarto.yml` renders only `*.qmd`.

| English | Turkish |
|---|---|
| Crop Markets (the brand) | Ürün Piyasaları (Turkish pages only; English keeps "Crop Markets") |
| crop (a product, as in "Pick a crop") | ürün (not "mahsul") |
| hazelnut | fındık |
| in-shell | kabuklu |
| kernel / shelled | iç fındık |
| commodity exchange | ticaret borsası (Giresun Ticaret Borsası, Ordu Ticaret Borsası) |
| crop, harvest (the year's yield) | hasat; "hasat miktarı" where the quantity is meant (crop size). Not "rekolte". A big or small crop is "bol" / "düşük hasat", and a crop "azaldı" or "arttı"; not "büyük/küçük hasat" or "hasat büyüdü/küçüldü" |
| crop estimate | hasat tahmini |
| season (Sep–Aug) | sezon |
| export | ihracat |
| destination | pazar / ülke |
| frost | don |
| frost days | donlu gün |
| naive forecast | naif tahmin ("fiyat olduğu yerde kalır") |
| backtest | geriye dönük test |
| walk-forward | ileriye yürüyen |
| holdout | ayrılmış test dönemi ("bir kez puanlandı, hiç ayarlanmadı") |
| development period | geliştirme dönemi |
| 8-in-10 range | 10'da 8 aralığı |
| coverage | kapsama ("kapsama oranı" in notes; "tuttu" in sentences and the column) |
| horizon (months ahead) | ufuk (glossed once on the forecasting page: "bu sürelere ufuk diyoruz") |
| quantile, percentile | yüzdelik ("90. yüzdelik"; "yüzdelik dilim" where a noun needs it). Not "kantil" |
| skill | beceri |
| pinball loss | pinball kaybı |
| sanity check | sağlama |
| whiskers (chart) | ince çizgiler |
| "Error ÷ naive's" (column) | Hata ÷ naif |
| Giresun quality | Giresun kalitesi |
| a (statistical) link, correlation in words | ilişki (not "bağ") |
| MAE | ortalama mutlak hata (MAE) |
| supply shock | arz şoku |
| dashboard | Gösterge paneli |
| Overview | Genel bakış |
| Analyses | Analizler |
| Data explorer | Veri gezgini |
| Methods | Yöntemler |
| Downloads | İndirmeler |
| as-of stamp | "Veriler Ekim 2026 itibarıyla" |

- **Kept as they are:** method names (SARIMA, SARIMAX, Chronos-Bolt, LightGBM), FOB, and source names (UN Comtrade, FAOSTAT, TOBB, Open-Meteo, ECB, OECD). The Turkish Methods page explains them.
- **Voice.** Plain, short, formal-neutral Turkish ("siz" register, no slang). Match the English: say the finding first, explain every term.

## Formats

- Decimal comma, thousands dot: `4,13`, `86.440 t`, `%31,5`.
- Percent sign goes before the number: `%3,5`, `−%3,5`.
- USD: `4,13 $/kg` in prose and tiles. Local currency label stays `TL`.
- **TL or lira (both languages):** "TL" wherever a price, rate or series is meant (axis titles, legends, columns, `TL/kg`, `USD/TL`, "TL naif" / "TL naive", "TL fiyatları" / "TL prices"). "Lira" only for the currency as a thing in its own right: "Lira krizleri" / "Lira crises", "liranın değer kaybı" / "the lira's depreciation", "eski lira" / "old lira". Never the ₺ sign.
- Not available: `N/A` in both languages.
- Months: Ocak, Şubat, Mart, Nisan, Mayıs, Haziran, Temmuz, Ağustos, Eylül, Ekim, Kasım, Aralık. Short: Oca, Şub, Mar, Nis, May, Haz, Tem, Ağu, Eyl, Eki, Kas, Ara.
- Seasons stay `2025/26`.

## Already used in drafts

Terms earlier tasks drafted in `tr.yml` and `_quarto-tr.yml` that the table lacks. Confirmed with the table.

| English | Turkish (draft) |
|---|---|
| Theme toggle (light / dark) | Açık / koyu tema |
| Language (switch label) | Dil |
| Chart window buttons: 5Y / 10Y / All | 5Y / 10Y / Tümü |
| Today's price | Bugünkü fiyat |
| Today | Bugün |
| 9-in-10 range | 10'da 9 |
| Middle (of the range) | Orta |
| Actual (value) | Gerçekleşen |
| Season average | Sezon ortalaması |
| Middle half of seasons | Sezonların orta yarısı |
| Earlier seasons | Önceki sezonlar |
| Outside the range | Aralığın dışında |
| Median | Medyan |
| Seasonal naive | Mevsimsel naif |
| Season regression | Sezon regresyonu |
| LightGBM quantiles | LightGBM yüzdelikleri |
| Gap | Fark |
| Sources and credits | Kaynaklar ve atıflar |
| Chart failed to load (message) | Bu grafik yüklenemedi ... sayfayı yenileyin |
| "{name} exchange" | {name} borsası |

## Suffixes

Prefer phrasings that avoid suffixing a `{field}`: "Giresun hasat tahmini, 2026", not "2026'daki Giresun tahmini". If a suffix is unavoidable, use an apostrophe and the vowel-harmony form of the last sound (`{year}'de`, `{source}'un`), and have the owner check it.
