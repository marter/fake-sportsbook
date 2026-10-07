const KEY = "fake_sportsbook_last_sport";

/** The league tab the user last opened, so Games reopens there. Best-effort only. */
export function getLastSport(): string {
  try {
    return localStorage.getItem(KEY) ?? "nfl";
  } catch {
    return "nfl";
  }
}

export function setLastSport(slug: string): void {
  try {
    localStorage.setItem(KEY, slug);
  } catch {
    // Private mode or storage disabled: just don't remember.
  }
}
