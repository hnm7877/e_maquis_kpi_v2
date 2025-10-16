#!/usr/bin/env python3
"""
Analyse directe des données de ventes sans serveur
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import SalesAnalytics

def analyze_sales_data():
    """Analyse directe des données de ventes"""
    try:
        print("Analyse directe des donnees de ventes...")
        
        # Créer une instance de SalesAnalytics
        analytics = SalesAnalytics()
        
        # Récupérer toutes les ventes
        all_sales = analytics.get_sales_from_all_tenants()
        
        if not all_sales:
            print("Aucune donnee de vente trouvee")
            return
        
        print(f"Total de ventes: {len(all_sales)}")
        
        # Analyser toutes les ventes pour trouver celles avec des coordonnées
        sample_sales = all_sales[:10]  # Prendre plus d'échantillons
        
        # Analyser TOUTES les ventes pour les champs disponibles
        available_fields = set()
        geo_fields = []
        sales_with_coords = []
        
        for sale in all_sales:  # Analyser TOUTES les ventes
            for key in sale.keys():
                available_fields.add(key)
                if any(geo_word in key.lower() for geo_word in ['lat', 'lon', 'coord', 'geo', 'location', 'address', 'gps']):
                    geo_fields.append(key)
            
            # Vérifier si cette vente a des coordonnées
            lat = sale.get('latitude')
            lon = sale.get('longitude')
            if lat is not None and lon is not None:
                try:
                    lat_val = float(lat)
                    lon_val = float(lon)
                    if -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
                        sales_with_coords.append({
                            'tenant_id': sale.get('tenant_id'),
                            'latitude': lat_val,
                            'longitude': lon_val,
                            'sale_id': sale.get('_id')
                        })
                except:
                    pass
        
        print(f"\nChamps disponibles ({len(available_fields)}):")
        for field in sorted(available_fields):
            print(f"  - {field}")
        
        print(f"\nChamps geographiques trouves ({len(set(geo_fields))}):")
        for field in set(geo_fields):
            print(f"  - {field}")
        
        print(f"\nVentes avec coordonnees trouvees: {len(sales_with_coords)}")
        if sales_with_coords:
            print("Premieres ventes avec coordonnees:")
            for i, sale_coord in enumerate(sales_with_coords[:5]):
                print(f"  {i+1}. Tenant: {sale_coord['tenant_id']}")
                print(f"     Latitude: {sale_coord['latitude']}")
                print(f"     Longitude: {sale_coord['longitude']}")
                print(f"     Sale ID: {sale_coord['sale_id']}")
        
        # Analyser quelques échantillons de ventes
        print(f"\nAnalyse detaillee par vente (echantillon de {len(sample_sales)}):")
        for i, sale in enumerate(sample_sales):
            print(f"\n  Vente {i} (Tenant: {sale.get('tenant_id', 'unknown')}):")
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
        
        # Tester la méthode get_sales_by_location
        print("\nTest de la methode get_sales_by_location:")
        try:
            locations = analytics.get_sales_by_location(radius_km=1.0)
            print(f"  Nombre de localisations trouvees: {len(locations)}")
            if locations:
                print(f"  Premier exemple: {locations[0]}")
            else:
                print("  Aucune localisation trouvee")
        except Exception as e:
            print(f"  Erreur: {e}")
        
        return {
            'total_sales': len(all_sales),
            'available_fields': list(available_fields),
            'geo_fields': list(set(geo_fields)),
            'has_coordinates': len(sales_with_coords) > 0,
            'sales_with_coords': len(sales_with_coords),
            'coords_examples': sales_with_coords[:3] if sales_with_coords else []
        }
        
    except Exception as e:
        print(f"Erreur lors de l'analyse: {e}")
        return None

def main():
    """Fonction principale"""
    print("Analyse directe des donnees de ventes")
    print("=" * 50)
    
    result = analyze_sales_data()
    
    if result:
        print(f"\nResume:")
        print(f"  Total ventes: {result['total_sales']}")
        print(f"  Champs disponibles: {len(result['available_fields'])}")
        print(f"  Champs geographiques: {len(result['geo_fields'])}")
        print(f"  Ventes avec coordonnees: {result['sales_with_coords']}")
        print(f"  A des coordonnees: {result['has_coordinates']}")
        
        if result['has_coordinates']:
            print("\nDes ventes avec coordonnees ont ete trouvees!")
            print("Exemples de coordonnees:")
            for i, coord in enumerate(result['coords_examples']):
                print(f"  {i+1}. Tenant: {coord['tenant_id']}, Lat: {coord['latitude']}, Lon: {coord['longitude']}")
            print("La methode get_sales_by_location devrait fonctionner avec ces donnees.")
        else:
            print("\nAucune vente avec coordonnees trouvee.")
            print("Les donnees de ventes ne contiennent pas d'informations de localisation.")

if __name__ == "__main__":
    main()
