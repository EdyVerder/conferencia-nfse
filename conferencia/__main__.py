"""Confere as notas de um arquivo JSON contra os lançamentos e gera um parecer em PDF por nota.

Uso: python -m conferencia [dados/notas_ficticias.json] [--saida saida/pareceres]
"""
import argparse
import datetime as dt
import json
import os
from decimal import Decimal
from pathlib import Path

from .parecer import gerar_pdf
from .regras import Lancamento, Nota, brl, carregar_tabela, conferir

VERDE, VERMELHO, AMARELO, CINZA, NEGRITO, FIM = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m"
DINHEIRO = {"valor_servicos", "iss_retido", "inss_retido", "irrf_retido", "csrf_retido", "valor_liquido",
            "valor_bruto"}


def _converter(d):
    saida = {}
    for k, v in d.items():
        if k in DINHEIRO:
            saida[k] = Decimal(v)
        elif k == "emissao":
            saida[k] = dt.date.fromisoformat(v)
        else:
            saida[k] = v
    return saida


def carregar(caminho):
    pares = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return [(Nota(**_converter(p["nota"])), Lancamento(**_converter(p["lancamento"]))) for p in pares]


def main():
    if os.name == "nt":
        os.system("")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arquivo", nargs="?", default="dados/notas_ficticias.json")
    ap.add_argument("--saida", default="saida/pareceres")
    ap.add_argument("--hoje", type=dt.date.fromisoformat, default=None, help="data de referência (AAAA-MM-DD)")
    args = ap.parse_args()

    tabela = carregar_tabela()
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)
    contagem = {"LANÇAR": 0, "DEVOLVER": 0}
    for nota, lanc in carregar(args.arquivo):
        r = conferir(nota, lanc, tabela, hoje=args.hoje)
        contagem[r.decisao] += 1
        pdf = gerar_pdf(r, tabela, pasta / f"parecer_{nota.numero}.pdf")
        cor = VERDE if r.decisao == "LANÇAR" else VERMELHO
        print(f"{cor}{NEGRITO}{r.decisao:<9}{FIM} nota {nota.numero:<11} {nota.prestador_nome:<34} "
              f"{brl(nota.valor_servicos):>13}")
        for a in r.apontamentos:
            print(f"          {AMARELO if a.gravidade == 'AVISA' else VERMELHO}↳ {a.mensagem}{FIM}")
        print(f"{CINZA}          {pdf.as_posix()}{FIM}")
    print(f"\n{NEGRITO}{contagem['LANÇAR']} para lançar · {contagem['DEVOLVER']} para devolver{FIM}")


if __name__ == "__main__":
    main()
