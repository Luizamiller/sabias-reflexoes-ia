# Como instalar e rodar

## O que você precisa

| Item | Para quê | Onde conseguir |
|---|---|---|
| n8n | Rodar o workflow | [n8n.io](https://n8n.io) (plano cloud com teste grátis) ou `npx n8n` no computador |
| Chave da API da OpenAI | Transcrição (Whisper) | platform.openai.com → API keys |
| Chave da API da Anthropic | Geração de conteúdo e agente | console.anthropic.com → API keys |
| Conta Google | Planilha de revisão | Google Sheets |
| Python 3.10+ | Agente do acervo | python.org |

> 🔐 **Nunca coloque chaves de API no código ou no GitHub.** No n8n elas ficam em *Credentials*; no Python, em variável de ambiente.

---

## Parte 1 — Workflow no n8n

### 1. Crie a planilha
1. Crie uma planilha no Google Sheets e renomeie a aba para **`Episodios`**.
2. Na linha 1, cole estes cabeçalhos (um por coluna, nesta ordem):

```
Data	Episódio	Título	Convidados	Status	Resumo curto	Show notes	Capítulos	Cortes	Citações	Post Instagram	Post LinkedIn	Newsletter - assunto	Newsletter - corpo	Alertas de revisão	Duração do episódio (min)	Tempo de processamento (s)	Versão do prompt	Tokens (entrada/saída)	Transcrição
```
> Dica: copie a linha acima (está separada por TAB) e cole na célula A1 — cada nome cai em uma coluna.

### 2. Importe o workflow
1. No n8n: **Workflows → Import from File** → escolha `workflows/episodio-para-conteudo.json`.
2. Abra cada nó com ⚠️ e conecte as credenciais:
   - **Transcrever (Whisper)** → nova credencial *OpenAI*.
   - **Claude: gerar conteúdo** → nova credencial *Anthropic*.
   - **Salvar para revisão (Sheets)** → nova credencial *Google Sheets OAuth2*.
3. No nó **Salvar para revisão (Sheets)**, troque `COLE_AQUI_A_URL_DA_PLANILHA` pela URL da sua planilha.

### 3. Configure a voz da marca
1. Preencha `config/voz-da-marca.md`.
2. Abra o nó **Montar pedido ao Claude** e cole o texto dentro da constante `VOZ_DA_MARCA`.

### 4. Teste
1. Abra o nó **Formulário: novo episódio** → copie a *Test URL*.
2. Clique em **Test workflow** e envie um áudio curto (2–5 min) pelo formulário.
3. Confira a nova linha na planilha. Se algum nó ficar vermelho, clique nele para ver o erro.
4. Quando funcionar, **ative** o workflow e use a *Production URL* do formulário com a equipe.

### Problemas comuns
| Erro | Causa provável | Solução |
|---|---|---|
| `413` ou "file too large" na transcrição | Áudio acima de 25 MB | Exporte em MP3 mono 64 kbps ou divida o episódio |
| "O Claude não devolveu JSON válido" | Resposta cortada ou com texto extra | Aumente `max_tokens` no nó "Montar pedido ao Claude" |
| Colunas vazias na planilha | Cabeçalhos diferentes dos do passo 1 | Copie os cabeçalhos exatamente como estão |
| `404` no Claude | Nome do modelo indisponível na sua conta | Troque a constante `MODELO` no nó "Montar pedido ao Claude" |

---

## Parte 2 — Agente "Pergunte ao acervo"

```bash
cd agente-acervo
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                                          # 5 testes, sem precisar de chave
```

Para usar de verdade:
```bash
export ANTHROPIC_API_KEY="sua-chave"               # Windows: set ANTHROPIC_API_KEY=sua-chave
streamlit run app.py
```

### Adicionando episódios reais
Crie um `.txt` por episódio em `dados/transcricoes/`, neste formato:

```
titulo: Nome do episódio
episodio: 12
---
[00:00] primeira fala
[00:15] segunda fala
```

A coluna **Transcrição** da planilha já sai nesse formato `[mm:ss]` — basta copiar e colar abaixo do `---`.
Apague os arquivos `exemplo-*.txt` quando colocar os reais.
