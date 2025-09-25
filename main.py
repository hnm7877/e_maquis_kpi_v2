from fastapi import FastAPI, HTTPException, Query
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
from prophet import Prophet
from prophet.plot import plot_plotly, plot_components_plotly
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import warnings
warnings.filterwarnings('ignore')

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

    def create_prophet_models(self, tenant_id: Optional[str] = None, days_ahead: int = 30) -> Dict[str, Any]:
        """Crée des modèles Prophet pour les prédictions de ventes"""
        all_sales = self.get_sales_from_all_tenants()
        
        if not all_sales:
            return {"error": "Aucune donnée disponible"}
        
        df = pd.DataFrame(all_sales)
        
        # Filtrer par tenant si spécifié
        if tenant_id:
            df = df[df['tenant_id'] == tenant_id]
            if df.empty:
                return {"error": f"Aucune donnée trouvée pour le tenant {tenant_id}"}
        
        # Trouver le champ de date
        date_fields = ['date', 'created_at', 'timestamp', 'sale_date']
        date_field = None
        for field in date_fields:
            if field in df.columns:
                date_field = field
                break
        
        if not date_field:
            return {"error": "Aucun champ de date trouvé"}
        
        try:
            df[date_field] = pd.to_datetime(df[date_field], errors='coerce')
            df = df.dropna(subset=[date_field])
        except:
            return {"error": "Impossible de convertir les dates"}
        
        # Préparer les données pour Prophet
        daily_sales = df.groupby(df[date_field].dt.date).size().reset_index()
        daily_sales.columns = ['ds', 'y']
        daily_sales['ds'] = pd.to_datetime(daily_sales['ds'])
        
        if len(daily_sales) < 7:
            return {"error": "Pas assez de données pour créer un modèle Prophet (minimum 7 jours)"}
        
        # Créer le modèle Prophet avec paramètres avancés
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            seasonality_mode='multiplicative',
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            holidays_prior_scale=10.0,
            changepoint_range=0.8
        )
        
        # Ajouter des régresseurs si disponibles
        if 'amount' in df.columns or 'total' in df.columns or 'price' in df.columns:
            amount_col = None
            for col in ['amount', 'total', 'price', 'value', 'salesPrice']:
                if col in df.columns:
                    amount_col = col
                    break
            
            if amount_col:
                try:
                    df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
                    daily_amounts = df.groupby(df[date_field].dt.date)[amount_col].sum().reset_index()
                    daily_amounts.columns = ['ds', 'amount']
                    daily_amounts['ds'] = pd.to_datetime(daily_amounts['ds'])
                    
                    # Fusionner avec les données de ventes
                    daily_sales = daily_sales.merge(daily_amounts, on='ds', how='left')
                    daily_sales['amount'] = daily_sales['amount'].fillna(0)
                    
                    # Ajouter comme régresseur
                    model.add_regressor('amount')
                except:
                    pass
        
        # Entraîner le modèle
        try:
            model.fit(daily_sales)
        except Exception as e:
            return {"error": f"Erreur lors de l'entraînement du modèle: {str(e)}"}
        
        # Créer les prédictions futures
        future = model.make_future_dataframe(periods=days_ahead)
        
        # Ajouter les régresseurs si disponibles
        if 'amount' in daily_sales.columns:
            # Pour les prédictions futures, utiliser la moyenne des montants
            avg_amount = daily_sales['amount'].mean()
            future['amount'] = avg_amount
        
        # Faire les prédictions
        forecast = model.predict(future)
        
        # Calculer les métriques de performance
        train_data = forecast[forecast['ds'] <= daily_sales['ds'].max()]
        actual = daily_sales['y'].values
        predicted = train_data['yhat'].values
        
        metrics = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "mse": float(mean_squared_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
            "mape": float(np.mean(np.abs((actual - predicted) / actual)) * 100)
        }
        
        # Préparer les données pour la visualisation
        historical_data = {
            "x": daily_sales['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": daily_sales['y'].tolist(),
            "type": "scatter",
            "mode": "lines+markers",
            "name": "Données Historiques",
            "line": {"color": "#1f77b4"}
        }
        
        forecast_data = {
            "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": forecast['yhat'].tolist(),
            "type": "scatter",
            "mode": "lines",
            "name": "Prédiction",
            "line": {"color": "#ff7f0e", "dash": "dash"}
        }
        
        # Intervalles de confiance
        upper_bound = {
            "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": forecast['yhat_upper'].tolist(),
            "type": "scatter",
            "mode": "lines",
            "name": "Limite Supérieure",
            "line": {"color": "rgba(255, 127, 14, 0.3)", "width": 0},
            "fill": "tonexty",
            "showlegend": False
        }
        
        lower_bound = {
            "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": forecast['yhat_lower'].tolist(),
            "type": "scatter",
            "mode": "lines",
            "name": "Limite Inférieure",
            "line": {"color": "rgba(255, 127, 14, 0.3)", "width": 0},
            "fill": "tonexty"
        }
        
        # Données des composantes
        components_data = {
            "trend": {
                "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                "y": forecast['trend'].tolist(),
                "type": "scatter",
                "mode": "lines",
                "name": "Tendance"
            },
            "yearly": {
                "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                "y": forecast.get('yearly', [0] * len(forecast)).tolist(),
                "type": "scatter",
                "mode": "lines",
                "name": "Saisonnalité Annuelle"
            },
            "weekly": {
                "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                "y": forecast.get('weekly', [0] * len(forecast)).tolist(),
                "type": "scatter",
                "mode": "lines",
                "name": "Saisonnalité Hebdomadaire"
            }
        }
        
        return {
            "historical": historical_data,
            "forecast": forecast_data,
            "upper_bound": upper_bound,
            "lower_bound": lower_bound,
            "components": components_data,
            "metrics": metrics,
            "model_info": {
                "tenant": tenant_id or "Tous les tenants",
                "training_days": len(daily_sales),
                "forecast_days": days_ahead,
                "last_training_date": str(daily_sales['ds'].max()),
                "forecast_start": str(forecast[forecast['ds'] > daily_sales['ds'].max()]['ds'].min())
            }
        }

    def get_advanced_product_predictions(self, product_name: str, days_ahead: int = 30, 
                                        include_trends: bool = True, include_seasonality: bool = True,
                                        confidence_interval: float = 0.95):
        """Prédictions avancées Prophet pour un produit avec options détaillées"""
        try:
            # Récupérer les données du produit (même logique que get_product_sales_predictions)
            all_sales = self.get_sales_from_all_tenants()
            products_map = self.get_global_products_map()
            
            if not all_sales:
                return {"error": "Aucune donnée de vente disponible"}
            
            # Filtrer par produit
            filtered_sales = []
            for sale in all_sales:
                items = sale.get('products') or sale.get('items') or sale.get('lignes') or []
                for item in items:
                    prod = item.get('product') or item.get('article') or {}
                    global_id = None
                    if isinstance(prod, dict):
                        global_id = prod.get('product') or prod.get('product_global') or prod.get('global_product_id')
                    
                    global_id_str = str(global_id) if global_id is not None else None
                    product_name_found = products_map.get(global_id_str) if global_id_str else "Produit inconnu"
                    
                    if product_name.lower() in product_name_found.lower():
                        filtered_sales.append(sale)
                        break
            
            if not filtered_sales:
                return {"error": f"Aucune vente trouvée pour le produit {product_name}"}
            
            # Préparer les données pour Prophet
            prophet_data = []
            print(f"Traitement de {len(filtered_sales)} ventes pour le produit {product_name}")
            
            for sale in filtered_sales:
                date_str = sale.get('date') or sale.get('created_at') or sale.get('timestamp')
                if date_str:
                    try:
                        date_obj = pd.to_datetime(date_str).date()
                        amount = float(sale.get('amount', 0) or sale.get('total', 0) or 0)
                        if amount > 0:
                            prophet_data.append({
                                'ds': date_obj,
                                'y': amount
                            })
                    except Exception as e:
                        print(f"Erreur lors du traitement d'une vente: {e}")
                        continue
            
            if not prophet_data:
                return {"error": f"Aucune donnée valide trouvée pour le produit {product_name}"}
            
            print(f"Données Prophet préparées: {len(prophet_data)} entrées")
            
            # Créer le DataFrame Prophet
            daily_sales = pd.DataFrame(prophet_data)
            daily_sales = daily_sales.groupby('ds')['y'].sum().reset_index()
            
            print(f"Données groupées par jour: {len(daily_sales)} jours")
            
            # Configuration avancée du modèle Prophet
            model = Prophet(
                interval_width=confidence_interval,
                yearly_seasonality=include_seasonality,
                weekly_seasonality=include_seasonality,
                daily_seasonality=False,
                seasonality_mode='multiplicative',
                changepoint_prior_scale=0.05,
                seasonality_prior_scale=10.0
            )
            
            # Entraîner le modèle
            model.fit(daily_sales)
            
            # Créer les prédictions futures
            future = model.make_future_dataframe(periods=days_ahead)
            forecast = model.predict(future)
            
            # Calculer les métriques
            train_size = int(len(daily_sales) * 0.8)
            train_data = daily_sales[:train_size]
            test_data = daily_sales[train_size:]
            
            if len(test_data) > 0:
                test_forecast = model.predict(test_data[['ds']])
                mae = mean_absolute_error(test_data['y'], test_forecast['yhat'])
                mse = mean_squared_error(test_data['y'], test_forecast['yhat'])
                rmse = np.sqrt(mse)
                r2 = r2_score(test_data['y'], test_forecast['yhat'])
                mape = np.mean(np.abs((test_data['y'] - test_forecast['yhat']) / test_data['y'])) * 100
            else:
                mae = mse = rmse = r2 = mape = 0
            
            # Préparer les données pour le frontend
            historical_data = {
                'x': daily_sales['ds'].dt.strftime('%Y-%m-%d').tolist(),
                'y': daily_sales['y'].tolist(),
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Historique',
                'line': {'color': '#3B82F6'}
            }
            
            forecast_data = {
                'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                'y': forecast['yhat'].tolist(),
                'type': 'scatter',
                'mode': 'lines',
                'name': 'Prédiction',
                'line': {'color': '#10B981'}
            }
            
            upper_bound = {
                'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                'y': forecast['yhat_upper'].tolist(),
                'type': 'scatter',
                'mode': 'lines',
                'name': 'Borne supérieure',
                'line': {'color': 'rgba(16, 185, 129, 0.3)'},
                'fill': 'tonexty'
            }
            
            lower_bound = {
                'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                'y': forecast['yhat_lower'].tolist(),
                'type': 'scatter',
                'mode': 'lines',
                'name': 'Borne inférieure',
                'line': {'color': 'rgba(16, 185, 129, 0.3)'},
                'fill': 'tonexty'
            }
            
            # Composants de saisonnalité
            components = {}
            if include_trends:
                components['trend'] = {
                    'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                    'y': forecast['trend'].tolist(),
                    'type': 'scatter',
                    'mode': 'lines',
                    'name': 'Tendance',
                    'line': {'color': '#F59E0B'}
                }
            
            if include_seasonality:
                if 'yearly' in forecast.columns:
                    components['yearly'] = {
                        'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                        'y': forecast['yearly'].tolist(),
                        'type': 'scatter',
                        'mode': 'lines',
                        'name': 'Saisonnalité annuelle',
                        'line': {'color': '#8B5CF6'}
                    }
                
                if 'weekly' in forecast.columns:
                    components['weekly'] = {
                        'x': forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
                        'y': forecast['weekly'].tolist(),
                        'type': 'scatter',
                        'mode': 'lines',
                        'name': 'Saisonnalité hebdomadaire',
                        'line': {'color': '#EF4444'}
                    }
            
            return {
                "product_name": product_name,
                "historical": historical_data,
                "forecast": forecast_data,
                "upper_bound": upper_bound,
                "lower_bound": lower_bound,
                "components": components,
                "metrics": {
                    "mae": float(mae),
                    "mse": float(mse),
                    "rmse": float(rmse),
                    "r2": float(r2),
                    "mape": float(mape)
                },
                "model_info": {
                    "product_name": product_name,
                    "training_days": len(daily_sales),
                    "forecast_days": days_ahead,
                    "confidence_interval": confidence_interval,
                    "include_trends": include_trends,
                    "include_seasonality": include_seasonality,
                    "last_training_date": daily_sales['ds'].max().strftime('%Y-%m-%d'),
                    "forecast_start": forecast['ds'].iloc[-days_ahead].strftime('%Y-%m-%d')
                }
            }
            
        except Exception as e:
            return {"error": f"Erreur lors de la prédiction avancée pour le produit {product_name}: {str(e)}"}

    def compare_products_predictions(self, product_names: list, days_ahead: int = 30):
        """Comparaison des prédictions entre plusieurs produits"""
        try:
            comparison_data = {}
            
            for product_name in product_names:
                predictions = self.get_advanced_product_predictions(product_name, days_ahead)
                if "error" not in predictions:
                    comparison_data[product_name] = predictions
            
            if not comparison_data:
                return {"error": "Aucune prédiction valide trouvée pour les produits spécifiés"}
            
            # Créer un graphique de comparaison
            comparison_chart = []
            for product_name, data in comparison_data.items():
                comparison_chart.append({
                    'x': data['forecast']['x'],
                    'y': data['forecast']['y'],
                    'type': 'scatter',
                    'mode': 'lines',
                    'name': f'{product_name} - Prédiction',
                    'line': {'color': f'hsl({hash(product_name) % 360}, 70%, 50%)'}
                })
            
            return {
                "products": comparison_data,
                "comparison_chart": comparison_chart,
                "summary": {
                    "total_products": len(comparison_data),
                    "forecast_days": days_ahead,
                    "best_performing": max(comparison_data.items(), 
                                         key=lambda x: x[1]['metrics']['r2'])[0] if comparison_data else None
                }
            }
            
        except Exception as e:
            return {"error": f"Erreur lors de la comparaison des produits: {str(e)}"}

    def get_product_insights(self, product_name: str, days_ahead: int = 30):
        """Insights avancés et recommandations pour un produit"""
        try:
            predictions = self.get_advanced_product_predictions(product_name, days_ahead)
            if "error" in predictions:
                return predictions
            
            # Analyser les tendances
            forecast_data = predictions['forecast']['y']
            historical_data = predictions['historical']['y']
            
            # Calculer la croissance
            recent_avg = np.mean(historical_data[-7:]) if len(historical_data) >= 7 else np.mean(historical_data)
            future_avg = np.mean(forecast_data[-7:]) if len(forecast_data) >= 7 else np.mean(forecast_data)
            growth_rate = ((future_avg - recent_avg) / recent_avg * 100) if recent_avg > 0 else 0
            
            # Analyser la volatilité
            volatility = np.std(historical_data) / np.mean(historical_data) * 100 if np.mean(historical_data) > 0 else 0
            
            # Recommandations
            recommendations = []
            if growth_rate > 10:
                recommendations.append("📈 Forte croissance prévue - Augmenter la production")
            elif growth_rate < -10:
                recommendations.append("📉 Déclin prévu - Réduire les stocks")
            else:
                recommendations.append("📊 Croissance stable - Maintenir la stratégie actuelle")
            
            if volatility > 50:
                recommendations.append("⚠️ Haute volatilité - Surveiller de près les ventes")
            
            if predictions['metrics']['r2'] > 0.8:
                recommendations.append("✅ Modèle très fiable - Confiance élevée dans les prédictions")
            elif predictions['metrics']['r2'] < 0.5:
                recommendations.append("⚠️ Modèle peu fiable - Améliorer la qualité des données")
            
            return {
                "product_name": product_name,
                "insights": {
                    "growth_rate": round(growth_rate, 2),
                    "volatility": round(volatility, 2),
                    "reliability": round(predictions['metrics']['r2'] * 100, 1),
                    "confidence_level": "Élevée" if predictions['metrics']['r2'] > 0.7 else "Moyenne" if predictions['metrics']['r2'] > 0.5 else "Faible"
                },
                "recommendations": recommendations,
                "key_metrics": predictions['metrics'],
                "forecast_summary": {
                    "total_predicted_sales": round(sum(forecast_data), 2),
                    "average_daily_sales": round(np.mean(forecast_data), 2),
                    "peak_predicted_sales": round(max(forecast_data), 2),
                    "lowest_predicted_sales": round(min(forecast_data), 2)
                }
            }
            
        except Exception as e:
            return {"error": f"Erreur lors de l'analyse des insights pour le produit {product_name}: {str(e)}"}

    def get_products_list(self) -> List[str]:
        """Récupère la liste de tous les produits uniques à partir des vraies données"""
        try:
            all_sales = self.get_sales_from_all_tenants()
            if not all_sales:
                return []
            
            products_set = set()
            products_map = self.get_global_products_map()
            
            print(f"Analyse de {len(all_sales)} ventes pour extraire les produits...")
            
            for sale in all_sales:
                # Essayer différentes structures de données comme dans get_product_sales_predictions
                items = sale.get('products') or sale.get('items') or sale.get('lignes') or []
                for item in items:
                    if item:  # Vérifier que l'item n'est pas None
                        prod = item.get('product') or item.get('article') or {}
                        global_id = None
                        
                        if isinstance(prod, dict):
                            global_id = prod.get('product') or prod.get('product_global') or prod.get('global_product_id')
                            # Essayer aussi les noms directs
                            product_name = prod.get('name') or prod.get('product_name') or prod.get('nom')
                            if product_name and product_name.strip():
                                products_set.add(product_name.strip())
                        
                        # Utiliser la map des produits globaux comme dans get_product_sales_predictions
                        global_id_str = str(global_id) if global_id is not None else None
                        product_name_found = products_map.get(global_id_str) if global_id_str else None
                        
                        if product_name_found and product_name_found != "Produit inconnu" and product_name_found.strip():
                            products_set.add(product_name_found.strip())
                
                # Essayer aussi directement dans la vente
                if 'product_name' in sale and sale['product_name'] and sale['product_name'].strip():
                    products_set.add(sale['product_name'].strip())
                if 'product' in sale and sale['product'] and sale['product'].strip():
                    products_set.add(sale['product'].strip())
                
                # Essayer aussi dans les champs de produits agrégés (comme dans SalesMap)
                if 'products_all' in sale and isinstance(sale['products_all'], list):
                    for prod in sale['products_all']:
                        if isinstance(prod, dict) and 'name' in prod and prod['name'] and prod['name'].strip():
                            products_set.add(prod['name'].strip())
                
                # Essayer dans les top_products
                if 'top_products' in sale and isinstance(sale['top_products'], list):
                    for prod in sale['top_products']:
                        if isinstance(prod, dict) and 'name' in prod and prod['name'] and prod['name'].strip():
                            products_set.add(prod['name'].strip())
            
            # Filtrer les produits vides et les doublons
            filtered_products = [p for p in products_set if p and p.strip() and p != "Produit inconnu"]
            
            if not filtered_products:
                print("Aucun produit trouvé dans les données, utilisation des produits de démonstration")
                return ["Produit A", "Produit B", "Produit C", "Produit D", "Produit E"]
            
            print(f"Produits trouvés: {len(filtered_products)} - {filtered_products[:10]}")
            return sorted(filtered_products)
            
        except Exception as e:
            print(f"Erreur lors de la récupération des produits: {e}")
            import traceback
            traceback.print_exc()
            return ["Produit A", "Produit B", "Produit C", "Produit D", "Produit E"]

    def get_tenant_specific_predictions(self, tenant_id: str, days_ahead: int = 30) -> Dict[str, Any]:
        """Prédictions spécifiques pour un tenant"""
        return self.create_prophet_models(tenant_id=tenant_id, days_ahead=days_ahead)
    
    def get_product_sales_predictions(self, product_name: Optional[str] = None, days_ahead: int = 30) -> Dict[str, Any]:
        """Prédictions basées sur les ventes de produits"""
        all_sales = self.get_sales_from_all_tenants()
        products_map = self.get_global_products_map()
        
        if not all_sales:
            return {"error": "Aucune donnée disponible"}
        
        # Filtrer par produit si spécifié
        if product_name:
            filtered_sales = []
            for sale in all_sales:
                items = sale.get('products') or sale.get('items') or sale.get('lignes') or []
                for item in items:
                    prod = item.get('product') or item.get('article') or {}
                    global_id = None
                    if isinstance(prod, dict):
                        global_id = prod.get('product') or prod.get('product_global') or prod.get('global_product_id')
                    
                    global_id_str = str(global_id) if global_id is not None else None
                    product_name_found = products_map.get(global_id_str) if global_id_str else "Produit inconnu"
                    
                    if product_name.lower() in product_name_found.lower():
                        filtered_sales.append(sale)
                        break
            
            if not filtered_sales:
                return {"error": f"Aucune vente trouvée pour le produit {product_name}"}
            
            all_sales = filtered_sales
        
        # Utiliser la même logique que create_prophet_models mais avec les ventes filtrées
        df = pd.DataFrame(all_sales)
        
        # Trouver le champ de date
        date_fields = ['date', 'created_at', 'timestamp', 'sale_date']
        date_field = None
        for field in date_fields:
            if field in df.columns:
                date_field = field
                break
        
        if not date_field:
            return {"error": "Aucun champ de date trouvé"}
        
        try:
            df[date_field] = pd.to_datetime(df[date_field], errors='coerce')
            df = df.dropna(subset=[date_field])
        except:
            return {"error": "Impossible de convertir les dates"}
        
        # Préparer les données pour Prophet
        daily_sales = df.groupby(df[date_field].dt.date).size().reset_index()
        daily_sales.columns = ['ds', 'y']
        daily_sales['ds'] = pd.to_datetime(daily_sales['ds'])
        
        if len(daily_sales) < 7:
            return {"error": "Pas assez de données pour créer un modèle Prophet (minimum 7 jours)"}
        
        # Créer le modèle Prophet
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            seasonality_mode='multiplicative'
        )
        
        # Entraîner le modèle
        try:
            model.fit(daily_sales)
        except Exception as e:
            return {"error": f"Erreur lors de l'entraînement du modèle: {str(e)}"}
        
        # Créer les prédictions futures
        future = model.make_future_dataframe(periods=days_ahead)
        forecast = model.predict(future)
        
        # Calculer les métriques
        train_data = forecast[forecast['ds'] <= daily_sales['ds'].max()]
        actual = daily_sales['y'].values
        predicted = train_data['yhat'].values
        
        metrics = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "mse": float(mean_squared_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
            "mape": float(np.mean(np.abs((actual - predicted) / actual)) * 100)
        }
        
        # Préparer les données pour la visualisation
        historical_data = {
            "x": daily_sales['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": daily_sales['y'].tolist(),
            "type": "scatter",
            "mode": "lines+markers",
            "name": "Données Historiques",
            "line": {"color": "#1f77b4"}
        }
        
        forecast_data = {
            "x": forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "y": forecast['yhat'].tolist(),
            "type": "scatter",
            "mode": "lines",
            "name": "Prédiction",
            "line": {"color": "#ff7f0e", "dash": "dash"}
        }
        
        return {
            "historical": historical_data,
            "forecast": forecast_data,
            "metrics": metrics,
            "model_info": {
                "product": product_name or "Tous les produits",
                "training_days": len(daily_sales),
                "forecast_days": days_ahead
            }
        }

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

# ===== ENDPOINTS PROPHET POUR PRÉDICTIONS AVANCÉES =====

@app.get("/prophet/predictions")
async def get_prophet_predictions(days_ahead: int = 30, tenant_id: Optional[str] = None):
    """Prédictions Prophet pour les ventes futures"""
    try:
        predictions = sales_analytics.create_prophet_models(tenant_id=tenant_id, days_ahead=days_ahead)
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/tenant/{tenant_id}")
async def get_tenant_predictions(tenant_id: str, days_ahead: int = 30):
    """Prédictions Prophet spécifiques pour un tenant"""
    try:
        predictions = sales_analytics.get_tenant_specific_predictions(tenant_id, days_ahead)
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/products")
async def get_product_predictions(product_name: Optional[str] = None, days_ahead: int = 30):
    """Prédictions Prophet basées sur les ventes de produits"""
    try:
        predictions = sales_analytics.get_product_sales_predictions(product_name, days_ahead)
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/products/advanced")
async def get_advanced_product_predictions(
    product_name: str = Query(..., description="Nom du produit"),
    days_ahead: int = Query(30, description="Nombre de jours à prédire"),
    include_trends: bool = Query(True, description="Inclure les tendances"),
    include_seasonality: bool = Query(True, description="Inclure la saisonnalité"),
    confidence_interval: float = Query(0.95, description="Intervalle de confiance")
):
    """Prédictions avancées Prophet pour un produit avec options détaillées"""
    try:
        predictions = sales_analytics.get_advanced_product_predictions(
            product_name, days_ahead, include_trends, include_seasonality, confidence_interval
        )
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/products/compare")
async def compare_products_predictions(
    product_names: str = Query(..., description="Noms des produits séparés par virgule"),
    days_ahead: int = Query(30, description="Nombre de jours à prédire")
):
    """Comparaison des prédictions entre plusieurs produits"""
    try:
        products = [name.strip() for name in product_names.split(',')]
        comparison = sales_analytics.compare_products_predictions(products, days_ahead)
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/products/insights")
async def get_product_insights(
    product_name: str = Query(..., description="Nom du produit"),
    days_ahead: int = Query(30, description="Nombre de jours à prédire")
):
    """Insights avancés et recommandations pour un produit"""
    try:
        insights = sales_analytics.get_product_insights(product_name, days_ahead)
        return insights
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products")
async def get_products():
    """Récupère la liste de tous les produits disponibles"""
    try:
        products = sales_analytics.get_products_list()
        return {"products": products}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/compare-tenants")
async def compare_tenant_predictions(days_ahead: int = 30):
    """Compare les prédictions entre tous les tenants"""
    try:
        all_sales = sales_analytics.get_sales_from_all_tenants()
        if not all_sales:
            return {"error": "Aucune donnée disponible"}
        
        df = pd.DataFrame(all_sales)
        tenants = df['tenant_id'].unique()
        
        comparison_data = {}
        for tenant in tenants:
            try:
                tenant_predictions = sales_analytics.get_tenant_specific_predictions(tenant, days_ahead)
                if "error" not in tenant_predictions:
                    comparison_data[tenant] = {
                        "forecast": tenant_predictions["forecast"],
                        "metrics": tenant_predictions["metrics"],
                        "model_info": tenant_predictions["model_info"]
                    }
            except:
                continue
        
        return {
            "comparison": comparison_data,
            "summary": {
                "total_tenants": len(tenants),
                "successful_models": len(comparison_data),
                "forecast_days": days_ahead
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prophet/accuracy-metrics")
async def get_prophet_accuracy_metrics(tenant_id: Optional[str] = None):
    """Métriques de précision des modèles Prophet"""
    try:
        # Créer un modèle avec 80% des données pour l'entraînement et 20% pour le test
        all_sales = sales_analytics.get_sales_from_all_tenants()
        
        if not all_sales:
            return {"error": "Aucune donnée disponible"}
        
        df = pd.DataFrame(all_sales)
        
        # Filtrer par tenant si spécifié
        if tenant_id:
            df = df[df['tenant_id'] == tenant_id]
            if df.empty:
                return {"error": f"Aucune donnée trouvée pour le tenant {tenant_id}"}
        
        # Trouver le champ de date
        date_fields = ['date', 'created_at', 'timestamp', 'sale_date']
        date_field = None
        for field in date_fields:
            if field in df.columns:
                date_field = field
                break
        
        if not date_field:
            return {"error": "Aucun champ de date trouvé"}
        
        try:
            df[date_field] = pd.to_datetime(df[date_field], errors='coerce')
            df = df.dropna(subset=[date_field])
        except:
            return {"error": "Impossible de convertir les dates"}
        
        # Préparer les données
        daily_sales = df.groupby(df[date_field].dt.date).size().reset_index()
        daily_sales.columns = ['ds', 'y']
        daily_sales['ds'] = pd.to_datetime(daily_sales['ds'])
        daily_sales = daily_sales.sort_values('ds')
        
        if len(daily_sales) < 14:
            return {"error": "Pas assez de données pour l'évaluation (minimum 14 jours)"}
        
        # Diviser les données : 80% entraînement, 20% test
        split_index = int(len(daily_sales) * 0.8)
        train_data = daily_sales[:split_index]
        test_data = daily_sales[split_index:]
        
        # Créer et entraîner le modèle
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=True,
            seasonality_mode='multiplicative'
        )
        
        model.fit(train_data)
        
        # Faire des prédictions sur les données de test
        future = model.make_future_dataframe(periods=len(test_data))
        forecast = model.predict(future)
        
        # Extraire les prédictions pour la période de test
        test_forecast = forecast[forecast['ds'] >= test_data['ds'].min()]
        test_forecast = test_forecast[test_forecast['ds'] <= test_data['ds'].max()]
        
        # Calculer les métriques
        actual = test_data['y'].values
        predicted = test_forecast['yhat'].values
        
        metrics = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "mse": float(mean_squared_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
            "mape": float(np.mean(np.abs((actual - predicted) / actual)) * 100),
            "training_days": len(train_data),
            "test_days": len(test_data),
            "accuracy_score": float(1 - (np.mean(np.abs((actual - predicted) / actual))))
        }
        
        # Données pour la visualisation de l'évaluation
        evaluation_data = {
            "actual": {
                "x": test_data['ds'].dt.strftime('%Y-%m-%d').tolist(),
                "y": actual.tolist(),
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Données Réelles",
                "line": {"color": "#1f77b4"}
            },
            "predicted": {
                "x": test_data['ds'].dt.strftime('%Y-%m-%d').tolist(),
                "y": predicted.tolist(),
                "type": "scatter",
                "mode": "lines+markers",
                "name": "Prédictions",
                "line": {"color": "#ff7f0e", "dash": "dash"}
            }
        }
        
        return {
            "metrics": metrics,
            "evaluation_data": evaluation_data,
            "model_info": {
                "tenant": tenant_id or "Tous les tenants",
                "training_period": f"{train_data['ds'].min()} à {train_data['ds'].max()}",
                "test_period": f"{test_data['ds'].min()} à {test_data['ds'].max()}"
            }
        }
        
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