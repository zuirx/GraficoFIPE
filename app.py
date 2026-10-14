from flask import Flask, render_template, request, jsonify
import duckdb, sqlite3, os
import webmotors
import olx
import ficha_tecnica_icarros

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')

def get_db_connection():
    return duckdb.connect(DB_PATH)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/docs')
@app.route('/api/docs')
def docs():
    return render_template('docs.html')

@app.route('/ranking')
def ranking():
    return render_template('ranking.html')

@app.route('/api/ranking', methods=['GET'])
def get_ranking():
    order = request.args.get('order', 'desvalorizacao')
    limit = int(request.args.get('limit', 100))
    if limit > 500: limit = 500
    
    conn = get_db_connection()
    if order == 'maior_preco':
        query = "SELECT * FROM ranking ORDER BY preco_atual DESC NULLS LAST LIMIT ?"
    elif order == 'menor_preco':
        query = "SELECT * FROM ranking ORDER BY preco_atual ASC NULLS LAST LIMIT ?"
    elif order == 'valorizacao':
        query = "SELECT * FROM ranking ORDER BY variacao_percentual DESC NULLS LAST LIMIT ?"
    else: # desvalorizacao
        query = "SELECT * FROM ranking ORDER BY variacao_percentual ASC NULLS LAST LIMIT ?"
        
    resultados = conn.execute(query, [limit]).fetchall()
    col_names = [desc[0] for desc in conn.description]
    conn.close()
    
    dados = [dict(zip(col_names, r)) for r in resultados]
    return jsonify(dados)

@app.route('/api/tipos')
def get_tipos():
    conn = get_db_connection()
    # Usa tipo_veiculo como id e nome
    tipos = conn.execute('SELECT DISTINCT tipo_veiculo AS id, tipo_veiculo AS nome FROM fipe ORDER BY tipo_veiculo').fetchall()
    conn.close()
    return jsonify([{'id': t[0], 'nome': t[1]} for t in tipos])

@app.route('/api/marcas/<path:tipo_id>')
def get_marcas(tipo_id):
    conn = get_db_connection()
    marcas = conn.execute('SELECT DISTINCT nome_marca AS id, nome_marca AS nome FROM fipe WHERE tipo_veiculo = ? ORDER BY nome_marca', (tipo_id,)).fetchall()
    conn.close()
    return jsonify([{'id': m[0], 'nome': m[1]} for m in marcas])

@app.route('/api/modelos/<path:marca_id>')
def get_modelos(marca_id):
    conn = get_db_connection()
    
    # 1. Obtém os modelos gerais (Média de todos os anos) - Mantém compatibilidade
    query_geral = '''
        SELECT DISTINCT nome_modelo
        FROM fipe
        WHERE nome_marca = ?
        ORDER BY nome_modelo
    '''
    modelos_gerais = conn.execute(query_geral, (marca_id,)).fetchall()
    
    # 2. Obtém os modelos específicos por ano
    # Pegamos apenas os anos que apareceram no último mês de referência para ser mais limpo? 
    # Ou todos os anos históricos? Vamos pegar a última cotação de cada (codigo_fipe, ano_modelo)
    query_anos = '''
        SELECT codigo_fipe, nome_modelo, ano_modelo, arg_max(valor_centavos, ano_referencia * 100 + mes_referencia)/100.0 as preco_atual
        FROM fipe
        WHERE nome_marca = ?
        GROUP BY codigo_fipe, nome_modelo, ano_modelo
        ORDER BY nome_modelo, ano_modelo DESC
    '''
    modelos_anos = conn.execute(query_anos, (marca_id,)).fetchall()
    conn.close()
    
    result = []
    # Adiciona os gerais (com um aviso visual no frontend se quiser, mas aqui só mandamos o text)
    for m in modelos_gerais:
        nome = m[0]
        result.append({
            'id': nome,
            'nome': f"{nome} (Média de Todos os Anos)"
        })
        
    # Adiciona os específicos por ano
    for m in modelos_anos:
        cod_fipe = m[0]
        nome = m[1]
        ano = m[2]
        preco = m[3]
        ano_str = "Zero KM" if ano == 32000 else str(ano)
        result.append({
            'id': f"{cod_fipe}|{ano}",
            'nome': f"{nome} ({ano_str})",
            'preco_atual': round(preco, 2) if preco else None
        })
        
    return jsonify(result)

@app.route('/api/meses')
def get_meses():
    conn = get_db_connection()
    meses = conn.execute('''
        SELECT DISTINCT 
            (ano_referencia * 100 + mes_referencia) AS codigo,
            CAST(mes_referencia AS VARCHAR) || '/' || CAST(ano_referencia AS VARCHAR) AS mes
        FROM fipe 
        ORDER BY codigo ASC
    ''').fetchall()
    conn.close()
    return jsonify([{'codigo': m[0], 'mes': m[1]} for m in meses])

