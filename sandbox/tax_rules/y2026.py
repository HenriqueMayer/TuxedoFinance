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
class TaxRuleSet:
    year: int
    reviewed_on: date
    source_urls: tuple[str, ...]
    employee_inss: tuple[ProgressiveBand, ...]
    irrf: tuple[ProgressiveBand, ...]
    irrf_dependent_deduction: Decimal
    irrf_simplified_deduction: Decimal
    irrf_reduction_zero_limit: Decimal
    irrf_reduction_full_amount: Decimal
    irrf_reduction_upper_limit: Decimal
    irrf_reduction_constant: Decimal
    irrf_reduction_slope: Decimal
    fgts_rate: Decimal


RULES_2026 = TaxRuleSet(
    year=2026,
    reviewed_on=date(2026, 9, 2),
    source_urls=(
        'https://www.gov.br/inss/pt-br/direitos-e-deveres/inscricao-e-contribuicao/tabela-de-contribuicao-mensal',
        'https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/tabelas/2026',
        'https://www.fgts.gov.br/Paginas/sobre-o-fgts/regras.aspx',
    ),
    employee_inss=(
        ProgressiveBand(D('1621.00'), D('0.075')),
        ProgressiveBand(D('2902.84'), D('0.09')),
        ProgressiveBand(D('4354.27'), D('0.12')),
        ProgressiveBand(D('8475.55'), D('0.14')),
    ),
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
)
