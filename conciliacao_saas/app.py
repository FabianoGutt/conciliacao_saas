"""
SaaS de Conciliação - Conta 91001001 TRANSITÓRIA DE FORNECEDORES
Protótipo Streamlit (Opção A)
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import sqlite3
import hashlib
import os
from pathlib import Path
import io

# ============================================================
# CONFIGURAÇÃO
# ============================================================
st.set_page_config(
    page_title="Conciliação Transitoria Fornecedores",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = Path(__file__).parent / "historico_conciliacoes.db"
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ESTABELECIMENTOS = ["101", "103", "104", "106"]

# ============================================================
# BANCO DE DADOS (Histórico)
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
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
    c.execute("""
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

def salvar_conciliacao(meta: dict, divergencias_df: pd.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
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
        meta["status"], meta["arquivo_financeiro"], meta["arquivo_recebimento"],
        meta.get("observacao", "")
    ))
    conc_id = c.lastrowid

    if not divergencias_df.empty:
        for _, row in divergencias_df.iterrows():
            c.execute("""
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
                str(row.get("Tipo", ""))
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

def carregar_divergencias(conciliacao_id: int):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM divergencias WHERE conciliacao_id = ? ORDER BY ABS(diferenca) DESC",
        conn, params=(conciliacao_id,)
    )
    conn.close()
    return df

# ============================================================
# FUNÇÕES DE NORMALIZAÇÃO E COMPARAÇÃO
# ============================================================
def normalizar_serie(s):
    """Normaliza série para comparação consistente.
    Remove espaços, zeros à esquerda e zeros à direita de séries numéricas
    (700/70000 → 7; 900/9 → 9). Séries alfanuméricas (ex: S) são apenas
    limpas. Observação: séries como 10 viram 1 — no contexto atual das
    planilhas isso não gera falso positivo relevante.
    """
    if pd.isna(s) or s is None:
        return ""
    s = str(s).strip().upper()
    s = "".join(s.split())
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
    """Remove zeros à esquerda do documento."""
    if pd.isna(d) or d is None:
        return ""
    s = str(d).strip()
    s = s.lstrip("0") or "0"
    return s

def _encontrar_linha_cabecalho(df_raw: pd.DataFrame, palavras_chave: list) -> int:
    """Procura a linha que contém o cabeçalho real (quando há títulos acima)."""
    for i in range(min(30, len(df_raw))):
        row_vals = [str(v).lower().strip() for v in df_raw.iloc[i].tolist()]
        row_text = " | ".join(row_vals)
        hits = sum(1 for p in palavras_chave if p in row_text)
        if hits >= 2:
            return i
    return 0


def _mapear_colunas(df: pd.DataFrame, tipo: str) -> dict:
    """Mapeia colunas de forma flexível (aceita variações de nome)."""
    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if tipo == "financeiro":
            if any(x in col_lower for x in ["título", "titulo", "title"]):
                col_map["documento"] = col
            elif "valor movto" in col_lower or ("valor" in col_lower and "movto" in col_lower):
                col_map["valor"] = col
            elif "valor" in col_lower and "documento" not in col_map:
                if "valor" not in col_map:
                    col_map["valor"] = col
            elif any(x in col_lower for x in ["dat transac", "data transac", "dat_transac"]):
                col_map["data"] = col
            elif col_lower.startswith("data") or "data" in col_lower:
                if "data" not in col_map:
                    col_map["data"] = col
            elif any(x in col_lower for x in ["série", "serie", "series"]):
                col_map["serie"] = col
        else:  # recebimento
            if "documento" in col_lower:
                col_map["documento"] = col
            elif any(x in col_lower for x in ["crédito", "credito", "credito"]):
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


def _ler_excel_robusto(file_or_path, sheet_name=0) -> pd.DataFrame:
    """Lê Excel tentando detectar a linha de cabeçalho automaticamente."""
    df = pd.read_excel(file_or_path, sheet_name=sheet_name, header=0)
    cols_str = " ".join(str(c).lower() for c in df.columns)

    if all(str(c).startswith("Unnamed") for c in df.columns) or (
        "título" not in cols_str and "titulo" not in cols_str and "documento" not in cols_str
        and "valor" not in cols_str and "crédito" not in cols_str and "credito" not in cols_str
    ):
        df_raw = pd.read_excel(file_or_path, sheet_name=sheet_name, header=None)
        palavras = ["título", "titulo", "documento", "valor", "crédito", "credito", "data", "série", "serie"]
        header_row = _encontrar_linha_cabecalho(df_raw, palavras)
        df = pd.read_excel(file_or_path, sheet_name=sheet_name, header=header_row)

    df = df.dropna(axis=1, how="all")
    return df


def preparar_financeiro(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara planilha Financeiro."""
    col_map = _mapear_colunas(df, "financeiro")

    required = ["documento", "valor", "data"]
    missing = [r for r in required if r not in col_map]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas no Financeiro: {missing}. "
            f"Colunas disponíveis: {list(df.columns)}. "
            f"Verifique se o arquivo tem as colunas Título, Valor Movto e Dat Transac."
        )

    out = pd.DataFrame()
    out["Documento"] = df[col_map["documento"]].apply(normalizar_documento)
    out["Série"] = df[col_map["serie"]].apply(normalizar_serie) if "serie" in col_map else ""
    out["Valor"] = pd.to_numeric(df[col_map["valor"]], errors="coerce").fillna(0)
    out["Data"] = pd.to_datetime(df[col_map["data"]], errors="coerce")
    out["Chave"] = out["Documento"] + "|" + out["Série"]
    out = out[out["Documento"].astype(str).str.len() > 0]
    return out.reset_index(drop=True)


