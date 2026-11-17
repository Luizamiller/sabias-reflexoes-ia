export type EpisodioResumo = {
  id: number; numero: string; titulo: string; convidados: string; status: string; origem: string; midia_tipo: "audio" | "video" | null; duracao_s: number;
  criado_em: string; atualizado_em: string; pecas_revisadas: number; pecas_total: number; alertas: number; exemplo: boolean;
};
export type Segmento = { id: number; inicio: string; inicio_s: number; texto: string };
export type Etapa = { nome: string; status: string; detalhe: string | null; iniciado_em: string | null; terminado_em: string | null };
export type Peca = { id: number; tipo: string; rotulo: string; conteudo: unknown; status: string; editada: boolean; revisado_em: string | null };
export type Pacote = {
  id: number; motor: string; prompt_versao: string; alertas: string[]; tokens_entrada: number; tokens_saida: number; tempo_s: number;
  criado_em: string; pecas: Peca[];
};
export type Midia = { tipo: "audio" | "video"; nome: string | null; bytes: number | null };
export type Episodio = EpisodioResumo & { erro: string | null; tem_audio: boolean; tem_midia: boolean; midia: Midia | null; segmentos: Segmento[]; etapas: Etapa[]; pacote: Pacote | null };
export type Fonte = {
  episodio_id: number; episodio: string; titulo: string; inicio: string; minutos: string[]; texto: string; citacao: string;
  lexical: number; semantica: number | null;
};
export type Biblioteca = {
  episodios: EpisodioResumo[];
  totais: { episodios: number; horas: number; trechos: number; perguntas: number; em_revisao: number };
};
export type EventoAssistente =
  | { tipo: "fontes"; fontes: Fonte[]; reescrita: string | null }
  | { tipo: "texto"; texto: string }
  | { tipo: "fim"; motor: string; chamou_modelo: boolean; citacoes_invalidas: string[]; resposta: string; pergunta_id: number }
  | { tipo: "erro"; mensagem: string };
export type Provedor = "anthropic" | "openai" | "voyage";
export type ChaveStatus = {
  provedor: Provedor; nome: string; uso: string; configurada: boolean; origem: "painel" | "ambiente" | null;
  mascara: string | null; atualizado_em: string | null;
};
export type Integracoes = { claude: boolean; whisper: boolean; n8n: boolean; ffmpeg: boolean; embeddings: string };
export type Avaliacao = Record<string, Record<string, { versao: string; acertos: number; total: number; taxa: number; linhas: { pergunta: string; ok: boolean; achados: string[] }[] }>>;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init);
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(typeof body?.detail === "string" ? body.detail : "Não foi possível concluir. Tente de novo.");
  return body as T;
}
const json = (b: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

export const api = {
  health: () => req<{ status: string; integracoes: Integracoes }>("/health"),
  biblioteca: () => req<Biblioteca>("/episodios"),
  episodio: (id: number) => req<Episodio>(`/episodios/${id}`),
  novo: (form: FormData) => req<EpisodioResumo>("/episodios", { method: "POST", body: form }),
  reprocessar: (id: number, transcrever = false) => req<EpisodioResumo>(`/episodios/${id}/reprocessar${transcrever ? "?transcrever=true" : ""}`, { method: "POST" }),
  editarSegmento: (id: number, texto: string) => req<Segmento>(`/segmentos/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }) }),
  apagar: (id: number) => req<void>(`/episodios/${id}`, { method: "DELETE" }),
  revisar: (pid: number, acao: string, conteudo?: unknown) => req<Episodio>(`/pecas/${pid}`, json({ acao, conteudo })),
  busca: (q: string) => req<{ resultados: Fonte[]; ms: number; versao: string }>(`/busca?q=${encodeURIComponent(q)}`),
  avaliarResposta: (id: number, util: boolean) => req<{ ok: boolean }>(`/perguntas/${id}/avaliacao`, json({ util })),
  historico: () => req<{ id: number; pergunta: string; motor: string; chamou_modelo: boolean; fontes: string[]; citacoes_invalidas: string[]; util: boolean | null; ms: number; criado_em: string }[]>("/perguntas"),
  avaliacao: () => req<Avaliacao>("/avaliacao"),
  config: () => req<{ voz_da_marca: string; prompt: { versao: string; system: string; user: string }; changelog: string }>("/config"),
  chaves: () => req<ChaveStatus[]>("/config/chaves"),
  salvarChave: (provedor: Provedor, valor: string) => req<{ chaves: ChaveStatus[]; mensagem: string }>(`/config/chaves/${provedor}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ valor }) }),
  removerChave: (provedor: Provedor) => req<{ chaves: ChaveStatus[] }>(`/config/chaves/${provedor}`, { method: "DELETE" }),
  testarChave: (provedor: Provedor) => req<{ ok: boolean; mensagem: string }>(`/config/chaves/${provedor}/testar`, { method: "POST" }),
  salvarVoz: (texto: string) => req<{ ok: boolean }>("/config/voz", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }) }),
};

/** Lê o stream SSE do assistente e entrega cada evento. */
export async function perguntar(pergunta: string, onEvento: (e: EventoAssistente) => void, signal?: AbortSignal) {
  const res = await fetch("/api/assistente", { ...json({ pergunta }), signal });
  if (!res.ok || !res.body) throw new Error("Não foi possível falar com o assistente.");
  const leitor = res.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    const partes = buffer.split("\n\n");
    buffer = partes.pop() ?? "";
    for (const p of partes) if (p.startsWith("data: ")) onEvento(JSON.parse(p.slice(6)));
  }
}

/** Upload com progresso real (fetch não expõe o progresso do envio). Devolve a promessa e uma função para cancelar. */
export function enviarComProgresso(form: FormData, onProgresso: (enviado: number, total: number) => void) {
  if (import.meta.env.VITE_DEMO) {  // na demonstração o servidor roda no navegador e só atende fetch
    onProgresso(1, 1);
    return { promessa: api.novo(form), cancelar: () => {} };
  }
  const xhr = new XMLHttpRequest();
  const promessa = new Promise<EpisodioResumo>((resolve, reject) => {
    xhr.open("POST", "/api/episodios");
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgresso(e.loaded, e.total); };
    xhr.onload = () => {
      let body: { detail?: unknown } | null = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* resposta sem JSON */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as unknown as EpisodioResumo);
      else reject(new Error(typeof body?.detail === "string" ? body.detail : `O envio falhou (${xhr.status}).`));
    };
    xhr.onerror = () => reject(new Error("A conexão caiu durante o envio."));
    xhr.onabort = () => reject(new Error("Envio cancelado."));
    xhr.send(form);
  });
  return { promessa, cancelar: () => xhr.abort() };
}
