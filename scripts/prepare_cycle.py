#!/usr/bin/env python3
"""Prepare one TITO forecast cycle for the UFFIS web viewer.

Reads the raw cycle folder that the pipeline writes (one `<region>_<res>`
model folder with a summary/ composite per domain, plus its fim/ routine
folders) and produces small web assets under data/<cycle>/:

  ef5/<product>_<mode>_<stat>_<domain>.png   colorized overlays
  fim/prob_ge_<TT>cm.png                     flood probability overlays
  ibf/warning_level.png                      FGS matrix warning grid
  manifest.json                              bounds, legends, cycle facts

Usage:
  python scripts/prepare_cycle.py <raw_cycle_dir> <repo_data_dir>
                                  [--region NAME]

  e.g. python scripts/prepare_cycle.py raw/20260903.160000 data
       python scripts/prepare_cycle.py raw/20251225.120000 data --region comoros

Model domains are auto-detected: every sub folder that holds a summary/
directory is one domain. The coarsest resolution becomes the "n" (base)
domain, a second one becomes "h" (higher resolution overlay). Guatemala
writes combined_overbank FIM products, Comoros writes pluvial_overbank
ones; the first available variant of combined_overbank, pluvial_overbank,
combined, pluvial is used.

Comoros FIM rasters are georeferenced in the store grid (Moznet / UTM zone
38S) and their WKT carries no EPSG code, so the geographic bounds fall back
to a local UTM inverse transform when rasterio cannot reproject.

The viewer (index.html) discovers cycles through data/cycles.json, which
this script updates. Static GIS context layers live in data/gis (Guatemala)
and data/gis_comoros (Comoros) and are shared by all cycles of a region.
"""
import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

# ---------------------------------------------------------------- palettes
RAIN_EDGES = [1, 5, 10, 25, 50, 75, 100, 150, 250, 100000]
RAIN_COLORS = ["#B8E186", "#66BD63", "#1A9850", "#FFFFBF", "#FDAE61",
               "#F46D43", "#D73027", "#A50026", "#762A83"]
RAIN_LABELS = ["1 to 5", "5 to 10", "10 to 25", "25 to 50", "50 to 75",
               "75 to 100", "100 to 150", "150 to 250", "250 and more"]

UQ_EDGES = [0.1, 1, 2, 4, 6, 10, 20, 100000]
UQ_COLORS = ["#ACACAC", "#C8CE33", "#F79320", "#BC3F34", "#D14FC8",
             "#2B2BD5", "#FFFFFF"]
UQ_LABELS = ["0.1 to 1", "1 to 2", "2 to 4", "4 to 6", "6 to 10",
             "10 to 20", "20 and more"]

SM_EDGES = [10, 30, 50, 70, 85, 95, 101]
SM_COLORS = ["#F6E8C3", "#DFC27D", "#80CDC1", "#35978F", "#01665E",
             "#003C30"]
SM_LABELS = ["10 to 30", "30 to 50", "50 to 70", "70 to 85", "85 to 95",
             "95 to 100"]

PROB_EDGES = [0.05, 0.2, 0.5, 0.8, 1.01]
PROB_COLORS = ["#BFDBFE", "#60A5FA", "#2563EB", "#7C3AED"]
PROB_LABELS = ["5 to 20 percent", "20 to 50", "50 to 80", "80 to 100"]

IBF_COLORS = ["#8DC63F", "#FFF200", "#F7941D", "#ED1C24"]
IBF_LABELS = ["Very low", "Low", "Medium", "High"]

PRODUCTS = {
    "qpeaccum": ("Rainfall accumulation (mm)", RAIN_EDGES, RAIN_COLORS, RAIN_LABELS),
    "maxunitq": ("Max unit streamflow (m3/s per km2)", UQ_EDGES, UQ_COLORS, UQ_LABELS),
    "maxsm": ("Soil saturation (percent)", SM_EDGES, SM_COLORS, SM_LABELS),
}
MODES = ["nowcast", "forecast"]
STATS = ["min", "median", "max"]
FIM_THRESHOLDS = ["10", "30", "70", "100"]
FIM_VARIANTS = ["combined_overbank", "pluvial_overbank", "combined", "pluvial"]

