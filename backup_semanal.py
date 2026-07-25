import os
import zipfile
from datetime import datetime

def run_weekly_backup():
    backup_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'Respaldos_Mi_Consultorio')
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    zip_filename = os.path.join(backup_dir, f'Espacio_Terapeutico_Backup_{timestamp}.zip')
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', '.idea', '.vscode'}
    exclude_extensions = {'.pyc'}
    
    print(f"Iniciando respaldo semanal en: {zip_filename}")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file.endswith('.zip') or any(file.endswith(ext) for ext in exclude_extensions):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, project_dir)
                zipf.write(file_path, arcname)
                
    print(f"✅ Respaldo semanal completado con éxito: {zip_filename}")

if __name__ == '__main__':
    run_weekly_backup()
