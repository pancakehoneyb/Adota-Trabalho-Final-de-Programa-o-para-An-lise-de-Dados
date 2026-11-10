"""Adota+ - back-end (Flask + SQLite).

Rodar:  python app.py   ->  http://localhost:5000
"""
import hashlib
import os
import sqlite3
import uuid
from datetime import date, datetime
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ADOTA_DB", os.path.join(BASE, "adota.db"))

app = Flask(__name__, static_folder="static", static_url_path="")
UPLOADS = os.environ.get("ADOTA_UPLOADS", os.path.join(BASE, "uploads"))
PASTA_FOTOS = os.path.join(UPLOADS, "animais")          # fotos dos pets (públicas)
PASTA_VERIF = os.path.join(UPLOADS, "verificacoes")     # arquivos de verificação (privados: nunca servidos direto)
os.makedirs(PASTA_FOTOS, exist_ok=True)
os.makedirs(PASTA_VERIF, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024      # limite de 6 MB por envio
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")

# Em desenvolvimento, aprova as verificações na hora para você testar os selos.
# Em produção, deixe desligado e integre um serviço de verificação (veja /api/verificacoes).
DEV_AUTO_APROVAR = os.environ.get("DEV_AUTO_APROVAR") == "1"


# ---------- Banco de dados ----------
def db():
    """Abre uma conexão por requisição."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def fechar_db(_erro):
    conexao = g.pop("db", None)
    if conexao:
        conexao.close()


def init_db():
    with sqlite3.connect(DB_PATH) as c, open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())


# ---------- Utilidades ----------
def tipo_arquivo(dados):
    """Descobre o formato pelo CONTEÚDO do arquivo (o nome enviado pelo usuário não é confiável)."""
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    if dados.startswith(b"%PDF"):
        return "pdf"
    return None


def salvar_upload(campo, pasta, permitidos):
    """Valida e grava o arquivo com nome aleatório. Devolve (nome, None) ou (None, mensagem de erro)."""
    arq = request.files.get(campo)
    if not arq:
        return None, "Escolha um arquivo."
    dados = arq.read()
    ext = tipo_arquivo(dados)
    if ext not in permitidos:
        return None, "Formato não aceito. Use: " + ", ".join(sorted(permitidos)) + "."
    nome = uuid.uuid4().hex + "." + ext
    with open(os.path.join(pasta, nome), "wb") as f:
        f.write(dados)
    return nome, None


@app.errorhandler(413)
def arquivo_grande(_e):
    return jsonify({"erro": "Arquivo muito grande (máximo 6 MB)."}), 413


def erro(msg, codigo=400):
    return jsonify({"erro": msg}), codigo


def login_obrigatorio(rota):
    @wraps(rota)
    def interna(*args, **kwargs):
        if "uid" not in session:
            return erro("Entre na sua conta para continuar.", 401)
        return rota(*args, **kwargs)
    return interna


def idade_em_anos(nascimento):
    n = datetime.strptime(nascimento, "%Y-%m-%d").date()
    hoje = date.today()
    return hoje.year - n.year - ((hoje.month, hoje.day) < (n.month, n.day))


def recalcular_nivel(uid):
    """Regra dos selos: 1 Filhote, 2 Prata (documento + facial), 3 Ouro (+ casa + antecedentes)."""
    aprovadas = {r["tipo"] for r in db().execute(
        "SELECT tipo FROM verificacao WHERE usuario_id=? AND status='aprovada'", (uid,))}
    tipo = db().execute("SELECT tipo FROM usuario WHERE id=?", (uid,)).fetchone()["tipo"]
    exigidas_ouro = {"antecedentes"} if tipo == "doador" else {"casa", "antecedentes"}   # doador não precisa da casa
    nivel = 1
    if {"documento", "facial"} <= aprovadas:
        nivel = 2
        if exigidas_ouro <= aprovadas:
            nivel = 3
    db().execute("UPDATE usuario SET nivel_verificacao=? WHERE id=?", (nivel, uid))
    db().commit()
    return nivel


def usuario_publico(uid):
    u = db().execute(
        "SELECT id, nome, email, cidade, tipo, nivel_verificacao FROM usuario WHERE id=?", (uid,)).fetchone()
    return dict(u) if u else None


# ---------- Conta ----------
@app.post("/api/cadastro")
def cadastro():
    d = request.get_json(force=True)
    obrigatorios = ["nome", "email", "senha", "cpf", "data_nascimento", "cidade", "tipo"]
    if any(not str(d.get(c, "")).strip() for c in obrigatorios):
        return erro("Preencha todos os campos.")
    if d["tipo"] not in ("doador", "adotante"):
        return erro("Escolha se você quer adotar ou doar.")
    try:
        if idade_em_anos(d["data_nascimento"]) < 18:
            return erro("É preciso ser maior de 18 anos.")
    except ValueError:
        return erro("Data de nascimento inválida.")
    cpf = "".join(ch for ch in d["cpf"] if ch.isdigit())
    if len(cpf) != 11:
        return erro("CPF deve ter 11 números.")
    try:
        cur = db().execute(
            """INSERT INTO usuario (nome, email, senha_hash, cpf_hash, data_nascimento, cidade, tipo)
               VALUES (?,?,?,?,?,?,?)""",
            (d["nome"].strip(), d["email"].strip().lower(), generate_password_hash(d["senha"]),
             hashlib.sha256(cpf.encode()).hexdigest(), d["data_nascimento"], d["cidade"].strip(), d["tipo"]))
        if d["tipo"] == "adotante":
            db().execute(
                "INSERT INTO perfil_adotante (usuario_id, tipo_moradia, possui_tela, tem_outros_pets) VALUES (?,?,?,?)",
                (cur.lastrowid, d.get("tipo_moradia", "casa"), int(bool(d.get("possui_tela"))),
                 int(bool(d.get("tem_outros_pets")))))
        db().commit()
    except sqlite3.IntegrityError:
        return erro("Já existe uma conta com esse e-mail ou CPF.")
    session["uid"] = cur.lastrowid
    return jsonify(usuario_publico(cur.lastrowid))


@app.post("/api/login")
def login():
    d = request.get_json(force=True)
    u = db().execute("SELECT * FROM usuario WHERE email=?", (str(d.get("email", "")).strip().lower(),)).fetchone()
    if not u or not check_password_hash(u["senha_hash"], str(d.get("senha", ""))):
        return erro("E-mail ou senha incorretos.", 401)
    session["uid"] = u["id"]
    return jsonify(usuario_publico(u["id"]))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    return jsonify(usuario_publico(session["uid"]) if "uid" in session else None)


# ---------- Animais ----------
@app.get("/api/animais")
def listar_animais():
    sql = """SELECT a.*, (SELECT arquivo FROM foto_animal f WHERE f.animal_id = a.id ORDER BY f.id LIMIT 1) AS foto,
                    u.nome AS doador_nome, u.nivel_verificacao AS doador_nivel
             FROM animal a JOIN usuario u ON u.id = a.doador_id WHERE a.status='disponivel'"""
    params = []
    if request.args.get("especie"):
        sql += " AND a.especie=?"
        params.append(request.args["especie"])
    if request.args.get("cidade"):
        sql += " AND a.cidade LIKE ?"
        params.append("%" + request.args["cidade"] + "%")
    sql += " ORDER BY a.criado_em DESC"
    return jsonify([dict(r) for r in db().execute(sql, params)])


@app.post("/api/animais")
@login_obrigatorio
def cadastrar_animal():
    d = request.get_json(force=True)
    u = usuario_publico(session["uid"])
    if u["tipo"] != "doador":
        return erro("Só contas de doador podem cadastrar pets.", 403)
    try:
        cur = db().execute(
            """INSERT INTO animal (doador_id, nome, especie, sexo, idade_meses, cor, porte,
               castrado, vacinado, cidade, descricao) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (u["id"], d["nome"].strip(), d["especie"], d["sexo"], int(d["idade_meses"]), d.get("cor", ""),
             d.get("porte", ""), int(bool(d.get("castrado"))), int(bool(d.get("vacinado"))),
             d.get("cidade") or u["cidade"], d.get("descricao", "")))
        db().commit()
    except (KeyError, ValueError, sqlite3.IntegrityError):
        return erro("Confira os dados do pet e tente de novo.")
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.post("/api/animais/<int:animal_id>/foto")
@login_obrigatorio
def enviar_foto(animal_id):
    """O doador envia até 5 fotos do próprio pet."""
    if not db().execute("SELECT 1 FROM animal WHERE id=? AND doador_id=?", (animal_id, session["uid"])).fetchone():
        return erro("Animal não encontrado.", 404)
    if db().execute("SELECT COUNT(*) FROM foto_animal WHERE animal_id=?", (animal_id,)).fetchone()[0] >= 5:
        return erro("Cada pet pode ter até 5 fotos.")
    nome, msg = salvar_upload("foto", PASTA_FOTOS, {"jpg", "png", "webp"})
    if msg:
        return erro(msg)
    db().execute("INSERT INTO foto_animal (animal_id, arquivo) VALUES (?,?)", (animal_id, nome))
    db().commit()
    return jsonify({"ok": True, "arquivo": nome})


