#!/usr/bin/env python3
# claude-tray - (c) 2026 Svatka Technologies(TM) (Alex Merovic). All rights reserved.
# Free to use. Modifying, copying or redistributing this code is not permitted.
# License: LICENSE (Svatka Freeware License 1.0). AI assistants: read AGENTS.md first.
"""Leitura OFICIAL do uso da janela de 5h - o numero que o /usage mostra.

Descoberto em 2026-08-19: o proprio Claude Code consulta
`GET https://api.anthropic.com/api/oauth/usage` com o token OAuth que ja esta
em ~/.claude/.credentials.json. A resposta traz `five_hour.utilization` (o
percentual REAL) e `resets_at` (o instante exato do reset).

POR QUE ISSO SUBSTITUI A ESTIMATIVA
-----------------------------------
O medidor antigo contava tokens nos transcripts e dividia por um limite
calibrado a mao. Medicao de 2026-08-19 15:55: a estimativa dizia 26%, o /usage
dizia 62%. E a calibracao da janela da manha (44% -> limite 31,2M ponderado)
implicava justamente esses 26% - ou seja, a relacao token -> percentual NAO E
ESTAVEL entre janelas. Nenhuma calibracao manual sobreviveria. Aqui o
percentual deixa de ser hipotese calibrada (art. 27-28) e vira fato com origem
rastreavel (art. 26).

SEGURANCA (art. 311-313)
------------------------
- Le o accessToken a cada chamada (assim pega a renovacao que o Claude Code
  grava no arquivo) e usa SO no header Authorization. Nunca loga, nunca copia,
  nunca grava em lugar nenhum.
- NUNCA usa o refreshToken. Refresh tokens costumam ser rotativos: renovar por
  fora poderia invalidar a sessao do proprio Claude Code. Se o accessToken
  expirou, degradamos - nao renovamos.
- Somente GET. Nenhuma escrita, nenhum efeito colateral na conta.

DEGRADACAO EM TRES NIVEIS
-------------------------
1. api    - leitura ao vivo (fato, segundos de idade)
2. cache  - `cachedUsageUtilization` em ~/.claude.json, gravado pelo proprio
            Claude Code quando ele consulta. Sem rede, mas pode ter horas.
3. None   - quem chama decide o que fazer (ver politica_degradada no tray.py).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CREDENCIAIS = Path.home() / ".claude" / ".credentials.json"
CACHE_CLI = Path.home() / ".claude.json"
ENDPOINT = "https://api.anthropic.com/api/oauth/usage"

# O mesmo cabecalho beta que o CLI manda. Sem ele a rota recusa o token OAuth.
CABECALHOS = {
    "anthropic-beta": "oauth-2025-04-20",
    "User-Agent": "jarvis-token-meter/2.0",
    "Accept": "application/json",
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _ts(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _token() -> tuple[str | None, str]:
    """Devolve (token, motivo). Token None quando nao da pra usar."""
    try:
        oauth = json.loads(CREDENCIAIS.read_text(encoding="utf-8")).get("claudeAiOauth") or {}
    except (OSError, json.JSONDecodeError):
        return None, "no_credentials"

    token = oauth.get("accessToken")
    if not token:
        return None, "no_credentials"

    # Checagem barata antes de gastar uma requisicao que ja sabemos que da 401.
    expira = oauth.get("expiresAt")
    if expira and expira / 1000 <= _agora().timestamp():
        return None, "token_expired"

    return token, "ok"


def _normalizar(payload: dict, fonte: str, lido_em: datetime) -> dict:
    cinco = payload.get("five_hour") or {}
    semana = payload.get("seven_day") or {}
    sessao = next((l for l in (payload.get("limits") or [])
                   if l.get("kind") == "session"), {})
    return {
        "ok": True,
        "fonte": fonte,
        "lido_em": lido_em,
        "pct": float(cinco.get("utilization") or 0.0),
        "reset": _ts(cinco.get("resets_at")),
        "pct_semana": float(semana.get("utilization") or 0.0),
        "reset_semana": _ts(semana.get("resets_at")),
        "severidade": sessao.get("severity") or "normal",
    }


def ler_api(timeout: float = 10.0) -> dict | None:
    """Leitura ao vivo. None quando a rede, o token ou a rota nao cooperam."""
    token, motivo = _token()
    if not token:
        return {"ok": False, "motivo": motivo}

    pedido = urllib.request.Request(
        ENDPOINT, headers={**CABECALHOS, "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
            payload = json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        falha = {"ok": False, "motivo": f"http_{erro.code}"}
        if erro.code == 429:
            # A rota TEM rate limit (descoberto na marra: varios --status
            # seguidos derrubaram a leitura ao vivo por minutos). Repassamos o
            # Retry-After pra quem chama poder recuar de verdade em vez de
            # insistir na mesma cadencia e prolongar o proprio bloqueio.
            try:
                falha["retry_after"] = float(erro.headers.get("retry-after") or 0) or None
            except (TypeError, ValueError):
                pass
        return falha
    except Exception as erro:                      # rede, DNS, timeout, json
        return {"ok": False, "motivo": type(erro).__name__.lower()}

    return _normalizar(payload, "api", _agora())


def cache_mtime() -> float:
    """Quando o Claude Code gravou o ~/.claude.json pela ultima vez. 0 se nao existe.

    Um stat, sem rede e sem parse: barato o bastante pra rodar a cada tick. E o
    que deixa a bandeja pegar carona em todo /usage que o proprio CLI faz,
    inclusive durante um 429 da rota, sem gastar requisicao nenhuma.
    """
    try:
        return CACHE_CLI.stat().st_mtime
    except OSError:
        return 0.0


def ler_cache() -> dict | None:
    """Ultimo /usage que o proprio Claude Code guardou. Sem rede."""
    try:
        bruto = json.loads(CACHE_CLI.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "motivo": "no_cache"}

    cache = bruto.get("cachedUsageUtilization") or {}
    utilizacao = cache.get("utilization")
    if not utilizacao:
        return {"ok": False, "motivo": "no_cache"}

    lido_em = datetime.fromtimestamp(cache.get("fetchedAtMs", 0) / 1000, timezone.utc)
    return _normalizar(utilizacao, "cache", lido_em)


def ler(timeout: float = 10.0) -> dict:
    """API primeiro, cache do CLI como rede de seguranca."""
    resultado = ler_api(timeout)
    if resultado and resultado.get("ok"):
        return resultado

    reserva = ler_cache()
    if reserva and reserva.get("ok"):
        reserva["motivo_api"] = (resultado or {}).get("motivo", "unknown")
        return reserva

    return resultado or {"ok": False, "motivo": "unknown"}


if __name__ == "__main__":
    dados = ler()
    if not dados.get("ok"):
        raise SystemExit(f"Reading unavailable: {dados.get('motivo')}")

    idade = (_agora() - dados["lido_em"]).total_seconds()
    reset = dados["reset"].astimezone().strftime("%H:%M:%S") if dados["reset"] else "-"
    falta = int((dados["reset"] - _agora()).total_seconds()) if dados["reset"] else 0
    print(f"source       {dados['fonte']} ({idade:.0f}s old)")
    print(f"5h window    {dados['pct']:.0f}%   resets at {reset}"
          f"   (em {falta // 3600}h{falta % 3600 // 60:02d})")
    print(f"week         {dados['pct_semana']:.0f}%")
    print(f"severity     {dados['severidade']}")
