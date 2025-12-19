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
                    <b>Consultorios:</b> {int(row['cant_consultorios'])}<br>
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
