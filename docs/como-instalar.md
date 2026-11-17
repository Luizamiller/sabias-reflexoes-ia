# Como instalar e rodar

## O que você precisa

| Item | Para quê | Obrigatório? |
|---|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | Backend | Sim |
| Node 22 + pnpm | Interface | Sim |
| Chave da Anthropic | Gerar as 8 peças, responder no assistente, reescrever perguntas | Não — sem ela, rascunho extrativo e respostas com os trechos |
| Chave da OpenAI | Transcrever áudio (Whisper) | Não — sem ela, envie a transcrição pronta |
| n8n | Rodar o workflow original | Não |

> Nunca coloque chaves no código ou no GitHub. No backend elas ficam em `backend/.env`; no n8n, em *Credentials* e *Variables*.

## 1. Backend e interface

```bash
cd backend
cp .env.example .env          # preencha o que tiver
uv sync
uv run alembic upgrade head
uv run python -m app.seed     # 6 episódios fictícios
uv run uvicorn app.main:app --port 8102
```

```bash
cd web
pnpm install
pnpm dev                      # http://localhost:5102
```

## 2. Adicionando episódios

Pela interface, em **Novo episódio**: cole a transcrição, envie um `.txt` ou um áudio. Formato da transcrição:

```
titulo: Nome do episódio        (opcional quando colado na interface)
episodio: 12
---
[00:00] primeira fala
[00:15] segunda fala
```

A coluna **Transcrição** da planilha do n8n já sai nesse formato.

## 3. Workflow no n8n (opcional)

O workflow `workflows/episodio-para-conteudo.json` continua gravando na planilha de revisão e agora também envia cada episódio ao acervo.

1. Crie a planilha com a aba **`Episodios`** e os cabeçalhos abaixo (separados por TAB):

```
Data	Episódio	Título	Convidados	Status	Resumo curto	Show notes	Capítulos	Cortes	Citações	Post Instagram	Post LinkedIn	Newsletter - assunto	Newsletter - corpo	Alertas de revisão	Duração do episódio (min)	Tempo de processamento (s)	Versão do prompt	Tokens (entrada/saída)	Transcrição
```

2. No n8n: **Workflows → Import from File** e conecte as credenciais *OpenAI*, *Anthropic* e *Google Sheets OAuth2*.
3. Troque `COLE_AQUI_A_URL_DA_PLANILHA` no nó de Sheets pela URL da planilha.
4. Em **Settings → Variables**, crie `ACERVO_URL` (ex.: `https://acervo.seudominio.com`) e `ACERVO_TOKEN` com o mesmo valor de `N8N_TOKEN` do `backend/.env`.
5. Cole o conteúdo de `config/voz-da-marca.md` na constante `VOZ_DA_MARCA` do nó **Montar pedido ao Claude**.
6. Teste com um áudio curto (2–5 min). O episódio aparece na planilha e na Biblioteca como "aguardando revisão".

| Erro | Causa provável | Solução |
|---|---|---|
| `413` ou "file too large" | Áudio acima de 25 MB | MP3 mono 64 kbps ou dividir o episódio |
| "O Claude não devolveu JSON válido" | Resposta cortada | Aumente `max_tokens` no nó do prompt |
| `401` em "Enviar ao acervo" | Token diferente | `ACERVO_TOKEN` precisa ser igual a `N8N_TOKEN` |
| `404` no Claude | Modelo indisponível na conta | Troque `MODELO` no nó do prompt |

## 4. Testes

```bash
cd backend && uv run pytest              # sem chave: o modelo é simulado
cd backend && uv run python -m app.eval  # qualidade da busca
cd web && pnpm test && PLAYWRIGHT_CHANNEL=msedge pnpm test:e2e
```
