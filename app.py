import streamlit as st

import pandas as pd

import numpy as np

import folium

from streamlit_folium import st_folium

from folium.plugins import HeatMap

from scipy.spatial import cKDTree

import io



# Configuración de la página

st.set_page_config(page_title="Tablero de Cobertura Geográfica", layout="wide")



# --- 1. FUNCIONES DE FORMATO ---

def formato_es(valor):

    if pd.isna(valor) or valor == 0: return "0,00"

    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def formato_porcentaje(parte, total):

    if total == 0: return "0,0 %"

    return f"{(parte / total) * 100:.1f}".replace(".", ",") + " %"



def formato_miles(valor):

    return f"{int(valor):,}".replace(",", ".")



# --- 2. PROCESAMIENTO DE DATOS ---

@st.cache_data

def cargar_y_procesar_datos():

    # Carga de archivos

    df_afi_raw = pd.read_csv('Afiliados interior geolocalizacion.csv')

    df_cons_raw = pd.read_csv('Consultorios GeoLocalizacion (1).csv')



    # A. Deduplicación y limpieza

    df_afi_clean = df_afi_raw.drop_duplicates(subset=['AFI_ID', 'CALLE', 'NUMERO'])

    

    LAT_MIN, LAT_MAX = -56.0, -21.0

    LON_MIN, LON_MAX = -74.0, -53.0



    def filtrar_geo(df):

        df['LATITUD'] = pd.to_numeric(df['LATITUD'], errors='coerce')

        df['LONGITUD'] = pd.to_numeric(df['LONGITUD'], errors='coerce')

        mask = (df['LATITUD'].between(LAT_MIN, LAT_MAX)) & (df['LONGITUD'].between(LON_MIN, LON_MAX))

        return df[mask].copy()



    df_mapa_afi = filtrar_geo(df_afi_clean)

    df_mapa_cons = filtrar_geo(df_cons_raw)



    # B. Cálculo de Distancias

    tree = cKDTree(df_mapa_cons[['LATITUD', 'LONGITUD']].values)

    dist, _ = tree.query(df_mapa_afi[['LATITUD', 'LONGITUD']].values, k=1)

    df_mapa_afi['distancia_km'] = dist * 111.13 



    # C. Agrupación por Localidad (Data para el mapa)

    resumen_afi = df_mapa_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(

        cant_afiliados=('AFI_ID', 'nunique'),

        dist_media=('distancia_km', 'mean'),

        lat_ref=('LATITUD', 'mean'), 

        lon_ref=('LONGITUD', 'mean')

    ).reset_index()



    resumen_cons = df_mapa_cons.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_consultorios')

    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='left').fillna(0)

    data_final['afi_por_cons'] = data_final['cant_afiliados'] / data_final['cant_consultorios'].replace(0, np.nan)

    

    return data_final, df_afi_clean, df_cons_raw, df_mapa_afi, df_mapa_cons



# --- 3. INTERFAZ Y FILTROS ---

st.title("📍 Tablero de Gestión de Cobertura Sanitaria")


# --- SECCIÓN DE AYUDA / MANUAL ---
with st.expander("❓ ¿Cómo usar este tablero y qué significan las métricas?"):
    st.markdown("""
    ### 📖 Guía de Usuario
    Este tablero permite analizar la relación geográfica entre nuestros **afiliados** y los **consultorios** disponibles.
    
    * **Filtros:** Utilice el panel izquierdo para segmentar por provincia o ajustar el rango de distancia. 
    * **Tipos de Vista:** 
        * **Marcadores:** Muestra puntos exactos. El tamaño del círculo depende de la cantidad de afiliados. 
        * **Heatmap:** Muestra la densidad poblacional. Las zonas rojas son las de mayor concentración.
    
    ### 📊 Glosario de Métricas
    * **Éxito Geo:** Porcentaje de registros que tenían coordenadas válidas dentro de Argentina y pudieron ser mapeados.
    * **Distancia Media:** Es el promedio de kilómetros que deben recorrer los afiliados de esa localidad para llegar al consultorio más cercano.
    * **Afiliados/Cons.:** Indica cuántos afiliados "le corresponden" a cada consultorio en esa localidad.
    * **Puntos Rojos en Mapa:** Localidades que tienen afiliados pero **0 consultorios** registrados.
    """)

