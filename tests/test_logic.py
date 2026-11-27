"""Testes da lógica (rodam em qualquer sistema, sem Windows e sem interface)."""
from nexus import bottleneck as bn
from nexus import diagnostics as dg
from nexus import drivers as drv
from nexus import optimize as opt
from nexus import relatorio as rel
from nexus import repair as rp
from nexus import startup as st
from nexus import update as up
from nexus.core import HIST


def contexto(**extra):
    drivers = [dict(DeviceName="Microsoft Basic Display Adapter", DeviceClass="DISPLAY", DriverProviderName="Microsoft",
                    DriverVersion="10.0", data="2020-01-01"),
               dict(DeviceName="Realtek Audio", DeviceClass="MEDIA", DriverProviderName="Realtek", DriverVersion="6.0", data="2019-03-01"),
               dict(DeviceName="Intel Ethernet", DeviceClass="NET", DriverProviderName="Intel", DriverVersion="12", data="2099-01-01")]
    for d in drivers:
        drv.classificar(d)
    ctx = dict(
        inv={"os": {"Caption": "Windows 11", "BuildNumber": "26100", "bootdias": 20},
             "cpu": [{"Name": "Ryzen", "NumberOfCores": 6, "NumberOfLogicalProcessors": 12}], "placa": [], "bios": [],
             "gpu": [{"Name": "NVIDIA GTX 1650", "AdapterRAM": 4 * 1024 ** 3}],
             "ram": [{"Capacity": 8 * 1024 ** 3, "Speed": 3200, "ConfiguredClockSpeed": 2133}],
             "discos": [{"FriendlyName": "HDD", "tipo": "HDD", "Size": 1e12, "saude": "Healthy", "estado": "OK"}]},
        windows={"eventos": [{"nome": "Microsoft-Windows-WHEA-Logger", "qtd": 3}], "desligamentos": 1, "servicos": [], "reinicio": False},
        plano="Economia de energia", drivers=drivers,
        erros_pnp=drv.classificar_erros([{"Name": "Dispositivo PCI", "ConfigManagerErrorCode": 28, "DeviceID": "PCI", "PNPClass": "System"}]),
        wu=[], amostras=[{"cpu": 40, "ram_pct": 86, "cpu_temp": 92, "gpu_temp": 70, "gpu_util": 10, "ram_total": 8 * 1024 ** 3,
                          "gpu_throttle": None}] * 3,
        discos_uso=[("C:\\", 500e9, 480e9, 20e9)], startup=[("a", "b", "c")] * 16, top=[])
    ctx.update(extra)
    return ctx


def test_diagnostico_encontra_problemas_chave():
    titulos = " | ".join(p.titulo for p in dg.diagnosticar(contexto()))
    for esperado in ("Driver ausente", "Driver genérico", "WHEA", "Plano de energia em Economia", "Pouco espaço livre",
                     "Temperatura do processador crítica", "Muitos programas na inicialização", "apenas HDD"):
        assert esperado in titulos, esperado


def test_driver_recente_nao_e_marcado_antigo():
    ctx = contexto()
    assert all(p["status"] != "antigo" for p in ctx["drivers"] if "Intel" in p["DeviceName"])


def test_pontuacao_transparente():
    probs = dg.diagnosticar(contexto())
    geral, notas = dg.pontuar(probs)
    assert 0 <= geral <= 100 and set(notas) == set(dg.CATEGORIAS)
    assert notas["Drivers"][0] < 100 and notas["Temperaturas"][0] < 100


def test_pc_saudavel_nota_alta():
    ctx = contexto(windows={}, plano="Equilibrado", drivers=[], erros_pnp=[], discos_uso=[("C:\\", 500e9, 100e9, 400e9)], startup=[],
                   amostras=[{"cpu": 10, "ram_pct": 40, "cpu_temp": 50, "gpu_temp": 45, "gpu_util": 5}] * 3)
    ctx["inv"]["ram"] = [{"Capacity": 16 * 1024 ** 3, "Speed": 3200, "ConfiguredClockSpeed": 3200}] * 2
    ctx["inv"]["discos"] = [{"tipo": "SSD", "saude": "Healthy", "FriendlyName": "x"}]
    geral, _ = dg.pontuar(dg.diagnosticar(ctx))
    assert geral >= 95


