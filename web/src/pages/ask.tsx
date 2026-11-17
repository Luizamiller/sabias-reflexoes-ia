import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUp, CornerDownRight, LoaderCircle, ThumbsDown, ThumbsUp } from "lucide-react";
import { motion } from "motion/react";
import { Fragment, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { Button } from "@/components/ui/primitives";
import { api, perguntar, type Fonte } from "@/lib/api";
import { cn, MOTOR, tituloLimpo } from "@/lib/utils";

type Turno = {
  pergunta: string; resposta: string; fontes: Fonte[]; fim?: { motor: string; citacoes_invalidas: string[]; pergunta_id: number; chamou_modelo: boolean };
  erro?: string; util?: boolean;
};
const EXEMPLOS = ["O que já falamos sobre medo de mudar de carreira?", "Como lidar com um elogio sem se justificar?",
  "Por que sinto culpa quando gasto dinheiro?", "Qual a capital da Austrália?"];
const CITACAO = /\(Ep\.\s*([\w-]+)\s*[–-]\s*(\d{1,2}:\d{2})\)/g;

export function AskPage() {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [carregando, setCarregando] = useState(false);
  const fim = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const enviar = async (q: string) => {
    if (q.trim().length < 3 || carregando) return;
    setTexto("");
    setCarregando(true);
    const idx = turnos.length;
    setTurnos((t) => [...t, { pergunta: q.trim(), resposta: "", fontes: [] }]);
    const atualizar = (f: (t: Turno) => Turno) => setTurnos((ts) => ts.map((t, i) => (i === idx ? f(t) : t)));
    try {
      await perguntar(q.trim(), (ev) => {
        if (ev.tipo === "fontes") atualizar((t) => ({ ...t, fontes: ev.fontes }));
        else if (ev.tipo === "texto") atualizar((t) => ({ ...t, resposta: t.resposta + ev.texto }));
        else if (ev.tipo === "fim") atualizar((t) => ({ ...t, fim: ev }));
        else if (ev.tipo === "erro") atualizar((t) => ({ ...t, erro: ev.mensagem }));
        fim.current?.scrollIntoView({ block: "end", behavior: "smooth" });
      });
    } catch (e) {
      atualizar((t) => ({ ...t, erro: (e as Error).message }));
    } finally {
      setCarregando(false);
      qc.invalidateQueries({ queryKey: ["biblioteca"] });
    }
  };

  return (
    <div className="mx-auto flex min-h-dvh max-w-[860px] flex-col px-5 sm:px-10">
      <header className="pt-10">
        <p className="eyebrow">Pergunte ao acervo</p>
        <h1 className="mt-3 text-[34px] leading-tight">Respostas só com o que foi dito — <em className="text-accent-ink">e onde.</em></h1>
        <p className="mt-2 max-w-[600px] text-ink-2">Cada afirmação traz episódio e minuto. Se o acervo não fala do assunto, o assistente diz que não encontrou, sem chamar o modelo.</p>
      </header>

      <div className="flex-1 space-y-10 py-10">
        {!turnos.length && (
          <ul className="divide-y divide-line border-y border-line">
            {EXEMPLOS.map((e) => (
              <li key={e}>
                <button onClick={() => enviar(e)} className="flex w-full items-center gap-3 py-3.5 text-left font-serif text-[16px] text-ink-2 hover:text-ink">
                  <CornerDownRight className="size-4 text-ink-3" />{e}
                </button>
              </li>
            ))}
          </ul>
        )}
        {turnos.map((t, i) => <TurnoView key={i} t={t} onUtil={(u) => setTurnos((ts) => ts.map((x, j) => (j === i ? { ...x, util: u } : x)))} />)}
        <div ref={fim} />
      </div>

      <form onSubmit={(e) => { e.preventDefault(); enviar(texto); }}
        className="sticky bottom-4 mb-4 flex items-end gap-2 rounded-[14px] border border-line-strong bg-surface p-2 pl-4 shadow-[0_12px_40px_-18px_rgba(36,26,38,.35)] focus-within:border-accent">
        <label htmlFor="pergunta" className="sr-only">Sua pergunta</label>
        <textarea id="pergunta" rows={1} value={texto} onChange={(e) => setTexto(e.target.value)} maxLength={500}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(texto); } }}
          placeholder="O que já falamos sobre descanso?" className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-2 font-serif text-[16px] outline-none placeholder:text-ink-3" />
        <Button type="submit" variant="primary" size="icon" disabled={carregando || texto.trim().length < 3} aria-label="Perguntar">
          {carregando ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
        </Button>
      </form>
    </div>
  );
}

