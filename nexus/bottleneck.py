"""Gravação de sessão (ex.: jogo) e identificação do componente que limita o desempenho."""
import statistics
import time


def _pct(valores, p):
    v = sorted(x for x in valores if x is not None)
    if not v:
        return None
    return v[min(len(v) - 1, int(len(v) * p / 100))]


def _med(valores):
    v = [x for x in valores if x is not None]
    return statistics.mean(v) if v else None


class Gravador:
    def __init__(self):
        self.ativo = False
        self.amostras = []
        self.inicio = 0.0

    def iniciar(self):
        self.ativo, self.amostras, self.inicio = True, [], time.time()

    def parar(self):
        self.ativo = False
        return time.time() - self.inicio

    def add(self, s):
        if self.ativo:
            vram = None
            if s.get("gpu_vram") and s["gpu_vram"][1]:
                vram = s["gpu_vram"][0] / s["gpu_vram"][1] * 100
            self.amostras.append({k: s.get(k) for k in ("cpu", "ram_pct", "cpu_temp", "gpu_temp", "gpu_util",
                                                         "gpu_throttle", "fps")} | {"vram": vram})

    @property
    def duracao(self):
        return time.time() - self.inicio if self.ativo else 0


def _limitada(thr):
    return bool(thr) and thr not in ("0x0000000000000000", "0x0", "Not Active", "[N/A]")


def analisar(amostras):
    """Retorna (resumo dict, achados [(titulo, explicacao, status, gravidade)])."""
    if len(amostras) < 5:
        return {}, [("Sessão muito curta", "Grave pelo menos alguns minutos de uso para uma análise confiável.", "suspeita", "info")]
    col = lambda k: [a[k] for a in amostras]  # noqa: E731
    r = {"amostras": len(amostras),
         "cpu_med": _med(col("cpu")), "cpu_p95": _pct(col("cpu"), 95),
         "gpu_med": _med(col("gpu_util")), "gpu_p95": _pct(col("gpu_util"), 95),
         "ram_max": max((x for x in col("ram_pct") if x is not None), default=None),
         "vram_max": max((x for x in col("vram") if x is not None), default=None),
         "cpu_temp_max": max((x for x in col("cpu_temp") if x is not None), default=None),
         "gpu_temp_max": max((x for x in col("gpu_temp") if x is not None), default=None),
         "fps_med": _med(col("fps")), "fps_1pct": _pct([x for x in col("fps") if x], 1)}
    lim = [a for a in amostras if _limitada(a.get("gpu_throttle")) and (a.get("gpu_util") or 0) > 50]
    r["gpu_limitada_pct"] = len(lim) / len(amostras) * 100
    A = []
    gm, cm, c95 = r["gpu_med"], r["cpu_med"], r["cpu_p95"]
    if gm is not None and cm is not None:
        if gm < 70 and (c95 or 0) >= 85:
            A.append(("Processador limitando o desempenho",
                      f"A CPU chegou a {c95:.0f}% enquanto a GPU ficou em apenas {gm:.0f}%. A placa de vídeo está esperando o processador.",
                      "confirmado" if cm >= 80 else "suspeita", "alto"))
        elif gm >= 95:
            A.append(("Placa de vídeo no limite (normal em jogos)",
                      f"A GPU ficou em média {gm:.0f}%. É o comportamento esperado quando o jogo é limitado pela placa: "
                      "para ganhar FPS reduza resolução, sombras ou ative DLSS/FSR.", "confirmado", "info"))
        elif gm < 50 and cm < 60:
            A.append(("Nenhum componente no limite",
                      "CPU e GPU tiveram folga. Se houve travadas, a causa pode estar no jogo, no disco ou na rede.",
                      "suspeita", "info"))
    if r["ram_max"] and r["ram_max"] >= 92:
        A.append(("Memória RAM esgotada", f"A RAM chegou a {r['ram_max']:.0f}%. Acima disso o Windows usa o disco como memória, causando travadas.",
                  "confirmado", "alto"))
    if r["vram_max"] and r["vram_max"] >= 95:
        A.append(("Memória de vídeo (VRAM) esgotada", f"A VRAM chegou a {r['vram_max']:.0f}%. Reduza a qualidade das texturas.",
                  "confirmado", "médio"))
    for chave, nome, lim_ in (("cpu_temp_max", "processador", 90), ("gpu_temp_max", "placa de vídeo", 85)):
        if r[chave] and r[chave] >= lim_:
            A.append((f"Temperatura alta no {nome}", f"Pico de {r[chave]:.0f} °C. Em temperaturas assim o hardware reduz a velocidade.",
                      "confirmado", "alto"))
    if r["gpu_limitada_pct"] >= 20:
        A.append(("GPU reduzindo a frequência", f"Em {r['gpu_limitada_pct']:.0f}% do tempo a NVIDIA reportou limitação "
                  "(térmica, de energia ou de driver).", "confirmado", "médio"))
    if r["fps_med"]:
        fps = [x for x in col("fps") if x]
        quedas = sum(1 for x in fps if x < r["fps_med"] * 0.6)
        r["quedas_pct"] = quedas / len(fps) * 100
        if r["quedas_pct"] >= 5:
            A.append(("Quedas de desempenho detectadas",
                      f"{r['quedas_pct']:.0f}% do tempo o FPS ficou abaixo de 60% da média ({r['fps_med']:.0f}). "
                      "Veja acima qual componente estava no limite nesses momentos.", "confirmado", "médio"))
    if not A:
        A.append(("Nenhum gargalo identificado", "Os recursos ficaram dentro do esperado durante a sessão.", "suspeita", "info"))
    return r, A


def texto(r, achados, duracao):
    L = [f"Sessão de {duracao / 60:.1f} min ({r.get('amostras', 0)} amostras)", ""]
    f = lambda v, u="%": "N/D" if v is None else f"{v:.0f}{u}"  # noqa: E731
    if r:
        L += [f"CPU: média {f(r['cpu_med'])} • pico(95%) {f(r['cpu_p95'])} • temp máx {f(r['cpu_temp_max'], '°C')}",
              f"GPU: média {f(r['gpu_med'])} • pico(95%) {f(r['gpu_p95'])} • temp máx {f(r['gpu_temp_max'], '°C')}",
              f"RAM máx {f(r['ram_max'])} • VRAM máx {f(r['vram_max'])}"]
        if r.get("fps_med"):
            L.append(f"FPS: média {f(r['fps_med'], '')} • 1% piores {f(r['fps_1pct'], '')}")
        L.append("")
    for t, e, st, g in achados:
        L += [f"[{g.upper()} | {st}] {t}", f"   {e}", ""]
    return "\n".join(L)
