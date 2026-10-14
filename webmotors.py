import os
import re
import urllib.parse
import duckdb
from patchright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')

def normalize_slug(text):
    """Normaliza texto para slug de URL (minúsculo, sem acentos, sem caracteres especiais)."""
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

# Mapeamento de marcas FIPE / comuns para os slugs do Webmotors
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
    'dodge': 'dodge',
    'jaguar': 'jaguar',
    'chrysler': 'chrysler',
    'alfa romeo': 'alfa-romeo'
}

# Modelos populares para detecção imediata da marca
POPULAR_MODELS = {
    'gol': 'volkswagen',
    'voyage': 'volkswagen',
    'saveiro': 'volkswagen',
    'fox': 'volkswagen',
    'polo': 'volkswagen',
    'virtus': 'volkswagen',
    't-cross': 'volkswagen',
    'nivus': 'volkswagen',
    'taos': 'volkswagen',
    'amarok': 'volkswagen',
    'jetta': 'volkswagen',
    'up': 'volkswagen',
    'golf': 'volkswagen',
    'fusca': 'volkswagen',
    'santana': 'volkswagen',
    'palio': 'fiat',
    'uno': 'fiat',
    'strada': 'fiat',
    'toro': 'fiat',
    'mobi': 'fiat',
    'argo': 'fiat',
    'cronos': 'fiat',
    'pulse': 'fiat',
    'fastback': 'fiat',
    'siena': 'fiat',
    'grand siena': 'fiat',
    'fiorino': 'fiat',
    'punto': 'fiat',
    'linea': 'fiat',
    'doblo': 'fiat',
    'idea': 'fiat',
    'onix': 'chevrolet',
    'onix plus': 'chevrolet',
    'prisma': 'chevrolet',
    'celta': 'chevrolet',
    'corsa': 'chevrolet',
    'tracker': 'chevrolet',
    's10': 'chevrolet',
    'spin': 'chevrolet',
    'cruze': 'chevrolet',
    'montana': 'chevrolet',
    'classic': 'chevrolet',
    'cobalt': 'chevrolet',
    'astra': 'chevrolet',
    'vectra': 'chevrolet',
    'meriva': 'chevrolet',
    'zafira': 'chevrolet',
    'ka': 'ford',
    'fiesta': 'ford',
    'ecosport': 'ford',
    'ranger': 'ford',
    'focus': 'ford',
    'fusion': 'ford',
    'territory': 'ford',
    'maverick': 'ford',
    'corolla': 'toyota',
    'corolla cross': 'toyota',
    'hilux': 'toyota',
    'yaris': 'toyota',
    'etios': 'toyota',
    'sw4': 'toyota',
    'rav4': 'toyota',
    'hb20': 'hyundai',
    'hb20s': 'hyundai',
    'hb20x': 'hyundai',
    'creta': 'hyundai',
    'tucson': 'hyundai',
    'ix35': 'hyundai',
    'i30': 'hyundai',
    'civic': 'honda',
    'fit': 'honda',
    'city': 'honda',
    'hr-v': 'honda',
    'cr-v': 'honda',
    'wr-v': 'honda',
    'sandero': 'renault',
    'logan': 'renault',
    'duster': 'renault',
    'kwid': 'renault',
    'captur': 'renault',
    'oroch': 'renault',
    'clio': 'renault',
    'renegade': 'jeep',
    'compass': 'jeep',
    'commander': 'jeep',
    'kicks': 'nissan',
    'versa': 'nissan',
    'march': 'nissan',
    'frontier': 'nissan',
    'sentra': 'nissan',
    '208': 'peugeot',
    '2008': 'peugeot',
    '3008': 'peugeot',
    '207': 'peugeot',
    '206': 'peugeot',
    'c3': 'citroen',
    'c4': 'citroen',
    'c4 cactus': 'citroen',
    'aircross': 'citroen',
    'l200': 'mitsubishi',
    'asx': 'mitsubishi',
    'pajero': 'mitsubishi',
    'eclipse cross': 'mitsubishi',
    'outlander': 'mitsubishi',
    'dolphin': 'byd',
    'seal': 'byd',
    'song plus': 'byd',
    'yuan plus': 'byd',
    'haval h6': 'gwm',
    'ora 03': 'gwm',
    'tiggo 5x': 'caoa-chery',
    'tiggo 7': 'caoa-chery',
    'tiggo 8': 'caoa-chery',
    'sportage': 'kia',
    'cerato': 'kia',
    'picanto': 'kia'
}

