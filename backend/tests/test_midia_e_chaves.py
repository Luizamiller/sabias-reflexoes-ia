"""Chaves de API pelo painel (cifradas, nunca devolvidas inteiras), upload de vídeo, transcrição em partes,
edição de trecho e exportação."""
import subprocess

import pytest

from app import segredos
from app.db import SessionLocal
from app.models import Configuracao
from app.pipeline import midia as M

CHAVE_OPENAI = "sk-proj-teste-" + "x" * 30 + "abcd"


@pytest.fixture
def sem_chaves():
    db = SessionLocal()
    for p in segredos.PROVEDORES:
        segredos.remover(db, p)
    db.close()
    yield
    db = SessionLocal()
    for p in segredos.PROVEDORES:
        segredos.remover(db, p)
    db.close()


def test_chave_salva_cifrada_e_so_mascara_sai_do_servidor(client, sem_chaves):
    assert client.get("/api/health").json()["integracoes"]["whisper"] is False
    r = client.put("/api/config/chaves/openai", params={"testar": False}, json={"valor": f"  {CHAVE_OPENAI} "})
    assert r.status_code == 200
    info = next(c for c in r.json()["chaves"] if c["provedor"] == "openai")
    assert info["configurada"] and info["origem"] == "painel" and info["mascara"] == "sk-pro…abcd"
    assert CHAVE_OPENAI not in client.get("/api/config/chaves").text
    db = SessionLocal()
    guardado = db.get(Configuracao, "segredo:openai").valor
    db.close()
    assert CHAVE_OPENAI not in guardado and "abcd" not in guardado     # cifrado em repouso
    assert segredos.chave("openai") == CHAVE_OPENAI                      # o servidor consegue usar
    assert client.get("/api/health").json()["integracoes"]["whisper"] is True
    client.delete("/api/config/chaves/openai")
    assert segredos.chave("openai") is None


def test_formato_errado_e_chave_recusada_pelo_provedor(client, sem_chaves, monkeypatch):
    assert "começam com" in client.put("/api/config/chaves/anthropic", json={"valor": "sk-" + "a" * 40}).json()["detail"]
    assert "Anthropic, não da OpenAI" in client.put("/api/config/chaves/openai", json={"valor": "sk-ant-" + "a" * 40}).json()["detail"]
    assert client.put("/api/config/chaves/outro", json={"valor": "x" * 30}).status_code == 422
    monkeypatch.setattr(segredos, "testar", lambda p, v: (False, "O provedor recusou a chave."))
    r = client.put("/api/config/chaves/openai", json={"valor": CHAVE_OPENAI})
    assert r.status_code == 422 and segredos.chave("openai") is None   # não salva chave recusada


def test_teste_da_chave_interpreta_respostas_do_provedor():
    import httpx
    def cliente(status):
        return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status, json={})))
    assert segredos.testar("openai", CHAVE_OPENAI, cliente(200))[0] is True
    assert segredos.testar("anthropic", "sk-ant-x", cliente(401)) == (False, "O provedor recusou a chave (inválida, revogada ou sem permissão).")
    assert segredos.testar("voyage", "pa-x", cliente(429))[0] is True


def test_tipo_da_midia():
    assert M.tipo_da_midia("Ep 12.MP4") == "video" and M.tipo_da_midia("ep.m4a") == "audio"
    assert M.tipo_da_midia("gravacao", "video/quicktime") == "video" and M.tipo_da_midia("x.pdf") is None


ffmpeg = pytest.mark.skipif(M.ffmpeg() is None, reason="ffmpeg indisponível")


def _video(caminho, segundos=5):
    subprocess.run([M.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}",
                    "-f", "lavfi", "-i", f"color=c=black:s=64x64:d={segundos}", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(caminho)], check=True, capture_output=True)
    return caminho


