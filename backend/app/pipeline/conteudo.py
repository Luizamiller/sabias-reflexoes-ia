"""Episódio → 8 peças de conteúdo, com validação contra alucinação.

- O prompt é lido de `prompts/v1-episodio-para-conteudo.md` (versionado, como no projeto original).
- `validar` é a porta para Python do nó "Validar resposta" do workflow n8n: JSON completo,
  cortes com horário válido e dentro do episódio, citações que existem literalmente.
- Sem chave da Anthropic, `rascunho_deterministico` monta peças extrativas (só frases da própria
  transcrição) para a equipe ter por onde começar — e marca isso como alerta.
"""
from __future__ import annotations

import json
import re
import time

from ..config import REPO_DIR, get_settings
from ..search.engine import Fala, mmss, segundos

PECAS = ["resumo_curto", "show_notes", "capitulos", "cortes", "citacoes", "post_instagram", "post_linkedin", "newsletter"]
ROTULOS = {"resumo_curto": "Resumo curto", "show_notes": "Show notes", "capitulos": "Capítulos", "cortes": "Cortes para Reels",
           "citacoes": "Citações", "post_instagram": "Post para Instagram", "post_linkedin": "Post para LinkedIn",
           "newsletter": "Newsletter"}
PROMPTS_DIR = REPO_DIR / "prompts"


def transcricao_ts(falas: list[Fala]) -> str:
    return "\n".join(f"[{mmss(f.inicio)}] {f.texto}" for f in falas)


def carregar_prompt(versao: str = "v1") -> tuple[str, str]:
    arq = next(PROMPTS_DIR.glob(f"{versao}-*.md"))
    texto = arq.read_text(encoding="utf-8")
    blocos = re.findall(r"```\n(.*?)\n```", texto, flags=re.S)
    return blocos[0], blocos[1]  # system, user


def montar_pedido(titulo: str, numero: str, convidados: str, falas: list[Fala], voz: str, versao: str = "v1") -> tuple[str, str]:
    system, user = carregar_prompt(versao)
    system = system.replace("{{VOZ_DA_MARCA}}", voz.strip())
    user = (user.replace("{{titulo}}", titulo).replace("{{numero}}", numero).replace("{{convidados}}", convidados)
            .replace("{{transcricao_com_timestamps}}", transcricao_ts(falas)))
    return system, user


def gerar_com_claude(titulo, numero, convidados, falas, voz, versao="v1", cliente=None) -> tuple[dict, dict]:
    cfg = get_settings()
    if cliente is None:
        import anthropic

        from ..segredos import chave
        cliente = anthropic.Anthropic(api_key=chave("anthropic"))
    system, user = montar_pedido(titulo, numero, convidados, falas, voz, versao)
    t0 = time.perf_counter()
    resp = cliente.messages.create(model=cfg.modelo_claude, max_tokens=4000, system=system,
                                   messages=[{"role": "user", "content": user}])
    bruto = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    limpo = re.sub(r"^```(?:json)?\s*|```\s*$", "", bruto.strip())
    try:
        dados = json.loads(limpo)
    except json.JSONDecodeError:
        raise ValueError("O Claude não devolveu JSON válido. Início da resposta: " + bruto[:300])
    uso = getattr(resp, "usage", None)
    return dados, {"tokens_entrada": getattr(uso, "input_tokens", 0), "tokens_saida": getattr(uso, "output_tokens", 0),
                   "tempo_s": round(time.perf_counter() - t0, 1)}


def _frases_citaveis(falas: list[Fala], n: int) -> list[str]:
    candidatas = [f.texto for f in falas[1:] if 60 <= len(f.texto) <= 160 and "fictício" not in f.texto.lower()]
    return sorted(candidatas, key=lambda t: (-len(set(t.split())), t))[:n]


