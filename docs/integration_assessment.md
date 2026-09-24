# UFFIS viewer: integration assessment

An inventory of everything built in the Guatemala work (mainly
`Tito\GT_train_case`, `Tito\UQ_warnings` and the training package) and how
each piece is, or can be, integrated into this viewer. Status codes:
DONE (in the viewer now), READY (data and method exist, small step),
PLANNED (needs upstream work first).

## 1. EF5 / TITO forecast chain

What exists. The operational chain runs two domains per cycle
(guatemala_900m national, guatemala_90m southern high resolution), three
run families (10 scampr, 10 stream_sat, 50 stormlab), and writes per run
maxunitq, maxq, maxsm, qpeaccum, qpfaccum, gauge time series and logs,
plus min, median and max composites in summary/ for qpeaccum, maxunitq
and maxsm in both nowcast and forecast modes.

In the viewer. DONE: the summary composites drive segments 1 and 2 with
the Min, Median, Max switch; both domains drawn (900 m always, 90 m added
in basin mode). The maxunitq layers use the exact operational FLASH
palette from 35_ef5_layers.py: class edges 0.1, 1, 2, 4, 6, 10, 20 and
colors #ACACAC, #C8CE33, #F79320, #BC3F34, #D14FC8, #2B2BD5, #FFFFFF,
the same scale taught in training session D1_S2.

READY next: maxq (absolute discharge) composites are not written by the
pipeline summary step; if wanted as a layer, add them to the summary step
and prepare_cycle.py picks them up with one dictionary entry. qpfaccum is
currently zero in the members (StormLab rain is folded into qpeaccum), so
a separate forecast-rain-only layer needs a pipeline change first.

## 2. Gauge time series (training session D2_S4)

What exists. Every run writes ts.<gauge>.crest.<cycle>.csv hydrographs at
three gauges (Rio Villalobos at Villa Nueva, at Petapa, and the basin
outlet at Palin; coordinates from the training 20_timeseries.py set). The
D2_S4 notebook established the reading: spaghetti or band plots per
family, peak statistics, QPE reconstruction reference.

In the viewer. DONE: prepare_cycle.py aggregates the member series into
min, median, max envelopes per family (nowcast = scampr + stream_sat,
forecast = stormlab) and per domain; clicking a gauge opens the
hydrograph with both families, the cycle time marker, hover readout and a
900 m / 90 m switch.

READY next: peak-time and peak-size histograms per gauge (the D2_S4
statistics) could be added to the modal from the same JSONs by shipping
the per-member peaks; add them to prepare_cycle.py when wanted.

## 3. UQ flood potential warning product (Tito\UQ_warnings)