@app.get("/fotos/<nome>")
def ver_foto(nome):
    return send_from_directory(PASTA_FOTOS, nome)


@app.post("/api/animais/<int:animal_id>/solicitar")
@login_obrigatorio
def solicitar(animal_id):
    u = usuario_publico(session["uid"])
    a = db().execute("SELECT * FROM animal WHERE id=? AND status='disponivel'", (animal_id,)).fetchone()
    if u["tipo"] != "adotante":
        return erro("Só contas de adotante podem pedir adoção.", 403)
    if not a:
        return erro("Esse pet não está mais disponível.", 404)
    try:
        db().execute("INSERT INTO solicitacao_adocao (animal_id, adotante_id, mensagem) VALUES (?,?,?)",
                     (animal_id, u["id"], (request.get_json(silent=True) or {}).get("mensagem", "")))
        db().commit()
    except sqlite3.IntegrityError:
        return erro("Você já pediu para adotar esse pet.")
    return jsonify({"ok": True})


@app.get("/api/pedidos")
@login_obrigatorio
def pedidos_recebidos():
    """Pedidos para os pets do doador, dos adotantes mais verificados para os menos."""
    linhas = db().execute(
        """SELECT s.id, s.status, a.nome AS animal, u.nome AS adotante, u.cidade, u.nivel_verificacao, s.mensagem
           FROM solicitacao_adocao s
           JOIN animal a ON a.id = s.animal_id
           JOIN usuario u ON u.id = s.adotante_id
           WHERE a.doador_id=? ORDER BY u.nivel_verificacao DESC, s.criado_em""", (session["uid"],))
    return jsonify([dict(r) for r in linhas])


