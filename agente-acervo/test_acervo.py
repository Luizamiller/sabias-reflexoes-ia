"""Testes do agente — rodam sem chave de API (o modelo é simulado).

    pytest -q
"""
from types import SimpleNamespace

from acervo import Acervo, responder, RESPOSTA_SEM_FONTE


class ClienteFalso:
    """Simula a API do Claude e guarda o que foi enviado."""
    def __init__(self):
        self.enviado = None
        self.messages = self

    def create(self, **kwargs):
        self.enviado = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Resposta simulada (Ep. 1 – 01:02).")])


acervo = Acervo()


def test_carrega_episodios_de_exemplo():
    assert len(acervo.episodios) >= 2
    assert all(t.inicio for t in acervo.trechos)


def test_busca_encontra_o_episodio_certo():
    achados = acervo.buscar("medo de mudar de carreira")
    assert achados, "deveria achar algo"
    assert achados[0][0].episodio == "1"

    achados = acervo.buscar("culpa de descansar")
    assert achados[0][0].episodio == "2"


def test_busca_ignora_acentos():
    assert acervo.buscar("preguica")[0][0].episodio == "2"


def test_nao_chama_modelo_quando_assunto_nao_existe():
    cliente = ClienteFalso()
    r = responder(acervo, "receita de bolo de cenoura com cobertura", cliente=cliente)
    assert r["resposta"] == RESPOSTA_SEM_FONTE
    assert r["chamou_modelo"] is False
    assert cliente.enviado is None


def test_envia_trechos_com_fonte_para_o_modelo():
    cliente = ClienteFalso()
    r = responder(acervo, "como testar uma nova área antes de mudar?", cliente=cliente)
    assert r["chamou_modelo"] is True
    conteudo = cliente.enviado["messages"][0]["content"]
    assert 'fonte="Ep. 1 –' in conteudo
    assert "SOMENTE" in cliente.enviado["system"]
