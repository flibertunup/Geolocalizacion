import streamlit as st

import pandas as pd

import numpy as np

import folium

from streamlit_folium import st_folium

from folium.plugins import HeatMap

from scipy.spatial import cKDTree

import plotly.express as px

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

@st.cache_data
def cargar_y_procesar_datos():
    # --- Función interna para rescatar nombres que Excel convirtió en fecha ---
    def rescatar_nombre_localidad(valor):
        if pd.isna(valor): return "SIN DATO"
        # Si Pandas lo leyó como fecha (Timestamp o datetime)
        if isinstance(valor, (pd.Timestamp, np.datetime64)) or hasattr(valor, 'month'):
            try:
                meses = ["", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", 
                         "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]
                # Retornamos formato "25 DE MAYO"
                return f"{valor.day} DE {meses[valor.month]}"
            except:
                return str(valor).upper()
        return str(valor).upper().strip()

    # 1. CARGA Y NORMALIZACIÓN DE ARCHIVOS DE AFILIADOS
    archivos_excel = [
        'afiliados interior geolocalizacion parte 1.xlsx'
        # 'afiliados interior geolocalizacion parte 2.xlsx',
        # 'afiliados interior geolocalizacion parte 3.xlsx'
    ]
    
    lista_df_afi = []
    for archivo in archivos_excel:
        try:
            temp_df = pd.read_excel(archivo)
            temp_df.columns = temp_df.columns.str.upper()
            
            # Aplicamos el rescate de nombres
            if 'LOCALIDAD' in temp_df.columns:
                temp_df['LOCALIDAD'] = temp_df['LOCALIDAD'].apply(rescatar_nombre_localidad)
            if 'PROVINCIA' in temp_df.columns:
                temp_df['PROVINCIA'] = temp_df['PROVINCIA'].astype(str).str.upper().fillna("SIN DATO")
                
            lista_df_afi.append(temp_df)
        except Exception as e:
            st.error(f"Error al leer o procesar {archivo}: {e}")
    
    if lista_df_afi:
        df_afi_raw = pd.concat(lista_df_afi, ignore_index=True)
    else:
        return None
        
    # 2. CARGA DE CONSULTORIOS
    try:
        df_cons_raw = pd.read_excel('consultorios geolocalizacion 1.xlsx')
        df_cons_raw.columns = df_cons_raw.columns.str.upper()
        
        # Aplicamos el rescate de nombres también aquí
        df_cons_raw['LOCALIDAD'] = df_cons_raw['LOCALIDAD'].apply(rescatar_nombre_localidad)
        df_cons_raw['PROVINCIA'] = df_cons_raw['PROVINCIA'].astype(str).str.upper().fillna("SIN DATO")
        
        # FILTRO POR PAÍS
        if 'PAIS' in df_cons_raw.columns:
            df_cons_raw = df_cons_raw[df_cons_raw['PAIS'].astype(str).str.upper() == 'ARGENTINA']
    except Exception as e:
        st.error(f"Error en consultorios: {e}")
        return None

    cons_base = df_cons_raw.copy() # Base completa original
    
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
    df_mapa_cons = filtrar_geo(cons_base)

    # SEPARACIÓN LÓGICA (Dentro de cargar_y_procesar_datos)
    # Filtramos solo lo que NO es farmacia para cálculos médicos
    cons_geo_only = df_mapa_cons[df_mapa_cons['DESC_TIPO_EFECTOR'] != 'FARMACIA'].copy()
    
    # B. Cálculo de Distancias
    # Usamos 'cons_geo_only' para el árbol de distancias
    tree = cKDTree(cons_geo_only[['LATITUD', 'LONGITUD']].values)
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
    resumen_cons = cons_geo_only.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_consultorios=('LOCALIDAD', 'size'),
        lat_cons=('LATITUD', 'mean'),
        lon_cons=('LONGITUD', 'mean')
    ).reset_index()


    # Agrupamos farmacias por separado
    resumen_far = df_mapa_cons[df_mapa_cons['DESC_TIPO_EFECTOR'] == 'FARMACIA'].groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_farmacias')
    
    # D. USAMOS MERGE OUTER PARA MOSTRAR TAMBIÉN LOCALIDADES CON CONSULTORIOS SIN AFILIADOS.
    # Esto asegura que si hay consultorios en una ciudad sin afiliados, la ciudad NO desaparezca.
    # 1. Unimos Afiliados con Consultorios
    data_final = pd.merge(resumen_afi, resumen_cons, on=['LOCALIDAD', 'PROVINCIA'], how='outer')

    # 2. Unimos el resultado con Farmacias
    data_final = pd.merge(data_final, resumen_far, on=['LOCALIDAD', 'PROVINCIA'], how='outer')

    # 3. RELLENAMOS LOS HUECOS (Crucial)
    data_final = data_final.fillna(0)
    
    # Consolidamos coordenadas: Si no hay lat_ref (porque no hay afiliados), usamos lat_cons
    data_final['lat_ref'] = np.where(data_final['lat_ref'] == 0, data_final['lat_cons'], data_final['lat_ref'])
    data_final['lon_ref'] = np.where(data_final['lon_ref'] == 0, data_final['lon_cons'], data_final['lon_ref'])

    # Si no hay afiliados, la distancia media no existe (NaN) para que luego se vea como "-"
    data_final.loc[data_final['cant_afiliados'] == 0, 'dist_media'] = np.nan
    
    # Cálculo del ratio
    data_final['cons_por_afi'] = data_final['cant_consultorios'] / data_final['cant_afiliados'].replace(0, np.nan)
    
    # Limpiamos columnas auxiliares
    data_final = data_final.drop(columns=['lat_cons', 'lon_cons'])
    
    return data_final, df_afi_clean, cons_base, df_mapa_afi, df_mapa_cons


