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
