import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from scipy.spatial import cKDTree

# Configuración de página
st.set_page_config(page_title="Mapa de Cobertura Argentina", layout="wide")

# --- FUNCIÓN PARA FORMATO ARGENTINO (1.234,56) ---
def formato_es(valor):
    if pd.isna(valor):
        return "0,00"
    # Formatea con punto en miles y coma en decimales
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data
def cargar_y_procesar_datos():
    # Cargar archivos
    df_afi = pd.read_csv('Afiliados interior geolocalizacion.csv')
    df_cons = pd.read_csv('Consultorios GeoLocalizacion (1).csv')

    # --- LIMPIEZA Y FILTRO GEOGRÁFICO (Bounding Box Argentina) ---
    LAT_MIN, LAT_MAX = -56.0, -21.0
    LON_MIN, LON_MAX = -74.0, -53.0

    def limpiar_coords(df):
        df['LATITUD'] = pd.to_numeric(df['LATITUD'], errors='coerce')
        df['LONGITUD'] = pd.to_numeric(df['LONGITUD'], errors='coerce')
        mask = (df['LATITUD'].between(LAT_MIN, LAT_MAX)) & (df['LONGITUD'].between(LON_MIN, LON_MAX))
        return df[mask].copy()

    df_afi = limpiar_coords(df_afi)
    df_cons = limpiar_coords(df_cons)

    # --- CÁLCULO DE DISTANCIAS ---
    tree = cKDTree(df_cons[['LATITUD', 'LONGITUD']].values)
    dist, _ = tree.query(df_afi[['LATITUD', 'LONGITUD']].values, k=1)
    df_afi['distancia_km'] = dist * 111.13 # Conversión grados a km

    # --- MÉTRICAS POR LOCALIDAD ---
    resumen_afi = df_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'count'),
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'first'),
        lon_ref=('LONGITUD', 'first')
    ).reset_index()

    resumen_cons = df_cons.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_consultorios')
    
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='left').fillna(0)
    data_final['afi_por_cons'] = data_final['cant_afiliados'] / data_final['cant_consultorios'].replace(0, np.nan)
    
    return data_final

# --- INTERFAZ DE LA APP ---
st.title("📍 Mapa de Gestión de Salud - Argentina")

try:
    data = cargar_y_processed_datos()

    # Sidebar con métricas formateadas
    st.sidebar.header("Resumen General")
    st.sidebar.metric("Total Afiliados", formato_es(data['cant_afiliados'].sum()).split(',')[0])
    st.sidebar.metric("Distancia Promedio (Km)", formato_es(data['dist_media'].mean()))

    # Creación del Mapa
    m = folium.Map(location=[-38.4161, -63.6167], zoom_start=4, tiles="cartodbpositron")

    for _, row in data.iterrows():
        # Formatear valores para el Tooltip
        afiliados_str = f"{int(row['cant_afiliados']):,}".replace(",", ".")
        cons_str = str(int(row['cant_consultorios']))
        dist_str = formato_es(row['dist_media'])
        ratio_str = formato_es(row['afi_por_cons'])

        tooltip_info = f"""
            <div style="font-family: Arial; width: 200px;">
                <h4 style="margin-bottom:5px;">{row['LOCALIDAD']}</h4>
                <hr style="margin:5px 0;">
                <b>Afiliados:</b> {afiliados_str}<br>
                <b>Consultorios:</b> {cons_str}<br>
                <b>Afiliados/Cons.:</b> {ratio_str}<br>
                <b>Dist. Media:</b> {dist_str} km
            </div>
        """
        
        folium.CircleMarker(
            location=[row['lat_ref'], row['lon_ref']],
            radius=min(25, 5 + (row['cant_afiliados'] / 100)),
            tooltip=folium.Tooltip(tooltip_info),
            color="#003366",
            fill=True,
            fill_opacity=0.7
        ).add_to(m)

    st_folium(m, width="100%", height=600)

except Exception as e:
    st.error(f"Error al cargar la aplicación: {e}")
