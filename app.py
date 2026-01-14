import streamlit as st

import pandas as pd

import numpy as np

import folium

from streamlit_folium import st_folium

from folium.plugins import HeatMap

from scipy.spatial import cKDTree

import io

import pyodbc


# Función con caché para no conectar a la DB en cada click:
@st.cache_resource
def conectar_db():
    return pyodbc.connect('DSN=PostgresUP')
    

# --- SEGURIDAD ---
CLAVE_DESARROLLADOR = "admin123" # Cambia esto por tu clave


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

def cargar_y_procesar_datos():
    # --- CONEXIÓN Y CARGA SQL ---
    query_afiliados = """
    SELECT  
        af."codigo"        AS "Codigo",
        af."apellidos"     AS "Apellidos",
        af."nombres"       AS "Nombres",
        af."afi_id"        AS "AFI_ID",
        COALESCE(
             (SELECT dafi."domiafi_id" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."domiafi_id" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "DOMIAFI_ID",
        COALESCE(
             (SELECT dafi."calle" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."calle" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "CALLE",
        COALESCE(
             (SELECT dafi."numero" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."numero" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "NUMERO",
        COALESCE(
             (SELECT dafi."piso" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."piso" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "PISO",
        COALESCE(
             (SELECT dafi."dpto" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."dpto" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "DEPARTAMENTO",
        COALESCE (
             (SELECT loc."codigo_postal" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT loc."codigo_postal" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "CODIGOPOST",
        COALESCE (
             (SELECT loc."localidad" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT loc."localidad" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "LOCALIDAD",
        COALESCE (
             (SELECT loc."pcia_codigo" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT loc."pcia_codigo" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "CODIGO_PROVINCIA",
        COALESCE (
             (SELECT p."nombre" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc, "sa_provincias" p
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' 
              AND p."codigo" = loc."pcia_codigo" LIMIT 1),
             (SELECT p."nombre" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc, "sa_provincias" p
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' 
              AND p."codigo" = loc."pcia_codigo" LIMIT 1)
        ) AS "PROVINCIA",   
        COALESCE (
             (SELECT pa."nombre" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc, "sa_provincias" pr, "sa_paises" pa
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST'
              AND pr."codigo" = loc."pcia_codigo" AND pr."pais_codigo" = pa."codigo" LIMIT 1),
             (SELECT pa."nombre" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd, "sa_localidades" loc, "sa_provincias" pr, "sa_paises" pa
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND loc."loc_id" = dafi."loc_loc_id" AND datd."td_codigo" = 'POST' 
              AND pr."codigo" = loc."pcia_codigo" AND pr."pais_codigo" = pa."codigo" LIMIT 1)
        ) AS "PAIS",                       
        COALESCE(
             (SELECT dafi."latitud" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."latitud" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "LATITUD",
        COALESCE(
             (SELECT dafi."longitud" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1),
             (SELECT dafi."longitud" FROM "sa_domicilios_afiliado" dafi, "sa_domiafi_td" datd
              WHERE dafi."afi_afi_id" = af."afi_id" AND dafi."domiafi_id" = datd."domiafi_domiafi_id" AND datd."td_codigo" = 'POST' LIMIT 1)
        ) AS "LONGITUD"     
    FROM "sa_afiliados" af
    WHERE af."estado" = 'A'
    ORDER BY af."apellidos", af."nombres";  
    """
    
    try:
        conn = conectar_db()
        df_afi_raw = pd.read_sql(query_afiliados, conn)
        # conn.close() # Opcional si usas cache_resource
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # Carga de consultorios
    df_cons_raw = pd.read_csv('Consultorios GeoLocalizacion (1).csv')

    # FILTRO POR PAÍS
    df_cons_raw = df_cons_raw[df_cons_raw['PAIS'] == 'ARGENTINA']

    
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

    # C. Agrupación
    resumen_afi = df_mapa_afi.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'nunique'),
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'mean'), 
        lon_ref=('LONGITUD', 'mean')
    ).reset_index()

    # Agrupamos consultorios y obtenemos sus coordenadas promedio también
    resumen_cons = df_mapa_cons.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_consultorios=('LOCALIDAD', 'size'),
        lat_cons=('LATITUD', 'mean'),
        lon_cons=('LONGITUD', 'mean')
    ).reset_index()

    # D. USAMOS MERGE OUTER PARA MOSTRAR TAMBIÉN LOCALIDADES CON CONSULTORIOS SIN AFILIADOS.
    # Esto asegura que si hay consultorios en una ciudad sin afiliados, la ciudad NO desaparezca.
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='outer').fillna(0)
    
    # Consolidamos coordenadas: Si no hay lat_ref (porque no hay afiliados), usamos lat_cons
    data_final['lat_ref'] = np.where(data_final['lat_ref'] == 0, data_final['lat_cons'], data_final['lat_ref'])
    data_final['lon_ref'] = np.where(data_final['lon_ref'] == 0, data_final['lon_cons'], data_final['lon_ref'])

    # Si no hay afiliados, la distancia media no existe (NaN) para que luego se vea como "-"
    data_final.loc[data_final['cant_afiliados'] == 0, 'dist_media'] = np.nan
    
    # Cálculo del ratio
    data_final['cons_por_afi'] = data_final['cant_consultorios'] / data_final['cant_afiliados'].replace(0, np.nan)
    
    # Limpiamos columnas auxiliares
    data_final = data_final.drop(columns=['lat_cons', 'lon_cons'])
    
    return data_final, df_afi_clean, df_cons_raw, df_mapa_afi, df_mapa_cons


