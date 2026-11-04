# Data sources

Survey done on 2026-11-04. "Verified" means data was actually pulled from the source,
not just found on a web page.

## Prices

| Source | What it has | History | Access | Verified |
|---|---|---|---|---|
| Ordu Commodity Exchange, "Geçmiş Yıllar" sheet | Daily average in-shell price on days with registered trades (about 100 days a year) | 1999 to today | Public Google Sheet, one tab per year, exports as CSV | Yes |
| TOBB exchange price system | Daily min, max and average price, quantity (kg), number of trades and value (TL) for 12 hazelnut grades across 6 exchanges | 2005 to today | HTML form, POST per grade and exchange | Yes |
| Giresun Commodity Exchange statistics page | Monthly min, max and average price in TL and USD, with the monthly exchange rate | 1985 to today | JSON embedded in the page HTML | Yes |
| Giresun Commodity Exchange statistics page | Daily volume-weighted price and quantity | Current season only | Same JSON; history must be built by saving it daily | Yes |
| TMO (Turkish Grain Board) purchase price | One floor price per season and quality | Long | Announced in the news only, compiled by hand | Partly |

TOBB coverage detail: only Ordu / Tombul Levant in-shell is still updated. Kernel prices by
size grade (9-11, 11-13, 13-15 and others) run from 2005 to about 2016, mostly from the Düzce
and Trabzon exchanges. Giresun / Tombul Giresun in-shell runs 2005 to March 2023.

TOBB grade codes (`alt_kod`, with `ana_kod=9`): 204 kernel 11-13, 205 kernel 12-14, 206 kernel
13-15, 908 kernel 9-11, 906 / 907 / 905 kernel 9-15 graded (1st class, 2nd class, extra),
909 kernel wrinkled, 910 kernel defective, 202 in-shell Sivri, 911 in-shell Tombul (Giresun),
904 in-shell Tombul (Levant).

TOBB exchange codes: 5DÜ10 Düzce, 5FA10 Fatsa, 5GI10 Giresun, 5OR10 Ordu, 5AD20 Sakarya,
5TR10 Trabzon.

## Price drivers

| Source | What it has | History | Access | Verified |
|---|---|---|---|---|
| UN Comtrade | Turkey's monthly exports of HS 080221 (in-shell) and 080222 (shelled) by destination country, in kg and USD | 2000 to about 3 months ago | Public preview API, no key, 500 rows per call, rate limited | Yes |
| FAOSTAT | Annual production, area and yield by country | 1961 to latest year | Bulk zip download (the query API now needs a login) | Yes |
| Giresun Commodity Exchange statistics page | Crop estimate vs actual harvest per year; purchases split by traders, TMO and cooperatives | 1990s to today | Same embedded JSON | Yes |
| TÜİK (Turkish Statistical Institute) | Production by province per year | Long | MEDAS query tool needs a browser; likely a manual export | No |
| Open-Meteo archive | Daily weather for any coordinate (temperature, precipitation and more) | 1940 to today | Free API, no key | Yes |
| TCMB (central bank) | Daily exchange rates | 1990s to today | One XML file per day, no key | Yes |
| Inflation | Turkish CPI | Long | Annual from the World Bank API; monthly needs a free TCMB EVDS key | Annual only |

Derived series worth noting: export value divided by export quantity from Comtrade gives a
monthly unit value, which works as an international price for Turkish hazelnuts.

## Checked and not useful

- TÜRİB (Turkish product exchange): no hazelnut trading found.
- TMO website: no downloadable hazelnut tables.
- INC (International Nut and Dried Fruit Council): yearly narrative review, not data tables.
- USDA FAS GAIN "Turkey: Tree Nuts Annual": yearly PDF reports, useful for reading, not for data.
- Italian prices (Cuneo and Alessandria-Asti chambers of commerce): scattered PDF price lists only.

## Things to handle in cleaning

- Prices before 2005 are in old lira. Turkey removed six zeros on 1 January 2005.
- In the Ordu sheet, most prices carry an asterisk meaning "special-terms producer average".
- Exporters and TMO work on a September to August season, not the calendar year.
- The Ordu sheet is a live Google Sheet that can change or disappear, so every pull saves a raw copy.