What exists. The uq_warning_product pipeline classifies P(UQ >= 0.5) and
p90 into the four product classes (0.5, 1, 2, 4 with colors #7FDCBE,
#FFD23F, #F4802A, #AB1111) and delineates warning polygon products:
n900_pot_A/B (national) and v90_pot_A/B (Villalobos) GeoJSONs per cycle,
plus verification layers. The S6 training exercise turned the threshold
into a knob: probability mask, one step binary closing, 8 connectivity,
minimum area 25 cells, and the lesson that the threshold draws the zone.

In the viewer. The class colors and the probability logic are in the FIM
and IBF sections. DECISION (Sep 2026): the viewer does NOT produce or
display alert polygons; it shows only what TITO writes per cycle. The
polygon delineation method stays documented in the training material
(the S6 threshold exercise) for whenever the pipeline itself starts
emitting polygon products.

## 4. FIM flood map library (GT_train_case, fim_utils v0.4)

What exists. The Santa Ines Petapa library: 200 hydraulic scenarios in a
zarr store (5 m, EPSG 3857), pluvial and fluvial matching per member,
per-cycle products prob_depth_ge_{10,30,70,100}cm and likelihood_class in
raw and overbank variants for pluvial, fluvial and combined routines,
pf_summary.json, trigger and member decision tables. The depth explorer
notebook proved the products reduce to 6 matched maps, a weight sum and
three cuts. Caution recorded: the packaged store index.csv is stale; the
correct storm order is the rank by magnitudes_SantaInesPetapa_real.csv.

In the viewer. DONE: segment 3 shows combined_overbank probabilities at
the four thresholds as toggleable layers on the pilot window, with the
blue to purple product scale, auto zoom, and basin gating (FIM only in
basin mode).

READY next: likelihood_class layers (already in each cycle folder) as an
alternative "classes" view; the per-member matched-scenario table as a
popup fact ("this cycle matched N distinct scenarios"). PLANNED: more
pilot basins appear automatically once their FIM units run (the viewer's
basin list is data driven from data/gis/basins_90m.geojson).

## 5. IBF routine (ibf_utils, IBF design note)

What exists. The receptor pipeline (buildings, roads, admin units with
population; FGS flood risk matrix per Speight et al. 2018; severity
anchors 0.10, 0.30, 0.70 m; likelihood cutoff configurable) is merged in
the TITO repo and chained after FIM, but this cycle's zip contains no IBF
receptor outputs yet.

In the viewer. PARTIAL: segment 4 computes a grid-level FGS matrix
warning field from the FIM probabilities (very low to high, green,
yellow, amber, red) as an honest stand-in. PLANNED: when the pipeline
writes the receptor GeoPackage/CSV/JSON per cycle, prepare_cycle.py
converts buildings and roads at yellow and above to a GeoJSON and the
viewer draws them with the ibf_viz popup conventions; district choropleth
from the admin summary. The ibf_viz repo (AHWALab) already holds the
display language for that product.

## 6. Administrative and local data

What exists and is used (uq_warning_product\gis, prepared from SEGEPLAN
and INSIVUMEH datasets): nat_departamentos (22), nat_municipios (343 with
population and the vulnerability fields iv, exp, sen, cap),
nat_cabeceras (340), nat_floodprone (3751 settlements with amenaza class
and population), nat_carreteras, basin_aoi, and the AOI clips used in
training (vulnerabilidad_municipal_aoi, lugares_inundacion_aoi and
friends, all subsets of the national layers).

In the viewer. DONE: all six national layers plus the 90 m basin outline
and the gauge locations, with the project display conventions: dashed
boundaries and solid roads that turn white over satellite, settlement
dots never in the hazard palette (Muy Alta black with white rim, Alta
white with black rim), vulnerability terciles computed client side from
iv. The CONRED report points of the June 2023 event are training
verification data, deliberately not shown in a live forecast view.

## 7. Interactive precedents

FIM_results_explorer_20to22Jun2023.html (49 cycle hindcast stepper),
S6_mapa_amenaza.html, S7_mapa_fim.html, ejercicio_zonas_alerta.html, the
ibf_viz site. The viewer inherits their folium and Leaflet conventions
(legend boxes, layer control, white boundary rule, ASCII-only display
text). READY next: a cycle dropdown in the header once several cycles are
in data/cycles.json, which gives the explorer's step-through behavior for
free; the prepare script already maintains the list newest first.

## 8. INSIVUMEH receptor additions (IBFv1.1 package, Aug 2026)

The team package IBFv11_Guatemala_260820.zip adds two INSIVUMEH layers to
the IBF workflow: Puentes.shp (689 bridges) and Servicios_salud.shp
(3574 health facilities: health posts, health centers, convergence
centers, IGSS, hospitals), both in Guatemala Transverse Mercator,
ingested by the updated workflow (bridges_path, health_centers_path
config entries; exposure extracted per feature like roads). DONE in the
viewer: both are Image overlays (reprojected to EPSG 4326, slim fields,
name and municipio on hover). When the per-cycle IBF receptor outputs
ship, the same two receptor groups arrive classified by warning level.

## 9. Summary of next integration steps, in order of effort

1. DONE (Sep 2026): region and cycle dropdowns in the header. The page
   lists every cycle of data/cycles.json grouped by region and opens the
   first cycle of the deployment default (DEFAULT_REGION in index.html).
2. likelihood_class layers in segment 3.
3. Per-gauge peak statistics in the hydrograph modal.
4. IBF receptor products (now including bridges and health centers) once
   the pipeline ships them per cycle.
5. maxq composites if absolute discharge maps are wanted.
6. New pilot basins: add the outline to basins_90m.geojson and run their
   FIM units; the domain buttons and gating pick them up with no code
   change.

Note: producing warning polygons in or for the viewer is off the table by
decision; the viewer displays only what TITO writes.

## 10. Comoros integration (Sep 2026)

The 20251225 11:00-13:00 cycles came from the Comoros 30 m deployment
(STREAM-Sat QPE + 5 member StormLab QPF, one model grid). Differences
from Guatemala handled by prepare_cycle.py:

- One domain only (`comoros_30m`), so the viewer hides the domain switch
  and derives the base label from the manifest (`base_label`).
- FIM lives under `fim/stream_sat_stormlab/pluvial_overbank` (pluvial
  hazards only); the script selects the first existing variant of
  combined_overbank, pluvial_overbank, combined, pluvial.
- The FIM WKT is a bare LOCAL_CS (Moznet / UTM zone 38S), so the
  geographic bounds use a local UTM inverse fallback.
- No gauge time series on the stored cycles, so the Comoros context
  layers are the FIM commune outlines instead of the Guatemala
  administrative set (scripts/prepare_comoros_gis.py).

Multi-site layout (55 municipality stores). The first production runs
wrote every site into one shared folder, so each site overwrote the
previous one and only one municipality survived per cycle (rasters from
the last triggered site, summary from the last site processed; the
earlier Vouani/Moimbassa file mix came from exactly that). The TITO hook
now writes `fim/<chain>/<Site>/` per site and mosaics the triggered ones
(per-pixel max) into `fim/<chain>/<mode>/`, which is what the viewer
reads. prepare_cycle.py exports the triggered municipalities of each
cycle as `data/<cycle>/fim/triggered_sites.geojson`; the viewer adds it
as the "FIM triggered sites (N)" layer, so the outline always matches the
extent of the probability mosaic. Commune names are ASCII-folded from the
ADM3 spelling and matched to the site stems with accent/separator
insensitive folding.
