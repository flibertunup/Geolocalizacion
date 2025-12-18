import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from scipy.spatial import cKDTree

# Configuración de página
st.set_page_config(page_title="Mapa de Afiliados y Consultorios", layout="wide")

@st.cache_data
def cargar_y_procesar_datos():
    # Cargar los archivos (deben estar en la misma carpeta que app.py)
    df_afi = pd.read_csv('Afiliados interior geolocalizacion.csv')
    df_cons = pd.read_csv('Consultorios GeoLocalizacion (1).csv')

    # Limpieza de datos con coordenadas válidas
    df_afi = df_afi.dropna(subset=['LATITUD', 'LONGITUD'])
    df_cons = df_cons.dropna(subset=['LATITUD', 'LONGITUD'])

    # --- CÁLCULO DE DISTANCIAS ---
    # Creamos el árbol de búsqueda con consultorios
    tree = cKDTree(df_cons[['LATITUD', 'LONGITUD']].values)
    # Buscamos el consultorio más cercano para cada afiliado
    dist, _ = tree.query(df_afi[['LATITUD', 'LONGITUD']].values, k=1)
    df_afi['distancia_km'] = dist * 111.13  # Conversión aprox de grados a km

    # --- MÉTRICAS POR LOCALIDAD ---
    # Agrupamos afiliados por localidad
    resumen_afi = df_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'count'),
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'first'),
        lon_ref=('LONGITUD', 'first')
    ).reset_index()

    # Agrupamos consultorios por localidad
    resumen_cons = df_cons.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_consultorios')

    # Unimos todo
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='left').fillna(0)
    
    # Métrica solicitada: Afiliados por Consultorio
    # Evitamos división por cero reemplazando 0 consultorios por NaN
    data_final['afi_por_cons'] = data_final['cant_afiliados'] / data_final['cant_consultorios'].replace(0, np.nan)
    
    return data_final

# Ejecución de la app
st.title("📍 Mapa Interactivos de Cobertura - Argentina")

try:
    data = cargar_y_procesar_datos()

    # Sidebar con métricas generales
    st.sidebar.header("Métricas Generales")
    st.sidebar.metric("Total Afiliados", len(data['cant_afiliados']))
    st.sidebar.metric("Promedio Distancia", f"{data['dist_media'].mean():.2f} km")

    # Creación del Mapa
    m = folium.Map(location=[-38.4161, -63.6167], zoom_start=4, tiles="cartodbpositron")

    for _, row in data.iterrows():
        # Texto del Tooltip con HTML
        tooltip_info = f"""
            <div style="font-family: sans-serif;">
                <h4>{row['LOCALIDAD']}</h4>
                <b>Provincia:</b> {row['PROVINCIA']}<br>
                <b>Afiliados:</b> {int(row['cant_afiliados'])}<br>
                <b>Consultorios:</b> {int(row['cant_consultorios'])}<br>
                <b>Afiliados por Consultorio:</b> {row['afi_por_cons']:.2f}<br>
                <b>Distancia media al consultorio:</b> {row['dist_media']:.2f} km
            </div>
        """
        
        folium.CircleMarker(
            location=[row['lat_ref'], row['lon_ref']],
            radius=min(20, 5 + (row['cant_afiliados'] / 50)), # Tamaño dinámico
            tooltip=folium.Tooltip(tooltip_info),
            color="#318ce7",
            fill=True,
            fill_opacity=0.6
        ).add_to(m)

    # Mostrar mapa en Streamlit
    st_folium(m, width="100%", height=600)

except FileNotFoundError:
    st.error("No se encontraron los archivos CSV. Asegúrate de que estén en la misma carpeta que app.py")