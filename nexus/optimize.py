"""Perfis de Game Boost / Work Boost, preferência de GPU e controle de processos."""
import os

from .core import HIST, IS_WIN, log, ps, aplicar_plano
from .hardware import resumo_gpu

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

PERFIS = {
    "maximo": dict(nome="Máximo desempenho", plano="maximo",
                   desc="Plano de energia de desempenho máximo. Mais consumo e calor; ideal para PC de mesa."),
    "equilibrado": dict(nome="Equilibrado", plano="equilibrado",
                        desc="Plano Equilibrado do Windows: bom desempenho com consumo moderado."),
    "baixo_consumo": dict(nome="Baixo consumo", plano="economia",
                          desc="Economia de energia. Prolonga a bateria em notebooks, reduz desempenho."),
    "baixo_ram": dict(nome="Baixo consumo de memória", plano="equilibrado",
                      desc="Plano equilibrado + lista dos processos que mais usam RAM para você fechar."),
    "antigo": dict(nome="Hardware antigo", plano="equilibrado",
                   desc="Plano equilibrado + sugestões de configurações gráficas leves para PCs antigos."),
}

PROTEGIDOS = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
              "lsass.exe", "svchost.exe", "winlogon.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe",
              "memory compression", "nexuspc.exe", "python.exe", "pythonw.exe", "msmpeng.exe"}


def aplicar_perfil(chave):
    p = PERFIS[chave]
    return aplicar_plano(p["plano"], f"Perfil '{p['nome']}'")


def dicas_graficas(inv, perfil):
    """Recomendações de configurações de jogo conforme o hardware real."""
    gpus = inv.get("gpu", [])
    vram = max((resumo_gpu(g) for g in gpus), default=0) / 1024 ** 3
    nomes = " ".join((g.get("Name") or "") for g in gpus).lower()
    ram = sum((m.get("Capacity") or 0) for m in inv.get("ram", [])) / 1024 ** 3
    integrada = ("intel" in nomes and "arc" not in nomes) or ("radeon graphics" in nomes) or not gpus
    d = []
    if integrada:
        d += ["Placa de vídeo integrada: use resolução 720p–900p, texturas baixas e sombras no mínimo.",
              "Ative FSR/XeSS (quando o jogo tiver) em modo Desempenho.",
              "Feche navegador e launchers: a GPU integrada divide a RAM com o sistema."]
    elif 0 < vram <= 4:
        d += [f"GPU com ~{vram:.0f} GB de VRAM: texturas em Média e sombras Média; evite resolução acima de 1080p.",
              "Ative DLSS/FSR em Equilibrado para ganhar FPS."]
    else:
        d += ["VRAM confortável: priorize texturas Alta; reduza sombras e volumetria se faltar FPS.",
              "Ative DLSS/FSR em Qualidade para manter nitidez."]
    if 0 < ram < 12:
        d.append(f"Com {ram:.0f} GB de RAM, feche programas em segundo plano antes de jogar.")
    if perfil == "antigo":
        d.append("Desative V-Sync, Motion Blur, Profundidade de Campo e reflexos em tempo real.")
    if perfil == "maximo":
        d.append("Use monitor com taxa de atualização alta e limite o FPS ao refresh para evitar calor.")
    return d


def definir_gpu_alta(exe):
    """Faz o Windows usar a GPU de alto desempenho para um programa (reversível)."""
    if not IS_WIN or not os.path.isfile(exe):
        return False, "Arquivo não encontrado."
    chave = "HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences"
    e = exe.replace("'", "''")
    cod, saida = ps(f"New-Item -Path '{chave}' -Force | Out-Null; "
                    f"try {{ (Get-ItemProperty -Path '{chave}' -Name '{e}' -ErrorAction Stop).'{e}' }} catch {{ '' }}")
    anterior = saida.strip()
    cod, saida = ps(f"Set-ItemProperty -Path '{chave}' -Name '{e}' -Value 'GpuPreference=2;'")
    if cod != 0:
        return False, saida.strip()[:150]
    HIST.registrar("GPU de alto desempenho", exe, "Aplicado",
                   {"tipo": "gpu_pref", "exe": exe, "anterior": anterior or None})
    return True, "Programa configurado para usar a GPU de alto desempenho."


