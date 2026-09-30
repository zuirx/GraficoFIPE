from flask import Flask, render_template, request, jsonify
import sqlite3
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fetcher', 'fipe.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/docs')
@app.route('/api/docs')
def docs():
    return render_template('docs.html')

@app.route('/api/tipos')
def get_tipos():
    conn = get_db_connection()
    tipos = conn.execute('SELECT id, nome FROM tipos_veiculo').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tipos])

@app.route('/api/marcas/<int:tipo_id>')
def get_marcas(tipo_id):
    conn = get_db_connection()
    marcas = conn.execute('SELECT id, nome FROM marcas WHERE tipo_veiculo_id = ? ORDER BY nome', (tipo_id,)).fetchall()
    conn.close()
    return jsonify([dict(m) for m in marcas])

@app.route('/api/modelos/<int:marca_id>')
def get_modelos(marca_id):
    # Obtém o mês mais recente para basear o preço
    conn = get_db_connection()
    mes_row = conn.execute('SELECT id, codigo FROM tabelas_fipe ORDER BY codigo DESC LIMIT 1').fetchone()
    
    if mes_row:
        tabela_id = mes_row['id']
        query = '''
            SELECT mod.id, mod.nome, AVG(v.valor) as preco_atual
            FROM modelos mod
            LEFT JOIN versoes ver ON mod.id = ver.modelo_id
            LEFT JOIN valores_fipe v ON ver.id = v.versao_id AND v.tabela_id = ?
            WHERE mod.marca_id = ?
            GROUP BY mod.id, mod.nome
            ORDER BY mod.nome
        '''
        modelos = conn.execute(query, (tabela_id, marca_id)).fetchall()
    else:
        modelos = conn.execute('SELECT id, nome FROM modelos WHERE marca_id = ? ORDER BY nome', (marca_id,)).fetchall()
        
    conn.close()
    
    result = []
    for m in modelos:
        preco = m['preco_atual'] if 'preco_atual' in m.keys() else None
        result.append({
            'id': m['id'],
            'nome': m['nome'],
            'preco_atual': round(preco, 2) if preco else None
        })
        
    return jsonify(result)

@app.route('/api/meses')
def get_meses():
    conn = get_db_connection()
    meses = conn.execute('SELECT codigo, mes FROM tabelas_fipe ORDER BY codigo ASC').fetchall()
    conn.close()
    return jsonify([dict(m) for m in meses])

@app.route('/api/dados', methods=['POST'])
def get_dados():
    data = request.json
    modelo_ids = data.get('modelos', [])
    mes_inicio = data.get('mes_inicio')
    mes_fim = data.get('mes_fim')

    if not modelo_ids:
        return jsonify([])

    conn = get_db_connection()
    
    placeholders = ','.join('?' * len(modelo_ids))
    query = f'''
        SELECT 
            mod.id AS modelo_id,
            mod.nome AS modelo_nome,
            t.codigo AS mes_codigo,
            t.mes AS mes_nome,
            AVG(v.valor) AS preco_medio
        FROM valores_fipe v
        JOIN versoes ver ON v.versao_id = ver.id
        JOIN modelos mod ON ver.modelo_id = mod.id
        JOIN tabelas_fipe t ON v.tabela_id = t.id
        WHERE mod.id IN ({placeholders})
    '''
    
    params = list(modelo_ids)
    
    if mes_inicio:
        query += ' AND t.codigo >= ?'
        params.append(mes_inicio)
    if mes_fim:
        query += ' AND t.codigo <= ?'
        params.append(mes_fim)
        
    query += ' GROUP BY mod.id, mod.nome, t.codigo, t.mes ORDER BY t.codigo ASC'
    
    resultados = conn.execute(query, params).fetchall()
    conn.close()
    
    meses_dict = {}
    modelos_data = {}
    modelo_nomes = {}
    
    for row in resultados:
        m_id = row['modelo_id']
        m_nome = row['modelo_nome']
        mes_cod = row['mes_codigo']
        mes_nome = row['mes_nome'].strip()
        preco = row['preco_medio']
        
        meses_dict[mes_cod] = mes_nome
        
        if m_id not in modelos_data:
            modelos_data[m_id] = {}
            modelo_nomes[m_id] = m_nome
            
        modelos_data[m_id][mes_cod] = preco
        
    sorted_mes_codigos = sorted(meses_dict.keys())
    labels = [meses_dict[cod] for cod in sorted_mes_codigos]
    
    series = []
    for m_id, data_dict in modelos_data.items():
        data_points = [data_dict.get(cod, None) for cod in sorted_mes_codigos]
        series.append({
            "label": modelo_nomes[m_id],
            "data": data_points
        })
        
    return jsonify({
        "labels": labels,
        "datasets": series
    })

