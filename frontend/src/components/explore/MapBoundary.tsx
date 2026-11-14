import { Component, type ReactNode } from "react";

export function MapUnavailable({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="map-wrap map-failed" role="note">
      <div>
        <strong>The interactive map could not start</strong>
        <p>Your browser may not support WebGL, or the map failed to load. You can still choose any location by searching for a place or entering latitude and longitude in the investigation panel.</p>
        {onRetry && <button type="button" className="btn btn-ghost" onClick={onRetry}>Restart globe</button>}
      </div>
    </div>
  );
}

/** Keeps the investigation usable if the map bundle or WebGL fails. */
export default class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <MapUnavailable onRetry={() => this.setState({ failed: false })} /> : this.props.children;
  }
}
