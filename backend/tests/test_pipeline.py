"""Pipeline, validação contra alucinação, revisão humana e integração com o n8n."""
import json
from types import SimpleNamespace

import pytest

from app.pipeline.conteudo import PECAS, carregar_prompt, montar_pedido, rascunho_deterministico, validar
from app.pipeline.processar import processar
from app.search.engine import Fala

FALAS = [Fala(0, "Olá, sejam bem-vindos."), Fala(20, "O medo de mudar costuma ser maior antes da decisão do que depois dela."),
         Fala(70, "Projetos pequenos mostram se você gosta do dia a dia, não só da ideia."), Fala(130, "Até a próxima.")]
TEXTO = " ".join(f.texto for f in FALAS)


def _conteudo(**extra):
    base = {k: "x" for k in PECAS} | {"capitulos": [], "cortes": [], "citacoes": [], "newsletter": {"assunto": "a", "corpo": "b"}}
    return base | extra


def test_prompt_versionado_e_lido_do_repositorio():
    system, user = carregar_prompt("v1")
    assert "Use SOMENTE o que está na transcrição" in system and "{{transcricao_com_timestamps}}" in user
    s, u = montar_pedido("Ep teste", "9", "Ninguém", FALAS, "Tom acolhedor")
    assert "Tom acolhedor" in s and "[00:20] O medo de mudar" in u


def test_validacao_aponta_citacao_inventada_e_corte_invalido():
    alertas = validar(_conteudo(citacoes=["O medo de mudar costuma ser maior antes da decisão", "Frase que ninguém disse no episódio"],
                                cortes=[{"inicio": "00:20", "fim": "00:10"}, {"inicio": "00:20", "fim": "05:00"},
                                        {"inicio": "00:20", "fim": "00:25"}]), TEXTO, 140)
    texto = " | ".join(alertas)
    assert "ninguém disse" in texto and "medo de mudar" not in texto
    assert "horário inválido" in texto and "passa do fim" in texto and "duração fora do ideal" in texto


def test_validacao_exige_todas_as_pecas():
    with pytest.raises(ValueError, match="Campos ausentes"):
        validar({"resumo_curto": "x"}, TEXTO, 140)


def test_rascunho_sem_llm_so_usa_frases_da_transcricao():
    r = rascunho_deterministico("Ep", FALAS, 140)
    assert set(PECAS) <= set(r)
    assert all(c in TEXTO for c in r["citacoes"])
    assert validar(r, TEXTO, 140) == r["alertas_revisao"]  # nenhuma citação ou corte inválido


def test_upload_de_transcricao_processa_e_entra_em_revisao(client):
    txt = "titulo: x\nepisodio: 99\n---\n" + "\n".join(f"[{f.inicio // 60:02d}:{f.inicio % 60:02d}] {f.texto}" for f in FALAS)
    r = client.post("/api/episodios", data={"titulo": "Episódio de teste", "numero": "99"},
                    files={"arquivo": ("ep99.txt", txt.encode(), "text/plain")})
    assert r.status_code == 201
    ep = client.get(f"/api/episodios/{r.json()['id']}").json()
    assert ep["status"] == "revisao" and len(ep["segmentos"]) == 4
    assert [e["status"] for e in ep["etapas"]] == ["pulada", "ok", "ok", "ok"]
    assert ep["pacote"]["motor"] == "rascunho_deterministico"
    assert client.get("/api/busca", params={"q": "projetos pequenos mostram se você gosta"}).json()["resultados"][0]["episodio"] == "99"


def test_audio_sem_chave_do_whisper_e_recusado(client):
    r = client.post("/api/episodios", data={"titulo": "Áudio", "numero": "100"}, files={"arquivo": ("ep.mp3", b"ID3", "audio/mpeg")})
    assert r.status_code == 422 and "chave da OpenAI" in r.json()["detail"]


def test_revisao_humana_publica_so_quando_todas_as_pecas_forem_revisadas(client):
    ep = client.get("/api/episodios/1").json()
    pecas = ep["pacote"]["pecas"]
    client.post(f"/api/pecas/{pecas[0]['id']}", json={"acao": "editar", "conteudo": "Resumo reescrito pela equipe."})
    for p in pecas[1:-1]:
        assert client.post(f"/api/pecas/{p['id']}", json={"acao": "aprovar"}).json()["status"] == "revisao"
    final = client.post(f"/api/pecas/{pecas[-1]['id']}", json={"acao": "rejeitar"}).json()
    assert final["status"] == "publicado" and final["pacote"]["pecas"][0]["editada"]


def test_pipeline_com_claude_simulado(client):
    conteudo = rascunho_deterministico("Ep", FALAS, 140) | {"alertas_revisao": [], "citacoes": ["Uma citação inventada pelo modelo"]}

    class Claude:
        messages = None

        def __init__(self):
            self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(
                content=[SimpleNamespace(type="text", text="```json\n" + json.dumps(conteudo, ensure_ascii=False) + "\n```")],
                usage=SimpleNamespace(input_tokens=1200, output_tokens=800)))

    txt = "\n".join(f"[{f.inicio // 60:02d}:{f.inicio % 60:02d}] {f.texto}" for f in FALAS)
    eid = client.post("/api/episodios", data={"titulo": "Com Claude", "numero": "101", "transcricao": txt}).json()["id"]
    processar(eid, cliente_claude=Claude())
    p = client.get(f"/api/episodios/{eid}").json()["pacote"]
    assert p["motor"] == "claude" and p["tokens_entrada"] == 1200
    assert any("inventada" in a for a in p["alertas"])


def test_webhook_do_n8n(client):
    corpo = {"titulo": "Do n8n", "numero": "102", "transcricao_com_timestamps": "[00:00] Olá\n[00:40] Tudo certo por aqui, obrigado.",
             "conteudo": _conteudo(citacoes=["Tudo certo por aqui"]), "tokens_entrada": 10}
    assert client.post("/api/integracoes/n8n/episodios", json=corpo).status_code == 401
    assert client.post("/api/integracoes/n8n/episodios", json=corpo, headers={"X-Webhook-Token": "errado"}).status_code == 401
    r = client.post("/api/integracoes/n8n/episodios", json=corpo, headers={"X-Webhook-Token": "segredo-de-teste"})
    assert r.status_code == 201 and r.json()["alertas"] == []
    incompleto = corpo | {"conteudo": {"resumo_curto": "x"}}
    assert client.post("/api/integracoes/n8n/episodios", json=incompleto, headers={"X-Webhook-Token": "segredo-de-teste"}).status_code == 422