def parse_car_query(query, brand=None, year=None):
    """
    Analisa a string de busca e extrai:
    - marca (slug Webmotors)
    - modelo (slug Webmotors)
    - ano (int)
    - versão / query limpa
    """
    clean_query = query.strip()
    extracted_year = year

    # 1. Extração do ano (ex: '(2015)' ou '2015')
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
        'haval h6', 'song plus', 'yuan plus', 'dolphin mini', 'serie 3', 'serie 1'
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
            # Se a primeira palavra for marca e houver segunda palavra, o modelo é a segunda
            if first_norm in BRAND_MAP.values() and len(parts) > 1:
                model_slug = normalize_slug(parts[1])
            else:
                model_slug = first_norm

    # 3. Identificação da marca
    detected_brand = brand
    # Verifica nos modelos populares
    if not detected_brand and model_slug in POPULAR_MODELS:
        detected_brand = POPULAR_MODELS[model_slug]

    # Se não encontrado, tenta DuckDB
    if not detected_brand and os.path.exists(DB_PATH):
        try:
            conn = duckdb.connect(DB_PATH, read_only=True)
            # Busca por modelo completo
            row = conn.execute("SELECT nome_marca FROM fipe WHERE tipo_veiculo = 'carro' AND nome_modelo = ? LIMIT 1", [clean_query]).fetchone()
            if not row and model_slug:
                # Busca por prefixo do modelo
                row = conn.execute("SELECT nome_marca FROM fipe WHERE tipo_veiculo = 'carro' AND (nome_modelo ILIKE ? OR nome_modelo ILIKE ?) LIMIT 1", [f"{model_slug} %", f"{model_slug}/%"]).fetchone()
            if row:
                detected_brand = row[0]
            conn.close()
        except Exception:
            pass

    # Se ainda não detectou, verifica se alguma marca conhecida está na query
    if not detected_brand:
        for b_name, b_slug in BRAND_MAP.items():
            if re.search(rf'\b{re.escape(b_name)}\b', lower_query):
                detected_brand = b_slug
                break

    # Normalizar marca para o slug do Webmotors
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

