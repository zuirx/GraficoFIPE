import time
import datetime
import requests

# Tabela oficial e consolidada das alíquotas de IPVA para automóveis de passeio (gasolina/flex),
# taxas anuais de licenciamento (Detran/SEFAZ) e regras de isenção por tempo de fabricação nos 27 estados.
ESTADOS_IPVA = {
    'AC': {
        'nome': 'Acre',
        'aliquota': 2.0,
        'isencao_anos': 20,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 114.80,
        'observacoes': 'Alíquota de 2% para automóveis de passeio. Desconto de 10% para pagamento em cota única.'
    },
    'AL': {
        'nome': 'Alagoas',
        'aliquota': 3.0,
        'isencao_anos': 20,
        'desconto_avista': 5.0,
        'max_parcelas': 6,
        'taxa_licenciamento': 120.50,
        'observacoes': 'Alíquota de 3% para automóveis até 160cv (acima pode chegar a 3,25%). Isenção aos 20 anos.'
    },
    'AP': {
        'nome': 'Amapá',
        'aliquota': 3.0,
        'isencao_anos': 10,
        'desconto_avista': 20.0,
        'max_parcelas': 6,
        'taxa_licenciamento': 110.00,
        'observacoes': 'Uma das regras de isenção mais rápidas do país: veículos com mais de 10 anos não pagam.'
    },
    'AM': {
        'nome': 'Amazonas',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 122.88,
        'observacoes': 'Alíquota padrão de 3% (2% para carros de até 1000cc). Isenção aos 15 anos.'
    },
    'BA': {
        'nome': 'Bahia',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 8.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 165.35,
        'observacoes': 'Alíquota padrão de 3% para carros de passeio. Isenção após 15 anos de fabricação. Parcelamento em até 5 parcelas.'
    },
    'CE': {
        'nome': 'Ceará',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 5.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 173.40,
        'observacoes': 'Alíquota média de 3% para automóveis flex/gasolina. Isenção com 15 anos.'
    },
    'DF': {
        'nome': 'Distrito Federal',
        'aliquota': 3.5,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 6,
        'taxa_licenciamento': 95.00,
        'observacoes': 'Alíquota de 3,5% para carros de passeio. Isenção para veículos com 15 anos ou mais. Parcelamento em até 6 vezes.'
    },
    'ES': {
        'nome': 'Espírito Santo',
        'aliquota': 2.0,
        'isencao_anos': 15,
        'desconto_avista': 5.0,
        'max_parcelas': 6,
        'taxa_licenciamento': 178.50,
        'observacoes': 'Uma das menores alíquotas do Brasil (2%). Isenção para veículos fabricados há mais de 15 anos.'
    },
    'GO': {
        'nome': 'Goiás',
        'aliquota': 3.75,
        'isencao_anos': 15,
        'desconto_avista': 7.0,
        'max_parcelas': 10,
        'taxa_licenciamento': 195.00,
        'observacoes': 'Alíquota de 3,75% (3% para carros 1.0). Isenção a partir de 15 anos. Permite parcelamento em até 10 parcelas.'
    },
    'MA': {
        'nome': 'Maranhão',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 157.33,
        'observacoes': 'Alíquota de 3% (2,5% para até 100cv). Isenção após 15 anos de fabricação.'
    },
    'MT': {
        'nome': 'Mato Grosso',
        'aliquota': 3.0,
        'isencao_anos': 18,
        'desconto_avista': 5.0,
        'max_parcelas': 8,
        'taxa_licenciamento': 140.00,
        'observacoes': 'Alíquota padrão de 3% (podendo ir a 4% acima de 150cv). Isenção aos 18 anos.'
    },
    'MS': {
        'nome': 'Mato Grosso do Sul',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 15.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 215.76,
        'observacoes': 'Alíquota com benefício fiscal fixada em 3% para veículos de passeio. Isenção aos 15 anos.'
    },
    'MG': {
        'nome': 'Minas Gerais',
        'aliquota': 4.0,
        'isencao_anos': 30,
        'desconto_avista': 3.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 39.36,
        'observacoes': 'Alíquota de 4,0%. Isenção por idade restrita a veículos com 30+ anos. A taxa de licenciamento (TRLAV) é uma das menores do país.'
    },
    'PA': {
        'nome': 'Pará',
        'aliquota': 2.5,
        'isencao_anos': 15,
        'desconto_avista': 15.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 300.93,
        'observacoes': 'Alíquota de 2,5% para veículos de passeio. Isenção para mais de 15 anos de fabricação. Taxa fixada em 60 UPFs.'
    },
    'PB': {
        'nome': 'Paraíba',
        'aliquota': 2.5,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 222.39,
        'observacoes': 'Alíquota de 2,5% para carros de passeio. Isenção a partir de 15 anos. Taxa de 3 UFR-PB.'
    },
    'PR': {
        'nome': 'Paraná',
        'aliquota': 3.5,
        'isencao_anos': 20,
        'desconto_avista': 6.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 90.94,
        'observacoes': 'Alíquota de 3,5% para automóveis. Isenção aos 20 anos de fabricação. Parcelamento oficial em até 5 cotas.'
    },
    'PE': {
        'nome': 'Pernambuco',
        'aliquota': 2.4,
        'isencao_anos': 20,
        'desconto_avista': 7.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 128.40,
        'observacoes': 'Alíquota unificada de 2,4% (Lei 18.305/2023), uma das menores do Nordeste. Isenção aos 20 anos.'
    },
    'PI': {
        'nome': 'Piauí',
        'aliquota': 2.5,
        'isencao_anos': 15,
        'desconto_avista': 15.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 145.00,
        'observacoes': 'Alíquota de 2,5% para veículos até R$ 150 mil (3% acima). Isenção aos 15 anos.'
    },
    'RJ': {
        'nome': 'Rio de Janeiro',
        'aliquota': 4.0,
        'isencao_anos': 15,
        'desconto_avista': 3.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 268.65,
        'observacoes': 'Alíquota de 4,0% para automóveis flex/gasolina. Isenção aos 15 anos de fabricação. Taxa inclui emissão de CRLV digital e guia GRT.'
    },
    'RN': {
        'nome': 'Rio Grande do Norte',
        'aliquota': 3.0,
        'isencao_anos': 10,
        'desconto_avista': 5.0,
        'max_parcelas': 7,
        'taxa_licenciamento': 90.00,
        'observacoes': 'Alíquota de 3,0%. Isenção aos 10 anos de fabricação.'
    },
    'RS': {
        'nome': 'Rio Grande do Sul',
        'aliquota': 3.0,
        'isencao_anos': 20,
        'desconto_avista': 6.0,
        'max_parcelas': 6,
        'taxa_licenciamento': 114.13,
        'observacoes': 'Alíquota de 3,0% para automóveis. Isenção com 20 anos ou mais. Permite parcelamento em até 6x (Janeiro a Junho).'
    },
    'RO': {
        'nome': 'Rondônia',
        'aliquota': 3.0,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 180.00,
        'observacoes': 'Alíquota de 3% para automóveis de passeio. Isenção com 15 anos.'
    },
    'RR': {
        'nome': 'Roraima',
        'aliquota': 3.0,
        'isencao_anos': 10,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 98.50,
        'observacoes': 'Alíquota de 3,0%. Isenção a partir de 10 anos de fabricação.'
    },
    'SC': {
        'nome': 'Santa Catarina',
        'aliquota': 2.0,
        'isencao_anos': 30,
        'desconto_avista': 0.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 149.37,
        'observacoes': 'Menor alíquota do país (2,0% unificada para carros de passeio). Isenção a partir de 30 anos.'
    },
    'SP': {
        'nome': 'São Paulo',
        'aliquota': 4.0,
        'isencao_anos': 20,
        'desconto_avista': 3.0,
        'max_parcelas': 5,
        'taxa_licenciamento': 160.22,
        'observacoes': 'Alíquota de 4,0% para veículos a gasolina e flex. Isenção para veículos com mais de 20 anos. Parcelamento oficial em até 5x (Janeiro a Maio) ou 3x.'
    },
    'SE': {
        'nome': 'Sergipe',
        'aliquota': 2.5,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 3,
        'taxa_licenciamento': 150.00,
        'observacoes': 'Alíquota de 2,5% para carros de passeio (3% para veículos acima de 120 mil). Isenção aos 15 anos.'
    },
    'TO': {
        'nome': 'Tocantins',
        'aliquota': 2.0,
        'isencao_anos': 15,
        'desconto_avista': 10.0,
        'max_parcelas': 4,
        'taxa_licenciamento': 120.00,
        'observacoes': 'Alíquota de 2% para automóveis de passeio. Isenção aos 15 anos de fabricação.'
    }
}

