"""
SaaS de Conciliação - Conta 91001001 TRANSITÓRIA DE FORNECEDORES
Streamlit V8.4 - Supabase PostgreSQL + Storage
Sem autenticação nesta fase
"""

import io
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from supabase import create_client


# ============================================================
# FORMATAÇÃO NUMÉRICA PT-BR
# ============================================================

def formatar_numero_br(valor):
    if valor is None or pd.isna(valor):
        return ""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return ""
    return (
        f"{numero:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def formatar_moeda_br(valor):
    numero = formatar_numero_br(valor)
    return f"R$ {numero}" if numero else ""


def parse_numero_br(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Conciliação Transitória de Fornecedores",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

STORAGE_BUCKET = "conciliacoes"


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"].strip()
    key = st.secrets["SUPABASE_SECRET_KEY"].strip()

    if not url:
        raise RuntimeError("SUPABASE_URL não configurada.")
    if not key:
        raise RuntimeError("SUPABASE_SECRET_KEY não configurada.")

    return create_client(url, key)


supabase = get_supabase()


def _buscar_paginado(tabela, colunas="*", filtros=None, ordem=None, limite=1000):
    """
    Busca registros da tabela em páginas para não depender do limite
    padrão da Data API.
    """
    filtros = filtros or []
    registros = []
    inicio = 0

    while True:
        consulta = supabase.table(tabela).select(colunas)

        for metodo, coluna, valor in filtros:
            if metodo == "eq":
                consulta = consulta.eq(coluna, valor)
            elif metodo == "neq":
                consulta = consulta.neq(coluna, valor)
            elif metodo == "ilike":
                consulta = consulta.ilike(coluna, valor)

        if ordem:
            coluna_ordem, desc = ordem
            consulta = consulta.order(
                coluna_ordem,
                desc=desc,
            )

        resposta = (
            consulta
            .range(inicio, inicio + limite - 1)
            .execute()
        )

        dados = resposta.data or []
        registros.extend(dados)

        if len(dados) < limite:
            break

        inicio += limite

    return registros


def obter_estabelecimentos():
    dados = _buscar_paginado(
        "estabelecimentos",
        colunas="id,codigo,nome,ativo",
        filtros=[
            ("eq", "ativo", True),
        ],
        ordem=("codigo", False),
    )
    return dados


def obter_codigos_estabelecimentos():
    return [
        str(item["codigo"])
        for item in obter_estabelecimentos()
    ]


def obter_estabelecimento_id(codigo):
    codigo = str(codigo)

    dados = _buscar_paginado(
        "estabelecimentos",
        colunas="id,codigo,nome,ativo",
        filtros=[
            ("eq", "codigo", codigo),
        ],
    )

    if not dados:
        raise ValueError(
            f"Estabelecimento {codigo} não encontrado no Supabase."
        )

    return dados[0]["id"]


def _data_iso(valor):
    if valor is None or pd.isna(valor):
        return None

    try:
        return pd.Timestamp(valor).strftime("%Y-%m-%d")
    except Exception:
        return None


def _sanitizar_nome_arquivo(nome):
    nome = Path(str(nome)).name
    caracteres_invalidos = '<>:"/\\|?*'

    for caractere in caracteres_invalidos:
        nome = nome.replace(caractere, "_")

    return nome or "arquivo.xlsx"


def _periodo_storage(periodo):
    texto = str(periodo or "").strip()
    texto = texto.replace("/", "-")
    texto = texto.replace("\\", "-")
    return texto or "sem-periodo"


def _upload_storage(file_bytes, caminho, content_type):
    """Envia bytes para o Supabase Storage usando arquivo temporário.

    A versão do storage3 utilizada pelo ambiente do Streamlit espera
    um caminho de arquivo/PathLike no parâmetro `file` durante o upload.
    Por isso gravamos temporariamente os bytes recebidos pelo Streamlit.
    """
    sufixo = Path(caminho).suffix or ".xlsx"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=sufixo,
            delete=False,
        ) as temp_file:
            temp_file.write(file_bytes)
            temp_path = temp_file.name

        return (
            supabase.storage
            .from_(STORAGE_BUCKET)
            .upload(
                path=caminho,
                file=temp_path,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "false",
                },
            )
        )

    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _remover_storage(caminhos):
    caminhos = [
        caminho
        for caminho in caminhos
        if caminho
    ]

    if not caminhos:
        return

    (
        supabase.storage
        .from_(STORAGE_BUCKET)
        .remove(caminhos)
    )


# ============================================================
# BANCO / HISTÓRICO NO SUPABASE
# ============================================================

def salvar_conciliacao(meta, divergencias_df):
    resposta = (
        supabase
        .table("conciliacoes")
        .insert(meta)
        .select("id")
        .execute()
    )

    if not resposta.data:
        raise RuntimeError(
            "O Supabase não retornou o ID da conciliação."
        )

    conc_id = resposta.data[0]["id"]

    try:
        if not divergencias_df.empty:
            registros = []

            for _, row in divergencias_df.iterrows():
                registros.append(
                    {
                        "conciliacao_id": conc_id,
                        "documento": str(
                            row.get("Documento", "")
                        ),
                        "serie": str(
                            row.get("Série", "")
                        ),
                        "chave": str(
                            row.get("Chave", "")
                        ),
                        "data_financeiro": _data_iso(
                            row.get("Data Financeiro")
                        ),
                        "data_recebimento": _data_iso(
                            row.get("Data Recebimento")
                        ),
                        "valor_financeiro": float(
                            row.get(
                                "Valor Financeiro",
                                0,
                            )
                            or 0
                        ),
                        "valor_recebimento": float(
                            row.get(
                                "Valor Recebimento",
                                0,
                            )
                            or 0
                        ),
                        "diferenca": float(
                            row.get(
                                "Diferença",
                                0,
                            )
                            or 0
                        ),
                        "tipo": str(
                            row.get(
                                "Tipo",
                                "",
                            )
                        ),
                    }
                )

            (
                supabase
                .table("divergencias")
                .insert(registros)
                .execute()
            )

        return conc_id

    except Exception:
        (
            supabase
            .table("conciliacoes")
            .delete()
            .eq("id", conc_id)
            .execute()
        )
        raise