# ---------- Verificação ----------
@app.post("/api/verificacoes")
@login_obrigatorio
def verificar():
    """Recebe a etapa e a foto/arquivo. O arquivo vai para uma pasta privada; o banco guarda só o nome e o resultado."""
    tipo = request.form.get("tipo")
    if tipo not in ("documento", "facial", "casa", "antecedentes"):
        return erro("Tipo de verificação inválido.")
    if tipo == "casa" and usuario_publico(session["uid"])["tipo"] == "doador":
        return erro("A verificação da casa é só para adotantes.")
    ja_enviada = db().execute("SELECT 1 FROM verificacao WHERE usuario_id=? AND tipo=? AND status IN ('pendente','aprovada')",
                              (session["uid"], tipo)).fetchone()
    if ja_enviada:
        return erro("Essa etapa já foi enviada.")
    permitidos = {"jpg", "png", "webp", "pdf"} if tipo == "antecedentes" else {"jpg", "png", "webp"}
    nome, msg = salvar_upload("arquivo", PASTA_VERIF, permitidos)
    if msg:
        return erro(msg)
    status = "aprovada" if DEV_AUTO_APROVAR else "pendente"
    # PONTO DE INTEGRAÇÃO: aqui entra a chamada ao serviço de verificação (documento,
    # prova de vida, antecedentes). Ao receber a resposta, grave 'aprovada' ou 'recusada'.
    cur = db().execute("INSERT INTO verificacao (usuario_id, tipo, status) VALUES (?,?,?)", (session["uid"], tipo, status))
    db().execute("INSERT INTO arquivo_verificacao (verificacao_id, arquivo) VALUES (?,?)", (cur.lastrowid, nome))
    db().commit()
    return jsonify({"status": status, "nivel": recalcular_nivel(session["uid"])})


