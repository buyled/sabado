from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# Configuración centralizada
class Config:
    GOMANAGE_BASE_URL = "http://buyled.clonico.es:8181"
    GOMANAGE_USERNAME = "distri"
    GOMANAGE_PASSWORD = "GOtmt%"
    GOMANAGE_AUTH_TOKEN = "AKAAAQAAAAhtb2JpbGVBAACgAAIAAAAHZGlzdHJpAACQAAsAAAAIAAAAAGhdIuoAMAAMAAAAAgAMAKAAGgAAAA9TU09BY2Nlc3NUb2tlbgAAoAANAAAADVJPTEVfUFNDVXNlcgAAoAAPAAAANEQzQzM1OEI5Qzc0MjI3NTQ1MkM5NkZFMzIxRjREMjFCRkUzOEYyMUFBODlELm9lcGFzMQAA0AAQAAAACAAAAABoXTD6ANAAFwAAAAgAAAAAAAAAeADQABsAAAAIAAAAAAAAAHgA0AAcAAAACAAAAAAMwnAPALAAFQAAABBTNG0v02DCpLdqzAJOPicS"
    SESSION_TIMEOUT_MINUTES = 25
    REQUEST_TIMEOUT = 30
    CACHE_TIMEOUT_MINUTES = 30

# Singleton para gestión de sesión
class SessionManager:
    def __init__(self):
        self.session_id = None
        self.session_expires = None
        self.last_auth_attempt = None
        self.auth_failures = 0
        self.max_auth_failures = 3
        
    def is_session_valid(self):
        """Verificar si la sesión actual es válida"""
        if not self.session_id or not self.session_expires:
            return False
        return datetime.now() < self.session_expires
    
    def should_retry_auth(self):
        """Verificar si podemos intentar autenticar de nuevo"""
        if self.auth_failures >= self.max_auth_failures:
            if self.last_auth_attempt:
                time_since_last = datetime.now() - self.last_auth_attempt
                if time_since_last.total_seconds() < 300:  # 5 minutos
                    return False
            self.auth_failures = 0  # Reset después de 5 minutos
        return True
    
    def authenticate(self):
        """Autenticar con GoManage"""
        if not self.should_retry_auth():
            print("❌ Demasiados intentos de autenticación fallidos")
            return False
            
        try:
            print(f"🔐 Autenticando con GoManage...")
            
            auth_url = f"{Config.GOMANAGE_BASE_URL}/gomanage/static/auth/j_spring_security_check"
            
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'GoManage-Client/1.0'
            }
            
            auth_data = {
                'j_username': Config.GOMANAGE_USERNAME,
                'j_password': Config.GOMANAGE_PASSWORD
            }
            
            response = requests.post(
                auth_url,
                headers=headers,
                data=auth_data,
                timeout=Config.REQUEST_TIMEOUT,
                allow_redirects=False
            )
            
            print(f"📊 Respuesta de autenticación: {response.status_code}")
            
            if response.status_code == 200 and 'Set-Cookie' in response.headers:
                cookies = response.headers['Set-Cookie']
                for cookie in cookies.split(';'):
                    if 'JSESSIONID' in cookie:
                        self.session_id = cookie.split('=')[1].split(';')[0]
                        self.session_expires = datetime.now() + timedelta(minutes=Config.SESSION_TIMEOUT_MINUTES)
                        self.auth_failures = 0
                        print(f"✅ Sesión iniciada: {self.session_id[:20]}...")
                        return True
            
            self.auth_failures += 1
            self.last_auth_attempt = datetime.now()
            print(f"❌ Fallo de autenticación #{self.auth_failures}")
            return False
            
        except requests.exceptions.Timeout:
            print("⏰ Timeout en autenticación")
            self.auth_failures += 1
            self.last_auth_attempt = datetime.now()
            return False
        except requests.exceptions.ConnectionError:
            print("🔌 Error de conexión con GoManage")
            self.auth_failures += 1
            self.last_auth_attempt = datetime.now()
            return False
        except Exception as e:
            print(f"❌ Error inesperado en autenticación: {str(e)}")
            self.auth_failures += 1
            self.last_auth_attempt = datetime.now()
            return False
    
    def get_auth_headers(self):
        """Obtener headers de autenticación"""
        if not self.session_id:
            return None
            
        return {
            'Cookie': f"JSESSIONID={self.session_id}",
            'Authorization': f"oecp {Config.GOMANAGE_AUTH_TOKEN}",
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'GoManage-Client/1.0'
        }