def rascunho_deterministico(titulo: str, falas: list[Fala], duracao_s: int) -> dict:
    """Peças extrativas: só usa frases que existem na transcrição. Ponto de partida para a revisão."""
    uteis = [f for f in falas if "fictício" not in f.texto.lower()] or falas
    n_cap = min(5, max(2, len(uteis) // 3))
    passo = max(1, len(uteis) // n_cap)
    capitulos = [{"inicio": mmss(uteis[i].inicio), "titulo": " ".join(uteis[i].texto.split()[:7]).rstrip(",.") + "…"}
                 for i in range(0, len(uteis), passo)][:n_cap]
    cortes = []
    for i in range(len(uteis)):
        j = i
        while j + 1 < len(uteis) and uteis[j + 1].inicio - uteis[i].inicio <= 75:
            j += 1
        fim = uteis[j + 1].inicio if j + 1 < len(uteis) else duracao_s
        if 30 <= fim - uteis[i].inicio <= 90 and not any(c["inicio"] == mmss(uteis[i].inicio) for c in cortes):
            cortes.append({"inicio": mmss(uteis[i].inicio), "fim": mmss(fim), "gancho": uteis[i].texto,
                           "por_que_funciona": "Trecho contínuo que faz sentido sozinho (seleção automática por duração)."})
        if len(cortes) == 3:
            break
    citacoes = _frases_citaveis(falas, 3)
    resumo = uteis[0].texto if len(uteis[0].texto) <= 160 else uteis[0].texto[:157] + "…"
    corpo = [f.texto for f in uteis]
    terco = max(1, len(corpo) // 3)
    show_notes = "\n\n".join(" ".join(corpo[k: k + terco]) for k in range(0, len(corpo), terco))
    destaque = citacoes[0] if citacoes else resumo
    return {
        "resumo_curto": resumo,
        "show_notes": show_notes,
        "capitulos": capitulos,
        "cortes": cortes,
        "citacoes": citacoes,
        "post_instagram": f"“{destaque}”\n\nNo episódio {titulo.replace('[EXEMPLO FICTÍCIO] ', '')}, a conversa vai além. Link na bio.",
        "post_linkedin": f"{resumo}\n\nUma ideia do episódio que fica: “{destaque}”",
        "newsletter": {"assunto": titulo.replace("[EXEMPLO FICTÍCIO] ", ""), "corpo": f"{resumo}\n\n{show_notes.split(chr(10))[0]}"},
        "alertas_revisao": ["Rascunho automático sem modelo de linguagem: peças extraídas da transcrição. Revise tom e ordem antes de publicar."],
    }


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.lower().replace("“", "").replace("”", "").replace('"', "")).strip()


def validar(conteudo: dict, transcricao_texto: str, duracao_s: int) -> list[str]:
    """Porta do nó 'Validar resposta' (n8n). Problemas viram alertas para o revisor; não travam o fluxo."""
    faltando = [k for k in PECAS if k not in conteudo]
    if faltando:
        raise ValueError("Campos ausentes na resposta: " + ", ".join(faltando))
    alertas = list(conteudo.get("alertas_revisao") or [])
    for c in conteudo.get("cortes") or []:
        try:
            ini, fim = segundos(c["inicio"]), segundos(c["fim"])
        except (KeyError, ValueError):
            alertas.append(f"Corte com horário inválido: {c.get('inicio')}–{c.get('fim')}")
            continue
        if fim <= ini:
            alertas.append(f"Corte com horário inválido: {c['inicio']}–{c['fim']}")
        elif fim > duracao_s + 5:
            alertas.append(f"Corte {c['inicio']}–{c['fim']} passa do fim do episódio")
        elif not 20 <= fim - ini <= 120:
            alertas.append(f"Corte {c['inicio']}–{c['fim']} com duração fora do ideal ({fim - ini}s)")
    texto = _norm(transcricao_texto)
    for q in conteudo.get("citacoes") or []:
        if _norm(q)[:40] not in texto:
            alertas.append(f'Citação não encontrada literalmente na transcrição: "{q[:60]}..."')
    return alertas
