#!/usr/bin/env python3
# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""SessionStart hook: garante que o medidor esteja de pe quando voce comeca.

CONTRATO DO HOOK (importante pra qualquer edicao aqui)
-----------------------------------------------------
- O stdout de um hook de SessionStart entra no CONTEXTO da sessao. Cada linha
  impressa aqui e cara: vira token em toda conversa. Silencio e o default.
- Ele roda ANTES de voce digitar qualquer coisa. Tudo que demora aqui atrasa a
  abertura da sessao - por isso a consulta usa --offline (sem rede).
- Falhar nunca pode travar a sessao: qualquer excecao vira saida silenciosa.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

# Sem console e sem janela: o processo filho sobrevive ao fim do hook.
DESACOPLADO = 0x00000008 | 0x00000200        # DETACHED_PROCESS | NEW_PROCESS_GROUP


def estado() -> dict:
    """O que da pra saber sem gastar rede nem tempo."""
    cli = shutil.which("claude-tray")
    if not cli:
        return {"instalado": False, "rodando": False, "autostart": False}

    try:
        saida = subprocess.run(
            [cli, "--status", "--json", "--offline"],
            capture_output=True, text=True, timeout=10)
        dados = json.loads(saida.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return {"instalado": True, "rodando": False, "autostart": False}

    return {
        "instalado": True,
        "rodando": bool(dados.get("running")),
        "autostart": bool(dados.get("autostart")),
    }


def decidir(situacao: dict) -> str:
    """O QUE FAZER quando uma sessao do Claude Code abre.

    Retorna uma de tres acoes:
        "nada"    - sai calado (nenhum token gasto, nenhum processo novo)
        "subir"   - lanca o medidor agora, em silencio
        "avisar"  - imprime UMA linha, que entra no contexto da sessao

    <<< ESCREVA A POLITICA AQUI >>>

    `situacao` traz tres booleanos: `instalado` (o CLI existe no PATH),
    `rodando` (ja tem medidor de pe) e `autostart` (esta registrado no logon).

    OS TRADE-OFFS REAIS, porque nao existe resposta obvia:

    - SUBIR SEMPRE que nao estiver rodando e o mais util e o mais invasivo:
      abrir uma sessao passa a ter efeito colateral fora do terminal. Quem
      fechou o medidor de proposito o ve ressuscitar sem ter pedido.

    - NUNCA SUBIR (so avisar) respeita a intencao do usuario, mas custa uma
      linha de contexto em TODA sessao - e depois de ler o mesmo aviso trinta
      vezes ele vira ruido que ninguem le.

    - AVISAR SO QUANDO NAO ESTA INSTALADO e o meio-termo comum: o hook so fala
      quando tem noticia nova (falta instalar), e cala nos outros casos.

    - `autostart` muda a leitura de "nao esta rodando". Com autostart ativo e
      medidor parado, ou o logon ainda nao aconteceu ou o usuario fechou na
      mao - e ai subir de novo contraria uma decisao explicita dele.

    POLITICA ESCOLHIDA: falar so quando ha noticia NOVA.
    ---------------------------------------------------
    "Nao instalado" e a unica situacao em que o usuario pode nao saber de algo:
    ele instalou o plugin e o medidor nao veio junto (sao dois passos - plugin
    pelo Claude Code, pacote pelo pipx/uv). Vale a linha de contexto porque tem
    acao clara e acontece UMA vez: instalou, o aviso some pra sempre.

    "Instalado e parado" nao e noticia - quem fechou o medidor sabe que fechou.
    Repetir isso a cada sessao gastaria contexto todo dia pra contar ao usuario
    uma decisao que foi dele.

    E "subir" nunca e retornado: abrir uma sessao de terminal nao deveria ter
    efeito colateral fora do terminal. Quem quiser o medidor sempre de pe tem
    `claude-tray --autostart`, que e explicito e roda uma vez so. A mecanica de
    subir continua em main() de proposito - mude o `return` abaixo e ela
    funciona, sem precisar escrever nada.
    """
    if not situacao["instalado"]:
        return "avisar"
    return "nada"


def main() -> int:
    situacao = estado()
    acao = decidir(situacao)

    if acao == "subir":
        alvo = shutil.which("claude-trayw") or shutil.which("claude-tray")
        if alvo:
            kwargs = {"creationflags": DESACOPLADO} if os.name == "nt" else {"start_new_session": True}
            subprocess.Popen([alvo], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **kwargs)
    elif acao == "avisar":
        if not situacao["instalado"]:
            print("claude-tray is not installed: `uv tool install claude-tray`")
        elif not situacao["rodando"]:
            print("claude-tray is not running: run `claude-trayw` to see usage in the tray.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Um medidor de uso nunca pode ser o motivo de uma sessao nao abrir.
        sys.exit(0)