try:

    data_mapa_raw, afi_base, cons_base, afi_geo_all, cons_geo_all = cargar_y_procesar_datos()



    # --- SIDEBAR: FILTROS ---

    st.sidebar.header("🔍 Filtros de Visualización")

    

    list_prov = ["Todas"] + sorted(afi_base['PROVINCIA'].unique().tolist())

    prov_sel = st.sidebar.selectbox("Seleccionar Provincia", list_prov)



    tipo_mapa = st.sidebar.radio("Tipo de Vista", ["Marcadores (Localidades)", "Heatmap (Distribución de Afiliados)"])



    max_dist_data = float(data_mapa_raw['dist_media'].max())

    dist_range = st.sidebar.slider("Rango de Distancia Promedio (Km)", 0.0, max_dist_data, (0.0, max_dist_data))



    # APLICAR FILTROS A LOS DATOS

    if prov_sel != "Todas":

        data_filtrada = data_mapa_raw[data_mapa_raw['PROVINCIA'] == prov_sel]

        afi_total_stats = len(afi_base[afi_base['PROVINCIA'] == prov_sel])

        afi_geo_stats = len(afi_geo_all[afi_geo_all['PROVINCIA'] == prov_sel])

        cons_total_stats = len(cons_base[cons_base['PROVINCIA'] == prov_sel])

        cons_geo_stats = len(cons_geo_all[cons_geo_all['PROVINCIA'] == prov_sel])

    else:

        data_filtrada = data_mapa_raw

        afi_total_stats = len(afi_base)

        afi_geo_stats = len(afi_geo_all)

        cons_total_stats = len(cons_base)

        cons_geo_stats = len(cons_geo_all)



    # Filtro de Distancia

    data_filtrada = data_filtrada[data_filtrada['dist_media'].between(dist_range[0], dist_range[1])]



    # --- SIDEBAR: MÉTRICAS RECALCULADAS ---

    st.sidebar.markdown("---")

    st.sidebar.subheader(f"📊 Estadísticas: {prov_sel}")

    

    # Métricas de Afiliados

    st.sidebar.write("**Afiliados**")

    st.sidebar.write(f"Total Base: {formato_miles(afi_total_stats)}")

    st.sidebar.write(f"En Mapa: {formato_miles(afi_geo_stats)}")

    st.sidebar.info(f"Éxito Geo: {formato_porcentaje(afi_geo_stats, afi_total_stats)}")

    

    st.sidebar.markdown("---")

    

    # Métricas de Consultorios

    st.sidebar.write("**Consultorios**")

    st.sidebar.write(f"Total Base: {formato_miles(cons_total_stats)}")

    st.sidebar.write(f"En Mapa: {formato_miles(cons_geo_stats)}")

    st.sidebar.success(f"Éxito Geo: {formato_porcentaje(cons_geo_stats, cons_total_stats)}")



    st.sidebar.markdown("---")

    

    # Métrica de Distancia Promedio (basada en el filtro aplicado)

    if not data_filtrada.empty:

        dist_prom_filtrada = data_filtrada['dist_media'].mean()

        st.sidebar.metric("Distancia Promedio", f"{formato_es(dist_prom_filtrada)} km")



# --- MAPA CON ZOOM DINÁMICO ---
    if not data_filtrada.empty:
        centro = [data_filtrada['lat_ref'].mean(), data_filtrada['lon_ref'].mean()]
        zoom = 4 if prov_sel == "Todas" else 7
    else:
        centro, zoom = [-38.4161, -63.6167], 4

    m = folium.Map(location=centro, zoom_start=zoom, tiles="cartodbpositron")

    if tipo_mapa == "Marcadores (Localidades)":
        for _, row in data_filtrada.iterrows():
            # Cálculo de la métrica específica para el tooltip
            afi_cons_ratio = row['cant_afiliados'] / row['cant_consultorios'] if row['cant_consultorios'] > 0 else np.nan
            
            # Construcción del Tooltip con HTML y CSS para recuperar el diseño anterior
            tooltip_txt = f"""
                <div style="font-family: Arial; width: 220px;">
                    <h4 style="margin-bottom:5px; color:#1f77b4;">{row['LOCALIDAD']}</h4>
                    <p style="font-size:12px; color:gray; margin-top:0;">{row['PROVINCIA']}</p>
                    <hr style="margin:5px 0;">
                    <b>Afiliados:</b> {formato_miles(row['cant_afiliados'])}<br>
                    <b>Consultorios:</b> {formato_miles(row['cant_consultorios'])}<br>
                    <b>Afiliados/Cons.:</b> {formato_es(afi_cons_ratio)}<br>
                    <b>Dist. Media:</b> {formato_es(row['dist_media'])} km
                </div>
            """
            
            color = "#d62728" if row['cant_consultorios'] == 0 else "#1f77b4"
            
            folium.CircleMarker(
                location=[row['lat_ref'], row['lon_ref']],
                radius=min(25, 5 + (row['cant_afiliados'] / 100)),
                tooltip=folium.Tooltip(tooltip_txt), # Usamos el HTML aquí
                color=color, 
                fill=True, 
                fill_opacity=0.6
            ).add_to(m)
    else:
        # Heatmap (Sigue igual)
        heat_data = [[row['lat_ref'], row['lon_ref'], row['cant_afiliados']] for _, row in data_filtrada.iterrows()]
        HeatMap(heat_data, radius=15, blur=10).add_to(m)

    st_folium(m, width="100%", height=550, key="mapa_dinamico")



    # --- TABLA DE DATOS ---

    st.markdown("---")

    st.subheader(f"📋 Detalle de Localidades ({prov_sel})")

    

    # Preparación de la tabla asegurando tipos de datos

    tabla_display = data_filtrada[['LOCALIDAD', 'PROVINCIA', 'cant_afiliados', 'dist_media', 'cant_consultorios']].copy()

    

    # Convertir consultorios a entero para evitar el .0

    tabla_display['cant_consultorios'] = tabla_display['cant_consultorios'].astype(int)

    

    tabla_display.columns = ['Localidad', 'Provincia', 'Afiliados', 'Dist. Media (Km)', 'Consultorios']

    

    # Formateo de la tabla: Distancia con 2 decimales y Consultorios como entero (sin formato de miles con coma)

    st.dataframe(

        tabla_display.style.format({

            'Dist. Media (Km)': '{:.2f}',

            'Afiliados': lambda x: f"{x:,}".replace(",", "."),

            'Consultorios': lambda x: f"{int(x):,}".replace(",", ".")

        }), 

        use_container_width=True

    )



    # Botón de Descarga

    csv = tabla_display.to_csv(index=False).encode('utf-8-sig')

    st.download_button(

        label="📥 Descargar tabla como CSV",

        data=csv,

        file_name=f'reporte_cobertura_{prov_sel.lower()}.csv',

        mime='text/csv',

    )



except Exception as e:

    st.error(f"Error en la aplicación: {e}")