def test_hardware_antigo_nao_perde_pontos_por_idade():
    ctx = contexto(windows={}, plano="Equilibrado", drivers=[], erros_pnp=[], discos_uso=[("C:\\", 500e9, 100e9, 400e9)], startup=[],
                   amostras=[{"cpu": 10, "ram_pct": 40, "cpu_temp": 50, "gpu_temp": 45, "gpu_util": 5}] * 3)
    ctx["inv"]["cpu"] = [{"Name": "Intel Core 2 Duo E6600", "NumberOfCores": 2, "NumberOfLogicalProcessors": 2}]
    ctx["inv"]["ram"] = [{"Capacity": 16 * 1024 ** 3, "Speed": 800, "ConfiguredClockSpeed": 800}] * 2
    ctx["inv"]["discos"] = [{"tipo": "SSD", "saude": "Healthy", "FriendlyName": "x"}]
    assert dg.pontuar(dg.diagnosticar(ctx))[1]["Hardware"][0] == 100


def test_relatorios():
    ctx = contexto()
    probs = dg.diagnosticar(ctx)
    geral, notas = dg.pontuar(probs)
    assert "PONTUAÇÃO GERAL" in dg.texto_relatorio(ctx, probs, geral, notas)
    html = rel.gerar(ctx, probs, geral, notas)
    assert html.startswith("<!doctype html>") and "NEXUS PC" in html


CASOS_REPARO = [
    ("sfc_verificar", 0, "A Proteção de Recursos do Windows não encontrou nenhuma violação de integridade.", "ok"),
    ("sfc_verificar", 0, "Windows Resource Protection did not find any integrity violations.", "ok"),
    ("sfc_reparar", 0, "encontrou arquivos corrompidos e os reparou com êxito.", "reparado"),
    ("sfc_reparar", 0, "found corrupt files but was unable to fix some of them.", "problema"),
    ("dism_verificar", 0, "No component store corruption detected.", "ok"),
    ("dism_reparar", 0, "The restore operation completed successfully.", "reparado"),
    ("chkdsk", 0, "nenhum problema foi encontrado.", "ok"),
]


def test_interpretacao_reparo():
    for chave, cod, texto, esperado in CASOS_REPARO:
        assert rp.interpretar(chave, cod, texto)[0] == esperado, (chave, texto)


def test_regras_inicializacao():
    rec = lambda n, c, e=True: st._recomendar(n, c, e)[0]  # noqa: E731
    assert rec("Spotify", "C:\\a\\spotify.exe") == "desativar"
    assert rec("SecurityHealth", "C:\\Windows\\SecurityHealthSystray.exe") == "proteger"
    assert rec("RtkAudUService", "C:\\Windows\\realtek.exe") == "manter"
    assert rec("x", "C:\\Users\\a\\AppData\\Local\\Temp\\x.exe") == "suspeito"
    assert rec("x", "C:\\nao\\existe.exe", False) == "suspeito"
    assert st._executavel('"C:\\Program Files\\A\\a.exe" --min') == "C:\\Program Files\\A\\a.exe"


def test_gargalo_cpu():
    am = [{"cpu": 95, "gpu_util": 40, "ram_pct": 60, "gpu_temp": 60, "cpu_temp": 70, "vram": 50, "gpu_throttle": None, "fps": 50}] * 30
    r, ach = bn.analisar(am)
    assert "Processador limitando" in ach[0][0]


def test_gargalo_gpu_normal_e_ram():
    am = [{"cpu": 50, "gpu_util": 99, "ram_pct": 95, "gpu_temp": 60, "cpu_temp": 60, "vram": 50, "gpu_throttle": None, "fps": None}] * 30
    titulos = [a[0] for a in bn.analisar(am)[1]]
    assert any("Placa de vídeo no limite" in t for t in titulos) and any("RAM" in t for t in titulos)