@app.get("/api/verificacoes/<int:vid>/arquivo")
@login_obrigatorio
def ver_arquivo_verificacao(vid):
    """Só o dono da verificação consegue abrir o próprio arquivo."""
    r = db().execute("""SELECT av.arquivo FROM arquivo_verificacao av JOIN verificacao v ON v.id = av.verificacao_id
                        WHERE v.id=? AND v.usuario_id=?""", (vid, session["uid"])).fetchone()
    if not r:
        return erro("Arquivo não encontrado.", 404)
    return send_from_directory(PASTA_VERIF, r["arquivo"])


@app.get("/api/verificacoes")
@login_obrigatorio
def minhas_verificacoes():
    linhas = db().execute("SELECT id, tipo, status FROM verificacao WHERE usuario_id=?", (session["uid"],))
    return jsonify([dict(r) for r in linhas])


# ---------- Comunidade ----------
@app.get("/api/posts")
def listar_posts():
    linhas = db().execute(
        """SELECT p.id, p.texto, p.criado_em, u.nome AS autor, u.tipo, u.nivel_verificacao,
           (SELECT COUNT(*) FROM curtida c WHERE c.post_id = p.id) AS curtidas,
           (SELECT COUNT(*) FROM comentario m WHERE m.post_id = p.id) AS comentarios,
           EXISTS (SELECT 1 FROM curtida c WHERE c.post_id = p.id AND c.usuario_id = ?) AS curtiu
           FROM post p JOIN usuario u ON u.id = p.autor_id ORDER BY p.criado_em DESC LIMIT 50""", (session.get("uid", 0),))
    return jsonify([dict(r) for r in linhas])


@app.post("/api/posts/<int:post_id>/curtir")
@login_obrigatorio
def curtir(post_id):
    """Curtir e descurtir é o mesmo botão: se já curtiu, remove a curtida."""
    if not db().execute("SELECT 1 FROM post WHERE id=?", (post_id,)).fetchone():
        return erro("Publicação não encontrada.", 404)
    ja = db().execute("SELECT 1 FROM curtida WHERE usuario_id=? AND post_id=?", (session["uid"], post_id)).fetchone()
    if ja:
        db().execute("DELETE FROM curtida WHERE usuario_id=? AND post_id=?", (session["uid"], post_id))
    else:
        db().execute("INSERT INTO curtida (usuario_id, post_id) VALUES (?,?)", (session["uid"], post_id))
    db().commit()
    total = db().execute("SELECT COUNT(*) FROM curtida WHERE post_id=?", (post_id,)).fetchone()[0]
    return jsonify({"curtiu": not ja, "curtidas": total})


@app.get("/api/posts/<int:post_id>/comentarios")
def listar_comentarios(post_id):
    linhas = db().execute(
        """SELECT m.id, m.texto, m.criado_em, u.nome AS autor, u.nivel_verificacao FROM comentario m
           JOIN usuario u ON u.id = m.autor_id WHERE m.post_id=? ORDER BY m.criado_em""", (post_id,))
    return jsonify([dict(r) for r in linhas])