# Per region viewer defaults (labels, start view). Regions without an entry
# fall back to derived labels and to fitting the base domain on the map.
REGION_META = {
    "comoros": {
        "label": "Comoros",
        "base_label": "Comoros 30 m",
        "view": {"center": [-11.88, 43.885], "zoom": 9},
    },
    "guatemala": {
        "label": "Guatemala",
        "base_label": "National 900 m",
        "view": {"center": [14.95, -90.65], "zoom": 8},
    },
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def read_grid(path):
    with rasterio.open(path) as src:
        a = src.read(1).astype("float32")
        if src.nodata is not None:
            a[a == src.nodata] = np.nan
        return a, src.bounds, src.crs


def colorize(a, edges, colors, alpha=210):
    """Classified RGBA image; below the first edge or NaN is transparent."""
    rgba = np.zeros(a.shape + (4,), dtype=np.uint8)
    vals = np.nan_to_num(a, nan=-1e30)
    for lo, hi, color in zip(edges[:-1], edges[1:], colors):
        r, g, b = hex_to_rgb(color)
        rgba[(vals >= lo) & (vals < hi)] = (r, g, b, alpha)
    return rgba


def save_png(rgba, path):
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


# ------------------------------------------------------------- georeference
def utm_zone_from_crs(crs):
    """(zone, south) parsed from a CRS name or proj string, else None."""
    try:
        text = crs.to_string()
    except Exception:
        return None
    m = re.search(r"UTM zone (\d+)([NS])", text)
    if m:
        return int(m.group(1)), m.group(2) == "S"
    m = re.search(r"\+proj=utm\s+\+zone=(\d+)(?:\s+\+south)?", text)
    if m:
        return int(m.group(1)), "+south" in text
    return None


def utm_to_lonlat(zone, south, easting, northing):
    """Inverse transverse Mercator on WGS84; metres -> degrees.

    Used only when rasterio cannot reproject because the raster WKT has no
    EPSG code (Comoros FIM products carry a bare LOCAL_CS name)."""
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0 = 0.9996
    x = easting - 500000.0
    y = northing
    if south:
        y -= 10000000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    sp, cp, tp = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sp ** 2)
    r1 = a * (1 - e2) / (1 - e2 * sp ** 2) ** 1.5
    t1, c1 = tp ** 2, ep2 * cp ** 2
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tp / r1) * (
        d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon0 = math.radians(zone * 6 - 183)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2
                     + 24 * t1 ** 2) * d ** 5 / 120) / cp
    return math.degrees(lon), math.degrees(lat)


def bounds_4326(bounds, crs):
    if crs is None or crs.is_geographic:
        return [bounds.bottom, bounds.left, bounds.top, bounds.right]
    try:
        from rasterio.warp import transform_bounds
        w, s, e, n = transform_bounds(crs, "EPSG:4326",
                                      bounds.left, bounds.bottom,
                                      bounds.right, bounds.top)
        return [s, w, n, e]
    except Exception:
        pass
    zone = utm_zone_from_crs(crs)
    if zone:
        z, south = zone
        lons, lats = [], []
        for x, y in [(bounds.left, bounds.bottom), (bounds.left, bounds.top),
                     (bounds.right, bounds.bottom), (bounds.right, bounds.top)]:
            lon, lat = utm_to_lonlat(z, south, x, y)
            lons.append(lon)
            lats.append(lat)
        return [min(lats), min(lons), max(lats), max(lons)]
    raise RuntimeError("cannot georeference raster: %s" % crs)


def crop_to_valid(a, bounds):
    """Crop the grid to the rows and columns that hold any finite value."""
    valid = np.isfinite(a)
    rows = np.where(valid.any(axis=1))[0]
    cols = np.where(valid.any(axis=0))[0]
    if len(rows) == 0:
        return a, bounds
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    c0, c1 = int(cols.min()), int(cols.max()) + 1
    h, w = a.shape
    dy = (bounds.top - bounds.bottom) / h
    dx = (bounds.right - bounds.left) / w
    new = rasterio.coords.BoundingBox(
        left=bounds.left + c0 * dx, bottom=bounds.top - r1 * dy,
        right=bounds.left + c1 * dx, top=bounds.top - r0 * dy)
    return a[r0:r1, c0:c1], new


