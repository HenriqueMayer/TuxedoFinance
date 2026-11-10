import type { Messages } from "./en";

export const ptBR: Messages = {
  app: { name: "Tuxedo Finance" },
  nav: { home: "Início", signOut: "Sair" },
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
  settings: { language: "Idioma", theme: "Tema", light: "Claro", dark: "Escuro" },
};
