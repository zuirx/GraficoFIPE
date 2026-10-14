# -*- coding: utf-8 -*-
"""
ficha_tecnica.py
Módulo para pesquisar e extrair ficha técnica completa de veículos do portal CarrosNaWeb
utilizando Playwright (Patchright) e OCR automatizado para validação de segurança.

Funcionalidades:
- Pesquisa no Google pelo veículo + "site:carrosnaweb.com.br"
- Clica no link relacionado do CarrosNaWeb
- Trata e resolve automaticamente captcha (img.asp) com ddddocr
- Extrai ficha técnica completa:
  - Título, ano, modelo e fotos
  - Especificações categorizadas (Motor, Transmissão, Desempenho, Consumo, Dimensões, etc.)
  - Equipamentos de série e opcionais (Segurança, Conforto, Infotenimento)
- Armazenamento em cache SQLite local para alta performance e economia de recursos
"""

import os
import sys
import time
import json
import sqlite3
import re
from io import BytesIO
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
from PIL import Image

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

import ddddocr

# Caminho do banco de cache para fichas técnicas
CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fichas_cache.db')


def init_cache_db():
    """Inicializa a tabela de cache SQLite para fichas técnicas."""
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
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Cache] Erro ao inicializar cache: {e}")


def get_from_cache(termo: str) -> Optional[Dict[str, Any]]:
    """Recupera os dados de ficha técnica do cache local, se existirem."""
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
    """Salva a ficha técnica no cache SQLite local."""
    try:
        init_cache_db()
        termo_limpo = termo.strip().lower()
        conn = sqlite3.connect(CACHE_DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT OR REPLACE INTO fichas_cache (termo_busca, url, carro, dados_json)
            VALUES (?, ?, ?, ?)
        ''', (termo_limpo, dados.get("url", ""), dados.get("carro", ""), json.dumps(dados, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Cache] Erro ao salvar no cache: {e}")


def _resolver_captcha(ocr_engine, img_bytes: bytes) -> str:
    """Aprimora a imagem do captcha com 3x bicubic e executa OCR."""
    try:
        img = Image.open(BytesIO(img_bytes))
        img_upscaled = img.resize((img.width * 3, img.height * 3), Image.BICUBIC)
        buf = BytesIO()
        img_upscaled.save(buf, format='PNG')
        codigo = ocr_engine.classification(buf.getvalue())
        return codigo.strip()
    except Exception:
        return ocr_engine.classification(img_bytes).strip()


def extrair_ficha_de_html(html: str, url: str = "") -> Dict[str, Any]:
    """
    Analisa o HTML da página do CarrosNaWeb e extrai todas as informações da ficha técnica.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Título e Nome do Carro
    title_tag = soup.find("title")
    title_text = title_tag.text.strip() if title_tag else ""
    
    car_name = ""
    for font in soup.find_all("font"):
        size = font.get("size")
        if size in ["4", "5", "6"]:
            t = font.get_text(strip=True)
            if len(t) > 3 and not any(w in t.lower() for w in ["ficha técnica", "compartilhe", "carros na web", "catálogo", "busca detalhada"]):
                car_name = t
                break
                
    if not car_name and title_text:
        parts = title_text.split("|")
        if len(parts) >= 2:
            car_name = parts[1].strip()
        else:
            car_name = title_text.replace("Carros na Web", "").strip(" -|")
            
    # 2. Fotos do Veículo
    images = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "imagensbd007" in src and "thumbCompara" not in src:
            if not src.startswith("http"):
                src = "https://www.carrosnaweb.com.br/" + src.replace("\\", "/").lstrip("/")
            if src not in images:
                images.append(src)
                
    # 3. Equipamentos (Segurança, Conforto, Infotenimento)
    equipamentos = {
        "Segurança": [],
        "Conforto": [],
        "Infotenimento": []
    }
    
    for t in soup.find_all("table"):
        txt = t.get_text()
        if re.search(r'seguran|conforto|infotenimento', txt, re.IGNORECASE) and t.find("img", src=re.compile(r'verde|amar')):
            current_cat = None
            for tr in t.find_all("tr"):
                row_t = tr.get_text(" ", strip=True)
                if re.search(r'seguran', row_t, re.IGNORECASE) and len(row_t) < 30:
                    current_cat = "Segurança"
                    continue
                elif re.search(r'conforto', row_t, re.IGNORECASE) and len(row_t) < 30:
                    current_cat = "Conforto"
                    continue
                elif re.search(r'infotenimento', row_t, re.IGNORECASE) and len(row_t) < 30:
                    current_cat = "Infotenimento"
                    continue
                    
                if current_cat:
                    cells = tr.find_all(["td", "th"])
                    td_idx = 0
                    while td_idx < len(cells):
                        img = cells[td_idx].find("img")
                        if img:
                            src = img.get("src", "")
                            status = img.get("title", "")
                            if not status:
                                if "verde" in src: status = "De série"
                                elif "amar" in src: status = "Opcional"
                                else: status = "Indisponível"
                            
                            if "srie" in status.lower() or "serie" in status.lower():
                                status = "De série"
                            elif "opcional" in status.lower():
                                status = "Opcional"
                                
                            if td_idx + 1 < len(cells):
                                name = cells[td_idx + 1].get_text(strip=True)
                                if name and len(name) > 1 and not name.startswith("http"):
                                    if not any(x["nome"] == name for x in equipamentos[current_cat]):
                                        equipamentos[current_cat].append({
                                            "nome": name,
                                            "tipo": status
                                        })
                                td_idx += 2
                                continue
                        td_idx += 1

    # 4. Especificações Técnicas por Seção
    specs = {}
    current_section = "Geral"
    sec_candidates = ["MOTOR", "TRANSMISSÃO", "DESEMPENHO", "CONSUMO", "AUTONOMIA", 
                      "SUSPENSÃO", "FREIOS", "DIREÇÃO", "PNEUS", "DIMENSÕES", "AERODINÂMICA"]
                      
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        row_text = tr.get_text(" ", strip=True)
        
        is_sec_header = False
        for sc in sec_candidates:
            pattern = re.escape(sc[:6])
            if re.search(pattern, row_text, re.IGNORECASE) and len(cells) <= 2 and len(row_text) < 35:
                current_section = sc.capitalize()
                if current_section not in specs:
                    specs[current_section] = {}
                is_sec_header = True
                break
        if is_sec_header:
            continue
            
        if tr.find("img", src=re.compile(r'verde|amar')):
            continue
            
        if len(cells) == 2:
            k = cells[0].get_text(strip=True)
            v = cells[1].get_text(strip=True)
            if k and v and len(k) < 50 and not any(w in k.lower() for w in ["compartilhe", "busca detalhada", "página principal", "equipamentos"]):
                if current_section not in specs:
                    specs[current_section] = {}
                specs[current_section][k] = v
        elif len(cells) == 4:
            k1 = cells[0].get_text(strip=True)
            v1 = cells[1].get_text(strip=True)
            k2 = cells[2].get_text(strip=True)
            v2 = cells[3].get_text(strip=True)
            if current_section not in specs:
                specs[current_section] = {}
            if k1 and v1 and len(k1) < 50:
                specs[current_section][k1] = v1
            if k2 and v2 and len(k2) < 50:
                specs[current_section][k2] = v2

    specs = {k: v for k, v in specs.items() if v}

    return {
        "sucesso": True,
        "carro": car_name or "Veículo",
        "titulo": title_text,
        "url": url,
        "fotos": images,
        "especificacoes": specs,
        "equipamentos": equipamentos
    }


def obter_ficha_tecnica(termo_carro: str, force_refresh: bool = False, max_tentativas_captcha: int = 6) -> Dict[str, Any]:
    """
    Busca no Google e extrai a ficha técnica completa do carro no CarrosNaWeb.
    
    Args:
        termo_carro: Termo com nome do veículo, motor e ano (ex: "Gol Special 1.0 Total Flex 8V 5p (2015)")
        force_refresh: Se True, ignora o cache e executa uma nova raspagem
        max_tentativas_captcha: Número máximo de tentativas para resolver o captcha
        
    Returns:
        Dicionário com todos os dados da ficha técnica ou erro.
    """
    termo_carro = termo_carro.strip()
    if not termo_carro:
        return {"sucesso": False, "erro": "Termo de busca não fornecido."}
        
    # 1. Verifica cache
    if not force_refresh:
        cached = get_from_cache(termo_carro)
        if cached:
            print(f"[FichaTecnica] Retornando dados do cache para: '{termo_carro}'")
            return cached
            
    print(f"[FichaTecnica] Iniciando busca no Google para: '{termo_carro}'...")
    ocr = ddddocr.DdddOcr(show_ad=False)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR"
        )
        page = context.new_page()
        
        try:
            # Acessa o Google
            page.goto("https://www.google.com/?hl=pt-BR", wait_until="domcontentloaded", timeout=20000)
            
            # Aceita termos/cookies do Google se existirem
            for text in ["Aceitar tudo", "Concordo", "Aceito"]:
                btn = page.locator(f"button:has-text('{text}')")
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    time.sleep(0.5)
                    break
                    
            query = f"{termo_carro} site:carrosnaweb.com.br"
            search_box = page.locator('textarea[name="q"], input[name="q"]').first
            search_box.fill(query)
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.keyboard.press("Enter")
            time.sleep(1.5)
            
            # Localiza o link principal do CarrosNaWeb
            target_link = page.locator('#search a:has(h3), #rso a:has(h3)').first
            if target_link.count() == 0:
                omitted = page.locator('a:has-text("repetir a pesquisa")')
                if omitted.count() > 0:
                    with page.expect_navigation(wait_until="domcontentloaded"):
                        omitted.first.click()
                    time.sleep(1)
                    target_link = page.locator('#search a:has(h3), #rso a:has(h3)').first
                    
            if target_link.count() == 0:
                return {"sucesso": False, "erro": "Nenhum resultado encontrado no Google para este veículo."}
                
            title_text = target_link.locator("h3").inner_text() if target_link.locator("h3").count() > 0 else ""
            print(f"[FichaTecnica] Clicando no link relacionado do site: '{title_text}'...")
            
            with page.expect_navigation(timeout=25000):
                target_link.click()
                
            time.sleep(1.5)
            print(f"[FichaTecnica] URL de destino: {page.url}")
            
            # Se a página caiu no erro 500 por causa de política de referer do IIS
            if "500 - Internal server error" in page.title() or "500" in page.content()[:400]:
                target_url = page.url
                print(f"[FichaTecnica] 500 detectado. Abrindo catálogo para inicializar sessão e navegando para {target_url}...")
                new_page = context.new_page()
                new_page.goto("https://www.carrosnaweb.com.br/catalogo.asp")
                time.sleep(1)
                new_page.goto(target_url)
                page.close()
                page = new_page
                time.sleep(1.5)
                print(f"[FichaTecnica] Nova página: {page.url}")
            
            # Loop de resolução de captcha (fichadetalheValida.asp)
            for tentativa in range(max_tentativas_captcha):
                if "fichadetalhe.asp" in page.url and "token=" in page.url and "fichadetalheValida" not in page.url:
                    print("[FichaTecnica] Sucesso! Ficha técnica carregada.")
                    break
                    
                img_captcha = page.locator('img[src*="img.asp"]')
                if img_captcha.count() > 0 and img_captcha.first.is_visible():
                    print(f"[FichaTecnica] Captcha detectado. Resolvendo tentativa {tentativa + 1}/{max_tentativas_captcha}...")
                    img_bytes = img_captcha.first.screenshot()
                    code = _resolver_captcha(ocr, img_bytes)
                    print(f"[FichaTecnica] Código reconhecido: '{code}'")
                    page.locator('input[name="txt_key"]').fill(code)
                    
                    try:
                        with page.expect_navigation(timeout=15000):
                            page.locator('input[type="submit"][name="Submit"]').click()
                    except Exception:
                        page.locator('input[type="submit"][name="Submit"]').click()
                    time.sleep(1)
                else:
                    break
                    
            print(f"[FichaTecnica] Página final: {page.url} ({page.title()})")
            html_final = page.content()
            
            if "Preencha o campo com os caracteres" in html_final:
                return {
                    "sucesso": False, 
                    "erro": "Não foi possível validar o captcha de segurança após várias tentativas."
                }
                
            if "500 - Internal server error" in page.title():
                return {
                    "sucesso": False, 
                    "erro": "O servidor do CarrosNaWeb retornou erro interno temporário ao processar a ficha."
                }
                
            dados = extrair_ficha_de_html(html_final, page.url)
            
            # Salva no cache se foi bem sucedido
            if dados.get("sucesso") and len(dados.get("especificacoes", {})) > 0:
                save_to_cache(termo_carro, dados)
                
            return dados
            
        except Exception as e:
            print(f"[FichaTecnica] Erro durante o processo: {e}")
            return {"sucesso": False, "erro": str(e)}
        finally:
            browser.close()


if __name__ == "__main__":
    termo = sys.argv[1] if len(sys.argv) > 1 else "Gol Special 1.0 Total Flex 8V 5p (2015)"
    print(f"Executando busca para: {termo}")
    res = obter_ficha_tecnica(termo)
    print("\n" + "="*50)
    print("RESULTADO:")
    print("Sucesso:", res.get("sucesso"))
    print("Carro:", res.get("carro"))
    print("URL:", res.get("url"))
    print("Fotos:", len(res.get("fotos", [])))
    print("Seções de especificações:", list(res.get("especificacoes", {}).keys()))
    for s, items in res.get("especificacoes", {}).items():
        print(f"  [{s}] {len(items)} campos")
    for cat, items in res.get("equipamentos", {}).items():
        print(f"  [Equipamentos {cat}] {len(items)} itens")
    if not res.get("sucesso"):
        print("Erro:", res.get("erro"))
    print("="*50)