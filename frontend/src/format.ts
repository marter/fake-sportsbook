const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatMoney(cents: number): string {
  return usd.format(cents / 100);
}

export function formatAmericanOdds(price: number): string {
  return price > 0 ? `+${price}` : `${price}`;
}

export function formatPoint(point: number): string {
  return point > 0 ? `+${point}` : `${point}`;
}

export function formatKickoff(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function formatDayHeading(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

const relative = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });

export function formatTimeAgo(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 60) return relative.format(-minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (hours < 24) return relative.format(-hours, "hour");
  return relative.format(-Math.round(hours / 24), "day");
}

// Team names whose nickname is more than one word.
const MULTI_WORD_NICKNAMES = ["Red Sox", "White Sox", "Blue Jays", "Trail Blazers"];

/** "San Francisco 49ers" -> ["San Francisco", "49ers"], "Boston Red Sox" -> ["Boston", "Red Sox"] */
export function splitTeamName(name: string): [string, string] {
  const multi = MULTI_WORD_NICKNAMES.find((n) => name.endsWith(` ${n}`));
  if (multi) return [name.slice(0, -multi.length - 1), multi];
  const i = name.lastIndexOf(" ");
  return i === -1 ? ["", name] : [name.slice(0, i), name.slice(i + 1)];
}

/** American odds as an exact fraction [numerator, denominator]: +150 -> 5/2, -110 -> 21/11. */
function decimalFraction(price: number): [bigint, bigint] {
  return price > 0
    ? [BigInt(100 + price), 100n]
    : [BigInt(-price + 100), BigInt(-price)];
}

/** Mirrors the backend exactly: stake times every leg's decimal odds, rounded down to the
 * cent. One price is a single bet; several is a parlay. BigInt so 8 legs can't lose precision. */
export function parlayPayoutCents(stakeCents: number, prices: number[]): number {
  let num = BigInt(stakeCents);
  let den = 1n;
  for (const price of prices) {
    const [n, d] = decimalFraction(price);
    num *= n;
    den *= d;
  }
  return Number(num / den);
}

export function payoutCents(stakeCents: number, priceAmerican: number): number {
  return parlayPayoutCents(stakeCents, [priceAmerican]);
}

/** Combined American odds of several prices, for display (e.g. three -110s -> +596). */
export function combinedAmericanOdds(prices: number[]): number {
  const decimal = prices.reduce((acc, p) => acc * (p > 0 ? 1 + p / 100 : 1 + 100 / -p), 1);
  return decimal >= 2 ? Math.round((decimal - 1) * 100) : Math.round(-100 / (decimal - 1));
}

/** "12.5" -> 1250. Returns null for anything that isn't a non-negative amount. */
export function parseDollars(value: string): number | null {
  const trimmed = value.trim().replace(/^\$/, "");
  if (!/^\d*(\.\d{0,2})?$/.test(trimmed) || trimmed === "" || trimmed === ".") return null;
  return Math.round(parseFloat(trimmed) * 100);
}

/** "Bills -4.5", "Over 47.5", "Bills moneyline" */
export function selectionLabel(market: string, outcome: string, point: number | null): string {
  if (market === "totals") return `${outcome} ${point}`;
  const nickname = splitTeamName(outcome)[1];
  if (market === "spreads" && point != null) return `${nickname} ${formatPoint(point)}`;
  return `${nickname} moneyline`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatSignedMoney(cents: number): string {
  return `${cents > 0 ? "+" : cents < 0 ? "−" : ""}${formatMoney(Math.abs(cents))}`;
}