def _normalizar_historico(registros):
    hist = pd.DataFrame(registros)

    if hist.empty:
        return hist

    estab_ids = {
        item["id"]: str(item["codigo"])
        for item in obter_estabelecimentos()
    }

    hist["estabelecimento"] = (
        hist["estabelecimento_id"]
        .map(estab_ids)
        .fillna("")
    )

    return hist


def listar_historico(estabelecimento=None):
    filtros = []

    if (
        estabelecimento
        and estabelecimento != "Todos"
    ):
        estabelecimento_id = (
            obter_estabelecimento_id(
                estabelecimento
            )
        )
        filtros.append(
            (
                "eq",
                "estabelecimento_id",
                estabelecimento_id,
            )
        )

    registros = _buscar_paginado(
        "conciliacoes",
        colunas="*",
        filtros=filtros,
        ordem=("data_execucao", True),
    )

    return _normalizar_historico(registros)


def carregar_divergencias(conciliacao_id):
    registros = _buscar_paginado(
        "divergencias",
        colunas="*",
        filtros=[
            (
                "eq",
                "conciliacao_id",
                conciliacao_id,
            ),
        ],
        ordem=("diferenca", True),
    )

    return pd.DataFrame(registros)


def consultar_historico_avancado(
    estabelecimento="Todos",
    status="Todos",
    busca="",
    periodo_inicio=None,
    periodo_fim=None,
):
    filtros = []

    if (
        estabelecimento
        and estabelecimento != "Todos"
    ):
        filtros.append(
            (
                "eq",
                "estabelecimento_id",
                obter_estabelecimento_id(
                    estabelecimento
                ),
            )
        )

    if (
        status
        and status != "Todos"
    ):
        filtros.append(
            (
                "eq",
                "status",
                status,
            )
        )

    registros = _buscar_paginado(
        "conciliacoes",
        colunas="*",
        filtros=filtros,
        ordem=("data_execucao", True),
    )

    hist = _normalizar_historico(
        registros
    )

    if hist.empty:
        return hist

    hist["data_execucao_dt"] = pd.to_datetime(
        hist["data_execucao"],
        errors="coerce",
    )

    if periodo_inicio is not None:
        inicio = pd.Timestamp(
            periodo_inicio
        )
        hist = hist[
            hist["data_execucao_dt"].dt.date
            >= inicio.date()
        ]

    if periodo_fim is not None:
        fim = (
            pd.Timestamp(
                periodo_fim
            )
            + pd.Timedelta(days=1)
            - pd.Timedelta(seconds=1)
        )

        hist = hist[
            hist["data_execucao_dt"]
            <= fim
        ]

    busca = str(
        busca or ""
    ).strip()

    if busca:
        busca_lower = busca.lower()

        mask = (
            hist["id"]
            .astype(str)
            .str.contains(
                busca,
                case=False,
                na=False,
            )
            |
            hist["estabelecimento"]
            .astype(str)
            .str.contains(
                busca,
                case=False,
                na=False,
            )
            |
            hist["periodo"]
            .astype(str)
            .str.contains(
                busca,
                case=False,
                na=False,
            )
            |
            hist["observacao"]
            .astype(str)
            .str.contains(
                busca,
                case=False,
                na=False,
            )
        )

        div_documento = (
            _buscar_paginado(
                "divergencias",
                colunas="conciliacao_id",
                filtros=[
                    (
                        "ilike",
                        "documento",
                        f"%{busca}%",
                    )
                ],
            )
        )

        div_chave = (
            _buscar_paginado(
                "divergencias",
                colunas="conciliacao_id",
                filtros=[
                    (
                        "ilike",
                        "chave",
                        f"%{busca}%",
                    )
                ],
            )
        )

        div_ids = {
            item["conciliacao_id"]
            for item in (
                div_documento
                + div_chave
            )
        }

        mask = (
            mask
            |
            hist["id"].isin(
                div_ids
            )
        )

        hist = hist[mask]

    if "data_execucao_dt" in hist.columns:
        hist = hist.drop(
            columns=[
                "data_execucao_dt"
            ]
        )

    return hist.reset_index(
        drop=True
    )


