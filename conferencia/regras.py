"""Regras da conferência: cada regra olha a nota e o lançamento e devolve apontamentos.

Um apontamento BLOQUEIA (a nota volta para quem lançou) ou só AVISA (vai para o parecer, mas pode lançar).
As alíquotas ficam em regras.json; os valores do repositório são ilustrativos.
"""
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

BLOQUEIA, AVISA = "BLOQUEIA", "AVISA"
CENTAVO = Decimal("0.01")


def dinheiro(valor):
    return Decimal(str(valor)).quantize(CENTAVO, ROUND_HALF_UP)


def brl(valor):
    texto = f"{dinheiro(valor):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass
class Nota:
    numero: str
    prestador_cnpj: str
    emissao: dt.date
    codigo_servico: str
    municipio_servico: str
    valor_servicos: Decimal
    prestador_nome: str = ""
    situacao: str = "NORMAL"
    iss_retido: Decimal = Decimal(0)
    inss_retido: Decimal = Decimal(0)
    irrf_retido: Decimal = Decimal(0)
    csrf_retido: Decimal = Decimal(0)
    valor_liquido: Decimal = Decimal(0)


@dataclass
class Lancamento:
    documento: str
    fornecedor_cnpj: str
    competencia: str          # AAAA-MM
    valor_bruto: Decimal
    valor_liquido: Decimal


@dataclass
class Apontamento:
    regra: str
    gravidade: str
    mensagem: str


@dataclass
class Resultado:
    nota: Nota
    lancamento: Lancamento
    apontamentos: list = field(default_factory=list)

    @property
    def decisao(self):
        return "DEVOLVER" if any(a.gravidade == BLOQUEIA for a in self.apontamentos) else "LANÇAR"


def cnpj_valido(cnpj):
    digitos = re.sub(r"\D", "", cnpj)
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False

    def dv(base, pesos):
        resto = sum(int(n) * p for n, p in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(digitos[:12], pesos)
    return digitos[12:] == d1 + dv(digitos[:12] + d1, [6] + pesos)


def carregar_tabela(caminho=Path(__file__).with_name("regras.json")):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def esperado(nota, tabela):
    """Retenções que a nota deveria ter, pelo código de serviço e pelo município."""
    servico = tabela["servicos"].get(nota.codigo_servico, {})
    base = nota.valor_servicos
    iss = dinheiro(base * Decimal(str(tabela["iss"].get(nota.municipio_servico, 0))))
    inss = dinheiro(base * Decimal(str(tabela["inss"]))) if servico.get("cessao_mao_de_obra") else Decimal(0)
    irrf = dinheiro(base * Decimal(str(servico.get("irrf", 0))))
    csrf = dinheiro(base * Decimal(str(tabela["csrf"]))) if servico.get("csrf") else Decimal(0)
    dispensa = Decimal(str(tabela["dispensa_ate"]))
    irrf = irrf if irrf > dispensa else Decimal(0)
    csrf = csrf if csrf > dispensa else Decimal(0)
    return {"ISS": iss, "INSS": inss, "IRRF": irrf, "PIS/COFINS/CSLL": csrf}


def conferir(nota, lanc, tabela, hoje=None):
    hoje = hoje or dt.date.today()
    r = Resultado(nota, lanc)
    add = r.apontamentos.append

    if nota.situacao.upper() == "CANCELADA":
        add(Apontamento("situacao", BLOQUEIA, f"A nota {nota.numero} está cancelada na prefeitura."))
    if not cnpj_valido(nota.prestador_cnpj):
        add(Apontamento("cnpj", BLOQUEIA, f"O CNPJ do prestador ({nota.prestador_cnpj}) é inválido."))
    elif re.sub(r"\D", "", nota.prestador_cnpj) != re.sub(r"\D", "", lanc.fornecedor_cnpj):
        add(Apontamento("cnpj", BLOQUEIA, f"O prestador da nota ({nota.prestador_cnpj}) não é o fornecedor "
                                          f"do lançamento ({lanc.fornecedor_cnpj})."))
    if nota.numero.lstrip("0") != lanc.documento.lstrip("0"):
        add(Apontamento("numero", BLOQUEIA, f"O lançamento cita o documento {lanc.documento}, "
                                            f"mas a nota é a {nota.numero}."))
    if nota.emissao > hoje:
        add(Apontamento("emissao", BLOQUEIA, f"A data de emissão ({nota.emissao:%d/%m/%Y}) está no futuro."))
    elif nota.emissao.strftime("%Y-%m") != lanc.competencia:
        add(Apontamento("competencia", AVISA, f"Nota emitida em {nota.emissao:%m/%Y}, lançada na competência "
                                              f"{lanc.competencia[5:]}/{lanc.competencia[:4]}."))
    if dinheiro(nota.valor_servicos) != dinheiro(lanc.valor_bruto):
        add(Apontamento("valor", BLOQUEIA, f"Valor da nota {brl(nota.valor_servicos)} diferente do lançado "
                                           f"{brl(lanc.valor_bruto)}."))

    devido = esperado(nota, tabela)
    informado = {"ISS": nota.iss_retido, "INSS": nota.inss_retido, "IRRF": nota.irrf_retido,
                 "PIS/COFINS/CSLL": nota.csrf_retido}
    for tributo, valor in devido.items():
        if abs(dinheiro(informado[tributo]) - valor) > CENTAVO:
            add(Apontamento("retencao", BLOQUEIA, f"{tributo} retido {brl(informado[tributo])}; o esperado para "
                                                  f"o serviço {nota.codigo_servico} é {brl(valor)}."))
    liquido = dinheiro(nota.valor_servicos) - sum(dinheiro(v) for v in informado.values())
    if dinheiro(lanc.valor_liquido) != liquido:
        add(Apontamento("liquido", BLOQUEIA, f"O líquido lançado ({brl(lanc.valor_liquido)}) não fecha com a "
                                             f"nota menos as retenções ({brl(liquido)})."))
    return r
