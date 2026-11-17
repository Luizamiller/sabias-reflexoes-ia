import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { Skeleton } from "@/components/ui/primitives";
import { api, type EpisodioResumo } from "@/lib/api";
import { cn, duracao, STATUS, tituloLimpo } from "@/lib/utils";

export function StatusPill({ status }: { status: string }) {
  const s = STATUS[status] ?? { rotulo: status, tom: "neutro" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[12px]",
      { ok: "text-ok", atencao: "text-accent-ink", erro: "text-danger", andamento: "text-ink-2", neutro: "text-ink-3" }[s.tom])}>
      <span className={cn("size-1.5 rounded-full", { ok: "bg-ok", atencao: "bg-accent", erro: "bg-danger", andamento: "animate-pulse bg-ink-3", neutro: "bg-ink-3" }[s.tom])} />
      {s.rotulo}
    </span>
  );
}

export function LibraryPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["biblioteca"], queryFn: api.biblioteca,
    refetchInterval: (q) => (q.state.data?.episodios.some((e) => ["recebido", "transcrevendo", "indexando", "gerando"].includes(e.status)) ? 2000 : false),
  });
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-[1080px] px-5 py-10 sm:px-10">
      <header className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-end">
        <div>
          <p className="eyebrow">Biblioteca</p>
          <h1 className="mt-3 text-[38px] leading-[1.1] sm:text-[46px]">Tudo o que já foi dito, <em className="text-accent-ink">com episódio e minuto.</em></h1>
          <p className="mt-4 max-w-[560px] text-[15.5px] text-ink-2">
            Cada episódio entra como transcrição, vira oito peças de conteúdo para revisão e passa a responder perguntas no assistente.
          </p>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) navigate(`/busca?q=${encodeURIComponent(q.trim())}`); }}
          className="flex items-center gap-2 rounded-[12px] border border-line-strong bg-surface px-3.5 focus-within:border-accent">
          <Search className="size-4 text-ink-3" />
          <label htmlFor="busca-home" className="sr-only">Buscar no acervo</label>
          <input id="busca-home" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar: medo de mudar de carreira"
            className="h-12 min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-3" />
        </form>
      </header>

      <dl className="mt-10 grid grid-cols-2 border-y border-line sm:grid-cols-4">
        {[
          ["Episódios", data?.totais.episodios],
          ["Horas transcritas", data?.totais.horas.toLocaleString("pt-BR")],
          ["Trechos pesquisáveis", data?.totais.trechos],
          ["Aguardando revisão", data?.totais.em_revisao],
        ].map(([k, v], i) => (
          <div key={k as string} className={cn("py-5", i > 0 && "sm:border-l sm:border-line sm:pl-6", i % 2 === 1 && "border-l border-line pl-6")}>
            <dt className="text-[12px] text-ink-3">{k}</dt>
            <dd className="tnum mt-1 font-serif text-[30px] leading-none">{v ?? "—"}</dd>
          </div>
        ))}
      </dl>

      <section className="mt-10" aria-labelledby="eps-h">
        <div className="flex items-end justify-between">
          <h2 id="eps-h" className="text-[22px]">Episódios</h2>
          <Link to="/novo" className="text-[13px] font-medium text-accent-ink hover:underline">Adicionar episódio</Link>
        </div>
        <ol className="mt-4 divide-y divide-line border-y border-line">
          {isLoading && Array.from({ length: 4 }).map((_, i) => <li key={i} className="py-5"><Skeleton className="h-10" /></li>)}
          {data?.episodios.map((e, i) => <Linha key={e.id} e={e} i={i} />)}
        </ol>
      </section>
    </div>
  );
}

function Linha({ e, i }: { e: EpisodioResumo; i: number }) {
  const progresso = e.pecas_total ? e.pecas_revisadas / e.pecas_total : 0;
  return (
    <motion.li initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 8) * 0.035 }}>
      <Link to={`/episodios/${e.id}`} className="group grid grid-cols-[56px_minmax(0,1fr)_auto] items-center gap-4 py-5 sm:grid-cols-[72px_minmax(0,1fr)_160px_120px_20px]">
        <span className="font-serif text-[34px] leading-none text-ink-3 tnum transition-colors group-hover:text-accent">{e.numero.padStart(2, "0")}</span>
        <span className="min-w-0">
          <span className="block truncate font-serif text-[19px] leading-snug">{tituloLimpo(e.titulo)}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-ink-3">
            {e.convidados}<span aria-hidden>·</span><span className="font-mono text-[12px]">{duracao(e.duracao_s)}</span>
            {e.exemplo && <span className="rounded-full border border-line px-2 py-px text-[11px]">exemplo fictício</span>}
            {e.origem === "n8n" && <span className="rounded-full border border-line px-2 py-px text-[11px]">via n8n</span>}
          </span>
        </span>
        <span className="hidden sm:block"><StatusPill status={e.status} /></span>
        <span className="hidden sm:block">
          <span className="flex items-center justify-between text-[12px] text-ink-3"><span>peças</span><span className="tnum">{e.pecas_revisadas}/{e.pecas_total || 8}</span></span>
          <span className="mt-1 block h-1 overflow-hidden rounded-full bg-sunken"><span className="block h-full bg-ok" style={{ width: `${progresso * 100}%` }} /></span>
        </span>
        <ArrowRight className="size-4 text-ink-3 transition-transform group-hover:translate-x-0.5" />
      </Link>
    </motion.li>
  );
}