@app.route('/api/dados', methods=['POST'])
def get_dados():
    data = request.json
    modelo_ids = data.get('modelos', [])
    mes_inicio = data.get('mes_inicio')
    mes_fim = data.get('mes_fim')

    if not modelo_ids:
        return jsonify([])

    conn = get_db_connection()
    
    modelos_gerais = []
    modelos_especificos = []
    for m in modelo_ids:
        if '|' in m:
            parts = m.split('|')
            modelos_especificos.append((parts[0], int(parts[1]), m))
        else:
            modelos_gerais.append(m)

    where_mes = ""
    params_mes = []
    if mes_inicio:
        where_mes += " AND (ano_referencia * 100 + mes_referencia) >= ?"
        params_mes.append(int(mes_inicio))
    if mes_fim:
        where_mes += " AND (ano_referencia * 100 + mes_referencia) <= ?"
        params_mes.append(int(mes_fim))

    queries = []
    params = []

    if modelos_gerais:
        placeholders = ','.join(['?'] * len(modelos_gerais))
        q = f'''
            SELECT 
                nome_modelo AS modelo_id,
                nome_modelo || ' (Média de Todos os Anos)' AS modelo_nome,
                (ano_referencia * 100 + mes_referencia) AS mes_codigo,
                CAST(mes_referencia AS VARCHAR) || '/' || CAST(ano_referencia AS VARCHAR) AS mes_nome,
                AVG(valor_centavos)/100.0 AS preco_medio
            FROM fipe
            WHERE nome_modelo IN ({placeholders})
            {where_mes}
            GROUP BY nome_modelo, ano_referencia, mes_referencia
        '''
        queries.append(q)
        params.extend(modelos_gerais)
        params.extend(params_mes)

    for cod_fipe, ano, m_id in modelos_especificos:
        q = f'''
            SELECT 
                ? AS modelo_id,
                MAX(nome_modelo) || ' (' || CASE WHEN MAX(ano_modelo) = 32000 THEN 'Zero KM' ELSE CAST(MAX(ano_modelo) AS VARCHAR) END || ')' AS modelo_nome,
                (ano_referencia * 100 + mes_referencia) AS mes_codigo,
                CAST(mes_referencia AS VARCHAR) || '/' || CAST(ano_referencia AS VARCHAR) AS mes_nome,
                AVG(valor_centavos)/100.0 AS preco_medio
            FROM fipe
            WHERE codigo_fipe = ? AND ano_modelo = ?
            {where_mes}
            GROUP BY codigo_fipe, ano_modelo, ano_referencia, mes_referencia
        '''
        queries.append(q)
        params.extend([m_id, cod_fipe, ano])
        params.extend(params_mes)

    final_query = " UNION ALL ".join(queries) + " ORDER BY mes_codigo ASC"
    
    resultados = conn.execute(final_query, params).fetchall()
    conn.close()
    
    meses_dict = {}
    modelos_data = {}
    modelo_nomes = {}
    
    for row in resultados:
        m_id = row[0]
        m_nome = row[1]
        mes_cod = row[2]
        mes_nome = str(row[3]).strip()
        preco = row[4]
        
        meses_dict[mes_cod] = mes_nome
        
        if m_id not in modelos_data:
            modelos_data[m_id] = {}
            modelo_nomes[m_id] = m_nome
            
        modelos_data[m_id][mes_cod] = preco
        
    sorted_mes_codigos = sorted(meses_dict.keys())
    labels = [meses_dict[cod] for cod in sorted_mes_codigos]
    
    # Busca dados macroeconômicos para o período
    macro_dados = []
    if sorted_mes_codigos:
        conn = get_db_connection()
        min_mes = sorted_mes_codigos[0]
        max_mes = sorted_mes_codigos[-1]
        try:
            macro_res = conn.execute("SELECT mes_codigo, ipca, selic, dolar FROM macro WHERE mes_codigo >= ? AND mes_codigo <= ? ORDER BY mes_codigo", (min_mes, max_mes)).fetchall()
            macro_dict = {r[0]: {'ipca': r[1], 'selic': r[2], 'dolar': r[3]} for r in macro_res}
            for cod in sorted_mes_codigos:
                macro_dados.append(macro_dict.get(cod, {'ipca': 0, 'selic': 0, 'dolar': 0}))
        except Exception:
            for cod in sorted_mes_codigos:
                macro_dados.append({'ipca': 0, 'selic': 0, 'dolar': 0})
        finally:
            conn.close()

    series = []
    for m_id, data_dict in modelos_data.items():
        data_points = [data_dict.get(cod, None) for cod in sorted_mes_codigos]
        series.append({
            "label": modelo_nomes[m_id],
            "data": data_points
        })
        
    return jsonify({
        "labels": labels,
        "datasets": series,
        "macro": macro_dados
    })

