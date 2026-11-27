"""Diagnóstico baseado em regras e pontuação de saúde (0-100) com critérios transparentes."""
import statistics
import time
from dataclasses import dataclass, field

from . import drivers as drv
from . import hardware as hw
from .core import IS_WIN, aslist, fmt_bytes, log, plano_ativo, ps_json

GRAVIDADES = ["crítico", "alto", "médio", "baixo", "info"]
PENALIDADE = {"crítico": 35, "alto": 20, "médio": 10, "baixo": 4, "info": 0}
CATEGORIAS = ["Hardware", "Drivers", "Windows", "Temperaturas", "Inicialização", "Armazenamento"]
PESOS = {"Hardware": 15, "Drivers": 20, "Windows": 20, "Temperaturas": 15, "Inicialização": 10, "Armazenamento": 20}


@dataclass
class Problema:
    titulo: str
    categoria: str
    gravidade: str            # crítico/alto/médio/baixo/info
    status: str               # "confirmado" ou "suspeita"
    explicacao: str
    causas: list = field(default_factory=list)
    recomendacao: str = ""
    evidencia: str = ""


# ---------------------------------------------------------------- coleta de contexto
_PS_WINDOWS = r"""
$o = [ordered]@{}
$ev = @(Get-WinEvent -FilterHashtable @{LogName='System';Level=1,2;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 4000 -ErrorAction SilentlyContinue)
$o.eventos = @($ev | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 10 |
               ForEach-Object { [pscustomobject]@{nome=$_.Name; qtd=$_.Count} })
$o.desligamentos = @($ev | Where-Object { $_.Id -eq 41 -and $_.ProviderName -like '*Kernel-Power*' }).Count
$o.servicos = @(Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.State -ne 'Running' -and
               $_.ExitCode -ne 0 -and $_.ExitCode -ne 1077 } | Select-Object -First 15 Name,DisplayName,ExitCode)
$o.reinicio = [bool]((Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') -or
               (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'))
$o | ConvertTo-Json -Compress -Depth 4
"""


def coletar_contexto(progresso=lambda pct, msg: None, buscar_wu=True):
    """Executa toda a análise de coleta. progresso(pct, mensagem)."""
    ctx = {}
    progresso(3, "Identificando hardware...")
    ctx["inv"] = hw.ler_inventario()

    progresso(25, "Verificando sistema operacional...")
    ctx["windows"] = ps_json(_PS_WINDOWS, timeout=150, default={}) or {}
    ctx["plano"] = plano_ativo()[1] if IS_WIN else ""
    try:
        from . import lhm
        ctx["sensores"] = lhm.estado() if IS_WIN else ""
    except Exception:  # noqa: BLE001
        ctx["sensores"] = ""

    progresso(45, "Lendo drivers e dispositivos...")
    drivers, erros = drv.ler_drivers() if IS_WIN else ([], [])
    ctx["drivers"], ctx["erros_pnp"] = drivers, drv.classificar_erros(erros)

    if buscar_wu:
        progresso(60, "Procurando drivers no Windows Update (pode demorar)...")
        ctx["wu"] = drv.buscar_atualizacoes() if IS_WIN else None
    else:
        ctx["wu"] = None

    progresso(78, "Medindo temperaturas e uso de recursos...")
    sens = hw.Sensores()
    sens.atualizar_lento()
    amostras = []
    for _ in range(4):
        time.sleep(0.8)
        amostras.append(sens.amostra())
    ctx["amostras"] = amostras

    progresso(92, "Verificando armazenamento e inicialização...")
    ctx["discos_uso"] = hw.discos_uso()
    ctx["startup"] = hw.programas_inicializacao()
    ctx["top"] = hw.top_processos(6)
    progresso(98, "Interpretando resultados...")
    return ctx


def _media(amostras, chave):
    v = [a[chave] for a in amostras if a.get(chave) is not None]
    return statistics.mean(v) if v else None


