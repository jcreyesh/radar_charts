import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Radar de productos", page_icon="📡", layout="wide")

REQUIRED = ["producto", "fecha", "atributo", "promedio"]


@st.cache_data(show_spinner=False)
def load_csv(file_bytes: bytes, dayfirst: bool) -> pd.DataFrame:
    # Detecta separador y tolera distintas codificaciones
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError:
            continue

    df.columns = df.columns.str.strip().str.lower()
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas: {', '.join(missing)}. "
            f"Columnas encontradas: {', '.join(df.columns)}"
        )

    df = df[REQUIRED].copy()
    df["producto"] = df["producto"].astype(str).str.strip()
    df["atributo"] = df["atributo"].astype(str).str.strip()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce", dayfirst=dayfirst)
    if df["promedio"].dtype == object:
        df["promedio"] = df["promedio"].astype(str).str.replace(",", ".", regex=False)
    df["promedio"] = pd.to_numeric(df["promedio"], errors="coerce")
    return df


st.title("📡 Gráfica de radar por producto")
st.caption("Carga el CSV descargado del agente (columnas: producto, fecha, atributo, promedio).")

uploaded = st.file_uploader("Archivo CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

with st.sidebar:
    st.header("Opciones")
    dayfirst = st.checkbox("Fechas en formato día/mes/año", value=False)

try:
    raw = load_csv(uploaded.getvalue(), dayfirst)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

# Limpieza básica
invalid = raw["fecha"].isna().sum() + raw["promedio"].isna().sum()
df = raw.dropna(subset=["fecha", "promedio"])
if invalid:
    st.warning(f"Se omitieron filas con fecha o promedio inválidos.")
if df.empty:
    st.error("No quedaron datos válidos para graficar.")
    st.stop()

all_products = sorted(df["producto"].unique())
all_attrs = sorted(df["atributo"].unique())
dmin, dmax = df["fecha"].min().date(), df["fecha"].max().date()

with st.sidebar:
    productos = st.multiselect("Productos", all_products, default=all_products[:3])
    atributos = st.multiselect("Atributos (ejes)", all_attrs, default=all_attrs)

    rango = st.date_input("Rango de fechas", value=(dmin, dmax), min_value=dmin, max_value=dmax)

    modo = st.radio(
        "Manejo de fechas",
        ["Promediar las fechas del rango", "Una serie por producto y fecha"],
    )
    relleno = st.checkbox("Rellenar polígonos", value=True)
    auto_range = st.checkbox("Escala automática", value=True)
    if not auto_range:
        rmin = st.number_input("Mínimo del eje", value=0.0)
        rmax = st.number_input("Máximo del eje", value=5.0)

if not productos:
    st.info("Selecciona al menos un producto.")
    st.stop()
if len(atributos) < 3:
    st.info("Selecciona al menos 3 atributos para formar un radar.")
    st.stop()
if not isinstance(rango, (tuple, list)) or len(rango) != 2:
    st.info("Selecciona fecha inicial y final.")
    st.stop()

ini, fin = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])
d = df[
    df["producto"].isin(productos)
    & df["atributo"].isin(atributos)
    & df["fecha"].between(ini, fin)
]
if d.empty:
    st.warning("No hay datos con los filtros seleccionados.")
    st.stop()

if modo.startswith("Promediar"):
    agg = d.groupby(["producto", "atributo"], as_index=False)["promedio"].mean()
    agg["serie"] = agg["producto"]
else:
    agg = d.groupby(["producto", "fecha", "atributo"], as_index=False)["promedio"].mean()
    agg["serie"] = agg["producto"] + " · " + agg["fecha"].dt.strftime("%Y-%m-%d")

wide = agg.pivot(index="serie", columns="atributo", values="promedio").reindex(columns=atributos)

if wide.isna().any().any():
    st.warning("Algunas series no tienen datos para todos los atributos; aparecerán con huecos.")

fig = go.Figure()
for serie, row in wide.iterrows():
    vals = row.tolist()
    fig.add_trace(
        go.Scatterpolar(
            r=vals + [vals[0]],  # cierra el polígono
            theta=atributos + [atributos[0]],
            name=serie,
            fill="toself" if relleno else "none",
            opacity=0.6 if relleno else 1,
            mode="lines+markers",
            hovertemplate="%{theta}: %{r:.2f}<extra>" + serie + "</extra>",
        )
    )

if auto_range:
    radial = dict(visible=True, range=[0, float(wide.max().max()) * 1.1])
else:
    radial = dict(visible=True, range=[rmin, rmax])

fig.update_layout(
    polar=dict(radialaxis=radial),
    legend=dict(orientation="h", yanchor="bottom", y=-0.2),
    height=650,
    margin=dict(t=40, b=40),
)

st.plotly_chart(fig, use_container_width=True)

with st.expander("Ver datos graficados"):
    st.dataframe(wide.round(3), use_container_width=True)
    st.download_button(
        "Descargar tabla (CSV)",
        wide.round(3).to_csv().encode("utf-8"),
        file_name="radar_datos.csv",
        mime="text/csv",
    )