"""Parecer em PDF: a decisão (lançar ou devolver) e o motivo em primeiro lugar, os dados da nota depois."""
import datetime as dt

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .regras import AVISA, BLOQUEIA, brl, esperado

CEU, BRASA, TINTA, CINZA, LINHA = (colors.HexColor(c) for c in ("#140c33", "#ff8a5b", "#1f2328", "#59636e", "#d1d9e0"))
VERDE, VERMELHO = colors.HexColor("#1a7f37"), colors.HexColor("#cf222e")
EST = {
    "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=17, textColor=colors.white, leading=21),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#c9c3ff"), leading=12),
    "secao": ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=10, textColor=CINZA, leading=14,
                            spaceBefore=14, spaceAfter=6),
    "texto": ParagraphStyle("texto", fontName="Helvetica", fontSize=10.5, textColor=TINTA, leading=15),
    "motivo": ParagraphStyle("motivo", fontName="Helvetica", fontSize=10.5, textColor=TINTA, leading=15,
                             leftIndent=12, bulletIndent=0, spaceAfter=4),
    "rodape": ParagraphStyle("rodape", fontName="Helvetica", fontSize=8, textColor=CINZA, alignment=TA_LEFT),
}


def _faixa_topo(resultado, agora):
    n = resultado.nota
    titulo = Paragraph("Parecer de conferência · NFS-e", EST["titulo"])
    sub = Paragraph(f"Nota {n.numero} · {n.prestador_nome} · gerado em {agora:%d/%m/%Y %H:%M}", EST["sub"])
    t = Table([[titulo], [sub]], colWidths=[17 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CEU), ("LEFTPADDING", (0, 0), (-1, -1), 16),
                           ("TOPPADDING", (0, 0), (0, 0), 14), ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
                           ("LINEBELOW", (0, -1), (-1, -1), 3, BRASA)]))
    return t


def _decisao(resultado):
    cor = VERMELHO if resultado.decisao == "DEVOLVER" else VERDE
    frase = ("A nota volta para correção antes do lançamento." if resultado.decisao == "DEVOLVER"
             else "Dados, valores e retenções conferem com o lançamento.")
    estilo = ParagraphStyle("dec", fontName="Helvetica-Bold", fontSize=20, textColor=colors.white, leading=24)
    t = Table([[Paragraph(resultado.decisao, estilo), Paragraph(frase, EST["texto"])]],
              colWidths=[5 * cm, 12 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), cor), ("BOX", (0, 0), (-1, -1), 1, cor),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                           ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
    return t


def _tabela(linhas, larguras, cabecalho=True, destaques=()):
    t = Table(linhas, colWidths=larguras)
    estilo = [("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("TEXTCOLOR", (0, 0), (-1, -1), TINTA),
              ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINHA), ("TOPPADDING", (0, 0), (-1, -1), 5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]
    if cabecalho:
        estilo += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("TEXTCOLOR", (0, 0), (-1, 0), CINZA),
                   ("ALIGN", (1, 0), (-1, -1), "RIGHT")]
    else:
        estilo += [("TEXTCOLOR", (0, 0), (0, -1), CINZA)]
    for i in destaques:
        estilo += [("TEXTCOLOR", (0, i), (-1, i), VERMELHO), ("FONT", (0, i), (-1, i), "Helvetica-Bold", 9.5)]
    t.setStyle(TableStyle(estilo))
    return t


def gerar_pdf(resultado, tabela, caminho, agora=None):
    agora = agora or dt.datetime.now()
    n, lanc = resultado.nota, resultado.lancamento
    servico = tabela["servicos"].get(n.codigo_servico, {}).get("descricao", "serviço não cadastrado")
    bloqueios = [a for a in resultado.apontamentos if a.gravidade == BLOQUEIA]
    avisos = [a for a in resultado.apontamentos if a.gravidade == AVISA]

    hist = [_faixa_topo(resultado, agora), Spacer(1, 16), _decisao(resultado)]
    if bloqueios:
        hist.append(Paragraph("MOTIVO DA DEVOLUÇÃO", EST["secao"]))
        hist += [Paragraph(a.mensagem, EST["motivo"], bulletText="•") for a in bloqueios]
    if avisos:
        hist.append(Paragraph("OBSERVAÇÕES", EST["secao"]))
        hist += [Paragraph(a.mensagem, EST["motivo"], bulletText="•") for a in avisos]

    hist.append(Paragraph("NOTA", EST["secao"]))
    hist.append(_tabela([
        ["Prestador", f"{n.prestador_nome} · {n.prestador_cnpj}"],
        ["Número e emissão", f"{n.numero} · {n.emissao:%d/%m/%Y}" + (" · CANCELADA" if n.situacao == "CANCELADA" else "")],
        ["Serviço", f"{n.codigo_servico} · {servico}"],
        ["Local da prestação", n.municipio_servico],
        ["Lançamento", f"documento {lanc.documento} · competência {lanc.competencia[5:]}/{lanc.competencia[:4]} · "
                       f"fornecedor {lanc.fornecedor_cnpj}"],
    ], [4.2 * cm, 12.8 * cm], cabecalho=False))

    devido = esperado(n, tabela)
    informado = {"ISS": n.iss_retido, "INSS": n.inss_retido, "IRRF": n.irrf_retido, "PIS/COFINS/CSLL": n.csrf_retido}
    linhas = [["Valores", "Na nota", "Esperado", "Lançado"],
              ["Serviços", brl(n.valor_servicos), brl(n.valor_servicos), brl(lanc.valor_bruto)]]
    linhas += [[f"(-) {t}", brl(informado[t]), brl(devido[t]), ""] for t in devido]
    linhas.append(["Líquido", brl(n.valor_liquido), brl(n.valor_servicos - sum(devido.values())),
                   brl(lanc.valor_liquido)])
    hist.append(Paragraph("VALORES E RETENÇÕES", EST["secao"]))
    divergentes = [i for i, ln in enumerate(linhas[1:], start=1)
                   if ln[1] != ln[2] or (ln[3] and ln[3] != ln[1])]
    hist.append(_tabela(linhas, [5.5 * cm, 3.8 * cm, 3.8 * cm, 3.9 * cm], destaques=divergentes))
    hist += [Spacer(1, 22), Paragraph("Parecer gerado automaticamente pelo robô de conferência. "
                                      "Dados fictícios, alíquotas ilustrativas.", EST["rodape"])]

    doc = SimpleDocTemplate(str(caminho), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.6 * cm, title=f"Parecer NFS-e {n.numero}", author="Robô de conferência")
    doc.build(hist)
    return caminho