# Instancia global del gestor de sesión
session_manager = SessionManager()

# Cache mejorado con TTL
class DataCache:
    def __init__(self):
        self.cache = {}
        self.cache_timestamps = {}
    
    def get(self, key):
        """Obtener datos del cache si no han expirado"""
        if key not in self.cache:
            return None
            
        timestamp = self.cache_timestamps.get(key)
        if not timestamp:
            return None
            
        if datetime.now() - timestamp > timedelta(minutes=Config.CACHE_TIMEOUT_MINUTES):
            self.invalidate(key)
            return None
            
        return self.cache[key]
    
    def set(self, key, value):
        """Guardar datos en cache"""
        self.cache[key] = value
        self.cache_timestamps[key] = datetime.now()
    
    def invalidate(self, key):
        """Invalidar entrada del cache"""
        self.cache.pop(key, None)
        self.cache_timestamps.pop(key, None)
    
    def clear(self):
        """Limpiar todo el cache"""
        self.cache.clear()
        self.cache_timestamps.clear()

# Instancia global del cache
data_cache = DataCache()

def make_authenticated_request(method, url, **kwargs):
    """Realizar petición autenticada con reintentos automáticos"""
    max_retries = 2
    
    for attempt in range(max_retries):
        # Verificar/renovar sesión
        if not session_manager.is_session_valid():
            if not session_manager.authenticate():
                return None
        
        # Obtener headers de autenticación
        headers = session_manager.get_auth_headers()
        if not headers:
            continue
            
        # Combinar headers
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
        kwargs['headers'] = headers
        kwargs['timeout'] = kwargs.get('timeout', Config.REQUEST_TIMEOUT)
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, **kwargs)
            elif method.upper() == 'POST':
                response = requests.post(url, **kwargs)
            else:
                raise ValueError(f"Método HTTP no soportado: {method}")
            
            # Verificar respuesta exitosa
            if response.status_code == 200:
                return response
            
            # Si es error de autenticación, invalidar sesión e intentar de nuevo
            if response.status_code in [401, 403] and attempt < max_retries - 1:
                print(f"🔄 Error {response.status_code}, renovando sesión...")
                session_manager.session_id = None
                continue
            
            print(f"❌ Error HTTP {response.status_code}: {response.text[:200]}")
            return response
            
        except requests.exceptions.Timeout:
            print(f"⏰ Timeout en intento {attempt + 1}")
            if attempt < max_retries - 1:
                continue
        except requests.exceptions.ConnectionError:
            print(f"🔌 Error de conexión en intento {attempt + 1}")
            if attempt < max_retries - 1:
                continue
        except Exception as e:
            print(f"❌ Error inesperado: {str(e)}")
            if attempt < max_retries - 1:
                continue
    
    return None

# ============================================================================
# RUTAS PRINCIPALES
# ============================================================================

@app.route('/')
def index():
    """Página principal - ÚNICA RUTA"""
    return render_template('index_unified.html')

@app.route('/health')
def health_check():
    """Health check para monitoreo"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'session_valid': session_manager.is_session_valid(),
        'cache_entries': len(data_cache.cache)
    })

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/auth', methods=['POST'])
def authenticate():
    """Endpoint de autenticación manual"""
    try:
        success = session_manager.authenticate()
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Autenticación exitosa",
                "session_valid": True,
                "expires_in": int((session_manager.session_expires - datetime.now()).total_seconds())
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Error de autenticación con GoManage",
                "session_valid": False,
                "retry_after": 300 if session_manager.auth_failures >= session_manager.max_auth_failures else 0
            }), 401
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}",
            "session_valid": False
        }), 500

@app.route('/api/customers', methods=['GET'])
def get_customers():
    """Obtener lista de clientes con cache inteligente"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = request.args.get('search', '').strip().lower()
        
        # Intentar obtener del cache
        cache_key = 'all_customers'
        all_customers = data_cache.get(cache_key)
        
        if not all_customers:
            print("📥 Cargando clientes desde GoManage...")
            all_customers = load_customers_from_api()
            if all_customers is not None:
                data_cache.set(cache_key, all_customers)
            else:
                return jsonify({
                    "status": "error",
                    "message": "Error cargando clientes desde GoManage"
                }), 500
        
        # Aplicar filtro de búsqueda
        filtered_customers = all_customers
        if search:
            filtered_customers = [
                customer for customer in all_customers
                if any(search in str(customer.get(field, '')).lower() 
                      for field in ['business_name', 'name', 'vat_number', 'email', 'city'])
            ]
        
        # Aplicar paginación
        total = len(filtered_customers)
        start = (page - 1) * per_page
        end = start + per_page
        customers_page = filtered_customers[start:end]
        
        return jsonify({
            "status": "success",
            "customers": customers_page,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            },
            "cached": True
        })
        
    except Exception as e:
        print(f"❌ Error en get_customers: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}"
        }), 500

