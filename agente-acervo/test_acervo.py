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
    # Limitação conhecida da v2: frases longas fora do tema podem passar do limiar por acaso
    # (ex.: "...com cobertura"). Nesses casos o Claude é a rede de segurança: o SYSTEM manda
    # dizer que o acervo não trata do assunto. Ver "Limitações" no README.
    r = responder(acervo, "receita de bolo de cenoura", cliente=cliente)
    assert r["resposta"] == RESPOSTA_SEM_FONTE
    assert r["chamou_modelo"] is False
    assert cliente.enviado is None


def test_busca_encontra_variacoes_da_palavra():
    # "culpada" (pergunta) precisa casar com "culpa" (episódio 2)
    achados = acervo.buscar("me sinto culpada quando paro")
    assert any(t.episodio == "2" for t, _ in achados)


def test_trechos_guardam_todos_os_minutos():
    t = acervo.trechos[0]
    assert t.minutos[0] == t.inicio and len(t.minutos) >= 2


class ClienteReescrita(ClienteFalso):
    """1ª chamada: reescrita da pergunta. 2ª chamada: resposta final."""
    def __init__(self):
        super().__init__()
        self.chamadas = []

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        if len(self.chamadas) == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="largar o emprego e testar projetos pequenos")])
        return super().create(**kwargs)


def test_reescrita_da_pergunta_e_usada_na_busca():
    cliente = ClienteReescrita()
    r = responder(acervo, "devo pedir demissão já?", cliente=cliente, reescrever=True)
    assert len(cliente.chamadas) == 2
    assert "Pergunta: devo pedir demissão já?" in cliente.chamadas[0]["messages"][0]["content"]
    assert any(t.episodio == "1" for t in r["fontes"])


def test_envia_trechos_com_fonte_para_o_modelo():
    cliente = ClienteFalso()
    r = responder(acervo, "como testar uma nova área antes de mudar?", cliente=cliente)
    assert r["chamou_modelo"] is True
    conteudo = cliente.enviado["messages"][0]["content"]
    assert 'fonte="Ep. 1 –' in conteudo
    assert "SOMENTE" in cliente.enviado["system"]
