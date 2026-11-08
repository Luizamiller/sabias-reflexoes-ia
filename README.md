# 🎙️ Às Sábias Reflexões — IA de episódio a conteúdo

> Automação com IA que transforma o áudio de um episódio de podcast em show notes, capítulos, cortes para Reels, posts e newsletter — e um agente que responde perguntas sobre todo o acervo citando episódio e minuto.

**Autora:** Luiza Miller · Product Owner do Às Sábias Reflexões (dez/2024–ago/2025)
**Stack:** n8n · Claude API · OpenAI Whisper · Google Sheets · Python · Streamlit

---

## 1. O problema

Como Product Owner do podcast, acompanhei de perto o que acontecia depois de cada gravação. O episódio pronto era só o começo: alguém precisava ouvir tudo de novo para escrever a descrição, marcar os capítulos, achar os melhores trechos para Reels, escrever posts para cada rede e montar a newsletter.

Era trabalho manual, repetitivo e sempre feito com pressa — e o acervo de episódios antigos, cheio de conteúdo bom, ficava esquecido porque ninguém lembrava *em qual episódio* algo tinha sido dito.

## 2. A solução

O projeto tem duas partes independentes:

| | Parte 1 — Episódio → Conteúdo | Parte 2 — Pergunte ao acervo |
|---|---|---|
| **O que faz** | Recebe o áudio e entrega 8 peças de conteúdo prontas para revisão | Responde perguntas sobre episódios antigos com citação de episódio e minuto |
| **Quem usa** | Equipe de conteúdo | Equipe (pauta, cortes antigos) e, futuramente, ouvintes |
| **Ferramentas** | n8n, Whisper, Claude, Google Sheets | Python, TF-IDF, Claude, Streamlit |
| **Pasta** | [`workflows/`](workflows/) e [`prompts/`](prompts/) | [`agente-acervo/`](agente-acervo/) |

### Arquitetura

```mermaid
flowchart LR
    A[📤 Formulário n8n<br/>áudio + título] --> B[Whisper<br/>transcrição com timestamps]
    B --> C[Formata<br/>linhas mm:ss]
    C --> D[Claude<br/>prompt v1 + voz da marca]
    D --> E{Validação<br/>automática}
    E -->|JSON + alertas| F[(Google Sheets<br/>status: aguardando revisão)]
    F --> G[👩 Revisão humana<br/>aprova e publica]
    F -. transcrições .-> H[(Acervo)]
    H --> I[Busca TF-IDF<br/>top 5 trechos]
    I -->|relevante| J[Claude<br/>responde com fonte]
    I -->|nada relevante| K[“Não encontrei”<br/>sem chamar o modelo]
```

### O que sai de cada episódio (uma linha na planilha)

Resumo curto · Show notes · Capítulos com horário · 3–5 cortes para Reels (início, fim, gancho e por que funciona) · Citações literais · Post para Instagram · Post para LinkedIn · Newsletter (assunto + corpo) · **Alertas de revisão** · Tempo de processamento · Tokens usados · Versão do prompt

## 3. Decisões de produto e de prompt

Estas escolhas foram o centro do projeto — a parte técnica é simples de propósito.

**Humano no circuito, sempre.** Nada é publicado automaticamente. Toda linha entra na planilha como *"Aguardando revisão"*. Um podcast fala em nome de pessoas reais; o custo de uma frase inventada é muito maior que o tempo economizado.

**Validação automática contra alucinação.** Depois que o Claude responde, um nó de código confere:
- se a resposta é um JSON válido com todos os campos;
- se cada **citação existe literalmente** na transcrição;
- se cada **corte** tem horário válido, dentro da duração do episódio e com duração razoável.

O que falhar não trava o fluxo: vira um ⚠️ na coluna *Alertas de revisão*, para o revisor olhar primeiro.

**O modelo tem permissão para dizer que não sabe.** O campo `alertas_revisao` no esquema dá ao Claude um lugar honesto para registrar trechos confusos da transcrição, em vez de "chutar". No agente do acervo, se a busca não encontra nada relevante, a resposta é *"não encontrei"* — e o modelo nem é chamado (zero custo, zero chance de inventar).

**Timestamps prontos na entrada.** O Whisper devolve segundos; o workflow converte para `[mm:ss]` antes de enviar. O modelo só precisa *copiar* horários que já existem, em vez de calcular — o que reduz cortes com horários inexistentes.

**Voz da marca separada da lógica.** O tom do podcast fica em [`config/voz-da-marca.md`](config/voz-da-marca.md). A equipe ajusta o estilo sem mexer nas regras do prompt.

**Prompts versionados.** Cada versão fica em [`prompts/`](prompts/), com o motivo da mudança em [`CHANGELOG.md`](prompts/CHANGELOG.md). A versão usada é gravada em cada linha da planilha, para comparar resultados entre versões.

## 4. Resultados

> ⏳ **Em medição.** Os números abaixo serão preenchidos com episódios reais — veja o método em [`docs/metricas.md`](docs/metricas.md).

| Métrica | Antes (manual) | Depois (com IA) |
|---|---|---|
| Tempo da equipe por episódio | _a medir_ | _a medir_ |
| Tempo de processamento automático | — | _a medir_ |
| % de peças aprovadas sem edição | — | _a medir_ |
| Custo de API por episódio | — | _a medir_ |

## 5. Como rodar

Guia completo em [`docs/como-instalar.md`](docs/como-instalar.md). Resumo:

**Parte 1 (n8n):** importe `workflows/episodio-para-conteudo.json` no n8n, conecte as credenciais da OpenAI, Anthropic e Google Sheets, cole a URL da planilha e abra o link do formulário.

**Parte 2 (agente):**
```bash
cd agente-acervo
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sua-chave"
pytest -q                 # testes rodam sem chave de API
streamlit run app.py      # interface de chat
```

As transcrições em `agente-acervo/dados/transcricoes/` são **exemplos fictícios** para testes. Para usar com o acervo real, coloque os `.txt` dos episódios no mesmo formato.

## 6. Limitações e próximos passos

- **Áudio acima de 25 MB** precisa ser comprimido ou dividido (limite da API de transcrição). Próximo passo: dividir automaticamente no próprio fluxo.
- **Busca por palavras (TF-IDF)** não entende sinônimos: "ansiedade" não encontra "nervosismo". Próximo passo: embeddings, que buscam por significado.
- **Identificação de quem fala** (diarização) ainda não existe; as citações não dizem se foi o apresentador ou o convidado.
- **Publicação**: depois da aprovação na planilha, um segundo fluxo poderia agendar os posts automaticamente.

## 7. O que aprendi

_[Escreva aqui, com suas palavras, depois de rodar com episódios reais: o que deu errado na primeira versão do prompt, o que a equipe achou, o que você mudaria.]_

---

📫 [LinkedIn](https://www.linkedin.com/in/luiza-miller) · luizamiller.pharma@gmail.com
