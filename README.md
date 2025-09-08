# tqscanner

Scrapes TitleQuote (https://titlequote.stlmsd.com/#/) into a normalized JSON.

## Output
Writes to `output/TitlequoteScanner-Output/tq_data.json` with this shape:
```json
{
  "Trustee": "TitleQuote",
  "Sale_date": "MM/DD/YYYY",
  "Sale_time": "",
  "FileNo": "12345",         // Quote ID (fallback: Locator)
  "PropAddress": "123 Main St",
  "PropCity": "",
  "PropZip": "63101",
  "County": "",
  "OpeningBid": "12345.67",  // numeric string, no $ or commas
  "vendor": "",
  "status- DROP DOWN": "Stage name",
  "Foreclosure Status": ""
}