@app.route('/api/veiculos', methods=['POST'])
def get_veiculos():
    data = request.json
    marca_id = data.get('marca_id')
    modelo_ids = data.get('modelos', [])
    mes_codigo = data.get('mes_codigo') # Usa o mês final selecionado
    preco_min = data.get('preco_min')
    preco_max = data.get('preco_max')
    
    if not marca_id and not modelo_ids:
        return jsonify([])
        
    conn = get_db_connection()
    
    query = '''
        SELECT 
            m.nome AS marca,
            mod.nome AS modelo,
            ver.descricao AS versao,
            v.valor AS preco
        FROM valores_fipe v
        JOIN versoes ver ON v.versao_id = ver.id
        JOIN modelos mod ON ver.modelo_id = mod.id
        JOIN marcas m ON mod.marca_id = m.id
        JOIN tabelas_fipe t ON v.tabela_id = t.id
        WHERE t.codigo = ?
    '''
    params = [mes_codigo]
    
    if modelo_ids and len(modelo_ids) > 0:
        placeholders = ','.join('?' * len(modelo_ids))
        query += f' AND mod.id IN ({placeholders})'
        params.extend(modelo_ids)
    elif marca_id:
        query += ' AND m.id = ?'
        params.append(marca_id)
        
    if preco_min:
        query += ' AND v.valor >= ?'
        params.append(preco_min)
        
    if preco_max:
        query += ' AND v.valor <= ?'
        params.append(preco_max)
        
    query += ' ORDER BY v.valor DESC'
    
    resultados = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in resultados])

@app.route('/api/consulta', methods=['GET'])
def consulta_dados():
    fipe = request.args.get('fipe')
    marca = request.args.get('marca')
    modelo = request.args.get('modelo')
    ano_modelo = request.args.get('ano_modelo')
    mes = request.args.get('mes')
    limit = request.args.get('limit', 100)
    
    query = "SELECT * FROM valores_fipe WHERE 1=1"
    params = []
    
    if fipe:
        query += " AND codigo_fipe = ?"
        params.append(fipe)
    if marca:
        query += " AND marca LIKE ?"
        params.append(f"%{marca}%")
    if modelo:
        query += " AND modelo LIKE ?"
        params.append(f"%{modelo}%")
    if ano_modelo:
        query += " AND ano_modelo = ?"
        params.append(ano_modelo)
    if mes:
        query += " AND mes LIKE ?"
        params.append(f"%{mes}%")
        
    try:
        limit = int(limit)
        if limit > 1000: limit = 1000
    except:
        limit = 100
        
    query += " LIMIT ?"
    params.append(limit)
    
    conn = get_db_connection()
    resultados = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in resultados])

# --- Sistema de Sugestões ---
import time
import datetime

SUGESTOES_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sugestoes.db')
SUGESTOES_RATE_LIMIT = {} # ip -> list of timestamps
LIMIT_REQUESTS = 3
LIMIT_WINDOW = 3600 # 1 hour

def init_sugestoes_db():
    conn = sqlite3.connect(SUGESTOES_DB)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sugestoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            ip TEXT, 
            nome TEXT, 
            mensagem TEXT, 
            data TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_sugestoes_db()

@app.route('/api/sugestao', methods=['POST'])
def save_sugestao():
    ip = request.remote_addr
    now = time.time()
    
    if ip in SUGESTOES_RATE_LIMIT:
        SUGESTOES_RATE_LIMIT[ip] = [t for t in SUGESTOES_RATE_LIMIT[ip] if now - t < LIMIT_WINDOW]
        if len(SUGESTOES_RATE_LIMIT[ip]) >= LIMIT_REQUESTS:
            return jsonify({'error': 'Limite atingido. Tente novamente mais tarde.'}), 429
            
    if ip not in SUGESTOES_RATE_LIMIT:
        SUGESTOES_RATE_LIMIT[ip] = []
        
    data = request.json
    nome = data.get('nome', 'Anônimo').strip()
    mensagem = data.get('mensagem', '').strip()
    
    if not mensagem:
        return jsonify({'error': 'A mensagem não pode estar vazia.'}), 400
        
    SUGESTOES_RATE_LIMIT[ip].append(now)
        
    conn = sqlite3.connect(SUGESTOES_DB)
    conn.execute('INSERT INTO sugestoes (ip, nome, mensagem, data) VALUES (?, ?, ?, ?)', 
                 (ip, nome, mensagem, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=7177)
