/** Pricing calculator used by the landing seat slider. */

export const MIN_SEATS = 1;
export const MAX_SEATS = 50;

export function clampSeats(seats: number): number {
  if (!Number.isFinite(seats)) return MIN_SEATS;
  return Math.min(Math.max(Math.round(seats), MIN_SEATS), MAX_SEATS);
}

/** Monthly total = seats × live per-operator price (UZS). */
export function computeMonthlyTotal(
  seats: number,
  pricePerOperator: number,
): number {
  return clampSeats(seats) * Math.max(0, pricePerOperator);
}
