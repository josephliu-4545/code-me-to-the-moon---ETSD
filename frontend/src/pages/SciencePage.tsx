import type { VariableId, VariableInfo } from "../api/types";
import PageHero from "../components/ui/PageHero";
import VariableGlyph from "../components/ui/VariableGlyph";

const CONTENTS = [
  { id: "fg-sources", label: "Where does the data come from?" },
  { id: "fg-datasets", label: "What does each dataset represent?" },
  { id: "fg-method", label: "How are trends calculated?" },
  { id: "fg-reliable", label: "What makes a finding reliable?" },
  { id: "fg-limits", label: "What are the limitations?" },
  { id: "fg-disagree", label: "Why can two datasets disagree?" },
  { id: "fg-refs", label: "References" },
];

/** Illustration (not data): a selected point inside the grid cell whose value it receives. */
function GridCellDiagram() {
  return (
    <figure className="diagram">
      <svg viewBox="0 0 300 180" role="img" aria-label="Illustration: a selected point falls inside one grid cell; the value describes the whole cell, not the point.">
        <g className="dg-grid">
          {[0, 1, 2, 3, 4].map((c) => [0, 1, 2].map((r) => <rect key={`${c}-${r}`} x={20 + c * 52} y={18 + r * 50} width={52} height={50} />))}
        </g>
        <rect className="dg-cell" x={124} y={68} width={52} height={50} />
        <circle className="dg-point" cx={140} cy={88} r={4} />
        <path className="dg-lead" d="M144 86 L 214 40" />
        <text x={218} y={38} className="dg-text">your point</text>
        <path className="dg-lead" d="M176 112 L 226 150" />
        <text x={190} y={166} className="dg-text">value = whole cell</text>
      </svg>
      <figcaption>Illustration. Cell sizes range from about 250 m (MODIS pixels) to about 55 km (NASA POWER cells).</figcaption>
    </figure>
  );
}

const STEPS: { title: string; body: React.ReactNode }[] = [
  { title: "Retrieve", body: <>NASA data for the exact spatial support shown on the map: a native grid cell, a NASA POWER grid-cell estimate, or a circular area of MODIS pixels for NDVI.</> },
  { title: "Quality-screen", body: <>each observation using the product’s own quality information. Missing values stay missing: they are never set to zero or interpolated, and never filled from another dataset or version.</> },
  { title: "Summarise each year", body: <>with variable-specific rules, such as monthly means for temperature or twelve monthly accumulations for precipitation. Years that fail completeness rules are shown but excluded from the trend.</> },
  { title: "Estimate the slope", body: <>with Theil–Sen (the median of all pairwise slopes), which is robust to outliers. At least 3 eligible years are required.</> },
  { title: "Test significance", body: <>with a two-sided Mann–Kendall test, only with at least 8 eligible years and after a lag-1 serial-dependence screen. Otherwise the slope is reported as descriptive only. NDVI is the exception: cloud gaps leave few complete years, so each month is compared only with the same month in other years (seasonal Sen slope and Seasonal Kendall test).</> },
];

function jump(e: React.MouseEvent<HTMLAnchorElement>, id: string) {
  // In-page navigation without touching the hash (the hash selects the section).
  e.preventDefault();
  const el = document.getElementById(id);
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
  el?.focus({ preventScroll: true });
}

function DatasetChapter({ v, n }: { v: VariableInfo; n: number }) {
  return (
    <article className="chapter" aria-labelledby={`ch-${v.id}`}>
      <header className="chapter-head">
        <span className="chapter-num mono">{String(n).padStart(2, "0")}</span>
        <VariableGlyph id={v.id as VariableId} size={26} />
        <div>
          <h3 id={`ch-${v.id}`} className="chapter-title">{v.name}</h3>
          <p className="chapter-source">{v.dataset.source} · <span className="mono">{v.dataset.id} · {v.dataset.version}</span></p>
        </div>
      </header>
      <p className="chapter-desc">{v.description}</p>
      <dl className="spec">
        <div><dt>Type</dt><dd>{v.dataset.provenance}</dd></div>
        <div><dt>Annual value</dt><dd>{v.annual_value}</dd></div>
        <div><dt>Units</dt><dd className="mono">{v.units} · slope {v.slope_units}</dd></div>
        <div><dt>Spatial</dt><dd>{v.spatial_resolution}</dd></div>
        <div><dt>Temporal</dt><dd>{v.temporal_resolution}</dd></div>
        <div><dt>From</dt><dd className="mono">{v.available_from.slice(0, 4)} · up to {v.max_years} years per request</dd></div>
        <div><dt>Region mode</dt><dd>{v.modes.region ? `Supported (${v.region_shape ?? "area"})` : <span className="muted">{v.region_unsupported_reason}</span>}</dd></div>
        {v.datasets && v.datasets.length > 0 && <div><dt>Datasets</dt><dd className="mono">{v.datasets.join(" · ")}</dd></div>}
        <div><dt>DOI</dt><dd>{v.dataset.doi ? <a href={`https://doi.org/${v.dataset.doi}`} target="_blank" rel="noreferrer" className="mono">doi:{v.dataset.doi}</a> : "—"}</dd></div>
      </dl>
    </article>
  );
}

