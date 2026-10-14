import os
import json
import urllib.request
import duckdb

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macro_cache.json')

def fetch_bcb_serie(serie_id, timeout=10):
    url = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados?formato=json'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))

def parse_bcb_items(raw_items):
    data_dict = {}
    for item in raw_items:
        try:
            parts = item['data'].split('/')
            mes_cod = int(parts[2]) * 100 + int(parts[1])
            data_dict[mes_cod] = float(item['valor'])
        except Exception:
            pass
    return data_dict

def carregar_ou_atualizar_cache():
    # Tenta buscar dados frescos do Banco Central do Brasil
    try:
        dolar_raw = fetch_bcb_serie(3696) # Taxa de câmbio - Dólar americano (venda) - mensal fim de período
        selic_raw = fetch_bcb_serie(4390) # Taxa Selic acumulada no mês (% a.m.)
        ipca_raw = fetch_bcb_serie(433)   # IPCA mensal (% a.m.)

        dolar = parse_bcb_items(dolar_raw)
        selic = parse_bcb_items(selic_raw)
        ipca = parse_bcb_items(ipca_raw)

        all_meses = sorted(set(dolar.keys()) | set(selic.keys()) | set(ipca.keys()))
        cache = []
        for m in all_meses:
            if m >= 200001:
                cache.append({
                    'mes_codigo': m,
                    'ipca': ipca.get(m, 0.0),
                    'selic': selic.get(m, 0.0),
                    'dolar': dolar.get(m, 0.0)
                })

        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)

        return cache
    except Exception as e:
        print(f"[macro_service] Erro ao buscar dados do BCB: {e}. Usando cache local.")
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

def inicializar_tabela_macro(conn):
    try:
        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        has_table = 'macro' in tables
        has_data = False
        if has_table:
            cnt = conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
            if cnt >= 50:
                has_data = True

        if not has_data:
            print("[macro_service] Criando e populando tabela 'macro'...")
            conn.execute("CREATE TABLE IF NOT EXISTS macro (mes_codigo INTEGER PRIMARY KEY, ipca DOUBLE, selic DOUBLE, dolar DOUBLE)")
            conn.execute("DELETE FROM macro")

            # Carrega do cache se existir ou busca do BCB
            dados = []
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                        dados = json.load(f)
                except Exception:
                    pass

            if not dados:
                dados = carregar_ou_atualizar_cache()

            if dados:
                rows = [(d['mes_codigo'], float(d.get('ipca', 0.0)), float(d.get('selic', 0.0)), float(d.get('dolar', 0.0))) for d in dados]
                conn.executemany("INSERT INTO macro VALUES (?, ?, ?, ?)", rows)
                print(f"[macro_service] Tabela 'macro' populada com {len(rows)} registros.")
    except Exception as e:
        print(f"[macro_service] Erro ao inicializar tabela macro: {e}")

def obter_dados_macro(conn, sorted_mes_codigos):
    if not sorted_mes_codigos:
        return []

    min_mes = sorted_mes_codigos[0]
    max_mes = sorted_mes_codigos[-1]

    try:
        macro_res = conn.execute(
            "SELECT mes_codigo, ipca, selic, dolar FROM macro WHERE mes_codigo >= ? AND mes_codigo <= ? ORDER BY mes_codigo",
            (min_mes, max_mes)
        ).fetchall()
        
        # Se tabela vazia, tenta inicializar e consultar novamente
        if not macro_res:
            inicializar_tabela_macro(conn)
            macro_res = conn.execute(
                "SELECT mes_codigo, ipca, selic, dolar FROM macro WHERE mes_codigo >= ? AND mes_codigo <= ? ORDER BY mes_codigo",
                (min_mes, max_mes)
            ).fetchall()

        macro_dict = {r[0]: {'ipca': round(r[1] or 0.0, 4), 'selic': round(r[2] or 0.0, 4), 'dolar': round(r[3] or 0.0, 4)} for r in macro_res}
        
        resultado = []
        for cod in sorted_mes_codigos:
            resultado.append(macro_dict.get(cod, {'ipca': 0.0, 'selic': 0.0, 'dolar': 0.0}))
        return resultado
    except Exception as e:
        print(f"[macro_service] Erro ao obter dados macro: {e}")
        try:
            inicializar_tabela_macro(conn)
        except Exception:
            pass
        return [{'ipca': 0.0, 'selic': 0.0, 'dolar': 0.0} for _ in sorted_mes_codigos]
