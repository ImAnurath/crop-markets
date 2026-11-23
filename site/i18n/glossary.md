# Glossary: English to Turkish

Fixed term pairs that every translator must use. The owner (a native speaker) confirms this list once, before `tr.yml` and the Turkish prose are translated at scale. Not a page: `site/_quarto.yml` renders only `*.qmd`.

| English | Turkish |
|---|---|
| hazelnut | fındık |
| in-shell | kabuklu |
| kernel / shelled | iç fındık |
| commodity exchange | ticaret borsası (Giresun Ticaret Borsası, Ordu Ticaret Borsası) |
| crop estimate | rekolte tahmini |
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
| coverage | kapsama |
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
- USD: `4,13 $/kg` in prose and tiles (owner to confirm). Local currency label stays `TL`.
- Months: Ocak, Şubat, Mart, Nisan, Mayıs, Haziran, Temmuz, Ağustos, Eylül, Ekim, Kasım, Aralık. Short: Oca, Şub, Mar, Nis, May, Haz, Tem, Ağu, Eyl, Eki, Kas, Ara.
- Seasons stay `2025/26`.

## Already used in drafts

Terms earlier tasks drafted in `tr.yml` and `_quarto-tr.yml` that the table lacks. Confirm or correct them in the same pass.

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
| LightGBM quantiles | LightGBM kantilleri |
| Gap | Fark |
| Sources and credits | Kaynaklar ve atıflar |
| Chart failed to load (message) | Bu grafik yüklenemedi ... sayfayı yenileyin |
| "{name} exchange" | {name} borsası |

## Suffixes

Prefer phrasings that avoid suffixing a `{field}`: "Giresun rekolte tahmini, 2026", not "2026'daki Giresun tahmini". If a suffix is unavoidable, use an apostrophe and the vowel-harmony form of the last sound (`{year}'de`, `{source}'un`), and have the owner check it.