@app.route('/api/veiculos', methods=['POST'])
def get_veiculos():
    data = request.json
    marca_id = data.get('marca_id')
    modelo_ids = data.get('modelos', [])
    mes_codigo = data.get('mes_codigo')
    preco_min = data.get('preco_min')
    preco_max = data.get('preco_max')
    
    if not marca_id and not modelo_ids:
        return jsonify([])
        
    conn = get_db_connection()
    
    query = '''
        SELECT 
            nome_marca AS marca,
            nome_modelo AS modelo,
            CAST(ano_modelo AS VARCHAR) || ' - ' || nome_combustivel AS versao,
            valor_centavos/100.0 AS preco
        FROM fipe
        WHERE (ano_referencia * 100 + mes_referencia) = ?
    '''
    params = [int(mes_codigo)]
    
    if modelo_ids and len(modelo_ids) > 0:
        modelos_gerais = []
        condicoes_especificas = []
        
        for m in modelo_ids:
            if '|' in m:
                parts = m.split('|')
                condicoes_especificas.append(f"(codigo_fipe = '{parts[0]}' AND ano_modelo = {parts[1]})")
            else:
                modelos_gerais.append(m)
                
        or_conditions = []
        if modelos_gerais:
            placeholders = ','.join(['?'] * len(modelos_gerais))
            or_conditions.append(f"nome_modelo IN ({placeholders})")
            params.extend(modelos_gerais)
            
        if condicoes_especificas:
            or_conditions.append(" OR ".join(condicoes_especificas))
            
        if or_conditions:
            query += f" AND ({' OR '.join(or_conditions)})"
            
    elif marca_id:
        query += ' AND nome_marca = ?'
        params.append(marca_id)
        
    if preco_min:
        query += ' AND valor_centavos/100.0 >= ?'
        params.append(float(preco_min))
        
    if preco_max:
        query += ' AND valor_centavos/100.0 <= ?'
        params.append(float(preco_max))
        
    query += ' ORDER BY preco DESC'
    
    resultados = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify([{
        'marca': r[0],
        'modelo': r[1],
        'versao': r[2],
        'preco': r[3]
    } for r in resultados])

@app.route('/api/consulta', methods=['GET'])
def consulta_dados():
    fipe = request.args.get('fipe')
    marca = request.args.get('marca')
    modelo = request.args.get('modelo')
    ano_modelo = request.args.get('ano_modelo')
    mes = request.args.get('mes')
    ano = request.args.get('ano')
    limit = request.args.get('limit', 100)
    
    query = "SELECT * FROM fipe WHERE 1=1"
    params = []
    
    if fipe:
        query += " AND codigo_fipe = ?"
        params.append(fipe)
    if marca:
        query += " AND nome_marca ILIKE ?"
        params.append(f"%{marca}%")
    if modelo:
        query += " AND nome_modelo ILIKE ?"
        params.append(f"%{modelo}%")
    if ano_modelo:
        query += " AND ano_modelo = ?"
        params.append(int(ano_modelo))
    if mes:
        query += " AND mes_referencia = ?"
        params.append(int(mes))
    if ano:
        query += " AND ano_referencia = ?"
        params.append(int(ano))
        
    try:
        limit = int(limit)
        if limit > 1000: limit = 1000
    except:
        limit = 100
        
    query += " LIMIT ?"
    params.append(limit)
    
    conn = get_db_connection()
    resultados = conn.execute(query, params).fetchall()
    
    # Obter os nomes das colunas
    col_names = [desc[0] for desc in conn.description]
    conn.close()
    
    dados = [dict(zip(col_names, r)) for r in resultados]
    return jsonify(dados)

# --- Sistema de Sugestões ---
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

import time
import datetime

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

# --- Integração Webmotors ---
WEBMOTORS_RATE_LIMIT = {}  # ip -> list of timestamps
WEBMOTORS_MAX_REQUESTS = 10
WEBMOTORS_WINDOW = 86400  # 24 horas

def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

