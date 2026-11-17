import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, EyeOff, FileText, Film, KeyRound, LoaderCircle, Music, Search, Trash2, Upload, X } from "lucide-react";
import { Tabs } from "radix-ui";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useToast } from "@/components/toast";
import { Button, Skeleton } from "@/components/ui/primitives";
import { api, enviarComProgresso, type ChaveStatus, type Provedor } from "@/lib/api";
import { cn, duracao, tamanho, tituloLimpo } from "@/lib/utils";

function Pagina({ eyebrow, titulo, sub, children }: { eyebrow: string; titulo: ReactNode; sub?: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-[960px] px-5 py-10 sm:px-10">
      <p className="eyebrow">{eyebrow}</p>
      <h1 className="mt-3 text-[34px] leading-tight">{titulo}</h1>
      {sub && <p className="mt-2 max-w-[640px] text-ink-2">{sub}</p>}
      <div className="mt-8">{children}</div>
    </div>
  );
}

const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
function destacar(texto: string, q: string): ReactNode {
  const termos = norm(q).split(/\s+/).filter((t) => t.length > 3).map((t) => t.slice(0, 5));
  if (!termos.length) return texto;
  return texto.split(/(\s+)/).map((p, i) => termos.some((t) => norm(p).startsWith(t))
    ? <mark key={i} className="rounded-[3px] bg-accent-wash px-0.5 text-ink">{p}</mark> : <Fragment key={i}>{p}</Fragment>);
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [texto, setTexto] = useState(q);
  useEffect(() => setTexto(q), [q]);
  const { data, isFetching } = useQuery({ queryKey: ["busca", q], queryFn: () => api.busca(q), enabled: q.length >= 2 });
  return (
    <Pagina eyebrow="Busca" titulo="Encontre o momento exato" sub="Busca híbrida: pedaços de palavras (para casar “culpa” com “culpada”) e vetores semânticos para reordenar.">
      <form onSubmit={(e) => { e.preventDefault(); setParams(texto.trim() ? { q: texto.trim() } : {}); }}
        className="flex items-center gap-2 rounded-[12px] border border-line-strong bg-surface px-3.5 focus-within:border-accent">
        <Search className="size-4 text-ink-3" />
        <label htmlFor="q" className="sr-only">Termo de busca</label>
        <input id="q" autoFocus value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="descanso não é preguiça" className="h-12 min-w-0 flex-1 bg-transparent outline-none" />
      </form>
      {data && <p className="mt-3 text-[12.5px] text-ink-3">{data.resultados.length} trechos · {data.ms} ms · busca {data.versao}</p>}
      {isFetching && <Skeleton className="mt-6 h-40" />}
      {data && !data.resultados.length && <p className="mt-10 border-y border-line py-10 text-center text-ink-3">Nada no acervo passou do limiar de relevância para essa busca.</p>}
      <ol className="mt-6 divide-y divide-line">
        {data?.resultados.map((r) => (
          <li key={r.citacao + r.texto.slice(0, 12)}>
            <Link to={`/episodios/${r.episodio_id}?t=${r.inicio}`} className="group block py-5">
              <p className="flex flex-wrap items-baseline gap-x-3 text-[12.5px]">
                <span className="font-mono text-accent-ink">{r.citacao}</span>
                <span className="text-ink-3">{tituloLimpo(r.titulo)}</span>
                <span className="ml-auto font-mono text-[11.5px] text-ink-3">léxica {r.lexical.toFixed(2)}{r.semantica != null && ` · semântica ${r.semantica.toFixed(2)}`}</span>
              </p>
              <p className="mt-2 font-serif text-[17px] leading-relaxed group-hover:text-accent-ink">{destacar(r.texto, q)}</p>
            </Link>
          </li>
        ))}
      </ol>
    </Pagina>
  );
}

const EXEMPLO = `[00:00] Olá, sejam bem-vindos a mais um episódio.
[00:14] Hoje a conversa é sobre recomeços.
[00:31] ...`;

const EXT_VIDEO = /\.(mp4|mov|mkv|webm|avi|m4v|mpe?g|wmv)$/i;
const tipoArquivo = (f: File) => f.name.toLowerCase().endsWith(".txt") ? "texto" : (f.type.startsWith("video/") || EXT_VIDEO.test(f.name)) ? "video" : "audio";

