"""Busca e assistente — inclui os testes do agente original (agente-acervo/test_acervo.py), portados."""
import json
from types import SimpleNamespace

from app.db import SessionLocal
from app.eval import carregar_exemplos, relatorio
from app.search.engine import Indice
from app.search.service import RESPOSTA_SEM_FONTE, responder_stream, verificar_citacoes

ORIGINAIS = carregar_exemplos({"1", "2"})
acervo = Indice(ORIGINAIS, "v2")


class ClienteFalso:
    """Simula a API do Claude (sem streaming) e guarda o que foi enviado."""

    def __init__(self, texto="Resposta simulada (Ep. 1 – 01:02)."):
        self.enviado, self.texto = None, texto
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.enviado = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.texto)])


# ---------- portados do projeto original ----------

def test_carrega_episodios_de_exemplo():
    assert len(ORIGINAIS) >= 2 and all(t.inicio for t in acervo.trechos)


def test_busca_encontra_o_episodio_certo():
    assert acervo.buscar("medo de mudar de carreira")[0].trecho.episodio == "1"
    assert acervo.buscar("culpa de descansar")[0].trecho.episodio == "2"


def test_busca_ignora_acentos():
    assert acervo.buscar("preguica")[0].trecho.episodio == "2"


def test_busca_encontra_variacoes_da_palavra():
    assert any(r.trecho.episodio == "2" for r in acervo.buscar("me sinto culpada quando paro"))


def test_trechos_guardam_todos_os_minutos():
    t = acervo.trechos[0]
    assert t.minutos[0] == t.inicio and len(t.minutos) >= 2


def test_nao_chama_modelo_quando_assunto_nao_existe():
    cliente = ClienteFalso()
    with SessionLocal() as db:
        eventos = list(responder_stream(db, "receita de bolo de cenoura", cliente=cliente))
    assert eventos[0]["fontes"] == [] and eventos[-1]["chamou_modelo"] is False
    assert eventos[1]["texto"] == RESPOSTA_SEM_FONTE and cliente.enviado is None


def test_envia_trechos_com_fonte_para_o_modelo():
    cliente = ClienteFalso()
    with SessionLocal() as db:
        fim = list(responder_stream(db, "como testar uma nova área antes de mudar?", cliente=cliente))[-1]
    assert fim["chamou_modelo"] is True
    assert 'fonte="Ep. 1 –' in cliente.enviado["messages"][0]["content"] and "SOMENTE" in cliente.enviado["system"]


# ---------- novos ----------

def test_numeros_originais_da_avaliacao_se_mantem():
    r = relatorio()["original (2 episódios, 9 perguntas)"]
    assert (r["v1"]["acertos"], r["v2"]["acertos"]) == (7, 8)  # 78% e 89%, como no README original
    assert r["v3"]["acertos"] >= r["v2"]["acertos"]


def test_citacao_inventada_e_detectada():
    cliente = ClienteFalso("Testar em projetos pequenos ajuda (Ep. 1 – 01:20). Também vale viajar (Ep. 9 – 10:00).")
    with SessionLocal() as db:
        fim = list(responder_stream(db, "testar a nova área antes de pedir demissão", cliente=cliente))[-1]
    assert fim["citacoes_invalidas"] == ["Ep. 9 – 10:00"]


def test_sem_modelo_responde_de_forma_extrativa_com_citacoes():
    with SessionLocal() as db:
        eventos = list(responder_stream(db, "culpa por gastar dinheiro com algo caro"))
    assert eventos[-1]["motor"] == "extrativo" and "(Ep. 3 –" in eventos[1]["texto"]


def test_verificar_citacoes_aceita_qualquer_fala_do_trecho():
    r = acervo.buscar("conversar com quem já trabalha na área")
    minuto = r[0].trecho.minutos[-1]
    assert verificar_citacoes(f"texto (Ep. 1 – {minuto})", r) == []


def test_assistente_via_sse(client):
    with client.stream("POST", "/api/assistente", json={"pergunta": "como lidar com elogio sem se justificar"}) as resp:
        eventos = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    assert eventos[0]["tipo"] == "fontes" and eventos[0]["fontes"][0]["episodio"] == "4"
    assert eventos[-1]["tipo"] == "fim" and eventos[-1]["pergunta_id"]
    assert client.post(f"/api/perguntas/{eventos[-1]['pergunta_id']}/avaliacao", json={"util": True}).json()["ok"]
