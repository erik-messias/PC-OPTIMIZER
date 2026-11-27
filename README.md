# NEXUS PC

Sistema de diagnóstico, otimização e manutenção para **Windows 10/11**. Em vez de aplicar ajustes às cegas,
ele **analisa o computador antes**, explica o que está errado, diferencia **problema confirmado** de **suspeita**
e só altera algo com a sua aprovação, registrando tudo e permitindo desfazer.

## O que já funciona (Fases 1 a 7)

| Módulo | O que faz |
|---|---|
| Dashboard | Nota de saúde 0–100, temperaturas, uso de CPU/GPU/RAM, disco livre, problemas e drivers em tempo real |
| Análise completa | Hardware, Windows, eventos de erro, serviços, drivers, temperaturas e armazenamento, com progresso e relatório `.txt` |
| Diagnóstico | Cada problema com gravidade, situação (confirmado/suspeita), causas possíveis e recomendação |
| Drivers | Lista todos os drivers; aponta ausentes, genéricos e antigos; busca no **Windows Update**; instala só o que você aprovar (com ponto de restauração e backup da lista de drivers) |
| Monitoramento | Gráficos ao vivo: CPU, RAM, GPU, VRAM, temperaturas, disco |
| Game Boost | 5 perfis de energia (reversíveis), dicas gráficas para o seu hardware, GPU de alto desempenho por jogo, contador de FPS |
| Limpeza | Mostra tamanho, local e consequência de cada categoria antes de apagar |
| Inicialização | Lista programas com fabricante, RAM em uso e recomendação (manter / pode desativar / suspeito). **Desativa e reativa** de forma reversível, sem apagar nada; itens de segurança do Windows são protegidos |
| Work Boost | 6 perfis (navegação, imagens, vídeo, programação, escritório, multitarefa): plano de energia reversível + recomendações pelo seu hardware e pelos processos abertos |
| Gargalos | No Monitoramento, **grave uma sessão** (ex.: jogando) e receba a análise: CPU, GPU, RAM, VRAM, temperatura e quedas de FPS, apontando o que limita o desempenho |
| Histórico de desempenho | Evolução da nota ao longo do tempo, análises e sessões gravadas |
| Relatório HTML | Relatório completo em arquivo único, para abrir no navegador, imprimir ou enviar |
| Meus perfis | Perfis próprios: plano de energia + programas que você costuma fechar (sempre com confirmação) |
| Atualização | Verifica novas versões nas Releases e avisa no menu lateral |
| Reparação | SFC, DISM e CHKDSK com explicação, saída ao vivo e resultado em linguagem simples. Verificações só leem; reparos pedem confirmação |
| Histórico | Data, alteração, motivo, resultado e botão **Reverter** |

**Em breve:** instalação automática de atualizações e testes em mais configurações de hardware.

## Como a nota é calculada
Cada categoria (Hardware, Drivers, Windows, Temperaturas, Inicialização, Armazenamento) começa em 100.
Problemas confirmados descontam: crítico −35, alto −20, médio −10, baixo −4; **suspeitas descontam metade**.
Hardware antigo **não** perde pontos por ser antigo.

## Limitações honestas
- **Temperatura da CPU:** o NEXUS PC traz o [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) embutido (aberto oculto). A maioria dos processadores só informa a temperatura com o driver **PawnIO**, de terceiros: em Configurações > Sensores há um botão que o instala via winget, **só se você aprovar**. GPU NVIDIA é lida via `nvidia-smi`. Veja `THIRD_PARTY.md`.
- **Drivers:** a comparação com versões "oficiais" é feita contra o Windows Update. Para placa de vídeo, o app abre o site do fabricante; ele não baixa drivers de fontes não oficiais.
- Nada foi testado em todas as combinações de hardware. Use o ponto de restauração.

## Baixar
**Releases** (ou Actions → Build EXE → Artifacts → NexusPC). O Windows SmartScreen pode avisar, pois o `.exe` não é assinado.

## Instalador
O build também gera `NexusPC-Setup.exe` (Inno Setup) quando possível. Se não aparecer na release, use o `NexusPC.exe` direto: não precisa instalar.

## Testes
```
pip install psutil pytest
python -m pytest tests
```
Os testes cobrem diagnóstico, pontuação, gargalos, reparação, inicialização e histórico, e rodam em CI a cada push.

## Rodar do código
```
pip install -r requirements.txt
python nexus_pc.py
```
Dados, logs e relatórios ficam em `%APPDATA%\NexusPC`.