export function NewEpisodePage() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [modo, setModo] = useState("arquivo");
  const [form, setForm] = useState({ titulo: "", numero: "", convidados: "" });
  const [transcricao, setTranscricao] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [duracaoMidia, setDuracaoMidia] = useState<number | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const [progresso, setProgresso] = useState<{ enviado: number; total: number } | null>(null);
  const cancelar = useRef<(() => void) | null>(null);
  const tipo = arquivo ? tipoArquivo(arquivo) : null;
  const midia = tipo === "audio" || tipo === "video";
  const semChave = midia && h && !h.integracoes.whisper;

  // lê a duração no próprio navegador, antes de enviar
  useEffect(() => {
    setDuracaoMidia(null);
    if (!arquivo || !midia) return;
    const url = URL.createObjectURL(arquivo);
    const el = document.createElement(tipo === "video" ? "video" : "audio");
    el.preload = "metadata";
    el.onloadedmetadata = () => { if (Number.isFinite(el.duration)) setDuracaoMidia(Math.round(el.duration)); URL.revokeObjectURL(url); };
    el.onerror = () => URL.revokeObjectURL(url);
    el.src = url;
    return () => URL.revokeObjectURL(url);
  }, [arquivo]); // eslint-disable-line react-hooks/exhaustive-deps

  const enviar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.set("titulo", form.titulo); fd.set("numero", form.numero); fd.set("convidados", form.convidados || "Sem convidados");
      if (modo === "colar") fd.set("transcricao", transcricao); else if (arquivo) fd.set("arquivo", arquivo);
      setProgresso({ enviado: 0, total: arquivo?.size ?? 1 });
      const { promessa, cancelar: c } = enviarComProgresso(fd, (enviado, total) => setProgresso({ enviado, total }));
      cancelar.current = c;
      return promessa;
    },
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ["biblioteca"] }); navigate(`/episodios/${e.id}`); },
    onError: (e) => toast((e as Error).message, "erro"),
    onSettled: () => { setProgresso(null); cancelar.current = null; },
  });
  const escolher = (f: File | undefined | null) => { if (f) setArquivo(f); };
  const pct = progresso ? Math.min(100, Math.round((progresso.enviado / progresso.total) * 100)) : 0;
  const IconeArq = tipo === "video" ? Film : tipo === "audio" ? Music : FileText;

  return (
    <Pagina eyebrow="Novo episódio" titulo="Do vídeo ao acervo" sub="Envie o vídeo ou o áudio do episódio: o áudio é extraído, transcrito com marcação de tempo, indexado para a busca e vira um rascunho das 8 peças. Tudo entra como “aguardando revisão”.">
      <form className="grid gap-6" onSubmit={(e) => { e.preventDefault(); enviar.mutate(); }}>
        <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
          <Campo id="numero" rotulo="Número" valor={form.numero} onChange={(v) => setForm({ ...form, numero: v })} placeholder="12" />
          <Campo id="titulo" rotulo="Título" valor={form.titulo} onChange={(v) => setForm({ ...form, titulo: v })} placeholder="Recomeçar depois dos 30" />
        </div>
        <Campo id="convidados" rotulo="Convidados" valor={form.convidados} onChange={(v) => setForm({ ...form, convidados: v })} placeholder="Sem convidados" obrigatorio={false} />

        <Tabs.Root value={modo} onValueChange={setModo}>
          <Tabs.List className="flex gap-1 border-b border-line">
            {[["arquivo", "Vídeo, áudio ou .txt", Upload], ["colar", "Colar transcrição", FileText]].map(([v, r, I]) => {
              const Icone = I as typeof FileText;
              return (
                <Tabs.Trigger key={v as string} value={v as string} className="-mb-px flex items-center gap-2 border-b-2 border-transparent px-3 pb-2.5 text-[14px] text-ink-2 data-[state=active]:border-accent data-[state=active]:text-ink">
                  <Icone className="size-4" />{r as string}
                </Tabs.Trigger>
              );
            })}
          </Tabs.List>
          <Tabs.Content value="colar" className="pt-4">
            <label htmlFor="transcricao" className="text-[13px] text-ink-2">Uma fala por linha, no formato <code className="font-mono text-[12px]">[mm:ss] texto</code> — o mesmo da coluna Transcrição da planilha do n8n.</label>
            <textarea id="transcricao" rows={12} value={transcricao} onChange={(e) => setTranscricao(e.target.value)} placeholder={EXEMPLO}
              className="mt-2 w-full rounded-[10px] border border-line-strong bg-surface p-3.5 font-mono text-[13px] leading-relaxed outline-none focus:border-accent" />
          </Tabs.Content>
          <Tabs.Content value="arquivo" className="pt-4">
            <label
              onDragOver={(e) => { e.preventDefault(); setArrastando(true); }} onDragLeave={() => setArrastando(false)}
              onDrop={(e) => { e.preventDefault(); setArrastando(false); escolher(e.dataTransfer.files?.[0]); }}
              className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[12px] border border-dashed bg-surface px-6 py-10 text-center transition-colors",
                arrastando ? "border-accent bg-accent-wash" : "border-line-strong hover:border-accent")}>
              {arquivo ? (
                <>
                  <IconeArq className="size-6 text-accent" strokeWidth={1.6} />
                  <span className="max-w-full truncate text-[15px] font-medium">{arquivo.name}</span>
                  <span className="font-mono text-[12px] text-ink-3">
                    {{ video: "vídeo", audio: "áudio", texto: "transcrição" }[tipo!]} · {tamanho(arquivo.size)}{duracaoMidia != null && ` · ${duracao(duracaoMidia)}`}
                  </span>
                  <span className="text-[12px] text-accent-ink underline-offset-4 hover:underline">trocar arquivo</span>
                </>
              ) : (
                <>
                  <Upload className="size-5 text-ink-3" />
                  <span className="text-[14px]">Arraste o arquivo aqui ou clique para escolher</span>
                  <span className="text-[12px] text-ink-3">Vídeo (MP4, MOV, MKV, WEBM), áudio (MP3, M4A, WAV) ou .txt com a transcrição · até 2 GB</span>
                </>
              )}
              <input type="file" aria-label="Arquivo do episódio" accept=".txt,audio/*,video/*,.mkv,.mov,.m4a" className="sr-only" onChange={(e) => escolher(e.target.files?.[0])} />
            </label>
            {midia && h && (
              <p className={cn("mt-2 flex items-center gap-1.5 text-[12.5px]", semChave ? "text-warn" : "text-ink-3")}>
                {semChave ? <>Para transcrever é preciso a chave da OpenAI. <Link to="/configuracoes#chaves" className="font-medium underline underline-offset-4">Cadastrar chave</Link></>
                  : <>Transcrição com Whisper{tipo === "video" ? ", depois de extrair a trilha de áudio" : ""}{duracaoMidia ? ` · custo estimado US$ ${(duracaoMidia / 60 * 0.006).toFixed(2)}` : ""}</>}
              </p>
            )}
          </Tabs.Content>
        </Tabs.Root>

        {progresso && (
          <div role="status" aria-label="Progresso do envio" className="rounded-[12px] border border-line bg-surface p-4">
            <div className="flex items-baseline justify-between text-[13px]">
              <span>{pct < 100 ? "Enviando o arquivo" : "Arquivo recebido, preparando o processamento"}</span>
              <span className="tnum font-mono text-[12px] text-ink-3">{tamanho(progresso.enviado)} de {tamanho(progresso.total)} · {pct}%</span>
            </div>
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-sunken">
              <div className="h-full rounded-full bg-accent transition-[width] duration-200" style={{ width: `${pct}%` }} />
            </div>
            {pct < 100 && <Button type="button" size="sm" variant="ghost" className="mt-2 -ml-2" onClick={() => cancelar.current?.()}>Cancelar envio</Button>}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <p className="text-[12.5px] text-ink-3">{h?.integracoes.claude ? "As peças serão geradas pelo Claude com o prompt v1." : <>Sem chave do Claude: as peças serão um rascunho extrativo, marcado para revisão. <Link to="/configuracoes#chaves" className="underline underline-offset-4">Cadastrar chave</Link></>}</p>
          <Button type="submit" variant="primary" size="lg" disabled={enviar.isPending || (modo === "arquivo" && (!arquivo || !!semChave))}>{enviar.isPending ? "Enviando" : "Adicionar ao acervo"}</Button>
        </div>
      </form>
    </Pagina>
  );
}

