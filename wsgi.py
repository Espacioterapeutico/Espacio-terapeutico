import sys
import os

# Configuración WSGI para PythonAnywhere (Usuario: Espacioterapeutico)
project_home = '/home/Espacioterapeutico'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import app as application