def model_dirs(raw):
    """Summary-capable model folders, coarsest resolution first (n, h)."""
    dirs = [d for d in sorted(raw.iterdir())
            if d.is_dir() and (d / "summary").is_dir()]

    def res(d):
        m = re.search(r"_(\d+)m", d.name)
        return -int(m.group(1)) if m else 0

    return sorted(dirs, key=res)


def find_fim(raw, dirs):
    """First FIM routine folder and the product variant to read.

    The finest model grid is searched first (FIM runs on the high
    resolution domain only)."""
    for md in reversed(dirs):
        froot = md / "fim"
        if not froot.is_dir():
            continue
        for routine in sorted(p for p in froot.iterdir() if p.is_dir()):
            for variant in FIM_VARIANTS:
                vdir = routine / variant
                if vdir.is_dir():
                    return routine, vdir, variant.endswith("overbank")
    return None, None, False


def main(raw_dir, data_dir, region=None):
    raw = Path(raw_dir)
    cycle = raw.name
    dirs = model_dirs(raw)
    if not dirs:
        raise SystemExit("no <model>/summary folder found in %s" % raw)
    keys = ["n", "h", "m", "p"][:len(dirs)]
    domains = dict(zip(keys, dirs))

    region_key = region or dirs[0].name.split("_")[0]
    meta = REGION_META.get(region_key, {})

    out = Path(data_dir) / cycle
    (out / "ef5").mkdir(parents=True, exist_ok=True)
    (out / "fim").mkdir(exist_ok=True)
    (out / "ibf").mkdir(exist_ok=True)
    manifest = {"cycle": cycle, "region": region_key,
                "region_label": meta.get("label", region_key.title()),
                "ef5": {}, "fim": {}, "ibf": {}, "legends": {}}
    if "base_label" in meta:
        manifest["base_label"] = meta["base_label"]
    else:
        m = re.search(r"_(\d+m)", dirs[0].name)
        manifest["base_label"] = "%s %s" % (manifest["region_label"],
                                            m.group(1) if m else "")
    if "view" in meta:
        manifest["view"] = meta["view"]

    manifest["legends"] = {
        "qpeaccum": {"title": "Rainfall accumulation (mm)",
                     "colors": RAIN_COLORS, "labels": RAIN_LABELS},
        "maxunitq": {"title": "Max unit streamflow (m3/s per km2)",
                     "colors": UQ_COLORS, "labels": UQ_LABELS},
        "maxsm": {"title": "Soil saturation (percent)",
                  "colors": SM_COLORS, "labels": SM_LABELS},
        "fimprob": {"title": "Probability, fraction of members",
                    "colors": PROB_COLORS, "labels": PROB_LABELS},
        "ibf": {"title": "IBF warning level (FGS matrix)",
                "colors": IBF_COLORS, "labels": IBF_LABELS},
    }

    # ---------------------------------------------------------------- EF5
    for dom, mdir in domains.items():
        sdir = mdir / "summary"
        for prod, (title, edges, colors, labels) in PRODUCTS.items():
            for mode in MODES:
                for stat in STATS:
                    tif = sdir / f"{prod}_{mode}_{stat}.{cycle}.tif"
                    if not tif.exists():
                        continue
                    a, b, crs = read_grid(tif)
                    if dom != "n":
                        a, b = crop_to_valid(a, b)
                    name = f"{prod}_{mode}_{stat}_{dom}.png"
                    save_png(colorize(a, edges, colors), out / "ef5" / name)
                    manifest["ef5"][name] = {
                        "bounds": bounds_4326(b, crs), "product": prod,
                        "mode": mode, "stat": stat, "domain": dom}
                    print("ef5", name, a.shape)

    # ---------------------------------------------------------------- FIM
    routine, fim_root, overbank = find_fim(raw, dirs)
    probs = {}
    if fim_root:
        suffix = "_overbank" if overbank else ""
        for tt in FIM_THRESHOLDS:
            tif = fim_root / f"prob_depth_ge_{tt}cm{suffix}.{cycle}.tif"
            if not tif.exists():
                continue
            a, b, crs = read_grid(tif)
            probs[tt] = a
            name = f"prob_ge_{tt}cm.png"
            save_png(colorize(a, PROB_EDGES, PROB_COLORS), out / "fim" / name)
            manifest["fim"][name] = {"bounds": bounds_4326(b, crs),
                                     "threshold_cm": int(tt)}
            print("fim", name, a.shape)
        manifest["fim"]["variant"] = fim_root.name
        pf = routine / "pf_summary.json"
        if pf.exists():
            s = json.load(open(pf))
            trig = s.get("trigger", {})
            summary = {"triggered": trig.get("triggered"),
                       "max_uq": trig.get("max_uq"),
                       "runs_checked": trig.get("runs_checked"),
                       "thresholds_m": s.get("thresholds_m")}
            members = (s.get("routines", {}).get("PF", {}) or {}).get("members_used")
            if members is not None:
                summary["members_used"] = members
            manifest["fim"]["summary"] = summary

    # ---------------------------------------------------------------- IBF
    # Grid-level warning per the Flood Guidance Statement matrix
    # (Speight et al. 2018). Severity anchors follow the project defaults:
    # Minor P(depth >= 10 cm), Significant P(>= 30 cm), Severe P(>= 70 cm).
    # Likelihood bands: below 5 percent no signal, Very Low below 20,
    # Low 20 to 40, Medium 40 to 60, High 60 and more.
    if all(t in probs for t in ("10", "30", "70")):
        def band(P):
            bd = np.zeros(P.shape, dtype="uint8")
            bd[P >= 0.05] = 1
            bd[P >= 0.2] = 2
            bd[P >= 0.4] = 3
            bd[P >= 0.6] = 4
            return bd
        MATRIX = {  # severity -> warning level per likelihood band 1..4
            "minor":       [0, 1, 1, 1, 2],
            "significant": [0, 1, 2, 2, 3],
            "severe":      [0, 2, 3, 3, 4],
        }
        warn = np.zeros(probs["10"].shape, dtype="uint8")
        for sev, key in [("minor", "10"), ("significant", "30"),
                         ("severe", "70")]:
            lut = np.array(MATRIX[sev], dtype="uint8")
            warn = np.maximum(warn, lut[band(np.nan_to_num(probs[key]))])
        rgba = np.zeros(warn.shape + (4,), dtype=np.uint8)
        for level, color in enumerate(IBF_COLORS, start=1):
            r, g, bl = hex_to_rgb(color)
            rgba[warn == level] = (r, g, bl, 215)
        save_png(rgba, out / "ibf" / "warning_level.png")
        tif = next(iter((fim_root).glob(f"prob_depth_ge_10cm{suffix}.*.tif")))
        _, b, crs = read_grid(tif)
        manifest["ibf"]["warning_level.png"] = {"bounds": bounds_4326(b, crs)}
        counts = {lab: int((warn == k).sum())
                  for k, lab in enumerate(IBF_LABELS, start=1)}
        manifest["ibf"]["cell_counts"] = counts
        print("ibf warning_level.png", counts)

    # ------------------------------------------------------- time series
    # One JSON per gauge and domain: the ensemble envelope (min, median,
    # max) of the member discharge series, split into the nowcast family
    # (observed rainfall runs) and the forecast family (stormlab runs).
    (out / "ts").mkdir(exist_ok=True)
    import csv as _csv

    def read_series(path):
        d = {}
        with open(path) as fh:
            rd = _csv.reader(fh)
            next(rd)
            for row in rd:
                try:
                    d[row[0]] = float(row[1])
                except (ValueError, IndexError):
                    pass
        return d

    def family_stats(files):
        members = [read_series(p) for p in files]
        members = [m for m in members if m]
        if not members:
            return None
        counts = {}
        for m in members:
            for t in m:
                counts[t] = counts.get(t, 0) + 1
        need = max(1, int(0.8 * len(members)))
        times = sorted(t for t, c in counts.items() if c >= need)
        mn, md, mx = [], [], []
        for t in times:
            vals = sorted(m[t] for m in members if t in m)
            mn.append(round(vals[0], 2))
            md.append(round(vals[len(vals) // 2], 2))
            mx.append(round(vals[-1], 2))
        return {"times": times, "min": mn, "median": md, "max": mx,
                "members": len(members)}

    for dom, droot in domains.items():
        gauge_ids = set()
        for p in droot.glob("*/*/ts.*.crest.*.csv"):
            gauge_ids.add(p.name.split(".")[1])
        for g in sorted(gauge_ids):
            fam = {}
            now_files = list(droot.glob(f"scampr/*/ts.{g}.crest.*.csv")) + \
                        list(droot.glob(f"stream_sat/*/ts.{g}.crest.*.csv"))
            fc_files = list(droot.glob(f"stormlab/*/ts.{g}.crest.*.csv"))
            s = family_stats(now_files)
            if s:
                fam["nowcast"] = s
            s = family_stats(fc_files)
            if s:
                fam["forecast"] = s
            if not fam:
                continue
            js = {"gauge": g, "domain": dom, "cycle": cycle, "families": fam}
            with open(out / "ts" / f"{g}_{dom}.json", "w") as f:
                json.dump(js, f)
            manifest.setdefault("ts", {})[f"{g}_{dom}"] = {
                k: v["members"] for k, v in fam.items()}
            print("ts", g, dom, {k: v["members"] for k, v in fam.items()})

    # -------------------------------------------- static gis (Guatemala)
    # The Comoros context layers (FIM site and commune outlines) are built
    # by scripts/prepare_comoros_gis.py and committed under data/gis_comoros.
    if region_key == "guatemala":
        gis_dir = Path(data_dir) / "gis"
        gis_dir.mkdir(exist_ok=True)
        gauges_path = gis_dir / "gauges.geojson"
        if not gauges_path.exists():
            GAUGES = {
                "cuenca_villalobos_1": {"name": "Rio Villalobos at Villa Nueva",
                                        "lat": 14.487846, "lon": -90.535389},
                "cuenca_villalobos_2": {"name": "Rio Villalobos at Petapa",
                                        "lat": 14.486986, "lon": -90.541955},
                "cuenca_villalobos_out": {"name": "Basin outlet, Michatoya at Palin",
                                          "lat": 14.412713, "lon": -90.671137},
            }
            gj = {"type": "FeatureCollection", "features": [
                {"type": "Feature",
                 "properties": {"id": k, "name": v["name"], "basin": "villalobos"},
                 "geometry": {"type": "Point",
                              "coordinates": [v["lon"], v["lat"]]}}
                for k, v in GAUGES.items()]}
            json.dump(gj, open(gauges_path, "w"))
            print("wrote", gauges_path)
        basins_path = gis_dir / "basins_90m.geojson"
        if not basins_path.exists() and (gis_dir / "basin_aoi.geojson").exists():
            b = json.load(open(gis_dir / "basin_aoi.geojson"))
            for f in b["features"]:
                f["properties"] = {"id": "villalobos", "name": "Cuenca Villalobos"}
            json.dump(b, open(basins_path, "w"))
            print("wrote", basins_path)

    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)

    # update the cycle index (newest first)
    idx_path = Path(data_dir) / "cycles.json"
    cycles = []
    if idx_path.exists():
        cycles = json.load(open(idx_path))
    if cycle not in cycles:
        cycles.append(cycle)
    cycles = sorted(cycles, reverse=True)
    json.dump(cycles, open(idx_path, "w"), indent=1)
    print("manifest written, cycles:", cycles)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raw_dir", help="raw cycle folder written by the pipeline")
    ap.add_argument("data_dir", help="viewer data folder, usually data")
    ap.add_argument("--region", default=None,
                    help="region key for labels and the start view "
                         "(default: inferred from the model folder name, "
                         "e.g. comoros_30m -> comoros)")
    args = ap.parse_args()
    main(args.raw_dir, args.data_dir, args.region)
