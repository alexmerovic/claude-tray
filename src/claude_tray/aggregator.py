#!/usr/bin/env python3
"""Agrega o consumo de tokens do Claude Code na JANELA DE 5H corrente.

Fonte de verdade: os transcripts em ~/.claude/projects/**/*.jsonl.
Nenhuma chamada de API, nenhuma credencial. Tudo deterministico (art. 17-20).

DUAS ARMADILHAS RESOLVIDAS AQUI
-------------------------------
1. Dedupe por `message.id`. Cada resposta do assistente aparece VARIAS vezes no
   JSONL (uma linha por bloco de conteudo), sempre com o mesmo `usage`. Somar
   linha a linha infla ~2,5x. Mesma logica de session_metrics.py.

2. Filtro por mtime. Sao 252 arquivos; abrir todos a cada 30s e desperdicio.
   Se uma mensagem caiu nas ultimas 5h, o arquivo dela foi modificado nas
   ultimas 5h. Lemos so esses (tipico: 2-5 arquivos).

MODELAGEM DA JANELA (inferencia, nao spec publicada)
----------------------------------------------------
O bloco de 5h comeca na primeira mensagem apos >=5h de ociosidade, com o
inicio ancorado na hora cheia, e expira 5h depois. Reproduz o RESET do
contador. Uma janela deslizante so decairia, nunca zeraria.

O DENOMINADOR NAO EXISTE LOCALMENTE. Vasculhado: .claude.json, stats-cache.json
e o resto de ~/.claude/ nao guardam o limite do plano. O `limite_tokens` do
config.json e CALIBRACAO do operador (ancorada no que /usage mostrar), portanto
o percentual e HIPOTESE CALIBRADA, nao fato (art. 27-28). Os valores absolutos
de token sao fato.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
JANELA = timedelta(hours=5)

# Folga de leitura: cobre a janela e ainda deixa margem pra detectar o gap que
# define o inicio do bloco.
FOLGA_LEITURA = timedelta(hours=12)

# Preco por milhao de tokens (USD). Serve pra ordem de grandeza, nao e fatura.
PRECOS = {
    "claude-opus-5":    {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
    "claude-sonnet-5":  {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5": {"input": 1.00, "output":  5.00, "cache_write": 1.25, "cache_read": 0.10},
}
PRECO_PADRAO = PRECOS["claude-opus-5"]

CAMPOS = (
    ("input",       "input_tokens"),
    ("output",      "output_tokens"),
    ("cache_write", "cache_creation_input_tokens"),
    ("cache_read",  "cache_read_input_tokens"),
)


def _preco(modelo: str) -> dict:
    for chave, tabela in PRECOS.items():
        if modelo and modelo.startswith(chave):
            return tabela
    return PRECO_PADRAO


def _parse_ts(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _arquivos_recentes(agora: datetime) -> list[Path]:
    """So transcripts tocados dentro da folga. Evita abrir os 252."""
    if not PROJECTS_DIR.is_dir():
        return []
    corte = (agora - FOLGA_LEITURA).timestamp()
    recentes = []
    for caminho in PROJECTS_DIR.rglob("*.jsonl"):
        try:
            if caminho.stat().st_mtime >= corte:
                recentes.append(caminho)
        except OSError:
            continue
    return recentes


def _eventos(caminhos: list[Path], desde: datetime) -> list[dict]:
    """Registros de uso deduplicados por message.id, ordenados no tempo."""
    vistos: set[str] = set()
    eventos: list[dict] = []

    for caminho in caminhos:
        try:
            bruto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for linha in bruto.splitlines():
            if not linha.strip():
                continue
            try:
                entrada = json.loads(linha)
            except json.JSONDecodeError:
                continue

            mensagem = entrada.get("message") or {}
            uso = mensagem.get("usage")
            msg_id = mensagem.get("id")
            if not uso or not msg_id or msg_id in vistos:
                continue

            ts = _parse_ts(entrada.get("timestamp"))
            if not ts or ts < desde:
                continue

            vistos.add(msg_id)
            eventos.append({
                "ts": ts,
                "modelo": mensagem.get("model") or "",
                "sessao": entrada.get("sessionId") or entrada.get("session_id") or "",
                "tokens": {destino: (uso.get(origem) or 0) for destino, origem in CAMPOS},
            })

    eventos.sort(key=lambda e: e["ts"])
    return eventos


def _inicio_do_bloco(eventos: list[dict], agora: datetime):
    """Inicio do bloco de 5h vigente, ancorado na hora cheia.

    Percorre do mais antigo ao mais novo abrindo bloco novo sempre que houver
    gap >= 5h. Devolve None se o ultimo bloco ja expirou (ninguem consumindo).
    """
    inicio = None
    anterior = None

    for evento in eventos:
        ts = evento["ts"]
        if inicio is None or (ts - inicio) >= JANELA or (anterior and (ts - anterior) >= JANELA):
            inicio = ts.replace(minute=0, second=0, microsecond=0)
        anterior = ts

    if inicio is None or (agora - inicio) >= JANELA:
        return None
    return inicio


def estado(limite: float, base: str = "ponderado") -> dict:
    """Fotografia da janela de 5h corrente.

    base: 'ponderado' (input-equivalente, padrao), 'bruto' (soma crua dos 4
    tipos) ou 'custo' (USD estimado). O percentual sai da base escolhida.
    """
    agora = datetime.now(timezone.utc)
    eventos = _eventos(_arquivos_recentes(agora), agora - FOLGA_LEITURA)
    inicio = _inicio_do_bloco(eventos, agora)

    tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    custo = 0.0
    ponderado = 0.0
    sessoes: set[str] = set()
    modelos: set[str] = set()
    ultima = None
    fim = None

    if inicio is not None:
        fim = inicio + JANELA
        for evento in eventos:
            if not (inicio <= evento["ts"] < fim):
                continue
            tabela = _preco(evento["modelo"])
            for chave, quantidade in evento["tokens"].items():
                tokens[chave] += quantidade
                custo += quantidade / 1_000_000 * tabela[chave]
                # Input-equivalente: cada tipo pesa o quanto ele custa em
                # relacao ao input do MESMO modelo. Somar os quatro tipos crus
                # seria somar reais com centavos - cache_read costuma ser ~97%
                # do volume bruto e custa 10% do input.
                ponderado += quantidade * (tabela[chave] / tabela["input"])
            if evento["sessao"]:
                sessoes.add(evento["sessao"])
            if evento["modelo"]:
                modelos.add(evento["modelo"])
            ultima = evento["ts"]

    total = sum(tokens.values())
    ponderado = int(ponderado)
    custo = round(custo, 2)

    # A medida que vai contra o limite depende da base escolhida no config.
    medida = {"bruto": total, "ponderado": ponderado, "custo": custo}[base]
    pct = (medida / limite * 100) if limite > 0 else 0.0

    return {
        "ativo": inicio is not None,
        "inicio": inicio,
        "fim": fim,
        "restante_seg": int((fim - agora).total_seconds()) if fim else 0,
        "tokens": tokens,
        "total": total,
        "ponderado": ponderado,
        "custo_usd": custo,
        "base": base,
        "medida": medida,
        "pct": pct,
        "sessoes": len(sessoes),
        "modelos": sorted(modelos),
        "ultima_atividade": ultima,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Token consumption in the current 5h window.")
    parser.add_argument("--limite", type=float, default=10_000_000)
    parser.add_argument("--base", choices=("ponderado", "bruto", "custo"), default="ponderado")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    dados = estado(args.limite, args.base)

    if args.json:
        serial = dict(dados)
        for campo in ("inicio", "fim", "ultima_atividade"):
            serial[campo] = dados[campo].isoformat() if dados[campo] else None
        print(json.dumps(serial, indent=2, ensure_ascii=False))
    elif not dados["ativo"]:
        print("Nenhum bloco de 5h ativo (sem atividade recente).")
    else:
        t = dados["tokens"]
        ini = dados["inicio"].astimezone().strftime("%H:%M")
        fin = dados["fim"].astimezone().strftime("%H:%M")
        horas, resto = divmod(dados["restante_seg"], 3600)
        print(f"Janela 5h: {ini} -> {fin}  (reset em {horas}h{resto // 60:02d})")
        print()
        print(f"  saida       {t['output']:>12,}")
        print(f"  entrada     {t['input']:>12,}")
        print(f"  cache write {t['cache_write']:>12,}")
        print(f"  cache read  {t['cache_read']:>12,}")
        print(f"  {'-' * 24}")
        print(f"  bruto       {dados['total']:>12,}   (soma crua dos 4 tipos)")
        print(f"  ponderado   {dados['ponderado']:>12,}   (input-equivalente)")
        print(f"  custo USD   {dados['custo_usd']:>12}   (estimado)")
        print()
        print(f"MEDIDOR [base={dados['base']}]: {dados['medida']:,} / {args.limite:,.0f}"
              f"  =  {dados['pct']:.1f}%")
        print(f"Sessoes: {dados['sessoes']}  Modelos: {', '.join(dados['modelos']) or '-'}")
