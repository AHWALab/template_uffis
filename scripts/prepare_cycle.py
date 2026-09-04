#!/usr/bin/env python3
"""Prepare one TITO forecast cycle for the UFFIS web viewer.

Reads the raw cycle folder that the pipeline writes (guatemala_900m and
guatemala_90m with their summary composites, plus guatemala_90m/fim) and
produces small web assets under data/<cycle>/:

  ef5/<product>_<mode>_<stat>_<domain>.png   colorized overlays
  fim/prob_ge_<TT>cm.png                     flood probability overlays
  ibf/warning_level.png                      FGS matrix warning grid
  manifest.json                              bounds, legends, cycle facts

Usage:
  python scripts/prepare_cycle.py <raw_cycle_dir> <repo_data_dir>
  e.g. python scripts/prepare_cycle.py raw/20260903.160000 data

The viewer (index.html) discovers cycles through data/cycles.json, which
this script updates. Static GIS context layers live in data/gis and are
shared by all cycles.
"""
import json
import sys
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


def bounds_4326(bounds, crs):
    if crs and crs.to_epsg() == 4326:
        return [bounds.bottom, bounds.left, bounds.top, bounds.right]
    from rasterio.warp import transform_bounds
    w, s, e, n = transform_bounds(crs, "EPSG:4326",
                                  bounds.left, bounds.bottom,
                                  bounds.right, bounds.top)
    return [s, w, n, e]


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


def main(raw_dir, data_dir):
    raw = Path(raw_dir)
    cycle = raw.name
    out = Path(data_dir) / cycle
    (out / "ef5").mkdir(parents=True, exist_ok=True)
    (out / "fim").mkdir(exist_ok=True)
    (out / "ibf").mkdir(exist_ok=True)
    manifest = {"cycle": cycle, "ef5": {}, "fim": {}, "ibf": {}, "legends": {}}

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
    domains = {"n": raw / "guatemala_900m" / "summary",
               "h": raw / "guatemala_90m" / "summary"}
    crop_cache = {}
    for dom, sdir in domains.items():
        for prod, (title, edges, colors, labels) in PRODUCTS.items():
            for mode in MODES:
                for stat in STATS:
                    tif = sdir / f"{prod}_{mode}_{stat}.{cycle}.tif"
                    if not tif.exists():
                        continue
                    a, b, crs = read_grid(tif)
                    if dom == "h":
                        key = a.shape
                        if key not in crop_cache:
                            _, cb = crop_to_valid(a, b)
                            crop_cache[key] = cb
                        a, b = crop_to_valid(a, b)
                    name = f"{prod}_{mode}_{stat}_{dom}.png"
                    save_png(colorize(a, edges, colors), out / "ef5" / name)
                    manifest["ef5"][name] = {
                        "bounds": bounds_4326(b, crs), "product": prod,
                        "mode": mode, "stat": stat, "domain": dom}
                    print("ef5", name, a.shape)

    # ---------------------------------------------------------------- FIM
    fim_dirs = list((raw / "guatemala_90m" / "fim").glob("*"))
    fim_root = fim_dirs[0] if fim_dirs else None
    probs = {}
    if fim_root:
        for tt in FIM_THRESHOLDS:
            tif = (fim_root / "combined_overbank" /
                   f"prob_depth_ge_{tt}cm_overbank.{cycle}.tif")
            if not tif.exists():
                continue
            a, b, crs = read_grid(tif)
            probs[tt] = a
            name = f"prob_ge_{tt}cm.png"
            save_png(colorize(a, PROB_EDGES, PROB_COLORS), out / "fim" / name)
            manifest["fim"][name] = {"bounds": bounds_4326(b, crs),
                                     "threshold_cm": int(tt)}
            print("fim", name, a.shape)
        pf = fim_root / "pf_summary.json"
        if pf.exists():
            s = json.load(open(pf))
            manifest["fim"]["summary"] = {
                "triggered": s["trigger"]["triggered"],
                "max_uq": s["trigger"]["max_uq"],
                "runs_checked": s["trigger"]["runs_checked"],
                "members_used": s["routines"]["PF"]["members_used"],
                "thresholds_m": s["thresholds_m"]}

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
        tif = (fim_root / "combined_overbank" /
               f"prob_depth_ge_10cm_overbank.{cycle}.tif")
        _, b, crs = read_grid(tif)
        manifest["ibf"]["warning_level.png"] = {"bounds": bounds_4326(b, crs)}
        counts = {lab: int((warn == k).sum())
                  for k, lab in enumerate(IBF_LABELS, start=1)}
        manifest["ibf"]["cell_counts"] = counts
        print("ibf warning_level.png", counts)

    # ------------------------------------------------------- time series
    # One JSON per gauge and domain: the ensemble envelope (min, median,
    # max) of the member discharge series, split into the nowcast family
    # (scampr + stream_sat runs) and the forecast family (stormlab runs).
    (out / "ts").mkdir(exist_ok=True)
    import csv as _csv

    def read_series(path):
        d = {}
        with open(path) as fh:
            rd = _csv.reader(fh)
            header = next(rd)
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

    dom_dirs = {"n": raw / "guatemala_900m", "h": raw / "guatemala_90m"}
    for dom, droot in dom_dirs.items():
        if not droot.exists():
            continue
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

    # -------------------------------------------- static gis (write once)
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
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
