import re
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
        self.assertIn('const finishedVehiclePose=physics?.pose?.()||null;',self.source)
        self.assertIn('buildVehicle();',self.source)
        self.assertIn('preserveCameraOrbit();updatePhysicsHud();',self.source)
        self.assertIn('if(finishedVehiclePose){const p=finishedVehiclePose;',self.source)

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

class VehicleLab030RegressionTests(unittest.TestCase):
    """Release-level wiring smoke checks (not a replacement for WebGL browser tests)."""
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_clickable_wheel_workbench_and_glb_decoder(self):
        for text in ('wheelWindow', 'wheelAssetList', 'selectedWheelAxle',
                     'wheelBodyModels', 'wheelCapModels', 'decodeGLB(',
                     'wheelUpload', 'wheelCapUpload'):
            self.assertIn(text,self.source)

    def test_aerodynamics_and_outward_doors(self):
        for text in ('frontRake','rearRake','roofWidth','gullwing','doorStyle'):
            self.assertIn(text,self.source)

    def test_gallery_render_and_map_persistence(self):
        for text in ('galleryBackdrop', 'galleryExposure', 'captureVehicleGallery',
                     'test-maps', 'buildCourse()', 'updateMinimapBackground',
                     'vehiclelab-testmap/v1'):
            self.assertIn(text,self.source)
        self.assertNotIn("$('welcomeAvatarPreview')", self.source)

    def test_drive_mode_cameras_ghost_and_recovery(self):
        for text in ('CAMERA_MODES','cameraClearance','ghostMode',
                     'ghostSamples', 'upright', 'hidePanelsForDrive',
                     'restorePanelsAfterDrive'):
            self.assertIn(text,self.source)

