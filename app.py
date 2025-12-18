import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from scipy.spatial import cKDTree

# Configuración de la página
st.set_page_config(page_title="Tablero de Cobertura Geográfica", layout="wide")

# --- 1. FUNCIONES DE FORMATO ---
def formato_es(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formato_porcentaje(parte, total):
    if total == 0:
        return "0,0 %"
    porcentaje = (parte / total) * 100
    return f"{porcentaje:.1f}".replace(".", ",") + " %"

def formato_miles(valor):
    return f"{int(valor):,}".replace(",", ".")

# --- 2. PROCESAMIENTO DE DATOS ---
@st.cache_data
def cargar_y_procesar_datos():
    # Carga de archivos
    df_afi_raw = pd.read_csv('Afiliados interior geolocalizacion.csv')
    df_cons_raw = pd.read_csv('Consultorios GeoLocalizacion (1).csv')

    # A. Deduplicación de Afiliados (Igual a Power BI)
    df_afi_clean = df_afi_raw.drop_duplicates(subset=['AFI_ID', 'CALLE', 'NUMERO'])
    total_afi_bi = len(df_afi_clean)
    total_cons_bi = len(df_cons_raw) # Total de la base de consultorios

    # B. Filtro Geográfico (Solo coordenadas válidas en Argentina)
    LAT_MIN, LAT_MAX = -56.0, -21.0
    LON_MIN, LON_MAX = -74.0, -53.0

    def filtrar_geo(df):
        df['LATITUD'] = pd.to_numeric(df['LATITUD'], errors='coerce')
        df['LONGITUD'] = pd.to_numeric(df['LONGITUD'], errors='coerce')
        mask = (df['LATITUD'].between(LAT_MIN, LAT_MAX)) & (df['LONGITUD'].between(LON_MIN, LON_MAX))
        return df[mask].copy()

    df_mapa_afi = filtrar_geo(df_afi_clean)
    df_mapa_cons = filtrar_geo(df_cons_raw)

    # C. Cálculo de Distancias
    tree = cKDTree(df_mapa_cons[['LATITUD', 'LONGITUD']].values)
    dist, _ = tree.query(df_mapa_afi[['LATITUD', 'LONGITUD']].values, k=1)
    df_mapa_afi['distancia_km'] = dist * 111.13 

    # D. Agrupación por Localidad
    resumen_afi = df_mapa_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'nunique'),
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'mean'), 
        lon_ref=('LONGITUD', 'mean')
    ).reset_index()

    resumen_cons = df_mapa_cons.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_consultorios')
    
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='left').fillna(0)
    data_final['afi_por_cons'] = data_final['cant_afiliados'] / data_final['cant_consultorios'].replace(0, np.nan)
    
    # Retornamos los datos del mapa y las métricas de control
    metrics = {
        "afi_total": total_afi_bi,
        "afi_geo": len(df_mapa_afi),
        "cons_total": total_cons_bi,
        "cons_geo": len(df_mapa_cons)
    }
    
    return data_final, metrics

# --- 3. INTERFAZ ---
st.title("📍 Análisis de Cobertura y Geolocalización")

try:
    data, m = cargar_y_procesar_datos()

    # --- SIDEBAR: ESTADO DE LA BASE ---
    st.sidebar.header("📊 Salud de los Datos")
    
    # Sección Afiliados
    st.sidebar.subheader("Afiliados")
    st.sidebar.write(f"**Total (Deduplicados):** {formato_miles(m['afi_total'])}")
    st.sidebar.write(f"**En Mapa:** {formato_miles(m['afi_geo'])}")
    st.sidebar.info(f"**Éxito Geo:** {formato_porcentaje(m['afi_geo'], m['afi_total'])}")
    
    st.sidebar.markdown("---")
    
    # Sección Consultorios
    st.sidebar.subheader("Consultorios")
    st.sidebar.write(f"**Total Base:** {formato_miles(m['cons_total'])}")
    st.sidebar.write(f"**En Mapa:** {formato_miles(m['cons_geo'])}")
    st.sidebar.success(f"**Éxito Geo:** {formato_porcentaje(m['cons_geo'], m['cons_total'])}")

    # Métrica de Distancia
    st.sidebar.markdown("---")
    dist_prom = data['dist_media'].mean()
    st.sidebar.metric("Distancia Promedio Gral.", f"{formato_es(dist_prom)} km")

    # --- MAPA ---
    mapa_base = folium.Map(location=[-38.4161, -63.6167], zoom_start=4, tiles="cartodbpositron")

    for _, row in data.iterrows():
        tooltip_info = f"""
            <div style="font-family: Arial; width: 220px;">
                <h4 style="margin-bottom:5px; color:#1f77b4;">{row['LOCALIDAD']}</h4>
                <p style="font-size:12px; color:gray; margin-top:0;">{row['PROVINCIA']}</p>
                <hr style="margin:5px 0;">
                <b>Afiliados:</b> {formato_miles(row['cant_afiliados'])}<br>
                <b>Consultorios:</b> {int(row['cant_consultorios'])}<br>
                <b>Afiliados/Cons.:</b> {formato_es(row['afi_por_cons'])}<br>
                <b>Dist. Media:</b> {formato_es(row['dist_media'])} km
            </div>
        """
        
        color_node = "#d62728" if row['cant_consultorios'] == 0 else "#1f77b4"
        
        folium.CircleMarker(
            location=[row['lat_ref'], row['lon_ref']],
            radius=min(25, 5 + (row['cant_afiliados'] / 100)),
            tooltip=folium.Tooltip(tooltip_info),
            color=color_node,
            fill=True,
            fill_opacity=0.6
        ).add_to(mapa_base)

    st_folium(mapa_base, width="100%", height=600)

except Exception as e:
    st.error(f"Error en la aplicación: {e}")
