#!/usr/bin/env python3
"""Medidor de tokens do Claude Code na bandeja do Windows.

Um icone ao lado do relogio, com o percentual da janela de 5h corrente.
Sem janela, sem overlay, sem nada voando na tela.

Rodar:      claude-trayw             (sem console)
Depurar:    claude-tray --debug      (imprime cada refresh)

FONTE DO PERCENTUAL (mudou em 2026-08-19)
-----------------------------------------
O numero vem de usage_api.py - a MESMA rota que o /usage do Claude Code usa.
Antes era estimativa: tokens dos transcripts divididos por um limite calibrado
a mao. Media 26% quando o /usage real dizia 62%, porque a relacao token ->
percentual nao e estavel entre janelas. Os transcripts continuam servindo, mas
so para os valores ABSOLUTOS do tooltip (tokens e custo), que sao fato.

O RELOGIO ANDA SOZINHO. `resets_at` e um instante absoluto, entao o tempo
restante e subtracao local a cada tick - nao depende de rede nem de leitura
nova. Rede caida congela o percentual, nunca o relogio.

O Windows nao sabe desenhar TEXTO na bandeja - so aceita um HICON. Entao o
numero e desenhado numa bitmap via Pillow a cada refresh e convertido em icone.
O pystray chama DestroyIcon no handle anterior a cada troca (_update_icon ->
_release_icon), entao nao ha vazamento de handle GDI - que e o bug classico
desta categoria de app.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import pystray

from . import aggregator, config, usage_api
from .config import PADRAO

NEWLINE = chr(10)

# Canvas grande: o Windows reduz pra 16x16 (ou 20/24 em DPI alto) com
# antialiasing. Desenhar direto em 16x16 sairia serrilhado.
LADO = 64


carregar_config = config.carregar


def classificar(pct: float, limiares: dict) -> str:
    """Traduz 'quanto ja foi consumido' em faixa: folgado | tranquilo | atencao | critico.

    A MESMA escala serve aos dois icones, e e isso que faz o par funcionar. O
    icone de uso recebe o percentual da cota; o de tempo recebe o percentual da
    JANELA ja decorrida. Como as duas medem consumo, as cores sao comparaveis
    de relance:

        uso mais quente que o tempo  -> gastando rapido demais, freia
        tempo mais quente que o uso  -> sobra cota e falta relogio, acelera
        as duas iguais               -> ritmo casado com a janela

    E por isso que "vermelho" no icone de tempo nao e alarme: reset chegando e
    coisa boa. Quem alarma e o DESCOLAMENTO entre os dois.

    TRADE-OFF (ajuste os limiares no config.json conforme seu ritmo real):
    cortes baixos avisam cedo e voce planeja, mas os icones vivem ambar e viram
    ruido de fundo; cortes altos mantem tudo limpo, mas o aviso chega quando ja
    nao da mais pra reorganizar o trabalho da janela.
    """
    if pct >= limiares["critico"]:
        return "critico"
    if pct >= limiares["atencao"]:
        return "atencao"
    if pct >= limiares.get("folgado", 30):
        return "tranquilo"
    return "folgado"


def _fonte(tamanho: int):
    for nome in ("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"):
        caminho = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / nome
        if caminho.exists():
            try:
                return ImageFont.truetype(str(caminho), tamanho)
            except OSError:
                continue
    return ImageFont.load_default()


def rotulo_do_icone(dados: dict) -> str:
    """Decide os 1-2 caracteres que aparecem DENTRO do icone.

    Cabem 2 caracteres legiveis em 16x16 - e so. Essa escassez forca uma
    escolha: dos dois numeros que existem (quanto voce ja gastou e quanto falta
    pro reset), qual merece o espaco em cada momento?

    O comportamento abaixo e o default: sempre o percentual. Ele responde
    "quanto eu queimei" - otimo no comeco da janela, quando da pra reorganizar
    o trabalho. Mas quando voce ja estourou, o percentual congela numa noticia
    ruim que nao muda, enquanto o dado acionavel virou o relogio: em quanto
    tempo isso libera.

    TODO (Alex): reescreva conforme seu ritmo real de trabalho. O `dados` traz
    tudo que voce precisa - `pct`, `restante_seg`, `ativo`, `sessoes`,
    `custo_usd`. Ideias: trocar pro tempo restante ("2h" / "20m") acima de um
    certo percentual; mostrar o relogio so na ultima meia hora; ou manter o
    percentual sempre e assumir que o reset voce olha no hover.
    """
    if not dados["ativo"]:
        return "-"
    if dados["pct"] >= 100:
        return "!!"            # 3 digitos nao sao legiveis em 16x16
    return str(int(dados["pct"]))


def rotulo_tempo(restante_seg: int) -> str:
    """Tempo ate o reset em no maximo 2 caracteres.

    >=1h vira "3h"; abaixo disso, os minutos crus ("45", "20", "5"). Os minutos
    sem sufixo seriam ambiguos com o percentual - quem desfaz a ambiguidade e a
    COR do icone (ciano), nao um caractere, porque caractere aqui e o recurso
    escasso.
    """
    if restante_seg <= 0:
        return "-"
    minutos = restante_seg // 60
    if minutos >= 60:
        return f"{minutos // 60}h"
    return str(max(minutos, 1))


def desenhar(pct: float, cor: str, ativo: bool, rotulo: str | None = None,
             icone_cfg: dict | None = None, arco_pct: float | None = None) -> Image.Image:
    """Arco de progresso + rotulo no centro, fundo transparente.

    Em 16x16 o arco COMPETE com o numero - se a fonte for grande demais os dois
    encostam e o numero deixa de ser lido como numero. Por isso arco fino,
    numero folgado, e a opcao de desligar o arco de vez pelo config.

    `arco_pct` desacopla o que o ARCO mostra do que o NUMERO mostra. Com ele o
    numero pode dizer o uso enquanto o arco diz o tempo restante - as duas
    perguntas num icone so.
    """
    cfg = {**PADRAO["icone"], **(icone_cfg or {})}
    espessura = int(cfg.get("espessura", 4))
    if arco_pct is None:
        arco_pct = pct
    img = Image.new("RGBA", (LADO, LADO), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if cfg.get("arco", True) and espessura > 0:
        caixa = (espessura // 2, espessura // 2,
                 LADO - espessura // 2 - 1, LADO - espessura // 2 - 1)
        # Trilho: mostra quanto falta. Sem ele, 8% e 80% parecem a mesma coisa.
        d.arc(caixa, 0, 360, fill="#30363d", width=espessura)
        if ativo and arco_pct > 0:
            # Comeca em -90 (topo) e anda horario, como um relogio.
            d.arc(caixa, -90, -90 + min(arco_pct, 100) * 3.6, fill=cor, width=espessura)

    if rotulo is None:
        rotulo = rotulo_do_icone({"ativo": ativo, "pct": pct, "restante_seg": 0})

    # Chaves do JSON vem como string; normaliza pra int.
    tabela = {int(k): v for k, v in cfg.get("fonte", {}).items()}
    tamanho = tabela.get(len(rotulo), min(tabela.values()) if tabela else 22)
    fonte = _fonte(tamanho)
    esq, topo, dir_, base = d.textbbox((0, 0), rotulo, font=fonte)
    d.text(
        ((LADO - (dir_ - esq)) / 2 - esq, (LADO - (base - topo)) / 2 - topo),
        rotulo, font=fonte, fill=cor,
    )
    return img


def formatar(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def projecao(dados: dict) -> str:
    """Extrapola o ritmo atual ate o fim da janela.

    E esta linha que responde a pergunta real - "da tempo?". Uso e relogio
    isolados nao decidem nada: 80% com 3h pela frente estoura, 80% com 5 min
    nao. O ritmo cruza os dois.

    Extrapolacao linear de proposito. Modelo mais esperto exigiria prever o que
    voce vai fazer nas proximas horas - isso e chute com cara de precisao.
    """
    decorrido_h = max(5 - dados["restante_seg"] / 3600, 0.05)
    restante_h = dados["restante_seg"] / 3600
    ritmo = dados["pct"] / decorrido_h                      # %/h

    if dados["pct"] >= 100:
        return f"Capped - frees up in {int(restante_h)}h{int(restante_h % 1 * 60):02d}"

    fim = dados["pct"] + ritmo * restante_h
    if fim < 100:
        return f"Pace {ritmo:.0f}%/h - ends at {fim:.0f}%"

    ate_estourar = (100 - dados["pct"]) / ritmo if ritmo > 0 else 99
    return f"Pace {ritmo:.0f}%/h - caps out in {int(ate_estourar)}h{int(ate_estourar % 1 * 60):02d}"


def politica_degradada(idade_seg: float, stale_seg: float) -> str:
    """O que o icone faz quando a leitura oficial para de chegar.

    TRADE-OFF (ajuste `stale_seg` no config, ou reescreva esta funcao):
    manter o ultimo percentual e a escolha certa na maioria das vezes - sem
    Claude Code rodando o consumo nao sobe, entao o numero velho continua
    verdadeiro. Mas se a rede caiu COM voce trabalhando, ele congela numa
    noticia otimista demais, que e o pior jeito de errar num medidor.

    Default: acima de stale_seg o numero fica cinza. Cinza aqui nao quer dizer
    "janela inativa" - quer dizer "nao confio mais neste numero". O relogio,
    esse, continua correto de qualquer jeito.
    """
    return "confiavel" if idade_seg <= stale_seg else "velha"


def tooltip(dados: dict, cfg: dict) -> str:
    """Detalhe do hover. O Shell_NotifyIcon corta em 127 caracteres."""
    if not dados["ativo"]:
        if dados.get("motivo"):
            return f"Claude - no official reading ({dados['motivo']})"
        return "Claude - no active 5h window"

    horas, resto = divmod(max(dados["restante_seg"], 0), 3600)
    fim = dados["reset"].astimezone().strftime("%H:%M")
    linhas = [
        f"Usage {dados['pct']:.0f}%  -  week {dados['pct_semana']:.0f}%",
        f"Resets in {horas}h{resto // 60:02d} (at {fim})",
        projecao(dados),
        _linha_origem(dados),
    ]
    return NEWLINE.join(linhas)[:127]


def _linha_origem(dados: dict) -> str:
    """Ultima linha: de onde veio o numero e ha quanto tempo.

    Existe porque um medidor que nao conta a idade da propria leitura mente por
    omissao - foi exatamente assim que a versao anterior ficou 6h defasada sem
    dar nenhum sinal.
    """
    consumo = dados.get("consumo")
    idade = int(dados.get("idade") or 0)
    origem = "cache" if dados.get("fonte") == "cache" else "official"
    if consumo:
        return (f"{formatar(consumo['total'])} tok - US$ {consumo['custo_usd']:.0f}"
                f" - {origem} {idade}s")
    return f"{origem} reading, {idade}s old"


def tooltip_tempo(dados: dict) -> str:
    """Hover do icone de tempo: o relogio primeiro, o uso como contexto."""
    if not dados["ativo"]:
        return "Claude - no active 5h window"

    horas, resto = divmod(max(dados["restante_seg"], 0), 3600)
    fim = dados["reset"].astimezone().strftime("%H:%M")
    linhas = [
        f"Resets in {horas}h{resto // 60:02d}  (at {fim})",
        f"Window usage: {dados['pct']:.0f}%",
        f"Pace: {dados['pct'] / max(5 - dados['restante_seg'] / 3600, 0.1):.0f}%/h",
    ]
    return "\n".join(linhas)[:127]


class Medidor:
    def __init__(self, debug: bool = False):
        self.cfg = carregar_config()
        self.debug = debug
        self.ultimo: dict | None = None
        self.oficial: dict | None = None      # ultima leitura oficial que deu certo
        self.consumo: dict | None = None      # ultimo agregado dos transcripts
        self.motivo: str | None = None        # por que a leitura falhou, se falhou
        self.ultimo_poll = 0.0
        self.ultimo_consumo = 0.0

        menu = pystray.Menu(
            pystray.MenuItem(self._resumo, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Refresh now", self._agora),
            pystray.MenuItem("Open config.json", self._abrir_config),
            pystray.MenuItem("Reload config", self._recarregar),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._sair),
        )

        self.icone = pystray.Icon(
            "claude_tokens",
            desenhar(0, self.cfg["cores"]["inativo"], False, icone_cfg=self.cfg.get("icone")),
            "Claude - starting...",
            menu=menu,
        )

        # Segundo icone: so o tempo ate o reset. Uso sozinho nao decide nada -
        # 80% com 3h pela frente e 80% com 5 min sao situacoes opostas.
        cfg_tempo = {**PADRAO["icone_tempo"], **self.cfg.get("icone_tempo", {})}
        self.cfg_tempo = cfg_tempo
        self.icone_tempo = None
        if cfg_tempo.get("ativo", True):
            self.icone_tempo = pystray.Icon(
                "claude_tempo",
                desenhar(0, cfg_tempo["cor_final"], False, "-", self.cfg.get("icone")),
                "Claude - 5h window reset",
                menu=menu,
            )

    def _resumo(self, _=None) -> str:
        if not self.ultimo or not self.ultimo["ativo"]:
            return "No active window"
        d = self.ultimo
        consumo = d.get("consumo")
        cauda = f"  -  US$ {consumo['custo_usd']:.2f}" if consumo else ""
        return f"{d['pct']:.0f}%  -  week {d['pct_semana']:.0f}%{cauda}"

    def _agora(self, *_):
        self._poll_oficial()
        self._poll_consumo()
        self.atualizar()

    def _abrir_config(self, *_):
        config.abrir_no_editor()

    def _recarregar(self, *_):
        self.cfg = carregar_config()
        self.cfg_tempo = {**PADRAO["icone_tempo"], **self.cfg.get("icone_tempo", {})}
        self.atualizar()

    def _sair(self, *_):
        self._sair_tudo()

    # ---- coleta ---------------------------------------------------------

    def _poll_oficial(self):
        """Percentual e reset REAIS. Uma requisicao GET, sem efeito colateral."""
        leitura = usage_api.ler()
        self.ultimo_poll = time.monotonic()
        if leitura.get("ok") and self._mais_fresca(leitura):
            self.oficial = leitura
            self.motivo = None
        elif leitura.get("ok"):
            # Chegou leitura valida, porem mais VELHA que a que ja tenho - e o
            # cache do CLI (que pode ter horas) entrando no lugar de uma leitura
            # boa de 1 minuto atras, so porque a rede piscou. Aceitar seria
            # regredir no tempo e ainda por cima em silencio.
            self.motivo = leitura.get("motivo_api") or "stale_reading"
        else:
            # Nao apaga a leitura anterior: numero velho identificado vale mais
            # que numero nenhum. Quem decide ate quando e politica_degradada.
            self.motivo = leitura.get("motivo")
        if self.debug:
            print(f"[api] {leitura.get('fonte') or leitura.get('motivo')}"
                  f" pct={leitura.get('pct')}", flush=True)

    def _mais_fresca(self, leitura: dict) -> bool:
        """Uma leitura so substitui a anterior se for mais recente que ela."""
        if not self.oficial:
            return True
        return leitura["lido_em"] >= self.oficial["lido_em"]

    def _poll_consumo(self):
        """Tokens absolutos dos transcripts - so pro tooltip. Custa I/O local."""
        self.ultimo_consumo = time.monotonic()
        try:
            self.consumo = aggregator.estado(self.cfg["limite"], self.cfg["base"])
        except Exception as erro:
            self.consumo = None
            if self.debug:
                print(f"[consumo] {erro!r}", flush=True)

    def _intervalo_api(self) -> float:
        base = float(self.cfg.get("intervalo_api_seg", 60))
        reset = (self.oficial or {}).get("reset")
        if reset and (reset - datetime.now(timezone.utc)).total_seconds() <= 0:
            return min(base, 30.0)      # janela virou: reconfirmar logo
        return base

    def snapshot(self) -> dict:
        """Estado agora. O RELOGIO e recalculado aqui, nao na hora do poll -
        e por isso que ele anda a cada tick mesmo sem rede nova."""
        agora = datetime.now(timezone.utc)
        oficial = self.oficial
        if not oficial:
            return {"ativo": False, "pct": 0.0, "pct_semana": 0.0, "restante_seg": 0,
                    "reset": None, "idade": None, "fonte": None,
                    "motivo": self.motivo, "consumo": self.consumo}

        restante = int((oficial["reset"] - agora).total_seconds()) if oficial["reset"] else 0
        return {
            "ativo": restante > 0,
            "pct": oficial["pct"],
            "pct_semana": oficial["pct_semana"],
            "restante_seg": max(restante, 0),
            "reset": oficial["reset"],
            "idade": (agora - oficial["lido_em"]).total_seconds(),
            "fonte": oficial["fonte"],
            "motivo": self.motivo,
            "consumo": self.consumo,
        }

    # ---- desenho --------------------------------------------------------

    def atualizar(self):
        dados = self.snapshot()
        self.ultimo = dados

        faixa = classificar(dados["pct"], self.cfg["limiares"]) if dados["ativo"] else "inativo"
        if dados["ativo"] and politica_degradada(
                dados["idade"] or 0, float(self.cfg.get("stale_seg", 300))) == "velha":
            faixa = "inativo"
        cor = self.cfg["cores"][faixa]

        # Fracao da janela JA CONSUMIDA. E esta - e nao a sobra - que alimenta
        # cor e anel do icone de tempo, porque e ela que anda no mesmo sentido
        # que o uso: as duas comecam em zero e crescem ate o limite.
        sobra_pct = max(0.0, min(dados["restante_seg"] / (5 * 3600) * 100, 100))
        decorrido_pct = 100 - sobra_pct
        arco = sobra_pct if self.cfg.get("modo_arco", "tempo") == "tempo" else dados["pct"]

        self.icone.icon = desenhar(dados["pct"], cor, dados["ativo"],
                                   rotulo_do_icone(dados), self.cfg.get("icone"), arco)
        self.icone.title = tooltip(dados, self.cfg)

        if self.icone_tempo is not None:
            # A cor do relogio sai da MESMA escala do uso, alimentada pelo
            # quanto da janela ja passou (100 - sobra). Assim as duas cores sao
            # comparaveis: o que interessa nao e cada uma, e a diferenca entre
            # elas. Ver classificar().
            if not dados["ativo"]:
                cor_t = self.cfg_tempo["cor_final"]
            elif self.cfg_tempo.get("modo_cor", "escala") == "escala":
                cor_t = self.cfg["cores"][classificar(decorrido_pct, self.cfg["limiares"])]
            else:
                cor_t = self.cfg_tempo["cor"]
            # O anel mostra o tempo DECORRIDO, nao a sobra: assim ele enche em
            # sentido horario, igual ao de uso, e os dois viram a mesma
            # pergunta lado a lado - "quanto ja foi". Um anel que esvazia
            # enquanto o vizinho enche obriga a inverter a leitura na cabeca.
            self.icone_tempo.icon = desenhar(
                decorrido_pct, cor_t, dados["ativo"],
                rotulo_tempo(dados["restante_seg"]) if dados["ativo"] else "-",
                self.cfg.get("icone"), decorrido_pct,
            )
            self.icone_tempo.title = tooltip_tempo(dados)

        if self.debug:
            falta = dados["restante_seg"]
            print(f"[{time.strftime('%H:%M:%S')}] {dados['pct']:5.1f}%  {faixa:9}  "
                  f"reset em {falta // 3600}h{falta % 3600 // 60:02d}  "
                  f"fonte={dados['fonte']} idade={int(dados['idade'] or 0)}s", flush=True)

    def _tick(self):
        agora = time.monotonic()
        if agora - self.ultimo_poll >= self._intervalo_api():
            self._poll_oficial()
        if agora - self.ultimo_consumo >= float(self.cfg.get("intervalo_consumo_seg", 120)):
            self._poll_consumo()
        self.atualizar()

    def _laco(self):
        while True:
            try:
                self._tick()
            except Exception as erro:              # nunca derrubar a bandeja
                if self.debug:
                    print(f"[erro] {erro!r}", flush=True)
            time.sleep(max(int(self.cfg.get("intervalo_seg", 15)), 5))

    def rodar(self):
        threading.Thread(target=self._laco, daemon=True).start()
        # Cada Icon cria a propria janela oculta e o proprio message loop, que
        # no win32 e por thread - entao o segundo roda numa thread propria.
        if self.icone_tempo is not None:
            threading.Thread(target=self.icone_tempo.run, daemon=True).start()
        self.icone.run()

    def _sair_tudo(self):
        if self.icone_tempo is not None:
            self.icone_tempo.stop()
        self.icone.stop()


if __name__ == "__main__":            # pragma: no cover - a porta oficial e o cli
    from .cli import main

    raise SystemExit(main())