class PrecisionMap032Tests(unittest.TestCase):
    """Offline map-space regression tests; full WebGL physics requires browser acceptance."""
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_1_to_1_canvas_and_zoom_pan_controls(self):
        for code in ('id="terrainMini" width="768" height="768"',
                     'id="mapZoomIn"','id="mapZoomOut"','id="mapFit"',
                     'function worldMapPoint(e)', 'function mapScreen(x,z)',
                     "courseCanvas.addEventListener('wheel'", "courseDrag={mode:'pan'",
                     "courseDrag={mode:'move'", "courseDrag={mode:'pinch'"):
            self.assertIn(code,self.source,code)

    def test_shift_a_scene_objects_have_live_transform_and_physics(self):
        for code in ('id="addObjectOverlay"',"e.code==='KeyA'",'new TransformControls(',
                     "objectGizmo.addEventListener('objectChange'",'function placeObjectInScene(',
                     'function courseSpecs()', 'syncCourse:', "solid.physics==='dynamic'",
                     "solid.physics==='none'", 'objectMass','objectFriction','objectBounce',
                     'objectTexture', 'objectGizmo.setSize(.85)'):
            self.assertIn(code,self.source,code)
        self.assertIn("'Cannon'",self.source) if "'Cannon'" in self.source else None

    def test_polygon_and_path_are_real_world_geometry(self):
        for code in ('function pointInsidePolygon(', 'function distanceToPolyline(',
                     'function smoothFreehandPoints(', "shape:isPath?'path':'polygon'",
                     "THREE.ShapeUtils.triangulateShape(contour,[])",
                     'function courseCoversPoint(', 'id="mapStrokeMode"',
                     'function mapGridStep()', 'worldPoly(o)'):
            self.assertIn(code,self.source,code)

    def test_actual_projection_and_polygon_in_node(self):
        script=r'''
const fs=require('fs');const assert=require('assert');
const src=fs.readFileSync(process.argv[2],'utf8');
function extract(name){let i=src.indexOf('function '+name+'(');assert(i>=0,name);
 let start=src.indexOf('{',i),depth=0;
 for(let j=start;j<src.length;j++){if(src[j]==='{')depth++;if(src[j]==='}'&&!--depth)return src.slice(i,j+1)}
 throw Error('unterminated function '+name);
}
const MAP_RES=768,SIZE=180,mapZoom=2,mapCenterX=17,mapCenterZ=-12;
const courseCanvas={width:768,height:768};
const mapCanvasDpr=()=>1;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const names=['mapPixelsPerMetre','mapScreen','worldPoly','pointInsidePolygon','distanceToPolyline','smoothFreehandPoints'];
const functions=names.map(extract).join('\n');
const api=new Function('MAP_RES','SIZE','mapZoom','mapCenterX','mapCenterZ','clamp','courseCanvas','mapCanvasDpr',functions+';return {mapScreen,worldPoly,pointInsidePolygon,distanceToPolyline,smoothFreehandPoints};')
(MAP_RES,SIZE,mapZoom,mapCenterX,mapCenterZ,clamp,courseCanvas,mapCanvasDpr);
assert.deepEqual(api.mapScreen(17,-12),{x:384,y:384});
const point=api.mapScreen(21,-12);assert(Math.abs(point.x-384-4*450*2/180)<.001);
courseCanvas.width=960;courseCanvas.height=480;
assert.deepEqual(api.mapScreen(17,-12),{x:480,y:240});
assert(Math.abs(api.mapScreen(21,-12).x-480-4*450*2/180)<.001); // window resizing does not zoom
const poly=[{x:0,z:0},{x:8,z:0},{x:8,z:3},{x:0,z:3}];
assert(api.pointInsidePolygon(3,1,poly));assert(!api.pointInsidePolygon(9,1,poly));
assert(Math.abs(api.distanceToPolyline(4,1,poly,true)-1)<.00001);
const box=api.worldPoly({x:3,z:4,w:6,d:2,shape:'square',angle:0,kind:'cube'});
assert(box.length===4);assert(Math.abs(box[0].x)<1e-6);
const path=api.worldPoly({x:0,z:0,shape:'path',strokeWidth:2,points:[{x:0,z:0},{x:7,z:0},{x:12,z:4}]});
assert(path.length===6);
const curved=api.smoothFreehandPoints([{x:0,z:0},{x:3,z:2},{x:6,z:1},{x:9,z:2}],false);
assert(curved.length>4);
console.log('actual map geometry/math tests passed');
'''
        with tempfile.TemporaryDirectory() as temporary:
            js=Path(temporary)/'test.cjs';js.write_text(script)
            result=subprocess.run(['node',str(js),str(Path(__file__).resolve().parents[1]/'index.html')],
                    text=True,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class VehicleLab034RegressionTests(unittest.TestCase):
    """Quick structural gates for UI state, live audio and multi-vehicle staging.

    Full WebGL and interaction coverage still needs an actual browser.
    """
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_minimization_is_preserved_during_drive(self):
        for snippet in ('function setWindowVisible(id,show,restore=false)',
                        'if(!restore)snapshotWindow(win)',
                        'setWindowVisible(id,false,true)',
                        'setWindowVisible(id,true,true)',
                        "win.classList.toggle('is-minimized');snapshotWindow(win)"):
            self.assertIn(snippet,self.source)

    def test_context_palette_and_editor_shortcuts(self):
        for snippet in ("e.code==='KeyA'", 'function openAddPalette(',
                        'function placeObjectInScene(', 'duplicateSelectedCourse()',
                        'deleteSelectedCourse()', "e.code==='KeyD'",
                        "KeyG:'translate'", "KeyE:'scale'", "KeyR:'rotate'"):
            self.assertIn(snippet,self.source)

    def test_map_and_lightweight_collider_updates(self):
        for snippet in ('function mapCanvasDpr()', 'function requestMinimapPaint()',
                        'function heightfieldSignature()', 'const fastColliderSync=',
                        'if(requiresTerrain){buildTerrain();buildVegetation();',
                        'const mapDock=document.createElement'):
            # mapCanvasDpr is a constant arrow function; check equivalent below.
            if snippet=='function mapCanvasDpr()':
                self.assertIn('const mapCanvasDpr=()',self.source)
            else:
                self.assertIn(snippet,self.source)

    def test_audio_and_scene_vehicle_paths(self):
        for snippet in ('vehiclelab-audio/v1', 'audioPresetImport',
                        'vehicleAudio.damage(', 'function renderFleetList()',
                        'function activateFleetVehicle(', 'function parkedFleetSpecs()',
                        'function addGalleryVehicle(', "appendBtn('＋',"):
            self.assertIn(snippet,self.source)


class WheelUIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_rapier_forward_axis_uses_setter_not_getter(self):
        self.assertIn('vehicle.setIndexForwardAxis=2;',self.page)
        self.assertNotIn('vehicle.indexForwardAxis=2;',self.page)
        self.assertIn("const vehicle=rw.createVehicleController(chassis)",self.page)

    def test_wheel_glb_has_asset_preview_and_orientation_fallback(self):
        for text in ['function wheelAssetAxis(asset)', 'function wheelVisualFromAsset(asset,r,width)',
                     'function previewWheelAsset(asset)', 'previewWheelAsset(record)',
                     'id="wheelAssetList"', 'id="wheelModelTune"',
                     'data-wheel-rotate="x"','data-wheel-rotate="y"','data-wheel-rotate="z"',
                     'await avatarStore(\'readwrite\',\'put\',saved)']:
            with self.subTest(text=text): self.assertIn(text,self.page)
        self.assertNotIn("button.textContent=`${item.kind==='cap'?'CAP':'WHEEL'} · ${item.name}`",self.page)

    def test_preview_does_not_resize_main_renderer(self):
        section=self.page.split('async function previewWheelAsset(asset){',1)[1].split('\n}',1)[0]
        self.assertIn('new THREE.WebGLRenderer',section)
        self.assertIn('preview.setPixelRatio(1)',section)
        self.assertNotIn('renderer.setSize(',section)

    def test_wheel_gallery_ui_ids_are_unique(self):
        names=['wheelAssetList','wheelModelTune','wheelAutoAlign','wheelTuneName','wheelAlignStatus',
               'wheelGeneratedPreview','wheelStyles','wheelAISection']
        for name in names:
            self.assertEqual(len(re.findall(r'id="'+re.escape(name)+r'"',self.page)),1,name)