# Cache simples em memória para geolocalização de IP (ip -> (uf, timestamp))
_GEO_CACHE = {}
_CACHE_TTL = 86400  # 24 horas

def obter_uf_por_ip(client_ip=None):
    """
    Detecta a UF brasileira do usuário baseando-se no endereço IP.
    Suporta IPs locais/privados realizando fallback para o IP público de saída.
    """
    now = time.time()
    clean_ip = (client_ip or '').strip()

    # Verifica cache
    if clean_ip and clean_ip in _GEO_CACHE:
        cached_uf, ts = _GEO_CACHE[clean_ip]
        if now - ts < _CACHE_TTL:
            return cached_uf

    is_local = (
        not clean_ip or
        clean_ip in ('127.0.0.1', '::1', 'localhost') or
        clean_ip.startswith('192.168.') or
        clean_ip.startswith('10.') or
        clean_ip.startswith('172.16.') or clean_ip.startswith('172.31.')
    )

    detected_uf = None

    # 1ª Tentativa: ipapi.co
    try:
        url = 'https://ipapi.co/json/' if is_local else f'https://ipapi.co/{clean_ip}/json/'
        headers = {'User-Agent': 'FipeData/2.0 (IPVA GeoResolver)'}
        res = requests.get(url, headers=headers, timeout=2.5)
        if res.status_code == 200:
            data = res.json()
            code = (data.get('region_code') or '').upper()
            if code in ESTADOS_IPVA:
                detected_uf = code
    except Exception:
        pass

    # 2ª Tentativa: ipwhois.app como fallback
    if not detected_uf:
        try:
            url = 'https://ipwhois.app/json/' if is_local else f'https://ipwhois.app/json/{clean_ip}'
            res = requests.get(url, timeout=2.5)
            if res.status_code == 200:
                data = res.json()
                code = (data.get('region_code') or '').upper()
                if code in ESTADOS_IPVA:
                    detected_uf = code
                else:
                    region_name = (data.get('region') or '').lower()
                    for uf_key, info in ESTADOS_IPVA.items():
                        if info['nome'].lower() in region_name:
                            detected_uf = uf_key
                            break
        except Exception:
            pass

    # Fallback padrão caso a detecção não tenha retornado uma UF válida
    final_uf = detected_uf if detected_uf in ESTADOS_IPVA else 'SP'

    if clean_ip:
        _GEO_CACHE[clean_ip] = (final_uf, now)

    return final_uf

