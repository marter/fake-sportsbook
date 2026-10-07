import { NavLink } from "react-router-dom";
import type { Sport } from "./types";

export function SportTabs({ sports }: { sports: Sport[] }) {
  return (
    <nav className="sport-tabs" aria-label="Leagues">
      {sports.map((s) => (
        <NavLink
          key={s.slug}
          to={`/games/${s.slug}`}
          className={`sport-tab${s.in_season ? "" : " sport-tab--off"}`}
          title={s.in_season ? undefined : s.season_note}
        >
          {s.name}
          {!s.in_season && <span className="sport-tab-note">Off</span>}
        </NavLink>
      ))}
    </nav>
  );
}
