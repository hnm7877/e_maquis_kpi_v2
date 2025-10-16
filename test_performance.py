#!/usr/bin/env python3
"""
Script de test des performances optimisées
"""

import requests
import time
import json
from typing import Dict, Any

API_BASE = "http://localhost:8001"

def test_endpoint_performance(endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Teste les performances d'un endpoint"""
    start_time = time.time()
    
    try:
        response = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=30)
        end_time = time.time()
        
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "response_time": end_time - start_time,
            "success": response.status_code == 200,
            "data_size": len(response.content) if response.content else 0
        }
    except Exception as e:
        end_time = time.time()
        return {
            "endpoint": endpoint,
            "status_code": 0,
            "response_time": end_time - start_time,
            "success": False,
            "error": str(e)
        }

def test_cache_performance():
    """Teste les performances du cache"""
    print("🧪 Test des performances du cache...")
    
    # Test 1: Premier appel (sans cache)
    print("\n1️⃣ Premier appel (sans cache):")
    result1 = test_endpoint_performance("/products")
    print(f"   Temps: {result1['response_time']:.2f}s")
    print(f"   Succès: {result1['success']}")
    
    # Test 2: Deuxième appel (avec cache)
    print("\n2️⃣ Deuxième appel (avec cache):")
    result2 = test_endpoint_performance("/products")
    print(f"   Temps: {result2['response_time']:.2f}s")
    print(f"   Succès: {result2['success']}")
    
    # Test 3: Statut du cache
    print("\n3️⃣ Statut du cache:")
    cache_status = test_endpoint_performance("/cache/status")
    if cache_status['success']:
        try:
            data = json.loads(requests.get(f"{API_BASE}/cache/status").text)
            print(f"   Cache valide: {data.get('databases_cache_valid', False)}")
            print(f"   Âge du cache: {data.get('cache_age_seconds', 0):.2f}s")
            print(f"   TTL: {data.get('cache_ttl_seconds', 0)}s")
            print(f"   Bases de données en cache: {data.get('cached_databases_count', 0)}")
        except:
            print("   Erreur lors de la lecture du statut du cache")
    
    # Test 4: Vider le cache
    print("\n4️⃣ Vidage du cache:")
    clear_result = requests.post(f"{API_BASE}/cache/clear")
    print(f"   Statut: {clear_result.status_code}")
    if clear_result.status_code == 200:
        print("   Cache vidé avec succès")
    
    # Test 5: Appel après vidage du cache
    print("\n5️⃣ Appel après vidage du cache:")
    result3 = test_endpoint_performance("/products")
    print(f"   Temps: {result3['response_time']:.2f}s")
    print(f"   Succès: {result3['success']}")

def test_database_optimization():
    """Teste l'optimisation des bases de données"""
    print("\n🗄️ Test de l'optimisation des bases de données...")
    
    # Test des analytics
    result = test_endpoint_performance("/analytics/sales")
    print(f"   Analytics - Temps: {result['response_time']:.2f}s")
    print(f"   Analytics - Succès: {result['success']}")
    
    # Test des prédictions
    result = test_endpoint_performance("/prophet/predictions", {"days_ahead": 30})
    print(f"   Prédictions - Temps: {result['response_time']:.2f}s")
    print(f"   Prédictions - Succès: {result['success']}")

def main():
    """Fonction principale de test"""
    print("🚀 Test des performances optimisées")
    print("=" * 50)
    
    try:
        # Vérifier que le serveur est en cours d'exécution
        response = requests.get(f"{API_BASE}/", timeout=5)
        if response.status_code != 200:
            print("❌ Le serveur n'est pas accessible")
            return
    except:
        print("❌ Le serveur n'est pas accessible. Démarrez-le avec: python main.py")
        return
    
    print("✅ Serveur accessible")
    
    # Tests de performance
    test_cache_performance()
    test_database_optimization()
    
    print("\n🎯 Tests terminés!")

if __name__ == "__main__":
    main()
