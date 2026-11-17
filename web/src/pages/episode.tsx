import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, AudioLines, Check, CircleDashed, Download, Film, KeyRound, LoaderCircle, Music, Pencil, RotateCcw, Search, Sparkles, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { DropdownMenu } from "radix-ui";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { useToast } from "@/components/toast";
import { Button, buttonVariants, Skeleton } from "@/components/ui/primitives";
import { api, type Episodio, type Peca, type Segmento } from "@/lib/api";
import { cn, duracao, ETAPAS, MOTOR, segundos, tamanho, tituloLimpo } from "@/lib/utils";
import { StatusPill } from "./library";

type Capitulo = { inicio: string; titulo: string };
type Corte = { inicio: string; fim: string; gancho: string; por_que_funciona: string };

export function EpisodePage() {
  const { id } = useParams();
  const eid = Number(id);
  const [params, setParams] = useSearchParams();
  const { data: e, isLoading, isError } = useQuery({
    queryKey: ["episodio", eid], queryFn: () => api.episodio(eid),
    refetchInterval: (q) => (["recebido", "transcrevendo", "indexando", "gerando"].includes(q.state.data?.status ?? "") ? 1500 : false),
  });
  const alvo = params.get("t");
  const [foco, setFoco] = useState<number | null>(null);
  const [tocando, setTocando] = useState(false);
  const [acompanhar, setAcompanhar] = useState(true);
  const [filtro, setFiltro] = useState("");
  const [editando, setEditando] = useState<number | null>(null);
  const player = useRef<HTMLMediaElement | null>(null);

  const capitulos = useMemo(() => (e?.pacote?.pecas.find((p) => p.tipo === "capitulos")?.conteudo as Capitulo[] | undefined) ?? [], [e]);
  const cortes = useMemo(() => (e?.pacote?.pecas.find((p) => p.tipo === "cortes")?.conteudo as Corte[] | undefined) ?? [], [e]);
  const achados = useMemo(() => {
    const q = norm(filtro.trim());
    return q.length < 2 || !e ? null : e.segmentos.filter((s) => norm(s.texto).includes(q)).map((s) => s.id);
  }, [filtro, e]);

  const rolarAte = (inicio: number) => document.getElementById(`seg-${inicio}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  const irPara = (ts: string, atualizarUrl = true) => {
    const s = segundos(ts);
    const seg = e?.segmentos.filter((x) => x.inicio_s <= s).at(-1) ?? e?.segmentos[0];
    if (!seg) return;
    setFoco(seg.inicio_s);
    rolarAte(seg.inicio_s);
    if (player.current) { player.current.currentTime = s; player.current.play().catch(() => {}); }
    if (atualizarUrl) setParams({ t: ts }, { replace: true });
  };
  useEffect(() => { if (e && alvo) setTimeout(() => irPara(alvo, false), 120); }, [e?.id, alvo]); // eslint-disable-line react-hooks/exhaustive-deps

  // a fala que está tocando acende e, se "acompanhar" estiver ligado, a transcrição rola junto
  const aoTocar = () => {
    const t = player.current?.currentTime ?? 0;
    const seg = e?.segmentos.filter((x) => x.inicio_s <= t + 0.25).at(-1);
    if (seg && seg.inicio_s !== foco) {
      setFoco(seg.inicio_s);
      if (acompanhar && editando === null) rolarAte(seg.inicio_s);
    }
  };
  const proximoAchado = () => {
    if (!achados?.length || !e) return;
    const atual = e.segmentos.findIndex((s) => s.inicio_s === foco);
    const prox = e.segmentos.find((s, i) => i > atual && achados.includes(s.id)) ?? e.segmentos.find((s) => s.id === achados[0]);
    if (prox) { setFoco(prox.inicio_s); rolarAte(prox.inicio_s); }
  };

  if (isError) return <p className="p-10 text-ink-2">Episódio não encontrado. <Link className="underline" to="/">Voltar</Link></p>;
  if (isLoading || !e) return <div className="space-y-4 p-10"><Skeleton className="h-12 w-2/3" /><Skeleton className="h-96" /></div>;
  const capAtual = capitulos.filter((c) => segundos(c.inicio) <= (foco ?? -1)).at(-1);
  const video = e.midia?.tipo === "video";
  const eventosPlayer = {
    onTimeUpdate: aoTocar, onPlay: () => setTocando(true), onPause: () => setTocando(false),
  };
  const legendas = e.segmentos.length > 0 && <track kind="subtitles" srcLang="pt" label="Português" src={`/api/episodios/${e.id}/exportar?formato=vtt&v=${e.atualizado_em}`} />;

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-8 sm:px-10">
      <Link to="/" className="inline-flex items-center gap-1.5 text-[13px] text-ink-3 hover:text-ink"><ArrowLeft className="size-3.5" /> Biblioteca</Link>
      <header className="mt-5 flex flex-wrap items-end gap-x-6 gap-y-3">
        <span className="font-serif text-[64px] leading-[0.85] text-accent tnum">{e.numero.padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <h1 className="text-[30px] leading-tight sm:text-[36px]">{tituloLimpo(e.titulo)}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-[13.5px] text-ink-3">
            {e.convidados}<span aria-hidden>·</span><span className="font-mono text-[12.5px]">{duracao(e.duracao_s)}</span>
            <span aria-hidden>·</span><StatusPill status={e.status} />
            {e.exemplo && <span className="rounded-full border border-line px-2 py-px text-[11px]">exemplo fictício</span>}
            {e.midia && <span className="inline-flex items-center gap-1 text-[12.5px]">{video ? <Film className="size-3.5" /> : <Music className="size-3.5" />}{e.midia.nome}{e.midia.bytes ? ` · ${tamanho(e.midia.bytes)}` : ""}</span>}
          </p>
        </div>
        <Acoes e={e} />
      </header>

      {capitulos.length > 0 && (
        <div className="mt-8" aria-label="Capítulos">
          <div className="flex h-2 gap-[3px] overflow-hidden rounded-full">
            {capitulos.map((c, i) => {
              const ini = segundos(c.inicio), fim = i + 1 < capitulos.length ? segundos(capitulos[i + 1].inicio) : e.duracao_s;
              return <button key={c.inicio} onClick={() => irPara(c.inicio)} title={`${c.inicio} · ${c.titulo}`} aria-label={`Ir para ${c.titulo}`}
                style={{ flex: Math.max(1, fim - ini) }} className={cn("transition-colors", capAtual?.inicio === c.inicio ? "bg-accent" : "bg-line-strong hover:bg-ink-3")} />;
            })}
          </div>
          <p className="mt-2 text-[12.5px] text-ink-3">{capAtual ? <><span className="font-mono">{capAtual.inicio}</span> · {capAtual.titulo}</> : "Clique num capítulo, num corte ou numa fala para navegar."}</p>
        </div>
      )}

      {e.tem_midia && !video && (
        <audio ref={(el) => { player.current = el; }} controls preload="metadata" src={`/api/episodios/${e.id}/midia`} className="mt-4 w-full" {...eventosPlayer} />
      )}

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section aria-labelledby="transcricao-h" className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <h2 id="transcricao-h" className="eyebrow">Transcrição · {e.segmentos.length} falas</h2>
            {e.segmentos.length > 0 && (
              <div className="ml-auto flex items-center gap-3">
                {e.tem_midia && (
                  <label className="flex cursor-pointer items-center gap-1.5 text-[12.5px] text-ink-3">
                    <input type="checkbox" checked={acompanhar} onChange={(ev) => setAcompanhar(ev.target.checked)} className="accent-[var(--color-accent)]" />
                    Acompanhar a reprodução
                  </label>
                )}
                <form onSubmit={(ev) => { ev.preventDefault(); proximoAchado(); }}
                  className="flex h-9 w-[230px] items-center gap-2 rounded-[var(--radius-control)] border border-line-strong bg-surface px-2.5 focus-within:border-accent">
                  <Search className="size-3.5 shrink-0 text-ink-3" />
                  <input aria-label="Procurar na transcrição" value={filtro} onChange={(ev) => setFiltro(ev.target.value)} placeholder="Procurar na transcrição"
                    className="min-w-0 flex-1 bg-transparent text-[13px] outline-none" />
                  {achados && <span className="tnum shrink-0 font-mono text-[11px] text-ink-3">{achados.length}</span>}
                </form>
              </div>
            )}
          </div>
          {e.segmentos.length === 0 && (
            <p className="mt-6 border-y border-line py-10 text-center text-ink-3">
              {e.status === "erro" ? "A transcrição não foi concluída." : "A transcrição aparece aqui assim que o Whisper terminar."}
            </p>
          )}
          <ol className="mt-4 space-y-1">
            {e.segmentos.map((s) => {
              const cap = capitulos.find((c) => segundos(c.inicio) === s.inicio_s);
              const apagado = achados !== null && !achados.includes(s.id);
              return (
                <li key={s.id} id={`seg-${s.inicio_s}`} className="group relative scroll-mt-24">
                  {cap && <p className="mt-6 mb-2 font-serif text-[13px] italic text-accent-ink">{cap.titulo}</p>}
                  {editando === s.id ? (
                    <EditarFala eid={e.id} s={s} fechar={() => setEditando(null)} />
                  ) : (
                    <>
                      <button onClick={() => irPara(s.inicio)}
                        className={cn("grid w-full grid-cols-[52px_minmax(0,1fr)] gap-3 rounded-[8px] py-1.5 pr-10 pl-2 text-left transition-[background,opacity]",
                          foco === s.inicio_s ? (tocando ? "bg-accent-wash ring-1 ring-accent/30" : "bg-accent-wash") : "hover:bg-sunken/70", apagado && "opacity-35")}>
                        <span className="pt-[3px] font-mono text-[12px] text-ink-3">{s.inicio}</span>
                        <span className="font-serif text-[17px] leading-[1.65]">{achados ? destacarTermo(s.texto, filtro) : s.texto}</span>
                      </button>
                      <button onClick={() => setEditando(s.id)} aria-label={`Corrigir a fala de ${s.inicio}`}
                        className="absolute top-1.5 right-1.5 grid size-7 place-items-center rounded-[6px] text-ink-3 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-sunken hover:text-ink focus-visible:opacity-100">
                        <Pencil className="size-3.5" />
                      </button>
                    </>
                  )}
                </li>
              );
            })}
          </ol>
        </section>

        <aside className="space-y-8 lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:self-start lg:overflow-y-auto lg:pr-1 scrollbar-thin" aria-label="Produção e revisão">
          {e.tem_midia && video && (
            <video ref={(el) => { player.current = el; }} controls preload="metadata" playsInline src={`/api/episodios/${e.id}/midia`}
              aria-label="Vídeo do episódio" className="aspect-video w-full rounded-[12px] bg-black" {...eventosPlayer}>
              {legendas}
            </video>
          )}
          <Pipeline e={e} />
          {cortes.length > 0 && (
            <section aria-labelledby="cortes-h">
              <h2 id="cortes-h" className="eyebrow">Cortes para Reels</h2>
              <ul className="mt-3 space-y-2">
                {cortes.map((c) => (
                  <li key={c.inicio}>
                    <button onClick={() => irPara(c.inicio)} className="w-full rounded-[10px] border border-line bg-surface p-3 text-left hover:border-line-strong">
                      <span className="font-mono text-[12px] text-accent-ink">{c.inicio} → {c.fim} · {segundos(c.fim) - segundos(c.inicio)} s</span>
                      <span className="mt-1 block font-serif text-[15px] leading-snug">“{c.gancho}”</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {e.pacote && <Revisao e={e} />}
        </aside>
      </div>
    </div>
  );
}

const norm = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function destacarTermo(texto: string, termo: string) {
  const q = norm(termo.trim());
  const base = norm(texto);
  if (q.length < 2) return texto;
  const partes = [];
  let i = 0, j: number;
  while ((j = base.indexOf(q, i)) !== -1) {
    partes.push(texto.slice(i, j), <mark key={j} className="rounded-[3px] bg-accent/25 px-0.5 text-ink">{texto.slice(j, j + q.length)}</mark>);
    i = j + q.length;
  }
  partes.push(texto.slice(i));
  return partes;
}

function EditarFala({ eid, s, fechar }: { eid: number; s: Segmento; fechar: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [texto, setTexto] = useState(s.texto);
  const salvar = useMutation({
    mutationFn: () => api.editarSegmento(s.id, texto),
    onSuccess: (novo) => {
      qc.setQueryData<Episodio>(["episodio", eid], (ep) => ep && { ...ep, segmentos: ep.segmentos.map((x) => (x.id === novo.id ? novo : x)) });
      toast("Fala corrigida e busca atualizada");
      fechar();
    },
    onError: (err) => toast((err as Error).message, "erro"),
  });
  return (
    <form className="grid grid-cols-[52px_minmax(0,1fr)] gap-3 rounded-[8px] bg-surface px-2 py-2 ring-1 ring-accent/40"
      onSubmit={(ev) => { ev.preventDefault(); salvar.mutate(); }}>
      <span className="pt-2 font-mono text-[12px] text-ink-3">{s.inicio}</span>
      <div>
        <textarea autoFocus value={texto} onChange={(ev) => setTexto(ev.target.value)} rows={Math.max(2, Math.ceil(texto.length / 70))}
          aria-label={`Texto da fala de ${s.inicio}`}
          onKeyDown={(ev) => { if (ev.key === "Escape") fechar(); if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) salvar.mutate(); }}
          className="w-full resize-y rounded-[6px] border border-line-strong bg-paper p-2 font-serif text-[16px] leading-relaxed outline-none focus:border-accent" />
        <div className="mt-1.5 flex items-center gap-2">
          <Button size="sm" variant="primary" type="submit" disabled={salvar.isPending || !texto.trim() || texto === s.texto}>Salvar correção</Button>
          <Button size="sm" variant="ghost" type="button" onClick={fechar}>Cancelar</Button>
          <span className="ml-auto text-[11.5px] text-ink-3">Ctrl + Enter salva · Esc cancela</span>
        </div>
      </div>
    </form>
  );
}

function Acoes({ e }: { e: Episodio }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });
  const [confirmar, setConfirmar] = useState<"gerar" | "transcrever" | null>(null);
  const andamento = ["recebido", "transcrevendo", "indexando", "gerando"].includes(e.status);
  const refazer = useMutation({
    mutationFn: (transcrever: boolean) => api.reprocessar(e.id, transcrever),
    onSuccess: () => { setConfirmar(null); qc.invalidateQueries({ queryKey: ["episodio", e.id] }); toast("Processamento iniciado"); },
    onError: (err) => toast((err as Error).message, "erro"),
  });
  const formatos = [["txt", "Transcrição .txt"], ["srt", "Legenda .srt"], ["vtt", "Legenda .vtt"], ["md", "Pacote em Markdown"]];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button size="sm" disabled={!e.segmentos.length}><Download className="size-3.5" /> Exportar</Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content align="end" sideOffset={6} className="z-50 min-w-[210px] rounded-[10px] border border-line bg-surface p-1 shadow-lg">
            {formatos.map(([f, r]) => (
              <DropdownMenu.Item key={f} asChild>
                <a href={`/api/episodios/${e.id}/exportar?formato=${f}`} download className="block cursor-pointer rounded-[6px] px-3 py-2 text-[13.5px] outline-none data-[highlighted]:bg-sunken">{r}</a>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {confirmar ? (
        <span className="flex items-center gap-2 rounded-[8px] border border-line bg-surface py-1 pr-1 pl-3 text-[12.5px]">
          {confirmar === "gerar" ? "Gerar um pacote novo? As revisões atuais ficam no histórico." : "Transcrever de novo? As correções manuais se perdem."}
          <Button size="sm" variant="primary" onClick={() => refazer.mutate(confirmar === "transcrever")} disabled={refazer.isPending}>Confirmar</Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmar(null)}>Não</Button>
        </span>
      ) : (
        <>
          <Button size="sm" onClick={() => setConfirmar("gerar")} disabled={andamento || !e.segmentos.length}
            title={h?.integracoes.claude ? "Gera as 8 peças com o Claude" : "Sem chave do Claude: gera o rascunho extrativo"}>
            <Sparkles className="size-3.5" /> {h?.integracoes.claude ? "Gerar com Claude" : "Gerar de novo"}
          </Button>
          {e.tem_midia && <Button size="sm" variant="ghost" onClick={() => setConfirmar("transcrever")} disabled={andamento}><AudioLines className="size-3.5" /> Transcrever de novo</Button>}
        </>
      )}
    </div>
  );
}

function Pipeline({ e }: { e: Episodio }) {
  const qc = useQueryClient();
  const reprocessar = useMutation({ mutationFn: () => api.reprocessar(e.id, e.tem_midia && !e.segmentos.length), onSuccess: () => qc.invalidateQueries({ queryKey: ["episodio", e.id] }) });
  const andamento = ["recebido", "transcrevendo", "indexando", "gerando"].includes(e.status);
  if (!andamento && e.status !== "erro" && e.etapas.every((x) => x.status !== "erro")) {
    if (!e.pacote) return <p className="text-[12.5px] text-ink-3">Ainda sem pacote de conteúdo. Use “Gerar” no topo da página.</p>;
    return (
      <p className="text-[12.5px] text-ink-3">
        Processado por {MOTOR[e.pacote?.motor ?? ""] ?? e.pacote?.motor} · prompt {e.pacote?.prompt_versao}
        {e.pacote?.tokens_entrada ? ` · ${e.pacote.tokens_entrada.toLocaleString("pt-BR")} + ${e.pacote.tokens_saida.toLocaleString("pt-BR")} tokens` : ""}
      </p>
    );
  }
  return (
    <section aria-labelledby="pipe-h" className="rounded-[12px] border border-line bg-surface p-4">
      <h2 id="pipe-h" className="eyebrow">Processamento</h2>
      <ol className="mt-3 space-y-2.5">
        {e.etapas.map((x) => (
          <li key={x.nome} className="flex items-start gap-2.5 text-[13.5px]">
            {x.status === "ok" ? <Check className="mt-0.5 size-4 text-ok" /> : x.status === "rodando" ? <LoaderCircle className="mt-0.5 size-4 animate-spin text-accent" />
              : x.status === "erro" ? <X className="mt-0.5 size-4 text-danger" /> : <CircleDashed className="mt-0.5 size-4 text-ink-3" />}
            <span><span className={cn(x.status === "pendente" && "text-ink-3")}>{ETAPAS[x.nome] ?? x.nome}</span>
              {x.detalhe && <span className="block text-[12px] text-ink-3">{x.detalhe}</span>}</span>
          </li>
        ))}
      </ol>
      {e.status === "erro" && (
        <div className="mt-3">
          <p className="text-[12.5px] text-danger">{e.erro}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => reprocessar.mutate()}><RotateCcw className="size-3.5" /> Tentar de novo</Button>
            {/chave/i.test(e.erro ?? "") && <Link to="/configuracoes#chaves" className={buttonVariants({ size: "sm", variant: "ghost" })}><KeyRound className="size-3.5" /> Chaves de API</Link>}
          </div>
        </div>
      )}
    </section>
  );
}

function Revisao({ e }: { e: Episodio }) {
  const p = e.pacote!;
  const revisadas = p.pecas.filter((x) => x.status !== "pendente").length;
  return (
    <section aria-labelledby="rev-h">
      <div className="flex items-end justify-between">
        <h2 id="rev-h" className="eyebrow">Revisão humana · {revisadas}/{p.pecas.length}</h2>
        <span className="text-[12px] text-ink-3">nada é publicado sem aprovação</span>
      </div>
      {p.alertas.length > 0 && (
        <ul className="mt-3 space-y-1.5 rounded-[10px] border border-warn/30 bg-warn-wash p-3">
          {p.alertas.map((a) => <li key={a} className="flex gap-2 text-[12.5px] text-warn"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{a}</li>)}
        </ul>
      )}
      <ul className="mt-3 space-y-2">{p.pecas.map((x) => <PecaItem key={x.id} p={x} eid={e.id} />)}</ul>
    </section>
  );
}

function PecaItem({ p, eid }: { p: Peca; eid: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [aberta, setAberta] = useState(p.status === "pendente" && p.tipo === "resumo_curto");
  const [editando, setEditando] = useState(false);
  const texto = typeof p.conteudo === "string";
  const [rascunho, setRascunho] = useState(texto ? (p.conteudo as string) : JSON.stringify(p.conteudo, null, 2));
  const [erro, setErro] = useState<string | null>(null);
  const revisar = useMutation({
    mutationFn: ({ acao, conteudo }: { acao: string; conteudo?: unknown }) => api.revisar(p.id, acao, conteudo),
    onSuccess: (d) => { qc.setQueryData(["episodio", eid], d); qc.invalidateQueries({ queryKey: ["biblioteca"] }); setEditando(false); },
    onError: (e) => toast((e as Error).message, "erro"),
  });
  const salvar = () => {
    try {
      revisar.mutate({ acao: "editar", conteudo: texto ? rascunho : JSON.parse(rascunho) });
      setErro(null);
    } catch { setErro("O conteúdo não é um JSON válido."); }
  };
  const cor = { pendente: "text-ink-3", aprovada: "text-ok", editada: "text-ok", rejeitada: "text-danger" }[p.status];

  return (
    <li className="rounded-[10px] border border-line bg-surface">
      <button onClick={() => setAberta(!aberta)} aria-expanded={aberta} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <span className="flex-1 text-[14px] font-medium">{p.rotulo}</span>
        <span className={cn("text-[12px]", cor)}>{{ pendente: "pendente", aprovada: "aprovada", editada: "editada e aprovada", rejeitada: "rejeitada" }[p.status]}</span>
      </button>
      <AnimatePresence initial={false}>
        {aberta && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="border-t border-line px-4 py-3">
              {editando ? (
                <>
                  <textarea value={rascunho} onChange={(ev) => setRascunho(ev.target.value)} rows={texto ? 6 : 12} aria-label={`Editar ${p.rotulo}`}
                    className={cn("w-full resize-y rounded-[8px] border border-line-strong bg-paper p-3 outline-none focus:border-accent", texto ? "font-serif text-[15px]" : "font-mono text-[12px]")} />
                  {erro && <p className="mt-1 text-[12px] text-danger">{erro}</p>}
                </>
              ) : <Conteudo p={p} />}
              <div className="mt-3 flex flex-wrap gap-2">
                {editando ? (
                  <>
                    <Button size="sm" variant="primary" onClick={salvar} disabled={revisar.isPending}>Salvar e aprovar</Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditando(false)}>Cancelar</Button>
                  </>
                ) : p.status === "pendente" ? (
                  <>
                    <Button size="sm" variant="primary" onClick={() => revisar.mutate({ acao: "aprovar" })} disabled={revisar.isPending}><Check className="size-3.5" /> Aprovar</Button>
                    <Button size="sm" onClick={() => setEditando(true)}><Pencil className="size-3.5" /> Editar</Button>
                    <Button size="sm" variant="ghost" onClick={() => revisar.mutate({ acao: "rejeitar" })}><X className="size-3.5" /> Rejeitar</Button>
                  </>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => revisar.mutate({ acao: "reabrir" })}><RotateCcw className="size-3.5" /> Reabrir revisão</Button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

function Conteudo({ p }: { p: Peca }) {
  const c = p.conteudo as never;
  if (typeof c === "string") return <p className="whitespace-pre-line font-serif text-[15px] leading-relaxed">{c}</p>;
  if (p.tipo === "capitulos") return <ol className="space-y-1 text-[13.5px]">{(c as Capitulo[]).map((x) => <li key={x.inicio}><span className="font-mono text-[12px] text-ink-3">{x.inicio}</span> {x.titulo}</li>)}</ol>;
  if (p.tipo === "cortes") return <ul className="space-y-2 text-[13.5px]">{(c as Corte[]).map((x) => <li key={x.inicio}><span className="font-mono text-[12px] text-accent-ink">{x.inicio}–{x.fim}</span> {x.gancho}<span className="block text-[12px] text-ink-3">{x.por_que_funciona}</span></li>)}</ul>;
  if (p.tipo === "citacoes") return <ul className="space-y-2">{(c as string[]).map((x) => <li key={x} className="border-l-2 border-accent pl-3 font-serif text-[15px] italic">{x}</li>)}</ul>;
  if (p.tipo === "newsletter") {
    const n = c as { assunto: string; corpo: string };
    return <div><p className="text-[13px] text-ink-3">Assunto</p><p className="font-medium">{n.assunto}</p><p className="mt-2 whitespace-pre-line font-serif text-[15px]">{n.corpo}</p></div>;
  }
  return <pre className="overflow-x-auto font-mono text-[12px]">{JSON.stringify(c, null, 2)}</pre>;
}