def test_sessao_curta():
    assert "curta" in bn.analisar([{}] * 2)[1][0][0]


def test_dicas_work_e_game():
    inv = {"ram": [{"Capacity": 8 * 1024 ** 3}], "discos": [{"tipo": "HDD"}], "cpu": [{"NumberOfLogicalProcessors": 4}],
           "gpu": [{"Name": "Intel UHD Graphics", "AdapterRAM": 1 << 30}]}
    assert any("SSD" in d for d in opt.dicas_trabalho("video", inv, []))
    assert any("integrada" in d for d in opt.dicas_graficas(inv, "antigo"))


def test_historico_e_desempenho():
    i = HIST.registrar("Teste", "motivo", "ok", {"tipo": "plano_energia", "guid": "x"})
    assert HIST.listar()[0][0] == i
    HIST.registrar_desempenho(80, {"Hardware": 90}, 3)
    assert HIST.listar_desempenho()[-1][1] == 80
    assert HIST.reverter(999999)[0] is False


def test_versoes():
    assert up._versao("v2.1.0") > up._versao("1.9.9") and up._versao("1.0.0") == up._versao("1.0.0")


def test_lhm_interpreta_sensores_intel_amd_gpu_disco():
    from nexus import lhm
    linhas = [
        {"Identifier": "/intelcpu/0/temperature/0", "SensorType": "Temperature", "Name": "Core #1", "Value": 55.0},
        {"Identifier": "/intelcpu/0/temperature/5", "SensorType": "Temperature", "Name": "CPU Package", "Value": 62.0},
        {"Identifier": "/intelcpu/0/power/0", "SensorType": "Power", "Name": "CPU Package", "Value": 35.5},
        {"Identifier": "/gpu-nvidia/0/temperature/0", "SensorType": "Temperature", "Name": "GPU Core", "Value": 71.0},
        {"Identifier": "/gpu-nvidia/0/load/0", "SensorType": "Load", "Name": "GPU Core", "Value": 88.0},
        {"Identifier": "/nvme/0/temperature/0", "SensorType": "Temperature", "Name": "Temperature", "Value": 48.0},
        {"Identifier": "/lpc/nct/0/fan/0", "SensorType": "Fan", "Name": "Fan #1", "Value": 1200.0},
        {"Identifier": "/amdcpu/0/temperature/2", "SensorType": "Temperature", "Name": "Core (Tctl/Tdie)", "Value": None},
    ]
    r = lhm.interpretar(linhas)
    assert r["cpu_temp"] == 62.0 and r["cpu_consumo"] == 35.5
    assert r["gpu_temp"] == 71.0 and r["gpu_util"] == 88.0 and r["disco_temp"] == 48.0
    assert r["ventoinhas"] == [("Fan #1", 1200.0)]


def test_lhm_sem_prioridade_usa_maior_temperatura():
    from nexus import lhm
    linhas = [{"Identifier": "/amdcpu/0/temperature/1", "SensorType": "Temperature", "Name": "Core #1", "Value": 50.0},
              {"Identifier": "/amdcpu/0/temperature/2", "SensorType": "Temperature", "Name": "Core #2", "Value": 58.0}]
    assert lhm.interpretar(linhas)["cpu_temp"] == 58.0


def test_diagnostico_orienta_sobre_sensor_ausente():
    ctx = contexto(sensores="sem_pawnio")
    ctx["amostras"] = [{"cpu": 10, "ram_pct": 40, "cpu_temp": None}] * 3
    p = [x for x in dg.diagnosticar(ctx) if "indisponível" in x.titulo]
    assert p and "PawnIO" in p[0].recomendacao


def test_disco_quente():
    ctx = contexto()
    ctx["amostras"] = [{"cpu": 10, "ram_pct": 40, "cpu_temp": 50, "disco_temp": 72}] * 3
    assert any("Disco com temperatura alta" in x.titulo for x in dg.diagnosticar(ctx))
