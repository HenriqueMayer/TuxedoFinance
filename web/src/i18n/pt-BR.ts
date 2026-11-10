import type { Messages } from "./en";

export const ptBR: Messages = {
  app: { name: "Tuxedo Finance" },
  nav: {
    main: "Principal",
    home: "Início",
    transactions: "Transações",
    wallet: "Carteira",
    plan: "Planejar",
    settings: "Ajustes",
    signOut: "Sair",
  },
  window: { close: "Fechar", expand: "Expandir para tela cheia", restore: "Restaurar tamanho" },
  common: { comingSoon: "Esta área está em construção." },
  login: {
    title: "Entrar",
    username: "Usuário",
    password: "Senha",
    submit: "Entrar",
    noAccount: "Ainda não tem conta?",
    signUp: "Criar conta",
  },
  signup: {
    title: "Crie sua conta",
    email: "E-mail",
    submit: "Criar conta",
    haveAccount: "Já tem uma conta?",
    closed: "O cadastro está fechado nesta instalação.",
  },
  home: { empty: "Nada aqui ainda. As próximas partes adicionam suas finanças." },
  errors: {
    network: "O servidor não respondeu. Verifique a conexão e tente de novo.",
    unexpected: "Algo deu errado. Tente de novo.",
    tooMany: "Muitas tentativas. Aguarde um minuto e tente de novo.",
  },
  settings: {
    title: "Ajustes",
    language: "Idioma",
    theme: "Tema",
    light: "Claro",
    dark: "Escuro",
    currency: "Moeda dos totais",
    currencyHelp: "Usada só nos totais consolidados. Cada registro mantém a própria moeda.",
    dateFormat: "Ordem da data",
    signedInAs: "Conectado como",
    saveFailed: "A alteração não foi salva. Tente de novo.",
  },
};
