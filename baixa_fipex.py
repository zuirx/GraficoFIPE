import urllib.request
import json
import duckdb
import os
import sys

API_URL = 'https://api.github.com/repos/fipex-labs/dataset/releases/latest'
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipex-prices-latest.csv')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')

def reporthook(blocknum, blocksize, totalsize):
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize
        sys.stdout.write(f"\rBaixando CSV: {percent:5.1f}% ({readsofar / (1024*1024):.1f} MB / {totalsize / (1024*1024):.1f} MB)")
        sys.stdout.flush()
    else:
        sys.stdout.write(f"\rBaixando CSV: {readsofar / (1024*1024):.1f} MB")
        sys.stdout.flush()

def main():
    print('Buscando a última versão no GitHub...')
    req = urllib.request.Request(API_URL)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    assets = data.get('assets', [])
    csv_url = None
    for asset in assets:
        if asset['name'] == 'fipex-prices-latest.csv':
            csv_url = asset['browser_download_url']
            break
            
    if not csv_url:
        print('Erro: Não foi possível encontrar o arquivo fipex-prices-latest.csv na release.')
        return
        
    print(f'URL encontrada: {csv_url}')
    
    # Download
    print(f'Iniciando download para {CSV_PATH}...')
    urllib.request.urlretrieve(csv_url, CSV_PATH, reporthook)
    print('\nDownload concluído!')
    
    # Atualiza banco
    print(f'Atualizando banco de dados DuckDB em {DB_PATH}...')
    
    # Remove banco antigo para recriar do zero
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
            
        conn = duckdb.connect(DB_PATH)
        
        print('Importando dados do CSV (isso pode levar alguns segundos)...')
        conn.execute(f"CREATE TABLE fipe AS SELECT * FROM read_csv_auto('{CSV_PATH}')")
        
        print('Criando índices para otimizar consultas...')
        conn.execute("CREATE INDEX idx_tipo ON fipe(tipo_veiculo)")
        conn.execute("CREATE INDEX idx_marca ON fipe(nome_marca)")
        conn.execute("CREATE INDEX idx_modelo ON fipe(nome_modelo)")

        print('Calculando ranking de variações e desvalorização (pré-computado)...')
        conn.execute("""
            CREATE TABLE ranking AS 
            SELECT 
                codigo_fipe,
                MAX(nome_marca) as marca,
                MAX(nome_modelo) as modelo,
                MAX(ano_modelo) as ano_modelo,
                MAX(valor_centavos)/100.0 as preco_max,
                MIN(valor_centavos)/100.0 as preco_min,
                arg_max(valor_centavos, ano_referencia * 100 + mes_referencia)/100.0 as preco_atual,
                arg_min(valor_centavos, ano_referencia * 100 + mes_referencia)/100.0 as preco_inicial,
                ((arg_max(valor_centavos, ano_referencia * 100 + mes_referencia) * 1.0) / 
                 NULLIF(arg_min(valor_centavos, ano_referencia * 100 + mes_referencia), 0) - 1) * 100.0 as variacao_percentual
            FROM fipe
            GROUP BY codigo_fipe
        """)
        conn.execute("CREATE INDEX idx_ranking_variacao ON ranking(variacao_percentual)")
        
        print('Banco de dados atualizado com sucesso!')
    except Exception as e:
        print(f'Erro ao atualizar o DuckDB: {e}')
    finally:
        if 'conn' in locals():
            conn.close()
            
    print('Tudo pronto! O Flask já pode usar os dados atualizados.')

if __name__ == '__main__':
    main()