def preparar_recebimento(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara planilha Recebimento."""
    col_map = _mapear_colunas(df, "recebimento")

    required = ["documento", "valor", "data"]
    missing = [r for r in required if r not in col_map]
    if missing:
        raise ValueError(
            f"Colunas obrigatórias não encontradas no Recebimento: {missing}. "
            f"Colunas disponíveis: {list(df.columns)}. "
            f"Verifique se o arquivo tem as colunas Documento, Crédito e Data Trans."
        )

    out = pd.DataFrame()
    out["Documento"] = df[col_map["documento"]].apply(normalizar_documento)
    out["Série"] = df[col_map["serie"]].apply(normalizar_serie) if "serie" in col_map else ""
    out["Valor"] = pd.to_numeric(df[col_map["valor"]], errors="coerce").fillna(0)
    out["Data"] = pd.to_datetime(df[col_map["data"]], errors="coerce")
    out["Chave"] = out["Documento"] + "|" + out["Série"]
    out = out[out["Documento"].astype(str).str.len() > 0]
    return out.reset_index(drop=True)

def conciliar(df_fin: pd.DataFrame, df_rec: pd.DataFrame, tolerancia: float = 0.02) -> dict:
    """
    Realiza a conciliação.
    Chave única = Documento + Série
    Duplicados são sumarizados.
    """
    fin_agg = df_fin.groupby("Chave").agg(
        Documento=("Documento", "first"),
        Série=("Série", "first"),
        Valor_Financeiro=("Valor", "sum"),
        Data_Financeiro=("Data", "min"),
        Qtd_Linhas_Fin=("Valor", "count")
    ).reset_index()

    rec_agg = df_rec.groupby("Chave").agg(
        Documento=("Documento", "first"),
        Série=("Série", "first"),
        Valor_Recebimento=("Valor", "sum"),
        Data_Recebimento=("Data", "min"),
        Qtd_Linhas_Rec=("Valor", "count")
    ).reset_index()

    merged = pd.merge(
        fin_agg, rec_agg,
        on=["Chave", "Documento", "Série"],
        how="outer",
        indicator=True
    )

    merged["Valor_Financeiro"] = merged["Valor_Financeiro"].fillna(0)
    merged["Valor_Recebimento"] = merged["Valor_Recebimento"].fillna(0)
    merged["Diferença"] = merged["Valor_Financeiro"] - merged["Valor_Recebimento"]

    def classificar(row):
        if row["_merge"] == "left_only":
            return "Só no Financeiro"
        elif row["_merge"] == "right_only":
            return "Só no Recebimento"
        elif abs(row["Diferença"]) > tolerancia:
            return "Valor Diferente"
        else:
            return "OK"

    merged["Tipo"] = merged.apply(classificar, axis=1)

    divergencias = merged[merged["Tipo"] != "OK"].copy()
    divergencias = divergencias.rename(columns={
        "Data_Financeiro": "Data Financeiro",
        "Data_Recebimento": "Data Recebimento",
        "Valor_Financeiro": "Valor Financeiro",
        "Valor_Recebimento": "Valor Recebimento",
    })

    cols_show = ["Documento", "Série", "Chave", "Data Financeiro", "Data Recebimento",
                 "Valor Financeiro", "Valor Recebimento", "Diferença", "Tipo"]
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

# ============================================================
# INTERFACE
# ============================================================
def main():
    init_db()

    st.title("⚖️ Conciliação Transitoria de Fornecedores")
    st.caption("Conta 91001001 • Estabelecimentos 101 / 103 / 104 / 106")

    with st.sidebar:
        st.header("Navegação")
        pagina = st.radio(
            "Ir para",
            ["Nova Conciliação", "Histórico"],
            label_visibility="collapsed"
        )
        st.divider()
        st.markdown("**Conta contábil**")
        st.code("91001001\nTRANSITORIA DE FORNECEDORES")
        st.markdown("---")
        st.caption("Protótipo v1.0 • Opção A")

    if pagina == "Nova Conciliação":
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
                help="Deve conter: Título, Valor Movto, Dat Transac, Série"
            )
        with c2:
            file_rec = st.file_uploader(
                "Planilha **Recebimentos**",
                type=["xlsx", "xls"],
                key="rec",
                help="Deve conter: Documento, Crédito, Data Trans, Série"
            )

        observacao = st.text_input("Observação (opcional)", placeholder="Ex: Conciliação mensal julho/2026")

        if st.button("🚀 Executar Conciliação", type="primary", use_container_width=True):
            if not file_fin or not file_rec:
                st.error("Envie as duas planilhas para continuar.")
                st.stop()

            with st.spinner("Processando planilhas..."):
                try:
                    df_fin_raw = _ler_excel_robusto(file_fin)
                    df_fin = preparar_financeiro(df_fin_raw)

                    xls_rec = pd.ExcelFile(file_rec)
                    sheet_rec = xls_rec.sheet_names[0]
                    for s in xls_rec.sheet_names:
                        if "ce0403" in s.lower() or "receb" in s.lower():
                            sheet_rec = s
                            break
                    df_rec_raw = _ler_excel_robusto(file_rec, sheet_name=sheet_rec)
                    df_rec = preparar_recebimento(df_rec_raw)

                    resultado = conciliar(df_fin, df_rec, tolerancia=tolerancia)

                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    nome_fin = f"{estabelecimento}_Financeiro_{ts}_{file_fin.name}"
                    nome_rec = f"{estabelecimento}_Recebimentos_{ts}_{file_rec.name}"
                    with open(UPLOAD_DIR / nome_fin, "wb") as f:
                        f.write(file_fin.getvalue())
                    with open(UPLOAD_DIR / nome_rec, "wb") as f:
                        f.write(file_rec.getvalue())

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
                    m3.metric("Diferença", f"R$ {resultado['diferenca']:,.2f}",
                              delta_color="inverse" if abs(resultado['diferenca']) > 0.02 else "off")
                    m4.metric("Divergências", resultado["qtd_divergencias"])

                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Docs Financeiro", resultado["qtd_docs_financeiro"])
                    c2.metric("Docs Recebimento", resultado["qtd_docs_recebimento"])
                    c3.metric("Só no Financeiro", resultado["qtd_so_financeiro"])
                    c4.metric("Só no Recebimento", resultado["qtd_so_recebimento"])

                    if resultado["qtd_divergencias"] > 0:
                        st.markdown("### ⚠️ Divergências encontradas")
                        div = resultado["divergencias"].copy()

                        for col in ["Data Financeiro", "Data Recebimento"]:
                            if col in div.columns:
                                div[col] = pd.to_datetime(div[col], errors="coerce").dt.strftime("%d/%m/%Y")
                        for col in ["Valor Financeiro", "Valor Recebimento", "Diferença"]:
                            if col in div.columns:
                                div[col] = div[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")

                        st.dataframe(div, use_container_width=True, hide_index=True)

                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                            resultado["divergencias"].to_excel(writer, index=False, sheet_name="Divergencias")
                        st.download_button(
                            "⬇️ Baixar divergências (Excel)",
                            data=buffer.getvalue(),
                            file_name=f"divergencias_{estabelecimento}_{periodo.replace('/','-')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.success("✅ Nenhuma divergência encontrada! Contas batem perfeitamente.")

                    st.info("🔑 A chave de comparação é **Documento + Série**. Documentos com a mesma numeração e séries diferentes são tratados como itens distintos.")

                except Exception as e:
                    st.error(f"Erro ao processar: {str(e)}")
                    st.exception(e)

    else:
        st.subheader("📜 Histórico de Conciliações")

        filtro_est = st.selectbox("Filtrar por estabelecimento", ["Todos"] + ESTABELECIMENTOS)
        hist = listar_historico(None if filtro_est == "Todos" else filtro_est)

        if hist.empty:
            st.info("Nenhuma conciliação realizada ainda.")
        else:
            hist_view = hist.copy()
            hist_view["data_execucao"] = pd.to_datetime(hist_view["data_execucao"]).dt.strftime("%d/%m/%Y %H:%M")
            hist_view["total_financeiro"] = hist_view["total_financeiro"].apply(lambda x: f"R$ {x:,.2f}")
            hist_view["total_recebimento"] = hist_view["total_recebimento"].apply(lambda x: f"R$ {x:,.2f}")
            hist_view["diferenca"] = hist_view["diferenca"].apply(lambda x: f"R$ {x:,.2f}")

            cols_show = ["id", "estabelecimento", "periodo", "data_execucao",
                         "total_financeiro", "total_recebimento", "diferenca",
                         "qtd_divergencias", "status", "observacao"]
            st.dataframe(hist_view[cols_show], use_container_width=True, hide_index=True)

            st.markdown("### Detalhes de uma conciliação")
            ids = hist["id"].tolist()
            selected_id = st.selectbox("Selecione o ID", ids, format_func=lambda x: f"#{x} — {hist.loc[hist['id']==x, 'estabelecimento'].values[0]} — {hist.loc[hist['id']==x, 'periodo'].values[0]}")

            if selected_id:
                row = hist[hist["id"] == selected_id].iloc[0]
                st.markdown(f"""
                **Estabelecimento:** {row['estabelecimento']}  
                **Período:** {row['periodo']}  
                **Executado em:** {row['data_execucao']}  
                **Status:** {row['status']}  
                **Observação:** {row['observacao'] or '-'}
                """)

                divs = carregar_divergencias(selected_id)
                if divs.empty:
                    st.success("Sem divergências nesta conciliação.")
                else:
                    st.markdown(f"**{len(divs)} divergência(s):**")
                    for col in ["data_financeiro", "data_recebimento"]:
                        if col in divs.columns:
                            divs[col] = pd.to_datetime(divs[col], errors="coerce").dt.strftime("%d/%m/%Y")
                    st.dataframe(divs.drop(columns=["id", "conciliacao_id"], errors="ignore"),
                                 use_container_width=True, hide_index=True)

                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        divs.to_excel(writer, index=False, sheet_name="Divergencias")
                    st.download_button(
                        "⬇️ Baixar divergências desta conciliação",
                        data=buffer.getvalue(),
                        file_name=f"historico_divergencias_id{selected_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

if __name__ == "__main__":
    main()