@app.route('/api/webmotors/status', methods=['GET'])
def webmotors_status():
    ip = get_client_ip()
    now = time.time()
    if ip in WEBMOTORS_RATE_LIMIT:
        WEBMOTORS_RATE_LIMIT[ip] = [t for t in WEBMOTORS_RATE_LIMIT[ip] if now - t < WEBMOTORS_WINDOW]
    else:
        WEBMOTORS_RATE_LIMIT[ip] = []
    restantes = max(0, WEBMOTORS_MAX_REQUESTS - len(WEBMOTORS_RATE_LIMIT[ip]))
    return jsonify({
        'tentativas_restantes': restantes,
        'max_tentativas': WEBMOTORS_MAX_REQUESTS
    })

@app.route('/api/webmotors', methods=['POST'])
def get_webmotors_listings():
    ip = get_client_ip()
    now = time.time()

    if ip in WEBMOTORS_RATE_LIMIT:
        WEBMOTORS_RATE_LIMIT[ip] = [t for t in WEBMOTORS_RATE_LIMIT[ip] if now - t < WEBMOTORS_WINDOW]
        if len(WEBMOTORS_RATE_LIMIT[ip]) >= WEBMOTORS_MAX_REQUESTS:
            return jsonify({
                'error': 'Limite de consultas ao Webmotors atingido. Tente novamente mais tarde.',
                'tentativas_restantes': 0
            }), 429

    if ip not in WEBMOTORS_RATE_LIMIT:
        WEBMOTORS_RATE_LIMIT[ip] = []

    data = request.json or {}
    modelo = data.get('modelo', '').strip()
    marca = data.get('marca', '').strip()
    ano = data.get('ano')

    if not modelo:
        return jsonify({'error': 'Modelo não informado.'}), 400

    # Se o ID foi passado no formato cod_fipe|ano, busca nome no duckdb
    if '|' in modelo:
        parts = modelo.split('|')
        cod_fipe = parts[0]
        ano_val = int(parts[1]) if parts[1].isdigit() else None
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT nome_marca, nome_modelo FROM fipe WHERE codigo_fipe = ? AND ano_modelo = ? LIMIT 1", [cod_fipe, ano_val]).fetchone()
            if row:
                marca = row[0]
                modelo = f"{row[1]} ({ano_val})"
                ano = ano_val
            conn.close()
        except Exception:
            pass

    # Registra o uso da cota de consulta
    WEBMOTORS_RATE_LIMIT[ip].append(now)
    restantes = max(0, WEBMOTORS_MAX_REQUESTS - len(WEBMOTORS_RATE_LIMIT[ip]))

    try:
        anuncios = webmotors.search_webmotors(query=modelo, brand=marca, year=ano, max_results=5)
        return jsonify({
            'success': True,
            'modelo_buscado': modelo,
            'tentativas_restantes': restantes,
            'max_tentativas': WEBMOTORS_MAX_REQUESTS,
            'anuncios': anuncios
        })
    except Exception as e:
        if now in WEBMOTORS_RATE_LIMIT[ip]:
            WEBMOTORS_RATE_LIMIT[ip].remove(now)
        restantes_corrigido = max(0, WEBMOTORS_MAX_REQUESTS - len(WEBMOTORS_RATE_LIMIT[ip]))
        return jsonify({
            'error': f"Erro ao consultar Webmotors: {str(e)}",
            'tentativas_restantes': restantes_corrigido
        }), 500

# --- Integração OLX ---
OLX_RATE_LIMIT = {}  # ip -> list of timestamps
OLX_MAX_REQUESTS = 5
OLX_WINDOW = 3600  # 1 hora

@app.route('/api/olx/status', methods=['GET'])
def olx_status():
    ip = get_client_ip()
    now = time.time()
    if ip in OLX_RATE_LIMIT:
        OLX_RATE_LIMIT[ip] = [t for t in OLX_RATE_LIMIT[ip] if now - t < OLX_WINDOW]
    else:
        OLX_RATE_LIMIT[ip] = []
    restantes = max(0, OLX_MAX_REQUESTS - len(OLX_RATE_LIMIT[ip]))

    ddds_lista = [
        {'ddd': k, 'uf': v['uf'].upper(), 'regiao': v['nome_regiao']}
        for k, v in sorted(olx.DDD_MAP.items())
    ]
    estados_lista = sorted(list({v['uf'].upper() for v in olx.DDD_MAP.values()}))

    return jsonify({
        'tentativas_restantes': restantes,
        'max_tentativas': OLX_MAX_REQUESTS,
        'ddds': ddds_lista,
        'estados': estados_lista
    })

