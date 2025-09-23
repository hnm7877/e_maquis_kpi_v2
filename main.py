from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import pandas as pd
from bson import ObjectId
import json
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import folium
from collections import defaultdict
import numpy as np

app = FastAPI(title="Multi-Tenant Sales Analytics API", version="1.0.0")

# Configuration CORS pour Next.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration MongoDB
MONGODB_URL = "mongodb+srv://hnm7877:c6df7nDTRx7PH446r@e-maquis.wiwkver.mongodb.net/test?retryWrites=true&w=majority"
client = MongoClient(MONGODB_URL)

class SalesAnalytics:
    def __init__(self):
        self.client = client
        self._global_products_cache: Optional[Dict[str, str]] = None
        self._geo_cache: Dict[str, Dict[str, Optional[str]]] = {}
        self._geolocator: Optional[Nominatim] = None
        
    def get_all_databases(self) -> List[str]:
        """Récupère toutes les bases de données du cluster"""
        try:
            # Filtrer les bases système
            system_dbs = ['admin', 'local', 'config']
            all_dbs = self.client.list_database_names()
            return [db for db in all_dbs if db not in system_dbs]
        except Exception as e:
            print(f"Erreur lors de la récupération des BDs: {e}")
            return []
    
    def get_sales_from_all_tenants(self) -> List[Dict]:
        """Récupère toutes les ventes de tous les tenants"""
        all_sales = []
        databases = self.get_all_databases()
        
        for db_name in databases:
            try:
                db = self.client[db_name]
                # Vérifier si la collection 'sales' existe
                if 'sales' in db.list_collection_names():
                    sales_collection = db['sales']
                    sales_data = list(sales_collection.find({}))
                    
                    # Ajouter le nom de la BD (tenant) à chaque document et convertir les ObjectId
                    processed_sales = []
                    for sale in sales_data:
                        sale['tenant_id'] = db_name
                        # Convertir tous les ObjectId en string de manière récursive
                        processed_sale = self._convert_objectids_to_strings(sale)
                        processed_sales.append(processed_sale)
                    
                    all_sales.extend(processed_sales)
                    print(f"✅ {len(sales_data)} ventes récupérées de {db_name}")
                else:
                    print(f"⚠️ Collection 'sales' non trouvée dans {db_name}")
                    
            except Exception as e:
                print(f"❌ Erreur avec la BD {db_name}: {e}")
                continue
        
        print(f"🎯 Total: {len(all_sales)} ventes récupérées de {len(databases)} bases de données")
        return all_sales
    
    def _convert_objectids_to_strings(self, obj):
        """Convertit récursivement tous les ObjectId en strings dans un objet"""
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_objectids_to_strings(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectids_to_strings(item) for item in obj]
        else:
            return obj
    
    def get_sales_analytics(self) -> Dict:
        """Calcule les KPIs principaux des ventes"""
        all_sales = self.get_sales_from_all_tenants()
        
        if not all_sales:
            return {"error": "Aucune donnée de vente trouvée"}
        
        # Convertir en DataFrame pour faciliter l'analyse
        df = pd.DataFrame(all_sales)
        
        analytics = {
            "total_sales": len(all_sales),
            "tenants_count": len(df['tenant_id'].unique()) if 'tenant_id' in df.columns else 0,
            "sales_by_tenant": {},
            "data_sample": all_sales[:5]  # Échantillon pour voir la structure
        }
        
        # Analytics par tenant
        if 'tenant_id' in df.columns:
            tenant_stats = df.groupby('tenant_id').size().to_dict()
            analytics["sales_by_tenant"] = tenant_stats
        
        # Si on a des montants, calculer le CA
        if 'amount' in df.columns or 'total' in df.columns or 'price' in df.columns:
            amount_col = None
            for col in ['amount', 'total', 'price', 'value']:
                if col in df.columns:
                    amount_col = col
                    break
            
            if amount_col:
                try:
                    df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
                    analytics["total_revenue"] = float(df[amount_col].sum())
                    analytics["average_sale"] = float(df[amount_col].mean())
                    analytics["revenue_by_tenant"] = df.groupby('tenant_id')[amount_col].sum().to_dict()
                except:
                    pass
        
        return analytics
    
    def get_sales_by_location(self, radius_km: float = 1.0, product_id: Optional[str] = None, product_name: Optional[str] = None) -> List[Dict]:
        """Regroupe les ventes par coordonnées géographiques, avec agrégat par produit.
        - product_id: filtre sur l'id du produit global
        - product_name: filtre sur le nom du produit global
        """
        all_sales = self.get_sales_from_all_tenants()
        products_map = self.get_global_products_map()
        
        # Filtrer les ventes qui ont des coordonnées
        sales_with_coords = []
        for sale in all_sales:
            lat = sale.get('latitude')
            lon = sale.get('longitude')
            if lat is not None and lon is not None:
                try:
                    lat = float(lat)
                    lon = float(lon)
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        # Préparer résumé produits + filtre éventuel
                        # Récupérer lignes d'articles (différentes clés possibles suivant tenants)
                        items: List[Dict[str, Any]] = (
                            sale.get('products')
                            or sale.get('items')
                            or sale.get('lignes')
                            or []
                        ) or []
                        product_entries = []
                        matched_sale = False if (product_id or product_name) else True
                        for item in items:
                            prod = item.get('product') or item.get('article') or {}
                            global_id = None
                            if isinstance(prod, dict):
                                # cas: { _id: ..., product: ObjectId('...') }
                                global_id = (
                                    prod.get('product')
                                    or prod.get('product_global')
                                    or prod.get('global_product_id')
                                )
                            # convert to string
                            global_id_str = str(global_id) if global_id is not None else None
                            name = products_map.get(global_id_str) if global_id_str else None
                            # quantité vendue: différents schémas possibles
                            raw_qty = (
                                item.get('saleQuantity')
                                or item.get('qty')
                                or item.get('qte')
                                or item.get('quantity')
                                or 1
                            )
                            try:
                                qty = int(raw_qty)
                            except Exception:
                                qty = 1
                            returned = item.get('returnedQuantity') or 0
                            try:
                                returned = int(returned)
                            except Exception:
                                returned = 0
                            qty = max(qty - returned, 0)

                            entry = {
                                'global_product_id': global_id_str,
                                'global_product_name': name,
                                'quantity': qty,
                            }
                            product_entries.append(entry)

                            if not matched_sale:
                                if product_id and global_id_str == product_id:
                                    matched_sale = True
                                if product_name and name and name.lower() == product_name.lower():
                                    matched_sale = True

                        if not matched_sale:
                            continue

                        sales_with_coords.append({
                            **sale,
                            'latitude': lat,
                            'longitude': lon,
                            'products_enriched': product_entries,
                        })
                except (ValueError, TypeError):
                    continue
        
        if not sales_with_coords:
            return []
        
        # Regrouper les ventes par proximité géographique
        location_groups = []
        processed = set()
        
        for i, sale in enumerate(sales_with_coords):
            if i in processed:
                continue
                
            # Créer un nouveau groupe
            group = {
                'latitude': sale['latitude'],
                'longitude': sale['longitude'],
                'country': None,
                'city': None,
                'sales': [sale],
                'total_sales': 1,
                'total_amount': 0,
                'tenants': {sale['tenant_id']: 1},
                'products_summary': {},  # nom produit -> quantité
            }
            
            # Calculer le montant pour cette vente
            amount = self._extract_amount(sale)
            if amount:
                group['total_amount'] = amount
            
            # Aggréger quantités par produit pour cette vente
            for p in sale.get('products_enriched', []):
                pname = p.get('global_product_name') or p.get('global_product_id') or 'N/A'
                group['products_summary'][pname] = group['products_summary'].get(pname, 0) + (p.get('quantity') or 0)

            processed.add(i)
            
            # Chercher les ventes proches
            for j, other_sale in enumerate(sales_with_coords[i+1:], i+1):
                if j in processed:
                    continue
                    
                distance = geodesic(
                    (sale['latitude'], sale['longitude']),
                    (other_sale['latitude'], other_sale['longitude'])
                ).kilometers
                
                if distance <= radius_km:
                    group['sales'].append(other_sale)
                    group['total_sales'] += 1
                    
                    # Ajouter le montant
                    other_amount = self._extract_amount(other_sale)
                    if other_amount:
                        group['total_amount'] += other_amount
                    
                    # Compter les tenants
                    tenant_id = other_sale['tenant_id']
                    group['tenants'][tenant_id] = group['tenants'].get(tenant_id, 0) + 1
                    
                    # agrégat produits
                    for p in other_sale.get('products_enriched', []):
                        pname = p.get('global_product_name') or p.get('global_product_id') or 'N/A'
                        group['products_summary'][pname] = group['products_summary'].get(pname, 0) + (p.get('quantity') or 0)

                    processed.add(j)
            
            # Calculer la position moyenne du groupe
            if len(group['sales']) > 1:
                avg_lat = sum(s['latitude'] for s in group['sales']) / len(group['sales'])
                avg_lon = sum(s['longitude'] for s in group['sales']) / len(group['sales'])
                group['latitude'] = avg_lat
                group['longitude'] = avg_lon
            
            group['tenant_count'] = len(group['tenants'])
            # Résolution pays/ville (approx, avec cache)
            geo = self._reverse_geocode_country_city(group['latitude'], group['longitude'])
            group['country'] = geo.get('country')
            group['city'] = geo.get('city')
            location_groups.append(group)
        
        # Trier par nombre de ventes décroissant
        location_groups.sort(key=lambda x: x['total_sales'], reverse=True)
        
        # Ajouter products_all (tous les produits) + top_products (compat)
        for g in location_groups:
            if not g['products_summary']:
                g['products_all'] = []
                g['top_products'] = []
                continue
            names = np.array(list(g['products_summary'].keys()))
            qty = np.array(list(g['products_summary'].values()), dtype=float)
            order_all = np.argsort(qty)[::-1]
            g['products_all'] = [
                {'name': str(names[i]), 'quantity': int(qty[i])}
                for i in order_all
            ]
            g['top_products'] = g['products_all'][:5]
        return location_groups
    
    def _extract_amount(self, sale: Dict) -> float:
        """Extrait le montant d'une vente"""
        amount_fields = ['salesPrice', 'amount', 'total', 'price', 'value']
        for field in amount_fields:
            if field in sale and sale[field] is not None:
                try:
                    return float(sale[field])
                except (ValueError, TypeError):
                    continue
        return 0.0
    
    def get_tenant_colors_mapping(self):
        """Récupère le mapping des couleurs par tenant"""
        # Palette de couleurs pour les tenants
        tenant_colors = [
            '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', 
            '#1abc9c', '#e67e22', '#34495e', '#f1c40f', '#e91e63',
            '#8e44ad', '#16a085', '#27ae60', '#2980b9', '#d35400',
            '#c0392b', '#7f8c8d', '#f39800', '#8b4513', '#4682b4'
        ]
        
        # Récupérer tous les tenants avec coordonnées
        all_sales = self.get_sales_from_all_tenants()
        all_tenants = list(set(sale['tenant_id'] for sale in all_sales if 'latitude' in sale and 'longitude' in sale))
        
        # Créer le mapping couleur par tenant (trié pour la cohérence)
        tenant_color_map = {tenant: tenant_colors[i % len(tenant_colors)] for i, tenant in enumerate(sorted(all_tenants))}
        
        return tenant_color_map, len(all_tenants)

    def get_global_products_map(self) -> Dict[str, str]:
        """Retourne un mapping {product_global_id_str: name} depuis la BD 'test'.
        Ajoute des logs détaillés pour vérification.
        """
        if self._global_products_cache is not None:
            return self._global_products_cache

        try:
            import os
            db_name = os.getenv('GLOBAL_PRODUCTS_DB', 'test')
            forced_collection = os.getenv('GLOBAL_PRODUCTS_COLLECTION')
            db = self.client[db_name]
            possible_names = [
                'productglobals', 'produtiglobals', 'productsglobals',
                'produitglobals', 'produitglobal', 'productiglobals'
            ]
            collection_name = None
            existing = set(db.list_collection_names())
            print(f"[Products] DB choisie: {db_name} | Collections existantes: {sorted(list(existing))[:10]}...")
            if forced_collection:
                if forced_collection in existing:
                    collection_name = forced_collection
                    print(f"[Products] Collection forcée via env: {collection_name}")
                else:
                    print(f"[Products] ATTENTION: collection forcée '{forced_collection}' introuvable dans {db_name}")
            if not collection_name:
                for name in possible_names:
                    if name in existing:
                        collection_name = name
                        break
            if not collection_name:
                print("[Products] Aucune collection produits globaux trouvée dans 'test' (noms possibles non présents).")
                self._global_products_cache = {}
                return self._global_products_cache

            coll = db[collection_name]
            print(f"[Products] Collection retenue: {collection_name}")
            mapping: Dict[str, str] = {}
            sample_names = []
            count = 0
            for doc in coll.find({}, {'_id': 1, 'name': 1}):
                count += 1
                if len(sample_names) < 5:
                    sample_names.append(doc.get('name'))
                mapping[str(doc.get('_id'))] = doc.get('name') or ''
            print(f"[Products] Documents chargés: {count} | Échantillon: {sample_names}")
            self._global_products_cache = mapping
            return mapping
        except Exception as e:
            print(f"[Products] Erreur lors du chargement des produits globaux: {e}")
            self._global_products_cache = {}
            return self._global_products_cache

    def get_global_products_list(self) -> List[Dict[str, Any]]:
        """Retourne la liste des produits globaux (id + name) depuis la BD 'test'."""
        try:
            import os
            db_name = os.getenv('GLOBAL_PRODUCTS_DB', 'test')
            forced_collection = os.getenv('GLOBAL_PRODUCTS_COLLECTION')
            db = self.client[db_name]
            possible_names = ['productglobals', 'produtiglobals', 'productsglobals', 'produitglobals', 'produitglobal', 'productiglobals']
            collection_name = None
            existing = set(db.list_collection_names())
            print(f"[ProductsList] DB choisie: {db_name} | Collections existantes: {sorted(list(existing))[:10]}...")
            if forced_collection and forced_collection in existing:
                collection_name = forced_collection
                print(f"[ProductsList] Collection forcée via env: {collection_name}")
            for name in possible_names:
                if name in existing:
                    collection_name = name
                    break
            if not collection_name:
                print("[ProductsList] Aucune collection produits globaux trouvée.")
                return []
            coll = db[collection_name]
            products: List[Dict[str, Any]] = []
            count = 0
            for doc in coll.find({}, {'_id': 1, 'name': 1}).limit(2000):
                count += 1
                products.append({'id': str(doc.get('_id')), 'name': doc.get('name') or ''})
            print(f"[ProductsList] {len(products)} produits retournés (scannés: {count}) depuis {collection_name}")
            return products
        except Exception as e:
            print(f"[ProductsList] Erreur: {e}")
            return []

    def _reverse_geocode_country_city(self, lat: float, lon: float) -> Dict[str, Optional[str]]:
        """Retourne {country, city} pour des coordonnées, avec cache simple et tolérance.
        """
        try:
            key = f"{round(lat, 3)}|{round(lon, 3)}"
            if key in self._geo_cache:
                return self._geo_cache[key]
            if self._geolocator is None:
                self._geolocator = Nominatim(user_agent="emaquis_kpi")
            location = self._geolocator.reverse((lat, lon), language='en')
            country = None
            city = None
            if location and location.raw and 'address' in location.raw:
                addr = location.raw['address']
                country = addr.get('country')
                city = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('county') or addr.get('state')
            result = {'country': country, 'city': city}
            self._geo_cache[key] = result
            return result
        except Exception:
            return {'country': None, 'city': None}

