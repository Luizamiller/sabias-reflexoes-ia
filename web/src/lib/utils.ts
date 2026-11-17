import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...v: ClassValue[]) => twMerge(clsx(v));

export const duracao = (s: number) => {
  const m = Math.floor(s / 60), r = s % 60;
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m}:${String(r).padStart(2, "0")}`;
};
export const segundos = (ts: string) => ts.split(":").map(Number).reduce((a, n) => a * 60 + n, 0);
export const tamanho = (b: number) =>
  b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(2).replace(".", ",")} GB` : b >= 1024 ** 2 ? `${(b / 1024 ** 2).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
export const tituloLimpo = (t: string) => t.replace(/^\[EXEMPLO FICTÍCIO\]\s*/, "");
export const dataCurta = (iso: string) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });

export const STATUS: Record<string, { rotulo: string; tom: string }> = {
  recebido: { rotulo: "Na fila", tom: "neutro" },
  transcrevendo: { rotulo: "Transcrevendo", tom: "andamento" },
  indexando: { rotulo: "Indexando", tom: "andamento" },
  gerando: { rotulo: "Gerando conteúdo", tom: "andamento" },
  revisao: { rotulo: "Aguardando revisão", tom: "atencao" },
  publicado: { rotulo: "Revisado", tom: "ok" },
  erro: { rotulo: "Erro", tom: "erro" },
};

export const ETAPAS: Record<string, string> = {
  transcricao: "Transcrição", indexacao: "Indexação para a busca", conteudo: "Geração das 8 peças", validacao: "Validação contra alucinação",
};

export const MOTOR: Record<string, string> = {
  claude: "Claude", n8n: "n8n (Whisper + Claude)", rascunho_deterministico: "Rascunho extrativo, sem modelo de linguagem",
  extrativo: "Sem modelo de linguagem", nenhum: "Sem chamada ao modelo",
};

export function aplicarTemaInicial() {
  try {
    const t = localStorage.getItem("tema");
    if (t === "escuro" || (!t && matchMedia("(prefers-color-scheme: dark)").matches)) document.documentElement.classList.add("dark");
  } catch { /* sem armazenamento */ }
}