# --- 3. INTERFAZ Y FILTROS ---

st.title("📍 Tablero de Gestión de Cobertura Sanitaria", anchor=False)


# --- SECCIÓN DE AYUDA / MANUAL ---
with st.expander("❓ ¿Cómo usar este tablero y qué significan las métricas?"):
    st.subheader("📖 Guía de Usuario", anchor=False)

    st.markdown("""
    Este tablero permite analizar la relación geográfica entre nuestros **afiliados** y los **consultorios** disponibles.
    
    * **Filtros:** Utilice el panel izquierdo para segmentar por provincia o ajustar el rango de distancia. 
    * **Tipos de Vista:** 
        * **Marcadores:** Muestra puntos exactos. El tamaño del círculo depende de la cantidad de afiliados. Los puntos rojos indican localidades que tienen afiliados pero **0 consultorios** localizados y los puntos grises
        representan localidades que tienen consultorios pero ningún afiliado encontrado.
        * **Heatmap:** Muestra la densidad poblacional. Las zonas rojas son las de mayor concentración.
    """)
    
    st.subheader("📊 Glosario de Métricas", anchor=False)

    st.markdown("""
    * **Éxito Geo:** Porcentaje de registros que tenían coordenadas válidas dentro de Argentina y pudieron ser mapeados.
    * **Distancia Media:** Es el promedio de kilómetros que deben recorrer los afiliados para llegar al consultorio más cercano.
    * **Cons./Afiliados:** Indica cuántos consultorios hay disponibles por cada afiliado en esa localidad.
    """)

