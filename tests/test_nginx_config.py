import unittest
from deploy.install import insert_api_location

SAMPLE='''server { listen 80; server_name vehiclelab.xyz; return 301 https://vehiclelab.xyz$request_uri; }
server { listen 443 ssl; server_name vehiclelab.xyz; root /var/www/vehiclelab.xyz; location / { try_files $uri $uri/ =404; } }
server { listen 443 ssl; server_name other.xyz; location / { return 204; } }
'''

class NginxTests(unittest.TestCase):
    def test_one_tls_location_and_idempotency(self):
        changed=insert_api_location(SAMPLE)
        self.assertEqual(changed.count('proxy_pass http://127.0.0.1:8766;'),1)
        self.assertIn('server_name other.xyz;',changed)
        self.assertEqual(insert_api_location(changed),changed)
    def test_ambiguous_site_rejected(self):
        with self.assertRaises(ValueError):insert_api_location('server { listen 80; server_name vehiclelab.xyz; }')
        with self.assertRaises(ValueError):insert_api_location(SAMPLE+SAMPLE)

if __name__=='__main__':unittest.main()