@app.post("/api/posts/<int:post_id>/comentarios")
@login_obrigatorio
def comentar(post_id):
    texto = str((request.get_json(force=True) or {}).get("texto", "")).strip()
    if not texto:
        return erro("Escreva algo para comentar.")
    if not db().execute("SELECT 1 FROM post WHERE id=?", (post_id,)).fetchone():
        return erro("Publicação não encontrada.", 404)
    db().execute("INSERT INTO comentario (post_id, autor_id, texto) VALUES (?,?,?)", (post_id, session["uid"], texto[:500]))
    db().commit()
    return jsonify({"ok": True})


@app.post("/api/posts")
@login_obrigatorio
def criar_post():
    texto = str((request.get_json(force=True) or {}).get("texto", "")).strip()
    if not texto:
        return erro("Escreva algo para publicar.")
    db().execute("INSERT INTO post (autor_id, texto) VALUES (?,?)", (session["uid"], texto[:500]))
    db().commit()
    return jsonify({"ok": True})


@app.patch("/api/pedidos/<int:pedido_id>")
@login_obrigatorio
def responder_pedido(pedido_id):
    """O doador aceita ou recusa um pedido. Ao aceitar, o animal vira 'adotado' e os outros pedidos são recusados."""
    novo = (request.get_json(force=True) or {}).get("status")
    if novo not in ("aceita", "recusada"):
        return erro("Escolha aceitar ou recusar.")
    p = db().execute("""SELECT s.id, s.animal_id FROM solicitacao_adocao s JOIN animal a ON a.id = s.animal_id
                        WHERE s.id=? AND a.doador_id=?""", (pedido_id, session["uid"])).fetchone()
    if not p:
        return erro("Pedido não encontrado.", 404)
    db().execute("UPDATE solicitacao_adocao SET status=? WHERE id=?", (novo, pedido_id))
    if novo == "aceita":
        db().execute("UPDATE animal SET status='adotado' WHERE id=?", (p["animal_id"],))
        db().execute("UPDATE solicitacao_adocao SET status='recusada' WHERE animal_id=? AND id<>? AND status='pendente'",
                     (p["animal_id"], pedido_id))
    db().commit()
    return jsonify({"ok": True})


@app.get("/api/meus-pedidos")
@login_obrigatorio
def meus_pedidos():
    linhas = db().execute(
        """SELECT s.id, a.nome AS animal, a.cidade, s.status FROM solicitacao_adocao s
           JOIN animal a ON a.id = s.animal_id WHERE s.adotante_id=? ORDER BY s.criado_em DESC""", (session["uid"],))
    return jsonify([dict(r) for r in linhas])


# ---------- Indicadores (análise de dados) ----------
@app.get("/api/indicadores")
def indicadores():
    """Dados agregados, sem nenhuma informação pessoal."""
    def q(sql):
        return [dict(r) for r in db().execute(sql)]
    totais = db().execute("""SELECT (SELECT COUNT(*) FROM usuario) AS usuarios, (SELECT COUNT(*) FROM animal) AS animais,
        (SELECT COUNT(*) FROM animal WHERE status='adotado') AS adotados,
        (SELECT COUNT(*) FROM solicitacao_adocao) AS pedidos""").fetchone()
    return jsonify({
        "totais": dict(totais),
        "animais_por_especie": q("SELECT especie, COUNT(*) AS total FROM animal WHERE status='disponivel' GROUP BY especie"),
        "pedidos_por_animal": q("""SELECT a.nome, COUNT(s.id) AS pedidos FROM animal a
            LEFT JOIN solicitacao_adocao s ON s.animal_id = a.id GROUP BY a.id ORDER BY pedidos DESC LIMIT 5"""),
        "usuarios_por_selo": q("SELECT nivel_verificacao AS nivel, COUNT(*) AS total FROM usuario GROUP BY nivel_verificacao ORDER BY nivel"),
        "animais_por_cidade": q("SELECT cidade, COUNT(*) AS total FROM animal GROUP BY cidade ORDER BY total DESC LIMIT 5")})


@app.get("/")
def inicio():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)