#!/usr/bin/env python3
"""
Script de test pour l'endpoint /products amélioré
Teste la récupération des vrais produits des ventes
"""

import requests
import json
import sys

API_BASE = 'http://localhost:8001'

def test_products_endpoint():
    """Test l'endpoint /products avec les vraies données"""
    try:
        print("🔍 Test de l'endpoint /products...")
        print(f"URL: {API_BASE}/products")
        
        response = requests.get(f"{API_BASE}/products", timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Réponse JSON reçue:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Vérifications
            assert "products" in data, "La réponse doit contenir une clé 'products'"
            assert isinstance(data["products"], list), "La clé 'products' doit être une liste"
            
            products = data["products"]
            print(f"\n📊 Statistiques:")
            print(f"   - Nombre de produits: {len(products)}")
            
            if products:
                print(f"   - Premier produit: {products[0]}")
                print(f"   - Dernier produit: {products[-1]}")
                print(f"   - Produits uniques: {len(set(products))}")
                
                # Vérifier qu'il n'y a pas de produits vides
                empty_products = [p for p in products if not p or not p.strip()]
                if empty_products:
                    print(f"   ⚠️  Produits vides trouvés: {empty_products}")
                else:
                    print(f"   ✅ Aucun produit vide")
                
                # Vérifier les produits de démonstration
                demo_products = ["Produit A", "Produit B", "Produit C", "Produit D", "Produit E"]
                is_demo = all(p in demo_products for p in products)
                if is_demo:
                    print(f"   📝 Utilisation des produits de démonstration")
                else:
                    print(f"   🎯 Vrais produits des ventes détectés!")
                    
            else:
                print(f"   ⚠️  Aucun produit trouvé")
                
            print(f"\n✅ Test réussi: {len(products)} produits récupérés")
            return True
            
        else:
            print(f"❌ Erreur HTTP: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Impossible de se connecter à {API_BASE}")
        print("Vérifiez que le serveur backend est démarré sur le port 8001")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Timeout lors de la requête")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

def test_health_endpoint():
    """Test l'endpoint de santé"""
    try:
        print("\n🏥 Test de l'endpoint de santé...")
        response = requests.get(f"{API_BASE}/health", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Serveur en ligne: {data}")
            return True
        else:
            print(f"❌ Serveur non disponible: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Serveur non accessible: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Test de l'endpoint /products amélioré")
    print("=" * 50)
    
    # Test de santé
    if not test_health_endpoint():
        print("\n❌ Le serveur backend n'est pas accessible")
        sys.exit(1)
    
    # Test des produits
    success = test_products_endpoint()
    
    if success:
        print("\n🎉 Tous les tests sont passés!")
    else:
        print("\n💥 Certains tests ont échoué")
        sys.exit(1)
