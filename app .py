import streamlit as st
import pickle
import numpy as np
import requests
import folium
from folium.plugins import HeatMap, MiniMap
from streamlit_folium import st_folium
import pandas as pd
import time
from geopy.geocoders import Nominatim

# ===== CONFIG =====
st.set_page_config(page_title="ADORA", layout="centered")

# ===== SESSION =====
if "show_result" not in st.session_state:
    st.session_state.show_result = False

if "geo" not in st.session_state:
    st.session_state.geo = None

# ===== STYLE =====
st.markdown("""
<style>
body { background-color: #0e1117; }
.stTextInput, .stNumberInput, .stSelectbox {
    background-color: #1e1e2f;
    padding: 10px;
    border-radius: 10px;
}
.stButton button {
    background-color: #ff4b4b;
    color: white;
    border-radius: 10px;
    height: 50px;
    font-size: 18px;
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

# ===== HEADER =====
st.markdown("""
<h1 style='text-align: center;'>🏠 ADORA</h1>
<p style='text-align: center; color: gray;'>Smart rent. Better choice.</p>
""", unsafe_allow_html=True)

# ===== LOAD MODEL =====
model = pickle.load(open("model.pkl", "rb"))

# ===== API KEY =====
API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjMzNDdmOTk2ZDI4NjQ3NzQ4ZjQ1YjYwNGZjYjBiY2Y3IiwiaCI6Im11cm11cjY0In0="

# ===== CAMPUS (lat, lon) =====
campuses = {
    "UEH - Cơ sở A": (10.7769, 106.7009),
    "UEH - Cơ sở B": (10.7626, 106.6660),
    "UEH - Cơ sở N": (10.7306, 106.6943)
}

# ===== INPUT =====
col1, col2 = st.columns(2)

with col1:
    address = st.text_input("📍 Địa chỉ")
    area = st.number_input("📐 Diện tích (m²)", min_value=0.0)

with col2:
    so_nguoi = st.number_input("👥 Số người", min_value=1)
    campus_name = st.selectbox("🏫 Cơ sở", list(campuses.keys()))

tien_nghi = st.selectbox("❄️ Tiện nghi", ["Có", "Không"])
gio_giac = st.selectbox("⏰ Giờ giấc tự do", ["Có", "Không"])
tien_ich = st.selectbox("🏪 Tiện ích xung quanh", ["Có", "Không"])

tien_nghi = 1 if tien_nghi == "Có" else 0
gio_giac = 1 if gio_giac == "Có" else 0
tien_ich = 1 if tien_ich == "Có" else 0

# ===== GEO (CACHE) -> (lat, lon) =====
@st.cache_data(show_spinner=False)
def geocode_cached(address):
    geolocator = Nominatim(user_agent="adora_app")
    for _ in range(3):
        try:
            loc = geolocator.geocode(address, timeout=10)
            if loc:
                return loc.latitude, loc.longitude  # (lat, lon)
        except:
            time.sleep(1)
    return 10.7769, 106.7009  # fallback HCM

# ===== DISTANCE (km) =====
def get_distance(coord1, coord2):
    # coord = (lat, lon)
    try:
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {
            "Authorization": API_KEY,
            "Content-Type": "application/json"
        }
        body = {
            "coordinates": [
                [coord1[1], coord1[0]],  # ORS cần (lon, lat)
                [coord2[1], coord2[0]]
            ]
        }
        res = requests.post(url, json=body, headers=headers)
        data = res.json()
        return data["routes"][0]["summary"]["distance"] / 1000
    except:
        # fallback haversine đơn giản
        return np.sqrt(
            (coord1[0] - coord2[0])**2 +
            (coord1[1] - coord2[1])**2
        ) * 111

# ===== LOAD DATA REAL + FIX =====
@st.cache_data
def load_real_data():
    df = pd.read_excel("bandau_full.xlsx")

    # chuẩn hoá tên cột
    df = df.rename(columns={
        "latitude": "lat",
        "longitude": "lon",
        "Lat": "lat",
        "Lng": "lon"
    })

    df = df.dropna(subset=["lat", "lon"])

    fixed = []

    for _, r in df.iterrows():
        lat = r["lat"]
        lon = r["lon"]

        # auto-fix đảo nếu bị swap
        if lat > 50:  # VN lat ~10-11
            lat, lon = lon, lat

        # auto-fix scale (vd 106700)
        if lat > 1000:
            lat /= 10000
            lon /= 10000

        fixed.append((lat, lon))

    return fixed

# ===== BUTTON =====
if st.button("🔮 Dự đoán ngay"):
    st.session_state.show_result = True
    st.session_state.geo = None

# ===== RESULT =====
if st.session_state.show_result:

    if not address:
        st.warning("⚠️ Vui lòng nhập địa chỉ")
        st.stop()

    if st.session_state.geo is None:
        st.session_state.geo = geocode_cached(address.strip())

    geo = st.session_state.geo          # (lat, lon)
    campus_coord = campuses[campus_name]# (lat, lon)

    distance = get_distance(geo, campus_coord)

    features = np.array([[distance, area, tien_nghi, gio_giac, so_nguoi, tien_ich]])
    price = model.predict(features)[0]

    # ===== RESULT CARD =====
    st.markdown(f"""
    <div style='background-color:#1e1e2f;padding:20px;border-radius:15px;text-align:center;'>
        <h3 style='color:#00ffcc;'>📏 {distance:.2f} km</h3>
        <h2 style='color:#ff4b4b;'>💰 {int(price):,} VND</h2>
        <p style='color:gray;'>Giá dự đoán</p>
    </div>
    """, unsafe_allow_html=True)

    # ===== HEATMAP =====
    st.markdown("### 🔥 Bản đồ HeatMap giá trọ")

    points = load_real_data()
    if len(points) > 1000:
        points = points[:800]

    heat_data = []

    for lat, lon in points:
        d = np.sqrt(
            (lat - campus_coord[0])**2 +
            (lon - campus_coord[1])**2
        ) * 111

        features = np.array([[d, area, tien_nghi, gio_giac, so_nguoi, tien_ich]])
        price = model.predict(features)[0]

        heat_data.append([lat, lon, price])

    # ===== MAP =====
    m = folium.Map(
        location=[geo[0], geo[1]],  # lat, lon
        zoom_start=14,
        tiles="CartoDB positron"
    )

    HeatMap(
        heat_data,
        radius=20,
        blur=18,
        max_zoom=15,
        gradient={
            0.2: 'purple',
            0.4: 'blue',
            0.6: 'cyan',
            0.8: 'orange',
            1.0: 'red'
        }
    ).add_to(m)

    # user
    folium.Marker(
        [geo[0], geo[1]],
        popup="📍 Bạn ở đây",
        icon=folium.Icon(color="red")
    ).add_to(m)

    # campus
    folium.Marker(
        [campus_coord[0], campus_coord[1]],
        popup="🏫 Trường",
        icon=folium.Icon(color="blue")
    ).add_to(m)

    folium.Circle(
        location=[geo[0], geo[1]],
        radius=500,
        color='red',
        fill=True,
        fill_opacity=0.1
    ).add_to(m)

    MiniMap().add_to(m)

    st_folium(m, width=750, height=550)
