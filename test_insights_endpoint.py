#!/usr/bin/env python3
"""
Script de test pour l'endpoint /prophet/products/insights
Teste la récupération des insights pour un produit
"""

import requests
import json
import sys

API_BASE = 'http://localhost:8001'

def test_insights_endpoint():
    """Test l'endpoint /prophet/products/insights"""
    try:
        print("🔍 Test de l'endpoint /prophet/products/insights...")
        
        # Test avec un produit réel
        product_name = "Awa"  # Un des produits trouvés dans la liste
        url = f"{API_BASE}/prophet/products/insights?product_name={product_name}"
        print(f"URL: {url}")
        
        response = requests.get(url, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Réponse JSON reçue:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Vérifications
            assert "insights" in data, "La réponse doit contenir une clé 'insights'"
            insights = data["insights"]
            
            print(f"\n📊 Vérification des insights:")
            print(f"   - growth_rate: {insights.get('growth_rate', 'N/A')}")
            print(f"   - volatility: {insights.get('volatility', 'N/A')}")
            print(f"   - reliability: {insights.get('reliability', 'N/A')}")
            print(f"   - confidence_level: {insights.get('confidence_level', 'N/A')}")
            
            if "recommendations" in data:
                recommendations = data["recommendations"]
                print(f"   - recommendations: {len(recommendations)} recommandations")
                for i, rec in enumerate(recommendations[:3]):  # Afficher les 3 premières
                    print(f"     {i+1}. {rec}")
            
            print(f"\n✅ Test réussi: Insights récupérés pour '{product_name}'")
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

if __name__ == "__main__":
    print("🚀 Test de l'endpoint /prophet/products/insights")
    print("=" * 50)
    
    success = test_insights_endpoint()
    
    if success:
        print("\n🎉 Test réussi!")
    else:
        print("\n💥 Test échoué")
        sys.exit(1)

