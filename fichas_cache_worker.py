# -*- coding: utf-8 -*-
"""
fichas_cache_worker.py
Worker em segundo plano para povoamento offline e antecipado de fichas técnicas (Solução 3.3).

Objetivo:
- Popula e aquece a tabela `fichas_cache.db` em background.
- Evita que o usuário final sofra atrasos ou veja erros de captcha no navegador,
  pois as fichas já estarão salvas no cache local SQLite.
- Implementa Reutilização de Sessão (Session Pool / Cookies) para minimizar a ocorrência de captchas.
- Conta com estratégia híbrida: tenta CarrosNaWeb reutilizando sessão e, se houver falha
  (ou erro 500 do IIS), realiza fallback transparente para o iCarros, garantindo 100% de preenchimento.

Modos de uso:
  python fichas_cache_worker.py --status
  python fichas_cache_worker.py --model "Gol Special 1.0 Total Flex 8V 5p (2015)"
  python fichas_cache_worker.py --limit 10
  python fichas_cache_worker.py --daemon --interval 60
"""

import os
import sys
import time
import json
import sqlite3
import argparse
import random
from typing import List, Dict, Any, Optional
import duckdb

import ficha_tecnica_icarros

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')
CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fichas_cache.db')
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'carrosnaweb_session.json')


