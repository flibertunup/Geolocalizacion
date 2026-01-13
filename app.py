import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
from scipy.spatial import cKDTree
import pyodbc

# =========================
# CONFIGURACIÓN GENERAL
# =========================

CLAVE_DESARROLLADOR = "admin123"

st.set_page_config(page_title="Tablero de Cobertura Geográfica", layout="wide")

LAT_MIN, LAT_MAX = -56.0, -21.0
LON_MIN, LON_MAX = -74.0, -53.0

# =========================
# FORMATO
# =========================

def formato_es(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formato_porcentaje(parte, total):
    if total == 0:
        return "0,0 %"
    return f"{(parte / total) * 100:.1f}".replace(".", ",") + " %"

def formato_miles(valor):
    return f"{int(valor):,}".replace(",", ".")

# =========================
# CLASIFICACIÓN GEO
# =========================

def clasificar_geo(df):
    df = df.copy()

    df["LAT_NUM"] = pd.to_numeric(df["LATITUD"], errors="coerce")
    df["LON_NUM"] = pd.to_numeric(df["LONGITUD"], errors="coerce")

    condiciones = [
        df["LATITUD"].isna() | df["LONGITUD"].isna(),
        df["LAT_NUM"].isna() | df["LON_NUM"].isna(),
        ~(df["LAT_NUM"].between(LAT_MIN, LAT_MAX) & df["LON_NUM"].between(LON_MIN, LON_MAX))
    ]

    motivos = [
        "Coordenadas Nulas en Origen",
        "Formato de Coordenada Inválido",
        "Ubicación Fuera de Argentina"
    ]

    df["motivo_no_localizado"] = np.select(condiciones, motivos, default="OK")

    df_geo = df[df["motivo_no_localizado"] == "OK"].copy()
    df_no_geo = df[df["motivo_no_localizado"] != "OK"].copy()

    df_geo["LATITUD"] = df_geo["LAT_NUM"]
    df_geo["LONGITUD"] = df_geo["LON_NUM"]

    return df_geo.drop(columns=["LAT_NUM", "LON_NUM"]), df_no_geo.drop(columns=["LAT_NUM", "LON_NUM"])

# =========================
# CARGA Y PROCESO
# =========================

@st.cache_data
def cargar_y_procesar_datos():
    df_afi_raw = pd.read_csv("Afiliados interior geolocalizacion.csv")
    df_cons_raw = pd.read_csv("Consultorios GeoLocalizacion (1).csv")

    df_cons_raw = df_cons_raw[df_cons_raw["PAIS"] == "ARGENTINA"]

    df_afi_clean = df_afi_raw.drop_duplicates(subset=["AFI_ID", "CALLE", "NUMERO"])

    df_afi_geo, afi_no_geo = clasificar_geo(df_afi_clean)
    df_cons_geo, cons_no_geo = clasificar_geo(df_cons_raw)

    # Distancias
    tree = cKDTree(df_cons_geo[["LATITUD", "LONGITUD"]].values)
    dist, _ = tree.query(df_afi_geo[["LATITUD", "LONGITUD"]].values, k=1)
    df_afi_geo["distancia_km"] = dist * 111.13

    resumen_afi = df_afi_geo.groupby(["LOCALIDAD", "PROVINCIA"]).agg(
        cant_afiliados=("AFI_ID", "nunique"),
        dist_media=("distancia_km", "mean"),
        lat_ref=("LATITUD", "mean"),
        lon_ref=("LONGITUD", "mean")
    ).reset_index()

    resumen_cons = df_cons_geo.groupby(["LOCALIDAD", "PROVINCIA"]).agg(
        cant_consultorios=("LOCALIDAD", "size"),
        lat_cons=("LATITUD", "mean"),
        lon_cons=("LONGITUD", "mean")
    ).reset_index()

    data_final = pd.merge(
        resumen_afi,
        resumen_cons,
        on=["LOCALIDAD", "PROVINCIA"],
        how="outer"
    ).fillna(0)

    data_final["lat_ref"] = np.where(data_final["lat_ref"] == 0, data_final["lat_cons"], data_final["lat_ref"])
    data_final["lon_ref"] = np.where(data_final["lon_ref"] == 0, data_final["lon_cons"], data_final["lon_ref"])
    data_final.loc[data_final["cant_afiliados"] == 0, "dist_media"] = np.nan
    data_final["cons_por_afi"] = data_final["cant_consultorios"] / data_final["cant_afiliados"].replace(0, np.nan)

    return (
        data_final,
        df_afi_clean,
        df_cons_raw,
        df_afi_geo,
        df_cons_geo,
        afi_no_geo,
        cons_no_geo
    )

# =========================
# APP
# =========================

st.title("📍 Tablero de Gestión de Cobertura Sanitaria", anchor=False)

try:
    (
        data_mapa_raw,
        afi_base,
        cons_base,
        afi_geo_all,
        cons_geo_all,
        afi_no_geo,
        cons_no_geo
    ) = cargar_y_procesar_datos()

    # =========================
    # PANEL DEV
    # =========================

    if "es_dev" not in st.session_state:
        st.session_state.es_dev = False

    with st.sidebar.expander("🔑 Acceso Staff"):
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar"):
            if password == CLAVE_DESARROLLADOR:
                st.session_state.es_dev = True
                st.rerun()
            else:
                st.error("Clave incorrecta")

    if st.session_state.es_dev:
        st.markdown("---")
        st.subheader("🛠️ Descargas de Auditoría")

        col1, col2 = st.columns(2)

        with col1:
            st.write(f"**Afiliados no localizados:** {formato_miles(len(afi_no_geo))}")
            st.download_button(
                "📥 Descargar Afiliados No Localizados",
                afi_no_geo.to_csv(index=False).encode("utf-8-sig"),
                "afiliados_no_localizados.csv",
                "text/csv"
            )

        with col2:
            st.write(f"**Consultorios no localizados:** {formato_miles(len(cons_no_geo))}")
            st.download_button(
                "📥 Descargar Consultorios No Localizados",
                cons_no_geo.to_csv(index=False).encode("utf-8-sig"),
                "consultorios_no_localizados.csv",
                "text/csv"
            )

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
