# -*- coding: utf-8 -*-
"""
ficha_tecnica_icarros.py
Módulo para consultar e extrair especificações técnicas completas de veículos do iCarros.
Sem necessidade de navegador, sem OCR e sem captcha (requisições HTTP padrão ultra-rápidas).

Funcionalidades:
- Análise e extração automática de marca, modelo, ano e versão a partir de strings no padrão FIPE
- Consulta ao catálogo oficial do iCarros (https://www.icarros.com.br/catalogo)
- Seleção inteligente da versão correta a partir das opções do catálogo
- Extração categorizada de todas as especificações:
  * Motorização (Motor, Câmbio, Combustível, Direção, Tração)
  * Performance e Consumo (Potência Álcool/Gasolina, 0-100 km/h, Torque, Consumo Urbano e Rodoviário, Velocidade Máx)
  * Dimensões e Capacidades (Comprimento, Largura, Altura, Entre-eixos, Peso, Porta-malas, Tanque, Ocupantes)
  * Freios, Suspensão e Direção
  * Equipamentos (Segurança, Conforto, Som, Janelas, Bancos, etc.)
- Cache local SQLite compartilhado (fichas_cache.db)
"""

import os
import sys
import re
import json
import sqlite3
from typing import Dict, Any, Optional, List
import requests
from bs4 import BeautifulSoup
import duckdb

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')
CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fichas_cache.db')

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.icarros.com.br/catalogo'
}

# Mapeamento para slugs no iCarros
BRAND_MAP = {
    'vw - volkswagen': 'volkswagen',
    'volkswagen': 'volkswagen',
    'gm - chevrolet': 'chevrolet',
    'chevrolet': 'chevrolet',
    'fiat': 'fiat',
    'ford': 'ford',
    'toyota': 'toyota',
    'hyundai': 'hyundai',
    'honda': 'honda',
    'renault': 'renault',
    'jeep': 'jeep',
    'nissan': 'nissan',
    'peugeot': 'peugeot',
    'citroen': 'citroen',
    'citroën': 'citroen',
    'mitsubishi': 'mitsubishi',
    'bmw': 'bmw',
    'mercedes-benz': 'mercedes-benz',
    'mercedes': 'mercedes-benz',
    'audi': 'audi',
    'byd': 'byd',
    'gwm': 'gwm',
    'caoa chery': 'caoa-chery',
    'chery': 'caoa-chery',
    'kia': 'kia',
    'volvo': 'volvo',
    'ram': 'ram',
    'land rover': 'land-rover',
    'porsche': 'porsche',
    'suzuki': 'suzuki',
    'jac': 'jac',
    'mini': 'mini',
    'subaru': 'subaru',
    'troller': 'troller',
    'lexus': 'lexus',
    'dodge': 'dodge'
}

POPULAR_MODELS = {
    'gol': 'volkswagen', 'voyage': 'volkswagen', 'saveiro': 'volkswagen', 'fox': 'volkswagen',
    'polo': 'volkswagen', 'virtus': 'volkswagen', 't-cross': 'volkswagen', 'nivus': 'volkswagen',
    'taos': 'volkswagen', 'amarok': 'volkswagen', 'jetta': 'volkswagen', 'up': 'volkswagen',
    'golf': 'volkswagen', 'fusca': 'volkswagen', 'santana': 'volkswagen',
    'palio': 'fiat', 'uno': 'fiat', 'strada': 'fiat', 'toro': 'fiat', 'mobi': 'fiat',
    'argo': 'fiat', 'cronos': 'fiat', 'pulse': 'fiat', 'fastback': 'fiat', 'siena': 'fiat',
    'grand siena': 'fiat', 'fiorino': 'fiat', 'punto': 'fiat', 'linea': 'fiat', 'doblo': 'fiat',
    'onix': 'chevrolet', 'onix plus': 'chevrolet', 'prisma': 'chevrolet', 'celta': 'chevrolet',
    'corsa': 'chevrolet', 'tracker': 'chevrolet', 's10': 'chevrolet', 'spin': 'chevrolet',
    'cruze': 'chevrolet', 'montana': 'chevrolet', 'classic': 'chevrolet', 'cobalt': 'chevrolet',
    'ka': 'ford', 'fiesta': 'ford', 'ecosport': 'ford', 'ranger': 'ford', 'focus': 'ford', 'fusion': 'ford',
    'corolla': 'toyota', 'corolla cross': 'toyota', 'hilux': 'toyota', 'yaris': 'toyota', 'etios': 'toyota',
    'hb20': 'hyundai', 'hb20s': 'hyundai', 'hb20x': 'hyundai', 'creta': 'hyundai', 'tucson': 'hyundai',
    'civic': 'honda', 'fit': 'honda', 'city': 'honda', 'hr-v': 'honda', 'cr-v': 'honda', 'wr-v': 'honda',
    'sandero': 'renault', 'logan': 'renault', 'duster': 'renault', 'kwid': 'renault', 'captur': 'renault',
    'renegade': 'jeep', 'compass': 'jeep', 'commander': 'jeep',
    'kicks': 'nissan', 'versa': 'nissan', 'march': 'nissan', 'frontier': 'nissan',
    '208': 'peugeot', '2008': 'peugeot', '3008': 'peugeot',
    'c3': 'citroen', 'c4': 'citroen', 'c4 cactus': 'citroen', 'aircross': 'citroen'
}