def format_money(val):
    if val is None:
        return "R$ 0,00"
    return f"R$ {val:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def calcular_cronograma_parcelas(valor_total, num_parcelas, mes_inicio='Janeiro'):
    """
    Gera a lista discriminada de cada parcela com centavos ajustados na última parcela.
    """
    if valor_total <= 0 or num_parcelas <= 1:
        return []

    meses_ano = [
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    ]

    idx_inicio = 0
    if mes_inicio in meses_ano:
        idx_inicio = meses_ano.index(mes_inicio)

    valor_parcela_base = round(valor_total / num_parcelas, 2)
    soma_anteriores = round(valor_parcela_base * (num_parcelas - 1), 2)
    valor_ultima = round(valor_total - soma_anteriores, 2)

    parcelas = []
    for i in range(1, num_parcelas + 1):
        v = valor_ultima if i == num_parcelas else valor_parcela_base
        mes_nome = meses_ano[(idx_inicio + i - 1) % len(meses_ano)]
        parcelas.append({
            'numero': i,
            'titulo': f"{i}ª Parcela",
            'mes': mes_nome,
            'valor': v,
            'valor_formatado': format_money(v)
        })
    return parcelas

def calcular_ipva(valor_fipe, ano_modelo=None, uf='SP', ano_referencia=None):
    """
    Calcula o valor do IPVA com base no valor de tabela FIPE, ano do modelo e UF.
    Verifica automaticamente se o veículo se enquadra na regra de isenção por idade.
    Calcula planos de parcelamento discriminados (ex: 3x padrão e limite estadual)
    e inclui taxa atualizada de licenciamento do DETRAN estadual.
    """
    uf_upper = (uf or 'SP').strip().upper()
    info = ESTADOS_IPVA.get(uf_upper, ESTADOS_IPVA['SP'])

    if not ano_referencia:
        ano_referencia = datetime.date.today().year

    aliquota = info['aliquota']
    isencao_anos = info['isencao_anos']
    desconto_avista = info['desconto_avista']
    max_parcelas = info['max_parcelas']
    taxa_licenciamento = float(info.get('taxa_licenciamento', 160.00))

    valor_base = float(valor_fipe or 0.0)

    # Identifica idade do veículo
    idade = None
    isento = False
    motivo_isencao = ""

    if ano_modelo and str(ano_modelo).isdigit():
        ano_int = int(ano_modelo)
        if ano_int == 32000:
            idade = 0
        else:
            idade = max(0, ano_referencia - ano_int)
            if idade >= isencao_anos:
                isento = True
                motivo_isencao = (
                    f"Veículo com {idade} anos de fabricação isento de IPVA em {info['nome']} "
                    f"(regra de isenção para veículos a partir de {isencao_anos} anos)."
                )

    if isento:
        valor_ipva = 0.0
        valor_avista = 0.0
        valor_parcela = 0.0
        planos_parcelamento = []
        custo_total_avista = taxa_licenciamento
        custo_total_parcelado = taxa_licenciamento
    else:
        valor_ipva = round(valor_base * (aliquota / 100.0), 2)
        valor_avista = round(valor_ipva * (1.0 - (desconto_avista / 100.0)), 2) if desconto_avista > 0 else valor_ipva
        valor_parcela = round(valor_ipva / max_parcelas, 2) if max_parcelas > 1 else valor_ipva

        # Planos de parcelamento discriminados
        planos_parcelamento = []
        
        # 1. Opção padrão de 3 parcelas (tradicionalmente presente na maioria dos estados)
        if max_parcelas >= 3:
            cronograma_3x = calcular_cronograma_parcelas(valor_ipva, 3, mes_inicio='Janeiro')
            planos_parcelamento.append({
                'num_parcelas': 3,
                'nome': 'Em 3x (Padrão)',
                'descricao': '3 parcelas mensais sem juros',
                'valor_parcela': round(valor_ipva / 3, 2),
                'valor_parcela_formatado': format_money(round(valor_ipva / 3, 2)),
                'cronograma': cronograma_3x
            })

        # 2. Opção máxima do estado caso seja diferente de 3 (ex: 5x em SP/PR, 6x em RS/DF, 10x em GO)
        if max_parcelas != 3 and max_parcelas > 1:
            cronograma_max = calcular_cronograma_parcelas(valor_ipva, max_parcelas, mes_inicio='Janeiro')
            planos_parcelamento.append({
                'num_parcelas': max_parcelas,
                'nome': f'Em {max_parcelas}x (Máximo Estadual)',
                'descricao': f'{max_parcelas} parcelas mensais sem juros',
                'valor_parcela': round(valor_ipva / max_parcelas, 2),
                'valor_parcela_formatado': format_money(round(valor_ipva / max_parcelas, 2)),
                'cronograma': cronograma_max
            })
        elif max_parcelas == 2:
            cronograma_2x = calcular_cronograma_parcelas(valor_ipva, 2, mes_inicio='Janeiro')
            planos_parcelamento.append({
                'num_parcelas': 2,
                'nome': 'Em 2x',
                'descricao': '2 parcelas mensais sem juros',
                'valor_parcela': round(valor_ipva / 2, 2),
                'valor_parcela_formatado': format_money(round(valor_ipva / 2, 2)),
                'cronograma': cronograma_2x
            })

        custo_total_avista = round(valor_avista + taxa_licenciamento, 2)
        custo_total_parcelado = round(valor_ipva + taxa_licenciamento, 2)

    return {
        'uf': uf_upper,
        'estado_nome': info['nome'],
        'valor_fipe': valor_base,
        'valor_fipe_formatado': format_money(valor_base),
        'aliquota': aliquota,
        'aliquota_formatada': f"{aliquota:.2f}%".replace('.', ','),
        'ano_modelo': ano_modelo,
        'idade_anos': idade,
        'isencao_anos': isencao_anos,
        'isento': isento,
        'motivo_isencao': motivo_isencao,
        'valor_ipva': valor_ipva,
        'valor_ipva_formatado': format_money(valor_ipva),
        'desconto_avista_pct': desconto_avista,
        'valor_avista': valor_avista,
        'valor_avista_formatado': format_money(valor_avista),
        'max_parcelas': max_parcelas,
        'valor_parcela': valor_parcela,
        'valor_parcela_formatado': format_money(valor_parcela),
        'planos_parcelamento': planos_parcelamento,
        'taxa_licenciamento': taxa_licenciamento,
        'taxa_licenciamento_formatada': format_money(taxa_licenciamento),
        'custo_total_avista': custo_total_avista,
        'custo_total_avista_formatado': format_money(custo_total_avista),
        'custo_total_parcelado': custo_total_parcelado,
        'custo_total_parcelado_formatado': format_money(custo_total_parcelado),
        'observacoes': info['observacoes']
    }

