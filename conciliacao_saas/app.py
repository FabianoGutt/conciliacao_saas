"""
SaaS de Conciliação - Conta 91001001 TRANSITÓRIA DE FORNECEDORES
Streamlit V2 - Dashboard + Nova Conciliação + Histórico
"""

import io
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Conciliação Transitória de Fornecedores",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "historico_conciliacoes.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ESTABELECIMENTOS = ["101", "103", "104", "106"]


# ============================================================
# TEMA VISUAL
# ============================================================

def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {
          --primary:#22c55e;
          --primary-dark:#16a34a;
          --secondary:#e0f2fe;
          --secondary-dark:#bae6fd;
          --accent:#d1fae5;
          --background:#f0f8ff;
          --background-dark:#e8f4fc;
          --card:#ffffff;
          --foreground:#374151;
          --foreground-dark:#1f2937;
          --muted-fg:#6b7280;
          --border:#e5e7eb;
          --sidebar-bg:#e0f2fe;
          --radius:.5rem;
        }

        html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;}
        .stApp{background:linear-gradient(180deg,var(--background) 0%,var(--background-dark) 100%)!important;color:var(--foreground)!important;}
        .stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6{color:var(--foreground-dark)!important;font-weight:700!important;}
        .stApp div[data-testid="stCaptionContainer"],.stApp div[data-testid="stCaptionContainer"] p{color:var(--muted-fg)!important;}

        section[data-testid="stSidebar"]{background:var(--sidebar-bg)!important;border-right:1px solid var(--border)!important;}

        /* ========================================================
   NAVEGAÇÃO DO SIDEBAR - RADIO
   ======================================================== */

        section[data-testid="stSidebar"] div[role="radiogroup"] {
            gap: 0.35rem !important;
        }
        
        section[data-testid="stSidebar"] div[role="radiogroup"] > label {
            background: #E0F2FE !important;
            border: 1px solid #BAE6FD !important;
            border-radius: 0.5rem !important;
            padding: 0.55rem 0.75rem !important;
            margin-bottom: 0.15rem !important;
            transition: all 0.15s ease !important;
        }
        
        /* Texto */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label p,
        section[data-testid="stSidebar"] div[role="radiogroup"] > label span {
            color: #374151 !important;
            font-weight: 500 !important;
        }
        
        /* Hover */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
            background: #BAE6FD !important;
            border-color: #93C5FD !important;
        }
        
        /* Item selecionado */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
            background: #D1FAE5 !important;
            border-color: #86EFAC !important;
        }
        
        /* Texto do item selecionado */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p,
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) span {
            color: #166534 !important;
            font-weight: 600 !important;
        }

        /* ========================================================
   BOTÃO / ÍCONE DO SIDEBAR
   ======================================================== */

        /* Botão que contém o controle */
        button[data-testid="stSidebarCollapseButton"] {
            color: #374151 !important;
            background-color: transparent !important;
        }
        
        /* Ícone Material Symbols Rounded */
        button[data-testid="stSidebarCollapseButton"] * {
            color: #374151 !important;
        }
        
        /* Classe específica do ícone identificada pelo F12 */
        button[data-testid="stSidebarCollapseButton"] .st-emotion-cache-12bp31y {
            color: #374151 !important;
        }
        
        /* Caso o ícone esteja em elementos internos */
        button[data-testid="stSidebarCollapseButton"] * {
            color: #374151 !important;
        }
        
        /* Hover */
        button[data-testid="stSidebarCollapseButton"]:hover {
            background-color: rgba(55, 65, 81, 0.08) !important;
        }
        
        button[data-testid="stSidebarCollapseButton"]:hover span,
        button[data-testid="stSidebarCollapseButton"]:hover .st-emotion-cache-12bp31y {
            color: #1f2937 !important;
        }
        section[data-testid="stSidebar"] h1,section[data-testid="stSidebar"] h2,section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,section[data-testid="stSidebar"] label,section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"]{color:var(--foreground-dark)!important;}

        .conta-contabil{background:#111827!important;border:1px solid #1f2937!important;border-radius:.5rem!important;padding:.8rem .9rem!important;margin-top:.5rem!important;}
        .conta-numero{color:#94a3b8!important;font-family:'IBM Plex Mono',monospace!important;font-size:.78rem!important;font-weight:500!important;margin-bottom:.25rem!important;}
        .conta-descricao{color:#fff!important;font-family:'IBM Plex Mono',monospace!important;font-size:.78rem!important;font-weight:600!important;}

        .stSelectbox label,.stTextInput label,.stNumberInput label,.stFileUploader label{color:var(--foreground-dark)!important;font-weight:500!important;}
        .stSelectbox [data-baseweb="select"],.stTextInput input,.stNumberInput input{background:#fff!important;color:var(--foreground-dark)!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;}
        .stSelectbox [data-baseweb="select"] *,.stTextInput input,.stNumberInput input{color:var(--foreground-dark)!important;}
        .stTextInput input::placeholder,.stNumberInput input::placeholder{color:var(--muted-fg)!important;opacity:1!important;}

        div[data-baseweb="popover"],div[data-baseweb="menu"],div[role="listbox"]{background:#fff!important;color:var(--foreground-dark)!important;border-color:var(--border)!important;}
        div[data-baseweb="popover"] [role="option"],div[role="listbox"] [role="option"]{background:#fff!important;color:var(--foreground-dark)!important;}
        div[data-baseweb="popover"] [role="option"]:hover,div[role="listbox"] [role="option"]:hover{background:var(--secondary)!important;color:var(--foreground-dark)!important;}

        section[data-testid="stFileUploader"]{background:transparent!important;border:none!important;padding:0!important;}
        section[data-testid="stFileUploader"] div[data-testid="stFileUploaderDropzone"]{background:#fff!important;border:1px dashed #86efac!important;border-radius:var(--radius)!important;min-height:90px!important;}
        section[data-testid="stFileUploader"] div[data-testid="stFileUploaderDropzone"] *{color:var(--foreground)!important;}
        section[data-testid="stFileUploader"] button{background:var(--secondary)!important;color:#0369a1!important;border:1px solid var(--secondary-dark)!important;}
        section[data-testid="stFileUploader"] button *{color:#0369a1!important;}

        .stButton>button{border-radius:var(--radius)!important;font-weight:600!important;padding:.6rem 1.2rem!important;transition:all .15s ease!important;}
        .stButton>button[kind="primary"]{background:var(--primary)!important;color:#fff!important;border:none!important;box-shadow:0 4px 8px rgba(34,197,94,.25)!important;}
        .stButton>button[kind="primary"] *{color:#fff!important;}
        .stButton>button[kind="primary"]:hover{background:var(--primary-dark)!important;}
        .stButton>button:not([kind="primary"]){background:var(--secondary)!important;color:#0369a1!important;border:1px solid var(--secondary-dark)!important;}
        .stButton>button:not([kind="primary"]) *{color:#0369a1!important;}

        div[data-testid="stMetric"]{background:#fff!important;border:1px solid var(--border)!important;border-radius:var(--radius)!important;padding:1rem 1.1rem!important;box-shadow:0 4px 8px rgba(0,0,0,.06)!important;}
        div[data-testid="stMetric"] label{color:var(--muted-fg)!important;font-weight:500!important;}
        div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:var(--foreground-dark)!important;font-weight:700!important;}
        div[data-testid="stMetric"] [data-testid="stMetricDelta"]{color:var(--muted-fg)!important;}

        div[data-testid="stAlert"]{border-radius:var(--radius)!important;}
        div[data-testid="stDataFrame"]{border:1px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden;box-shadow:0 4px 8px rgba(0,0,0,.05)!important;background:#fff!important;}
        .stDownloadButton>button{background:var(--secondary)!important;color:#0369a1!important;border:1px solid var(--secondary-dark)!important;border-radius:var(--radius)!important;font-weight:600!important;}
        .stDownloadButton>button *{color:#0369a1!important;}

        .dashboard-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.2rem;box-shadow:0 4px 8px rgba(0,0,0,.05);margin-bottom:1rem;}
        .dashboard-label{color:var(--muted-fg);font-size:.85rem;font-weight:500;}
        .dashboard-value{color:var(--foreground-dark);font-size:1.55rem;font-weight:700;margin-top:.2rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# BANCO SQLITE
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conciliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estabelecimento TEXT NOT NULL,
            periodo TEXT,
            data_execucao TEXT NOT NULL,
            total_financeiro REAL,
            total_recebimento REAL,
            diferenca REAL,
            qtd_docs_financeiro INTEGER,
            qtd_docs_recebimento INTEGER,
            qtd_divergencias INTEGER,
            qtd_so_financeiro INTEGER,
            qtd_so_recebimento INTEGER,
            qtd_valor_diferente INTEGER,
            status TEXT,
            arquivo_financeiro TEXT,
            arquivo_recebimento TEXT,
            observacao TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS divergencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conciliacao_id INTEGER,
            documento TEXT,
            serie TEXT,
            chave TEXT,
            data_financeiro TEXT,
            data_recebimento TEXT,
            valor_financeiro REAL,
            valor_recebimento REAL,
            diferenca REAL,
            tipo TEXT,
            FOREIGN KEY (conciliacao_id) REFERENCES conciliacoes(id)
        )
    """)
    conn.commit()
    conn.close()


def salvar_conciliacao(meta, divergencias_df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conciliacoes (
            estabelecimento, periodo, data_execucao,
            total_financeiro, total_recebimento, diferenca,
            qtd_docs_financeiro, qtd_docs_recebimento, qtd_divergencias,
            qtd_so_financeiro, qtd_so_recebimento, qtd_valor_diferente,
            status, arquivo_financeiro, arquivo_recebimento, observacao
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        meta["estabelecimento"], meta["periodo"], meta["data_execucao"],
        meta["total_financeiro"], meta["total_recebimento"], meta["diferenca"],
        meta["qtd_docs_financeiro"], meta["qtd_docs_recebimento"], meta["qtd_divergencias"],
        meta["qtd_so_financeiro"], meta["qtd_so_recebimento"], meta["qtd_valor_diferente"],
        meta["status"], meta["arquivo_financeiro"], meta["arquivo_recebimento"], meta.get("observacao", ""),
    ))
    conc_id = cursor.lastrowid
    if not divergencias_df.empty:
        for _, row in divergencias_df.iterrows():
            cursor.execute("""
                INSERT INTO divergencias (
                    conciliacao_id, documento, serie, chave,
                    data_financeiro, data_recebimento,
                    valor_financeiro, valor_recebimento, diferenca, tipo
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                conc_id,
                str(row.get("Documento", "")),
                str(row.get("Série", "")),
                str(row.get("Chave", "")),
                str(row.get("Data Financeiro", "") or ""),
                str(row.get("Data Recebimento", "") or ""),
                float(row.get("Valor Financeiro", 0) or 0),
                float(row.get("Valor Recebimento", 0) or 0),
                float(row.get("Diferença", 0) or 0),
                str(row.get("Tipo", "")),
            ))
    conn.commit()
    conn.close()
    return conc_id


def listar_historico(estabelecimento=None):
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM conciliacoes"
    params = []
    if estabelecimento and estabelecimento != "Todos":
        query += " WHERE estabelecimento = ?"
        params.append(estabelecimento)
    query += " ORDER BY data_execucao DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def carregar_divergencias(conciliacao_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM divergencias WHERE conciliacao_id = ? ORDER BY ABS(diferenca) DESC",
        conn,
        params=(conciliacao_id,),
    )
    conn.close()
    return df


# ============================================================
# NORMALIZAÇÃO / LEITURA
# ============================================================

def normalizar_serie(s):
    if pd.isna(s) or s is None:
        return ""
    s = "".join(str(s).strip().upper().split())
    if not s:
        return ""
    if s.replace(".", "").isdigit():
        try:
            num = float(s)
            if num == int(num):
                s_int = str(int(num))
                if s_int != "0":
                    s_int = s_int.rstrip("0") or "0"
                return s_int
            return str(num)
        except Exception:
            return s
    return s


def normalizar_documento(d):
    if pd.isna(d) or d is None:
        return ""
    return str(d).strip().lstrip("0") or "0"


def _encontrar_linha_cabecalho(df_raw, palavras_chave):
    for i in range(min(30, len(df_raw))):
        row_text = " | ".join(str(v).lower().strip() for v in df_raw.iloc[i].tolist())
        hits = sum(1 for p in palavras_chave if p in row_text)
        if hits >= 2:
            return i
    return 0


def _mapear_colunas(df, tipo):
    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if tipo == "financeiro":
            if any(x in col_lower for x in ["título", "titulo", "title"]):
                col_map["documento"] = col
            elif "valor movto" in col_lower or ("valor" in col_lower and "movto" in col_lower):
                col_map["valor"] = col
            elif "valor" in col_lower and "valor" not in col_map:
                col_map["valor"] = col
            elif any(x in col_lower for x in ["dat transac", "data transac", "dat_transac"]):
                col_map["data"] = col
            elif col_lower.startswith("data") or "data" in col_lower:
                if "data" not in col_map:
                    col_map["data"] = col
            elif any(x in col_lower for x in ["série", "serie", "series"]):
                col_map["serie"] = col
        else:
            if "documento" in col_lower:
                col_map["documento"] = col
            elif any(x in col_lower for x in ["crédito", "credito"]):
                col_map["valor"] = col
            elif "valor" in col_lower and "valor" not in col_map:
                col_map["valor"] = col
            elif any(x in col_lower for x in ["data trans", "data_trans"]):
                col_map["data"] = col
            elif col_lower.startswith("data") or "data" in col_lower:
                if "data" not in col_map:
                    col_map["data"] = col
            elif any(x in col_lower for x in ["série", "serie", "series"]):
                col_map["serie"] = col
    return col_map


def _ler_excel_robusto(file_or_path, sheet_name=0):
    df = pd.read_excel(file_or_path, sheet_name=sheet_name, header=0)
    cols_str = " ".join(str(c).lower() for c in df.columns)
    precisa_reler = (
        all(str(c).startswith("Unnamed") for c in df.columns)
        or (
            "título" not in cols_str and "titulo" not in cols_str and
            "documento" not in cols_str and "valor" not in cols_str and
            "crédito" not in cols_str and "credito" not in cols_str
        )
    )
    if precisa_reler:
        df_raw = pd.read_excel(file_or_path, sheet_name=sheet_name, header=None)
        palavras = ["título", "titulo", "documento", "valor", "crédito", "credito", "data", "série", "serie"]
        header_row = _encontrar_linha_cabecalho(df_raw, palavras)
        df = pd.read_excel(file_or_path, sheet_name=sheet_name, header=header_row)
    return df.dropna(axis=1, how="all")


def preparar_financeiro(df):
    col_map = _mapear_colunas(df, "financeiro")
    required = ["documento", "valor", "data"]
    missing = [r for r in required if r not in col_map]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas no Financeiro: {missing}. "
            f"Colunas disponíveis: {list(df.columns)}. "
            "Verifique se o arquivo tem as colunas Título, Valor Movto e Dat Transac."
        )
    out = pd.DataFrame()
    out["Documento"] = df[col_map["documento"]].apply(normalizar_documento)
    out["Série"] = df[col_map["serie"]].apply(normalizar_serie) if "serie" in col_map else ""
    out["Valor"] = pd.to_numeric(df[col_map["valor"]], errors="coerce").fillna(0)
    out["Data"] = pd.to_datetime(df[col_map["data"]], errors="coerce")
    out["Chave"] = out["Documento"] + "|" + out["Série"]
    return out[out["Documento"].astype(str).str.len() > 0].reset_index(drop=True)


def preparar_recebimento(df):
    col_map = _mapear_colunas(df, "recebimento")
    required = ["documento", "valor", "data"]
    missing = [r for r in required if r not in col_map]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas no Recebimento: {missing}. "
            f"Colunas disponíveis: {list(df.columns)}. "
            "Verifique se o arquivo tem as colunas Documento, Crédito e Data Trans."
        )
    out = pd.DataFrame()
    out["Documento"] = df[col_map["documento"]].apply(normalizar_documento)
    out["Série"] = df[col_map["serie"]].apply(normalizar_serie) if "serie" in col_map else ""
    out["Valor"] = pd.to_numeric(df[col_map["valor"]], errors="coerce").fillna(0)
    out["Data"] = pd.to_datetime(df[col_map["data"]], errors="coerce")
    out["Chave"] = out["Documento"] + "|" + out["Série"]
    return out[out["Documento"].astype(str).str.len() > 0].reset_index(drop=True)


# ============================================================
# MOTOR DE CONCILIAÇÃO
# ============================================================

def conciliar(df_fin, df_rec, tolerancia=0.02):
    fin_agg = df_fin.groupby("Chave").agg(
        Documento=("Documento", "first"),
        Série=("Série", "first"),
        Valor_Financeiro=("Valor", "sum"),
        Data_Financeiro=("Data", "min"),
        Qtd_Linhas_Fin=("Valor", "count"),
    ).reset_index()

    rec_agg = df_rec.groupby("Chave").agg(
        Documento=("Documento", "first"),
        Série=("Série", "first"),
        Valor_Recebimento=("Valor", "sum"),
        Data_Recebimento=("Data", "min"),
        Qtd_Linhas_Rec=("Valor", "count"),
    ).reset_index()

    merged = pd.merge(
        fin_agg,
        rec_agg,
        on=["Chave", "Documento", "Série"],
        how="outer",
        indicator=True,
    )

    merged["Valor_Financeiro"] = merged["Valor_Financeiro"].fillna(0)
    merged["Valor_Recebimento"] = merged["Valor_Recebimento"].fillna(0)
    merged["Diferença"] = merged["Valor_Financeiro"] - merged["Valor_Recebimento"]

    def classificar(row):
        if row["_merge"] == "left_only":
            return "Só no Financeiro"
        if row["_merge"] == "right_only":
            return "Só no Recebimento"
        if abs(row["Diferença"]) > tolerancia:
            return "Valor Diferente"
        return "OK"

    merged["Tipo"] = merged.apply(classificar, axis=1)
    divergencias = merged[merged["Tipo"] != "OK"].copy()
    divergencias = divergencias.rename(columns={
        "Data_Financeiro": "Data Financeiro",
        "Data_Recebimento": "Data Recebimento",
        "Valor_Financeiro": "Valor Financeiro",
        "Valor_Recebimento": "Valor Recebimento",
    })

    cols_show = [
        "Documento", "Série", "Chave", "Data Financeiro", "Data Recebimento",
        "Valor Financeiro", "Valor Recebimento", "Diferença", "Tipo",
    ]
    divergencias = divergencias[[c for c in cols_show if c in divergencias.columns]]
    divergencias = divergencias.sort_values("Diferença", key=abs, ascending=False)

    total_fin = df_fin["Valor"].sum()
    total_rec = df_rec["Valor"].sum()

    return {
        "merged": merged,
        "divergencias": divergencias,
        "total_financeiro": round(total_fin, 2),
        "total_recebimento": round(total_rec, 2),
        "diferenca": round(total_fin - total_rec, 2),
        "qtd_docs_financeiro": len(fin_agg),
        "qtd_docs_recebimento": len(rec_agg),
        "qtd_divergencias": len(divergencias),
        "qtd_so_financeiro": len(divergencias[divergencias["Tipo"] == "Só no Financeiro"]),
        "qtd_so_recebimento": len(divergencias[divergencias["Tipo"] == "Só no Recebimento"]),
        "qtd_valor_diferente": len(divergencias[divergencias["Tipo"] == "Valor Diferente"]),
        "qtd_ok": len(merged[merged["Tipo"] == "OK"]),
    }


def estilo_divergencias(df):
    if df is None or df.empty:
        return df

    def cor_linha(row):
        tipo = str(row.get("Tipo", ""))
        if tipo == "Só no Financeiro":
            return ["background-color:#fee2e2;color:#7f1d1d"] * len(row)
        if tipo == "Só no Recebimento":
            return ["background-color:#dbeafe;color:#1e3a8a"] * len(row)
        if tipo == "Valor Diferente":
            return ["background-color:#fef3c7;color:#78350f"] * len(row)
        return [""] * len(row)

    return (
        df.copy()
        .style
        .apply(cor_linha, axis=1)
        .set_properties(**{
            "font-family": "IBM Plex Mono, monospace",
            "font-size": "0.85rem",
            "border-color": "#e5e7eb",
        })
        .set_table_styles([
            {"selector": "th", "props": [
                ("background-color", "#22c55e"),
                ("color", "#ffffff"),
                ("font-weight", "600"),
                ("font-family", "DM Sans, sans-serif"),
                ("padding", "0.6rem 0.75rem"),
                ("border", "none"),
            ]},
            {"selector": "td", "props": [
                ("padding", "0.5rem 0.75rem"),
                ("border-bottom", "1px solid #e5e7eb"),
            ]},
        ])
    )


# ============================================================
# DASHBOARD
# ============================================================

def exibir_dashboard():
    st.subheader("📊 Dashboard")
    st.caption("Visão geral das conciliações realizadas")

    filtro_est = st.selectbox(
        "Estabelecimento",
        ["Todos"] + ESTABELECIMENTOS,
        key="dashboard_estabelecimento",
    )

    hist = listar_historico(None if filtro_est == "Todos" else filtro_est)

    if hist.empty:
        st.info("Nenhuma conciliação realizada ainda. Execute uma conciliação para começar a acompanhar os indicadores.")
        return

    total_conciliacoes = len(hist)
    total_ok = int((hist["status"] == "OK").sum())
    total_com_divergencias = int((hist["status"] == "COM DIVERGÊNCIAS").sum())
    total_divergencias = int(hist["qtd_divergencias"].fillna(0).sum())
    total_documentos = int(
        hist["qtd_docs_financeiro"].fillna(0).sum()
        + hist["qtd_docs_recebimento"].fillna(0).sum()
    )
    diferenca_acumulada = float(hist["diferenca"].fillna(0).sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Conciliações", total_conciliacoes)
    m2.metric("Sem divergências", total_ok)
    m3.metric("Com divergências", total_com_divergencias)
    m4.metric("Divergências", total_divergencias)

    m5, m6 = st.columns(2)
    m5.metric("Documentos analisados", total_documentos)
    m6.metric("Diferença acumulada", f"R$ {diferenca_acumulada:,.2f}")

    st.markdown("### Últimas conciliações")

    recentes = hist.head(10).copy()
    recentes["data_execucao"] = pd.to_datetime(recentes["data_execucao"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    recentes = recentes[
        [
            "id", "estabelecimento", "periodo", "data_execucao",
            "diferenca", "qtd_divergencias", "status",
        ]
    ]
    recentes = recentes.rename(columns={
        "id": "ID",
        "estabelecimento": "Estabelecimento",
        "periodo": "Período",
        "data_execucao": "Executado em",
        "diferenca": "Diferença",
        "qtd_divergencias": "Divergências",
        "status": "Status",
    })
    recentes["Diferença"] = recentes["Diferença"].apply(lambda x: f"R$ {x:,.2f}")
    st.dataframe(recentes, use_container_width=True, hide_index=True)


# ============================================================
# NOVA CONCILIAÇÃO
# ============================================================

def exibir_nova_conciliacao():
    st.subheader("Nova Conciliação")

    col1, col2, col3 = st.columns(3)
    with col1:
        estabelecimento = st.selectbox("Estabelecimento", ESTABELECIMENTOS, index=2)
    with col2:
        periodo = st.text_input("Período (ex: 07/2026)", value=datetime.now().strftime("%m/%Y"))
    with col3:
        tolerancia = st.number_input("Tolerância (R$)", min_value=0.0, value=0.02, step=0.01, format="%.2f")

    st.markdown("### Upload das planilhas")
    c1, c2 = st.columns(2)
    with c1:
        file_fin = st.file_uploader(
            "Planilha **Financeiro** (Fiscal)",
            type=["xlsx", "xls"],
            key="fin",
            help="Deve conter: Título, Valor Movto, Dat Transac, Série",
        )
    with c2:
        file_rec = st.file_uploader(
            "Planilha **Recebimentos**",
            type=["xlsx", "xls"],
            key="rec",
            help="Deve conter: Documento, Crédito, Data Trans, Série",
        )

    observacao = st.text_input("Observação (opcional)", placeholder="Ex: Conciliação mensal agosto/2026")

    if st.button("🚀 Executar Conciliação", type="primary", use_container_width=True):
        if not file_fin or not file_rec:
            st.error("Envie as duas planilhas para continuar.")
            return

        with st.spinner("Processando planilhas..."):
            try:
                df_fin = preparar_financeiro(_ler_excel_robusto(file_fin))

                xls_rec = pd.ExcelFile(file_rec)
                sheet_rec = xls_rec.sheet_names[0]
                for sheet_name in xls_rec.sheet_names:
                    if "ce0403" in sheet_name.lower() or "receb" in sheet_name.lower():
                        sheet_rec = sheet_name
                        break

                df_rec = preparar_recebimento(_ler_excel_robusto(file_rec, sheet_name=sheet_rec))
                resultado = conciliar(df_fin, df_rec, tolerancia=tolerancia)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                nome_fin = f"{estabelecimento}_Financeiro_{timestamp}_{file_fin.name}"
                nome_rec = f"{estabelecimento}_Recebimentos_{timestamp}_{file_rec.name}"

                with open(UPLOAD_DIR / nome_fin, "wb") as file:
                    file.write(file_fin.getvalue())
                with open(UPLOAD_DIR / nome_rec, "wb") as file:
                    file.write(file_rec.getvalue())

                meta = {
                    "estabelecimento": estabelecimento,
                    "periodo": periodo,
                    "data_execucao": datetime.now().isoformat(timespec="seconds"),
                    "total_financeiro": resultado["total_financeiro"],
                    "total_recebimento": resultado["total_recebimento"],
                    "diferenca": resultado["diferenca"],
                    "qtd_docs_financeiro": resultado["qtd_docs_financeiro"],
                    "qtd_docs_recebimento": resultado["qtd_docs_recebimento"],
                    "qtd_divergencias": resultado["qtd_divergencias"],
                    "qtd_so_financeiro": resultado["qtd_so_financeiro"],
                    "qtd_so_recebimento": resultado["qtd_so_recebimento"],
                    "qtd_valor_diferente": resultado["qtd_valor_diferente"],
                    "status": "OK" if resultado["qtd_divergencias"] == 0 else "COM DIVERGÊNCIAS",
                    "arquivo_financeiro": nome_fin,
                    "arquivo_recebimento": nome_rec,
                    "observacao": observacao,
                }

                conc_id = salvar_conciliacao(meta, resultado["divergencias"])
                st.success(f"Conciliação salva no histórico (ID #{conc_id})")

                st.markdown("---")
                st.subheader("📊 Resultado da Conciliação")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Financeiro", f"R$ {resultado['total_financeiro']:,.2f}")
                m2.metric("Total Recebimento", f"R$ {resultado['total_recebimento']:,.2f}")
                m3.metric("Diferença", f"R$ {resultado['diferenca']:,.2f}", delta_color="inverse" if abs(resultado["diferenca"]) > tolerancia else "off")
                m4.metric("Divergências", resultado["qtd_divergencias"])

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Docs Financeiro", resultado["qtd_docs_financeiro"])
                c2.metric("Docs Recebimento", resultado["qtd_docs_recebimento"])
                c3.metric("Só no Financeiro", resultado["qtd_so_financeiro"])
                c4.metric("Só no Recebimento", resultado["qtd_so_recebimento"])

                if resultado["qtd_divergencias"] > 0:
                    st.markdown("### ⚠️ Divergências encontradas")
                    st.markdown("🔴 **Só no Financeiro** &nbsp;&nbsp; 🔵 **Só no Recebimento** &nbsp;&nbsp; 🟡 **Valor Diferente**")
                    div_show = resultado["divergencias"].copy()
                    for column in ["Data Financeiro", "Data Recebimento"]:
                        if column in div_show.columns:
                            div_show[column] = pd.to_datetime(div_show[column], errors="coerce").dt.strftime("%d/%m/%Y")
                    for column in ["Valor Financeiro", "Valor Recebimento", "Diferença"]:
                        if column in div_show.columns:
                            div_show[column] = div_show[column].apply(lambda x: f"R$ {x:,.2f}" if pd.notna(x) else "")
                    st.dataframe(estilo_divergencias(div_show), use_container_width=True, hide_index=True, height=min(420, 48 + len(div_show) * 36))

                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        resultado["divergencias"].to_excel(writer, index=False, sheet_name="Divergencias")
                    st.download_button(
                        "⬇️ Baixar divergências (Excel)",
                        data=buffer.getvalue(),
                        file_name=f"divergencias_{estabelecimento}_{periodo.replace('/', '-')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                else:
                    st.success("✅ Nenhuma divergência encontrada! Contas batem perfeitamente.")

                st.info("🔑 A chave de comparação é **Documento + Série**. Documentos com a mesma numeração e séries diferentes são tratados como itens distintos.")

            except Exception as error:
                st.error(f"Erro ao processar: {error}")
                st.exception(error)


# ============================================================
# HISTÓRICO
# ============================================================

def exibir_historico():
    st.subheader("📜 Histórico de Conciliações")

    filtro_est = st.selectbox("Filtrar por estabelecimento", ["Todos"] + ESTABELECIMENTOS, key="historico_estabelecimento")
    hist = listar_historico(None if filtro_est == "Todos" else filtro_est)

    if hist.empty:
        st.info("Nenhuma conciliação realizada ainda.")
        return

    hist_view = hist.copy()
    hist_view["data_execucao"] = pd.to_datetime(hist_view["data_execucao"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    hist_view["total_financeiro"] = hist_view["total_financeiro"].apply(lambda x: f"R$ {x:,.2f}")
    hist_view["total_recebimento"] = hist_view["total_recebimento"].apply(lambda x: f"R$ {x:,.2f}")
    hist_view["diferenca"] = hist_view["diferenca"].apply(lambda x: f"R$ {x:,.2f}")

    cols_show = [
        "id", "estabelecimento", "periodo", "data_execucao",
        "total_financeiro", "total_recebimento", "diferenca",
        "qtd_divergencias", "status", "observacao",
    ]
    st.dataframe(hist_view[cols_show], use_container_width=True, hide_index=True)

    st.markdown("### Detalhes de uma conciliação")
    ids = hist["id"].tolist()

    def formatar_conciliacao(conciliacao_id):
        linha = hist[hist["id"] == conciliacao_id].iloc[0]
        return f"#{conciliacao_id} — {linha['estabelecimento']} — {linha['periodo']}"

    selected_id = st.selectbox("Selecione o ID", ids, format_func=formatar_conciliacao)

    if selected_id:
        row = hist[hist["id"] == selected_id].iloc[0]
        st.markdown(
            f"**Estabelecimento:** {row['estabelecimento']}  \n"
            f"**Período:** {row['periodo']}  \n"
            f"**Executado em:** {row['data_execucao']}  \n"
            f"**Status:** {row['status']}  \n"
            f"**Observação:** {row['observacao'] or '-'}"
        )

        divs = carregar_divergencias(selected_id)
        if divs.empty:
            st.success("Sem divergências nesta conciliação.")
            return

        st.markdown(f"**{len(divs)} divergência(s):**")
        for column in ["data_financeiro", "data_recebimento"]:
            if column in divs.columns:
                divs[column] = pd.to_datetime(divs[column], errors="coerce").dt.strftime("%d/%m/%Y")

        st.dataframe(divs.drop(columns=["id", "conciliacao_id"], errors="ignore"), use_container_width=True, hide_index=True)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            divs.to_excel(writer, index=False, sheet_name="Divergencias")

        st.download_button(
            "⬇️ Baixar divergências desta conciliação",
            data=buffer.getvalue(),
            file_name=f"historico_divergencias_id{selected_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


# ============================================================
# APLICAÇÃO
# ============================================================

def main():
    init_db()
    inject_css()

    st.title("⚖️ Conciliação Transitória de Fornecedores")
    st.caption("Conta 91001001 • Estabelecimentos 101 / 103 / 104 / 106")

    with st.sidebar:
        st.header("Navegação")
        pagina = st.radio(
            "Ir para",
            ["Dashboard", "Nova Conciliação", "Histórico"],
            index=0,
            label_visibility="collapsed",
        )
        st.divider()
        st.markdown("**Conta contábil**")
        st.markdown(
            """
            <div class="conta-contabil">
                <div class="conta-numero">91001001</div>
                <div class="conta-descricao">TRANSITORIA DE FORNECEDORES</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.caption("Versão 2.0 • Dashboard")

    if pagina == "Dashboard":
        exibir_dashboard()
    elif pagina == "Nova Conciliação":
        exibir_nova_conciliacao()
    else:
        exibir_historico()


if __name__ == "__main__":
    main()
