/** Payout request validation — shared by the dialog and unit tests. */

export function validatePayoutAmount(
  amount: number,
  balance: number,
  minimum: number,
): string | null {
  if (!Number.isFinite(amount) || amount <= 0) return "invalid";
  if (amount < minimum) return "below_minimum";
  if (amount > balance) return "over_balance";
  return null;
}