# ------------------------------------------------------------------------ regras
def diagnosticar(ctx):
    """Aplica as regras. Retorna lista de Problema (ordenada por gravidade)."""
    P = []
    inv, win = ctx.get("inv", {}), ctx.get("windows", {}) or {}
    am = ctx.get("amostras", [])

    # ---- Memória
    ram = inv.get("ram", [])
    total_ram = sum((m.get("Capacity") or 0) for m in ram)
    ram_pct = _media(am, "ram_pct")
    if not total_ram and am:
        total_ram = am[-1].get("ram_total", 0)
    if ram_pct is not None and ram_pct >= 90:
        P.append(Problema("Uso de memória RAM muito alto", "Windows", "alto", "confirmado",
                          f"A RAM está com {ram_pct:.0f}% de uso agora. Acima de ~90% o Windows passa a usar o disco "
                          "como memória, deixando tudo lento.",
                          ["Muitos programas ou abas abertas", "Programa com vazamento de memória",
                           "Pouca RAM instalada para o uso"],
                          "Veja os maiores consumidores em Game Boost/Work Boost e feche o que não usa.",
                          f"RAM em uso: {ram_pct:.0f}%"))
    elif ram_pct is not None and ram_pct >= 80:
        P.append(Problema("Uso de RAM elevado", "Windows", "médio", "suspeita",
                          f"A RAM está com {ram_pct:.0f}% de uso. Não é crítico, mas deixa pouca folga.",
                          ["Programas em segundo plano", "Navegador com muitas abas"],
                          "Analise os processos e reduza o que não é necessário.", f"RAM em uso: {ram_pct:.0f}%"))
    if total_ram and total_ram < 7.5 * 1024 ** 3:
        P.append(Problema("Pouca memória RAM instalada", "Hardware", "médio", "suspeita",
                          f"O PC tem {fmt_bytes(total_ram)} de RAM. Para o Windows 10/11 e jogos atuais, "
                          "16 GB é o ponto confortável.",
                          ["Uso pesado de navegador/jogos"],
                          "Se notar lentidão ao abrir vários programas, uma expansão de RAM é o upgrade mais barato.",
                          f"RAM: {fmt_bytes(total_ram)}"))
    # RAM abaixo da velocidade nominal (XMP/EXPO desligado)
    if ram:
        nominal = max((m.get("Speed") or 0) for m in ram)
        config = min((m.get("ConfiguredClockSpeed") or m.get("Speed") or 0) for m in ram)
        if nominal and config and config < nominal * 0.9:
            P.append(Problema("Memória RAM abaixo da velocidade nominal", "Hardware", "baixo", "suspeita",
                              f"Os pentes são vendidos para {nominal} MHz, mas operam a {config} MHz. "
                              "Isso reduz um pouco o desempenho (principalmente em jogos e CPUs AMD Ryzen).",
                              ["XMP/EXPO desativado na BIOS", "Limitação da placa-mãe ou do processador"],
                              "Entre na BIOS e ative o perfil XMP/EXPO. Só faça se souber o que está fazendo.",
                              f"Nominal {nominal} MHz / atual {config} MHz"))
        if len(ram) == 1 and (ram[0].get("Capacity") or 0) >= 4 * 1024 ** 3:
            P.append(Problema("Memória em canal único", "Hardware", "baixo", "suspeita",
                              "Há apenas 1 pente de RAM. Dois pentes iguais (dual channel) dobram a largura de banda, "
                              "o que ajuda em jogos e gráficos integrados.",
                              ["Configuração de fábrica econômica"],
                              "Se for possível, adicione um segundo pente igual ao atual."))

    # ---- Temperaturas
    for chave, nome in (("cpu_temp", "do processador"), ("gpu_temp", "da placa de vídeo")):
        t = _media(am, chave)
        if t is None:
            continue
        if t >= 90:
            P.append(Problema(f"Temperatura {nome} crítica", "Temperaturas", "crítico", "confirmado",
                              f"A temperatura {nome} está em {t:.0f} °C. Acima de ~90 °C o hardware reduz a "
                              "velocidade para se proteger e a vida útil cai.",
                              ["Cooler ou ventoinha sujo/parado", "Pasta térmica ressecada", "Má ventilação do gabinete"],
                              "Limpe poeira, verifique ventoinhas e fluxo de ar. Se persistir, troque a pasta térmica.",
                              f"{t:.0f} °C"))
        elif t >= 80:
            P.append(Problema(f"Temperatura {nome} alta", "Temperaturas", "médio", "confirmado",
                              f"A temperatura {nome} está em {t:.0f} °C. Em carga pesada é aceitável, "
                              "mas parado indica refrigeração fraca.",
                              ["Poeira acumulada", "Curva de ventoinhas conservadora"],
                              "Compare com o uso: se a temperatura é alta com o PC ocioso, limpe e revise o cooler.",
                              f"{t:.0f} °C"))
    thr = (am[-1].get("gpu_throttle") if am else None) or ""
    if thr and thr not in ("0x0000000000000000", "0x0", "Not Active", "[N/A]") and (_media(am, "gpu_util") or 0) > 50:
        P.append(Problema("Placa de vídeo limitando a frequência", "Temperaturas", "médio", "suspeita",
                          "A NVIDIA informa que a GPU está reduzindo a frequência (limite térmico, de energia ou de driver) "
                          "enquanto trabalha.",
                          ["Limitação térmica", "Limitação de energia", "Driver incorreto", "Problema de alimentação",
                           "Configuração de desempenho"],
                          "Antes de mudar qualquer coisa, analise temperatura, frequência, consumo e driver em Monitoramento.",
                          f"Códigos de limitação: {thr}"))
    if not any(a.get("cpu_temp") is not None for a in am):
        est = ctx.get("sensores", "")
        dica = {"sem_pawnio": "Vá em Configurações > Sensores de temperatura e instale o driver PawnIO (pede sua aprovação).",
                "desligado": "O leitor de sensores não está rodando: reinicie o NEXUS PC como Administrador.",
                "ativo": "O leitor está ativo, mas o seu processador não expõe sensor. Em alguns notebooks isso é normal."
                }.get(est, "Abra o LibreHardwareMonitor em segundo plano para ler a temperatura.")
        P.append(Problema("Temperatura do processador indisponível", "Temperaturas", "info", "confirmado",
                          "O Windows não informa a temperatura da CPU sem um driver de sensores.", [], dica))
    dt = _media(am, "disco_temp")
    if dt is not None and dt >= 60:
        P.append(Problema("Disco com temperatura alta", "Armazenamento", "médio" if dt < 70 else "alto", "confirmado",
                          f"Um dos discos está a {dt:.0f} °C. Calor constante reduz a vida útil e pode causar lentidão.",
                          ["Pouca ventilação no gabinete", "SSD NVMe sem dissipador"],
                          "Melhore o fluxo de ar; em SSD NVMe use dissipador.", f"{dt:.0f} °C"))

    # ---- CPU / gargalos
    cpu = _media(am, "cpu")
    if cpu is not None and cpu >= 85:
        top = ", ".join(f"{n} ({fmt_bytes(r)})" for n, _, r, _ in ctx.get("top", [])[:3])
        P.append(Problema("Processador com uso muito alto", "Windows", "alto", "suspeita",
                          f"A CPU ficou em média {cpu:.0f}% durante a análise. Se isso ocorre sem você estar "
                          "usando algo pesado, há um programa consumindo recursos.",
                          ["Atualização/indexação em segundo plano", "Antivírus em varredura", "Programa travado"],
                          "Abra o Gerenciador de Tarefas, ordene por CPU e identifique o processo.", f"CPU {cpu:.0f}%. Maiores em RAM: {top}"))

    # ---- Armazenamento
    for d in ctx.get("inv", {}).get("discos", []):
        saude = (d.get("saude") or "").lower()
        nome = d.get("FriendlyName") or "Disco"
        if saude and saude not in ("healthy", "saudável", "saudavel"):
            sev = "crítico" if saude in ("unhealthy", "não saudável") else "alto"
            P.append(Problema(f"Saúde do disco comprometida: {nome}", "Armazenamento", sev, "confirmado",
                              f"O Windows classifica este disco como '{d.get('saude')}'. Pode haver setores defeituosos "
                              "e risco de perda de dados.",
                              ["Desgaste do disco", "Falha física", "Cabo/porta com defeito"],
                              "Faça backup IMEDIATO dos arquivos importantes e considere trocar o disco.",
                              f"Estado: {d.get('estado')}"))
    discos = ctx.get("inv", {}).get("discos", [])
    if discos and all((d.get("tipo") or "").upper() == "HDD" for d in discos):
        P.append(Problema("Computador usa apenas HDD", "Armazenamento", "médio", "suspeita",
                          "Todos os discos são HDD (mecânicos). Esse é o principal motivo de lentidão ao ligar e abrir programas.",
                          ["Tecnologia mais lenta que SSD"],
                          "Instalar o Windows em um SSD é a melhor melhoria de desempenho possível."))
    for letra, total, usado, livre in ctx.get("discos_uso", []):
        pct = livre / total * 100 if total else 100
        if pct < 8 or livre < 5 * 1024 ** 3:
            P.append(Problema(f"Pouco espaço livre em {letra}", "Armazenamento", "alto", "confirmado",
                              f"Restam {fmt_bytes(livre)} ({pct:.0f}%). Com pouco espaço o Windows não consegue atualizar, "
                              "usar memória virtual nem manter o desempenho.",
                              ["Arquivos grandes", "Cache e temporários acumulados"],
                              "Use a Limpeza para ver o que pode ser liberado e mova arquivos para outro disco.",
                              f"Livre: {fmt_bytes(livre)}"))
        elif pct < 15:
            P.append(Problema(f"Espaço livre baixo em {letra}", "Armazenamento", "médio", "confirmado",
                              f"Restam {fmt_bytes(livre)} ({pct:.0f}%). Mantenha ao menos 15% livre.",
                              ["Arquivos acumulados"], "Veja o módulo de Limpeza.", f"Livre: {fmt_bytes(livre)}"))

    # ---- Drivers
    for e in ctx.get("erros_pnp", []):
        P.append(Problema(("Driver ausente: " if e["sem_driver"] else "Dispositivo com erro: ") + e["nome"],
                          "Drivers", "alto" if e["sem_driver"] else "médio", "confirmado",
                          f"O Gerenciador de Dispositivos reporta o erro {e['codigo']}: {e['causa']}.",
                          ["Driver não instalado", "Driver corrompido ou incompatível", "Dispositivo desconectado/defeituoso"],
                          "Procure o driver na central de Drivers (Windows Update) ou no site do fabricante.",
                          f"{e['id']}"))
    for x in ctx.get("drivers", []):
        if x.get("status") == "generico":
            P.append(Problema(f"Driver genérico: {x.get('DeviceName')}", "Drivers", "médio", "confirmado",
                              x["nota"], ["Driver do fabricante não instalado"],
                              "Instale o driver oficial do fabricante (veja a central de Drivers).",
                              f"Versão {x.get('DriverVersion')} ({x.get('data')})"))
        elif x.get("status") == "antigo":
            P.append(Problema(f"Driver antigo: {x.get('DeviceName')}", "Drivers", "baixo", "suspeita",
                              x["nota"], ["Nunca foi atualizado"],
                              "Só atualize se tiver problemas ou se o fabricante indicar correção relevante.",
                              f"Versão {x.get('DriverVersion')} ({x.get('data')})"))
    wu = ctx.get("wu")
    if wu:
        P.append(Problema(f"{len(wu)} driver(s) disponível(is) no Windows Update", "Drivers", "baixo", "confirmado",
                          "O Windows Update tem versões de drivers que ainda não estão instaladas neste PC.",
                          [], "Revise a lista na central de Drivers e aprove apenas o que fizer sentido.",
                          "; ".join((w.get("titulo") or "")[:50] for w in wu[:3])))

    # ---- Windows
    for ev in aslist(win.get("eventos")):
        nome, qtd = ev.get("nome", ""), ev.get("qtd", 0)
        baixo = nome.lower()
        if "whea" in baixo and qtd >= 1:
            P.append(Problema("Erros de hardware reportados (WHEA)", "Hardware", "alto", "confirmado",
                              f"O Windows registrou {qtd} erro(s) de hardware nos últimos 7 dias. Costumam vir de CPU, RAM, "
                              "PCIe ou overclock instável.",
                              ["Overclock/undervolt instável", "RAM com defeito", "Fonte fraca", "Superaquecimento"],
                              "Volte BIOS/overclock ao padrão e rode o Diagnóstico de Memória do Windows.", f"{qtd} eventos"))
        elif baixo in ("disk", "ntfs", "volmgr", "stornvme", "storahci") and qtd >= 1:
            P.append(Problema(f"Erros de armazenamento nos eventos ({nome})", "Armazenamento", "alto", "confirmado",
                              f"{qtd} erro(s) de disco/sistema de arquivos nos últimos 7 dias.",
                              ["Disco falhando", "Cabo SATA/porta ruim", "Desligamentos forçados"],
                              "Faça backup e execute a verificação de disco (CHKDSK).", f"{qtd} eventos"))
        elif baixo in ("nvlddmkm", "display", "atikmpag", "amdkmdap") and qtd >= 1:
            P.append(Problema("A placa de vídeo parou de responder (driver)", "Drivers", "médio", "confirmado",
                              f"{qtd} falha(s) do driver de vídeo nos últimos 7 dias (telas piscando/jogos fechando).",
                              ["Driver com bug", "Overclock instável", "Superaquecimento"],
                              "Reinstale o driver de vídeo e verifique temperatura.", f"{qtd} eventos"))
        elif qtd >= 30:
            P.append(Problema(f"Erros recorrentes: {nome}", "Windows", "baixo", "suspeita",
                              f"A origem '{nome}' registrou {qtd} erros em 7 dias.", ["Serviço ou programa com falha repetida"],
                              "Abra o Visualizador de Eventos e pesquise a mensagem completa.", f"{qtd} eventos"))
    desl = win.get("desligamentos") or 0
    if desl:
        P.append(Problema("Desligamentos inesperados", "Windows", "médio", "confirmado",
                          f"O Windows registrou {desl} desligamento(s) inesperado(s) (Kernel-Power 41) nos últimos 7 dias.",
                          ["Queda de energia", "Fonte instável", "Superaquecimento", "Botão de desligar forçado"],
                          "Verifique fonte, temperatura e se o PC não está sendo desligado à força."))
    for s in aslist(win.get("servicos")):
        P.append(Problema(f"Serviço com falha: {s.get('DisplayName') or s.get('Name')}", "Windows", "baixo", "confirmado",
                          f"Serviço automático parado com código de saída {s.get('ExitCode')}.",
                          ["Dependência ausente", "Programa desinstalado pela metade"],
                          "Se não usa o programa associado, pode ignorar. Caso contrário, reinstale-o.",
                          s.get("Name", "")))
    if win.get("reinicio"):
        P.append(Problema("Reinício do Windows pendente", "Windows", "baixo", "confirmado",
                          "Há atualizações ou instalações esperando reinício para terminar.", [],
                          "Reinicie o PC quando puder."))
    dias = (inv.get("os") or {}).get("bootdias") or 0
    if dias >= 14:
        P.append(Problema("PC ligado há muitos dias sem reiniciar", "Windows", "baixo", "suspeita",
                          f"O último boot foi há {dias} dias. Reiniciar libera memória e conclui atualizações.", [],
                          "Reinicie o computador."))
    plano = (ctx.get("plano") or "").lower()
    if plano and any(k in plano for k in ("economia", "power saver")):
        P.append(Problema("Plano de energia em Economia", "Windows", "médio", "confirmado",
                          "O plano 'Economia de energia' limita o processador e deixa o PC mais lento.",
                          ["Configuração herdada de notebook ou ajuste manual"],
                          "Em Game Boost, aplique o perfil Equilibrado ou Máximo desempenho (reversível)."))

    # ---- Inicialização
    n = len(ctx.get("startup", []))
    if n >= 15:
        P.append(Problema("Muitos programas na inicialização", "Inicialização", "médio", "suspeita",
                          f"{n} programas iniciam com o Windows, o que atrasa o boot e consome memória.", [],
                          "Veja a lista em Inicialização e desative o que não precisa abrir sempre.", f"{n} itens"))
    elif n >= 9:
        P.append(Problema("Vários programas na inicialização", "Inicialização", "baixo", "suspeita",
                          f"{n} programas iniciam com o Windows.", [], "Revise a lista em Inicialização.", f"{n} itens"))

    ordem = {g: i for i, g in enumerate(GRAVIDADES)}
    P.sort(key=lambda p: (ordem[p.gravidade], 0 if p.status == "confirmado" else 1))
    return P


