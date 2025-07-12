#!/usr/bin/env python3
"""
GoManage - Sistema de Gestión Empresarial
Aplicación Flask simple sin dependencias externas complejas
"""

import json
import os
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

class GoManageHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="static", **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.serve_index()
        elif parsed_path.path == '/api/dashboard':
            self.serve_dashboard_api()
        elif parsed_path.path == '/api/customers':
            self.serve_customers_api()
        elif parsed_path.path == '/api/health':
            self.serve_health_api()
        else:
            super().do_GET()
    
    def serve_index(self):
        """Servir la página principal"""
        try:
            with open('index.html', 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404, "Archivo index.html no encontrado")
    
    def serve_dashboard_api(self):
        """API del dashboard con datos de ejemplo"""
        data = {
            "status": "success",
            "data": {
                "total_customers": 1247,
                "total_products": 892,
                "active_orders": 156,
                "monthly_revenue": 45678.90,
                "session_valid": True,
                "last_update": datetime.now().isoformat()
            }
        }
        
        self.send_json_response(data)
    
    def serve_customers_api(self):
        """API de clientes con datos de ejemplo"""
        customers = [
            {"id": 1, "name": "ACME Distribuciones S.L.", "vat": "B12345678", "city": "Madrid", "email": "info@acme.com"},
            {"id": 2, "name": "Comercial López", "vat": "B87654321", "city": "Barcelona", "email": "lopez@comercial.com"},
            {"id": 3, "name": "Suministros García", "vat": "B11223344", "city": "Valencia", "email": "garcia@suministros.com"},
            {"id": 4, "name": "Distribuidora Norte", "vat": "B55667788", "city": "Bilbao", "email": "norte@distribuidora.com"},
            {"id": 5, "name": "Almacenes Sur", "vat": "B99887766", "city": "Sevilla", "email": "sur@almacenes.com"}
        ]
        
        data = {
            "status": "success",
            "customers": customers,
            "pagination": {
                "page": 1,
                "per_page": 50,
                "total": len(customers),
                "pages": 1
            }
        }
        
        self.send_json_response(data)
    
    def serve_health_api(self):
        """Health check"""
        data = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        }
        
        self.send_json_response(data)
    
    def send_json_response(self, data):
        """Enviar respuesta JSON"""
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json_data.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Log personalizado"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def run_server(port=5000):
    """Ejecutar el servidor"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, GoManageHandler)
    
    print(f"🚀 GoManage iniciado en http://localhost:{port}")
    print(f"📊 Dashboard: http://localhost:{port}")
    print(f"🔧 Health Check: http://localhost:{port}/api/health")
    print("Presiona Ctrl+C para detener el servidor")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Cerrando servidor...")
        httpd.shutdown()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    run_server(port)