const ONDE_CRIAR: Record<Provedor, string> = {
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
  voyage: "https://dashboard.voyageai.com/",
};

function Chaves() {
  const { data, isLoading } = useQuery({ queryKey: ["chaves"], queryFn: api.chaves });
  useEffect(() => { if (location.hash === "#chaves") document.getElementById("chaves")?.scrollIntoView(); }, [data]);
  return (
    <section id="chaves" aria-labelledby="chaves-h" className="scroll-mt-6">
      <h2 id="chaves-h" className="text-[19px]">Chaves de API</h2>
      <p className="mt-1 max-w-[640px] text-[13.5px] text-ink-2">
        Ficam cifradas no servidor e são usadas só por ele. Esta tela nunca recebe a chave de volta: depois de salva, aparece apenas o começo e o fim.
      </p>
      {import.meta.env.VITE_DEMO ? (
        <p className="mt-4 rounded-[12px] border border-line bg-surface p-4 text-[13.5px] text-ink-2">
          Desativado na demonstração online: aqui o servidor roda dentro do seu navegador, sem acesso à internet, e uma página pública
          não deve receber chaves. Para transcrever vídeos e gerar com o Claude, rode o projeto localmente (instruções no README).
        </p>
      ) : (
        <>
          {isLoading && <Skeleton className="mt-4 h-48" />}
          <ul className="mt-4 divide-y divide-line rounded-[12px] border border-line bg-surface">
            {data?.map((c) => <ChaveLinha key={c.provedor} c={c} />)}
          </ul>
        </>
      )}
    </section>
  );
}

