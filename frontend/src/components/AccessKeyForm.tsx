import { useId, useState } from "react";
import { readAccessKey, writeAccessKey } from "../state/accessKey";

/** Shown when the shared backend answers 401 api_key_required. */
export default function AccessKeyForm() {
  const id = useId();
  const [value, setValue] = useState("");
  const hadKey = readAccessKey() !== null;
  return (
    <form
      className="access-key-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!value.trim()) return;
        writeAccessKey(value.trim());
        window.location.reload();
      }}
    >
      <label htmlFor={id} className="field-label">
        {hadKey ? "The saved team access key was not accepted. Enter a new one:" : "Team access key"}
      </label>
      <div className="row-gap">
        <input id={id} type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste the key from the project maintainer" />
        <button type="submit" className="btn btn-primary">Save key</button>
        {hadKey && <button type="button" className="btn btn-ghost" onClick={() => { writeAccessKey(null); window.location.reload(); }}>Forget saved key</button>}
      </div>
      <p className="note">The key is stored only in this browser and sent to the backend as an X-API-Key header.</p>
    </form>
  );
}
