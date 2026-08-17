import streamlit as st
from supabase import create_client


st.title("Teste Supabase")

try:
    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )

    resposta = (
        supabase
        .table("estabelecimentos")
        .select("codigo,nome,ativo")
        .order("codigo")
        .execute()
    )

    st.success("Conexão com o Supabase funcionando!")

    st.write("Estabelecimentos encontrados:")

    st.dataframe(
        resposta.data,
        use_container_width=True,
        hide_index=True,
    )

except Exception as e:
    st.error("Falha na conexão com o Supabase.")
    st.exception(e)