function ChaveLinha({ c }: { c: ChaveStatus }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [editando, setEditando] = useState(false);
  const [valor, setValor] = useState("");
  const [ver, setVer] = useState(false);
  const [resultado, setResultado] = useState<{ ok: boolean; mensagem: string } | null>(null);
  const atualizar = (chaves: ChaveStatus[]) => { qc.setQueryData(["chaves"], chaves); qc.invalidateQueries({ queryKey: ["health"] }); };
  const salvar = useMutation({
    mutationFn: () => api.salvarChave(c.provedor, valor),
    onSuccess: (r) => { atualizar(r.chaves); setValor(""); setEditando(false); setResultado({ ok: true, mensagem: "Chave aceita pelo provedor e salva cifrada." }); },
    onError: (e) => setResultado({ ok: false, mensagem: (e as Error).message }),
  });
  const testar = useMutation({ mutationFn: () => api.testarChave(c.provedor), onSuccess: setResultado, onError: (e) => setResultado({ ok: false, mensagem: (e as Error).message }) });
  const remover = useMutation({
    mutationFn: () => api.removerChave(c.provedor),
    onSuccess: (r) => { atualizar(r.chaves); setResultado(null); toast("Chave removida"); },
  });
  const id = `chave-${c.provedor}`;

  return (
    <li className="px-4 py-4">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-[14.5px] font-medium">
            <KeyRound className="size-4 text-ink-3" strokeWidth={1.7} />{c.nome}
          </p>
          <p className="mt-0.5 text-[12.5px] text-ink-3">{c.uso}</p>
        </div>
        <div className="text-right text-[12.5px]">
          {c.configurada ? (
            <span className="text-ok"><span className="font-mono">{c.mascara}</span> · {c.origem === "painel" ? "cadastrada aqui" : "do ambiente do servidor"}</span>
          ) : <span className="text-ink-3">não configurada</span>}
        </div>
      </div>

      {editando ? (
        <form className="mt-3 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); setResultado(null); salvar.mutate(); }}>
          <label htmlFor={id} className="sr-only">Chave da {c.nome}</label>
          <div className="flex h-10 min-w-0 flex-1 items-center rounded-[var(--radius-control)] border border-line-strong bg-paper focus-within:border-accent">
            <input id={id} type={ver ? "text" : "password"} value={valor} onChange={(e) => setValor(e.target.value)} autoFocus required
              autoComplete="off" spellCheck={false} placeholder={c.provedor === "anthropic" ? "sk-ant-…" : c.provedor === "openai" ? "sk-…" : "pa-…"}
              className="h-full min-w-0 flex-1 bg-transparent px-3 font-mono text-[13px] outline-none" />
            <button type="button" onClick={() => setVer(!ver)} aria-label={ver ? "Esconder chave" : "Mostrar chave"} className="px-3 text-ink-3 hover:text-ink">
              {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          <Button type="submit" variant="primary" disabled={salvar.isPending || valor.trim().length < 10}>
            {salvar.isPending ? <><LoaderCircle className="size-4 animate-spin" /> Verificando</> : "Verificar e salvar"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => { setEditando(false); setValor(""); setResultado(null); }}>Cancelar</Button>
          <a href={ONDE_CRIAR[c.provedor]} target="_blank" rel="noreferrer noopener" className="basis-full text-[12px] text-ink-3 underline-offset-4 hover:underline">
            Onde criar uma chave da {c.nome.split(" ")[0]}
          </a>
        </form>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant={c.configurada ? "outline" : "primary"} onClick={() => { setEditando(true); setResultado(null); }}>
            {c.configurada ? "Trocar chave" : "Adicionar chave"}
          </Button>
          {c.configurada && <Button size="sm" variant="ghost" onClick={() => testar.mutate()} disabled={testar.isPending}>{testar.isPending ? "Testando" : "Testar conexão"}</Button>}
          {c.origem === "painel" && <Button size="sm" variant="ghost" className="text-danger" onClick={() => remover.mutate()} disabled={remover.isPending}><Trash2 className="size-3.5" /> Remover</Button>}
        </div>
      )}
      {resultado && (
        <p role="status" className={cn("mt-2 flex items-center gap-1.5 text-[12.5px]", resultado.ok ? "text-ok" : "text-danger")}>
          {resultado.ok ? <Check className="size-3.5" /> : <X className="size-3.5" />}{resultado.mensagem}
        </p>
      )}
    </li>
  );
}

function Campo({ id, rotulo, valor, onChange, placeholder, obrigatorio = true }: {
  id: string; rotulo: string; valor: string; onChange: (v: string) => void; placeholder?: string; obrigatorio?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-[13px] font-medium">{rotulo}</label>
      <input id={id} value={valor} required={obrigatorio} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        className="mt-1.5 h-11 w-full rounded-[var(--radius-control)] border border-line-strong bg-surface px-3 outline-none focus:border-accent" />
    </div>
  );
}

export function EvalPage() {
  const { data, isLoading } = useQuery({ queryKey: ["avaliacao"], queryFn: api.avaliacao, staleTime: Infinity });
  const [aberta, setAberta] = useState<string | null>(null);
  return (
    <Pagina eyebrow="Avaliação da busca" titulo="Medir antes de mudar"
      sub="A busca acerta quando um dos 3 primeiros trechos cobre o minuto esperado, ou quando não devolve nada para perguntas fora do acervo. Mesmo critério do projeto original.">
      {isLoading && <Skeleton className="h-64" />}
      {data && Object.entries(data).map(([suite, versoes]) => (
        <section key={suite} className="mb-10">
          <h2 className="text-[19px]">Gabarito {suite}</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {Object.values(versoes).map((v) => (
              <button key={v.versao} onClick={() => setAberta(aberta === suite + v.versao ? null : suite + v.versao)}
                className={cn("rounded-[12px] border bg-surface p-4 text-left transition-colors", aberta === suite + v.versao ? "border-accent" : "border-line hover:border-line-strong")}>
                <p className="flex items-baseline justify-between"><span className="font-mono text-[12px] text-ink-3">{v.versao}</span><span className="tnum text-[12px] text-ink-3">{v.acertos}/{v.total}</span></p>
                <p className="tnum mt-1 font-serif text-[34px] leading-none">{Math.round(v.taxa * 100)}%</p>
                <p className="mt-2 text-[12px] text-ink-3">{{ v1: "palavras inteiras, trechos de 6 falas", v2: "pedaços de palavras, trechos de 3 falas", v3: "híbrida: v2 + vetores semânticos" }[v.versao]}</p>
              </button>
            ))}
          </div>
          {Object.values(versoes).filter((v) => aberta === suite + v.versao).map((v) => (
            <ul key={v.versao} className="mt-4 divide-y divide-line rounded-[12px] border border-line bg-surface">
              {v.linhas.map((l) => (
                <li key={l.pergunta} className="grid grid-cols-[20px_minmax(0,1fr)] gap-3 px-4 py-2.5 text-[13.5px] sm:grid-cols-[20px_minmax(0,1fr)_260px]">
                  {l.ok ? <Check className="mt-0.5 size-4 text-ok" /> : <X className="mt-0.5 size-4 text-danger" />}
                  <span>{l.pergunta}</span>
                  <span className="col-start-2 font-mono text-[11.5px] text-ink-3 sm:col-start-auto">{l.achados.join(" · ") || "nada encontrado"}</span>
                </li>
              ))}
            </ul>
          ))}
        </section>
      ))}
      <p className="text-[12.5px] text-ink-3">
        Leitura honesta: com o vetor local (LSA), a v3 empata com a v2 — a nota semântica acompanha a lexical neste acervo pequeno e fictício.
        O ganho esperado vem com embeddings de provedor (Voyage ou OpenAI), ainda não medidos aqui, e com a reescrita da pergunta pelo Claude.
      </p>
    </Pagina>
  );
}

export function SettingsPage() {
  const { data } = useQuery({ queryKey: ["config"], queryFn: api.config });
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const toast = useToast();
  const [voz, setVoz] = useState<string | null>(null);
  const salvar = useMutation({ mutationFn: () => api.salvarVoz(voz ?? ""), onSuccess: () => toast("Voz da marca salva"), onError: (e) => toast((e as Error).message, "erro") });
  return (
    <Pagina eyebrow="Configurações" titulo="Chaves, voz e integrações">
      <Chaves />
      <section aria-labelledby="voz-h" className="mt-12">
        <h2 id="voz-h" className="text-[19px]">Voz da marca</h2>
        <p className="mt-1 text-[13.5px] text-ink-2">Separada da lógica do prompt: a equipe ajusta o tom sem mexer nas regras.</p>
        <textarea rows={14} value={voz ?? data?.voz_da_marca ?? ""} onChange={(e) => setVoz(e.target.value)} aria-label="Voz da marca"
          className="mt-3 w-full rounded-[10px] border border-line-strong bg-surface p-4 font-mono text-[12.5px] leading-relaxed outline-none focus:border-accent" />
        <Button variant="primary" className="mt-2" onClick={() => salvar.mutate()} disabled={voz === null || salvar.isPending}>Salvar</Button>
      </section>

      <section className="mt-12" aria-labelledby="prompt-h">
        <h2 id="prompt-h" className="text-[19px]">Prompt {data?.prompt.versao}</h2>
        <p className="mt-1 text-[13.5px] text-ink-2">Versionado em <code className="font-mono text-[12px]">prompts/</code>; a versão usada fica gravada em cada pacote de conteúdo.</p>
        <pre className="mt-3 max-h-80 overflow-auto rounded-[10px] border border-line bg-surface p-4 font-mono text-[12px] leading-relaxed whitespace-pre-wrap scrollbar-thin">{data?.prompt.system}</pre>
      </section>

      <section className="mt-12" aria-labelledby="int-h">
        <h2 id="int-h" className="text-[19px]">Integrações</h2>
        <dl className="mt-3 divide-y divide-line rounded-[12px] border border-line bg-surface text-[14px]">
          {[
            ["ffmpeg (extrair o áudio do vídeo)", h?.integracoes.ffmpeg, "instale o ffmpeg"],
            ["Embeddings da busca", true, h?.integracoes.embeddings],
            ["n8n (webhook do workflow)", h?.integracoes.n8n, "defina N8N_TOKEN"],
          ].map(([n, ok, falta]) => (
            <div key={n as string} className="flex items-center gap-3 px-4 py-3">
              <dt className="flex-1">{n as string}</dt>
              <dd className={cn("text-[12.5px]", ok ? "text-ok" : "text-ink-3")}>{n === "Embeddings da busca" ? falta as string : ok ? "disponível" : falta as string}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-[13px] text-ink-2">
          No n8n, o workflow <code className="font-mono text-[12px]">workflows/episodio-para-conteudo.json</code> envia cada episódio para
          <code className="mx-1 font-mono text-[12px]">POST /api/integracoes/n8n/episodios</code> com o cabeçalho <code className="font-mono text-[12px]">X-Webhook-Token</code>,
          em paralelo à planilha de revisão.
        </p>
      </section>
    </Pagina>
  );
}