@app.route('/api/olx', methods=['POST'])
def get_olx_listings():
    ip = get_client_ip()
    now = time.time()

    if ip in OLX_RATE_LIMIT:
        OLX_RATE_LIMIT[ip] = [t for t in OLX_RATE_LIMIT[ip] if now - t < OLX_WINDOW]
        if len(OLX_RATE_LIMIT[ip]) >= OLX_MAX_REQUESTS:
            return jsonify({
                'error': f'Limite de {OLX_MAX_REQUESTS} consultas à OLX atingido. Tente novamente mais tarde.',
                'tentativas_restantes': 0
            }), 429

    if ip not in OLX_RATE_LIMIT:
        OLX_RATE_LIMIT[ip] = []

    data = request.json or {}
    modelo = data.get('modelo', '').strip()
    marca = data.get('marca', '').strip()
    ano = data.get('ano')
    ddd = data.get('ddd')
    estado = data.get('estado')
    regiao = data.get('regiao')
    municipio = data.get('municipio')
    preco_min = data.get('preco_min')
    preco_max = data.get('preco_max')
    
    try:
        max_results = int(data.get('max_results', 15))
        if max_results > 30:
            max_results = 30
        if max_results < 1:
            max_results = 15
    except Exception:
        max_results = 15

    if not modelo:
        return jsonify({'error': 'Modelo não informado.'}), 400

    # Se o ID foi passado no formato cod_fipe|ano, busca nome no duckdb
    if '|' in modelo:
        parts = modelo.split('|')
        cod_fipe = parts[0]
        ano_val = int(parts[1]) if parts[1].isdigit() else None
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT nome_marca, nome_modelo FROM fipe WHERE codigo_fipe = ? AND ano_modelo = ? LIMIT 1", [cod_fipe, ano_val]).fetchone()
            if row:
                marca = row[0]
                modelo = f"{row[1]} ({ano_val})"
                ano = ano_val
            conn.close()
        except Exception:
            pass

    OLX_RATE_LIMIT[ip].append(now)
    restantes = max(0, OLX_MAX_REQUESTS - len(OLX_RATE_LIMIT[ip]))

    try:
        anuncios = olx.search_olx(
            query=modelo,
            brand=marca,
            year=ano,
            ddd=ddd,
            estado=estado,
            regiao=regiao,
            municipio=municipio,
            preco_min=preco_min,
            preco_max=preco_max,
            max_results=max_results
        )
        return jsonify({
            'success': True,
            'modelo_buscado': modelo,
            'tentativas_restantes': restantes,
            'max_tentativas': OLX_MAX_REQUESTS,
            'total': len(anuncios),
            'filtros': {
                'ddd': ddd,
                'estado': estado,
                'regiao': regiao,
                'municipio': municipio,
                'preco_min': preco_min,
                'preco_max': preco_max
            },
            'anuncios': anuncios
        })
    except Exception as e:
        if now in OLX_RATE_LIMIT[ip]:
            OLX_RATE_LIMIT[ip].remove(now)
        restantes_corrigido = max(0, OLX_MAX_REQUESTS - len(OLX_RATE_LIMIT[ip]))
        return jsonify({
            'error': f"Erro ao consultar OLX: {str(e)}",
            'tentativas_restantes': restantes_corrigido
        }), 500

# --- Ficha Técnica (iCarros) ---
@app.route('/api/ficha-tecnica', methods=['POST'])
def api_ficha_tecnica():
    data = request.json or {}
    modelo = data.get('modelo', '').strip()
    marca = data.get('marca', '').strip()

    if not modelo:
        return jsonify({'sucesso': False, 'erro': 'Modelo não informado.'}), 400

    # Se modelo tiver formato fipe "cod_fipe|ano"
    if '|' in modelo:
        parts = modelo.split('|')
        cod_fipe = parts[0]
        ano_val = int(parts[1]) if parts[1].isdigit() else None
        try:
            conn = get_db_connection()
            row = conn.execute("SELECT nome_marca, nome_modelo FROM fipe WHERE codigo_fipe = ? AND ano_modelo = ? LIMIT 1", [cod_fipe, ano_val]).fetchone()
            if row:
                marca = row[0]
                modelo = f"{row[1]} ({ano_val})"
            conn.close()
        except Exception:
            pass

    try:
        dados = ficha_tecnica_icarros.obter_ficha_tecnica_icarros(termo_carro=modelo)
        return jsonify(dados)
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

import threading
import check_release

def daily_update_check():
    while True:
        try:
            check_release.check_and_update()
        except Exception as e:
            print(f"Erro na checagem diária: {e}")
        time.sleep(86400) # Dorme por 24 horas

if __name__ == '__main__':
    init_sugestoes_db()
    
    # Inicia a checagem em background para não travar o início do servidor
    threading.Thread(target=daily_update_check, daemon=True).start()
    
    app.run(debug=True, port=7177)
