from dataclasses import dataclass
from datetime import date
from decimal import Decimal


D = Decimal


@dataclass(frozen=True)
class ProgressiveBand:
    upper: Decimal | None
    rate: Decimal
    deduction: Decimal = D('0')


@dataclass(frozen=True)
class SimpleBand:
    upper: Decimal
    rate: Decimal
    deduction: Decimal


@dataclass(frozen=True)
class TaxRuleSet:
    year: int
    reviewed_on: date
    source_urls: tuple[str, ...]
    minimum_wage: Decimal
    inss_ceiling: Decimal
    employee_inss: tuple[ProgressiveBand, ...]
    individual_inss_rate: Decimal
    irrf: tuple[ProgressiveBand, ...]
    irrf_dependent_deduction: Decimal
    irrf_simplified_deduction: Decimal
    irrf_reduction_zero_limit: Decimal
    irrf_reduction_full_amount: Decimal
    irrf_reduction_upper_limit: Decimal
    irrf_reduction_constant: Decimal
    irrf_reduction_slope: Decimal
    fgts_rate: Decimal
    employer_cpp_rate: Decimal
    default_rat_rate: Decimal
    default_fap: Decimal
    default_third_party_rate: Decimal
    simple_iii: tuple[SimpleBand, ...]
    simple_v: tuple[SimpleBand, ...]
    simple_iss_sublimit: Decimal
    simple_revenue_limit: Decimal
    presumed_service_rate: Decimal
    presumed_csll_rate: Decimal
    presumed_irpj_rate: Decimal
    presumed_irpj_additional_rate: Decimal
    presumed_irpj_monthly_threshold: Decimal
    presumed_pis_rate: Decimal
    presumed_cofins_rate: Decimal
    presumed_revenue_limit: Decimal
    presumed_increase_threshold: Decimal
    presumed_increase_rate: Decimal
    dividend_withholding_threshold: Decimal
    dividend_withholding_rate: Decimal


RULES_2026 = TaxRuleSet(
    year=2026,
    reviewed_on=date(2026, 9, 2),
    source_urls=(
        'https://www.gov.br/inss/pt-br/direitos-e-deveres/inscricao-e-contribuicao/tabela-de-contribuicao-mensal',
        'https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026',
        'https://www8.receita.fazenda.gov.br/SimplesNacional/Arquivos/manual/MANUAL_PGDAS-D_2018_V4.pdf',
        'https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/receita-federal-orienta-sobre-os-procedimentos-para-o-recolhimento-do-imposto-de-renda-retido-na-fonte-sobre-lucros-e-dividendos',
        'https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/beneficios-fiscais/perguntas-e-respostas-reducao-dos-incentivos-e-beneficios-tributarios.pdf/%40%40download/file',
        'https://www.fgts.gov.br/Paginas/sobre-o-fgts/regras.aspx',
    ),
    minimum_wage=D('1621.00'),
    inss_ceiling=D('8475.55'),
    employee_inss=(
        ProgressiveBand(D('1621.00'), D('0.075')),
        ProgressiveBand(D('2902.84'), D('0.09')),
        ProgressiveBand(D('4354.27'), D('0.12')),
        ProgressiveBand(D('8475.55'), D('0.14')),
    ),
    individual_inss_rate=D('0.11'),
    irrf=(
        ProgressiveBand(D('2428.80'), D('0')),
        ProgressiveBand(D('2826.65'), D('0.075'), D('182.16')),
        ProgressiveBand(D('3751.05'), D('0.15'), D('394.16')),
        ProgressiveBand(D('4664.68'), D('0.225'), D('675.49')),
        ProgressiveBand(None, D('0.275'), D('908.73')),
    ),
    irrf_dependent_deduction=D('189.59'),
    irrf_simplified_deduction=D('607.20'),
    irrf_reduction_zero_limit=D('5000.00'),
    irrf_reduction_full_amount=D('312.89'),
    irrf_reduction_upper_limit=D('7350.00'),
    irrf_reduction_constant=D('978.62'),
    irrf_reduction_slope=D('0.133145'),
    fgts_rate=D('0.08'),
    employer_cpp_rate=D('0.20'),
    default_rat_rate=D('0.01'),
    default_fap=D('1.00'),
    default_third_party_rate=D('0.058'),
    simple_iii=(
        SimpleBand(D('180000.00'), D('0.06'), D('0')),
        SimpleBand(D('360000.00'), D('0.112'), D('9360')),
        SimpleBand(D('720000.00'), D('0.135'), D('17640')),
        SimpleBand(D('1800000.00'), D('0.16'), D('35640')),
        SimpleBand(D('3600000.00'), D('0.21'), D('125640')),
        SimpleBand(D('4800000.00'), D('0.33'), D('648000')),
    ),
    simple_v=(
        SimpleBand(D('180000.00'), D('0.155'), D('0')),
        SimpleBand(D('360000.00'), D('0.18'), D('4500')),
        SimpleBand(D('720000.00'), D('0.195'), D('9900')),
        SimpleBand(D('1800000.00'), D('0.205'), D('17100')),
        SimpleBand(D('3600000.00'), D('0.23'), D('62100')),
        SimpleBand(D('4800000.00'), D('0.305'), D('540000')),
    ),
    simple_iss_sublimit=D('3600000.00'),
    simple_revenue_limit=D('4800000.00'),
    presumed_service_rate=D('0.32'),
    presumed_csll_rate=D('0.09'),
    presumed_irpj_rate=D('0.15'),
    presumed_irpj_additional_rate=D('0.10'),
    presumed_irpj_monthly_threshold=D('20000.00'),
    presumed_pis_rate=D('0.0065'),
    presumed_cofins_rate=D('0.03'),
    presumed_revenue_limit=D('78000000.00'),
    presumed_increase_threshold=D('5000000.00'),
    presumed_increase_rate=D('0.10'),
    dividend_withholding_threshold=D('50000.00'),
    dividend_withholding_rate=D('0.10'),
)
