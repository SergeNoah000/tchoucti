/** Curated ISO 4217 currencies relevant to the target market (Central/West
 *  Africa) plus the main international ones. `decimals` drives rounding when
 *  converting config amounts between currencies. */
export const CURRENCIES: { code: string; decimals: number }[] = [
  { code: "XAF", decimals: 0 },
  { code: "XOF", decimals: 0 },
  { code: "NGN", decimals: 2 },
  { code: "GHS", decimals: 2 },
  { code: "KES", decimals: 2 },
  { code: "ZAR", decimals: 2 },
  { code: "MAD", decimals: 2 },
  { code: "RWF", decimals: 0 },
  { code: "CDF", decimals: 2 },
  { code: "GNF", decimals: 0 },
  { code: "EUR", decimals: 2 },
  { code: "USD", decimals: 2 },
  { code: "GBP", decimals: 2 },
  { code: "CAD", decimals: 2 },
  { code: "CHF", decimals: 2 },
];

export const CURRENCY_CODES = CURRENCIES.map((c) => c.code);