@ffmpeg
def test_video_longo_e_cortado_em_partes_com_horario_somado(tmp_path, monkeypatch):
    monkeypatch.setattr(M.get_settings(), "parte_transcricao_s", 2)
    chamadas = []
    def falso(arq, chave, dica):
        chamadas.append((arq.name, dica))
        return [{"start": 0.4, "text": f" fala {len(chamadas)} "}, {"start": 1.2, "text": " "}]
    passos = []
    falas, total = M.transcrever(_video(tmp_path / "ep.mp4"), "k", "Podcast", passos.append, falso)
    assert len(chamadas) == 3 and 4.5 < total < 5.6
    assert [(f.inicio, f.texto) for f in falas] == [(0, "fala 1"), (2, "fala 2"), (4, "fala 3")]
    assert passos[0] == "Extraindo o áudio" and "Transcrevendo parte 3 de 3" in passos
    assert chamadas[1][1].startswith("Podcast") and "fala 1" in chamadas[1][1]   # continuidade entre partes
    assert not (tmp_path / ".tmp-ep").exists()                                   # temporários apagados


@ffmpeg
def test_upload_de_video_transcreve_indexa_e_exporta(client, sem_chaves, tmp_path, monkeypatch):
    client.put("/api/config/chaves/openai", params={"testar": False}, json={"valor": CHAVE_OPENAI})
    monkeypatch.setattr(M, "whisper", lambda arq, chave, dica: [
        {"start": 0.0, "text": "Bem-vindos ao episódio sobre jardinagem urbana."},
        {"start": 2.5, "text": "Plantar manjericão na janela muda a rotina da casa."}])
    dados = _video(tmp_path / "ep.mp4", 4).read_bytes()
    r = client.post("/api/episodios", data={"titulo": "Jardins na janela", "numero": "201"},
                    files={"arquivo": ("Gravação 201.mp4", dados, "video/mp4")})
    assert r.status_code == 201 and r.json()["midia_tipo"] == "video"
    eid = r.json()["id"]
    ep = client.get(f"/api/episodios/{eid}").json()
    assert ep["status"] == "revisao", ep["erro"]
    assert ep["midia"] == {"tipo": "video", "nome": "Gravação 201.mp4", "bytes": len(dados)}
    assert [s["texto"] for s in ep["segmentos"]][1].startswith("Plantar manjericão") and ep["etapas"][0]["status"] == "ok"

    parcial = client.get(f"/api/episodios/{eid}/midia", headers={"Range": "bytes=0-99"})
    assert parcial.status_code == 206 and len(parcial.content) == 100

    seg = ep["segmentos"][1]
    assert client.patch(f"/api/segmentos/{seg['id']}", json={"texto": "Plantar manjericão e alecrim na janela."}).status_code == 200
    achado = client.get("/api/busca", params={"q": "alecrim na janela"}).json()["resultados"][0]
    assert achado["episodio"] == "201"

    srt = client.get(f"/api/episodios/{eid}/exportar", params={"formato": "srt"})
    assert "00:00:02,000 --> " in srt.text and "alecrim" in srt.text and "attachment" in srt.headers["content-disposition"]
    assert client.get(f"/api/episodios/{eid}/exportar", params={"formato": "vtt"}).text.startswith("WEBVTT")
    md = client.get(f"/api/episodios/{eid}/exportar", params={"formato": "md"}).text
    assert "# Episódio 201" in md and "## Resumo curto" in md
    assert client.get(f"/api/episodios/{eid}/exportar", params={"formato": "pdf"}).status_code == 422

    arquivo = M.get_settings().storage_dir
    antes = len(list(arquivo.glob("*.mp4")))
    assert client.delete(f"/api/episodios/{eid}").status_code == 204
    assert len(list(arquivo.glob("*.mp4"))) == antes - 1    # a mídia sai do disco junto com o episódio


def test_formato_desconhecido_e_recusado(client, sem_chaves):
    client.put("/api/config/chaves/openai", params={"testar": False}, json={"valor": CHAVE_OPENAI})
    r = client.post("/api/episodios", data={"titulo": "PDF", "numero": "300"}, files={"arquivo": ("ep.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 415