def obter_tabela_estados():
    """Retorna a lista estruturada de todos os estados, alíquotas e taxa de licenciamento."""
    lista = []
    for k, v in sorted(ESTADOS_IPVA.items(), key=lambda item: item[1]['nome']):
        taxa_lic = float(v.get('taxa_licenciamento', 160.00))
        lista.append({
            'uf': k,
            'nome': v['nome'],
            'aliquota': v['aliquota'],
            'aliquota_formatada': f"{v['aliquota']:.2f}%".replace('.', ','),
            'isencao_anos': v['isencao_anos'],
            'desconto_avista': v['desconto_avista'],
            'max_parcelas': v['max_parcelas'],
            'taxa_licenciamento': taxa_lic,
            'taxa_licenciamento_formatada': format_money(taxa_lic),
            'observacoes': v['observacoes']
        })
    return lista

if __name__ == '__main__':
    print("--- Teste de IPVA, Parcelamento e Licenciamento ---")
    uf_detectada = obter_uf_por_ip()
    print(f"UF detectada pelo IP: {uf_detectada}")

    # Exemplo: Carro de R$ 50.000, ano 2018 em SP
    calc_sp = calcular_ipva(50000.0, ano_modelo=2018, uf='SP')
    print(f"\n--- SP (2018, R$ 50k) ---")
    print(f"IPVA SP: {calc_sp['valor_ipva_formatado']} | À vista: {calc_sp['valor_avista_formatado']}")
    print(f"Licenciamento SP: {calc_sp['taxa_licenciamento_formatada']}")
    print(f"Total À Vista c/ Licenciamento: {calc_sp['custo_total_avista_formatado']}")
    print(f"Planos de parcelamento:")
    for plano in calc_sp['planos_parcelamento']:
        print(f"  > {plano['nome']}: {plano['valor_parcela_formatado']}")
        for parc in plano['cronograma']:
            print(f"      {parc['titulo']} ({parc['mes']}): {parc['valor_formatado']}")