export default function SciencePage({ variables, caveats }: { variables: VariableInfo[]; caveats: string[] }) {
  return (
    <div className="page page-notebook science">
      <PageHero kicker="The Explorer’s Field Guide · Scientific Information" title={<>A notebook for <em>reading a changing planet</em></>} tone="notebook">
        <p>
          Every number in this tool comes from a named NASA dataset, a stated spatial footprint and a documented statistical method. This guide explains each of them, including what they cannot tell you.
        </p>
      </PageHero>

      <div className="page-body guide">
        <nav className="toc" aria-label="Field guide contents">
          <p className="toc-title">Field notes</p>
          <ol>
            {CONTENTS.map((c, i) => (
              <li key={c.id}><a href={`#${c.id}`} onClick={(e) => jump(e, c.id)}><span className="mono">{String(i + 1).padStart(2, "0")}</span>{c.label}</a></li>
            ))}
          </ol>
        </nav>

        <div className="guide-body">
          <section id="fg-sources" className="guide-section" tabIndex={-1} aria-labelledby="fg-sources-h">
            <p className="kicker">Question 01</p>
            <h2 id="fg-sources-h" className="section-title">Where does the data come from, and how is it collected?</h2>
            <p className="section-lede">Every signal comes from a named NASA product. They are produced in four different ways, and none of them is a ground station.</p>
            <div className="source-kinds">
              <div><span className="sk-label">Satellite retrieval</span><span className="sk-items">MODIS · SMAP</span><span className="sk-desc">Derived from radiance measured by instruments in orbit.</span></div>
              <div><span className="sk-label">Reanalysis-based estimate</span><span className="sk-items">NASA POWER</span><span className="sk-desc">Model output constrained by assimilated observations.</span></div>
              <div><span className="sk-label">Land-surface model</span><span className="sk-items">GLDAS Noah</span><span className="sk-desc">Simulated land water and energy driven by forcing data.</span></div>
              <div><span className="sk-label">Satellite + gauge merge</span><span className="sk-items">GPM IMERG</span><span className="sk-desc">Satellite precipitation calibrated with rain gauges.</span></div>
            </div>
            <ul className="distinctions">
              <li><strong>Model vs observation.</strong> NASA POWER and GLDAS are model or reanalysis estimates. MODIS and SMAP are satellite retrievals. IMERG merges satellite and gauge data. None of them is a ground station.</li>
            </ul>
          </section>

          <section id="fg-datasets" className="guide-section" tabIndex={-1} aria-labelledby="fg-datasets-h">
            <p className="kicker">Question 02</p>
            <h2 id="fg-datasets-h" className="section-title">What does each dataset actually represent?</h2>
            <p className="section-lede">Six environmental signals, each from its own NASA record. Each chapter lists the product, footprint and record length used by the analysis service.</p>
            <div className="chapters">
              {variables.map((v, i) => <DatasetChapter key={v.id} v={v} n={i + 1} />)}
            </div>
          </section>

          <section id="fg-method" className="guide-section" tabIndex={-1} aria-labelledby="fg-method-h">
            <p className="kicker">Question 03</p>
            <h2 id="fg-method-h" className="section-title">How are trends calculated?</h2>
            <ol className="process">
              {STEPS.map((s, i) => (
                <li key={s.title}>
                  <span className="process-node mono" aria-hidden>{i + 1}</span>
                  <p><strong>{s.title}</strong> {s.body}</p>
                </li>
              ))}
            </ol>
            {caveats.map((c) => <p key={c} className="caveat">{c}</p>)}
            <p className="note">Thresholds such as “12 of 12 months” are project policies chosen for transparency, not universal scientific standards.</p>
          </section>

          <section id="fg-reliable" className="guide-section" tabIndex={-1} aria-labelledby="fg-reliable-h">
            <p className="kicker">Question 04</p>
            <h2 id="fg-reliable-h" className="section-title">What makes a finding reliable?</h2>
            <ul className="distinctions">
              <li><strong>Enough complete years.</strong> A slope needs at least 3 eligible years and a significance test at least 8. Years failing the completeness rules are shown but never used.</li>
              <li><strong>An honest interval.</strong> The 95% interval shows the range of slopes consistent with the data. If it includes zero, no change is also consistent with the data.</li>
              <li><strong>Independence between years.</strong> A lag-1 serial-dependence screen runs before any significance test; strongly autocorrelated records are reported descriptively.</li>
              <li><strong>“No trend detected” is not “unchanged”.</strong> A non-significant test means the data are consistent with no monotonic trend; it is not proof of no change. When too few years qualify, the result is “trend unavailable”.</li>
              <li><strong>Sudden steps are flagged.</strong> A Pettitt test checks the yearly values for a single jump that stays at the new level, and reports it only when two flat levels fit better than a straight line. Such a step often means a change in the data source, so a slope across it should not be read as gradual change.</li>
              <li><strong>Missing data stay missing.</strong> Charts leave gaps for missing or unusable months instead of drawing lines across them.</li>
            </ul>
          </section>

          <section id="fg-limits" className="guide-section" tabIndex={-1} aria-labelledby="fg-limits-h">
            <p className="kicker">Question 05</p>
            <h2 id="fg-limits-h" className="section-title">What are the limitations?</h2>
            <div className="limits-grid">
              <ul className="distinctions">
                <li><strong>Grid cells are not points.</strong> A value represents an area from about 250 m (MODIS pixels) to about 55 km (NASA POWER cells), not a precise address.</li>
                <li><strong>Trends are not causes.</strong> A slope describes change over the eligible years only. It is not a forecast and does not attribute the change to climate, land use, or data artefacts.</li>
                <li><strong>Relationships are descriptive.</strong> Correlations between variables can arise from shared trends or seasonality and do not imply causation.</li>
              </ul>
              <GridCellDiagram />
            </div>
          </section>

          <section id="fg-disagree" className="guide-section" tabIndex={-1} aria-labelledby="fg-disagree-h">
            <p className="kicker">Question 06</p>
            <h2 id="fg-disagree-h" className="section-title">Why can two datasets disagree?</h2>
            <p className="section-lede">Products describing “the same” variable often measure different things: a different depth, a different footprint, a different method. Disagreement is information, not necessarily error — which is why datasets here are analysed separately and never merged.</p>
            <ul className="distinctions">
              <li><strong>Soil moisture.</strong> GLDAS reports water stored in a 0–10 cm model layer (kg m⁻²). Its converted volumetric value is a layer mean, not equivalent to SMAP’s ≈0–5 cm satellite retrieval. SMAP versions 005 and 006 are separate datasets and are never merged.</li>
            </ul>
          </section>

          <section id="fg-refs" className="guide-section" tabIndex={-1} aria-labelledby="fg-refs-h">
            <p className="kicker">Sources</p>
            <h2 id="fg-refs-h" className="section-title">References</h2>
            <ul className="refs">
              <li>Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall’s tau. <em>JASA</em> 63, 1379–1389.</li>
              <li>Mann, H. B. (1945). Nonparametric tests against trend. <em>Econometrica</em> 13, 245–259; Kendall, M. G. (1975). <em>Rank Correlation Methods</em>.</li>
              <li>NASA POWER Project, Langley Research Center — <a href="https://power.larc.nasa.gov/" target="_blank" rel="noreferrer">power.larc.nasa.gov</a>.</li>
              <li>Huffman, G. J. et al. GPM IMERG Final Precipitation L3 Monthly V07 — doi:10.5067/GPM/IMERG/3B-MONTH/07.</li>
              <li>Didan, K. MODIS/Terra Vegetation Indices 16-Day L3 250 m (MOD13Q1.061) — doi:10.5067/MODIS/MOD13Q1.061.</li>
              <li>Beaudoing, H. &amp; Rodell, M. GLDAS Noah Land Surface Model L4 3-hourly 0.25° V2.1 — doi:10.5067/E7TYRXPJKWOQ.</li>
              <li>O’Neill, P. E. et al. SMAP Enhanced L3 Radiometer 9 km Soil Moisture, V5 (doi:10.5067/4DQ54OUIJ9DL) and V6 (doi:10.5067/M20OXIZHY3RJ).</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