# Instance globale
sales_analytics = SalesAnalytics()

# Routes API
@app.get("/")
async def root():
    return {"message": "Multi-Tenant Sales Analytics API", "status": "active"}

@app.get("/health")
async def health_check():
    try:
        # Test de connexion MongoDB
        client.admin.command('ping')
        return {"status": "healthy", "mongodb": "connected"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/databases")
async def get_databases():
    """Liste toutes les bases de données disponibles"""
    try:
        databases = sales_analytics.get_all_databases()
        return {
            "databases": databases,
            "count": len(databases)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/all")
async def get_all_sales():
    """Récupère toutes les ventes de tous les tenants"""
    try:
        all_sales = sales_analytics.get_sales_from_all_tenants()
        return {
            "sales": all_sales,
            "total_count": len(all_sales)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/sales")
async def get_sales_analytics():
    """Récupère les analytics des ventes"""
    try:
        analytics = sales_analytics.get_sales_analytics()
        return analytics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/by-tenant/{tenant_id}")
async def get_sales_by_tenant(tenant_id: str):
    """Récupère les ventes d'un tenant spécifique"""
    try:
        db = client[tenant_id]
        if 'sales' not in db.list_collection_names():
            raise HTTPException(status_code=404, detail=f"Collection sales non trouvée dans {tenant_id}")
        
        sales_collection = db['sales']
        sales_data = list(sales_collection.find({}))
        
        # Convertir ObjectId en string de manière récursive
        for i, sale in enumerate(sales_data):
            sales_data[i] = sales_analytics._convert_objectids_to_strings(sale)
        
        return {
            "tenant_id": tenant_id,
            "sales": sales_data,
            "count": len(sales_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/kpis/dashboard")
async def get_dashboard_kpis():
    """KPIs principaux pour le dashboard"""
    try:
        all_sales = sales_analytics.get_sales_from_all_tenants()
        
        if not all_sales:
            return {"error": "Aucune donnée disponible"}
        
        df = pd.DataFrame(all_sales)
        
        # KPIs de base
        kpis = {
            "total_transactions": len(all_sales),
            "active_tenants": len(df['tenant_id'].unique()),
            "avg_transactions_per_tenant": len(all_sales) / len(df['tenant_id'].unique()),
        }
        
        # Top tenants par volume
        tenant_volumes = df.groupby('tenant_id').size().sort_values(ascending=False)
        kpis["top_tenants"] = [
            {"tenant": tenant, "transactions": int(volume)} 
            for tenant, volume in tenant_volumes.head(5).items()
        ]
        
        # Évolution temporelle si on a des dates
        date_fields = ['date', 'created_at', 'timestamp', 'sale_date']
        date_field = None
        for field in date_fields:
            if field in df.columns:
                date_field = field
                break
        
        if date_field:
            try:
                df[date_field] = pd.to_datetime(df[date_field], errors='coerce')
                daily_sales = df.groupby(df[date_field].dt.date).size()
                kpis["daily_trend"] = [
                    {"date": str(date), "transactions": int(count)}
                    for date, count in daily_sales.tail(7).items()
                ]
            except:
                pass
        
        return kpis
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/locations")
async def get_sales_locations(radius_km: float = 1.0, product_id: Optional[str] = None, product_name: Optional[str] = None):
    """Récupère les ventes regroupées par localisation géographique"""
    try:
        locations = sales_analytics.get_sales_by_location(radius_km, product_id=product_id, product_name=product_name)
        return {
            "locations": locations,
            "total_locations": len(locations),
            "radius_km": radius_km
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/map")
async def get_sales_map(radius_km: float = 1.0, product_id: Optional[str] = None, product_name: Optional[str] = None):
    """Génère une carte Folium des ventes par localisation"""
    try:
        locations = sales_analytics.get_sales_by_location(radius_km, product_id=product_id, product_name=product_name)
        
        if not locations:
            raise HTTPException(status_code=404, detail="Aucune vente avec coordonnées trouvée")
        
        # Calculer le centre de la carte (NumPy pour robustesse et vitesse)
        lat_arr = np.array([loc['latitude'] for loc in locations], dtype=float)
        lon_arr = np.array([loc['longitude'] for loc in locations], dtype=float)
        center_lat = float(lat_arr.mean())
        center_lon = float(lon_arr.mean())
        
        # Créer la carte
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=10,
            tiles='OpenStreetMap'
        )
        
        # Récupérer le mapping des couleurs cohérent
        tenant_color_map, _ = sales_analytics.get_tenant_colors_mapping()
        
        # Ajouter les markers pour chaque localisation
        for loc in locations:
            # Taille du marker basée sur le nombre de ventes
            radius = min(max(loc['total_sales'] * 3, 5), 50)
            
            # Couleur basée sur le tenant principal (celui avec le plus de ventes)
            main_tenant = max(loc['tenants'].items(), key=lambda x: x[1])[0]
            color = tenant_color_map.get(main_tenant, '#3498db')
            
            # Popup avec les informations détaillées
            tenants_info = "<br>".join([f"• {tenant}: {count} ventes" for tenant, count in loc['tenants'].items()])
            # Construire la liste HTML de tous les produits vendus
            products_info = "<br>".join([f"• {p['name']}: {p['quantity']}" for p in loc.get('products_all', [])])
            popup_text = f"""
            <div style="min-width:200px;">
                <b>📍 Localisation</b><br>
                <div style="background-color:{color}; color:white; padding:2px 8px; border-radius:4px; margin:4px 0;">
                    <b>Tenant principal: {main_tenant}</b>
                </div>
                <b>📊 Statistiques:</b><br>
                • Total ventes: {loc['total_sales']}<br>
                • Montant total: {loc['total_amount']:.2f} €<br>
                • Nombre de tenants: {loc['tenant_count']}<br><br>
                <b>🧃 Produits vendus (Top):</b><br>
                {products_info}<br><br>
                <b>🏢 Détails par tenant:</b><br>
                {tenants_info}<br><br>
                <b>🌍 Coordonnées:</b><br>
                • Lat: {loc['latitude']:.6f}<br>
                • Lon: {loc['longitude']:.6f}
            </div>
            """
            
            folium.CircleMarker(
                location=[loc['latitude'], loc['longitude']],
                radius=radius,
                popup=popup_text,
                color=color,
                fillColor=color,
                fillOpacity=0.6,
                weight=2
            ).add_to(m)
        
        # Retourner le HTML de la carte
        map_html = m._repr_html_()
        
        return {
            "map_html": map_html,
            "locations_count": len(locations),
            "center": {"latitude": center_lat, "longitude": center_lon}
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sales/tenants-colors")
async def get_tenants_colors():
    """Récupère le mapping des couleurs par tenant pour la légende"""
    try:
        tenant_color_map, total_tenants = sales_analytics.get_tenant_colors_mapping()
        
        return {
            "tenant_colors": tenant_color_map,
            "total_tenants": total_tenants
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/globals")
async def get_products_globals():
    """Expose la liste des produits globaux (pour les filtres côté front)."""
    try:
        items = sales_analytics.get_global_products_list()
        return {"products": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage du serveur Multi-Tenant Sales Analytics")
    print("📊 Connexion au cluster MongoDB...")
    
    # Test de connexion
    try:
        client.admin.command('ping')
        print("✅ Connexion MongoDB réussie")
        
        # Afficher les BDs disponibles
        analytics = SalesAnalytics()
        dbs = analytics.get_all_databases()
        print(f"📁 {len(dbs)} bases de données trouvées: {dbs}")
        
    except Exception as e:
        print(f"❌ Erreur de connexion MongoDB: {e}")
    
    uvicorn.run(app, host="127.0.0.1", port=8001)