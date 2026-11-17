import { duracao, segundos, tituloLimpo } from "../utils";

test("tempo do episódio", () => {
  expect(duracao(205)).toBe("3:25");
  expect(duracao(3725)).toBe("1 h 2 min");
  expect(segundos("02:25")).toBe(145);
});

test("título sem o marcador de exemplo", () => {
  expect(tituloLimpo("[EXEMPLO FICTÍCIO] O preço da culpa")).toBe("O preço da culpa");
});
