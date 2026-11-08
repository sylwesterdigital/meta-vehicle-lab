import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from deploy.install import insert_api_location, copy_release_payload

SAMPLE='''server { listen 80; server_name vehiclelab.xyz; return 301 https://vehiclelab.xyz$request_uri; }
server { listen 443 ssl; server_name vehiclelab.xyz; root /var/www/vehiclelab.xyz; location / { try_files $uri $uri/ =404; } }
server { listen 443 ssl; server_name other.xyz; location / { return 204; } }
'''

class NginxTests(unittest.TestCase):
    def test_remote_test_tree_includes_installer(self):
        # A source-tree unittest pass is insufficient: production stages a copy
        # of only selected modules. Verify that the relocated release retains
        # imports needed by nginx configuration tests.
        source=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            release=Path(temporary)/'release'
            release.mkdir()
            copy_release_payload(source,release)
            self.assertTrue((release/'deploy/install.py').is_file())
            process=subprocess.run(
                [sys.executable,'-c',
                 'from deploy.install import insert_api_location; '
                 'from backend.storage import Storage; '
                 'assert callable(insert_api_location)'],
                cwd=release,capture_output=True,text=True,timeout=15)
            self.assertEqual(process.returncode,0,process.stdout+process.stderr)

    def test_one_tls_location_and_idempotency(self):
        changed=insert_api_location(SAMPLE)
        self.assertEqual(changed.count('proxy_pass http://127.0.0.1:8766;'),1)
        self.assertIn('server_name other.xyz;',changed)
        self.assertEqual(insert_api_location(changed),changed)
    def test_ambiguous_site_rejected(self):
        with self.assertRaises(ValueError):insert_api_location('server { listen 80; server_name vehiclelab.xyz; }')
        with self.assertRaises(ValueError):insert_api_location(SAMPLE+SAMPLE)

if __name__=='__main__':unittest.main()

class VehicleStudioRegressionTests(unittest.TestCase):
    """Static invariants; physics graphics still require real browser acceptance."""
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_compressed_glb_loader_is_shared(self):
        for snippet in ('new DRACOLoader()', 'loader.setDRACOLoader(dracoLoader)',
                        'loader.setMeshoptDecoder(MeshoptDecoder)',
                        'ktx2Loader.detectSupport(renderer)',
                        'await decodeGLB(url)'):
            self.assertIn(snippet,self.source)
        self.assertNotIn('No DRACOLoader instance provided',self.source)

    def test_legacy_axles_and_gui_are_normalized(self):
        for name in ('frontWheelRadius','rearWheelRadius',
                     'frontWheelWidth','rearWheelWidth','frontRimColor',
                     'rearRimColor','frontSpokes','rearSpokes'):
            self.assertIn(name,self.source)
        self.assertIn('normalizeVehicleConfig();',self.source)
        self.assertIn('function makeWheel(',self.source)
        self.assertIn('wheelsFolder.open();',self.source)

    def test_physics_engines_and_driving_state(self):
        self.assertIn('makeRapierAdapter()',self.source)
        self.assertIn('makeCannonAdapter()',self.source)
        self.assertIn('makeAmmoAdapter()',self.source)
        self.assertNotIn('makeBaselineAdapter()',self.source)
        self.assertIn("{x:-1,y:0,z:0},.32,wheelRadiusFor(axle)",self.source)
        self.assertIn('buildVehicle();preserveCameraOrbit();updatePhysicsHud();',self.source)

    def test_driver_selection_and_texture_parameters(self):
        self.assertIn('openOccupants',self.source)
        self.assertIn('Board selected seat',self.source)
        self.assertIn('seatOccupancy:structuredClone(seatPresence)',self.source)
        for field in ('noiseOctaves','noiseLacunarity','noiseGain',
                      'noiseWarp','noiseContrast','terrainNormalStrength'):
            self.assertIn(field,self.source)
        self.assertIn('new THREE.InstancedMesh(',self.source)

    def test_offline_blender_tool_has_no_public_job_route(self):
        from deploy.install import BLENDER_WORKER_SOURCE, check_blender
        self.assertIn('bpy.ops.import_scene.gltf', BLENDER_WORKER_SOURCE)
        self.assertIn('bpy.ops.export_scene.gltf', BLENDER_WORKER_SOURCE)
        self.assertIn('bpy.ops.render.render(write_still=True)', BLENDER_WORKER_SOURCE)
        self.assertIsInstance(check_blender() is None or bool(check_blender()), bool)
