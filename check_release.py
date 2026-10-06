import urllib.request
import json
import os
import subprocess

API_URL = 'https://api.github.com/repos/fipex-labs/dataset/releases/latest'
LAST_RELEASE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'last_release.txt')

def check_and_update():
    print('Verificando último release no GitHub...')
    try:
        req = urllib.request.Request(API_URL)
        req.add_header('User-Agent', 'GraficoFIPE')
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Erro ao buscar na API: {e}")
        return

    latest_tag = data.get('tag_name')
    if not latest_tag:
        print("Erro: não foi possível encontrar a tag_name no release.")
        return

    print(f"Última versão encontrada no GitHub: {latest_tag}")

    last_tag = None
    if os.path.exists(LAST_RELEASE_FILE):
        with open(LAST_RELEASE_FILE, 'r') as f:
            last_tag = f.read().strip()

    if last_tag == latest_tag:
        print(f"Nenhuma atualização necessária. A versão atual ({last_tag}) já é a mais recente.")
        return

    print(f"Nova versão disponível! {last_tag} -> {latest_tag}. Iniciando baixa_fipex.py...")
    
    # Executa o baixa_fipex.py
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'baixa_fipex.py')
    result = subprocess.run(['python', script_path])
    
    if result.returncode == 0:
        print("Atualização concluída com sucesso. Salvando nova versão.")
        with open(LAST_RELEASE_FILE, 'w') as f:
            f.write(latest_tag)
    else:
        print(f"Erro ao executar baixa_fipex.py. Código: {result.returncode}")

if __name__ == '__main__':
    check_and_update()