# --- 3. INTERFAZ Y FILTROS ---

def reiniciar_filtros():
    st.session_state['provincia'] = "Todas"
    st.session_state['especialidad'] = "Todas"
    st.session_state['localidad'] = "Todas"
    if 'distancia' in st.session_state:
        # Esto resetea el slider si le pones key='distancia'
        del st.session_state['distancia']


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


    # Inyectamos el CSS específico para el contenedor 'boton-reset'
    st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"] > div:has(div#boton-reset) button {
            padding: 0px !important;
            height: 32px !important;
            width: 32px !important;
            min-width: 32px !important;
            border-radius: 5px;
            line-height: 32px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Creamos dos columnas en el sidebar: 
    # La primera (col_titulo) para el texto, la segunda (col_btn) muy estrecha para el botón.
    col_titulo, col_btn = st.sidebar.columns([0.8, 0.2], vertical_alignment="center")

    with col_titulo:
        st.header("🔍 Filtros")

    with col_btn:
        # Agregamos un margen superior pequeño para alinear el botón con el texto del header 
        st.markdown('<div id="boton-reset">', unsafe_allow_html=True)
        st.button("🔄", on_click=reiniciar_filtros, help="Reiniciar todos los filtros")
        st.markdown('</div>', unsafe_allow_html=True)

    
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

    prov_sel = st.sidebar.selectbox("Seleccionar Provincia", list_prov, key='provincia')

    # Filtro de Localidad (en cascada)
    loc_sel = "Todas"
    if prov_sel != "Todas":
        # Solo mostramos localidades que pertenecen a la provincia elegida
        list_loc = ["Todas"] + sorted(data_mapa_raw[data_mapa_raw['PROVINCIA'] == prov_sel]['LOCALIDAD'].unique().tolist())
        loc_sel = st.sidebar.selectbox("Seleccionar Localidad", list_loc, key='localidad')
    else:
        st.sidebar.info("Seleccione una provincia para filtrar por localidad.")


    # Filtro de Especialidad
    list_esp = ["Todas"] + sorted(cons_base['ESPECIALIDAD'].unique().tolist())
    esp_sel = st.sidebar.selectbox("Seleccionar Especialidad", list_esp, key='especialidad')
    

    tipo_mapa = st.sidebar.radio("Tipo de Vista", ["Marcadores (Localidades)", "Heatmap (Distribución de Afiliados)"])



    max_dist_data = float(data_mapa_raw['dist_media'].dropna().max())

    dist_range = st.sidebar.slider("Rango de Distancia Promedio (Km)", 0.0, max_dist_data, (0.0, max_dist_data), key='distancia')

    
    # --- APLICAR FILTROS EN CADENA ---
    # 1. Creamos copias de trabajo para no romper las bases originales
    afi_filtrados = afi_geo_all.copy()       # Afiliados con mapa
    cons_filtrados_all = cons_geo_all.copy() # Prestadores + Farmacias con mapa
    afi_base_f = afi_base.copy()             # Total Afiliados (para Éxito Geo)
    cons_base_f = cons_base.copy()           # Total Consultorios (para Éxito Geo)

    # Separamos antes de filtrar especialidad. Esto nos permite que las farmacias no desaparezcan si filtras una especialidad médica
    cons_médicos = cons_filtrados_all[cons_filtrados_all['DESC_TIPO_EFECTOR'] != 'FARMACIA']
    farmacias_f = cons_filtrados_all[cons_filtrados_all['DESC_TIPO_EFECTOR'] == 'FARMACIA']

    # 2. FILTRO ESPECIALIDAD: Solo afecta a consultorios (Primero, porque afecta el cálculo de distancias)
    if esp_sel != "Todas":
        cons_médicos = cons_médicos[cons_médicos['ESPECIALIDAD'] == esp_sel]
        # Filtramos también la base original de médicos para que el Éxito Geo sea real
        cons_base_f = cons_base_f[
            (cons_base_f['ESPECIALIDAD'] == esp_sel) | 
            (cons_base_f['DESC_TIPO_EFECTOR'] == 'FARMACIA')
        ]
        # Recalcular distancia al especialista más cercano (ignora farmacias)
        if not cons_médicos.empty and not afi_filtrados.empty:
            tree = cKDTree(cons_médicos[['LATITUD', 'LONGITUD']].values)
            dist, _ = tree.query(afi_filtrados[['LATITUD', 'LONGITUD']].values, k=1)
            afi_filtrados['distancia_km'] = dist * 111.13

    # 3. FILTRO PROVINCIA
    if prov_sel != "Todas":
        afi_filtrados = afi_filtrados[afi_filtrados['PROVINCIA'] == prov_sel]
        cons_médicos = cons_médicos[cons_médicos['PROVINCIA'] == prov_sel]
        farmacias_f = farmacias_f[farmacias_f['PROVINCIA'] == prov_sel]
        # Filtrar bases originales (para que se actualice el Sidebar)
        afi_base_f = afi_base_f[afi_base_f['PROVINCIA'] == prov_sel]
        cons_base_f = cons_base_f[cons_base_f['PROVINCIA'] == prov_sel]

    # 4. FILTRO LOCALIDAD
    if loc_sel != "Todas":
        # Filtrar mapa
        afi_filtrados = afi_filtrados[afi_filtrados['LOCALIDAD'] == loc_sel]
        cons_médicos = cons_médicos[cons_médicos['LOCALIDAD'] == loc_sel]
        farmacias_f = farmacias_f[farmacias_f['LOCALIDAD'] == loc_sel]
        # Filtrar bases originales
        afi_base_f = afi_base_f[afi_base_f['LOCALIDAD'] == loc_sel]
        cons_base_f = cons_base_f[cons_base_f['LOCALIDAD'] == loc_sel]

    # 5. CONSTRUCCIÓN DE LA TABLA "data_filtrada" (Resumen por Localidad/Provincia)
    # Agrupamos los datos YA FILTRADOS por Provincia, Localidad y Especialidad
    res_afi = afi_filtrados.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_afiliados=('AFI_ID', 'nunique'),
        dist_media=('distancia_km', 'mean'),
        lat_ref=('LATITUD', 'mean'),
        lon_ref=('LONGITUD', 'mean')
    ).reset_index()

    res_cons = cons_médicos.groupby(['LOCALIDAD', 'PROVINCIA']).agg(
        cant_consultorios=('LOCALIDAD', 'size'),
        lat_cons=('LATITUD', 'mean'),
        lon_cons=('LONGITUD', 'mean')
    ).reset_index()

    res_far = farmacias_f.groupby(['LOCALIDAD', 'PROVINCIA']).size().reset_index(name='cant_farmacias')

    # Unimos para tener la vista final
    data_filtrada = pd.merge(res_afi, res_cons, on=['LOCALIDAD', 'PROVINCIA'], how='outer')
    data_filtrada = pd.merge(data_filtrada, res_far, on=['LOCALIDAD', 'PROVINCIA'], how='outer').fillna(0)

    # Consolidación de coordenadas y métricas finales
    data_filtrada['lat_ref'] = np.where(data_filtrada['lat_ref'] == 0, data_filtrada['lat_cons'], data_filtrada['lat_ref'])
    data_filtrada['lon_ref'] = np.where(data_filtrada['lon_ref'] == 0, data_filtrada['lon_cons'], data_filtrada['lon_ref'])
    data_filtrada.loc[data_filtrada['cant_afiliados'] == 0, 'dist_media'] = np.nan
    data_filtrada['cons_por_afi'] = data_filtrada['cant_consultorios'] / data_filtrada['cant_afiliados'].replace(0, np.nan)

    # 6. FILTRO DE DISTANCIA (Sobre el resumen final)
    mask_distancia = (data_filtrada['dist_media'].between(dist_range[0], dist_range[1])) | (data_filtrada['dist_media'].isna())
    data_filtrada = data_filtrada[mask_distancia]


    # --- SIDEBAR: MÉTRICAS RECALCULADAS ---

    st.sidebar.markdown("---")

    # Título dinámico según el nivel de filtro
    titulo_stats = prov_sel if loc_sel == "Todas" else f"{loc_sel}, {prov_sel}"
    st.sidebar.subheader(f"📊 Estadísticas: {titulo_stats}")

    

    # Métricas de Afiliados
    st.sidebar.write("**Afiliados**")
    st.sidebar.write(f"Total Base Filtrada: {formato_miles(len(afi_base_f))}")
    st.sidebar.write(f"En Mapa: {formato_miles(len(afi_filtrados))}")
    st.sidebar.info(f"Éxito Geo: {formato_porcentaje(len(afi_filtrados), len(afi_base_f))}")

    

    st.sidebar.markdown("---")

    

    # Métricas de Consultorios
    st.sidebar.write(f"**Consultorios ({esp_sel if esp_sel != 'Todas' else 'Totales'})**")
    # Usamos cons_base_f (que ya tiene los filtros de provincia/localidad/especialidad aplicados)
    total_base_medicos = len(cons_base_f[cons_base_f['DESC_TIPO_EFECTOR'] != 'FARMACIA'])
    st.sidebar.write(f"Total Base Filtrada: {formato_miles(total_base_medicos)}")
    st.sidebar.write(f"En Mapa: {formato_miles(len(cons_médicos))}")
    st.sidebar.success(f"Éxito Geo: {formato_porcentaje(len(cons_médicos), total_base_medicos)}")

    

    # Métrica de Distancia Promedio (basada en el filtro aplicado)

    if not data_filtrada.empty:

        dist_prom_filtrada = data_filtrada['dist_media'].mean()

        st.sidebar.metric("Distancia Promedio", f"{formato_es(dist_prom_filtrada)} km")

    
    st.sidebar.markdown("---")

    # Métricas de Farmacias

    st.sidebar.write(f"**Farmacias**")
    # Filtramos la base original para contar solo farmacias en la zona elegida
    total_base_farmacias = len(cons_base_f[cons_base_f['DESC_TIPO_EFECTOR'] == 'FARMACIA'])
    st.sidebar.write(f"Total Base Filtrada: {formato_miles(total_base_farmacias)}")
    st.sidebar.write(f"En Mapa: {formato_miles(len(farmacias_f))}")
    st.sidebar.success(f"Éxito Geo: {formato_porcentaje(len(farmacias_f), total_base_farmacias)}")


    
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
                    <b>Farmacias:</b> {formato_miles(row['cant_farmacias'])}<br>
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

    # --- SECCIÓN DE VISTAS (MAPA + ANÁLISIS) ---

    # Creamos las pestañas
    tab_mapa, tab_carencias = st.tabs(["🗺️ Mapa de Cobertura", "🚩 Análisis de Carencias"])

    with tab_mapa:
        # Aquí movemos tu código del mapa que ya tenías
        st_folium(m, width="100%", height=550, key="mapa_dinamico")
        st.caption(f"Visualizando datos para: {prov_sel} - {loc_sel}")

    with tab_carencias:
        st.subheader(f"🚩 Especialidades con Mayor Distancia en {prov_sel}")
    
        with st.spinner("Calculando distancias por especialidad..."):
            # 1. Obtenemos especialidades (excluyendo farmacias y vacíos)
            base_medica = cons_base_f[cons_base_f['DESC_TIPO_EFECTOR'] != 'FARMACIA']
            todas_esp = [e for e in base_medica['ESPECIALIDAD'].unique() if str(e) != 'nan' and e != 'SIN DATO']
        
            lista_carencias = []

            # 2. Solo calculamos si hay afiliados y médicos en la zona
            if not afi_filtrados.empty and todas_esp:
                for esp in todas_esp:
                    # Médicos de esta especialidad con mapa
                    cons_esp = cons_geo_all[cons_geo_all['ESPECIALIDAD'] == esp]
                
                    # Opcional: Filtrar cons_esp por provincia si quieres que la carencia sea local
                    if prov_sel != "Todas":
                        cons_esp = cons_esp[cons_esp['PROVINCIA'] == prov_sel]

                    if not cons_esp.empty:
                        tree_esp = cKDTree(cons_esp[['LATITUD', 'LONGITUD']].values)
                        dist_esp, _ = tree_esp.query(afi_filtrados[['LATITUD', 'LONGITUD']].values, k=1)
                        dist_km_esp = dist_esp.mean() * 111.13
                        lista_carencias.append({"Especialidad": esp, "Distancia Promedio (Km)": dist_km_esp})

            # 3. Mostrar Gráfico
            if lista_carencias:
                df_carencias = pd.DataFrame(lista_carencias).sort_values("Distancia Promedio (Km)", ascending=False).head(10)
            
                # Crear gráfico horizontal con Plotly
                fig = px.bar(
                    df_carencias, 
                    x="Distancia Promedio (Km)", 
                    y="Especialidad",
                    orientation='h',
                    color="Distancia Media (Km)",
                    color_continuous_scale='Reds',
                    text_auto='.1f'
                )
            
                fig.update_layout(
                    yaxis={'categoryorder':'total ascending'},
                    height=500,
                    margin=dict(l=20, r=20, t=20, b=20),
                    coloraxis_showscale=False
                )
            
                st.plotly_chart(fig, use_container_width=True)
                st.info("💡 Este gráfico muestra cuánto deben viajar, en promedio, los afiliados de la zona seleccionada para atenderse por especialidad.")
            else:
                st.warning("No hay suficientes datos geolocalizados para generar el ranking de carencias en esta zona.")



    # --- TABLA DE DATOS ---

    st.markdown("---")

    st.subheader(f"📋 Detalle de Localidades ({prov_sel})", anchor=False)


    # Preparación de la tabla

    tabla_display = data_filtrada[['LOCALIDAD', 'PROVINCIA', 'cant_afiliados', 'cant_farmacias', 'cant_consultorios', 'dist_media', 'cons_por_afi']].copy()

    # 2. Renombramos columnas
    tabla_display.columns = ['Localidad', 'Provincia', 'Afiliados', 'Farmacias', 'Consultorios', 'Dist. Media (Km)', 'Cons./Afiliados']

    # 3. Formateamos las columnas numéricas fijas
    # Afiliados, Farmacias y Consultorios a entero con punto de miles
    # Distancia Media con coma decimal

    df_styled = tabla_display.copy()

    # Aplicamos el formato manualmente a las columnas conflictivas para que Streamlit no use "None"
    df_styled['Afiliados'] = df_styled['Afiliados'].apply(lambda x: f"{int(x):,}".replace(",", "."))
    df_styled['Farmacias'] = df_styled['Farmacias'].apply(lambda x: f"{int(x):,}".replace(",", "."))
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






















