import os
import re
import sys
import shutil
import subprocess
import time
import urllib.parse
import duckdb
from patchright.sync_api import sync_playwright

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fipe.duckdb')

_xvfb_process = None

def ensure_xvfb():
    """
    Garante que em servidores Linux sem display físico haja um display virtual (Xvfb) ativo,
    permitindo que o navegador seja iniciado em modo headed sem erro de XServer.
    """
    global _xvfb_process
    if not sys.platform.startswith('linux'):
        return

    if os.environ.get('DISPLAY'):
        return

    try:
        from pyvirtualdisplay import Display
        disp = Display(visible=0, size=(1280, 800))
        disp.start()
        print("[OLX] Display virtual iniciado com pyvirtualdisplay.")
        return
    except Exception:
        pass

    xvfb_bin = shutil.which('Xvfb')
    if not xvfb_bin:
        return

    if _xvfb_process and _xvfb_process.poll() is None:
        return

    try:
        display_num = 99
        while os.path.exists(f"/tmp/.X11-unix/X{display_num}") or os.path.exists(f"/tmp/.X{display_num}-lock"):
            display_num += 1
            if display_num > 130:
                break
        disp_str = f":{display_num}"
        _xvfb_process = subprocess.Popen(
            [xvfb_bin, disp_str, '-screen', '0', '1280x800x24', '-nolisten', 'tcp', '-ac'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        os.environ['DISPLAY'] = disp_str
        time.sleep(1)
        print(f"[OLX] Display virtual Xvfb iniciado automaticamente em {disp_str}")
    except Exception as e:
        print(f"[OLX] Erro ao iniciar Xvfb: {e}")

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

# Mapeamento completo dos DDDs do Brasil para UF e slug de região da OLX
DDD_MAP = {
    # São Paulo (SP)
    11: {'uf': 'sp', 'regiao': 'sao-paulo-e-regiao', 'nome_regiao': 'São Paulo e Região'},
    12: {'uf': 'sp', 'regiao': 'vale-do-paraiba-e-litoral-norte', 'nome_regiao': 'Vale do Paraíba e Litoral Norte'},
    13: {'uf': 'sp', 'regiao': 'baixada-santista-e-litoral-sul', 'nome_regiao': 'Baixada Santista e Litoral Sul'},
    14: {'uf': 'sp', 'regiao': 'regiao-de-bauru-e-marilia', 'nome_regiao': 'Região de Bauru e Marília'},
    15: {'uf': 'sp', 'regiao': 'regiao-de-sorocaba', 'nome_regiao': 'Região de Sorocaba'},
    16: {'uf': 'sp', 'regiao': 'regiao-de-ribeirao-preto', 'nome_regiao': 'Região de Ribeirão Preto'},
    17: {'uf': 'sp', 'regiao': 'regiao-de-sao-jose-do-rio-preto', 'nome_regiao': 'Região de São José do Rio Preto'},
    18: {'uf': 'sp', 'regiao': 'regiao-de-presidente-prudente', 'nome_regiao': 'Região de Presidente Prudente'},
    19: {'uf': 'sp', 'regiao': 'grande-campinas', 'nome_regiao': 'Grande Campinas e Região'},

    # Rio de Janeiro (RJ)
    21: {'uf': 'rj', 'regiao': 'rio-de-janeiro-e-regiao', 'nome_regiao': 'Rio de Janeiro e Região'},
    22: {'uf': 'rj', 'regiao': 'norte-do-estado-do-rio', 'nome_regiao': 'Norte do Estado do Rio'},
    24: {'uf': 'rj', 'regiao': 'serra-angra-dos-reis-e-regiao', 'nome_regiao': 'Serra, Angra dos Reis e Região'},

    # Espírito Santo (ES)
    27: {'uf': 'es', 'regiao': 'norte-do-espirito-santo', 'nome_regiao': 'Norte do Espírito Santo'},
    28: {'uf': 'es', 'regiao': 'sul-do-espirito-santo', 'nome_regiao': 'Sul do Espírito Santo'},

    # Minas Gerais (MG)
    31: {'uf': 'mg', 'regiao': 'belo-horizonte-e-regiao', 'nome_regiao': 'Belo Horizonte e Região'},
    32: {'uf': 'mg', 'regiao': 'juiz-de-fora-e-regiao', 'nome_regiao': 'Juiz de Fora e Região'},
    33: {'uf': 'mg', 'regiao': 'regiao-de-governador-valadares-e-teofilo-otoni', 'nome_regiao': 'Governador Valadares e Região'},
    34: {'uf': 'mg', 'regiao': 'triangulo-mineiro-e-alto-paranaiba', 'nome_regiao': 'Triângulo Mineiro e Alto Paranaíba'},
    35: {'uf': 'mg', 'regiao': 'sul-de-minas', 'nome_regiao': 'Sul de Minas'},
    37: {'uf': 'mg', 'regiao': 'regiao-de-divinopolis', 'nome_regiao': 'Região de Divinópolis'},
    38: {'uf': 'mg', 'regiao': 'regiao-de-montes-claros-e-diamantina', 'nome_regiao': 'Montes Claros e Diamantina'},

    # Paraná (PR)
    41: {'uf': 'pr', 'regiao': 'regiao-de-curitiba-e-paranagua', 'nome_regiao': 'Curitiba e Paranaguá'},
    42: {'uf': 'pr', 'regiao': 'regiao-de-ponta-grossa-e-guarapuava', 'nome_regiao': 'Ponta Grossa e Guarapuava'},
    43: {'uf': 'pr', 'regiao': 'regiao-de-londrina', 'nome_regiao': 'Região de Londrina'},
    44: {'uf': 'pr', 'regiao': 'regiao-de-maringa', 'nome_regiao': 'Região de Maringá'},
    45: {'uf': 'pr', 'regiao': 'regiao-de-foz-do-iguacu-e-cascavel', 'nome_regiao': 'Foz do Iguaçu e Cascavel'},
    46: {'uf': 'pr', 'regiao': 'regiao-de-francisco-beltrao-e-pato-branco', 'nome_regiao': 'Francisco Beltrão e Pato Branco'},

    # Santa Catarina (SC)
    47: {'uf': 'sc', 'regiao': 'norte-de-santa-catarina', 'nome_regiao': 'Norte de Santa Catarina'},
    48: {'uf': 'sc', 'regiao': 'florianopolis-e-regiao', 'nome_regiao': 'Florianópolis e Região'},
    49: {'uf': 'sc', 'regiao': 'oeste-de-santa-catarina', 'nome_regiao': 'Oeste de Santa Catarina'},

    # Rio Grande do Sul (RS)
    51: {'uf': 'rs', 'regiao': 'porto-alegre-e-regiao', 'nome_regiao': 'Porto Alegre e Região'},
    53: {'uf': 'rs', 'regiao': 'regiao-de-pelotas-e-rio-grande', 'nome_regiao': 'Pelotas e Rio Grande'},
    54: {'uf': 'rs', 'regiao': 'regiao-de-caxias-do-sul', 'nome_regiao': 'Região de Caxias do Sul'},
    55: {'uf': 'rs', 'regiao': 'regiao-de-santa-maria', 'nome_regiao': 'Região de Santa Maria'},

    # Distrito Federal / Goiás / Tocantins (DF/GO/TO)
    61: {'uf': 'df', 'regiao': 'distrito-federal-e-regiao', 'nome_regiao': 'Distrito Federal e Região'},
    62: {'uf': 'go', 'regiao': 'grande-goiania-e-anapolis', 'nome_regiao': 'Goiânia e Anápolis'},
    63: {'uf': 'to', 'regiao': 'tocantins', 'nome_regiao': 'Tocantins'},
    64: {'uf': 'go', 'regiao': 'rio-verde-caldas-novas-e-regiao', 'nome_regiao': 'Rio Verde e Caldas Novas'},

    # Mato Grosso / Mato Grosso do Sul (MT/MS)
    65: {'uf': 'mt', 'regiao': 'cuiaba-e-regiao', 'nome_regiao': 'Cuiabá e Região'},
    66: {'uf': 'mt', 'regiao': 'rondonopolis-sinop-e-regiao', 'nome_regiao': 'Rondonópolis e Sinop'},
    67: {'uf': 'ms', 'regiao': 'mato-grosso-do-sul', 'nome_regiao': 'Mato Grosso do Sul'},

    # Acre / Rondônia (AC/RO)
    68: {'uf': 'ac', 'regiao': 'acre', 'nome_regiao': 'Acre'},
    69: {'uf': 'ro', 'regiao': 'rondonia', 'nome_regiao': 'Rondônia'},

    # Bahia / Sergipe (BA/SE)
    71: {'uf': 'ba', 'regiao': 'grande-salvador', 'nome_regiao': 'Grande Salvador'},
    73: {'uf': 'ba', 'regiao': 'sul-da-bahia', 'nome_regiao': 'Sul da Bahia'},
    74: {'uf': 'ba', 'regiao': 'juazeiro-jacobina-e-regiao', 'nome_regiao': 'Juazeiro e Jacobina'},
    75: {'uf': 'ba', 'regiao': 'feira-de-santana-alagoinhas-e-regiao', 'nome_regiao': 'Feira de Santana e Região'},
    77: {'uf': 'ba', 'regiao': 'vitoria-da-conquista-barreiras-e-regiao', 'nome_regiao': 'Vitória da Conquista e Barreiras'},
    79: {'uf': 'se', 'regiao': 'sergipe', 'nome_regiao': 'Sergipe'},

    # Pernambuco / Alagoas / Paraíba / Rio Grande do Norte (PE/AL/PB/RN)
    81: {'uf': 'pe', 'regiao': 'grande-recife', 'nome_regiao': 'Grande Recife'},
    82: {'uf': 'al', 'regiao': 'alagoas', 'nome_regiao': 'Alagoas'},
    83: {'uf': 'pb', 'regiao': 'paraiba', 'nome_regiao': 'Paraíba'},
    84: {'uf': 'rn', 'regiao': 'rio-grande-do-norte', 'nome_regiao': 'Rio Grande do Norte'},
    87: {'uf': 'pe', 'regiao': 'petrolina-garanhuns-e-regiao', 'nome_regiao': 'Petrolina e Garanhuns'},

    # Ceará / Piauí (CE/PI)
    85: {'uf': 'ce', 'regiao': 'fortaleza-e-regiao', 'nome_regiao': 'Fortaleza e Região'},
    86: {'uf': 'pi', 'regiao': 'piaui', 'nome_regiao': 'Piauí'},
    88: {'uf': 'ce', 'regiao': 'juazeiro-do-norte-sobral-e-regiao', 'nome_regiao': 'Juazeiro do Norte e Sobral'},
    89: {'uf': 'pi', 'regiao': 'sul-do-piaui', 'nome_regiao': 'Sul do Piauí'},

    # Pará / Amazonas / Roraima / Amapá / Maranhão (PA/AM/RR/AP/MA)
    91: {'uf': 'pa', 'regiao': 'regiao-de-belem', 'nome_regiao': 'Região de Belém'},
    92: {'uf': 'am', 'regiao': 'regiao-de-manaus', 'nome_regiao': 'Região de Manaus'},
    93: {'uf': 'pa', 'regiao': 'regiao-de-santarem', 'nome_regiao': 'Região de Santarém'},
    94: {'uf': 'pa', 'regiao': 'regiao-de-maraba', 'nome_regiao': 'Região de Marabá'},
    95: {'uf': 'rr', 'regiao': 'roraima', 'nome_regiao': 'Roraima'},
    96: {'uf': 'ap', 'regiao': 'amapa', 'nome_regiao': 'Amapá'},
    97: {'uf': 'am', 'regiao': 'amazonas', 'nome_regiao': 'Amazonas'},
    98: {'uf': 'ma', 'regiao': 'regiao-de-sao-luis', 'nome_regiao': 'São Luís e Região'},
    99: {'uf': 'ma', 'regiao': 'regiao-de-imperatriz-e-caxias', 'nome_regiao': 'Imperatriz e Caxias'}
}

UF_VALIDAS = {
    'ac', 'al', 'ap', 'am', 'ba', 'ce', 'df', 'es', 'go', 'ma',
    'mt', 'ms', 'mg', 'pa', 'pb', 'pr', 'pe', 'pi', 'rj', 'rn',
    'rs', 'ro', 'rr', 'sc', 'sp', 'se', 'to'
}

def format_money(val):
    if val is None:
        return "Sob Consulta"
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def parse_car_query(query, brand=None, year=None):
    """
    Limpa e extrai marca, modelo, ano e versão da query FIPE/usuário.
    """
    clean_query = query.strip()
    extracted_year = year

    # 1. Extração de ano entre parênteses ou 4 dígitos
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

    # 2. Remove ruídos técnicos de versão que atrapalham busca de texto amplo
    # Mantém nomes de modelo e versão relevantes (ex: Gol Special, Corolla XEi, Renegade Longitude)
    search_terms = clean_query
    # Remove padrões como '1.0 Total Flex 8V 5p' mantendo o essencial se a query for muito longa
    words = search_terms.split()
    if len(words) > 4:
        # Pega as 3 primeiras palavras (ex: 'Gol Special')
        simplified = []
        for w in words:
            if re.match(r'^\d+p$', w.lower()) or w.lower() in ['8v', '16v', 'total', 'flex', 'manual', 'mec.', 'mec', 'aut.', 'aut']:
                continue
            simplified.append(w)
        if simplified:
            search_terms = " ".join(simplified[:3])

    return {
        'brand': brand,
        'year': extracted_year,
        'clean_query': clean_query,
        'search_terms': search_terms
    }

REGION_SYNONYMS = {
    'campinas': 'grande-campinas',
    'regiao-de-campinas': 'grande-campinas',
    'grande-campinas': 'grande-campinas',
    'sao-paulo': 'sao-paulo-e-regiao',
    'rio-de-janeiro': 'rio-de-janeiro-e-regiao',
    'belo-horizonte': 'belo-horizonte-e-regiao',
    'salvador': 'grande-salvador',
    'recife': 'grande-recife',
    'curitiba': 'regiao-de-curitiba-e-paranagua',
    'porto-alegre': 'porto-alegre-e-regiao',
    'florianopolis': 'florianopolis-e-regiao',
    'goiania': 'grande-goiania-e-anapolis',
    'brasilia': 'distrito-federal-e-regiao',
}

def build_olx_url(query_text, year=None, ddd=None, estado=None, regiao=None, municipio=None, preco_min=None, preco_max=None):
    """
    Constrói a URL da OLX com base nos filtros geográficos e de valores.
    """
    uf = (estado or '').strip().lower()
    if uf and uf not in UF_VALIDAS:
        uf = ''

    reg_slug = normalize_slug(regiao)
    if reg_slug in REGION_SYNONYMS:
        reg_slug = REGION_SYNONYMS[reg_slug]

    mun_slug = normalize_slug(municipio)

    # Aplica mapeamento de DDD caso fornecido
    if ddd:
        try:
            ddd_int = int(re.sub(r'[^\d]', '', str(ddd)))
            if ddd_int in DDD_MAP:
                info = DDD_MAP[ddd_int]
                if not uf:
                    uf = info['uf']
                if not reg_slug:
                    reg_slug = info['regiao']
        except Exception:
            pass

    if reg_slug in REGION_SYNONYMS:
        reg_slug = REGION_SYNONYMS[reg_slug]

    # Monta estrutura de caminhos da OLX
    path_parts = ["https://www.olx.com.br", "autos-e-pecas", "carros-vans-e-utilitarios"]
    if uf:
        path_parts.append(f"estado-{uf}")
        if reg_slug:
            path_parts.append(reg_slug)

    base_url = "/".join(path_parts)

    params = {}
    if query_text:
        params['q'] = query_text.strip()
    if year and str(year) != '32000':
        params['rs'] = str(year)
        params['re'] = str(year)
    if preco_min:
        try:
            params['ps'] = str(int(float(preco_min)))
        except Exception:
            pass
    if preco_max:
        try:
            params['pe'] = str(int(float(preco_max)))
        except Exception:
            pass

    if params:
        return f"{base_url}?{urllib.parse.urlencode(params)}"
    return base_url

def parse_card_data(raw, default_uf=None):
    """
    Trata os dados brutos de um card da OLX e retorna um dicionário estruturado.
    """
    title = (raw.get('title') or '').strip()
    url = (raw.get('url') or '').strip()
    price_text = (raw.get('priceText') or '').strip()
    loc_text = (raw.get('locationText') or '').strip()
    date_text = (raw.get('dateText') or '').strip()
    image_url = (raw.get('imageUrl') or '').strip()
    details = raw.get('details') or []

    # 1. ID do anúncio a partir da URL
    ad_id = None
    id_match = re.search(r'-(\d{7,13})(?:\?|$)', url)
    if id_match:
        ad_id = id_match.group(1)

    # 2. Preço
    clean_price = re.sub(r'[^\d]', '', price_text)
    preco_num = float(clean_price) if clean_price else None
    preco_formatado = format_money(preco_num) if preco_num is not None else (price_text or "Sob Consulta")

    # 3. Localização (cidade, bairro, estado e região)
    cidade = ''
    bairro = ''
    if loc_text:
        parts = [p.strip() for p in loc_text.split(',', 1)]
        cidade = parts[0]
        if len(parts) > 1:
            bairro = parts[1]

    estado = default_uf or ''
    regiao = ''
    uf_match = re.search(r'https?://([a-z]{2})\.olx\.com\.br/([^/]+)/', url)
    if uf_match:
        estado = uf_match.group(1).upper()
        regiao = uf_match.group(2).replace('-', ' ').title()
    else:
        uf_match2 = re.search(r'/estado-([a-z]{2})/?([^/?]+)?', url)
        if uf_match2:
            estado = uf_match2.group(1).upper()
            if uf_match2.group(2):
                regiao = uf_match2.group(2).replace('-', ' ').title()

    localizacao_formatada = cidade
    if bairro:
        localizacao_formatada += f", {bairro}"
    if estado:
        localizacao_formatada += f" - {estado}"

    # 4. Detalhes do veículo (km, ano, cor, motor, câmbio, combustível, carroceria)
    km_num = None
    km_formatado = "Não informado"
    cor = "Não informada"
    motor = ""
    carroceria = ""
    ano_modelo = None

    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
    if year_match:
        ano_modelo = int(year_match.group(1))

    for d in details:
        d_lower = d.lower()
        if 'km' in d_lower or 'quilômetro' in d_lower:
            km_digits = re.sub(r'[^\d]', '', d)
            if km_digits:
                km_num = int(km_digits)
                km_formatado = f"{km_num:,} km".replace(',', '.')
        elif 'cor ' in d_lower or d_lower in ['branco', 'preto', 'prata', 'cinza', 'vermelho', 'azul', 'verde', 'amarelo', 'bege', 'marrom', 'dourado', 'laranja']:
            cor = d.replace('Cor ', '').strip().title()
        elif re.match(r'^\d\.\d$', d):
            motor = d
        elif d_lower in ['hatch', 'sedã', 'seda', 'suv', 'picape', 'pick-up', 'van', 'utilitário', 'conversível', 'cupe', 'perua']:
            carroceria = d.title()

    cambio = "Manual"
    if re.search(r'\b(autom[aá]tico|auto|at|i-motion|imotion|cvt|dsg|tiptronic)\b', title.lower()):
        cambio = "Automático" if 'auto' in title.lower() else "Automatizado"

    combustivel = "Flex"
    if 'diesel' in title.lower():
        combustivel = "Diesel"
    elif 'gasolina' in title.lower():
        combustivel = "Gasolina"
    elif 'híbrido' in title.lower() or 'hibrido' in title.lower():
        combustivel = "Híbrido"
    elif 'elétrico' in title.lower() or 'eletrico' in title.lower():
        combustivel = "Elétrico"

    return {
        'id': ad_id,
        'titulo': title,
        'preco': preco_num,
        'preco_formatado': preco_formatado,
        'km': km_num,
        'km_formatado': km_formatado,
        'ano': ano_modelo,
        'ano_formatado': str(ano_modelo) if ano_modelo else "Não informado",
        'combustivel': combustivel,
        'cambio': cambio,
        'cor': cor,
        'motor': motor,
        'carroceria': carroceria,
        'cidade': cidade,
        'bairro': bairro,
        'estado': estado,
        'regiao': regiao,
        'localizacao': localizacao_formatada.strip(" -,"),
        'data_publicacao': date_text,
        'url': url,
        'foto': image_url
    }

def search_olx(query, brand=None, year=None, ddd=None, estado=None, regiao=None, municipio=None, preco_min=None, preco_max=None, max_results=15):
    """
    Pesquisa ofertas de veículos na OLX com filtros avançados usando Patchright.

    Args:
        query (str): Nome do modelo/versão, ex: "Gol Special 1.0 Total Flex 8V 5p (2015)"
        brand (str, opcional): Marca do veículo
        year (int, opcional): Ano do veículo
        ddd (int/str, opcional): DDD regional (ex: 11, 19, 21, 31)
        estado (str, opcional): Sigla da UF (ex: 'SP', 'RJ', 'MG')
        regiao (str, opcional): Nome ou slug da região (ex: 'regiao-de-campinas')
        municipio (str, opcional): Nome do município (ex: 'Campinas')
        preco_min (float/int, opcional): Preço mínimo desejado
        preco_max (float/int, opcional): Preço máximo desejado
        max_results (int): Quantidade máxima de anúncios retornados (padrão: 15)

    Returns:
        list: Lista com até `max_results` dicionários contendo os dados dos anúncios
    """
    if not query or not str(query).strip():
        return []

    parsed = parse_car_query(query, brand=brand, year=year)
    search_text = parsed['search_terms']
    target_year = parsed['year']

    # Monta URL com os filtros
    url = build_olx_url(
        query_text=search_text,
        year=target_year,
        ddd=ddd,
        estado=estado,
        regiao=regiao,
        municipio=municipio,
        preco_min=preco_min,
        preco_max=preco_max
    )

    ensure_xvfb()
    has_display = bool(os.environ.get('DISPLAY')) or (sys.platform in ('win32', 'darwin'))

    raw_items = []
    blocked_by_cf = False

    with sync_playwright() as p:
        browser = None
        if has_display:
            try:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        '--window-position=3000,3000',
                        '--window-size=1280,800',
                        '--mute-audio',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-blink-features=AutomationControlled'
                    ]
                )
            except Exception as e:
                print(f"[OLX] Falha ao iniciar modo headed: {e}")
                browser = None

        if not browser:
            try:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--window-size=1280,800',
                        '--disable-blink-features=AutomationControlled'
                    ]
                )
            except Exception as e:
                raise RuntimeError(
                    f"Falha ao iniciar navegador para OLX: {e}. "
                    "Para servidores Linux sem interface gráfica, instale o Xvfb: 'sudo apt-get install -y xvfb' "
                    "ou execute a aplicação com: 'xvfb-run -a python app.py'."
                )

        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500)

            title = page.title()
            if "Attention Required" in title or "Cloudflare" in title:
                blocked_by_cf = True

            # Faz rolagens suaves para renderizar itens virtuais/lazy loading
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(500)

            raw_items = page.evaluate("""() => {
                const cards = Array.from(document.querySelectorAll('section.olx-adcard'));
                const results = [];

                for (const card of cards) {
                    const linkEl = card.querySelector('a.olx-adcard__link, a[data-testid="adcard-link"]');
                    if (!linkEl) continue;

                    const titleEl = card.querySelector('.olx-adcard__title, h2');
                    const priceEl = card.querySelector('.olx-adcard__price, h3');
                    const locationEl = card.querySelector('.olx-adcard__location');
                    const dateEl = card.querySelector('.olx-adcard__date');

                    let imgUrl = '';
                    const imgEl = card.querySelector('picture img, img');
                    if (imgEl) {
                        imgUrl = imgEl.src || imgEl.getAttribute('data-src') || '';
                    }

                    const details = Array.from(card.querySelectorAll('.olx-adcard__detail')).map(d => {
                        return d.innerText.trim() || d.getAttribute('aria-label') || '';
                    }).filter(Boolean);

                    const title = titleEl ? titleEl.innerText.trim() : (linkEl.getAttribute('title') || '');
                    const price = priceEl ? priceEl.innerText.trim() : '';

                    if (title || price) {
                        results.push({
                            title: title,
                            url: linkEl.href,
                            priceText: price,
                            locationText: locationEl ? locationEl.innerText.trim() : '',
                            dateText: dateEl ? dateEl.innerText.trim() : '',
                            imageUrl: imgUrl,
                            details: details
                        });
                    }
                }
                return results;
            }""")
        except Exception as e:
            print(f"[OLX] Aviso durante extração: {e}")
        finally:
            browser.close()

    if not raw_items and blocked_by_cf:
        raise RuntimeError(
            "A OLX bloqueou a consulta em modo headless (Cloudflare). "
            "Certifique-se de que o Xvfb esteja instalado caso execute em servidor Linux sem display."
        )

    # Processamento e normalização
    parsed_items = []
    seen_ids = set()
    default_uf = estado.upper() if estado else (DDD_MAP.get(int(ddd), {}).get('uf', '').upper() if ddd and str(ddd).isdigit() and int(ddd) in DDD_MAP else None)

    for r in raw_items:
        raw_url = (r.get('url') or '')
        # Ignora blocos de recomendação / fallback da OLX quando não há resultado
        if 'rec_detail_location' in raw_url or 'listing_no_result' in raw_url or 'gallery_id=recents' in raw_url:
            continue

        it = parse_card_data(r, default_uf=default_uf)
        if not it['titulo'] and not it['preco']:
            continue
        uid = it['id'] or it['url']
        if uid in seen_ids:
            continue
        seen_ids.add(uid)

        # Filtros de segurança pós-captura
        if preco_min is not None and it['preco'] is not None and it['preco'] < float(preco_min):
            continue
        if preco_max is not None and it['preco'] is not None and it['preco'] > float(preco_max):
            continue

        parsed_items.append(it)

    # Se município foi especificado, tenta filtrar apenas anúncios do município
    if mun_lower := (municipio or '').lower().strip():
        matched_mun = [
            it for it in parsed_items 
            if mun_lower in it['cidade'].lower() or mun_lower in it['localizacao'].lower()
        ]
        if matched_mun:
            parsed_items = matched_mun

    # Ranqueamento dos anúncios por relevância
    query_words = set(re.findall(r'\b\w+\b', parsed['clean_query'].lower()))
    mun_lower = municipio.lower().strip() if municipio else ""
    target_uf = (default_uf or '').upper()

    def score_item(it):
        score = 0
        text = f"{it['titulo']} {it['cidade']} {it['bairro']} {it['cor']}".lower()

        # Correspondência de palavras da versão/modelo
        for w in query_words:
            if w in text:
                if re.match(r'^\d+(\.\d+)?$', w):
                    score += 4
                elif w in ['special', 'fire', 'comfortline', 'trendline', 'highline', 'tsi', 'gti', 'gts', 'lt', 'ltz', 'premier']:
                    score += 6
                else:
                    score += 2

        # Bônus para correspondência com estado e região solicitados
        if target_uf and it.get('estado') == target_uf:
            score += 25
        if mun_lower and mun_lower in it['cidade'].lower():
            score += 30

        # Bônus se possuir imagem e preço
        if it['foto']:
            score += 2
        if it['preco']:
            score += 2

        return score

    ranked_items = sorted(parsed_items, key=score_item, reverse=True)
    return ranked_items[:max_results]

if __name__ == '__main__':
    test_query = "Gol Special 1.0 Total Flex 8V 5p (2015)"
    test_ddd = 19
    test_min = 20000
    test_max = 50000

    if len(sys.argv) > 1:
        test_query = sys.argv[1]

    print(f"=== Buscando OLX: '{test_query}' (DDD: {test_ddd}, Min: {test_min}, Max: {test_max}) ===")
    anuncios = search_olx(test_query, ddd=test_ddd, preco_min=test_min, preco_max=test_max, max_results=15)
    print(f"Total encontrados: {len(anuncios)} anúncios\n")

    for idx, a in enumerate(anuncios, 1):
        print(f"[{idx:02d}] {a['titulo']}")
        print(f"     Preço: {a['preco_formatado']} | Km: {a['km_formatado']} | Ano: {a['ano_formatado']}")
        print(f"     Local: {a['localizacao']} | Câmbio: {a['cambio']} | Cor: {a['cor']} | Motor: {a['motor']}")
        print(f"     Data : {a['data_publicacao']} | Foto: {a['foto'][:70]}..." if a['foto'] else "     Sem foto")
        print(f"     Link : {a['url']}")
        print()