def encerrar_processo(pid, nome):
    if not psutil:
        return False, "psutil indisponível"
    if nome.lower() in PROTEGIDOS:
        return False, f"{nome} é um processo essencial e não será encerrado."
    try:
        psutil.Process(pid).terminate()
        HIST.registrar("Encerrar processo", nome, "Encerrado")
        return True, f"{nome} encerrado."
    except psutil.Error as e:
        return False, str(e)


# ------------------------------------------------------------------- Work Boost
WORK_PERFIS = {
    "navegacao": dict(curto="Navegação", nome="Navegação (muitas abas)", plano="equilibrado", ram_min=8,
                      base=["Ative a suspensão/economia de memória de abas do navegador.",
                            "Extensões pesam: desative as que não usa."]),
    "imagens": dict(curto="Imagens", nome="Edição de imagens", plano="maximo", ram_min=16,
                    base=["Mantenha os arquivos de trabalho em SSD.",
                          "Feche navegadores com muitas abas ao abrir o editor."]),
    "video": dict(curto="Vídeo", nome="Edição de vídeo", plano="maximo", ram_min=16,
                  base=["Use SSD para o projeto e o cache de renderização.",
                        "Use proxies/mídia otimizada se a prévia engasgar.",
                        "Evite outros programas pesados durante a renderização."]),
    "programacao": dict(curto="Programação", nome="Programação", plano="equilibrado", ram_min=16,
                        base=["Exclua pastas de projetos (node_modules, build) da varredura do antivírus.",
                              "Máquinas virtuais/Docker consomem muita RAM: pause as que não está usando."]),
    "escritorio": dict(curto="Escritório", nome="Aplicativos de escritório", plano="equilibrado", ram_min=8,
                       base=["O plano Equilibrado atende bem e gasta menos energia.",
                             "Desative programas de inicialização que não usa para o PC ligar mais rápido."]),
    "multitarefa": dict(curto="Multitarefa", nome="Multitarefa", plano="equilibrado", ram_min=16,
                        base=["Mantenha pelo menos 20% da RAM livre.",
                              "Use áreas de trabalho virtuais (Win+Tab) para organizar sem abrir tudo de uma vez."]),
}


def dicas_trabalho(chave, inv, top):
    """Recomendações do perfil de trabalho, ajustadas ao hardware real e aos processos atuais."""
    p = WORK_PERFIS[chave]
    d = list(p["base"])
    ram = sum((m.get("Capacity") or 0) for m in inv.get("ram", [])) / 1024 ** 3
    if ram and ram < p["ram_min"]:
        d.insert(0, f"Seu PC tem {ram:.0f} GB de RAM e esse tipo de trabalho rende melhor com {p['ram_min']} GB ou mais: "
                    "feche programas em segundo plano.")
    discos = inv.get("discos", [])
    if discos and all((x.get("tipo") or "").upper() == "HDD" for x in discos) and chave in ("imagens", "video", "programacao"):
        d.insert(0, "Todos os seus discos são HDD: um SSD traria o maior ganho para esse tipo de trabalho.")
    nucleos = sum((c.get("NumberOfLogicalProcessors") or 0) for c in inv.get("cpu", []))
    if nucleos and nucleos <= 4 and chave in ("video", "programacao"):
        d.append(f"Processador com {nucleos} threads: use resolução de prévia menor e evite tarefas em paralelo.")
    pesados = [f"{n} ({r / 1024 ** 2:.0f} MB)" for n, _, r, _ in top[:3] if r > 500 * 1024 ** 2]
    if pesados:
        d.append("Maiores consumidores agora: " + ", ".join(pesados) + ".")
    return d


def aplicar_work(chave):
    p = WORK_PERFIS[chave]
    return aplicar_plano(p["plano"], f"Work Boost '{p['nome']}'")