def load_customers_from_api():
    """Cargar todos los clientes desde la API con paginación"""
    try:
        all_customers = []
        page = 1
        page_size = 500
        
        while True:
            response = make_authenticated_request(
                'GET',
                f"{Config.GOMANAGE_BASE_URL}/gomanage/web/data/apitmt-customers/List",
                params={'page': page, 'size': page_size}
            )
            
            if not response or response.status_code != 200:
                if page == 1:  # Si falla la primera página, es un error
                    return None
                break  # Si falla una página posterior, devolver lo que tenemos
            
            data = response.json()
            page_entries = data.get('page_entries', [])
            
            if not page_entries:
                break
                
            all_customers.extend(page_entries)
            print(f"📄 Cargada página {page}: {len(page_entries)} clientes")
            
            if len(page_entries) < page_size:
                break
                
            page += 1
        
        print(f"✅ Total cargado: {len(all_customers)} clientes")
        return all_customers
        
    except Exception as e:
        print(f"❌ Error cargando clientes: {str(e)}")
        return None

@app.route('/api/customers', methods=['POST'])
def create_customer():
    """Crear nuevo cliente"""
    try:
        customer_data = request.get_json()
        
        if not customer_data:
            return jsonify({
                "status": "error",
                "message": "No se proporcionaron datos del cliente"
            }), 400
        
        # Validar campos obligatorios
        required_fields = ['business_name', 'name', 'vat_number']
        for field in required_fields:
            if not customer_data.get(field):
                return jsonify({
                    "status": "error",
                    "message": f"Campo obligatorio faltante: {field}"
                }), 400
        
        # Preparar payload con valores por defecto
        payload = {
            "has_discount_scale": True,
            "country_id": "ES",
            "currency_id": "eur",
            "periodicity_id": "1",
            "language_id": "cas",
            "business_name": customer_data.get("business_name"),
            "name": customer_data.get("name"),
            "vat_number": customer_data.get("vat_number"),
            "city": customer_data.get("city", ""),
            "street_name": customer_data.get("street_name", ""),
            "postal_code": customer_data.get("postal_code", 0),
            "province_id": int(customer_data.get("province_id", 3)),
            "payment_method_id": customer_data.get("payment_method_id", "007"),
            "tip_cli": customer_data.get("tip_cli", "3"),
            "send_invoices": customer_data.get("send_invoices", False),
            "send_newsletter": customer_data.get("send_newsletter", False),
            "is_public_administration": customer_data.get("is_public_administration", False),
            "control_level": 0,
            "customer_ambit": 0,
            "default_attachment_id": 0,
            "group_id": 0,
            "has_attachments": False,
            "has_self_invoicing": False,
            "has_shared_contacts_by_zone": False,
            "is_foreign": False,
            "is_invoiced_at_central": False,
            "is_not_regular_customer": False,
            "is_resident": False,
            "purchasing_group_commission": 0,
            "request_print_fluorinated_gas": False,
            "subgroup_id": 0,
            "is_locked": "Si"
        }
        
        print(f"🔄 Creando cliente: {payload['business_name']}")
        
        response = make_authenticated_request(
            'POST',
            f"{Config.GOMANAGE_BASE_URL}/gomanage/web/data/apitmt-customers/",
            json=payload
        )
        
        if response and response.status_code in [200, 201]:
            # Invalidar cache de clientes
            data_cache.invalidate('all_customers')
            
            return jsonify({
                "status": "success",
                "message": "Cliente creado exitosamente",
                "customer": response.json() if response.text else {}
            })
        else:
            error_message = response.text if response else "Sin respuesta del servidor"
            return jsonify({
                "status": "error",
                "message": f"Error creando cliente: {error_message}",
                "status_code": response.status_code if response else 0
            }), response.status_code if response else 500
            
    except Exception as e:
        print(f"❌ Error en create_customer: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}"
        }), 500

