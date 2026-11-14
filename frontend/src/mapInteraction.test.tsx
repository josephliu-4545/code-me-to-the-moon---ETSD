import { act, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Map as MLMap } from "maplibre-gl";
import MapView, { STYLE } from "./components/MapView";
import { attachRegionHandles, type EditableRegion } from "./lib/regionInteraction";

const fake = vi.hoisted(() => {
  const control = () => ({ enable: vi.fn(), disable: vi.fn(), isEnabled: () => true });
  class Marker {
    element: HTMLElement; p = { lng: 0, lat: 0 }; events: Record<string, () => void> = {};
    constructor(options: { element: HTMLElement }) { this.element = options.element; markers.push(this); }
    setLngLat(p: [number,number]) { this.p = { lng:p[0],lat:p[1] }; return this; }
    getLngLat() { return this.p; }
    getElement() { return this.element; }
    addTo() { return this; }
    on(name: string, fn: () => void) { this.events[name] = fn; return this; }
    remove() {}
  }
  const markers: Marker[] = [];
  class Map {
    events: Record<string, (e?: unknown) => void> = {};
    sources: Record<string, { setData: ReturnType<typeof vi.fn> }> = {};
    dragPan = control(); dragRotate = control(); touchZoomRotate = control();
    canvas = document.createElement("canvas");
    constructor() { maps.push(this); }
    on(name: string, fn: (e?: unknown) => void) { this.events[name] = fn; }
    once(name: string, fn: (e?: unknown) => void) { this.on(name,fn); }
    getCanvas() { return this.canvas; }
    addControl() {} setPadding() {} jumpTo() {} addLayer() {} setPaintProperty() {} setSky() {} remove() {}
    addSource(id: string) { this.sources[id] = { setData: vi.fn() }; }
    getSource(id: string) { return this.sources[id]; }
    getLayer() { return true; } isStyleLoaded() { return true; } getZoom() { return 2; }
    easeTo = vi.fn();
  }
  const maps: Map[] = [];
  return { Marker, Map, markers, maps };
});
vi.mock("maplibre-gl", () => ({ Marker:fake.Marker, Map:fake.Map, NavigationControl:class {}, setWorkerUrl:vi.fn() }));
const box: EditableRegion = { kind:"box", bounds:[95,16,97,17], limits:{min:0.1,max:5} };
beforeEach(() => { fake.maps.length = 0; fake.markers.length = 0; });
afterEach(() => vi.useRealTimers());

it("uses opaque unfaded NASA imagery with no reference raster at orbital zoom", () => {
  const raster = STYLE.layers.find(l => l.id === "bluemarble")!;
  expect(raster).toMatchObject({ paint:{ "raster-opacity":1,"raster-fade-duration":0,"raster-brightness-max":1 } });
  expect(STYLE.sources.bluemarble).toMatchObject({tileSize:256,maxzoom:8,scheme:"xyz"});
  expect(STYLE.layers.find(l=>l.id === "features")).toMatchObject({minzoom:5});
});
it("initializes geometry before tiles finish, shows only delayed status and clears it on recovery", () => {
  vi.useFakeTimers();
  render(<MapView latitude={16} longitude={96} footprint={null} onSelect={vi.fn()}/>);
  const m = fake.maps[0]!;
  act(() => m.events["style.load"]!());
  expect(m.sources.selection).toBeDefined();
  act(() => { m.events.error!({sourceId:"features"}); vi.advanceTimersByTime(10000); });
  expect(screen.queryByText("NASA imagery unavailable")).toBeNull();
  act(() => { m.events.error!({sourceId:"bluemarble"}); vi.advanceTimersByTime(10000); });
  expect(screen.queryByText("NASA imagery unavailable")).toBeNull();
  act(() => { m.events.error!({sourceId:"bluemarble"}); m.events.error!({sourceId:"bluemarble"}); vi.advanceTimersByTime(8000); });
  expect(screen.getByText("NASA imagery unavailable").parentElement).toHaveClass("imagery-error");
  expect(screen.queryByText(/could not load completely/)).toBeNull();
  act(() => m.events.sourcedata!({sourceId:"bluemarble",tile:{state:"loaded"}}));
  expect(screen.queryByText("NASA imagery unavailable")).toBeNull();
});
it("draws two corners without changing the point and removes handles on point mode", () => {
  const update = vi.fn(), select = vi.fn();
  const props = {latitude:16.5,longitude:96,footprint:null,onSelect:select,onRegionChange:update};
  const view = render(<MapView {...props} region={box}/>);
  const m = fake.maps[0]!;
  act(() => m.events["style.load"]!());
  fireEvent.click(screen.getByRole("button",{name:"Draw rectangle"}));
  const click = (lng:number,lat:number) => m.events.click!({originalEvent:{target:document.createElement("canvas")},lngLat:{lng,lat,wrap:()=>({lng})}});
  act(() => click(95,16)); act(() => click(98,18));
  expect(update).toHaveBeenCalledWith({...box,bounds:[95,16,98,18]});
  expect(select).not.toHaveBeenCalled();
  view.rerender(<MapView {...props} region={null}/>);
  expect(screen.queryByRole("button",{name:"Draw rectangle"})).toBeNull();
  expect(m.sources.selection!.setData).toHaveBeenLastCalledWith({type:"FeatureCollection",features:[]});
});
it("resizes and moves with bounded updates and restores map gestures after cancellation", () => {
  const m = new fake.Map(), update = vi.fn(), message = vi.fn();
  const handles = attachRegionHandles(m as unknown as MLMap,box,update,message,vi.fn());
  const corner = fake.markers[0]!, center = fake.markers[4]!;
  corner.events.dragstart!(); corner.setLngLat([94,15]); corner.events.drag!(); corner.events.dragend!();
  expect(update).toHaveBeenLastCalledWith({...box,bounds:[94,15,97,17]});
  expect(m.dragPan.enable).toHaveBeenCalled();
  center.events.dragstart!(); center.setLngLat([100,20]); center.events.drag!(); center.events.dragend!();
  expect(update).toHaveBeenLastCalledWith({...box,bounds:[98.5,19,101.5,21]});
  center.events.dragstart!(); center.setLngLat([180,20]); center.events.drag!();
  expect(message).toHaveBeenLastCalledWith(expect.stringContaining("Dateline"));
  window.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}));
  expect(update).toHaveBeenLastCalledWith({...box,bounds:[98.5,19,101.5,21]});
  expect(m.touchZoomRotate.enable).toHaveBeenCalled(); handles.dispose();
});
it("supports keyboard corner editing and a geodesic radius handle", () => {
  const m = new fake.Map(), update = vi.fn();
  const handles = attachRegionHandles(m as unknown as MLMap,box,update,vi.fn(),vi.fn());
  fake.markers[0]!.element.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowLeft"}));
  expect(update).toHaveBeenLastCalledWith({...box,bounds:[94.99,16,97,17]});
  handles.dispose(); fake.markers.length = 0;
  const circle: EditableRegion = {kind:"circle",center:[96,70],radiusKm:5,maxRadius:100};
  const circleHandles = attachRegionHandles(m as unknown as MLMap,circle,update,vi.fn(),vi.fn());
  const radius = fake.markers[0]!;
  radius.events.dragstart!(); radius.setLngLat([96,70+10/6371.0088*180/Math.PI]); radius.events.drag!(); radius.events.dragend!();
  expect(update.mock.lastCall![0].radiusKm).toBeCloseTo(10,8);
  circleHandles.dispose();
});