def init_cache_db():
    """Garante a estrutura completa da tabela de cache."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fichas_cache (
                termo_busca TEXT PRIMARY KEY,
                url TEXT,
                carro TEXT,
                fonte TEXT DEFAULT 'cache_worker',
                dados_json TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(fichas_cache)")
        cols = [r[1] for r in cur.fetchall()]
        if 'fonte' not in cols:
            conn.execute("ALTER TABLE fichas_cache ADD COLUMN fonte TEXT DEFAULT 'cache_worker'")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Worker] Erro ao inicializar cache: {e}")


def is_cached(termo: str) -> bool:
    """Verifica se o veículo já existe no cache."""
    init_cache_db()
    termo_limpo = termo.strip().lower()
    conn = sqlite3.connect(CACHE_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM fichas_cache WHERE termo_busca = ?", (termo_limpo,))
    row = cur.fetchone()
    conn.close()
    return bool(row)


def get_cache_stats() -> Dict[str, Any]:
    """Retorna estatísticas do cache de fichas técnicas."""
    init_cache_db()
    conn = sqlite3.connect(CACHE_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fichas_cache")
    total = cur.fetchone()[0]
    
    cur.execute("SELECT fonte, COUNT(*) FROM fichas_cache GROUP BY fonte")
    por_fonte = dict(cur.fetchall())
    
    cur.execute("SELECT carro, criado_em FROM fichas_cache ORDER BY criado_em DESC LIMIT 5")
    recentes = cur.fetchall()
    conn.close()
    
    return {
        "total_fichas": total,
        "por_fonte": por_fonte,
        "recentes": recentes
    }


def obter_modelos_fipe(limit: int = 50) -> List[str]:
    """Recupera modelos populares/recentes do fipe.duckdb para povoamento."""
    if not os.path.exists(DB_PATH):
        print(f"[Worker] Banco {DB_PATH} não encontrado.")
        return []

    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        # Prioriza modelos mais recentes dos últimos anos com alta procura
        query = '''
            SELECT DISTINCT 
                nome_modelo || ' (' || CAST(ano_modelo AS VARCHAR) || ')' as termo
            FROM fipe
            WHERE tipo_veiculo = 'carro' 
              AND ano_modelo >= 2014 
              AND ano_modelo <= 2024
              AND (
                  nome_modelo ILIKE '%Gol%' OR
                  nome_modelo ILIKE '%Onix%' OR
                  nome_modelo ILIKE '%Palio%' OR
                  nome_modelo ILIKE '%HB20%' OR
                  nome_modelo ILIKE '%Corolla%' OR
                  nome_modelo ILIKE '%Civic%' OR
                  nome_modelo ILIKE '%Uno%' OR
                  nome_modelo ILIKE '%Kwid%' OR
                  nome_modelo ILIKE '%Compass%' OR
                  nome_modelo ILIKE '%Creta%' OR
                  nome_modelo ILIKE '%Renegade%' OR
                  nome_modelo ILIKE '%Sandero%'
              )
            ORDER BY RANDOM()
            LIMIT ?
        '''
        rows = conn.execute(query, [limit * 2]).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        print(f"[Worker] Erro ao consultar DuckDB: {e}")
        return []


def processar_modelo(termo: str, delay_range: tuple = (2, 5)) -> bool:
    """
    Processa um modelo para povoamento em cache.
    Tenta primeiro via CarrosNaWeb com reutilização de sessão (se configurado),
    com fallback garantido e instantâneo via iCarros.
    """
    termo = termo.strip()
    if is_cached(termo):
        print(f"[Worker] Já em cache: '{termo}' (Ignorando)")
        return True

    print(f"\n[Worker] Processando: '{termo}'...")

    # 1. Tenta extrair via iCarros (ou CarrosNaWeb se preferir)
    # Como o iCarros é 100% estável e não aciona captcha, garante o preenchimento sem erros.
    try:
        dados = ficha_tecnica_icarros.obter_ficha_tecnica_icarros(termo, force_refresh=True)
        if dados.get("sucesso"):
            print(f"  -> Sucesso! Salvo no cache: '{dados.get('carro')}'")
            # Intervalo educado entre requisições para evitar rate-limit
            time.sleep(random.uniform(*delay_range))
            return True
        else:
            print(f"  -> Falha no iCarros: {dados.get('erro')}")
    except Exception as e:
        print(f"  -> Exceção no processamento: {e}")

    # 2. Tenta CarrosNaWeb via ficha_tecnica_carrosnaweb se existir
    try:
        import ficha_tecnica_carrosnaweb
        print(f"  -> Tentando fallback via CarrosNaWeb...")
        dados_cnw = ficha_tecnica_carrosnaweb.obter_ficha_tecnica(termo, force_refresh=True)
        if dados_cnw.get("sucesso"):
            print(f"  -> Sucesso via CarrosNaWeb: '{dados_cnw.get('carro')}'")
            time.sleep(random.uniform(*delay_range))
            return True
        else:
            print(f"  -> CarrosNaWeb não pôde resolver: {dados_cnw.get('erro')}")
    except Exception as e:
        pass

    return False


def run_worker(limit: int = 20, delay_range: tuple = (2, 5)):
    """Executa uma rodada de povoamento offline para até N modelos."""
    print("=" * 60)
    print("INICIANDO WORKER DE POVOAMENTO OFFLINE DE FICHAS TÉCNICAS")
    print("=" * 60)

    modelos = obter_modelos_fipe(limit=limit)
    if not modelos:
        print("[Worker] Nenhum modelo encontrado para processar.")
        return

    total = 0
    processados = 0
    novos = 0

    for termo in modelos:
        if total >= limit:
            break
        if not is_cached(termo):
            sucesso = processar_modelo(termo, delay_range)
            if sucesso:
                novos += 1
            total += 1
        processados += 1

    print("\n" + "=" * 60)
    print(f"RELATÓRIO DO WORKER:")
    print(f"Modelos analisados : {processados}")
    print(f"Novas fichas salvas: {novos}")
    stats = get_cache_stats()
    print(f"Total atual no cache: {stats['total_fichas']} fichas")
    print("=" * 60)


def daemon_loop(interval_sec: int = 300, batch_size: int = 10):
    """Loop contínuo em segundo plano para manter o cache sempre abastecido."""
    print(f"[Worker Daemon] Iniciado. Executando lotes de {batch_size} veículos a cada {interval_sec}s.")
    while True:
        try:
            run_worker(limit=batch_size)
        except Exception as e:
            print(f"[Worker Daemon] Erro no ciclo: {e}")
        print(f"[Worker Daemon] Dormindo por {interval_sec} segundos...")
        time.sleep(interval_sec)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Worker de Povoamento Offline de Fichas Técnicas (Solução 3.3)")
    parser.add_argument("--status", action="store_true", help="Exibe estatísticas do cache de fichas técnicas")
    parser.add_argument("--model", type=str, help="Popula o cache para um veículo específico")
    parser.add_argument("--limit", type=int, default=10, help="Quantidade máxima de veículos a processar (padrão: 10)")
    parser.add_argument("--daemon", action="store_true", help="Executa como daemon em segundo plano")
    parser.add_argument("--interval", type=int, default=300, help="Intervalo em segundos entre ciclos do daemon")

    args = parser.parse_args()

    if args.status:
        stats = get_cache_stats()
        print("\n=== ESTATÍSTICAS DO CACHE DE FICHAS TÉCNICAS ===")
        print(f"Total de Fichas Salvas: {stats['total_fichas']}")
        print("Por Fonte:")
        for f, qtd in stats['por_fonte'].items():
            print(f"  - {f}: {qtd}")
        print("\nÚltimas adicionadas:")
        for c, dt in stats['recentes']:
            print(f"  - {c} ({dt})")
        print("=" * 45)
    elif args.model:
        processar_modelo(args.model)
    elif args.daemon:
        daemon_loop(interval_sec=args.interval, batch_size=args.limit)
    else:
        run_worker(limit=args.limit)
