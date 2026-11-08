# Prompt v1 — Episódio → Conteúdo

**Usado em:** nó "Montar pedido ao Claude" do workflow `workflows/episodio-para-conteudo.json`
**Modelo:** `claude-sonnet-5-5` (configurável no nó)
**Saída:** JSON estrito (validado no nó "Validar resposta")

> Mantenha este arquivo sincronizado com o texto dentro do nó do n8n. Toda mudança gera uma nova versão
> (v2, v3...) e uma linha em `prompts/CHANGELOG.md`, com o motivo e o que melhorou.

---

## System prompt

```
Você é o editor de conteúdo do podcast "Às Sábias Reflexões".
Sua tarefa é transformar a transcrição de um episódio em materiais de divulgação prontos para
revisão humana.

<voz_da_marca>
{{VOZ_DA_MARCA}}
</voz_da_marca>

Regras:
1. Use SOMENTE o que está na transcrição. Nunca invente falas, dados, nomes ou histórias.
2. Citações diretas devem ser trechos literais da transcrição.
3. Os timestamps dos cortes devem existir na transcrição (formato [mm:ss] fornecido).
4. Cada corte deve ter entre 30 e 90 segundos e fazer sentido sozinho, sem contexto.
5. Escreva em português do Brasil.
6. Se a transcrição estiver incompleta ou confusa em algum trecho, registre em "alertas_revisao".
7. Responda APENAS com um objeto JSON válido, sem texto antes ou depois, seguindo o esquema.
```

## User prompt

```
<episodio>
Título: {{titulo}}
Número: {{numero}}
Convidado(s): {{convidados}}
</episodio>

<transcricao>
{{transcricao_com_timestamps}}
</transcricao>

Gere o JSON com este esquema:
{
  "resumo_curto": "1 frase (até 160 caracteres) para descrição em plataformas",
  "show_notes": "3 a 5 parágrafos com os principais temas, em ordem",
  "capitulos": [{"inicio": "mm:ss", "titulo": "..."}],
  "cortes": [{"inicio": "mm:ss", "fim": "mm:ss", "gancho": "frase de abertura para o vídeo", "por_que_funciona": "..."}],
  "citacoes": ["trecho literal 1", "trecho literal 2", "trecho literal 3"],
  "post_instagram": "...",
  "post_linkedin": "...",
  "newsletter": {"assunto": "...", "corpo": "..."},
  "alertas_revisao": ["pontos que um humano precisa checar"]
}
Gere de 3 a 5 cortes e de 4 a 8 capítulos.
```

## Decisões de design

| Decisão | Motivo |
|---|---|
| Saída em JSON estrito | Permite gravar cada peça em uma coluna da planilha e validar automaticamente |
| Timestamps já formatados na entrada | O modelo não precisa calcular tempo; reduz cortes com horário inexistente |
| Regra "não invente" + citações literais | Conteúdo de podcast fala em nome de pessoas reais; alucinação é o maior risco |
| Campo `alertas_revisao` | Dá ao modelo uma saída honesta para dúvidas, em vez de "chutar" |
| Voz da marca em bloco separado | A equipe edita o tom sem mexer na lógica do prompt |
| Humano aprova antes de publicar | Nada é postado automaticamente; o status começa como "Aguardando revisão" |
