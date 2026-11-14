import { useEffect, useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { fmtCoord } from "../lib/format";

interface Props {
  latitude: number;
  longitude: number;
  placeName: string;
  onChange: (lat: number, lon: number, name: string) => void;
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function LocationPanel({ latitude, longitude, placeName, onChange }: Props) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(query.trim(), 600);

  const search = useQuery({
    queryKey: ["geocode", debounced.toLowerCase()],
    queryFn: ({ signal }) => api.geocode(debounced, signal),
    enabled: debounced.length >= 3,
    staleTime: 24 * 3600 * 1000,
  });
  const listOpen = open && debounced.length >= 3;

  return (
    <section className="step" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className="step-title"><span className="step-num" aria-hidden>01</span>Where shall we investigate?</h2>
      <div className="place" aria-live="polite">
        <p className="place-name">{placeName || "Custom point"}</p>
        <p className="place-coords mono">{fmtCoord(latitude, longitude)}</p>
      </div>
      <div className="search">
        <label htmlFor={`${id}-q`} className="sr-only">Search for a place</label>
        <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>
        <input
          id={`${id}-q`}
          type="search"
          role="combobox"
          aria-autocomplete="list"
          placeholder="Search a city or place…"
          value={query}
          autoComplete="off"
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
          aria-expanded={listOpen && !!search.data?.results.length}
          aria-controls={`${id}-results`}
        />
        {listOpen && (
          <ul id={`${id}-results`} className="search-results" role="listbox" aria-label="Place search results">
            {search.isFetching && <li className="search-note">Searching…</li>}
            {search.isError && <li className="search-note error-text">Place search is unavailable. Enter coordinates or click the map.</li>}
            {search.data?.results.length === 0 && !search.isFetching && <li className="search-note">No places found.</li>}
            {search.data?.results.map((r) => (
              <li key={`${r.latitude},${r.longitude},${r.name}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    onChange(Number(r.latitude.toFixed(4)), Number(r.longitude.toFixed(4)), r.name.split(",").slice(0, 3).join(","));
                    setQuery("");
                    setOpen(false);
                  }}
                >
                  <span>{r.name}</span>
                  <span className="mono search-coord">{fmtCoord(r.latitude, r.longitude)}</span>
                </button>
              </li>
            ))}
            {search.data?.attribution && <li className="attrib">{search.data.attribution}</li>}
          </ul>
        )}
      </div>
      <CoordForm key={`${latitude},${longitude}`} latitude={latitude} longitude={longitude} onSubmit={(la, lo) => onChange(la, lo, "")} />
    </section>
  );
}

function CoordForm({ latitude, longitude, onSubmit }: { latitude: number; longitude: number; onSubmit: (lat: number, lon: number) => void }) {
  const id = useId();
  const [lat, setLat] = useState(String(latitude));
  const [lon, setLon] = useState(String(longitude));
  const [coordError, setCoordError] = useState("");

  function apply(e: React.FormEvent) {
    e.preventDefault();
    const la = Number(lat);
    const lo = Number(lon);
    if (lat.trim() === "" || !Number.isFinite(la) || la < -90 || la > 90) return setCoordError("Latitude must be between −90 and 90.");
    if (lon.trim() === "" || !Number.isFinite(lo) || lo < -180 || lo > 180) return setCoordError("Longitude must be between −180 and 180.");
    setCoordError("");
    onSubmit(Number(la.toFixed(4)), Number(lo.toFixed(4)));
  }

  return (
    <>
      <form className="coords" onSubmit={apply} aria-label="Enter coordinates">
        <label>
          <span className="field-label">Latitude</span>
          <input className="mono" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} aria-describedby={`${id}-ce`} />
        </label>
        <label>
          <span className="field-label">Longitude</span>
          <input className="mono" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} aria-describedby={`${id}-ce`} />
        </label>
        <button type="submit" className="btn btn-ghost">Set</button>
      </form>
      <p id={`${id}-ce`} className="error-text" role="alert">{coordError}</p>
    </>
  );
}
