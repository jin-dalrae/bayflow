import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
type Data = Record<string, any>;
type Props = {
  nodes: Data[];
  edges: Data[];
  frame: Data;
  selected: string | null;
  onSelect: (id: string) => void;
  activeDispatchEdges: Set<string>;
  trackedGroup: string | null;
  trackedPath: string[];
};
const colors: Record<string, string> = {
  "Muni Bus": "#e9b168",
  "Muni Metro": "#b6a4ef",
  BART: "#75c7f2",
  Caltrain: "#df8290",
  walk: "#637b75",
};
const routePalette=['#e4b96b','#6fc5b8','#e18498','#96b8ee','#b99ae0','#cad477','#df9c65','#84c6de','#cfb0a0','#77b486'];
const routeTint=(route:Data)=>{const label=String(route.short_name||route.service||route.id||'');const hash=Array.from(label).reduce((sum,c)=>sum+c.charCodeAt(0),0);return routePalette[hash%routePalette.length];};
const tint = (operator: string) => colors[operator] || "#96b5a9";
const location = (node: Data): L.LatLngTuple => [
  Number(node.lat),
  Number(node.lon),
];
function tooltip(title: string, detail: string) {
  const el = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  el.append(
    strong,
    document.createElement("br"),
    document.createTextNode(detail),
  );
  return el;
}
export default function TransitMap({
  nodes,
  edges,
  frame,
  selected,
  onSelect,
  activeDispatchEdges,
  trackedGroup,
  trackedPath,
}: Props) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    network = useRef<L.LayerGroup | null>(null),
    dynamic = useRef<L.LayerGroup | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const [tileStatus, setTileStatus] = useState("Loading street map…");
  const [reference, setReference] = useState<Data | null>(null),
    [referenceError, setReferenceError] = useState(""),
    [bus, setBus] = useState(true),
    [rail, setRail] = useState(true),
    [bart, setBart] = useState(true),
    [routeFilter, setRouteFilter] = useState(""),
    [query, setQuery] = useState(""),
    [view, setView] = useState(0);
  const referenceLayer = useRef<L.LayerGroup | null>(null);
  const referenceRenderer = useRef<L.Canvas | null>(null);
  const modelRenderer = useRef<L.Canvas | null>(null);
  const city = nodes.length > 100;
  const byEdge = useMemo(()=>Object.fromEntries(edges.map(e=>[e.id,e])),[edges]);
  const byPair = useMemo(()=>Object.fromEntries(edges.map(e=>[`${e.source}|${e.target}`,e.id])),[edges]);
  const trackedNodeIds = useMemo(()=>new Set(trackedPath.flatMap(id=>byEdge[id]?[byEdge[id].source,byEdge[id].target]:[])),[trackedPath,byEdge]);
  const trackedPairs = useMemo(()=>new Set(trackedPath.flatMap(id=>byEdge[id]?[[byEdge[id].source,byEdge[id].target].sort().join('|')]:[])),[trackedPath,byEdge]);
  useEffect(() => {
    let alive = true;
    fetch("/data/transit-reference.json")
      .then((r) => {
        if (!r.ok) throw Error("Reference snapshot unavailable");
        return r.json();
      })
      .then((d) => {
        if (alive) setReference(d);
      })
      .catch(() => {
        if (alive) setReferenceError("Agency reference snapshot unavailable");
      });
    return () => {
      alive = false;
    };
  }, []);
  const segments = useMemo(() => {
    const output: Record<string, L.LatLngTuple[]> = {};
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    for (const edge of edges) {
      const a = byId[edge.source],
        b = byId[edge.target];
      if (!a || !b) continue;
      if (Array.isArray(edge.geometry) && edge.geometry.length > 1) { output[edge.id] = edge.geometry; continue; }
      let best = Infinity;
      let path: L.LatLngTuple[] = [location(a), location(b)];
      const routes = (reference?.routes || []).filter((r: Data) =>
        edge.operator === "BART"
          ? r.operator === "BART" && r.route_type === 1
          : r.operator === "Muni" && r.short_name === edge.service,
      );
      for (const route of routes)
        for (const points of route.paths) {
          let ai = 0,
            bi = 0,
            ad = Infinity,
            bd = Infinity;
          for (let i = 0; i < points.length; i++) {
            const da =
              (points[i][0] - a.lat) ** 2 + (points[i][1] - a.lon) ** 2;
            const db =
              (points[i][0] - b.lat) ** 2 + (points[i][1] - b.lon) ** 2;
            if (da < ad) {
              ad = da;
              ai = i;
            }
            if (db < bd) {
              bd = db;
              bi = i;
            }
          }
          if (ai !== bi && ad + bd < best && ad + bd < 0.000025) {
            best = ad + bd;
            path = points.slice(Math.min(ai, bi), Math.max(ai, bi) + 1);
            if (ai > bi) path = path.slice().reverse();
          }
        }
      output[edge.id] = path;
    }
    return output;
  }, [nodes, edges, reference]);
  useEffect(() => {
    if (!container.current) return;
    const m = L.map(container.current, {
      zoomControl: false,
      scrollWheelZoom: false,
      zoomAnimation: false,
      minZoom: 9,
      maxZoom: 18,
    }).setView([37.774, -122.409], 13);
    map.current = m;
    const tiles = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        className: "sf-street-tiles",
      },
    ).addTo(m);
    tiles.on("tileload", () => setTileStatus("OpenStreetMap street map"));
    tiles.on("tileerror", () =>
      setTileStatus(
        "Street tiles unavailable · station coordinates remain visible",
      ),
    );
    L.control.zoom({ position: "topright" }).addTo(m);
    L.control.scale({ position: "bottomleft", imperial: false }).addTo(m);
    referenceRenderer.current = L.canvas({ padding: 0.2 });
    modelRenderer.current = L.canvas({padding:.2});
    referenceLayer.current = L.layerGroup().addTo(m);
    network.current = L.layerGroup().addTo(m);
    dynamic.current = L.layerGroup().addTo(m);
    m.on("moveend zoomend", () => {
      if (container.current) {
        container.current.dataset.zoom = String(m.getZoom());
        container.current.dataset.centerLat = String(m.getCenter().lat);
      }
      setView((v) => v + 1);
    });
    const observer = new ResizeObserver(() => m.invalidateSize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const layer = referenceLayer.current,
      m = map.current;
    if (!layer || !m || !reference) return;
    layer.clearLayers();
    const renderer = referenceRenderer.current!;
    const visible = (r: Data) =>
      r.operator === "BART" ? bart : r.route_type === 3 ? bus : rail;
    const routes = reference.routes.filter(
      (r: Data) => visible(r) && (!routeFilter || r.id === routeFilter),
    );
    for (const route of routes)
      for (const path of route.paths) {
        L.polyline(path, {
          renderer,
          color:
            route.operator === "BART"
              ? route.color
              : route.route_type === 3
                ? routeTint(route)
                : "#a998e0",
          weight: routeFilter
            ? 5
            : route.operator === "BART"
              ? 3
              : route.route_type === 3
                ? 2.2
                : 2.8,
          opacity: routeFilter
            ? 0.95
            : route.operator === "BART"
              ? 0.75
              : route.route_type === 3
                ? 0.65
                : 0.75,
        })
          .bindTooltip(
            tooltip(
              `${route.operator} ${route.short_name} · ${route.name}`,
              "Official GTFS reference route · no live vehicle data",
            ),
          )
          .addTo(layer);
      }
    const routeIds = new Set(
      routes.map((r: Data) => r.operator + ":" + r.feed_route_id),
    );
    for (const stop of reference.stops) {
      if (!m.getBounds().contains(location(stop))) continue;
      if (
        !stop.routes.some((id: string) =>
          routeIds.has(stop.operator + ":" + id),
        )
      )
        continue;
      if (
        stop.operator !== "BART" &&
        !stop.rail &&
        m.getZoom() < 14 &&
        !routeFilter
      )
        continue;
      L.circleMarker(location(stop), {
        renderer,
        radius: stop.operator === "BART" ? 4 : stop.rail ? 3 : 2,
        weight: 1,
        color:
          stop.operator === "BART"
            ? "#326faf"
            : stop.rail
              ? "#8173b5"
              : "#a47534",
        fillColor: "#f0f3e8",
        fillOpacity: 0.9,
      })
        .bindTooltip(
          tooltip(
            `${stop.name} · ${stop.operator}`,
            `GTFS reference stop · routes ${stop.routes.map((id: string) => reference.routes.find((r: Data) => r.operator === stop.operator && r.feed_route_id === id)?.short_name || id).join(", ")} · outside modeled demand unless highlighted`,
          ),
        )
        .addTo(layer);
    }
  }, [reference, bus, rail, bart, routeFilter, view]);
  useEffect(() => {
    const layer = network.current;
    if (!layer) return;
    layer.clearLayers();
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const seen = new Set<string>();
    for (const edge of edges) {
      const a = byId[edge.source],
        b = byId[edge.target];
      if (!a || !b) continue;
      const inspectedRoute = reference?.routes.find((route:Data)=>route.id===routeFilter);
      if(city && inspectedRoute && !trackedGroup && edge.route_id !== inspectedRoute.feed_route_id && edge.route_id !== inspectedRoute.id && edge.service !== inspectedRoute.short_name) continue;
      const key = [edge.source, edge.target].sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      L.polyline(segments[edge.id] || [location(a), location(b)], {
        renderer: city ? modelRenderer.current! : undefined,
        color: city && edge.operator === 'Muni Bus' ? routeTint(edge) : tint(edge.operator),
        weight: trackedPairs.has(key) ? 7 : edge.operator === "walk" ? 1.5 : city ? 1.6 : 4,
        opacity: trackedGroup ? trackedPairs.has(key) ? 1 : .2 : city ? .55 : .85,
        className: trackedPairs.has(key) ? "tracked-passenger-route" : "",

        dashArray: edge.operator === "walk" ? "4 6" : undefined,
      })
        .bindTooltip(
          tooltip(
            `${edge.operator} · ${edge.service}`,
            `${a.name} ↔ ${b.name} · simplified model connection`,
          ),
        )
        .addTo(layer);
    }
  }, [nodes, edges, segments, trackedGroup, trackedPath,city,trackedPairs,reference,routeFilter]);
  useEffect(()=>{
    if(!trackedGroup||!trackedPath.length||!map.current)return;
    const ids=trackedNodeIds;
    const points=nodes.filter(n=>ids.has(n.id)).map(location);
    if(points.length)map.current.fitBounds(L.latLngBounds(points),{padding:[65,70],animate:false});
  },[trackedGroup,trackedPath,nodes,trackedNodeIds]);
  useEffect(() => {
    const layer = dynamic.current;
    if (!layer) return;
    layer.clearLayers();
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    for (const edge of edges) {
      if (!activeDispatchEdges.has(edge.id)) continue;
      const a = byId[edge.source],
        b = byId[edge.target];
      if (a && b)
        L.polyline(segments[edge.id] || [location(a), location(b)], {
          color: "#eafa9d",
          weight: 8,
          opacity: 0.8,
          className: "dispatch-route",
        }).addTo(layer);
    }
    const bounds=map.current?.getBounds().pad(.2);
    const visibleNodes=city ? nodes.filter(node=>bounds?.contains(location(node))).sort((a,b)=>Number(frame.queues?.[b.id]||0)-Number(frame.queues?.[a.id]||0)) : nodes;
    let renderedMarkers=0;
    for (const node of visibleNodes) {
      const q = Number(
        frame.queues?.[node.id]?.count ?? frame.queues?.[node.id] ?? 0,
      );
      if(city && !q && selected!==node.id && !trackedNodeIds.has(node.id) && (renderedMarkers>=250 || (map.current?.getZoom()||0)<15)) continue;
      renderedMarkers++;
      if (q > 0)
        L.circleMarker(location(node), {
          renderer: city ? modelRenderer.current! : undefined,
          radius: Math.min(30, 8 + Math.sqrt(q) / 2),
          weight: 0,
          fillColor: q > 200 ? "#ff805b" : "#e9b168",
          fillOpacity: 0.3,
          interactive: false,
        }).addTo(layer);
      const marker = L.circleMarker(location(node), {
        renderer: city ? modelRenderer.current! : undefined,
        radius: selected === node.id ? 8 : city ? 3.5 : 5,
        weight: 2,
        color: tint(node.operator),
        fillColor: "#11221e",
        fillOpacity: 1,
        className: "station",
      });
      const permanent = [
        "oracle",
        "chase",
        "emb",
        "sf_caltrain",
        "millbrae",
      ].includes(node.id);
      marker
        .bindTooltip(
          tooltip(node.name, `${q.toLocaleString()} passengers waiting`),
          {
            permanent,
            direction:
              node.id === "oracle" || node.id === "chase" ? "right" : "left",
            className: "sf-station-label",
            offset: [node.id === "oracle" || node.id === "chase" ? 8 : -8, 0],
          },
        )
        .on("click", () => select.current(node.id))
        .addTo(layer);
      const el = marker.getElement();
      if (el) {
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.setAttribute("aria-label", `${node.name}, ${q} waiting`);
        el.addEventListener("keydown", (e) => {
          if (e instanceof KeyboardEvent && e.key === "Enter")
            select.current(node.id);
        });
      }
    }
    for (const vehicle of frame.vehicles || []) {
      const a = byId[vehicle.source],
        b = byId[vehicle.target];
      if (!a || !b) continue;
      const t = Math.max(0, Math.min(1, Number(vehicle.progress) || 0));
      const path = segments[vehicle.edge_id || byPair[`${vehicle.source}|${vehicle.target}`]] || [
        location(a),
        location(b),
      ];
      const lengths = path
        .slice(1)
        .map((p, i) => L.latLng(path[i]).distanceTo(L.latLng(p)));
      let remaining = t * lengths.reduce((x, y) => x + y, 0),
        point = path[path.length - 1];
      for (let i = 0; i < lengths.length; i++) {
        if (remaining <= lengths[i]) {
          const u = lengths[i] ? remaining / lengths[i] : 0;
          point = [
            path[i][0] + (path[i + 1][0] - path[i][0]) * u,
            path[i][1] + (path[i + 1][1] - path[i][1]) * u,
          ];
          break;
        }
        remaining -= lengths[i];
      }
      const trackedCount=(vehicle.passenger_groups||[]).filter((g:Data)=>g.cohort_id===trackedGroup).reduce((n:number,g:Data)=>n+g.count,0);
      L.circleMarker(point, {
        renderer: city ? modelRenderer.current! : undefined,
        radius: trackedCount ? 7 : 4,
        weight: 1,
        color: trackedCount ? "#fff" : "#10221c",
        fillColor: tint(vehicle.operator),
        fillOpacity: 1,
        className: trackedCount ? "sf-vehicle tracked-passenger-vehicle" : "sf-vehicle",
      })
        .bindTooltip(
          tooltip(
            vehicle.operator,
            `${vehicle.occupancy}/${vehicle.capacity} passengers · simulated vehicle${trackedCount ? ` · ${trackedCount} from tracked group ${trackedGroup}` : ""}`,
          ),
        )
        .addTo(layer);
    }
    for (const event of frame.events || []) {
      const ids = event.label?.includes("Chase")
        ? ["chase"]
        : event.label?.includes("Oracle")
          ? ["oracle"]
          : event.type === "delay"
            ? ["emb", "mont"]
            : event.type === "driver_shortage"
              ? ["townsend"]
              : [];
      for (const id of ids) {
        const n = byId[id];
        if (n)
          L.circleMarker(location(n), {
            radius: 20,
            color: "#ff805b",
            weight: 2,
            fillOpacity: 0,
            className: "disruption-location",
            interactive: false,
          }).addTo(layer);
      }
    }
  }, [nodes, edges, frame, selected, activeDispatchEdges, segments,trackedGroup,city,view,trackedNodeIds,byPair]);
  const fitRegion = () => {
    if (nodes.length)
      map.current?.fitBounds(L.latLngBounds(nodes.map(location)), {
        padding: [55, 65],
        animate: false,
      });
  };
  const muniStops =
      reference?.stops.filter((s: Data) => s.operator === "Muni").length || 0,
    bartStations =
      reference?.stops.filter((s: Data) => s.operator === "BART").length || 0;
  const busRoutes =
      reference?.routes.filter(
        (r: Data) => r.operator === "Muni" && r.route_type === 3,
      ).length || 0,
    railRoutes =
      reference?.routes.filter(
        (r: Data) => r.operator === "Muni" && r.route_type !== 3,
      ).length || 0;
  const snapshotDates = (reference?.sources || [])
    .map((source: Data) => {
      const d = source.feed_end_date;
      return `${source.operator} through ${d ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : "unknown date"}`;
    })
    .join(" · ");
  const matches =
    query.length >= 2
      ? (reference?.stops || [])
          .filter((s: Data) =>
            s.name.toLowerCase().includes(query.toLowerCase()),
          )
          .slice(0, 6)
      : [];
  const chooseRoute = (id: string) => {
    setRouteFilter(id);
    const r = reference?.routes.find((r: Data) => r.id === id);
    if (r?.paths.length)
      map.current?.fitBounds(L.latLngBounds(r.paths.flat()), {
        padding: [50, 65],
        animate: false,
      });
  };
  return (
    <>
      <div
        ref={container}
        className="sf-map"
        role="region"
        aria-label="Interactive San Francisco street map with simulated transit"
      />
      <div className="sf-map-controls">
        <button
          onClick={() =>
            map.current
              ?.closePopup()
              .setView([37.775, -122.408], 13, { animate: false })
          }
        >
          San Francisco
        </button>
        <button onClick={fitRegion}>{city?'City network':'Demo corridor'}</button>
        <button
          onClick={() => {
            if (reference)
              map.current?.fitBounds(
                L.latLngBounds(reference.stops.map(location)),
                { padding: [45, 45], animate: false },
              );
          }}
        >
          Bay Area
        </button>
      </div>
      <div className="sf-bus-shortcut"><button onClick={()=>{setBus(true);setRouteFilter('');map.current?.setView([37.767,-122.443],12,{animate:false});}}>Show all Muni bus lines ({busRoutes})</button><span>{bus&&!routeFilter?'All bus routes enabled':routeFilter?'Selected route only':'Bus layer hidden'} · {nodes.length.toLocaleString()} modeled stops</span></div>
      <details className="sf-layer-controls">
        <summary>
          Network layers · {reference ? reference.routes.length : "…"} routes
        </summary>
        <label>
          <input
            type="checkbox"
            checked={bus}
            onChange={(e) => setBus(e.target.checked)}
          />
          Muni bus lines ({busRoutes})
        </label>
        <label>
          <input
            type="checkbox"
            checked={rail}
            onChange={(e) => setRail(e.target.checked)}
          />
          Muni rail + cable cars ({railRoutes})
        </label>
        <label>
          <input
            type="checkbox"
            checked={bart}
            onChange={(e) => setBart(e.target.checked)}
          />
          BART stations + routes
        </label>
        <label>
          Inspect route
          <select
            aria-label="Inspect transit route"
            value={routeFilter}
            onChange={(e) => chooseRoute(e.target.value)}
          >
            <option value="">Show all routes · bus + rail</option>
            {reference?.routes.map((r: Data) => (
              <option key={r.id} value={r.id}>
                {r.operator} {r.short_name} · {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Find a station or bus stop
          <input
            aria-label="Find a station or bus stop"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Richmond, Geary"
          />
        </label>
        {matches.map((s: Data) => (
          <button
            key={s.id}
            onClick={() => {
              map.current?.setView(location(s), 16, { animate: false });
              setQuery("");
              L.popup()
                .setLatLng(location(s))
                .setContent(
                  tooltip(
                    s.name,
                    "Official GTFS reference stop · not a live service prediction",
                  ),
                )
                .openOn(map.current!);
            }}
          >
            {s.operator} · {s.name}
          </button>
        ))}
        <small>
          {reference?.stops.length.toLocaleString()} reference stops/stations.
          Bus stops appear at zoom 14+. {city?'City queues and vehicles use this modeled network.':'Highlighted corridor stations carry simulated demand.'}
        </small>
        <a href="/data/ATTRIBUTION.md" target="_blank" rel="noreferrer">
          Data sources, snapshot dates and licenses
        </a>
      </details>
      <div className="sf-map-source">
        {tileStatus} ·{" "}
        {reference
          ? `${muniStops.toLocaleString()} Muni stops · ${bartStations} BART stations`
          : referenceError || "Loading agency network…"}
        <br />
        GTFS snapshots: {snapshotDates} · reference, not live service
        <br />
        Highlighted vehicles and passenger queues: simulation
      </div>
    </>
  );
}
