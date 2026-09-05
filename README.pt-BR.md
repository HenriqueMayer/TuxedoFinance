[English](README.md) | [Português (Brasil)](README.pt-BR.md)

<p align="center">
  <img src="static/brand/tuxedo-mark-256.png" width="144" alt="Logo do Tuxedo Finance">
</p>

<h1 align="center">Tuxedo Finance</h1>

<p align="center">
  Finanças pessoais, simplificadas.<br>
  Uma aplicação de operação local para fluxo de caixa, despesas recorrentes,
  faturas de cartão, investimentos e planejamento mensal.
</p>

<p align="center">
  <a href="https://github.com/HenriqueMayer/TuxedoFinance/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/HenriqueMayer/TuxedoFinance/ci.yml?branch=main&amp;style=for-the-badge&amp;label=CI&amp;labelColor=101E18&amp;color=176B52" alt="Status da integração contínua"></a>
  <img src="https://img.shields.io/badge/version-0.2.0-B88A59?style=for-the-badge&amp;labelColor=101E18" alt="Versão 0.2.0">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-PolyForm%20Noncommercial-7C5C13?style=for-the-badge&amp;labelColor=101E18" alt="Licença PolyForm Noncommercial"></a>
</p>

O Tuxedo Finance organiza as finanças pessoais em registros categorizados.
É desenvolvido com Django para operação local simples, com interface em inglês
e português do Brasil. Cada instalação mantém seus registros financeiros em
um banco SQLite sob controle do responsável pela instalação.

## Prévia da interface

[Explore a prévia da interface](https://henriquemayer.github.io/TuxedoFinance/)
para conhecer Dashboard, Relatórios, Transações, Bancos e Investimentos nos
dois idiomas, incluindo o Dashboard nos temas claro e escuro.

A prévia é uma apresentação estática com dados fictícios. Não possui login,
backend público ou persistência de dados.

## Instalação inicial

Requer Python 3.12 e [uv](https://docs.astral.sh/uv/getting-started/installation/).
Execute estes comandos para uma nova instalação:

```bash
git clone https://github.com/HenriqueMayer/TuxedoFinance.git
cd TuxedoFinance
uv sync --locked
printf 'SECRET_KEY=%s\n' "$(uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')" > .env
uv run python manage.py migrate
uv run python manage.py runserver
```

Abra [a aplicação local](http://127.0.0.1:8000/), crie seu usuário e cadastre
um banco e uma conta antes de registrar a primeira transação.
O Node.js é necessário apenas para as ferramentas de desenvolvimento; a
aplicação utiliza os arquivos de frontend já compilados no repositório.

Os arquivos gerados `.env` e `db.sqlite3` são privados e ignorados pelo Git.
Consulte o [guia de operações](docs/operations.md) para backup e restauração.
Em uma instalação existente, preserve a chave e o banco de dados e reinicie com:

```bash
uv run python manage.py runserver
```

## Funcionalidades

| Área | Recursos |
|---|---|
| Dashboard | Saldo atual, receitas e despesas mensais, investimentos, faturas abertas e saldo projetado para o fim do mês. |
| Transações | Receitas e despesas, categorias, formas de pagamento, recorrências fixas, parcelas, filtros e exportação CSV. |
| Bancos | Bancos, contas por moeda, PIX, cartões de débito e crédito, faturas, transferências entre contas próprias, programas de fidelidade e taxas de câmbio manuais. |
| Relatórios | Gráficos SVG responsivos renderizados no servidor, resumos acessíveis e atualizações progressivas com HTMX. |
| Investimentos | Aportes, resgates e rendimentos manuais, produtos, ativos, quantidades, preços unitários, taxas e registros históricos de conversão. |
| Sandbox salarial | Estimativas de salário líquido CLT ou com ajustes manuais e orçamento mensal, sem armazenar os dados do cenário. |
| Localização | Inglês e português do Brasil, moeda de apresentação independente (BRL, USD, EUR, GBP, JPY, CHF) e preferência de formato de data. |
| Interface | Temas claro e escuro, navegação por teclado, campos condicionais, validação no servidor e formulários funcionais sem JavaScript. |

O **saldo atual** representa o dinheiro efetivo nas contas até hoje.
O **saldo projetado para o fim do mês** representa a previsão de fechamento.
Compras no cartão de crédito pertencem ao mês da fatura; o dinheiro sai da conta
na data de vencimento. A liquidação da fatura não é uma segunda despesa.

## Tutoriais

Estão previstos tutoriais nos dois idiomas:

| Idioma | Tutorial |
|---|---|
| Português (Brasil) | _link_TODO_ |
| English | _link_TODO_ |

## Tecnologia e configuração

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django 6.0 e autenticação nativa do Django |
| Frontend | Templates Django, Tailwind CSS, JavaScript, HTMX e gráficos SVG inline |
| Banco de dados | SQLite em modo WAL |
| Dependências | uv e lockfile Python versionado; lockfile npm para ferramentas de desenvolvimento |

A configuração vem do `.env` ou das variáveis do processo, que têm prioridade.
`SECRET_KEY` é obrigatória. `ALLOW_SIGNUPS=False` desativa novos cadastros e
preserva o login. `TUXEDO_DATA_DIR` define um diretório alternativo para o banco
de dados.

Consulte a [referência de configuração](docs/operations.md#configuration) para
conhecer as variáveis e seus valores padrão, e o
[guia de arquitetura](docs/architecture.md) para as responsabilidades dos
domínios e o fluxo de dados.

## Desenvolvimento

O [guia de contribuição](CONTRIBUTING.md) descreve os pré-requisitos, verificações,
traduções, compilação do frontend e testes de navegador. Após instalar as
dependências de desenvolvimento e o Chromium, execute:

```bash
npm run test:e2e
npm run test:preview
```

O comando de testes da aplicação cria um banco temporário e inicia seu próprio
servidor local. Ao terminar, remove os dados de teste e encerra seus processos.
A suíte da prévia verifica separadamente a apresentação estática versionada.

## Documentação

A documentação técnica é mantida em inglês.

- [Índice da documentação](docs/README.md) — estrutura do repositório e referências dos apps
- [Requisitos do produto](docs/product-requirements.md) — comportamento suportado e critérios de aceitação
- [Modelo de dados](docs/data-model.md) — entidades, relacionamentos e regras financeiras
- [Frontend](docs/frontend.md) e [design system](docs/design-system.html) — convenções da interface e catálogo de componentes
- [Operações](docs/operations.md) — configuração, dependências, backup e restauração
- [Histórico de alterações](CHANGELOG.md) e [processo de release](docs/versioning.md) — mudanças e versionamento
- [Coleções de categorias](docs/category-collections/) — exemplos em inglês e português prontos para importação

## Controle dos dados

Os registros financeiros permanecem no banco da instalação e não fazem parte
do repositório. O responsável pela instalação administra acesso, backups,
retenção e testes de restauração. Antes de atualizar, confira os requisitos de
compatibilidade da versão e siga o procedimento documentado de backup.

## Contribuição

Contribuições, relatos de problemas e sugestões são bem-vindos. Leia
[CONTRIBUTING.md](CONTRIBUTING.md) antes de propor uma alteração. Mudanças neste
README também devem atualizar a [versão em inglês](README.md).

## Licença

Copyright (c) 2026 Henrique Mayer.

Distribuído sob a [PolyForm Noncommercial License 1.0.0](LICENSE).
Consulte a licença para os termos completos de uso e distribuição.
