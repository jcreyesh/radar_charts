import io

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Radar de productos", page_icon="📡", layout="wide")

# Columnas del CSV
COL_PROD = "ID_PRODUCTO"
COL_COD = "CODIGO_FIZZ_SENSORIAL"
COL_CAT = "CATEGORIA_PARAMETRO"
COL_PARAM = "PARAMETRO"
COL_VAL = "VALOR_PROMEDIO"
REQUIRED = [COL_PROD, COL_COD, COL_CAT, COL_PARAM, COL_VAL]


@st.cache_data(show_spinner=False)
def load_csv(file_bytes: bytes) -> pd.DataFrame:
    # Detecta separador y tolera distintas codificaciones
    df = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        raise ValueError("No se pudo decodificar el archivo.")

    # Normaliza nombres de columnas a MAYÚSCULAS sin espacios extra
    df.columns = df.columns.str.strip().str.upper()
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas: {', '.join(missing)}. "
            f"Columnas encontradas: {', '.join(df.columns)}"
        )

    df = df[REQUIRED].copy()
    for c in (COL_PROD, COL_COD, COL_CAT, COL_PARAM):
        df[c] = df[c].astype(str).str.strip()
    if df[COL_VAL].dtype == object:
        df[COL_VAL] = df[COL_VAL].astype(str).str.replace(",", ".", regex=False)
    df[COL_VAL] = pd.to_numeric(df[COL_VAL], errors="coerce")
    return df


st.title("📡 Gráfica de radar por producto")
st.caption(f"Carga el CSV (columnas: {', '.join(REQUIRED)}).")

uploaded = st.file_uploader("Archivo CSV", type=["csv"])
if uploaded is None:
    st.info("Sube un archivo CSV para comenzar.")
    st.stop()

try:
    raw = load_csv(uploaded.getvalue())
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

# Limpieza básica
invalid = raw[COL_VAL].isna().sum()
df = raw.dropna(subset=[COL_VAL])
if invalid:
    st.warning(f"Se omitieron {invalid} filas con {COL_VAL} inválido.")
if df.empty:
    st.error("No quedaron datos válidos para graficar.")
    st.stop()

all_products = sorted(df[COL_PROD].unique())
all_cats = sorted(df[COL_CAT].unique())

with st.sidebar:
    st.header("Opciones")
    productos = st.multiselect("Productos", all_products, default=all_products[:3])
    categorias = st.multiselect("Categorías de parámetro", all_cats, default=all_cats)

    params_disp = sorted(df[df[COL_CAT].isin(categorias)][COL_PARAM].unique())
    parametros = st.multiselect("Parámetros (ejes)", params_disp, default=params_disp)

    codigos_disp = sorted(df[df[COL_PROD].isin(productos)][COL_COD].unique())
    codigos = st.multiselect("Códigos Fizz sensorial", codigos_disp, default=codigos_disp)

    modo = st.radio(
        "Manejo de códigos",
        ["Promediar los códigos seleccionados", "Una serie por producto y código"],
    )
    relleno = st.checkbox("Rellenar polígonos", value=True)
    auto_range = st.checkbox("Escala automática", value=True)
    if not auto_range:
        rmin = st.number_input("Mínimo del eje", value=0.0)
        rmax = st.number_input("Máximo del eje", value=5.0)

if not productos:
    st.info("Selecciona al menos un producto.")
    st.stop()
if len(parametros) < 3:
    st.info("Selecciona al menos 3 parámetros para formar un radar.")
    st.stop()
if not codigos:
    st.info("Selecciona al menos un código Fizz sensorial.")
    st.stop()

d = df[
    df[COL_PROD].isin(productos)
    & df[COL_CAT].isin(categorias)
    & df[COL_PARAM].isin(parametros)
    & df[COL_COD].isin(codigos)
]
if d.empty:
    st.warning("No hay datos con los filtros seleccionados.")
    st.stop()

if modo.startswith("Promediar"):
    agg = d.groupby([COL_PROD, COL_PARAM], as_index=False)[COL_VAL].mean()
    agg["serie"] = agg[COL_PROD]
else:
    agg = d.groupby([COL_PROD, COL_COD, COL_PARAM], as_index=False)[COL_VAL].mean()
    agg["serie"] = agg[COL_PROD] + " · " + agg[COL_COD]

wide = agg.pivot(index="serie", columns=COL_PARAM, values=COL_VAL).reindex(columns=parametros)

if wide.isna().any().any():
    st.warning("Algunas series no tienen datos para todos los parámetros; aparecerán con huecos.")

fig = px.line_polar(
    agg,
    r=COL_VAL,
    theta=COL_PARAM,
    color="serie",
    line_close=True,  # cierra el polígono
    markers=True,
    category_orders={COL_PARAM: parametros},
)
fig.update_traces(
    fill="toself" if relleno else "none",
    opacity=0.6 if relleno else 1,
    hovertemplate="%{theta}: %{r:.2f}<extra>%{fullData.name}</extra>",
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
