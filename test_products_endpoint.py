import requests
import json

try:
    response = requests.get('http://localhost:8001/products')
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Content: {response.text}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"JSON Data: {json.dumps(data, indent=2)}")
        if 'products' in data:
            print(f"Number of products: {len(data['products'])}")
            if data['products']:
                print(f"First few products: {data['products'][:5]}")
        else:
            print("No 'products' key in response")
    else:
        print(f"Error: {response.status_code} - {response.text}")
        
except Exception as e:
    print(f"Error: {e}")
