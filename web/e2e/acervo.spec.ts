import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 900 } });

test("biblioteca lista os episódios e abre a transcrição no minuto citado", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Tudo o que já foi dito/ })).toBeVisible();
  await expect(page.getByText("O preço da culpa")).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/biblioteca.png" });
  await page.goto("/episodios/3?t=02:25");
  await expect(page.getByRole("button", { name: /02:25 E quando a compra foi/ })).toBeVisible();
  await page.waitForTimeout(800);
  await page.screenshot({ path: "test-results/episodio.png" });
});

test("assistente responde com trechos e citações, e diz quando não encontra", async ({ page }) => {
  await page.goto("/perguntar");
  await page.getByLabel("Sua pergunta").fill("como lidar com elogio sem se justificar");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/trechos consultados/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Ep\. 4 · / }).first()).toBeVisible();
  await page.getByLabel("Sua pergunta").fill("qual a capital da Austrália");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Não encontrei esse assunto")).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/assistente.png", fullPage: true });
});

test("revisão humana de uma peça", async ({ page }) => {
  await page.goto("/episodios/5");
  await page.getByRole("button", { name: /Resumo curto/ }).click();
  const reabrir = page.getByRole("button", { name: "Reabrir revisão" });
  if (await reabrir.isVisible()) await reabrir.click();  // execução anterior já aprovou
  await page.getByRole("button", { name: "Aprovar", exact: true }).first().click();
  await expect(page.getByText("aprovada").first()).toBeVisible();
});

test("busca destaca os termos e mostra as notas", async ({ page }) => {
  await page.goto("/busca?q=amigos sumindo depois dos trinta");
  await expect(page.getByText(/Ep\. 5 –/).first()).toBeVisible();
  await expect(page.locator("mark").first()).toBeVisible();
});

test("chaves de API: formato errado é recusado e a chave nunca volta para a tela", async ({ page }) => {
  await page.goto("/configuracoes");
  const openai = page.getByRole("listitem").filter({ hasText: "OpenAI (Whisper)" });
  await openai.getByRole("button", { name: /Adicionar chave|Trocar chave/ }).click();
  await openai.getByLabel("Chave da OpenAI (Whisper)").fill("chave-de-teste-sem-prefixo-0000");
  await openai.getByRole("button", { name: "Verificar e salvar" }).click();
  await expect(openai.getByRole("status")).toContainText("começam com");
  const chaves = await (await page.request.get("/api/config/chaves")).text();
  expect(chaves).not.toContain("chave-de-teste");
});

test("novo episódio aceita vídeo e mostra o que falta para transcrever", async ({ page }) => {
  await page.goto("/novo");
  await page.getByLabel("Arquivo do episódio").setInputFiles({ name: "episodio-12.mp4", mimeType: "video/mp4", buffer: Buffer.alloc(2048) });
  await expect(page.getByText("episodio-12.mp4")).toBeVisible();
  await expect(page.getByText(/vídeo · 2 KB/)).toBeVisible();
  const h = await (await page.request.get("/api/health")).json();
  if (!h.integracoes.whisper) {
    await expect(page.getByRole("link", { name: "Cadastrar chave" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Adicionar ao acervo" })).toBeDisabled();
  }
});

test("episódio: procurar na transcrição e exportar legenda", async ({ page }) => {
  await page.goto("/episodios/3");
  await page.getByLabel("Procurar na transcrição").fill("compra");
  await expect(page.locator("ol mark").first()).toBeVisible();
  await page.getByRole("button", { name: "Exportar" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("menuitem", { name: "Legenda .srt" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.srt$/);
});
