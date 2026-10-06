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

/** "San Francisco 49ers" -> ["San Francisco", "49ers"] */
export function splitTeamName(name: string): [string, string] {
  const i = name.lastIndexOf(" ");
  return i === -1 ? ["", name] : [name.slice(0, i), name.slice(i + 1)];
}
