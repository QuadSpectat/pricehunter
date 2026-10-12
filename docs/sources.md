# Source notes (Step 1) - researched 2026-10-09

Status: secondary sources only. Every item marked VERIFY must be confirmed against official docs/gov.il before it goes into code or rules YAML.

## AliExpress Affiliate API (primary AliExpress provider)
- Auth: App Key + App Secret, signed requests (HMAC-MD5 / sign method per Open Platform docs). VERIFY current sign method.
- `aliexpress.affiliate.product.query` - keyword search; params: keywords, category_ids, page_no, page_size, min/max_sale_price, sort, target currency/language/country.
- Product detail endpoint - title, sale/original price, image, rating (evaluate_rate), orders.
- `aliexpress.affiliate.product.shipping.get` - shipping info. VERIFY it exists for our account tier and returns per-country freight/ETA.
- Note: Affiliate API is built for affiliate links; product pages open via promo links. Needs approved affiliate account.
- Docs: https://openservice.aliexpress.com (developer portal). Secondary: https://zuplo.com/learning-center/aliexpress-api-guide.md

## SerpAPI
- Google Shopping engine: `engine=google_shopping`, `q`, `gl=il` (country), `hl`, `location`. Country list: https://serpapi.com/google-shopping-countries
- Google Lens engine (`engine=google_lens`, `url=<public image URL>`): image -> visual matches. VERIFY params; image must be a public URL (we need to upload/host local images, or use vision LLM + text search as alternative).
- Paid per search; cache aggressively.

## Bank of Israel exchange rates
- SDMX REST: `https://edge.boi.gov.il/FusionEdgeServer/ws/public/sdmxapi/rest/data/EXR/RER_USD_ILS?startPeriod=YYYY-MM-DD&endPeriod=YYYY-MM-DD`
- Series pattern `RER_<CUR>_ILS` (representative rates). Returns SDMX-XML (`Obs TIME_PERIOD`, `OBS_VALUE`).
- Server rejects default urllib UA; send a normal User-Agent. Rates published ~15:45 on business days. VERIFY.
- Fallback FX provider: TBD (e.g. frankfurter.app / exchangerate.host).
- Ref: https://www.boi.org.il/media/upqgqpuv/extracting-representative-exchange-rates-from-the-new-series-database.pdf

## Israel import tax (for rules/israel.yaml) - VERIFY ALL on gov.il / Tax Authority
Reported timeline (secondary sources):
- Personal-import VAT exemption threshold was USD 75, raised to USD 150 (from Jan 2026).
- 2026-02-24: Knesset voted 59-25 to revoke the order; threshold reverted to USD 75, systems updated effective 2026-06-02.
- Under threshold: exempt from VAT, duty, purchase tax. Above: VAT 18% applies; customs duty generally not charged up to ~USD 500 (VERIFY, category-dependent).
- Threshold evaluated on goods value, excluding shipping and insurance (VERIFY - this contradicts "CIF" in the original prompt).
- Standard VAT 18% (VERIFY).
- Sources: https://www.vatupdate.com/2026/06/10/israel-restores-75-vat-exemption-threshold-for-personal-imports/ ,
  https://www.iclglobal.com/news_update/vat-exemption-threshold-for-personal-imports-to-israel-updated/ ,
  https://www.comgateway.com/blogs/the-quick-cheat-sheet-for-israel-customs-and-import-taxes/
- Handling/courier fees: not yet found. Needs research (Israel Post / couriers).

## Israel tax rules - verification attempt 2026-10-12
- gov.il pages return HTTP 403 to automated fetches, so they were NOT read directly.
- Via search-result summary of the Tax Authority parcel guide: <= USD 75 exempt (tobacco/alcohol excluded);
  75-500 USD no customs duty but VAT (and purchase tax where relevant); > 500 USD full taxes.
- Maariv 2026-02-24 quotes the Tax Authority letter: threshold stays USD 75 (extended to 2026-06-01);
  vatupdate (2026-06-10) says USD 75 restored from 2026-06-02. Status after June 2026 not confirmed.
- Still TO CONFIRM on gov.il: exact valuation basis (shipping/insurance), whether shipping enters the VAT base,
  current threshold today, purchase-tax items, any handling/broker fees.
- Official pages to check by hand are listed under `official_sources` in israel.yaml.
