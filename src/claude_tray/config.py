#!/usr/bin/env python3
"""Configuracao do usuario - onde mora, quais sao os defaults, como recarrega.

POR QUE FORA DO PACOTE
----------------------
Na versao original o config.json ficava ao lado do codigo. Instalado via pipx
ou uv, o codigo vive num venv de ferramentas que e APAGADO E RECRIADO a cada
upgrade - a configuracao do usuario iria junto, em silencio. Por isso ela mora
em ~/.claude-tray/config.json, que nenhum upgrade toca.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DIR_CONFIG = Path.home() / ".claude-tray"
CONFIG_PATH = DIR_CONFIG / "config.json"

# Defaults publicos = a configuracao que sobreviveu ao uso real, nao os valores
# do primeiro rascunho. Quem instala hoje comeca de onde a calibracao parou.
PADRAO = {
    # 'api' = percentual oficial (fato, a mesma rota do /usage).
    # 'estimativa' = modelo antigo de tokens/limite calibrado a mao. Erra por
    # ~2x porque a relacao token -> percentual NAO e estavel entre janelas.
    # So use estimativa se a rota cair de vez.
    "fonte": "api",
    "base": "ponderado",
    # Legado: alimentava o percentual estimado. Hoje so entra nos ABSOLUTOS do
    # tooltip (tokens e US$), onde o denominador nem e usado.
    "limite": 20_000_000,

    # Duas cadencias, de proposito. O relogio muda todo minuto e sai de graca
    # (subtracao local); o percentual custa uma requisicao. Bater na API a cada
    # 15s so pra ver um numero que anda em degraus seria desperdicio.
    "intervalo_seg": 15,
    "intervalo_api_seg": 60,
    "intervalo_consumo_seg": 120,
    # Acima disso a leitura vira cinza: "nao confio mais neste numero".
    "stale_seg": 300,

    "cores": {"folgado": "#0fadd6", "tranquilo": "#3fb950", "atencao": "#d29922",
              "critico": "#f85149", "inativo": "#6e7681"},
    "limiares": {"folgado": 30, "atencao": 60, "critico": 85},
    "icone": {"arco": True, "espessura": 4, "fonte": {"1": 34, "2": 28, "3": 22}},
    # 'uso' = o anel do icone de uso acompanha o proprio numero (cada icone
    # conta uma historia so). 'tempo' = o anel carrega o relogio; fazia sentido
    # quando o icone de tempo era ciano fixo, hoje seria pintar duas
    # informacoes com uma cor so.
    "modo_arco": "uso",
    # Segundo icone (o da direita), com o tempo ate o reset. modo_cor 'escala'
    # = mesma regra de cor do uso, aplicada ao quanto da janela JA PASSOU;
    # 'fixa' = ciano sempre.
    "icone_tempo": {"ativo": True, "modo_cor": "escala", "cor": "#0fadd6",
                    "cor_final": "#6e7681"},
}


def carregar() -> dict:
    """Config do usuario sobre os defaults. Arquivo corrompido nao derruba o app."""
    if not CONFIG_PATH.exists():
        gravar_padrao()
        return dict(PADRAO)
    try:
        dados = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Config quebrada e motivo pra ignorar a config, nunca pra nao abrir o
        # medidor - ele vale mais rodando com defaults do que nao rodando.
        return dict(PADRAO)
    fundido = dict(PADRAO)
    fundido.update(dados)
    return fundido


def gravar_padrao() -> Path:
    DIR_CONFIG.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(PADRAO, indent=2), encoding="utf-8")
    return CONFIG_PATH


def abrir_no_editor() -> None:
    """Abre a config no editor padrao do sistema."""
    if not CONFIG_PATH.exists():
        gravar_padrao()
    if os.name == "nt":
        os.startfile(CONFIG_PATH)                       # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open",
                          str(CONFIG_PATH)])
