# Como medir o resultado

Métrica boa é métrica que você consegue defender numa entrevista. Por isso: poucos números, medidos do mesmo jeito, com episódios reais.

## 1. Linha de base (antes)
Pergunte à equipe — ou cronometre um episódio feito à mão — quanto tempo leva cada tarefa:

| Tarefa | Tempo manual (min) |
|---|---|
| Ouvir/revisar o episódio para anotar temas | |
| Escrever descrição e show notes | |
| Marcar capítulos | |
| Encontrar trechos para cortes | |
| Escrever posts (Instagram + LinkedIn) | |
| Escrever a newsletter | |
| **Total** | |

## 2. Com a automação (depois)
Para cada episódio processado, a planilha já registra **tempo de processamento** e **tokens**. Anote também:

| Episódio | Tempo de revisão humana (min) | Peças aprovadas sem edição (de 8) | Peças reescritas | Alertas que eram problemas reais |
|---|---|---|---|---|
| | | | | |

## 3. Custo
Custo por episódio ≈ (minutos de áudio × preço por minuto do Whisper) + (tokens de entrada e saída × preço do modelo). Consulte os preços atuais nas páginas da OpenAI e da Anthropic no dia em que medir.

## 4. Como apresentar
Depois de **pelo menos 3 episódios reais**, preencha a tabela de Resultados do README. Exemplo de frase honesta:

> "Em 3 episódios, o tempo da equipe caiu de ~X min para ~Y min por episódio; Z de 8 peças foram aprovadas sem edição; o custo de API foi de cerca de R$ W por episódio."

Se o resultado for modesto, mostre mesmo assim — e explique o que você mudou no prompt por causa disso (registre no `prompts/CHANGELOG.md`). Iteração com base em dado é exatamente o que um AI Builder faz.
