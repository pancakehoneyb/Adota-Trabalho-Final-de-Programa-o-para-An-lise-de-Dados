-- Adota+ : banco de dados (SQLite)


CREATE TABLE IF NOT EXISTS usuario (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,
  cpf_hash TEXT NOT NULL UNIQUE,            -- guardamos só o hash (LGPD)
  data_nascimento TEXT NOT NULL,            -- AAAA-MM-DD
  cidade TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('doador','adotante')),
  nivel_verificacao INTEGER NOT NULL DEFAULT 1 CHECK (nivel_verificacao BETWEEN 1 AND 3),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS perfil_adotante (
  usuario_id INTEGER PRIMARY KEY REFERENCES usuario(id),
  tipo_moradia TEXT NOT NULL CHECK (tipo_moradia IN ('casa','apartamento','sitio')),
  possui_tela INTEGER NOT NULL DEFAULT 0,
  tem_outros_pets INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS animal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doador_id INTEGER NOT NULL REFERENCES usuario(id),
  nome TEXT NOT NULL,
  especie TEXT NOT NULL CHECK (especie IN ('cao','gato','outro')),
  sexo TEXT NOT NULL CHECK (sexo IN ('macho','femea')),
  idade_meses INTEGER NOT NULL CHECK (idade_meses >= 0),
  cor TEXT,
  porte TEXT,
  castrado INTEGER NOT NULL DEFAULT 0,
  vacinado INTEGER NOT NULL DEFAULT 0,
  cidade TEXT NOT NULL,
  descricao TEXT,
  status TEXT NOT NULL DEFAULT 'disponivel' CHECK (status IN ('disponivel','em_analise','adotado')),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verificacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL REFERENCES usuario(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('documento','facial','casa','antecedentes')),
  status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','aprovada','recusada')),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solicitacao_adocao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animal(id),
  adotante_id INTEGER NOT NULL REFERENCES usuario(id),
  mensagem TEXT,
  status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','aceita','recusada')),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (animal_id, adotante_id)           -- um pedido por pessoa por animal
);

CREATE TABLE IF NOT EXISTS post (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  autor_id INTEGER NOT NULL REFERENCES usuario(id),
  texto TEXT NOT NULL,
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS foto_animal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  animal_id INTEGER NOT NULL REFERENCES animal(id),
  arquivo TEXT NOT NULL,                    -- nome do arquivo na pasta uploads/animais
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS arquivo_verificacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  verificacao_id INTEGER NOT NULL UNIQUE REFERENCES verificacao(id),
  arquivo TEXT NOT NULL,                    -- nome do arquivo na pasta privada uploads/verificacoes
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curtida (
  usuario_id INTEGER NOT NULL REFERENCES usuario(id),
  post_id INTEGER NOT NULL REFERENCES post(id),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id, post_id)         -- uma curtida por pessoa por post
);

CREATE TABLE IF NOT EXISTS comentario (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id INTEGER NOT NULL REFERENCES post(id),
  autor_id INTEGER NOT NULL REFERENCES usuario(id),
  texto TEXT NOT NULL CHECK (length(texto) <= 500),
  criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
