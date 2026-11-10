# Tuxedo Finance

Aplicação de finanças pessoais auto-hospedada, para uma pessoa que lança os
dados à mão. Sem conexão com banco. Um lançamento leva poucos segundos, e o
Início responde às perguntas do mês: quanto sobra, para onde foi o dinheiro,
o que vence em breve.

[English](README.md)

## Estado

A versão 2.0 está em desenvolvimento nesta branch. É uma aplicação nova sobre
as regras financeiras da 1.x: uma API Django e um cliente React.

| Área | Estado |
|---|---|
| Lançamentos, categorias, parcelas, lançamentos recorrentes | Pronto |
| Carteira: contas, cartões, faturas, pagamentos, transferências | Pronto |
| Início: resultado do mês, gastos por categoria, o que vence, patrimônio | Pronto |
| Investimentos: saldos e unidades, aportes, resgates, valor de hoje | Pronto |
| Planejar: limite do mês, orçamentos por categoria, metas, próximos meses, planilha, simuladores | Pronto |
| Pontos, outras moedas, importação de extrato, site público | Ainda não |

A 2.0 tem um banco de dados novo. Não há atualização a partir da 1.x. A
última versão 1.x é a tag
[`v1.0.0`](https://github.com/HenriqueMayer/TuxedoFinance/tree/v1.0.0).

## Como rodar

Requisitos: Python 3.12 com [uv](https://docs.astral.sh/uv/) e Node.js 22.

```bash
cd web && npm ci && npx vite build
cd ../backend && cp .env.example .env    # defina SECRET_KEY no .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Abra http://127.0.0.1:8000.

Com Docker: veja [Operations](docs/operations.md#docker).

## Documentação

A documentação técnica está em inglês:
[Product](docs/product.md) · [Architecture](docs/architecture.md) ·
[Data model](docs/data-model.md) · [Development](docs/development.md) ·
[Operations](docs/operations.md)

## Licença

[PolyForm Noncommercial 1.0.0](LICENSE).
