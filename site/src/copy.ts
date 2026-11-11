/** The text of the public page, in its two languages. */

export type Language = "en" | "pt-BR";

const REPOSITORY = "https://github.com/HenriqueMayer/TuxedoFinance";

export const LINKS = {
  repository: REPOSITORY,
  docker: `${REPOSITORY}/blob/main/docs/operations.md#docker`,
  license: `${REPOSITORY}/blob/main/LICENSE`,
  product: `${REPOSITORY}/blob/main/docs/product.md`,
};

export const COMMANDS = `git clone ${REPOSITORY}.git
cd TuxedoFinance/web && npm ci && npx vite build
cd ../backend && cp .env.example .env    # set SECRET_KEY in .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver`;

export const COPY = {
  en: {
    lang: "en",
    title: "Tuxedo Finance — personal finance that you run yourself",
    description:
      "A self-hosted personal finance application for one person. You type what happened, and it answers how much is left, where the money went and what is due. Try it on this page.",
    skip: "Skip to the demonstration",
    other: { label: "Português", path: "pt-br/" },
    source: "Source code",
    heading: "How much can I still spend this month?",
    lead: "Tuxedo Finance answers from what you type. It has no bank connection and no account with anyone: it runs on your computer.",
    install: "Run it on your computer",
    fullScreen: "Open the demonstration in full screen",
    windowTitle: "Demonstration",
    frameTitle: "Tuxedo Finance with fictional data",
    caption: "This is the application itself, with fictional data. Click anything: nothing is saved.",
    placesTitle: "Four places, four questions",
    places: [
      {
        name: "Home",
        question: "How is this month?",
        text: "What is left to spend, where the money went, what is due, your net worth and your goals. You choose the blocks and their order.",
      },
      {
        name: "Transactions",
        question: "What did I record?",
        text: "The entries of a month, with search. An entry takes a few seconds. A bank statement in OFX or CSV can be imported and reviewed row by row.",
      },
      {
        name: "Wallet",
        question: "What do I have and what do I owe?",
        text: "Accounts by bank, cards and their invoices, transfers, investments, points and miles, and accounts in other currencies.",
      },
      {
        name: "Plan",
        question: "What do I intend?",
        text: "A limit for the month, budgets by category, goals that reserve real balances, the months ahead, and a short closing of each month.",
      },
    ],
    limitsTitle: "What it does not do",
    limits: [
      "It does not connect to your bank. You type, or you import a statement file.",
      "It is not a service. Nobody hosts it for you, and nobody else holds your records.",
      "It is made for one person, not for a team or a company.",
    ],
    yoursTitle: "Your records stay with you",
    yours:
      "The application and its database are files on a computer that you control. This page stores nothing about you and loads no tracker: the demonstration above runs in your browser from static files.",
    runTitle: "Run it on your computer",
    runLead: "You need Python 3.12 with uv, and Node.js 22.",
    runAfter: "Then open http://127.0.0.1:8000.",
    docker: "Run it with Docker",
    licenseText: "Free for personal, noncommercial use.",
    license: "PolyForm Noncommercial 1.0.0",
    productDoc: "What each screen does",
    notFound: "This page does not exist.",
    home: "Go to the first page",
  },
  "pt-BR": {
    lang: "pt-BR",
    title: "Tuxedo Finance — finanças pessoais que rodam no seu computador",
    description:
      "Um aplicativo de finanças pessoais para uma pessoa, hospedado por você. Você lança o que aconteceu e ele responde quanto resta, para onde foi o dinheiro e o que vence. Experimente nesta página.",
    skip: "Ir para a demonstração",
    other: { label: "English", path: "" },
    source: "Código-fonte",
    heading: "Quanto ainda posso gastar este mês?",
    lead: "O Tuxedo Finance responde a partir do que você lança. Sem conexão com banco e sem conta em serviço nenhum: ele roda no seu computador.",
    install: "Rodar no seu computador",
    fullScreen: "Abrir a demonstração em tela cheia",
    windowTitle: "Demonstração",
    frameTitle: "Tuxedo Finance com dados fictícios",
    caption: "Este é o próprio aplicativo, com dados fictícios. Clique em qualquer coisa: nada é gravado.",
    placesTitle: "Quatro lugares, quatro perguntas",
    places: [
      {
        name: "Início",
        question: "Como está este mês?",
        text: "Quanto resta para gastar, para onde foi o dinheiro, o que vence, seu patrimônio e suas metas. Você escolhe os blocos e a ordem.",
      },
      {
        name: "Transações",
        question: "O que eu registrei?",
        text: "Os lançamentos de um mês, com busca. Um lançamento leva alguns segundos. Um extrato em OFX ou CSV pode ser importado e revisado linha a linha.",
      },
      {
        name: "Carteira",
        question: "O que eu tenho e o que eu devo?",
        text: "Contas por banco, cartões e faturas, transferências, investimentos, pontos e milhas, e contas em outras moedas.",
      },
      {
        name: "Planejar",
        question: "O que eu pretendo?",
        text: "Um limite para o mês, orçamentos por categoria, metas que reservam saldos reais, os próximos meses e um fechamento curto de cada mês.",
      },
    ],
    limitsTitle: "O que ele não faz",
    limits: [
      "Não se conecta ao seu banco. Você lança, ou importa um arquivo de extrato.",
      "Não é um serviço. Ninguém hospeda para você, e ninguém mais guarda seus registros.",
      "É feito para uma pessoa, não para uma equipe ou uma empresa.",
    ],
    yoursTitle: "Seus registros ficam com você",
    yours:
      "O aplicativo e o banco de dados são arquivos em um computador que você controla. Esta página não guarda nada sobre você e não carrega rastreador: a demonstração acima roda no seu navegador, a partir de arquivos estáticos.",
    runTitle: "Rodar no seu computador",
    runLead: "Você precisa de Python 3.12 com uv e de Node.js 22.",
    runAfter: "Depois abra http://127.0.0.1:8000.",
    docker: "Rodar com Docker",
    licenseText: "Gratuito para uso pessoal e não comercial.",
    license: "PolyForm Noncommercial 1.0.0",
    productDoc: "O que cada tela faz",
    notFound: "Esta página não existe.",
    home: "Ir para a primeira página",
  },
} as const;