# --------------------------------------------------------------------- pontuação
def pontuar(problemas):
    """Pontuação por categoria e geral. Sem penalizar hardware antigo: só pesam problemas concretos
    (suspeitas valem metade). Retorna (geral, {categoria: (nota, [(titulo, penalidade)])})."""
    det = {c: [] for c in CATEGORIAS}
    for p in problemas:
        pen = PENALIDADE.get(p.gravidade, 0) * (1 if p.status == "confirmado" else 0.5)
        if pen and p.categoria in det:
            det[p.categoria].append((p.titulo, pen))
    notas = {}
    for c, itens in det.items():
        # limite de 60 pontos por categoria para uma única categoria não zerar a nota geral
        perda = min(60, sum(x[1] for x in itens))
        notas[c] = (round(100 - perda), itens)
    soma = sum(PESOS.values())
    geral = round(sum(notas[c][0] * PESOS[c] for c in CATEGORIAS) / soma)
    return geral, notas


def texto_relatorio(ctx, problemas, geral, notas):
    inv = ctx.get("inv", {})
    L = ["NEXUS PC - RELATÓRIO DE ANÁLISE", "=" * 60, ""]
    so = inv.get("os") or {}
    L.append(f"Sistema: {so.get('Caption', '?')} (build {so.get('BuildNumber', '?')})")
    for c in inv.get("cpu", []):
        L.append(f"CPU: {c.get('Name', '').strip()} - {c.get('NumberOfCores')} núcleos / {c.get('NumberOfLogicalProcessors')} threads")
    for p in inv.get("placa", []):
        L.append(f"Placa-mãe: {p.get('Manufacturer')} {p.get('Product')}")
    for b in inv.get("bios", []):
        L.append(f"BIOS: {b.get('Manufacturer')} {b.get('SMBIOSBIOSVersion')} ({b.get('data')})")
    for g in inv.get("gpu", []):
        L.append(f"Vídeo: {g.get('Name')} - driver {g.get('DriverVersion')} ({g.get('driverdata')})")
    ram = inv.get("ram", [])
    if ram:
        L.append(f"RAM: {fmt_bytes(sum((m.get('Capacity') or 0) for m in ram))} em {len(ram)} pente(s), "
                 f"{max((m.get('Speed') or 0) for m in ram)} MHz nominal")
    for d in inv.get("discos", []):
        L.append(f"Disco: {d.get('FriendlyName')} - {d.get('tipo')} {fmt_bytes(d.get('Size'))} - saúde {d.get('saude')}")
    L += ["", f"PONTUAÇÃO GERAL: {geral}/100", ""]
    for c in CATEGORIAS:
        n, itens = notas[c]
        L.append(f"  {c:<15}{n:>4}")
        for t, pen in itens:
            L.append(f"      -{pen:.0f}  {t}")
    L += ["", f"PROBLEMAS ({len(problemas)})", "-" * 60]
    for p in problemas:
        L.append(f"[{p.gravidade.upper()} | {p.status}] {p.titulo}")
        L.append(f"   {p.explicacao}")
        if p.causas:
            L.append("   Possíveis causas: " + "; ".join(p.causas))
        if p.recomendacao:
            L.append(f"   Recomendação: {p.recomendacao}")
        L.append("")
    return "\n".join(L)
