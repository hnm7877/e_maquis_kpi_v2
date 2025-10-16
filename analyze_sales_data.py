#!/usr/bin/env python3
"""
Script pour analyser la structure des données de ventes
et identifier les champs contenant des informations de localisation
"""

import requests
import json
from collections import defaultdict

API_BASE = "http://localhost:8001"

def analyze_sales_structure():
    """Analyse la structure des données de ventes"""
    try:
        print("Analyse de la structure des donnees de ventes...")
        
        # Récupérer les données de debug
        response = requests.get(f"{API_BASE}/debug/sales-sample")
        if response.status_code != 200:
            print(f"Erreur: {response.status_code}")
            return
        
        data = response.json()
        
        print(f"Total de ventes: {data['total_sales']}")
        print(f"Champs disponibles: {len(data['available_fields'])}")
        print(f"Champs geographiques trouves: {data['geo_related_fields']}")
        
        print("\nChamps disponibles:")
        for field in data['available_fields']:
            print(f"  - {field}")
        
        print(f"\nChamps geographiques:")
        for field in data['geo_related_fields']:
            print(f"  - {field}")
        
        print("\nAnalyse detaillee par vente:")
        for analysis in data['location_analysis']:
            print(f"\n  Vente {analysis['sale_index']} (Tenant: {analysis['tenant_id']}):")
            print(f"    Champs: {analysis['fields']}")
            if analysis['geo_fields_found']:
                print(f"    Champs geo trouves: {analysis['geo_fields_found']}")
            if analysis['location_objects']:
                print(f"    Objets de localisation: {len(analysis['location_objects'])}")
                for obj in analysis['location_objects']:
                    print(f"      - {obj['field']}: {obj['content']}")
        
        # Analyser les échantillons de ventes
        print("\nEchantillons de ventes:")
        for i, sale in enumerate(data['sample_sales']):
            print(f"\n  Vente {i}:")
            print(f"    Tenant: {sale.get('tenant_id', 'unknown')}")
            print(f"    Champs: {list(sale.keys())}")
            
            # Chercher des coordonnées dans différents formats
            coords_found = []
            
            # Champs directs
            for coord_field in ['latitude', 'lat', 'longitude', 'lon', 'lng', 'lng_lat', 'lng_lon']:
                if coord_field in sale and sale[coord_field] is not None:
                    coords_found.append(f"{coord_field}: {sale[coord_field]}")
            
            # Objets de localisation
            for location_field in ['location', 'address', 'geo', 'gps', 'coordinates', 'coords']:
                if location_field in sale and sale[location_field]:
                    coords_found.append(f"{location_field}: {sale[location_field]}")
            
            if coords_found:
                print(f"    Coordonnees trouvees: {coords_found}")
            else:
                print(f"    Aucune coordonnee trouvee")
        
        return data
        
    except Exception as e:
        print(f"❌ Erreur lors de l'analyse: {e}")
        return None

def test_location_endpoints():
    """Teste les endpoints de localisation"""
    print("\nTest des endpoints de localisation...")
    
    endpoints = [
        "/sales/map?radius_km=1",
        "/sales/locations?radius_km=1",
        "/sales/tenants-colors"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{API_BASE}{endpoint}")
            print(f"  {endpoint}: {response.status_code}")
            if response.status_code != 200:
                print(f"    Erreur: {response.text[:100]}...")
        except Exception as e:
            print(f"  {endpoint}: Erreur - {e}")

def main():
    """Fonction principale"""
    print("Analyse des donnees de ventes pour la geolocalisation")
    print("=" * 60)
    
    # Analyser la structure
    data = analyze_sales_structure()
    
    if data:
        # Tester les endpoints
        test_location_endpoints()
        
        print("\nRecommandations:")
        if data['geo_related_fields']:
            print("Des champs geographiques ont ete trouves!")
            print("Il faut adapter la methode get_sales_by_location pour utiliser ces champs.")
        else:
            print("Aucun champ geographique trouve dans les donnees.")
            print("Les donnees de ventes ne contiennent pas d'informations de localisation.")
            print("Il faut soit:")
            print("1. Ajouter des coordonnees aux donnees de ventes")
            print("2. Desactiver la fonctionnalite de carte geospatiale")
            print("3. Utiliser des donnees de localisation externes")

if __name__ == "__main__":
    main()
