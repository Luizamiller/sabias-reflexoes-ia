"""Interface web do agente — rode com:  streamlit run app.py"""
import streamlit as st

from acervo import Acervo, responder

st.set_page_config(page_title="Pergunte ao acervo", page_icon="🎙️")
st.title("🎙️ Pergunte ao acervo")
st.caption("Às Sábias Reflexões · respostas baseadas só nas transcrições, com episódio e minuto")


@st.cache_resource
def carregar():
    return Acervo()


acervo = carregar()

with st.sidebar:
    st.subheader(f"{len(acervo.episodios)} episódios indexados")
    for num, titulo in acervo.episodios:
        st.markdown(f"**Ep. {num}** — {titulo}")
    st.divider()
    st.caption(f"{len(acervo.trechos)} trechos pesquisáveis")

if "historico" not in st.session_state:
    st.session_state.historico = []

for papel, conteudo, fontes in st.session_state.historico:
    with st.chat_message(papel):
        st.markdown(conteudo)
        if fontes:
            with st.expander("Trechos consultados"):
                for t in fontes:
                    st.markdown(f"**{t.citacao}** · _{t.titulo}_\n\n> {t.texto}")

if pergunta := st.chat_input("Ex.: O que já falamos sobre medo de mudar?"):
    st.session_state.historico.append(("user", pergunta, []))
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        with st.spinner("Procurando no acervo..."):
            r = responder(acervo, pergunta)
        st.markdown(r["resposta"])
        if r["fontes"]:
            with st.expander("Trechos consultados"):
                for t in r["fontes"]:
                    st.markdown(f"**{t.citacao}** · _{t.titulo}_\n\n> {t.texto}")
    st.session_state.historico.append(("assistant", r["resposta"], r["fontes"]))
