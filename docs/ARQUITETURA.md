# Arquitetura e decisões

## Componentes

| Camada | Escolha | Motivo |
|---|---|---|
| API | FastAPI | Upload multipart, Server-Sent Events para o assistente, OpenAPI em `/api/docs` |
| Persistência | SQLAlchemy 2 + Alembic | SQLite no desenvolvimento; Postgres (imagem com pgvector) em produção |
| Busca | scikit-learn + NumPy, índice em memória | O acervo de um podcast cabe em memória; reconstrução em milissegundos |
| Geração e respostas | Claude (Messages API, streaming) | Mesmo prompt v1 do workflow n8n, lido de `prompts/` |
| Transcrição | Whisper (OpenAI), `verbose_json` com segmentos | Timestamps por fala, como no n8n |
| Orquestração externa | n8n → webhook com segredo compartilhado (`hmac.compare_digest`) | Mantém o workflow original e centraliza a revisão no acervo |
| Interface | React 19, Vite, Tailwind 4, Radix, Motion, TanStack Query | Leitura confortável (Literata), navegação por minuto, streaming |

Rust não foi usado: a busca inteira sobre o acervo leva poucos milissegundos.

## Pipeline de um episódio

`recebido → transcrevendo (se áudio) → indexando → gerando → revisao → publicado`

Cada etapa grava uma linha em `etapas` com status, detalhe e horários; a interface acompanha por polling. Falhas param o episódio em `erro` com a mensagem e um botão de reprocessar. O processamento usa `BackgroundTasks`; com volume, troque por uma fila.

## Busca

1. **Fatiamento**: trechos de 3 falas com 1 de sobreposição (v2), guardando o minuto de cada fala.
2. **Léxica**: TF-IDF de pedaços de 3 a 5 letras, sem acentos — "culpa" casa com "culpada".
3. **Semântica**: `Embedder` com três implementações (LSA local, Voyage, OpenAI).
4. **Fusão**: Reciprocal Rank Fusion (k = 60), robusta a escalas diferentes.
5. **Relevância**: limiar léxico de 0,12 (v2). Com embeddings de provedor, a nota semântica também pode tornar um trecho relevante.

A decisão de não deixar a LSA ampliar a relevância veio da avaliação: ela deixava passar "quais os melhores investimentos" e "receita de bolo", que o acervo não trata.

## Assistente

`POST /api/assistente` devolve eventos SSE: `fontes` (antes do texto, para a interface mostrar o que foi consultado), `texto` (pedaços do streaming) e `fim` (motor, se chamou o modelo, citações inválidas e o id para avaliação útil/não útil). Cada pergunta fica em `perguntas` para medir uso e qualidade.

## Próximos passos técnicos

- Vetores em pgvector com índice HNSW quando o acervo crescer.
- Medir a v3 com embeddings de provedor e calibrar `limiar_sem` com episódios reais.
- Fila de processamento e reprocessamento parcial (só gerar de novo as peças rejeitadas).
- Diarização para atribuir citações a quem falou.
