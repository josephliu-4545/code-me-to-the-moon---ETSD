import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { VariableId, VariableInfo } from "../api/types";
import { ErrorBox, Loading } from "../components/ResultPanels";
import { CHART, tickStyle } from "../components/science/chartTheme";
import RhoScale from "../components/science/RhoScale";
import SignalPair from "../components/science/SignalPair";
import Disclosure from "../components/ui/Disclosure";
import PageHero from "../components/ui/PageHero";
import VariableGlyph from "../components/ui/VariableGlyph";
import { fmt, fmtCoord } from "../lib/format";
import type { Selection } from "../state/selection";

const PAIRABLE: VariableId[] = ["temperature", "relative_humidity", "extreme_heat", "precipitation", "ndvi", "soil_moisture"];

function SystemPicker({ label, letter, value, other, onChange, name }: {
  label: string;
  letter: string;
  value: VariableId;
  other: VariableId;
  onChange: (v: VariableId) => void;
  name: (id: string) => string;
}) {
  const id = useId();
  return (
    <fieldset className="system-picker">
      <legend className="system-legend"><span className="system-letter" aria-hidden>{letter}</span>{label}</legend>
      <div className="system-options">
        {PAIRABLE.map((v) => (
          <label key={v} className={`system-option ${value === v ? "active" : ""} ${other === v ? "is-other" : ""}`}>
            <input type="radio" name={`${id}-sys`} value={v} checked={value === v} onChange={() => onChange(v)} />
            <VariableGlyph id={v} size={20} />
            <span>{name(v)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Connector({ a, b, name }: { a: VariableId; b: VariableId; name: (id: string) => string }) {
  return (
    <div className="connector" aria-hidden>
      <svg className="connector-orbits" viewBox="0 0 320 200">
        <ellipse cx="160" cy="100" rx="150" ry="58" />
        <ellipse cx="160" cy="100" rx="118" ry="40" className="co-inner" />
        <path className="co-link" d="M62 118 C 120 30, 200 30, 258 82" />
        {[[96, 70], [140, 52], [188, 50], [228, 62], [118, 136], [210, 140]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="1.6" className="co-star" />)}
      </svg>
      <div className="node node-a"><VariableGlyph id={a} size={28} /><span>{name(a)}</span></div>
      <span className="connector-label">vary together?</span>
      <div className="node node-b"><VariableGlyph id={b} size={28} /><span>{name(b)}</span></div>
    </div>
  );
}

export default function RelationshipsPage({ variables, selection }: { variables: VariableInfo[]; selection: Selection }) {
  const [a, setA] = useState<VariableId>("temperature");
  const [b, setB] = useState<VariableId>("relative_humidity");
  const [submitted, setSubmitted] = useState<null | { a: VariableId; b: VariableId; lat: number; lon: number; from: number; to: number; ds: string }>(null);
  const q = useQuery({
    queryKey: ["relationships", submitted],
    queryFn: ({ signal }) => api.relationships(submitted!.a, submitted!.b, submitted!.lat, submitted!.lon, submitted!.from, submitted!.to, submitted!.ds, signal),
    enabled: submitted !== null,
  });
  const name = (id: string) => variables.find((v) => v.id === id)?.short_name ?? id;
  const maxYears = Math.min(...[a, b].map((id) => variables.find((v) => v.id === id)?.max_years ?? 10));
  const span = selection.endYearInclusive - selection.startYear + 1;
  const tooLong = span > maxYears;
  const submittedIsCurrent = submitted !== null
    && submitted.a === a
    && submitted.b === b
    && submitted.lat === Number(selection.latitude.toFixed(4))
    && submitted.lon === Number(selection.longitude.toFixed(4))
    && submitted.from === selection.startYear
    && submitted.to === selection.endYearInclusive + 1
    && submitted.ds === selection.dataset;
  const currentRequestIsFetching = submittedIsCurrent && q.isFetching;
  const data = submittedIsCurrent ? q.data : undefined;
  const va = data?.variables[0];
  const vb = data?.variables[1];
  const unitsA = va ? data?.results[va]?.units.annual_value : undefined;
  const unitsB = vb ? data?.results[vb]?.units.annual_value : undefined;

  return (
    <div className="page relationships">
      <PageHero
        kicker="Connected Worlds · Earth System Relationships"
        tone="cosmic"
        title={<>Investigate <em>a connection</em>.</>}
        aside={<Connector a={a} b={b} name={name} />}
      >
        <p>
          Do two Earth signals rise and fall together at one place? Explore how two variables vary together at the selected location. Only calendar years eligible for both variables are paired. These are descriptive associations, never evidence of cause.
        </p>
      </PageHero>

      <div className="page-body">
        <div className="context-strip" role="group" aria-label="Shared investigation context">
          <div><span className="ctx-label">Location</span><span className="ctx-value">{selection.placeName || "Custom point"}</span><span className="ctx-sub mono">{fmtCoord(selection.latitude, selection.longitude)}</span></div>
          <div><span className="ctx-label">Period</span><span className="ctx-value mono">{selection.startYear}–{selection.endYearInclusive}</span><span className="ctx-sub">{span} years</span></div>
          <a className="ctx-edit" href="#explore">Change in Explore Earth →</a>
        </div>

        <section className="pair-builder" aria-label="Choose two variables">
          <SystemPicker label="Variable A" letter="A" value={a} other={b} onChange={setA} name={name} />
          <span className="pair-and" aria-hidden>×</span>
          <SystemPicker label="Variable B" letter="B" value={b} other={a} onChange={setB} name={name} />
        </section>
        <div className="pair-go">
          <div className="pair-messages">
            {a === b && <p className="error-text">Choose two different variables.</p>}
            {tooLong && <p className="error-text">The selected period ({span} years) exceeds the {maxYears}-year limit of one of these variables. Shorten it in Explore Earth.</p>}
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={a === b || tooLong || currentRequestIsFetching}
            onClick={() => setSubmitted({ a, b, lat: Number(selection.latitude.toFixed(4)), lon: Number(selection.longitude.toFixed(4)), from: selection.startYear, to: selection.endYearInclusive + 1, ds: selection.dataset })}
          >
            Compare annual values
          </button>
        </div>

        {!submittedIsCurrent && (
          <div className="reading-guide">
            <h2 className="guide-title">How to read a comparison</h2>
            <div className="guide-grid">
              <div><p className="guide-term">Spearman ρ · annual values</p><p>Rank correlation of the paired annual values, from −1 (opposite order) through 0 (no monotonic association) to +1 (same order). Shared long-term trends can inflate it.</p></div>
              <div><p className="guide-term">Spearman ρ · year-to-year changes</p><p>Correlation of first differences. It removes much of any shared trend, so it speaks to whether the two vary together from one year to the next.</p></div>
              <div><p className="guide-term">Shared observations</p><p>Only years that pass the completeness rules for both variables are paired. With few shared years, ρ is withheld rather than guessed.</p></div>
            </div>
            <p className="note">Lagged relationships and anomaly comparisons are not computed by the analysis service and are not shown.</p>
          </div>
        )}

        {submittedIsCurrent && q.isFetching && <Loading label="Retrieving both variables…" />}
        {submittedIsCurrent && q.isError && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
        {data && va && vb && !q.isFetching && (
          <>
          <section className="pair-timeline reveal" aria-labelledby="pt-h">
            <h3 id="pt-h" className="chart-title">Two signals, one place</h3>
            <SignalPair data={data} name={name} />
          </section>
          <div className="relation-result reveal">
            <section className="relation-chart" aria-labelledby="pairs-h">
              <h3 id="pairs-h" className="chart-title">Paired annual values ({data.common_eligible_years.length} years)</h3>
              {data.paired_values.length > 0 ? (
                <>
                  <div className="chart-plot" aria-hidden>
                    <ResponsiveContainer width="100%" height={320}>
                      <ScatterChart margin={{ top: 12, right: 16, bottom: 30, left: 8 }}>
                        <CartesianGrid stroke={CHART.grid} />
                        <XAxis type="number" dataKey={va} name={name(va)} domain={["auto", "auto"]} tick={tickStyle} stroke={CHART.axis} tickLine={false}
                          label={{ value: `${name(va)} (${unitsA})`, position: "insideBottom", offset: -18, fill: CHART.tick, fontSize: 12 }} tickFormatter={(v: number) => fmt(v, 2)} />
                        <YAxis type="number" dataKey={vb} name={name(vb)} domain={["auto", "auto"]} tick={tickStyle} stroke={CHART.axis} tickLine={false} width={72}
                          label={{ value: `${name(vb)} (${unitsB})`, angle: -90, position: "insideLeft", fill: CHART.tick, fontSize: 12, style: { textAnchor: "middle" } }} tickFormatter={(v: number) => fmt(v, 2)} />
                        <Tooltip cursor={{ strokeDasharray: "2 3" }} contentStyle={{ fontSize: 12 }} itemStyle={{ color: "var(--text-primary)" }} labelStyle={{ color: "var(--text-secondary)" }} formatter={(v) => fmt(Number(v), 3)} />
                        <Scatter data={data.paired_values} fill={CHART.obs} stroke={CHART.surface} strokeWidth={2} isAnimationActive={false} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                  <Disclosure summary="Paired values table" meta={`${data.paired_values.length} rows`}>
                    <div className="table-wrap">
                      <table className="table">
                        <thead><tr>{"year" in (data.paired_values[0] ?? {}) && <th scope="col">Year</th>}<th scope="col">{name(va)} ({unitsA})</th><th scope="col">{name(vb)} ({unitsB})</th></tr></thead>
                        <tbody>
                          {data.paired_values.map((p, i) => (
                            <tr key={i}>{"year" in p && <th scope="row" className="mono">{p.year}</th>}<td className="mono">{fmt(p[va], 3)}</td><td className="mono">{fmt(p[vb], 3)}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Disclosure>
                </>
              ) : (
                <p className="note">No years were eligible for both variables.</p>
              )}
            </section>
            <section className="relation-findings" aria-labelledby="assoc-h">
              <h3 id="assoc-h" className="chart-title">Descriptive association</h3>
              <RhoScale label="Spearman ρ (annual values)" value={data.spearman_rho_annual} />
              <RhoScale label="Spearman ρ (year-to-year changes)" value={data.spearman_rho_first_differences} />
              <dl className="kv">
                <dt>Common eligible years</dt><dd className="mono">{data.common_eligible_years.join(", ") || "none"}</dd>
              </dl>
              {data.unavailable_reasons.length > 0 && <p className="warn-text">Withheld: {data.unavailable_reasons.map((r) => r.replace(/_/g, " ")).join("; ")}.</p>}
              <h4 className="mini-title">Spatial alignment</h4>
              <ul className="bullets">{data.alignment.spatial.map((s) => <li key={s}>{s}</li>)}</ul>
              {data.alignment.spatial_supports_differ && <p className="warn-text">The two variables represent different spatial footprints, so their association is approximate.</p>}
              <p className="caveat">{data.interpretation}</p>
            </section>
          </div>
          <section className="cause-note" aria-labelledby="cause-h">
            <h3 id="cause-h" className="chart-title">Moving together is not causing</h3>
            <div className="cause-grid">
              <p><strong>“These variables moved together.”</strong> What this page can show: whether, in the shared eligible years, higher values of one tended to come with higher (or lower) values of the other.</p>
              <p><strong>“One caused the other to change.”</strong> What it cannot show. Shared seasonality, a common long-term trend, or a third factor can produce the same association. Establishing cause needs physical understanding and dedicated study designs.</p>
            </div>
          </section>
          </>
        )}
      </div>
    </div>
  );
}
