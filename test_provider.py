import os
import json
import re
import requests

BASE_URL = os.getenv("VENTE_BASE_URL", "https://ventetelegrambotrailway-production.up.railway.app").rstrip('/')
API_KEY = os.getenv("VENTE_API_KEY", "")

if not API_KEY:
    print("⚠️ تنبيه: يرجى ضبط VENTE_API_KEY في ملف .env أو كمتغير بيئي لتشغيل الفحص.")

print("=" * 70)
print("🚀 Vente Telegram Bot API Tester & Explorer")
print(f"Base URL: {BASE_URL}")
print(f"API Key:  {API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) >= 12 else f"API Key:  {'[مضبوط]' if API_KEY else '[غير مضبوط]'}")
print("=" * 70)

# Step 1: Probe Swagger & OpenAPI schema
print("\n[1/3] Searching for Swagger / OpenAPI Schema...")
schema_urls = [
    f"{BASE_URL}/api/swagger/?format=openapi",
    f"{BASE_URL}/swagger/?format=openapi",
    f"{BASE_URL}/api/swagger.json",
    f"{BASE_URL}/swagger.json",
    f"{BASE_URL}/api/schema/",
    f"{BASE_URL}/schema/",
    f"{BASE_URL}/api/openapi.json",
    f"{BASE_URL}/openapi.json",
    f"{BASE_URL}/api/swagger/",
    f"{BASE_URL}/swagger/",
]

schema = None
for url in schema_urls:
    try:
        r = requests.get(url, timeout=10)
        print(f"  GET {url} -> {r.status_code}")
        if r.status_code == 200:
            try:
                data = r.json()
                if "paths" in data:
                    schema = data
                    print(f"  🎉 Found OpenAPI JSON Schema at {url}!")
                    break
            except Exception:
                # Parse HTML for schema JSON URL
                matches = re.findall(r'["\']([^"\']+\.json[^"\']*)["\']', r.text) + re.findall(r'["\'](/api/[^"\']+)["\']', r.text)
                for m in matches:
                    if "schema" in m or "swagger" in m or "openapi" in m:
                        candidate = m if m.startswith("http") else f"{BASE_URL}{m}"
                        print(f"    Inspecting schema link from HTML: {candidate}")
                        try:
                            cr = requests.get(candidate, timeout=8)
                            if cr.status_code == 200:
                                cdata = cr.json()
                                if "paths" in cdata:
                                    schema = cdata
                                    print(f"    🎉 Found schema at: {candidate}")
                                    break
                        except Exception:
                            pass
                if schema:
                    break
    except Exception as e:
        print(f"  Error checking {url}: {e}")

if schema:
    with open("vente_swagger.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
    print("  💾 Saved full Swagger schema to vente_swagger.json")

    print("\n  📋 Available API Paths in Vente Bot:")
    paths = schema.get("paths", {})
    for path, methods in paths.items():
        m_list = [m.upper() for m in methods.keys()]
        first_m = list(methods.values())[0] if methods else {}
        desc = first_m.get("summary") or first_m.get("description") or ""
        print(f"    • {', '.join(m_list):<12} {path:<35} | {desc}")
else:
    print("  ⚠️ Direct OpenAPI schema not retrieved automatically. Proceeding to endpoint probing...")

# Step 2: Determine Working Authentication Method
print("\n[2/3] Testing Authentication Headers...")
auth_variants = [
    ("Bearer", {"Authorization": f"Bearer {API_KEY}"}),
    ("Token", {"Authorization": f"Token {API_KEY}"}),
    ("Api-Key", {"Authorization": f"Api-Key {API_KEY}"}),
    ("X-API-Key", {"X-API-Key": API_KEY}),
    ("Query Param", {"X-Empty": "1"}), # Uses ?api_key=
]

test_probe_endpoints = [
    "/api/wallet/balance/",
    "/api/wallet/",
    "/api/balance/",
    "/api/user/",
    "/api/me/",
    "/api/profile/",
    "/api/products/",
    "/api/services/",
]

working_auth = None
for name, headers in auth_variants:
    for ep in ["/api/wallet/", "/api/balance/", "/api/user/", "/api/products/"]:
        target_url = f"{BASE_URL}{ep}"
        params = {"api_key": API_KEY} if name == "Query Param" else {}
        try:
            r = requests.get(target_url, headers=headers, params=params, timeout=5)
            if r.status_code in (200, 201):
                working_auth = (name, headers, params)
                print(f"  ✅ SUCCESS with [{name}] on {ep} -> Status 200: {r.text[:120]}")
                break
            elif r.status_code not in (404, 405):
                print(f"  Response with [{name}] on {ep} -> Status {r.status_code}: {r.text[:80]}")
        except Exception as e:
            pass
    if working_auth:
        break

# Step 3: Comprehensive Endpoint Probe & Balance Discovery
print("\n[3/3] Probing All Wallet, Account & Service Endpoints...")
endpoints_to_probe = [
    "/api/wallet/balance/",
    "/api/wallet/",
    "/api/balance/",
    "/api/user/balance/",
    "/api/user/profile/",
    "/api/user/",
    "/api/users/me/",
    "/api/me/",
    "/api/profile/",
    "/api/account/",
    "/api/products/",
    "/api/services/",
    "/api/catalog/products/",
    "/api/v1/products/",
    "/api/v1/wallet/",
]

default_headers = {"Authorization": f"Bearer {API_KEY}", "X-API-Key": API_KEY}

for ep in endpoints_to_probe:
    target_url = f"{BASE_URL}{ep}"
    # Try default headers first
    try:
        r = requests.get(target_url, headers=default_headers, timeout=6)
        if r.status_code != 404:
            print(f"  🔹 GET {ep:<25} -> HTTP {r.status_code}: {r.text[:150]}")
        else:
            # Also try Token header if 404/401
            r_token = requests.get(target_url, headers={"Authorization": f"Token {API_KEY}"}, timeout=6)
            if r_token.status_code not in (404, 405):
                print(f"  🔹 GET {ep:<25} [Token Auth] -> HTTP {r_token.status_code}: {r_token.text[:150]}")
    except Exception as e:
        print(f"  ❌ Error probing {ep}: {e}")

print("\n" + "=" * 70)
print("Probe complete. If vente_swagger.json was created, review it for exact paths!")
print("=" * 70)