def excluir_conciliacao(
    conciliacao_id
):
    """
    Exclui a conciliação do PostgreSQL.
    As divergências são removidas por ON DELETE CASCADE.
    Os arquivos associados são removidos do Storage.
    """
    resposta = (
        supabase
        .table("conciliacoes")
        .select(
            "arquivo_financeiro,arquivo_recebimento"
        )
        .eq(
            "id",
            conciliacao_id
        )
        .execute()
    )

    if not resposta.data:
        return False, []

    registro = resposta.data[0]

    arquivos = [
        registro.get(
            "arquivo_financeiro"
        ),
        registro.get(
            "arquivo_recebimento"
        ),
    ]

    (
        supabase
        .table("conciliacoes")
        .delete()
        .eq(
            "id",
            conciliacao_id
        )
        .execute()
    )

    avisos = []

    try:
        _remover_storage(
            arquivos
        )
    except Exception as error:
        avisos.append(
            "A conciliação foi excluída, "
            "mas um ou mais arquivos do Storage "
            f"não puderam ser removidos: {error}"
        )

    return True, avisos


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

        /* Botão de fechar/abrir o sidebar */
        button[data-testid="stSidebarCollapseButton"] {
            color:#374151!important;
        }
        button[data-testid="stSidebarCollapseButton"] svg {
            color:#374151!important;
            fill:#374151!important;
            stroke:#374151!important;
        }
        button[data-testid="stSidebarCollapseButton"]:hover {
            color:#1f2937!important;
            background-color:rgba(55,65,81,.08)!important;
        }

        /* ========================================================
           NAVEGAÇÃO DO SIDEBAR - RADIO
           ======================================================== */
        section[data-testid="stSidebar"] div[role="radiogroup"] {
            gap:0.35rem!important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label {
            background:#E0F2FE!important;
            border:1px solid #BAE6FD!important;
            border-radius:0.5rem!important;
            padding:0.55rem 0.75rem!important;
            margin-bottom:0.15rem!important;
            transition:all 0.15s ease!important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label p,
        section[data-testid="stSidebar"] div[role="radiogroup"] > label span {
            color:#374151!important;
            font-weight:500!important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
            background:#BAE6FD!important;
            border-color:#93C5FD!important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
            background:#D1FAE5!important;
            border-color:#86EFAC!important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p,
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) span {
            color:#166534!important;
            font-weight:600!important;
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
        div[data-testid="stMetric"] label{color:var(--muted-fg)!important;font-size:0.78rem!important;font-weight:500!important;}
        div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:var(--foreground-dark)!important;font-size:1.35rem!important;line-height:1.2!important;font-weight:600!important;}
        div[data-testid="stMetric"] [data-testid="stMetricDelta"]{color:var(--muted-fg)!important;font-size: 0.75rem !important;}

        div[data-testid="stAlert"]{border-radius:var(--radius)!important;}
        div[data-testid="stDataFrame"]{border:1px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden;box-shadow:0 4px 8px rgba(0,0,0,.05)!important;background:#fff!important;}
        .stDownloadButton>button{background:var(--secondary)!important;color:#0369a1!important;border:1px solid var(--secondary-dark)!important;border-radius:var(--radius)!important;font-weight:600!important;}
        .stDownloadButton>button *{color:#0369a1!important;}

        .dashboard-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:1rem 1.2rem;box-shadow:0 4px 8px rgba(0,0,0,.05);margin-bottom:1rem;}
        .dashboard-label{color:var(--muted-fg);font-size:.85rem;font-weight:500;}
        .dashboard-value{color:var(--foreground-dark);font-size:1.55rem;font-weight:700;margin-top:.2rem;}

        .info-box{background:#eff6ff;border:1px solid #bfdbfe;border-radius:var(--radius);padding:0.9rem 1rem;margin:0.5rem 0 1rem 0;color:#1e3a8a;}
        .info-box strong{color:#1e3a8a;}
        .status-ok{color:#047857;font-weight:600;}
        .status-warning{color:#b45309;font-weight:600;}
        /* ========================================================
           NAVEGAÇÃO DO SIDEBAR - RADIO / OVERRIDE V8.4
           ======================================================== */
        section[data-testid="stSidebar"] [role="radiogroup"] {
            display:flex!important;
            flex-direction:column!important;
            gap:.35rem!important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label {
            display:flex!important;
            align-items:center!important;
            width:100%!important;
            box-sizing:border-box!important;
            background:#E0F2FE!important;
            border:1px solid #BAE6FD!important;
            border-radius:.5rem!important;
            padding:.55rem .75rem!important;
            margin:0!important;
            color:#374151!important;
            transition:background-color .15s ease,border-color .15s ease!important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label:hover {
            background:#BAE6FD!important;
            border-color:#93C5FD!important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background:#D1FAE5!important;
            border-color:#86EFAC!important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label p,
        section[data-testid="stSidebar"] [role="radiogroup"] label span {
            color:#374151!important;
            font-weight:500!important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p,
        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) span {
            color:#166534!important;
            font-weight:600!important;
        }

        /* Garante que o radio nativo continue visível sem alterar o tema global */
        section[data-testid="stSidebar"] [role="radiogroup"] input[type="radio"] {
            accent-color:#22C55E!important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )




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
    # A chave oficial da conciliação continua sendo Documento + Série.
    # Repetições de documento com séries diferentes são tratadas como operações distintas.
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

    # Diferença de data é apenas informativa e NÃO altera o status.
    merged["Data_Diferente_Informativa"] = (
        (merged["_merge"] == "both")
        & merged["Data_Financeiro"].notna()
        & merged["Data_Recebimento"].notna()
        & (merged["Data_Financeiro"].dt.date != merged["Data_Recebimento"].dt.date)
    )

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
    if not divergencias.empty:
        divergencias = divergencias.sort_values("Diferença", key=abs, ascending=False)

    # Lista separada apenas para informação sobre datas diferentes.
    informacoes_data = merged[
        merged["Data_Diferente_Informativa"]
    ].copy()

    informacoes_data = informacoes_data.rename(columns={
        "Data_Financeiro": "Data Financeiro",
        "Data_Recebimento": "Data Recebimento",
    })

    cols_data = [
        "Documento",
        "Série",
        "Chave",
        "Data Financeiro",
        "Data Recebimento",
        "Valor_Financeiro",
        "Valor_Recebimento",
        "Diferença",
    ]
    informacoes_data = informacoes_data[
        [c for c in cols_data if c in informacoes_data.columns]
    ]

    if not informacoes_data.empty:
        informacoes_data = informacoes_data.sort_values(
            ["Data Financeiro", "Documento"],
            ascending=[False, True],
        )

    total_fin = df_fin["Valor"].sum()
    total_rec = df_rec["Valor"].sum()

    return {
        "merged": merged,
        "divergencias": divergencias,
        "informacoes_data": informacoes_data,
        "total_financeiro": round(total_fin, 2),
        "total_recebimento": round(total_rec, 2),
        "diferenca": round(total_fin - total_rec, 2),
        "qtd_docs_financeiro": len(fin_agg),
        "qtd_docs_recebimento": len(rec_agg),
        "qtd_linhas_financeiro": len(df_fin),
        "qtd_linhas_recebimento": len(df_rec),
        "qtd_chaves_financeiro": df_fin["Chave"].nunique(),
        "qtd_chaves_recebimento": df_rec["Chave"].nunique(),
        "qtd_datas_invalidas_financeiro": int(df_fin["Data"].isna().sum()),
        "qtd_datas_invalidas_recebimento": int(df_rec["Data"].isna().sum()),
        "qtd_divergencias": len(divergencias),
        "qtd_so_financeiro": len(divergencias[divergencias["Tipo"] == "Só no Financeiro"]),
        "qtd_so_recebimento": len(divergencias[divergencias["Tipo"] == "Só no Recebimento"]),
        "qtd_valor_diferente": len(divergencias[divergencias["Tipo"] == "Valor Diferente"]),
        "qtd_datas_diferentes_informativas": len(informacoes_data),
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

def _status_dashboard(row):
    status = str(row.get("Status", ""))

    if status == "OK":
        return [
            "background-color:#d1fae5; color:#047857; font-weight:600"
        ] * len(row)

    if status == "COM DIVERGÊNCIAS":
        return [
            "background-color:#fee2e2; color:#b91c1c; font-weight:600"
        ] * len(row)

    return [""] * len(row)


def _preparar_dashboard_dados(hist: pd.DataFrame) -> pd.DataFrame:
    dados = hist.copy()

    dados["data_execucao"] = pd.to_datetime(
        dados["data_execucao"],
        errors="coerce",
    )

    for column in [
        "qtd_divergencias",
        "qtd_docs_financeiro",
        "qtd_docs_recebimento",
        "diferenca",
    ]:
        dados[column] = pd.to_numeric(
            dados[column],
            errors="coerce",
        ).fillna(0)

    return dados


def exibir_dashboard():
    st.subheader("📊 Dashboard")
    st.caption("Visão gerencial das conciliações realizadas")

    # ========================================================
    # FILTROS
    # ========================================================

    f1, f2 = st.columns(2)

    with f1:
        filtro_est = st.selectbox(
            "Estabelecimento",
            ["Todos"] + obter_codigos_estabelecimentos(),
            key="dashboard_estabelecimento",
        )

    with f2:
        filtro_status = st.selectbox(
            "Status",
            [
                "Todos",
                "OK",
                "COM DIVERGÊNCIAS",
            ],
            key="dashboard_status",
        )

    hist = listar_historico(
        None if filtro_est == "Todos" else filtro_est
    )

    if filtro_status != "Todos" and not hist.empty:
        hist = hist[hist["status"] == filtro_status].copy()

    if hist.empty:
        st.info(
            "Nenhuma conciliação encontrada para os filtros selecionados."
        )
        return

    dados = _preparar_dashboard_dados(hist)

    # ========================================================
    # INDICADORES PRINCIPAIS
    # ========================================================

    total_conciliacoes = len(dados)
    total_ok = int((dados["status"] == "OK").sum())
    total_com_divergencias = int(
        (dados["status"] == "COM DIVERGÊNCIAS").sum()
    )
    total_divergencias = int(
        dados["qtd_divergencias"].sum()
    )

    taxa_ok = (
        (total_ok / total_conciliacoes) * 100
        if total_conciliacoes
        else 0
    )

    total_documentos = int(
        dados["qtd_docs_financeiro"].sum()
        + dados["qtd_docs_recebimento"].sum()
    )

    diferenca_acumulada = float(
        dados["diferenca"].sum()
    )

    media_diferenca = float(
        dados["diferenca"].abs().mean()
    )

    maior_diferenca = float(
        dados["diferenca"].abs().max()
    )

    ultima_data = dados["data_execucao"].max()
    ultima_conciliacao = (
        ultima_data.strftime("%d/%m/%Y %H:%M")
        if pd.notna(ultima_data)
        else "-"
    )

    # ========================================================
    # CARDS PRINCIPAIS
    # ========================================================

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Conciliações",
        total_conciliacoes,
    )

    m2.metric(
        "Taxa OK",
        f"{taxa_ok:.1f}".replace(".", ",") + "%",
    )

    m3.metric(
        "Com divergências",
        total_com_divergencias,
    )

    m4.metric(
        "Total de divergências",
        total_divergencias,
    )

    m5, m6, m7, m8 = st.columns(4)

    m5.metric(
        "Documentos analisados",
        total_documentos,
    )

    m6.metric(
        "Diferença acumulada",
        formatar_moeda_br(diferenca_acumulada),
    )

    m7.metric(
        "Média da diferença",
        formatar_moeda_br(media_diferenca),
    )

    m8.metric(
        "Maior diferença",
        formatar_moeda_br(maior_diferenca),
    )

    # ========================================================
    # RESUMO OPERACIONAL
    # ========================================================

    st.markdown("### Resumo operacional")

    resumo_col1, resumo_col2 = st.columns(2)

    with resumo_col1:
        st.markdown(
            f"""
            <div class="dashboard-card">
                <div class="dashboard-label">Última conciliação</div>
                <div class="dashboard-value">{ultima_conciliacao}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with resumo_col2:
        estabelecimento_resumo = (
            "Todos"
            if filtro_est == "Todos"
            else filtro_est
        )
        st.markdown(
            f"""
            <div class="dashboard-card">
                <div class="dashboard-label">Visão atual</div>
                <div class="dashboard-value">Estabelecimento {estabelecimento_resumo}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ========================================================
    # CONCILIAÇÕES POR ESTABELECIMENTO
    # ========================================================

    st.markdown("### Conciliações por estabelecimento")

    por_estabelecimento = (
        dados.groupby("estabelecimento")
        .size()
        .rename("Conciliações")
        .sort_values(ascending=False)
    )

    st.bar_chart(
        por_estabelecimento,
        height=250,
    )

    # ========================================================
    # EVOLUÇÃO MENSAL
    # ========================================================

    st.markdown("### Evolução mensal")

    evolucao = dados.dropna(
        subset=["data_execucao"]
    ).copy()

    if not evolucao.empty:
        evolucao["Mês"] = (
            evolucao["data_execucao"]
            .dt.to_period("M")
            .astype(str)
        )

        evolucao_mensal = (
            evolucao.groupby("Mês")
            .size()
            .rename("Conciliações")
            .sort_index()
        )

        st.line_chart(
            evolucao_mensal,
            height=250,
        )

    # ========================================================
    # ÚLTIMAS CONCILIAÇÕES
    # ========================================================

    st.markdown("### Últimas conciliações")

    recentes = dados.sort_values(
        "data_execucao",
        ascending=False,
    ).head(10).copy()

    recentes["data_execucao"] = recentes[
        "data_execucao"
    ].dt.strftime("%d/%m/%Y %H:%M")

    recentes = recentes[
        [
            "id",
            "estabelecimento",
            "periodo",
            "data_execucao",
            "diferenca",
            "qtd_divergencias",
            "status",
        ]
    ]

    recentes = recentes.rename(
        columns={
            "id": "ID",
            "estabelecimento": "Estabelecimento",
            "periodo": "Período",
            "data_execucao": "Executado em",
            "diferenca": "Diferença",
            "qtd_divergencias": "Divergências",
            "status": "Status",
        }
    )

    recentes["Diferença"] = recentes[
        "Diferença"
    ].apply(
        lambda value: formatar_moeda_br(value)
    )

    st.dataframe(
        recentes.style.apply(
            _status_dashboard,
            axis=1,
        ),
        use_container_width=True,
        hide_index=True,
    )





# ============================================================
# NOVA CONCILIAÇÃO
# ============================================================

def exibir_nova_conciliacao():
    st.subheader("Nova Conciliação")

    estabelecimentos = obter_estabelecimentos()

    if not estabelecimentos:
        st.warning(
            "Nenhum estabelecimento ativo foi encontrado no Supabase."
        )
        return

    codigos_estabelecimentos = [
        str(item["codigo"])
        for item in estabelecimentos
    ]

    col1, col2, col3 = st.columns(3)

    with col1:
        estabelecimento = st.selectbox(
            "Estabelecimento",
            codigos_estabelecimentos,
            index=0,
            key="nova_estabelecimento",
        )

    with col2:
        periodo = st.text_input(
            "Período (ex: 07/2026)",
            value=datetime.now().strftime("%m/%Y"),
            key="nova_periodo",
        )

    with col3:
        tolerancia_texto = st.text_input(
            "Tolerância (R$)",
            value="0,02",
            key="nova_tolerancia",
            help=(
                "Use o formato brasileiro. "
                "Exemplos: 0,02 ou 1.234,56"
            ),
        )

        tolerancia = parse_numero_br(
            tolerancia_texto
        )

        if tolerancia is None or tolerancia < 0:
            st.error(
                "Informe uma tolerância válida. "
                "Exemplo: 0,02"
            )
            return

    st.markdown(
        "### Upload das planilhas"
    )

    c1, c2 = st.columns(2)

    with c1:
        file_fin = st.file_uploader(
            "Planilha **Financeiro** (Fiscal)",
            type=["xlsx", "xls"],
            key="fin",
            help=(
                "Deve conter: Título, "
                "Valor Movto, Dat Transac, Série"
            ),
        )

    with c2:
        file_rec = st.file_uploader(
            "Planilha **Recebimentos**",
            type=["xlsx", "xls"],
            key="rec",
            help=(
                "Deve conter: Documento, "
                "Crédito, Data Trans, Série"
            ),
        )

    observacao = st.text_input(
        "Observação (opcional)",
        placeholder=(
            "Ex: Conciliação mensal agosto/2026"
        ),
        key="nova_observacao",
    )

    if st.button(
        "🚀 Executar Conciliação",
        type="primary",
        use_container_width=True,
        key="executar_conciliacao",
    ):
        if not file_fin or not file_rec:
            st.error(
                "Envie as duas planilhas para continuar."
            )
            return

        with st.spinner(
            "Processando planilhas..."
        ):
            storage_paths = []

            try:
                # ==================================================
                # LEITURA E PREPARAÇÃO
                # ==================================================

                df_fin = preparar_financeiro(
                    _ler_excel_robusto(
                        file_fin
                    )
                )

                xls_rec = pd.ExcelFile(
                    file_rec
                )

                sheet_rec = (
                    xls_rec.sheet_names[0]
                )

                for sheet_name in (
                    xls_rec.sheet_names
                ):
                    if (
                        "ce0403"
                        in sheet_name.lower()
                        or
                        "receb"
                        in sheet_name.lower()
                    ):
                        sheet_rec = sheet_name
                        break

                df_rec = preparar_recebimento(
                    _ler_excel_robusto(
                        file_rec,
                        sheet_name=sheet_rec,
                    )
                )

                # ==================================================
                # QUALIDADE DOS ARQUIVOS / PRÉ-CONFERÊNCIA
                # ==================================================

                fin_linhas = len(df_fin)
                rec_linhas = len(df_rec)

                fin_chaves = (
                    df_fin["Chave"].nunique()
                )

                rec_chaves = (
                    df_rec["Chave"].nunique()
                )

                fin_datas_invalidas = int(
                    df_fin["Data"].isna().sum()
                )

                rec_datas_invalidas = int(
                    df_rec["Data"].isna().sum()
                )

                st.markdown(
                    "### 🔎 Resumo dos arquivos processados"
                )

                q1, q2, q3, q4 = st.columns(4)

                q1.metric(
                    "Linhas Financeiro",
                    fin_linhas,
                )

                q2.metric(
                    "Linhas Recebimento",
                    rec_linhas,
                )

                q3.metric(
                    "Chaves Financeiro",
                    fin_chaves,
                )

                q4.metric(
                    "Chaves Recebimento",
                    rec_chaves,
                )

                if (
                    fin_datas_invalidas
                    or rec_datas_invalidas
                ):
                    st.warning(
                        "Foram encontradas datas inválidas ou vazias: "
                        f"Financeiro: {fin_datas_invalidas} • "
                        f"Recebimento: {rec_datas_invalidas}."
                    )
                else:
                    st.success(
                        "Datas válidas em todas as linhas processadas."
                    )

                # ==================================================
                # MOTOR
                # ==================================================

                resultado = conciliar(
                    df_fin,
                    df_rec,
                    tolerancia=tolerancia,
                )

                # ==================================================
                # STORAGE
                # ==================================================

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )

                nome_fin = _sanitizar_nome_arquivo(
                    file_fin.name
                )

                nome_rec = _sanitizar_nome_arquivo(
                    file_rec.name
                )

                periodo_storage = (
                    _periodo_storage(
                        periodo
                    )
                )

                caminho_fin = (
                    f"{estabelecimento}/"
                    f"{periodo_storage}/"
                    f"financeiro/"
                    f"{timestamp}_"
                    f"{nome_fin}"
                )

                caminho_rec = (
                    f"{estabelecimento}/"
                    f"{periodo_storage}/"
                    f"recebimento/"
                    f"{timestamp}_"
                    f"{nome_rec}"
                )

                mime_excel = (
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )

                _upload_storage(
                    file_fin.getvalue(),
                    caminho_fin,
                    mime_excel,
                )

                storage_paths.append(
                    caminho_fin
                )

                try:
                    _upload_storage(
                        file_rec.getvalue(),
                        caminho_rec,
                        mime_excel,
                    )
                    storage_paths.append(
                        caminho_rec
                    )
                except Exception:
                    try:
                        _remover_storage(
                            [caminho_fin]
                        )
                    except Exception:
                        pass
                    raise

                # ==================================================
                # METADADOS
                # ==================================================

                estabelecimento_id = (
                    obter_estabelecimento_id(
                        estabelecimento
                    )
                )

                meta = {
                    "estabelecimento_id":
                        estabelecimento_id,

                    "periodo":
                        periodo,

                    "data_execucao":
                        datetime.now().astimezone().isoformat(timespec="seconds"),

                    "total_financeiro":
                        resultado[
                            "total_financeiro"
                        ],

                    "total_recebimento":
                        resultado[
                            "total_recebimento"
                        ],

                    "diferenca":
                        resultado[
                            "diferenca"
                        ],

                    "qtd_docs_financeiro":
                        resultado[
                            "qtd_docs_financeiro"
                        ],

                    "qtd_docs_recebimento":
                        resultado[
                            "qtd_docs_recebimento"
                        ],

                    "qtd_divergencias":
                        resultado[
                            "qtd_divergencias"
                        ],

                    "qtd_so_financeiro":
                        resultado[
                            "qtd_so_financeiro"
                        ],

                    "qtd_so_recebimento":
                        resultado[
                            "qtd_so_recebimento"
                        ],

                    "qtd_valor_diferente":
                        resultado[
                            "qtd_valor_diferente"
                        ],

                    "status":
                        (
                            "OK"
                            if resultado[
                                "qtd_divergencias"
                            ] == 0
                            else "COM DIVERGÊNCIAS"
                        ),

                    "arquivo_financeiro":
                        caminho_fin,

                    "arquivo_recebimento":
                        caminho_rec,

                    "observacao":
                        observacao,
                }

                # ==================================================
                # BANCO
                # ==================================================

                conc_id = (
                    salvar_conciliacao(
                        meta,
                        resultado[
                            "divergencias"
                        ],
                    )
                )

                st.success(
                    "Conciliação salva no histórico "
                    f"(ID #{conc_id})"
                )

                st.markdown("---")

                st.subheader(
                    "📊 Resultado da Conciliação"
                )

                m1, m2, m3, m4 = st.columns(4)

                m1.metric(
                    "Total Financeiro",
                    formatar_moeda_br(
                        resultado[
                            "total_financeiro"
                        ]
                    ),
                )

                m2.metric(
                    "Total Recebimento",
                    formatar_moeda_br(
                        resultado[
                            "total_recebimento"
                        ]
                    ),
                )

                m3.metric(
                    "Diferença",
                    formatar_moeda_br(
                        resultado[
                            "diferenca"
                        ]
                    ),
                    delta_color=(
                        "inverse"
                        if abs(
                            resultado[
                                "diferenca"
                            ]
                        ) > tolerancia
                        else "off"
                    ),
                )

                m4.metric(
                    "Divergências",
                    resultado[
                        "qtd_divergencias"
                    ],
                )

                c1, c2, c3, c4 = st.columns(4)

                c1.metric(
                    "Docs Financeiro",
                    resultado[
                        "qtd_docs_financeiro"
                    ],
                )

                c2.metric(
                    "Docs Recebimento",
                    resultado[
                        "qtd_docs_recebimento"
                    ],
                )

                c3.metric(
                    "Só no Financeiro",
                    resultado[
                        "qtd_so_financeiro"
                    ],
                )

                c4.metric(
                    "Só no Recebimento",
                    resultado[
                        "qtd_so_recebimento"
                    ],
                )

                if resultado[
                    "qtd_divergencias"
                ] > 0:

                    st.markdown(
                        "### ⚠️ Divergências encontradas"
                    )

                    st.markdown(
                        "🔴 **Só no Financeiro** "
                        "&nbsp;&nbsp; "
                        "🔵 **Só no Recebimento** "
                        "&nbsp;&nbsp; "
                        "🟡 **Valor Diferente**"
                    )

                    div_show = (
                        resultado[
                            "divergencias"
                        ].copy()
                    )

                    for column in [
                        "Data Financeiro",
                        "Data Recebimento",
                    ]:
                        if column in div_show.columns:
                            div_show[
                                column
                            ] = (
                                pd.to_datetime(
                                    div_show[
                                        column
                                    ],
                                    errors="coerce",
                                )
                                .dt.strftime(
                                    "%d/%m/%Y"
                                )
                            )

                    for column in [
                        "Valor Financeiro",
                        "Valor Recebimento",
                        "Diferença",
                    ]:
                        if column in div_show.columns:
                            div_show[
                                column
                            ] = (
                                div_show[
                                    column
                                ].apply(
                                    lambda value:
                                    (
                                        formatar_moeda_br(
                                            value
                                        )
                                        if pd.notna(value)
                                        else ""
                                    )
                                )
                            )

                    st.dataframe(
                        estilo_divergencias(
                            div_show
                        ),
                        use_container_width=True,
                        hide_index=True,
                        height=min(
                            420,
                            48
                            + len(
                                div_show
                            ) * 36,
                        ),
                    )

                    buffer = io.BytesIO()

                    with pd.ExcelWriter(
                        buffer,
                        engine="openpyxl",
                    ) as writer:
                        resultado[
                            "divergencias"
                        ].to_excel(
                            writer,
                            index=False,
                            sheet_name="Divergencias",
                        )

                    st.download_button(
                        "⬇️ Baixar divergências (Excel)",
                        data=buffer.getvalue(),
                        file_name=(
                            f"divergencias_"
                            f"{estabelecimento}_"
                            f"{periodo.replace('/', '-')}.xlsx"
                        ),
                        mime=mime_excel,
                    )

                else:
                    st.success(
                        "✅ Nenhuma divergência encontrada! "
                        "Contas batem perfeitamente."
                    )

                if (
                    resultado[
                        "qtd_datas_diferentes_informativas"
                    ] > 0
                ):
                    with st.expander(
                        "📅 Ver documentos com diferença de data "
                        f"({resultado['qtd_datas_diferentes_informativas']})"
                    ):
                        data_show = (
                            resultado[
                                "informacoes_data"
                            ].copy()
                        )

                        for column in [
                            "Data Financeiro",
                            "Data Recebimento",
                        ]:
                            if column in data_show.columns:
                                data_show[
                                    column
                                ] = (
                                    pd.to_datetime(
                                        data_show[
                                            column
                                        ],
                                        errors="coerce",
                                    )
                                    .dt.strftime(
                                        "%d/%m/%Y"
                                    )
                                )

                        if "Valor_Financeiro" in data_show.columns:
                            data_show[
                                "Valor Financeiro"
                            ] = data_show[
                                "Valor_Financeiro"
                            ].apply(
                                formatar_moeda_br
                            )
                            data_show = data_show.drop(
                                columns=[
                                    "Valor_Financeiro"
                                ]
                            )

                        if "Valor_Recebimento" in data_show.columns:
                            data_show[
                                "Valor Recebimento"
                            ] = data_show[
                                "Valor_Recebimento"
                            ].apply(
                                formatar_moeda_br
                            )
                            data_show = data_show.drop(
                                columns=[
                                    "Valor_Recebimento"
                                ]
                            )

                        if "Diferença" in data_show.columns:
                            data_show[
                                "Diferença"
                            ] = data_show[
                                "Diferença"
                            ].apply(
                                formatar_moeda_br
                            )

                        st.dataframe(
                            data_show,
                            use_container_width=True,
                            hide_index=True,
                        )

                st.info(
                    "🔑 A chave de comparação é "
                    "**Documento + Série**. "
                    "Documentos com a mesma numeração e séries "
                    "diferentes são tratados como itens distintos. "
                    "Diferenças de data são apenas informativas "
                    "e não geram divergência."
                )

            except Exception as error:
                # Se o registro ainda não foi persistido, remover uploads
                if storage_paths:
                    try:
                        _remover_storage(
                            storage_paths
                        )
                    except Exception:
                        pass

                st.error(
                    f"Erro ao processar: {error}"
                )
                st.exception(error)



# ============================================================
# HISTÓRICO
# ============================================================

def exibir_historico():
    st.subheader(
        "📜 Histórico de Conciliações"
    )

    estabelecimentos = obter_codigos_estabelecimentos()

    # ========================================================
    # FILTROS
    # ========================================================

    f1, f2, f3 = st.columns(3)

    with f1:
        filtro_est = st.selectbox(
            "Estabelecimento",
            ["Todos"] + estabelecimentos,
            key="historico_estabelecimento",
        )

    with f2:
        filtro_status = st.selectbox(
            "Status",
            [
                "Todos",
                "OK",
                "COM DIVERGÊNCIAS",
            ],
            key="historico_status",
        )

    with f3:
        busca = st.text_input(
            "🔎 Buscar ID, documento, chave ou observação",
            placeholder=(
                "Ex.: 127, 123456, 123456|1"
            ),
            key="historico_busca",
        )

    f4, f5 = st.columns(2)

    with f4:
        periodo_inicio = st.date_input(
            "Período inicial",
            value=None,
            key="historico_periodo_inicio",
        )

    with f5:
        periodo_fim = st.date_input(
            "Período final",
            value=None,
            key="historico_periodo_fim",
        )

    if (
        periodo_inicio
        and periodo_fim
        and periodo_inicio > periodo_fim
    ):
        st.warning(
            "O período inicial não pode ser maior que o período final."
        )
        return

    hist = consultar_historico_avancado(
        estabelecimento=filtro_est,
        status=filtro_status,
        busca=busca,
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
    )

    # ========================================================
    # RESUMO DOS FILTROS
    # ========================================================

    if hist.empty:
        st.info(
            "Nenhuma conciliação encontrada "
            "com os filtros informados."
        )
        return

    total_conciliacoes = len(hist)

    total_com_divergencias = int(
        (
            hist["status"]
            == "COM DIVERGÊNCIAS"
        ).sum()
    )

    total_divergencias = int(
        hist[
            "qtd_divergencias"
        ]
        .fillna(0)
        .sum()
    )

    diferenca_acumulada = float(
        hist[
            "diferenca"
        ]
        .fillna(0)
        .sum()
    )

    r1, r2, r3, r4 = st.columns(4)

    r1.metric(
        "Conciliações encontradas",
        total_conciliacoes,
    )

    r2.metric(
        "Com divergências",
        total_com_divergencias,
    )

    r3.metric(
        "Divergências",
        total_divergencias,
    )

    r4.metric(
        "Diferença acumulada",
        formatar_moeda_br(
            diferenca_acumulada
        ),
    )

    st.markdown(
        "### Resultados"
    )

    # ========================================================
    # TABELA
    # ========================================================

    hist_view = hist.copy()

    hist_view[
        "data_execucao"
    ] = (
        pd.to_datetime(
            hist_view[
                "data_execucao"
            ],
            errors="coerce",
        )
        .dt.strftime(
            "%d/%m/%Y %H:%M"
        )
    )

    hist_view[
        "total_financeiro"
    ] = hist_view[
        "total_financeiro"
    ].apply(
        formatar_moeda_br
    )

    hist_view[
        "total_recebimento"
    ] = hist_view[
        "total_recebimento"
    ].apply(
        formatar_moeda_br
    )

    hist_view[
        "diferenca"
    ] = hist_view[
        "diferenca"
    ].apply(
        formatar_moeda_br
    )

    cols_show = [
        "id",
        "estabelecimento",
        "periodo",
        "data_execucao",
        "total_financeiro",
        "total_recebimento",
        "diferenca",
        "qtd_divergencias",
        "status",
        "observacao",
    ]

    tabela = (
        hist_view[
            cols_show
        ].rename(
            columns={
                "id": "ID",
                "estabelecimento":
                    "Estabelecimento",
                "periodo":
                    "Período",
                "data_execucao":
                    "Executado em",
                "total_financeiro":
                    "Total Financeiro",
                "total_recebimento":
                    "Total Recebimento",
                "diferenca":
                    "Diferença",
                "qtd_divergencias":
                    "Divergências",
                "status":
                    "Status",
                "observacao":
                    "Observação",
            }
        )
    )

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
    )

    # ========================================================
    # DETALHES
    # ========================================================

    st.markdown(
        "### Detalhes de uma conciliação"
    )

    ids = (
        hist[
            "id"
        ].tolist()
    )

    def formatar_conciliacao(
        conciliacao_id
    ):
        linha = (
            hist[
                hist[
                    "id"
                ] == conciliacao_id
            ]
            .iloc[0]
        )

        status = linha[
            "status"
        ]

        simbolo = (
            "🟢"
            if status == "OK"
            else "🔴"
        )

        return (
            f"#{conciliacao_id} — "
            f"{linha['estabelecimento']} — "
            f"{linha['periodo']} — "
            f"{simbolo} {status}"
        )

    selected_id = st.selectbox(
        "Selecione o ID",
        ids,
        format_func=(
            formatar_conciliacao
        ),
        key="historico_selected_id",
    )

    if selected_id:
        row = (
            hist[
                hist[
                    "id"
                ] == selected_id
            ]
            .iloc[0]
        )

        d1, d2, d3, d4 = st.columns(4)

        d1.metric(
            "Estabelecimento",
            row[
                "estabelecimento"
            ],
        )

        d2.metric(
            "Período",
            row[
                "periodo"
            ],
        )

        d3.metric(
            "Status",
            row[
                "status"
            ],
        )

        d4.metric(
            "Divergências",
            int(
                row[
                    "qtd_divergencias"
                ]
                or 0
            ),
        )

        st.markdown(
            f"**Executado em:** "
            f"{row['data_execucao']}  \n"
            f"**Observação:** "
            f"{row['observacao'] or '-'}"
        )

        # ====================================================
        # EXCLUSÃO SEGURA
        # ====================================================

        st.markdown(
            "### Ações"
        )

        with st.expander(
            "🗑️ Excluir esta conciliação",
            expanded=False,
        ):
            st.warning(
                f"A exclusão da conciliação "
                f"#{selected_id} é permanente. "
                "Serão removidas a conciliação, "
                "todas as divergências vinculadas "
                "e os arquivos Excel associados."
            )

            with st.form(
                f"form_exclusao_{selected_id}",
                clear_on_submit=True,
            ):
                confirmar_exclusao = (
                    st.checkbox(
                        "Confirmo que desejo excluir "
                        "esta conciliação permanentemente.",
                        key=(
                            f"confirmar_exclusao_"
                            f"{selected_id}"
                        ),
                    )
                )

                excluir = (
                    st.form_submit_button(
                        "🗑️ Excluir definitivamente",
                        type="primary",
                        use_container_width=True,
                    )
                )

            if excluir:
                if not confirmar_exclusao:
                    st.error(
                        "Marque a confirmação "
                        "antes de excluir."
                    )
                else:
                    try:
                        sucesso, avisos = (
                            excluir_conciliacao(
                                selected_id
                            )
                        )

                        if sucesso:
                            for aviso in avisos:
                                st.warning(
                                    aviso
                                )

                            st.success(
                                f"Conciliação #{selected_id} "
                                "excluída com sucesso."
                            )

                            st.rerun()

                        else:
                            st.error(
                                f"A conciliação "
                                f"#{selected_id} "
                                "não foi encontrada."
                            )

                    except Exception as error:
                        st.error(
                            "Não foi possível excluir "
                            f"a conciliação #{selected_id}: "
                            f"{error}"
                        )

        # ====================================================
        # DIVERGÊNCIAS
        # ====================================================

        divs = carregar_divergencias(
            selected_id
        )

        if divs.empty:
            st.success(
                "Sem divergências nesta conciliação."
            )
            return

        st.markdown(
            f"**{len(divs)} divergência(s):**"
        )

        for column in [
            "data_financeiro",
            "data_recebimento",
        ]:
            if column in divs.columns:
                divs[
                    column
                ] = (
                    pd.to_datetime(
                        divs[
                            column
                        ],
                        errors="coerce",
                    )
                    .dt.strftime(
                        "%d/%m/%Y"
                    )
                )

        for column in [
            "valor_financeiro",
            "valor_recebimento",
            "diferenca",
        ]:
            if column in divs.columns:
                divs[
                    column
                ] = divs[
                    column
                ].apply(
                    formatar_moeda_br
                )

        st.dataframe(
            divs.drop(
                columns=[
                    "id",
                    "conciliacao_id",
                ],
                errors="ignore",
            ),
            use_container_width=True,
            hide_index=True,
        )

        buffer = io.BytesIO()

        with pd.ExcelWriter(
            buffer,
            engine="openpyxl",
        ) as writer:
            divs.to_excel(
                writer,
                index=False,
                sheet_name="Divergencias",
            )

        st.download_button(
            "⬇️ Baixar divergências desta conciliação",
            data=buffer.getvalue(),
            file_name=(
                "historico_divergencias_"
                f"id{selected_id}.xlsx"
            ),
            mime=(
                "application/"
                "vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )



# ============================================================
# APLICAÇÃO
# ============================================================

def main():
    try:
        st.title(
            "⚖️ Conciliação Transitória de Fornecedores"
        )

        st.caption(
            "Conta 91001001 • "
            "Estabelecimentos configurados no Supabase"
        )

        with st.sidebar:
            st.header(
                "Navegação"
            )

            pagina = st.radio(
                "Ir para",
                [
                    "Dashboard",
                    "Nova Conciliação",
                    "Histórico",
                ],
                index=0,
                label_visibility="collapsed",
            )

            st.divider()

            st.markdown(
                "**Conta contábil**"
            )

            st.markdown(
                """
                <div class="conta-contabil">
                    <div class="conta-numero">
                        91001001
                    </div>
                    <div class="conta-descricao">
                        TRANSITORIA DE FORNECEDORES
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                "---"
            )

            st.caption(
                "Versão 8.4 • Supabase"
            )

        if pagina == "Dashboard":
            exibir_dashboard()

        elif pagina == "Nova Conciliação":
            exibir_nova_conciliacao()

        else:
            exibir_historico()

    except Exception as error:
        st.error(
            f"Erro de inicialização: {error}"
        )
        st.exception(error)


if __name__ == "__main__":
    main()
