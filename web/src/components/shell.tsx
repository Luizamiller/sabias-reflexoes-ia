import { useQuery } from "@tanstack/react-query";
import { BookOpen, FlaskConical, Menu, MessageSquareQuote, Moon, Plus, Search, Settings2, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", rotulo: "Biblioteca", icone: BookOpen, end: true },
  { to: "/perguntar", rotulo: "Pergunte ao acervo", icone: MessageSquareQuote },
  { to: "/busca", rotulo: "Busca", icone: Search },
  { to: "/novo", rotulo: "Novo episódio", icone: Plus },
  { to: "/avaliacao", rotulo: "Avaliação da busca", icone: FlaskConical },
  { to: "/configuracoes", rotulo: "Configurações", icone: Settings2 },
];

function useTema() {
  const [escuro, setEscuro] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", escuro);
    try { localStorage.setItem("tema", escuro ? "escuro" : "claro"); } catch { /* ignora */ }
  }, [escuro]);
  return [escuro, setEscuro] as const;
}

export function Shell() {
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });
  const [escuro, setEscuro] = useTema();
  const [aberto, setAberto] = useState(false);
  const loc = useLocation();
  useEffect(() => setAberto(false), [loc.pathname]);

  const nav = (
    <nav aria-label="Principal" className="flex flex-col gap-0.5 px-3">
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.end}
          className={({ isActive }) => cn("flex items-center gap-2.5 rounded-[8px] px-3 py-2 text-[14px] transition-colors",
            isActive ? "bg-white/10 text-[#f4ead9]" : "text-[#bfaeb8] hover:bg-white/5 hover:text-[#f4ead9]")}>
          <n.icone className="size-4" strokeWidth={1.7} />{n.rotulo}
        </NavLink>
      ))}
    </nav>
  );
  const integracoes = h && (
    <ul className="space-y-1.5 px-6 text-[12px] text-[#9d8c97]">
      {[["Claude", h.integracoes.claude], ["Whisper", h.integracoes.whisper], ["n8n", h.integracoes.n8n]].map(([n, ok]) => (
        <li key={n as string} className="flex items-center gap-2">
          <span className={cn("size-1.5 rounded-full", ok ? "bg-[#8fc49a]" : "bg-[#5d4d58]")} />{n as string}
          <span className="ml-auto">{ok ? "conectado" : "sem chave"}</span>
        </li>
      ))}
      <li className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-[#d9a55b]" />Embeddings<span className="ml-auto">{h.integracoes.embeddings}</span></li>
    </ul>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col bg-plum py-6 lg:flex">
        <Marca />
        <div className="mt-8">{nav}</div>
        <div className="mt-auto space-y-4">
          {integracoes}
          <button onClick={() => setEscuro(!escuro)} className="mx-6 flex items-center gap-2 text-[12px] text-[#9d8c97] hover:text-[#f4ead9]">
            {escuro ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}{escuro ? "Tema claro" : "Tema escuro"}
          </button>
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-plum px-4 lg:hidden">
        <Marca compacta />
        <button onClick={() => setAberto(!aberto)} aria-label={aberto ? "Fechar menu" : "Abrir menu"} aria-expanded={aberto} className="text-[#f4ead9]">
          {aberto ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </header>
      {aberto && <div className="fixed inset-x-0 top-14 z-30 bg-plum pb-4 lg:hidden">{nav}</div>}

      <main className="min-w-0"><Outlet /></main>
    </div>
  );
}

function Marca({ compacta }: { compacta?: boolean }) {
  return (
    <NavLink to="/" className={cn("block", compacta ? "" : "px-6")}>
      <span className="block font-serif text-[22px] leading-none text-[#f4ead9] italic">Acervo</span>
      {!compacta && <span className="mt-1.5 block text-[11px] tracking-[0.12em] text-[#9d8c97] uppercase">Às Sábias Reflexões</span>}
    </NavLink>
  );
}
