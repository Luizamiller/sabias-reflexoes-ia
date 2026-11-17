import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import "./index.css";
import { Shell } from "@/components/shell";
import { ToastProvider } from "@/components/toast";
import { aplicarTemaInicial } from "@/lib/utils";
import { LibraryPage } from "@/pages/library";

aplicarTemaInicial();
const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

const lazy = <K extends string>(imp: () => Promise<Record<K, React.ComponentType>>, nome: K) =>
  async () => ({ Component: (await imp())[nome] });

if (import.meta.env.VITE_DEMO) await (await import("./demo/ponte")).iniciarDemo();

const router = createBrowserRouter([
  {
    element: <ToastProvider><Shell /></ToastProvider>,
    children: [
      { path: "/", element: <LibraryPage /> },
      { path: "/episodios/:id", lazy: lazy(() => import("@/pages/episode"), "EpisodePage") },
      { path: "/perguntar", lazy: lazy(() => import("@/pages/ask"), "AskPage") },
      { path: "/busca", lazy: lazy(() => import("@/pages/tools"), "SearchPage") },
      { path: "/novo", lazy: lazy(() => import("@/pages/tools"), "NewEpisodePage") },
      { path: "/avaliacao", lazy: lazy(() => import("@/pages/tools"), "EvalPage") },
      { path: "/configuracoes", lazy: lazy(() => import("@/pages/tools"), "SettingsPage") },
    ],
  },
], { basename: import.meta.env.BASE_URL.replace(/\/$/, "") || "/" });

const preload = () => { import("@/pages/episode"); import("@/pages/ask"); import("@/pages/tools"); };
if ("requestIdleCallback" in window) requestIdleCallback(preload); else setTimeout(preload, 1500);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