function TurnoView({ t, onUtil }: { t: Turno; onUtil: (u: boolean) => void }) {
  const idPorNumero = new Map(t.fontes.map((f) => [f.episodio, f.episodio_id]));
  const invalidas = new Set(t.fim?.citacoes_invalidas ?? []);
  return (
    <motion.article initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <p className="font-serif text-[22px] leading-snug">{t.pergunta}</p>
      <div className="mt-4 border-l-2 border-accent pl-5">
        {!t.resposta && !t.erro && <p className="flex items-center gap-2 text-[14px] text-ink-3"><LoaderCircle className="size-3.5 animate-spin" />Procurando no acervo</p>}
        {t.erro && <p className="text-[14px] text-danger">{t.erro}</p>}
        <div className="whitespace-pre-line font-serif text-[16.5px] leading-[1.75]">{comCitacoes(t.resposta, idPorNumero, invalidas)}</div>
        {t.fim && t.fim.citacoes_invalidas.length > 0 && (
          <p className="mt-3 flex items-start gap-2 rounded-[8px] bg-warn-wash px-3 py-2 text-[12.5px] text-warn">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> Citação que não corresponde a nenhum trecho consultado: {t.fim.citacoes_invalidas.join(", ")}. Confira antes de usar.
          </p>
        )}
      </div>

      {t.fontes.length > 0 && (
        <details className="mt-5 group" open={!t.fim?.chamou_modelo}>
          <summary className="cursor-pointer list-none text-[12.5px] font-medium text-ink-2 hover:text-ink">
            {t.fontes.length} trechos consultados <span className="text-ink-3 group-open:hidden">· mostrar</span>
          </summary>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {t.fontes.map((f) => (
              <li key={f.citacao + f.texto.slice(0, 10)}>
                <Link to={`/episodios/${f.episodio_id}?t=${f.inicio}`} className="block h-full rounded-[10px] border border-line bg-surface p-3 hover:border-line-strong">
                  <span className="flex items-center justify-between font-mono text-[11.5px] text-accent-ink"><span>{f.citacao}</span>
                    <span className="text-ink-3" title="nota lexical · nota semântica">{f.lexical.toFixed(2)}{f.semantica != null && ` · ${f.semantica.toFixed(2)}`}</span></span>
                  <span className="mt-1 block text-[12px] text-ink-3">{tituloLimpo(f.titulo)}</span>
                  <span className="mt-1.5 line-clamp-3 block font-serif text-[14px] leading-snug">{f.texto}</span>
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}

      {t.fim && (
        <div className="mt-4 flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
          <span>{MOTOR[t.fim.motor] ?? t.fim.motor}</span>
          <span aria-hidden>·</span>
          <span>Foi útil?</span>
          {[true, false].map((u) => (
            <button key={String(u)} aria-pressed={t.util === u} aria-label={u ? "Útil" : "Não foi útil"}
              onClick={async () => { await api.avaliarResposta(t.fim!.pergunta_id, u); onUtil(u); }}
              className={cn("rounded-[6px] p-1 hover:bg-sunken", t.util === u && "text-accent-ink")}>
              {u ? <ThumbsUp className="size-3.5" /> : <ThumbsDown className="size-3.5" />}
            </button>
          ))}
        </div>
      )}
    </motion.article>
  );
}

function comCitacoes(texto: string, ids: Map<string, number>, invalidas: Set<string>): ReactNode[] {
  const out: ReactNode[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(CITACAO)) {
    out.push(<Fragment key={`t${m.index}`}>{texto.slice(ultimo, m.index)}</Fragment>);
    const [, ep, ts] = m;
    const id = ids.get(ep);
    const invalida = invalidas.has(`Ep. ${ep} – ${ts}`);
    out.push(id && !invalida ? (
      <Link key={`c${m.index}`} to={`/episodios/${id}?t=${ts}`}
        className="mx-0.5 inline-flex items-center rounded-[5px] bg-accent-wash px-1.5 py-px align-baseline font-mono text-[11.5px] text-accent-ink not-italic hover:underline">
        Ep. {ep} · {ts}
      </Link>
    ) : <span key={`c${m.index}`} className="mx-0.5 rounded-[5px] bg-warn-wash px-1.5 py-px font-mono text-[11.5px] text-warn line-through">Ep. {ep} · {ts}</span>);
    ultimo = (m.index ?? 0) + m[0].length;
  }
  out.push(<Fragment key="fim">{texto.slice(ultimo)}</Fragment>);
  return out;
}
