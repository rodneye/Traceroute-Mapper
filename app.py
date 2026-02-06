import os
from typing import Dict, List

import pandas as pd
import pydeck as pdk
import streamlit as st

from geoip import geolocate_ips
from records import build_records
from traceroute_runner import trace_targets


def parse_targets(value: str) -> List[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def render_dataframe(df: pd.DataFrame) -> None:
    try:
        st.dataframe(df, width="stretch")
    except TypeError:
        st.dataframe(df, use_container_width=True)


PALETTE = [
    [27, 158, 119],
    [217, 95, 2],
    [117, 112, 179],
    [231, 41, 138],
    [102, 166, 30],
    [230, 171, 2],
    [166, 118, 29],
    [102, 102, 102],
]

GRAYSCALE_BASE = [20, 40, 60, 80, 100, 120, 140, 160]


def make_grayscale_palette(level: int) -> List[List[int]]:
    # level: 0 (dark) -> 100 (light)
    offset = int((level - 50) * 1.6)
    palette = []
    for base in GRAYSCALE_BASE:
        value = max(0, min(230, base + offset))
        palette.append([value, value, value])
    return palette


def build_color_map(
    destinations: List[str],
    grayscale: bool,
    grayscale_level: int,
) -> Dict[str, List[int]]:
    palette = make_grayscale_palette(grayscale_level) if grayscale else PALETTE
    return {dest: palette[i % len(palette)] for i, dest in enumerate(destinations)}


def format_total_rtt(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:.1f} ms"


def render_legend_filter(
    destinations: List[str],
    color_map: Dict[str, List[int]],
    totals: Dict[str, float],
):
    if not destinations:
        return []

    count = len(destinations)
    if count >= 9:
        cols_per_row = 3
    elif count >= 5:
        cols_per_row = 2
    else:
        cols_per_row = 1

    selected: List[str] = []
    for start in range(0, count, cols_per_row):
        row_items = destinations[start : start + cols_per_row]
        row_cols = st.columns(cols_per_row)
        for col, dest in zip(row_cols, row_items):
            with col:
                color = color_map[dest]
                rtt_label = format_total_rtt(totals.get(dest, float("nan")))
                item_cols = st.columns([0.12, 0.88])
                with item_cols[0]:
                    st.markdown(
                        '<div style="width:12px;height:12px;'
                        f'background-color: rgb({color[0]}, {color[1]}, {color[2]});'
                        'border-radius:2px;margin-top:6px;"></div>',
                        unsafe_allow_html=True,
                    )
                with item_cols[1]:
                    label = f"{dest} (total rtt {rtt_label})"
                    key = f"legend_{dest}"
                    if key in st.session_state:
                        checked = st.checkbox(label, key=key)
                    else:
                        checked = st.checkbox(label, value=True, key=key)
                if checked:
                    selected.append(dest)

    return selected



def build_map(
    df: pd.DataFrame,
    color_map: Dict[str, List[int]],
    show_hop_numbers: bool,
    map_style: str,
    monochrome: bool,
    outline_color: List[int],
    line_width_scale: int,
    line_width_min: int,
):
    if df.empty:
        st.info("No geolocated hops to map.")
        return

    df = df.copy()
    df["hop_label"] = df["hop"].apply(lambda v: "" if pd.isna(v) else str(int(v)))
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        st.info("No geolocated hops to map.")
        return

    destinations = sorted(df["destination"].unique())
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
        get_radius=30000,
        radius_min_pixels=4,
        get_line_color=outline_color,
        line_width_min_pixels=1,
        pickable=True,
    )

    layers = [scatter]

    if show_hop_numbers:
        text = pdk.Layer(
            "TextLayer",
            data=df,
            get_position="[lon, lat]",
            get_text="hop_label",
            get_color=[0, 0, 0, 220],
            get_size=12,
            size_min_pixels=12,
            size_max_pixels=24,
            billboard=True,
            get_text_anchor="start",
            get_alignment_baseline="bottom",
        )
        layers.append(text)

    if paths:
        path_color = [0, 0, 0] if monochrome else "color"
        path_layer = pdk.Layer(
            "PathLayer",
            data=paths,
            get_path="path",
            get_color=path_color,
            width_scale=line_width_scale,
            width_min_pixels=line_width_min,
            pickable=False,
        )
        layers.append(path_layer)

    view_state = pdk.ViewState(
        latitude=float(df["lat"].mean()),
        longitude=float(df["lon"].mean()),
        zoom=1.2,
    )

    tooltip = {
        "html": (
            "<b>{ip}</b><br/>"
            "Hop {hop}<br/>"
            "Latency: {rtt_ms} ms<br/>"
            "Reachable: {reachable}<br/>"
            "{city} {region} {country}<br/>"
            "{org}"
        ),
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=map_style,
        )
    )


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
    grayscale = st.checkbox("Grayscale map", value=False)
    map_style_label = st.selectbox(
        "Map style",
        ["Light", "Dark", "Monochrome"],
        index=0,
    )
    grayscale_level = st.slider(
        "Grayscale brightness",
        min_value=0,
        max_value=100,
        value=40,
    )
    line_thickness = st.slider(
        "Route thickness (px)",
        min_value=1,
        max_value=10,
        value=4,
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

        st.session_state["df"] = df

df = st.session_state.get("df", pd.DataFrame())

if not df.empty:
    destinations = sorted(df["destination"].unique())
    monochrome = grayscale or map_style_label == "Monochrome"
    color_map = build_color_map(
        destinations,
        grayscale=monochrome,
        grayscale_level=grayscale_level,
    )
    show_hop_numbers = False
    rtt_num = pd.to_numeric(df["rtt_ms"], errors="coerce")
    totals = (
        df.assign(rtt_num=rtt_num)
        .groupby("destination")["rtt_num"]
        .sum(min_count=1)
        .to_dict()
    )
    hop_container = st.container()
    legend_container = st.container()
    map_container = st.container()

    with legend_container:
        st.subheader("Legend")
        selected_destinations = render_legend_filter(destinations, color_map, totals)

    filtered = df[df["destination"].isin(selected_destinations)].copy()

    if filtered.empty:
        with map_container:
            st.info("No destinations selected.")
    else:
        with hop_container:
            st.subheader("Hop Data")
            render_dataframe(filtered)

        with map_container:
            st.subheader("Map")
            style_map = {
                "Light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                "Dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                "Monochrome": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            }
            outline_color = [0, 0, 0] if map_style_label != "Dark" else [255, 255, 255]
            line_width_min = int(line_thickness)
            line_width_scale = max(10, int(line_thickness) * 10)
            build_map(
                filtered,
                color_map=color_map,
                show_hop_numbers=show_hop_numbers,
                map_style=style_map.get(map_style_label, style_map["Light"]),
                monochrome=monochrome,
                outline_color=outline_color,
                line_width_scale=line_width_scale,
                line_width_min=line_width_min,
            )