try:

    data_mapa_raw, afi_base, cons_base, afi_geo_all, cons_geo_all = cargar_y_procesar_datos()



    # --- SIDEBAR: FILTROS ---

    st.sidebar.header("🔍 Filtros de Visualización")

    # --- SISTEMA DE ACCESO ---
    st.sidebar.markdown("---")
    # Inicializamos el estado si no existe
    if 'es_dev' not in st.session_state:
        st.session_state.es_dev = False

    if not st.session_state.es_dev:
        with st.sidebar.expander("🔑 Acceso Staff"):
            password = st.text_input("Contraseña", type="password", autocomplete="one-time-code")
            if st.button("Iniciar sesión"):
                if password == CLAVE_DESARROLLADOR:
                    st.session_state.es_dev = True
                    st.rerun()
                else:
                    st.error("Clave incorrecta")
    else:
        st.sidebar.success("🔓 Modo Desarrollador Activo")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.es_dev = False
            st.rerun()
    
    
    # Filtro de Provincia
    list_prov = ["Todas"] + sorted(afi_base['PROVINCIA'].unique().tolist())

    prov_sel = st.sidebar.selectbox("Seleccionar Provincia", list_prov)

    # Filtro de Localidad (en cascada)
    loc_sel = "Todas"
    if prov_sel != "Todas":
        # Solo mostramos localidades que pertenecen a la provincia elegida
        list_loc = ["Todas"] + sorted(data_mapa_raw[data_mapa_raw['PROVINCIA'] == prov_sel]['LOCALIDAD'].unique().tolist())
        loc_sel = st.sidebar.selectbox("Seleccionar Localidad", list_loc)
    else:
        st.sidebar.info("Seleccione una provincia para filtrar por localidad.")
        

    tipo_mapa = st.sidebar.radio("Tipo de Vista", ["Marcadores (Localidades)", "Heatmap (Distribución de Afiliados)"])



    max_dist_data = float(data_mapa_raw['dist_media'].dropna().max())

    dist_range = st.sidebar.slider("Rango de Distancia Promedio (Km)", 0.0, max_dist_data, (0.0, max_dist_data))

    
    # --- APLICAR FILTROS EN CADENA ---
    data_filtrada = data_mapa_raw.copy()

    # 1. Filtro Provincia
    if prov_sel != "Todas":
        data_filtrada = data_filtrada[data_filtrada['PROVINCIA'] == prov_sel]
        afi_total_stats = len(afi_base[afi_base['PROVINCIA'] == prov_sel])
        afi_geo_stats = len(afi_geo_all[afi_geo_all['PROVINCIA'] == prov_sel])
        cons_total_stats = len(cons_base[cons_base['PROVINCIA'] == prov_sel])
        cons_geo_stats = len(cons_geo_all[cons_geo_all['PROVINCIA'] == prov_sel])
    else:
        afi_total_stats, afi_geo_stats = len(afi_base), len(afi_geo_all)
        cons_total_stats, cons_geo_stats = len(cons_base), len(cons_geo_all)

    # 2. Filtro Localidad
    if loc_sel != "Todas":
        data_filtrada = data_filtrada[data_filtrada['LOCALIDAD'] == loc_sel]



    # Filtro de Distancia

    # Creamos una máscara que incluya los valores en rango O los valores nulos (0 afiliados)
    mask_distancia = (data_filtrada['dist_media'].between(dist_range[0], dist_range[1])) | (data_filtrada['dist_media'].isna())
    data_filtrada = data_filtrada[mask_distancia]



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

            # Definimos qué mostrar en la distancia y en el ratio si no hay afiliados
            distancia_label = "-" if row['cant_afiliados'] == 0 else f"{formato_es(row['dist_media'])} km"

            # Construcción del Tooltip con HTML y CSS para recuperar el diseño anterior
            tooltip_txt = f"""
                <div style="font-family: Arial; width: 220px;">
                    <h4 style="margin-bottom:5px; color:#1f77b4;">{row['LOCALIDAD']}</h4>
                    <p style="font-size:12px; color:gray; margin-top:0;">{row['PROVINCIA']}</p>
                    <hr style="margin:5px 0;">
                    <b>Afiliados:</b> {formato_miles(row['cant_afiliados'])}<br>
                    <b>Consultorios:</b> {formato_miles(row['cant_consultorios'])}<br>
                    <b>Cons./Afiliados:</b> {formato_es(row['cons_por_afi']) if pd.notna(row['cons_por_afi']) else "-"}<br>
                    <b>Dist. Media:</b> {distancia_label}
                </div>
            """
            
            if row['cant_afiliados'] == 0:
                color = "#95a5a6" # GRIS: Solo consultorios (capacidad ociosa)
            elif row['cant_consultorios'] == 0:
                color = "#d62728" # ROJO: Afiliados sin consultorio local
            else:
                color = "#1f77b4" # AZUL: Localidad con ambos servicios
                
            
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

    st.subheader(f"📋 Detalle de Localidades ({prov_sel})", anchor=False)


    # Preparación de la tabla

    tabla_display = data_filtrada[['LOCALIDAD', 'PROVINCIA', 'cant_afiliados', 'dist_media', 'cant_consultorios', 'cons_por_afi']].copy()

    # 2. Renombramos columnas
    tabla_display.columns = ['Localidad', 'Provincia', 'Afiliados', 'Dist. Media (Km)', 'Consultorios', 'Cons./Afiliados']

    # 3. Formateamos las columnas numéricas fijas
    # Afiliados y Consultorios a entero con punto de miles
    # Distancia Media con coma decimal

    df_styled = tabla_display.copy()

    # Aplicamos el formato manualmente a las columnas conflictivas para que Streamlit no use "None"
    df_styled['Afiliados'] = df_styled['Afiliados'].apply(lambda x: f"{int(x):,}".replace(",", "."))
    df_styled['Consultorios'] = df_styled['Consultorios'].apply(lambda x: f"{int(x):,}".replace(",", "."))
    df_styled['Dist. Media (Km)'] = df_styled['Dist. Media (Km)'].apply(
    lambda x: "-" if pd.isna(x) else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
)

    # LA CLAVE: Forzamos el guion en la columna Afiliados/Cons. antes de pasar al dataframe
   # df_styled['Afiliados/Cons.'] = df_styled['Afiliados/Cons.'].apply(
   # lambda x: "-" if (pd.isna(x) or np.isinf(x)) else f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
   # )

    df_styled['Cons./Afiliados'] = df_styled['Cons./Afiliados'].apply(lambda x: "-" if (pd.isna(x) or np.isinf(x)) else formato_es(x))
    
    
    # 4. Mostramos la tabla (ya procesada como texto para evitar el "None")
    st.dataframe(df_styled, use_container_width=True)

    # --- DESCARGA ---
    # Usamos la misma lógica para que el CSV sea consistente
    csv = df_styled.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
    label="📥 Descargar tabla como CSV",
    data=csv,
    file_name=f'reporte_cobertura_{prov_sel.lower()}.csv',
    mime='text/csv',
    )

    # --- PANEL SOLO PARA DESARROLLADORES ---
    if st.session_state.es_dev:
        st.markdown("---")
        st.subheader("🛠️ Descargas de Auditoría (Registros no localizados)")
        st.info("Estos archivos contienen los registros originales que no pudieron ser ubicados en el mapa por errores de coordenadas o país.")
        
        col1, col2 = st.columns(2)

        # 1. Afiliados no encontrados
        # Comparamos la base total vs los que sí entraron al mapa
        ids_en_mapa = afi_geo_all['AFI_ID'].unique()
        # Usamos df_afi_raw (retornado por tu función) para mantener el formato original
        afi_no_encontrados = afi_base[~afi_base['AFI_ID'].isin(ids_en_mapa)]

        with col1:
            st.write(f"**Afiliados no localizados:** {formato_miles(len(afi_no_encontrados))}")
            btn_afi = st.download_button(
                label="📥 Descargar Afiliados No Localizados",
                data=afi_no_encontrados.to_csv(index=False).encode('utf-8-sig'),
                file_name="afiliados_no_localizados.csv",
                mime="text/csv",
                key="btn_dev_afi"
            )

        # 2. Consultorios no encontrados
        # Comparamos por índice para ser precisos con los originales
        cons_en_mapa_idx = cons_geo_all.index
        cons_no_encontrados = cons_base[~cons_base.index.isin(cons_en_mapa_idx)]

        with col2:
            st.write(f"**Consultorios no localizados:** {formato_miles(len(cons_no_encontrados))}")
            btn_cons = st.download_button(
                label="📥 Descargar Consultorios No Localizados",
                data=cons_no_encontrados.to_csv(index=False).encode('utf-8-sig'),
                file_name="consultorios_no_localizados.csv",
                mime="text/csv",
                key="btn_dev_cons"
            )

except Exception as e:

      st.error(f"Error en la aplicación: {e}")





