import { useState } from "react";
import type { VariableInfo } from "../../api/types";
import { selectionBox, type Selection } from "../../state/selection";
import { boxPatch, boxProblem, regionLimits, type Box } from "../../lib/region";

export default function RegionBounds({ selection, info, onChange }: {
  selection: Selection; info: VariableInfo; onChange: (patch: Partial<Selection>) => void;
}) {
  const b = selectionBox(selection);
  // Keyed form keeps a typing draft without losing partial numeric input, and resets after map edits.
  return <BoundsForm key={b.join(",")} bounds={b} info={info} onChange={onChange} />;
}
function BoundsForm({ bounds, info, onChange }: { bounds: Box; info: VariableInfo; onChange: (patch: Partial<Selection>) => void }) {
  const [values, setValues] = useState(bounds.map(String));
  const [error, setError] = useState("");
  return <div className="region-bounds">
    <div className="years">{["West", "South", "East", "North"].map((name, i) => <label className="field" key={name}>
      <span className="field-label">{name} (degrees)</span>
      <input type="number" step="any" value={values[i]} onChange={(e) => setValues(values.map((v,j) => i === j ? e.target.value : v))} />
    </label>)}</div>
    <button type="button" className="btn btn-ghost" onClick={() => {
      const limits = regionLimits(info), b = values.map(Number) as Box;
      const problem = values.some(v => !v.trim()) ? "Enter all four bounds." : !limits ? "Region limits unavailable." : boxProblem(b, limits);
      setError(problem ?? "");
      if (!problem) onChange(boxPatch(b));
    }}>Apply bounds</button>
    <p className="step-note" role="status">{error || `${(bounds[2]-bounds[0]).toFixed(3)}° longitude × ${(bounds[3]-bounds[1]).toFixed(3)}° latitude. Drag corners to resize or the center to move.`}</p>
  </div>;
}