def normalize_slug(text: str) -> str:
    """Normaliza para slug simples de URL."""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r'[áàâãä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôõö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def init_cache_db():
    """Garante a existência da tabela de cache local SQLite e suas colunas."""
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fichas_cache (
                termo_busca TEXT PRIMARY KEY,
                url TEXT,
                carro TEXT,
                dados_json TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Adiciona coluna fonte se não existir
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(fichas_cache)")
        cols = [r[1] for r in cur.fetchall()]
        if 'fonte' not in cols:
            conn.execute("ALTER TABLE fichas_cache ADD COLUMN fonte TEXT DEFAULT 'icarros'")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Cache] Erro ao inicializar cache: {e}")


def get_from_cache(termo: str) -> Optional[Dict[str, Any]]:
    """Recupera os dados de ficha técnica do cache local SQLite."""
    try:
        init_cache_db()
        termo_limpo = termo.strip().lower()
        conn = sqlite3.connect(CACHE_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT dados_json FROM fichas_cache WHERE termo_busca = ?", (termo_limpo,))
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            dados = json.loads(row[0])
            dados["from_cache"] = True
            return dados
    except Exception as e:
        print(f"[Cache] Erro ao ler cache: {e}")
    return None


def save_to_cache(termo: str, dados: Dict[str, Any]):
    """Armazena a ficha técnica no cache local SQLite."""
    try:
        init_cache_db()
        termo_limpo = termo.strip().lower()
        conn = sqlite3.connect(CACHE_DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO fichas_cache (termo_busca, url, carro, fonte, dados_json)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            termo_limpo, 
            dados.get("url", ""), 
            dados.get("carro", ""), 
            "icarros",
            json.dumps(dados, ensure_ascii=False)
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Cache] Erro ao salvar no cache: {e}")


def parse_car_query(query: str, brand: str = None, year: int = None) -> Dict[str, Any]:
    """Identifica marca, modelo base, ano e termos da versão a partir da consulta."""
    clean_query = query.strip()
    extracted_year = year

    # 1. Extração do ano
    if not extracted_year:
        year_match = re.search(r'\((\d{4})\)', clean_query)
        if year_match:
            extracted_year = int(year_match.group(1))
            clean_query = re.sub(r'\s*\(\d{4}\)', '', clean_query).strip()
        else:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', clean_query)
            if year_match:
                extracted_year = int(year_match.group(1))
                clean_query = re.sub(r'\b(19\d{2}|20\d{2})\b', '', clean_query).strip()

    # 2. Identificação do modelo base
    multi_word_models = [
        'grand siena', 'novo gol', 'corolla cross', 'hb20s', 'hb20x', 'hb20',
        'c4 cactus', 'c3 aircross', 'aircross', 'tiggo 5x', 'tiggo 7', 'tiggo 8',
        'haval h6', 'song plus', 'yuan plus', 'dolphin mini'
    ]
    model_slug = ""
    lower_query = clean_query.lower()
    for mwm in multi_word_models:
        if mwm in lower_query:
            model_slug = normalize_slug(mwm)
            break

    if not model_slug:
        parts = clean_query.split()
        if parts:
            first_norm = normalize_slug(parts[0])
            if first_norm in BRAND_MAP.values() and len(parts) > 1:
                model_slug = normalize_slug(parts[1])
            else:
                model_slug = first_norm

    # 3. Identificação da marca
    detected_brand = brand
    if not detected_brand and model_slug in POPULAR_MODELS:
        detected_brand = POPULAR_MODELS[model_slug]

    if not detected_brand and os.path.exists(DB_PATH):
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            row = conn.execute("SELECT nome_marca FROM fipe WHERE tipo_veiculo = 'carro' AND nome_modelo = ? LIMIT 1", [clean_query]).fetchone()
            if not row and model_slug:
                row = conn.execute("SELECT nome_marca FROM fipe WHERE tipo_veiculo = 'carro' AND (nome_modelo ILIKE ? OR nome_modelo ILIKE ?) LIMIT 1", [f"{model_slug} %", f"{model_slug}/%"]).fetchone()
            if row:
                detected_brand = row[0]
            conn.close()
        except Exception:
            pass

    if not detected_brand:
        for b_name, b_slug in BRAND_MAP.items():
            if re.search(rf'\b{re.escape(b_name)}\b', lower_query):
                detected_brand = b_slug
                break

    brand_slug = ""
    if detected_brand:
        norm_b = detected_brand.lower().strip()
        brand_slug = BRAND_MAP.get(norm_b, normalize_slug(detected_brand))

    return {
        'brand': detected_brand,
        'brand_slug': brand_slug,
        'model_slug': model_slug,
        'year': extracted_year,
        'clean_query': clean_query
    }


def extrair_ficha_icarros_html(html: str, url: str = "") -> Dict[str, Any]:
    """Extrai todas as especificações e equipamentos da página HTML do iCarros."""
    soup = BeautifulSoup(html, 'html.parser')

    # Nome do Carro
    h1 = soup.find('h1')
    car_name = h1.get_text(strip=True) if h1 else ""
    if not car_name and soup.title:
        car_name = soup.title.string.split('-')[0].strip()

    # Imagens do Catálogo
    fotos = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if ('catalogo' in src or 'imagensbd' in src) and not any(w in src for w in ['icon', 'logo', 'arrow', 'banner', 'avatar']):
            if not src.startswith('http'):
                src = 'https://www.icarros.com.br' + src
            if src not in fotos:
                fotos.append(src)

    # Especificações organizadas por seções
    especificacoes: Dict[str, Dict[str, str]] = {
        "Motorização": {},
        "Performance e Consumo": {},
        "Dimensões e Capacidades": {},
        "Freios, Suspensão e Direção": {}
    }
    
    equipamentos: Dict[str, List[str]] = {
        "Segurança": [],
        "Conforto": [],
        "Som e Conectividade": [],
        "Outros": []
    }

    # As fichas técnicas do iCarros listam dados em blocos e no texto da página
    for item in soup.find_all(class_='technical-sheet-item'):
        txt = item.get_text(' : ', strip=True)
        parts = [p.strip() for p in txt.split(' : ') if p.strip()]
        if len(parts) >= 2:
            campo = parts[0]
            valor = ' '.join(parts[1:])
            valor = re.sub(r'\s+', ' ', valor).strip()

            campo_l = campo.lower()
            if any(w in campo_l for w in ['motor', 'câmbio', 'combustível', 'cilindrada', 'válvulas', 'injeção']):
                especificacoes["Motorização"][campo] = valor
            elif any(w in campo_l for w in ['potência', 'torque', '0-100', 'consumo', 'velocidade', 'tempo']):
                especificacoes["Performance e Consumo"][campo] = valor
            elif any(w in campo_l for w in ['altura', 'largura', 'comprimento', 'entre-eixos', 'peso', 'tanque', 'porta-malas', 'ocupantes']):
                especificacoes["Dimensões e Capacidades"][campo] = valor
            elif any(w in campo_l for w in ['direção', 'tração', 'suspensão', 'freios']):
                especificacoes["Freios, Suspensão e Direção"][campo] = valor
            else:
                especificacoes["Motorização"][campo] = valor

    # Extrai equipamentos de série do bloco descritivo
    page_text = soup.get_text('\n', strip=True)
    equip_map = {
        "Segurança": ["Airbag", "Freios ABS", "Alarme", "Controle de tração", "Distribuição eletrônica de frenagem", "Isofix", "Sensor de estacionamento"],
        "Conforto": ["Ar-condicionado", "Travas elétricas", "Ar-quente", "Piloto automático", "Volante com regulagem", "Direção hidráulica", "Direção elétrica"],
        "Som e Conectividade": ["Cd player", "Entrada USB", "Rádio FM/AM", "Kit Multimídia", "Bluetooth", "Computador de bordo", "GPS"],
        "Outros": ["Vidros elétricos", "Desemb. traseiro", "Teto solar", "Bancos de couro", "Ajuste de altura", "Farol de neblina", "Rodas de liga leve"]
    }
    
    for cat, items in equip_map.items():
        for it in items:
            if re.search(rf'\b{re.escape(it)}\b', page_text, re.IGNORECASE):
                if it not in equipamentos[cat]:
                    equipamentos[cat].append(it)

    # Remove seções vazias
    especificacoes = {k: v for k, v in especificacoes.items() if v}
    equipamentos = {k: v for k, v in equipamentos.items() if v}

    return {
        "sucesso": True,
        "carro": car_name or "Veículo",
        "url": url,
        "fotos": fotos,
        "especificacoes": especificacoes,
        "equipamentos": equipamentos
    }


def obter_ficha_tecnica_icarros(termo_carro: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Busca e retorna a ficha técnica detalhada de um veículo diretamente do iCarros.
    
    Args:
        termo_carro: Nome do modelo/versão e ano (ex: "Gol Special 1.0 Total Flex 8V 5p (2015)")
        force_refresh: Se True, ignora o cache local
        
    Returns:
        Dicionário estruturado com as especificações técnicas
    """
    termo_carro = termo_carro.strip()
    if not termo_carro:
        return {"sucesso": False, "erro": "Termo de busca não fornecido."}

    # 1. Verifica no cache local
    if not force_refresh:
        cached = get_from_cache(termo_carro)
        if cached:
            print(f"[iCarros] Retornando dados do cache para: '{termo_carro}'")
            return cached

    parsed = parse_car_query(termo_carro)
    brand_slug = parsed['brand_slug']
    model_slug = parsed['model_slug']
    year = parsed['year']
    clean_query = parsed['clean_query']

    if not brand_slug or not model_slug:
        return {
            "sucesso": False,
            "erro": f"Não foi possível identificar a marca e modelo a partir de '{termo_carro}'."
        }

    # URL base do catálogo daquele ano
    if year:
        catalog_url = f"https://www.icarros.com.br/catalogo/marcas/{brand_slug}/{model_slug}/{year}"
    else:
        catalog_url = f"https://www.icarros.com.br/catalogo/marcas/{brand_slug}/{model_slug}"

    print(f"[iCarros] Consultando catálogo: {catalog_url}")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    try:
        resp = session.get(catalog_url, timeout=12)
        if resp.status_code != 200:
            return {
                "sucesso": False,
                "erro": f"Catálogo do iCarros retornou status {resp.status_code} para {catalog_url}."
            }

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # O iCarros traz um <select> com todas as versões cadastradas para o ano
        version_options = []
        for select in soup.find_all('select'):
            for opt in select.find_all('option'):
                val = opt.get('value', '')
                text = opt.get_text(strip=True)
                if val and f"{brand_slug}/{model_slug}/" in val:
                    version_options.append((val, text))

        target_version_path = ""
        # Palavras da consulta do usuário para ranqueamento
        query_words = set(re.findall(r'\b\w+\b', clean_query.lower()))
        query_words.discard(model_slug.lower())
        query_words.discard(brand_slug.lower())

        if version_options:
            def score_version(opt_tuple):
                val, text = opt_tuple
                text_l = f"{val} {text}".lower()
                score = 0
                for w in query_words:
                    if w in text_l:
                        if w in ['special', 'fire', 'trendline', 'comfortline', 'highline', 'tsi', 'lt', 'ltz', 'sense', 'xei']:
                            score += 5
                        elif re.match(r'^\d+(\.\d+)?$', w):
                            score += 3
                        elif w in ['2p', '4p', '5p']:
                            score += 4
                        else:
                            score += 1
                return score

            best_option = max(version_options, key=score_version)
            target_version_path = best_option[0]
            print(f"[iCarros] Versão selecionada: '{best_option[1]}' (path: {target_version_path})")

        if target_version_path:
            final_url = f"https://www.icarros.com.br/catalogo/marcas/{target_version_path.lstrip('/')}"
            ficha_resp = session.get(final_url, timeout=12)
            if ficha_resp.status_code == 200:
                dados = extrair_ficha_icarros_html(ficha_resp.text, final_url)
            else:
                dados = extrair_ficha_icarros_html(resp.text, resp.url)
        else:
            dados = extrair_ficha_icarros_html(resp.text, resp.url)

        if dados.get("sucesso") and len(dados.get("especificacoes", {})) > 0:
            save_to_cache(termo_carro, dados)
            return dados
        else:
            return {"sucesso": False, "erro": "Ficha técnica encontrada, mas sem especificações válidas."}

    except Exception as e:
        print(f"[iCarros] Erro ao extrair ficha técnica: {e}")
        return {"sucesso": False, "erro": str(e)}


if __name__ == '__main__':
    termo = sys.argv[1] if len(sys.argv) > 1 else "Gol Special 1.0 Total Flex 8V 5p (2015)"
    print(f"=== Buscando Ficha Técnica no iCarros: '{termo}' ===")
    res = obter_ficha_tecnica_icarros(termo)
    print("\n" + "=" * 50)
    print("RESULTADO ICARROS:")
    print("Sucesso:", res.get("sucesso"))
    print("Carro:", res.get("carro"))
    print("URL:", res.get("url"))
    print("Fotos:", len(res.get("fotos", [])))
    print("Especificações:")
    for secao, campos in res.get("especificacoes", {}).items():
        print(f"\n  [{secao}] ({len(campos)} campos):")
        for k, v in campos.items():
            print(f"    - {k}: {v}")
    print("\nEquipamentos:")
    for cat, itens in res.get("equipamentos", {}).items():
        print(f"  [{cat}]: {', '.join(itens)}")
    if not res.get("sucesso"):
        print("Erro:", res.get("erro"))
    print("=" * 50)