@app.route('/api/sales-orders', methods=['GET'])
def get_sales_orders():
    """Obtener pedidos de venta con cache"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        customer_id = request.args.get('customer_id')
        sort = request.args.get('sort', 'date')
        from_date = request.args.get('from_date')
        
        # Construir clave de cache
        cache_key = f"sales_orders_{page}_{per_page}_{customer_id}_{sort}_{from_date}"
        cached_data = data_cache.get(cache_key)
        
        if cached_data:
            return jsonify(cached_data)
        
        # Construir parámetros
        params = {
            'page': page,
            'size': per_page,
            'sort': sort
        }
        
        if customer_id:
            params['customer_id'] = customer_id
        if from_date:
            params['from_date'] = from_date
        
        print(f"📄 Cargando pedidos de venta - Página {page}")
        
        response = make_authenticated_request(
            'GET',
            f"{Config.GOMANAGE_BASE_URL}/gomanage/web/data/apitmt-sales-invoices/List",
            params=params
        )
        
        if not response or response.status_code != 200:
            return jsonify({
                "status": "error",
                "message": f"Error cargando pedidos: {response.status_code if response else 'Sin respuesta'}"
            }), 500
        
        data = response.json()
        sales_orders = data.get('page_entries', [])
        total_entries = data.get('total_entries', 0)
        
        result = {
            "status": "success",
            "sales_orders": sales_orders,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total_entries,
                "pages": (total_entries + per_page - 1) // per_page
            }
        }
        
        # Guardar en cache
        data_cache.set(cache_key, result)
        
        print(f"✅ Cargados {len(sales_orders)} pedidos de {total_entries} totales")
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error en get_sales_orders: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}"
        }), 500

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard_data():
    """Obtener datos del dashboard con cache"""
    try:
        cache_key = 'dashboard_data'
        cached_data = data_cache.get(cache_key)
        
        if cached_data:
            return jsonify(cached_data)
        
        # Cargar datos para el dashboard
        customers = data_cache.get('all_customers')
        if not customers:
            customers = load_customers_from_api()
            if customers:
                data_cache.set('all_customers', customers)
        
        # Obtener algunos pedidos para métricas
        sales_response = make_authenticated_request(
            'GET',
            f"{Config.GOMANAGE_BASE_URL}/gomanage/web/data/apitmt-sales-invoices/List",
            params={'size': 100}
        )
        
        sales_data = []
        total_sales = 0
        if sales_response and sales_response.status_code == 200:
            sales_data = sales_response.json().get('page_entries', [])
            total_sales = sum(float(order.get('total', 0)) for order in sales_data)
        
        dashboard_data = {
            "status": "success",
            "data": {
                "total_customers": len(customers) if customers else 0,
                "total_products": 0,  # Placeholder
                "active_orders": len(sales_data),
                "monthly_revenue": total_sales,
                "session_valid": session_manager.is_session_valid(),
                "last_update": datetime.now().isoformat()
            }
        }
        
        # Guardar en cache por menos tiempo (5 minutos)
        data_cache.set(cache_key, dashboard_data)
        
        return jsonify(dashboard_data)
        
    except Exception as e:
        print(f"❌ Error en dashboard: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error cargando dashboard: {str(e)}"
        }), 500

# ============================================================================
# MANEJO DE ERRORES
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint no encontrado"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Error interno del servidor"
    }), 500

# ============================================================================
# INICIALIZACIÓN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    print("🚀 Iniciando GoManage...")
    print(f"📡 Puerto: {port}")
    print(f"🔧 Debug: {debug}")
    print(f"🌐 GoManage API: {Config.GOMANAGE_BASE_URL}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)