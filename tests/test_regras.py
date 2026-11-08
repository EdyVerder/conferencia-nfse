import datetime as dt
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from conferencia.__main__ import carregar
from conferencia.parecer import gerar_pdf
from conferencia.regras import BLOQUEIA, Lancamento, Nota, brl, carregar_tabela, cnpj_valido, conferir, esperado

HOJE = dt.date(2026, 11, 7)
TABELA = carregar_tabela()
DADOS = Path(__file__).resolve().parents[1] / "dados" / "notas_ficticias.json"
D = Decimal


def nota_ok():
    return Nota(numero="2026001845", prestador_cnpj="71.456.069/0001-72", emissao=dt.date(2026, 11, 3),
                codigo_servico="17.19", municipio_servico="Aracaju/SE", valor_servicos=D("12000.00"),
                iss_retido=D("600.00"), irrf_retido=D("180.00"), csrf_retido=D("558.00"), valor_liquido=D("10662.00"))


def lanc_ok():
    return Lancamento(documento="2026001845", fornecedor_cnpj="71.456.069/0001-72", competencia="2026-11",
                      valor_bruto=D("12000.00"), valor_liquido=D("10662.00"))


def test_cnpj():
    assert cnpj_valido("71.456.069/0001-72")
    assert not cnpj_valido("71.456.069/0001-73")
    assert not cnpj_valido("11.111.111/1111-11")


def test_brl():
    assert brl(D("1234567.8")) == "R$ 1.234.567,80"


def test_nota_certa_lanca():
    r = conferir(nota_ok(), lanc_ok(), TABELA, hoje=HOJE)
    assert r.decisao == "LANÇAR" and r.apontamentos == []


@pytest.mark.parametrize("mudanca, regra", [
    ({"iss_retido": D("360.00")}, "retencao"),
    ({"prestador_cnpj": "71.456.069/0001-73"}, "cnpj"),
    ({"situacao": "CANCELADA"}, "situacao"),
    ({"emissao": dt.date(2026, 12, 1)}, "emissao"),
    ({"numero": "999"}, "numero"),
])
def test_bloqueios(mudanca, regra):
    r = conferir(replace(nota_ok(), **mudanca), lanc_ok(), TABELA, hoje=HOJE)
    assert r.decisao == "DEVOLVER"
    assert regra in {a.regra for a in r.apontamentos if a.gravidade == BLOQUEIA}


def test_liquido_lancado_errado():
    r = conferir(nota_ok(), replace(lanc_ok(), valor_liquido=D("11000.00")), TABELA, hoje=HOJE)
    assert [a.regra for a in r.apontamentos] == ["liquido"]


def test_competencia_diferente_so_avisa():
    r = conferir(replace(nota_ok(), emissao=dt.date(2026, 10, 30)), lanc_ok(), TABELA, hoje=HOJE)
    assert r.decisao == "LANÇAR" and [a.regra for a in r.apontamentos] == ["competencia"]


def test_dispensa_de_retencao_pequena():
    devido = esperado(replace(nota_ok(), valor_servicos=D("450.00")), TABELA)
    assert devido["IRRF"] == 0            # 1,5% de 450 = 6,75: dispensado
    assert devido["PIS/COFINS/CSLL"] == D("20.93")


def test_dados_ficticios_e_pareceres(tmp_path):
    decisoes = []
    for nota, lanc in carregar(DADOS):
        r = conferir(nota, lanc, TABELA, hoje=HOJE)
        decisoes.append(r.decisao)
        pdf = gerar_pdf(r, TABELA, tmp_path / f"{nota.numero}.pdf")
        assert pdf.read_bytes()[:5] == b"%PDF-"
    assert decisoes.count("LANÇAR") == 3 and decisoes.count("DEVOLVER") == 4
