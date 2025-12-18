import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from scipy.spatial import cKDTree

# Configuración de la página
st.set_page_config(page_title="Mapa de Cobertura Salud", layout="wide")

# --- 1. FUNCIÓN PARA FORMATO ARGENTINO (1.234,56) ---
def formato_es(valor):
    if pd.isna(valor) or valor == 0:
        return "0,00"
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 2. PROCESAMIENTO DE DATOS ---
@st.cache_data
def cargar_y_procesar_datos():
    # Cargar archivos (Asegúrate que los nombres en GitHub sean idénticos a estos)
    df_afi = pd.read_csv('Afiliados interior geolocalizacion.csv')
    df_cons = pd.read_csv('Consultorios GeoLocalizacion (1).csv')

    # A. Eliminar duplicados como en Power Query
    df_afi = df_afi.drop_duplicates(subset=['AFI_ID', 'CALLE', 'NUMERO'])

    # B. Guardar el total de la base (para comparar con Power BI)
    total_unicos_base = df_afi['AFI_ID'].nunique()

    # C. Limpieza y Filtro Geográfico de Argentina
    LAT_MIN, LAT_MAX = -56.0, -21.0
    LON_MIN, LON_MAX = -74.0, -53.0

    def filtrar_geo(df):
        df['LATITUD'] = pd.to_numeric(df['LATITUD'], errors='coerce')
        df['LONGITUD'] = pd.to_numeric(df['LONGITUD'], errors='coerce')
        mask = (df['LATITUD'].between(LAT_MIN, LAT_MAX)) & (df['LONGITUD'].between(LON_MIN, LON_MAX))
        return df[mask].copy()

    df_mapa_afi = filtrar_geo(df_afi)
    df_mapa_cons = filtrar_geo(df_cons)

    # D. Cálculo de Distancia al consultorio más cercano
    # Creamos el árbol con los consultorios válidos
    tree = cKDTree(df_mapa_cons[['LATITUD', 'LONGITUD']].values)
    dist, _ = tree.query(df_mapa_afi[['LATITUD', 'LONGITUD']].values, k=1)
    df_mapa_afi['distancia_km'] = dist * 111.13 

    # E. Agrupación por Localidad para el Mapa
    resumen_afi = df_mapa_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'nunique'), # Distinct Count
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'mean'), 
        lon_ref=('LONGITUD', 'mean')
    ).reset_index()

    resumen_cons = df_mapa_cons.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_consultorios')
    
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='left').fillna(0)
    data_final['afi_por_cons'] = data_final['cant_afiliados'] / data_final['cant_consultorios'].replace(0, np.nan)
    
    return data_final, total_unicos_base

# --- 3. INTERFAZ DE USUARIO ---
st.title("📍 Mapa Interactivo de Afiliados y Consultorios")

try:
    # Obtener datos procesados
    data, total_base = cargar_y_procesar_datos()

    # --- SIDEBAR (PANEL LATERAL) ---
    st.sidebar.header("📊 Resumen de Datos")
    
    # Total igual a Power BI
    st.sidebar.metric("Total Afiliados Únicos", f"{total_base:,}".replace(",", "."))
    
    # Total que se puede mostrar en el mapa
    afi_en_mapa = int(data['cant_afiliados'].sum())
    st.sidebar.metric("Afiliados Geolocalizados", f"{afi_en_mapa:,}".replace(",", "."))
    
    # Alerta si hay mucha diferencia
    diferencia = total_base - afi_en_mapa
    if diferencia > 0:
        st.sidebar.warning(f"Hay {diferencia:,}".replace(",", ".") + " registros sin coordenadas válidas.")

    # Métrica de Distancia
    dist_prom_gral = data['dist_media'].mean()
    st.sidebar.metric("Distancia Promedio", f"{formato_es(dist_prom_gral)} km")

    # --- MAPA ---
    m = folium.Map(location=[-38.4161, -63.6167], zoom_start=4, tiles="cartodbpositron")

    for _, row in data.iterrows():
        # Formatear textos para el Tooltip
        afiliados_str = f"{int(row['cant_afiliados']):,}".replace(",", ".")
        cons_str = str(int(row['cant_consultorios']))
        dist_str = formato_es(row['dist_media'])
        ratio_str = formato_es(row['afi_por_cons'])

        tooltip_info = f"""
            <div style="font-family: Arial; width: 220px;">
                <h4 style="margin-bottom:5px; color:#1f77b4;">{row['LOCALIDAD']}</h4>
                <p style="font-size:12px; color:gray; margin-top:0;">{row['PROVINCIA']}</p>
                <hr style="margin:5px 0;">
                <b>Afiliados:</b> {afiliados_str}<br>
                <b>Consultorios:</b> {cons_str}<br>
                <b>Afiliados/Cons.:</b> {ratio_str}<br>
                <b>Dist. Media:</b> {dist_str} km
            </div>
        """
        
        # Color: Rojo si hay 0 consultorios, Azul si hay al menos 1
        color_marker = "#d62728" if row['cant_consultorios'] == 0 else "#1f77b4"
        
        folium.CircleMarker(
            location=[row['lat_ref'], row['lon_ref']],
            radius=min(25, 5 + (row['cant_afiliados'] / 100)),
            tooltip=folium.Tooltip(tooltip_info),
            color=color_marker,
            fill=True,
            fill_opacity=0.6
        ).add_to(m)

    st_folium(m, width="100%", height=600)

except Exception as e:
    st.error(f"Se produjo un error: {e}")
