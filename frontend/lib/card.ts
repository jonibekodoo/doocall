/** Card-form helpers shared by the Paylov dialogs (one-time pay, link a card). */

/** "8600000000000000" → "8600 0000 0000 0000" (digits only, max 19). */
export function fmtCardNumber(value: string): string {
  return value
    .replace(/\D/g, "")
    .slice(0, 19)
    .replace(/(.{4})/g, "$1 ")
    .trim();
}

/** "1226" → "12/26" while typing. */
export function fmtExpiryInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 4);
  return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
}

/** Paylov wants YYMM. The label says MM/YY, but accept YY/MM too: pick the
 * ordering whose month part is 01-12. Returns "" when neither is valid. */
export function toYYMM(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length !== 4) return "";
  const a = digits.slice(0, 2);
  const b = digits.slice(2, 4);
  const ai = Number(a);
  const bi = Number(b);
  if (ai >= 1 && ai <= 12) return `${b}${a}`; // MM/YY → YYMM
  if (bi >= 1 && bi <= 12) return `${a}${b}`; // YY/MM → YYMM
  return "";
}

/** Stored YYMM → "MM/YY" for display. */
export function fmtYYMM(yymm: string): string {
  return yymm.length === 4 ? `${yymm.slice(2)}/${yymm.slice(0, 2)}` : yymm;
}

/** "860000******9999" → "9999". */
export function cardLast4(masked: string): string {
  return masked.replace(/\D/g, "").slice(-4);
}
