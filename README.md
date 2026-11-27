# Otimizador de PC (Windows)

App com interface gráfica que:

- limpa **todos os Temp** (usuário, Windows e LocalAppData) e esvazia a lixeira
- ativa o plano de energia **Desempenho máximo**, CPU a 100% e **todos os núcleos ativos** (sem core parking)
- ajusta a rede (TCP auto-tuning, RSS, limpa DNS; troca de DNS opcional)
- otimiza **todos os discos** (`defrag /O`: desfragmenta HDD, faz TRIM em SSD)
- cria um **ponto de restauração** antes de mexer em qualquer coisa
- mede **pontos (0–1000) antes e depois** e salva um relatório em `%APPDATA%\OtimizadorPC`
- botão **Drivers**: lê o hardware (CPU, placa-mãe, vídeo, rede, áudio), aponta dispositivos sem driver e instala os drivers pendentes pelo **Windows Update** (assinados pela Microsoft); para a placa de vídeo, detecta NVIDIA/AMD/Intel e abre a página oficial
- tem um **contador de FPS** (overlay sempre no topo, via [PresentMon](https://github.com/GameTechDev/PresentMon)); arraste com o mouse, duplo clique fecha

## Baixar
Aba **Actions → Build EXE → Artifacts → OtimizadorPC**, ou em **Releases** (ao criar uma tag `v1.0.0`).

## Rodar do código
```
pip install -r requirements.txt
python otimizador_pc.py
```

## Observações
- Precisa de Administrador (o .exe pede sozinho).
- O Windows SmartScreen pode avisar por o .exe não ser assinado; é esperado.
- Desempenho máximo gasta mais bateria em notebook.
- Não mexe em registro nem em serviços de propósito.
