#!/usr/bin/env python3
"""
Script de test pour les prédictions Prophet
Démontre toutes les fonctionnalités de prédiction avancées
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8001"
PROPHET_ENDPOINTS = [
    "/prophet/predictions",
    "/prophet/accuracy-metrics",
    "/prophet/compare-tenants",
    "/prophet/products"
]

def test_prophet_endpoint(endpoint, params=None):
    """Test un endpoint Prophet et affiche les résultats"""
    print(f"\n🔮 Test de {endpoint}")
    print("=" * 60)
    
    try:
        url = f"{BASE_URL}{endpoint}"
        response = requests.get(url, params=params, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            
            # Afficher les métadonnées
            if 'model_info' in data:
                print(f"📊 Informations du modèle:")
                for key, value in data['model_info'].items():
                    print(f"   • {key}: {value}")
            
            if 'metrics' in data:
                print(f"📈 Métriques de performance:")
                for key, value in data['metrics'].items():
                    if isinstance(value, float):
                        print(f"   • {key}: {value:.4f}")
                    else:
                        print(f"   • {key}: {value}")
            
            if 'summary' in data:
                print(f"📋 Résumé:")
                for key, value in data['summary'].items():
                    print(f"   • {key}: {value}")
            
            # Compter les graphiques disponibles
            chart_count = 0
            chart_types = []
            
            for key, value in data.items():
                if isinstance(value, dict) and ('x' in value or 'lat' in value):
                    chart_count += 1
                    chart_types.append(key)
            
            print(f"✅ Succès: {chart_count} graphiques générés")
            if chart_types:
                print(f"📊 Types de graphiques: {', '.join(chart_types)}")
            
            # Sauvegarder un échantillon pour inspection
            sample_file = f"prophet_sample_{endpoint.replace('/', '_')}.json"
            with open(sample_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Échantillon sauvé: {sample_file}")
            
        else:
            print(f"❌ Erreur {response.status_code}: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Impossible de se connecter au serveur. Assurez-vous qu'il est démarré.")
    except Exception as e:
        print(f"❌ Erreur: {e}")

def test_prophet_predictions():
    """Test les prédictions Prophet avec différents paramètres"""
    print("\n🔮 Test des Prédictions Prophet")
    print("=" * 60)
    
    # Test prédictions générales
    test_prophet_endpoint("/prophet/predictions", {"days_ahead": 30})
    
    # Test prédictions avec différents horizons
    for days in [7, 14, 30, 60]:
        print(f"\n📅 Test avec {days} jours de prédiction")
        test_prophet_endpoint("/prophet/predictions", {"days_ahead": days})

def test_tenant_specific_predictions():
    """Test les prédictions spécifiques par tenant"""
    print("\n🏢 Test des Prédictions par Tenant")
    print("=" * 60)
    
    try:
        # Récupérer la liste des tenants
        response = requests.get(f"{BASE_URL}/analytics/sales", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'sales_by_tenant' in data:
                tenants = list(data['sales_by_tenant'].keys())[:3]  # Tester les 3 premiers tenants
                
                for tenant in tenants:
                    print(f"\n🏢 Test pour le tenant: {tenant}")
                    test_prophet_endpoint(f"/prophet/tenant/{tenant}", {"days_ahead": 30})
            else:
                print("⚠️ Aucun tenant trouvé dans les données")
        else:
            print("❌ Impossible de récupérer la liste des tenants")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des tenants: {e}")

def test_product_predictions():
    """Test les prédictions basées sur les produits"""
    print("\n📦 Test des Prédictions par Produit")
    print("=" * 60)
    
    try:
        # Récupérer la liste des produits
        response = requests.get(f"{BASE_URL}/products/globals", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'products' in data and data['products']:
                # Tester avec les 3 premiers produits
                products = data['products'][:3]
                
                for product in products:
                    print(f"\n📦 Test pour le produit: {product['name']}")
                    test_prophet_endpoint("/prophet/products", {
                        "product_name": product['name'],
                        "days_ahead": 30
                    })
            else:
                print("⚠️ Aucun produit trouvé")
        else:
            print("❌ Impossible de récupérer la liste des produits")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des produits: {e}")

def test_accuracy_metrics():
    """Test les métriques de précision"""
    print("\n📊 Test des Métriques de Précision")
    print("=" * 60)
    
    # Test métriques générales
    test_prophet_endpoint("/prophet/accuracy-metrics")
    
    # Test métriques par tenant
    try:
        response = requests.get(f"{BASE_URL}/analytics/sales", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if 'sales_by_tenant' in data:
                tenants = list(data['sales_by_tenant'].keys())[:2]  # Tester les 2 premiers tenants
                
                for tenant in tenants:
                    print(f"\n🏢 Métriques pour le tenant: {tenant}")
                    test_prophet_endpoint("/prophet/accuracy-metrics", {"tenant_id": tenant})
    except Exception as e:
        print(f"❌ Erreur lors du test des métriques par tenant: {e}")

def test_tenant_comparison():
    """Test la comparaison entre tenants"""
    print("\n⚖️ Test de la Comparaison entre Tenants")
    print("=" * 60)
    
    # Test comparaison avec différents horizons
    for days in [14, 30, 60]:
        print(f"\n📅 Comparaison avec {days} jours de prédiction")
        test_prophet_endpoint("/prophet/compare-tenants", {"days_ahead": days})

def test_performance():
    """Test les performances des endpoints Prophet"""
    print("\n⚡ Test de Performance des Endpoints Prophet")
    print("=" * 60)
    
    for endpoint in PROPHET_ENDPOINTS:
        start_time = time.time()
        test_prophet_endpoint(endpoint)
        end_time = time.time()
        duration = end_time - start_time
        print(f"⏱️ {endpoint}: {duration:.2f}s")

def main():
    """Fonction principale de test"""
    print("🔮 Test des Prédictions Prophet - Multi-Tenant Sales Analytics")
    print("=" * 80)
    print(f"🕐 Début des tests: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test de connectivité
    try:
        health_response = requests.get(f"{BASE_URL}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ Serveur accessible")
        else:
            print("⚠️ Serveur accessible mais problème de santé")
    except:
        print("❌ Serveur non accessible. Démarrez-le avec: python main.py")
        return
    
    # Tests des prédictions Prophet
    test_prophet_predictions()
    test_tenant_specific_predictions()
    test_product_predictions()
    test_accuracy_metrics()
    test_tenant_comparison()
    test_performance()
    
    print(f"\n🎉 Tests terminés: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n📋 Résumé des fonctionnalités Prophet testées:")
    print("   • Prédictions temporelles avec Prophet")
    print("   • Intervalles de confiance et incertitude")
    print("   • Métriques de performance (MAE, RMSE, R², MAPE)")
    print("   • Prédictions spécifiques par tenant")
    print("   • Prédictions basées sur les produits")
    print("   • Comparaison multi-tenants")
    print("   • Validation croisée et évaluation des modèles")
    
    print("\n🔗 Pour utiliser les prédictions dans votre frontend:")
    print("   1. Ouvrez prophet_dashboard.html dans votre navigateur")
    print("   2. Utilisez les endpoints /prophet/* pour intégrer dans votre app")
    print("   3. Les données sont optimisées pour Plotly.js côté client")
    
    print("\n📚 Documentation Prophet: https://facebook.github.io/prophet/")

if __name__ == "__main__":
    main()
