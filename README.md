# NEXUS PC

Sistema de diagnóstico, otimização e manutenção para **Windows 10/11**. Em vez de aplicar ajustes às cegas,
ele **analisa o computador antes**, explica o que está errado, diferencia **problema confirmado** de **suspeita**
e só altera algo com a sua aprovação, registrando tudo e permitindo desfazer.

## O que já funciona (Fases 1 a 3)

| Módulo | O que faz |
|---|---|
| Dashboard | Nota de saúde 0–100, temperaturas, uso de CPU/GPU/RAM, disco livre, problemas e drivers em tempo real |
| Análise completa | Hardware, Windows, eventos de erro, serviços, drivers, temperaturas e armazenamento, com progresso e relatório `.txt` |
| Diagnóstico | Cada problema com gravidade, situação (confirmado/suspeita), causas possíveis e recomendação |
| Drivers | Lista todos os drivers; aponta ausentes, genéricos e antigos; busca no **Windows Update**; instala só o que você aprovar (com ponto de restauração e backup da lista de drivers) |
| Monitoramento | Gráficos ao vivo: CPU, RAM, GPU, VRAM, temperaturas, disco |
| Game Boost | 5 perfis de energia (reversíveis), dicas gráficas para o seu hardware, GPU de alto desempenho por jogo, contador de FPS |
| Limpeza | Mostra tamanho, local e consequência de cada categoria antes de apagar |
| Inicialização | Lista programas que abrem com o Windows e sinaliza entradas suspeitas (somente leitura) |
| Histórico | Data, alteração, motivo, resultado e botão **Reverter** |

**Em breve:** Work Boost com perfis, Reparação (SFC/DISM/CHKDSK), desativar itens de inicialização, atualizador automático.

## Como a nota é calculada
Cada categoria (Hardware, Drivers, Windows, Temperaturas, Inicialização, Armazenamento) começa em 100.
Problemas confirmados descontam: crítico −35, alto −20, médio −10, baixo −4; **suspeitas descontam metade**.
Hardware antigo **não** perde pontos por ser antigo.

## Limitações honestas
- **Temperatura da CPU** no Windows exige um driver de sensores. Abra o [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) em segundo plano e o NEXUS PC lê sozinho. GPU NVIDIA é lida via `nvidia-smi`.
- **Drivers:** a comparação com versões "oficiais" é feita contra o Windows Update. Para placa de vídeo, o app abre o site do fabricante; ele não baixa drivers de fontes não oficiais.
- Nada foi testado em todas as combinações de hardware. Use o ponto de restauração.

## Baixar
**Releases** (ou Actions → Build EXE → Artifacts → NexusPC). O Windows SmartScreen pode avisar, pois o `.exe` não é assinado.

## Rodar do código
```
pip install -r requirements.txt
python nexus_pc.py
```
Dados, logs e relatórios ficam em `%APPDATA%\NexusPC`.
