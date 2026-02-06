import os
from typing import List

import pandas as pd
import pydeck as pdk
import streamlit as st

from geoip import geolocate_ips
from records import build_records
from traceroute_runner import trace_targets


def parse_targets(value: str) -> List[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def build_map(df: pd.DataFrame):
    if df.empty:
        st.info("No geolocated hops to map.")
        return

    df = df.copy()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        st.info("No geolocated hops to map.")
        return

    destinations = sorted(df["destination"].unique())
    palette = [
        [27, 158, 119],
        [217, 95, 2],
        [117, 112, 179],
        [231, 41, 138],
        [102, 166, 30],
        [230, 171, 2],
        [166, 118, 29],
        [102, 102, 102],
    ]
    color_map = {dest: palette[i % len(palette)] for i, dest in enumerate(destinations)}
    df["color"] = df["destination"].map(color_map)

    paths = []
    for dest in destinations:
        subset = df[df["destination"] == dest].sort_values("hop")
        coords = subset[["lon", "lat"]].values.tolist()
        if len(coords) >= 2:
            paths.append({"destination": dest, "path": coords, "color": color_map[dest]})

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_color="color",
        get_radius=25000,
        radius_min_pixels=3,
        pickable=True,
    )

    layers = [scatter]

    if paths:
        path_layer = pdk.Layer(
            "PathLayer",
            data=paths,
            get_path="path",
            get_color="color",
            width_scale=20,
            width_min_pixels=2,
            pickable=False,
        )
        layers.append(path_layer)

    view_state = pdk.ViewState(
        latitude=float(df["lat"].mean()),
        longitude=float(df["lon"].mean()),
        zoom=1.2,
    )

    tooltip = {
        "html": "<b>{ip}</b><br/>Hop {hop}<br/>{city} {region} {country}",
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip))


st.set_page_config(page_title="Traceroute Mapper", layout="wide")

st.title("Traceroute Mapper")

with st.sidebar:
    st.header("Settings")
    targets_str = st.text_input("Targets (comma-separated IPs)", "8.8.8.8,1.1.1.1")
    source_ip = st.text_input("Source IP (optional)", "")
    max_hops = st.number_input("Max hops", min_value=1, max_value=64, value=30)
    timeout = st.number_input("Timeout (seconds)", min_value=1, max_value=10, value=2)
    queries = st.number_input("Queries per hop", min_value=1, max_value=5, value=1)
    geo_cache = st.text_input("Geo cache CSV", "data/geocache.csv")
    ipinfo_token = st.text_input(
        "IPinfo token (optional)",
        os.environ.get("IPINFO_TOKEN", ""),
        type="password",
    )
    run = st.button("Run traceroute")

st.caption("Note: Setting a source IP may require root privileges on Linux.")

if run:
    targets = parse_targets(targets_str)
    if not targets:
        st.error("Please enter at least one target IP.")
    else:
        status = st.status("Running traceroutes...", expanded=False)
        try:
            results = trace_targets(
                targets=targets,
                source=source_ip or None,
                max_hops=int(max_hops),
                timeout=int(timeout),
                queries=int(queries),
            )
            status.update(label="Geolocating hops...", state="running")
            hop_ips = [hop.ip for hops in results.values() for hop in hops if hop.ip]
            geo = geolocate_ips(hop_ips, cache_path=geo_cache, token=ipinfo_token or None)
            records = build_records(results, geo)
            df = pd.DataFrame(records)
            status.update(label="Done", state="complete")
        except Exception as exc:
            status.update(label="Failed", state="error")
            st.exception(exc)
            df = pd.DataFrame()

        if not df.empty:
            st.subheader("Hop Data")
            st.dataframe(df, width="stretch")

            st.subheader("Map")
            build_map(df)