def format_money(val):
    if val is None:
        return "Sob Consulta"
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def search_webmotors(query, brand=None, year=None, max_results=5):
    """
    Pesquisa ofertas no Webmotors usando Patchright.
    
    Args:
        query (str): Nome do modelo/versão, ex: "Gol Special 1.0 Total Flex 8V 5p (2015)"
        brand (str, opcional): Marca do veículo, ex: "VW - VolksWagen"
        year (int, opcional): Ano do modelo, ex: 2015
        max_results (int): Quantidade máxima de anúncios retornados (padrão: 5)
        
    Returns:
        list: Lista com até `max_results` dicionários contendo os dados dos veículos
    """
    if not query or not query.strip():
        return []

    parsed = parse_car_query(query, brand, year)
    brand_slug = parsed['brand_slug']
    model_slug = parsed['model_slug']
    target_year = parsed['year']
    clean_query = parsed['clean_query']

    # Monta URL do Webmotors
    if brand_slug and model_slug:
        if target_year and target_year != 32000:
            url = f"https://www.webmotors.com.br/carros/estoque/{brand_slug}/{model_slug}/de.{target_year}/ate.{target_year}"
        else:
            url = f"https://www.webmotors.com.br/carros/estoque/{brand_slug}/{model_slug}"
    elif model_slug:
        url = f"https://www.webmotors.com.br/carros/estoque?termo={urllib.parse.quote(model_slug)}"
    else:
        url = f"https://www.webmotors.com.br/carros/estoque?termo={urllib.parse.quote(clean_query)}"

    captured_items = []

    # Inicializa Patchright com janela posicionada fora da tela para discrição
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--window-position=3000,3000',
                '--window-size=1280,800',
                '--mute-audio',
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        page = browser.new_page()

        def on_response(res):
            if '/api/search/car' in res.url:
                try:
                    data = res.json()
                    items = data.get('SearchResults', [])
                    if items:
                        valid = [it for it in items if it.get('Specification', {}).get('Title')]
                        if valid:
                            captured_items.extend(valid)
                except Exception:
                    pass

        page.on('response', on_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3500)
        except Exception as e:
            print(f"[Webmotors] Aviso ao carregar página: {e}")
        finally:
            browser.close()

    # Deduplicação por UniqueId
    unique_items = {}
    for it in captured_items:
        uid = it.get('UniqueId')
        if uid and uid not in unique_items:
            unique_items[uid] = it

    items_list = list(unique_items.values())

    # Ranqueamento dos anúncios por relevância com as palavras da versão
    query_words = set(re.findall(r'\b\w+\b', clean_query.lower()))
    if model_slug:
        query_words.discard(model_slug.lower())
    if brand_slug:
        query_words.discard(brand_slug.lower())

    def score_item(it):
        spec = it.get('Specification', {})
        title = (spec.get('Title') or '').lower()
        version = (spec.get('Version', {}).get('Value') or '').lower()
        text = f"{title} {version}"

        score = 0
        for w in query_words:
            if w in text:
                if w in ['special', 'fire', 'comfortline', 'trendline', 'highline', 'tsi', 'gti', 'gts', 'lt', 'ltz', 'premier']:
                    score += 5
                elif re.match(r'^\d+(\.\d+)?$', w):
                    score += 3
                else:
                    score += 1
        return score

    ranked_items = sorted(items_list, key=score_item, reverse=True)

    results = []
    for it in ranked_items[:max_results]:
        spec = it.get('Specification', {})
        prices = it.get('Prices', {})
        seller = it.get('Seller', {})
        media = it.get('Media', {})

        uid = it.get('UniqueId')
        make_name = normalize_slug(spec.get('Make', {}).get('Value', brand_slug or 'carro'))
        model_name = normalize_slug(spec.get('Model', {}).get('Value', model_slug or 'modelo'))
        version_name = normalize_slug(spec.get('Version', {}).get('Value', 'versao'))
        doors = spec.get('NumberPorts', '4')
        year_fab = spec.get('YearFabrication', target_year or '')
        year_mod = int(spec.get('YearModel', target_year or 0)) if spec.get('YearModel') else ''

        # Link direto para o anúncio no Webmotors
        ad_url = f"https://www.webmotors.com.br/comprar/{make_name}/{model_name}/{version_name}/{doors}-portas/{year_fab}-{year_mod}/{uid}" if uid else ""

        # Foto do veículo
        photo_path = it.get('PhotoPath')
        if not photo_path and media.get('Photos'):
            photo_path = media['Photos'][0].get('PhotoPath')

        image_url = ""
        if photo_path:
            norm_photo = photo_path.replace('\\', '/')
            if not norm_photo.startswith('http'):
                image_url = f"https://image.webmotors.com.br/_fotos/anunciousados/gigante/{norm_photo}?s=fill&w=400&h=300&q=70&type=webp"
            else:
                image_url = norm_photo

        preco_num = prices.get('Price')
        km_num = spec.get('Odometer')

        results.append({
            'id': uid,
            'titulo': spec.get('Title'),
            'marca': spec.get('Make', {}).get('Value'),
            'modelo': spec.get('Model', {}).get('Value'),
            'versao': spec.get('Version', {}).get('Value'),
            'ano_fabricacao': year_fab,
            'ano_modelo': year_mod,
            'ano_formatado': f"{year_fab}/{year_mod}" if year_fab and year_mod else str(year_mod or year_fab),
            'preco': preco_num,
            'preco_formatado': format_money(preco_num),
            'km': km_num,
            'km_formatado': f"{int(km_num):,} km".replace(',', '.') if km_num is not None else "Não informado",
            'combustivel': spec.get('Fuel', 'Flex'),
            'cambio': spec.get('Transmission', 'Manual'),
            'cor': spec.get('Color', {}).get('Primary', 'Não informada'),
            'cidade': seller.get('City', ''),
            'estado': seller.get('State', ''),
            'localizacao': f"{seller.get('City', '')} - {seller.get('State', '')}".strip(" -"),
            'url': ad_url,
            'foto': image_url
        })

    return results

if __name__ == '__main__':
    import sys
    test_query = "Gol Special 1.0 Total Flex 8V 5p (2015)"
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])

    print(f"=== Buscando Webmotors: '{test_query}' ===")
    anuncios = search_webmotors(test_query, max_results=5)
    print(f"Encontrados: {len(anuncios)} anúncios\n")

    for idx, a in enumerate(anuncios, 1):
        print(f"[{idx}] {a['titulo']}")
        print(f"    Preço: {a['preco_formatado']} | Km: {a['km_formatado']} | Ano: {a['ano_formatado']}")
        print(f"    Local: {a['localizacao']} | Câmbio: {a['cambio']} | Cor: {a['cor']}")
        print(f"    Link : {a['url']}")
        print(f"    Foto : {a['foto'][:80]}..." if a['foto'] else "    Foto : Sem foto")
        print()
