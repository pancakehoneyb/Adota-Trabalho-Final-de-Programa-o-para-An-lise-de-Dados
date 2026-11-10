# Adota+

Aplicativo web de adoção responsável de animais. O doador cadastra os pets, o adotante pede adoção, e o **selo de confiança** (Filhote, Patinha de prata, Patinha de ouro) mostra ao doador quem já comprovou mais sobre si.

Projeto da disciplina Programação para Análise de Dados (Ibmec). Back-end em Python (Flask), banco SQLite e front-end em HTML, CSS e JavaScript.

## Como rodar

```bash
pip install -r requirements.txt
python app.py
```

Abra http://localhost:5000. O banco `adota.db` é criado sozinho na primeira execução e começa **vazio**.

Para testar os selos sem serviço de verificação, ligue o modo de desenvolvimento (aprova as etapas na hora; use só em testes):

```bash
DEV_AUTO_APROVAR=1 python app.py          # Windows (PowerShell): $env:DEV_AUTO_APROVAR=1; python app.py
```

## Testes automáticos

```bash
python -m unittest -v
```

Os testes usam um banco temporário e cobrem cadastro, regras de maioridade, selos, pedidos, aceitar/recusar, comunidade e indicadores.

## Dados reais

O banco não vem com dados de exemplo. Para carregar animais reais de ONGs ou abrigos (com autorização), preencha um CSV no formato de `dados/modelo_animais.csv` e rode:

```bash
python importar_animais_csv.py dados/animais.csv --doador email-da-ong@exemplo.com
```

A conta de doador precisa existir antes (crie pelo app). CSVs com dados reais ficam fora do Git (veja `.gitignore`).

## Estrutura

| Arquivo | Função |
|---|---|
| `app.py` | API Flask e regras de negócio (cada rota tem comentário) |
| `schema.sql` | Criação das 10 tabelas do banco |
| `uploads/` | Fotos dos pets e arquivos de verificação (criada sozinha; fora do Git) |
| `static/index.html` | Telas, estilo e lógica do front-end |
| `test_app.py` | Testes automáticos |
| `importar_animais_csv.py` | Carga de animais reais a partir de CSV |

## Funcionalidades

- Cadastro e login (maiores de 18 anos; senha e CPF guardados como hash)
- Doador: cadastra pets com foto (até 5), vê os pedidos ordenados pelo selo, aceita ou recusa
- Adotante: busca pets por espécie e cidade, pede adoção, acompanha seus pedidos
- Verificação em etapas (documento, facial, casa, antecedentes) com envio de foto ou PDF e cálculo do selo
  (no celular a câmera abre direto; os arquivos ficam em pasta privada, só o dono acessa)
- Comunidade com publicações, curtidas e comentários
- Indicadores de adoção (dados agregados, sem informação pessoal)

## Ainda não implementado

Apadrinhamento, favoritos, tela de moderação para revisar os arquivos de verificação, login com Google, confirmação de e-mail e verificação automática de documento e rosto (hoje as etapas ficam pendentes até existir um provedor de verificação).

## Sobre fotos e arquivos enviados

- Fotos dos pets: JPG, PNG ou WebP, até 6 MB, no máximo 5 por pet. Ficam em `uploads/animais`.
- Arquivos de verificação: JPG, PNG ou WebP (PDF só para antecedentes). Ficam em `uploads/verificacoes`, que **não** é servida pelo site; só o dono do arquivo consegue abri-lo.
- O formato é conferido pelo conteúdo do arquivo, e os nomes são aleatórios.
- Esses arquivos são dados pessoais: não envie a pasta `uploads/` para o Git (já está no `.gitignore`) e apague os arquivos de verificação depois da análise.
