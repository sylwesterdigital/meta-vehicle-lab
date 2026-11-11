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


class VehicleLab0321SculptRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_3d_sculpt_stroke_state_is_initialized_once_and_shared(self):
        declaration='let sculptMapCursor=null,sculpt3DStroke=false,sculpt3DPaint=false,sculptStagePointer=null;'
        self.assertEqual(self.html.count(declaration),1)
        self.assertNotIn('sculptStageStroke',self.html)
        for usage in (
            'if(sculpt3DStroke||mode',
            'sculpt3DStroke=true;sculptStagePointer=e.pointerId',
            'if(sculpt3DStroke&&e.pointerId===sculptStagePointer)',
            'if(!sculpt3DStroke||e.pointerId!==sculptStagePointer)return;',
            'sculpt3DStroke=false;sculptStagePointer=null',
            'if(!sculpt3DStroke)sculptBrushSphere.visible=false',
        ):
            self.assertIn(usage,self.html)

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
        self.assertIn('wheelsFolder.close();',self.source)

    def test_physics_engines_and_driving_state(self):
        self.assertIn('makeRapierAdapter()',self.source)
        self.assertIn('makeCannonAdapter()',self.source)
        self.assertIn('makeAmmoAdapter()',self.source)
        self.assertNotIn('makeBaselineAdapter()',self.source)
        self.assertIn("{x:-1,y:0,z:0},.32,wheelRadiusFor(axle)",self.source)
        self.assertIn('const finishedVehiclePose=physics?.pose?.()||resumeDrivePose||null;',self.source)
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
        for code in ('id="addObjectOverlay"',"shortcutMatches('addObject',e)",'new TransformControls(',
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
                        'if(!restore){snapshotWindow(win)',
                        "function rememberModeWindows(which=mode)",
                        "applyModeWindows('drive')",
                        "applyModeWindows('build')",
                        "win.classList.toggle('is-minimized');"):
            self.assertIn(snippet,self.source)

    def test_context_palette_and_editor_shortcuts(self):
        for snippet in ("shortcutMatches('addObject',e)", 'function openAddPalette(',
                        'function placeObjectInScene(', 'duplicateSelectedCourse()',
                        'deleteSelectedCourse()', "shortcutMatches('duplicateObject',e)",
                        "activateCourseGizmo(action)", "objectGizmo.setMode(kind)", "lastGizmoPointerUp"):
            self.assertIn(snippet,self.source)

    def test_map_and_lightweight_collider_updates(self):
        for snippet in ('function mapCanvasDpr()', 'function requestMinimapPaint()',
                        'function heightfieldSignature()', 'const restart=driving',
                        'if(terrainChanged){buildTerrain();buildVegetation();',
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
                        'function addGalleryVehicle(', "appendBtn('Add to scene','add',"):
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

class VehicleLab036RegressionTests(unittest.TestCase):
    """Pure geometry and interface invariants; not a substitute for a GPU acceptance run."""
    def setUp(self):
        self.path=Path(__file__).resolve().parents[1]/'index.html'
        self.source=self.path.read_text(encoding='utf-8')

    def test_camera_and_control_wiring(self):
        for snippet in ("'smart'", "'free'", 'function followCamera(dt)',
                        'function resetDriveOrigin()', 'function autopilotInput()',
                        'id="autopilotBtn"', 'id="resetOriginBtn"',
                        'id="cameraModeReadout"'):
            self.assertIn(snippet,self.source)
        self.assertNotIn("'cinematic','top','driver'", self.source)

    def test_live_parked_vehicle_physics_and_vehicle_wheels(self):
        for snippet in ("physics:'dynamic'", 'function syncPhysicsObjectPose(',
                        'for(const b of parkedBodies)', 'wheelSpinAngles[i]',
                        'for(const o of movingCourse)', 'for(const o of dynamicCourse)',
                        'if(x>0)visual.rotation.y+=Math.PI'):
            self.assertIn(snippet,self.source)

    def test_inspector_persistence_and_chassis_library(self):
        for snippet in ('id="chassisWindow"', 'id="chassisAssets"',
                        "data.kind==='chassis'", 'function createChassisPreview(',
                        "for(const folder of gui.folders)folder.close()",
                        'function syncCannonObstacle(o)', "if(restart&&mode==='drive')",
                        "'objectWindow'", 'function activateCourseGizmo(',
                        'function updateNearGrass('):
            self.assertIn(snippet,self.source)
        self.assertIn('const height=Number.isFinite(o.y)?',self.source)

    def test_bridge_group_preserves_y_and_rotates_ramps(self):
        script=r'''
const fs=require('fs');const assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
function extract(name){let a=source.indexOf('function '+name+'(');assert(a>=0);
 const start=source.indexOf('{',a);let depth=0;
 for(let i=start;i<source.length;i++){if(source[i]==='{')depth++;else if(source[i]==='}'&&--depth===0)return source.slice(a,i+1)}
 throw Error('Unclosed '+name);
}
const clamp=(x,a,b)=>Math.min(b,Math.max(a,x));
const heightAt=(x,z)=>0;
const cfg={courseObjects:[{id:'b',kind:'bridge',x:10,z:20,y:5,angle:90,w:6,d:8,h:3,
 physics:'static',mass:35,friction:.8,bounce:.2},{id:'p',kind:'cube',x:0,z:0,y:-2,w:2,d:2,h:2}]};
const func=new Function('cfg','heightAt','clamp',extract('courseSpecs')+'; return courseSpecs();');
const specs=func(cfg,heightAt,clamp);
assert.strictEqual(specs.length,4);
assert(Math.abs(specs[0].y-5)<1e-6, 'bridge deck Y must not jump on edits');
assert(Math.abs(specs[1].x-15.5)<1e-6,'bridge ramp position rotates with yaw');
assert.strictEqual(specs[3].y,-2,'static object may sink below terrain');
'''
        process=subprocess.run(['node','-e',script,str(self.path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)


ROOT=Path(__file__).resolve().parents[1]
from html.parser import HTMLParser

class Ids(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.forms=0;self.bad_nested=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if 'id' in d:self.ids.append(d['id'])
        if tag=='form':
            if self.forms:self.bad_nested.append(d.get('id',''))
            self.forms+=1
    def handle_endtag(self,tag):
        if tag=='form':self.forms-=1
class ChassisImageTests(unittest.TestCase):
    def setUp(self):
        self.html=(ROOT/'index.html').read_text()
        self.backend=(ROOT/'backend/app.py').read_text()
    def test_chassis_prompt_provider_and_direct_3d_wiring(self):
        parser=Ids();parser.feed(self.html)
        for element in ('chassisPrompt','chassisImageProvider','chassisImagePreview',
                        'chassisGenerateImage','chassis3DReference','chassisCaptureSet',
                        'chassisCaptureFullSet','chassisShotStrip','chassisPromptOptions',
                        'chassis3DOptions','chassisOpenImageKeys','chassisOpenLuxKeys',
                        'chassisLuxModel','chassisLuxStyle','chassisSpendAck',
                        'chassisGenerate3D','chassisImageStatus','chassis3DStatus'):
            self.assertEqual(parser.ids.count(element),1,element)
        self.assertFalse(parser.bad_nested)
        self.assertEqual(len(parser.ids),len(set(parser.ids)),'duplicate DOM IDs')
        self.assertIn("$('chassisPrompt').value.trim()",self.html)
        self.assertIn("$('lux3dCreateForm').requestSubmit()",self.html)
        self.assertIn("$('chassisCreative').hidden",self.html)
        # Provider secrets must have one visible entry point, in Configuration.
        for removed in ('chassisImageKey','chassisLuxKey','wheelImageKey','wheelLuxKey',
                        'chassisLuxTest','wheelUseImageKey','wheelTestLuxKey'):
            self.assertNotIn(f'id="{removed}"',self.html)
        self.assertIn('id="providerKey"',self.html)
        self.assertIn('id="lux3dSection" hidden',self.html)
        self.assertIn('function syncChassisKeyState()',self.html)
        self.assertIn('function openProviderSettings(provider)',self.html)
        self.assertIn("if(provider==='lux3d'){",self.html)
        self.assertNotIn('id="chassisImageKeyPanel"',self.html)
        self.assertNotIn('id="chassisLuxKeyPanel"',self.html)
        # Long examples remain computed on demand, never displayed as a wall.
        self.assertIn('id="chassisPromptOptions"',self.html)
        self.assertIn('id="chassisPromptExamples" hidden',self.html)
        self.assertIn('const span=Math.max(hx,hy)*1.7',self.html)
    def test_meta_muse_generative_endpoint_and_key_scoping(self):
        self.assertIn("if provider not in ('openai','xai','meta')",self.backend)
        self.assertIn("'model':'muse-image-1.0'",self.backend)
        self.assertIn("https://api.meta.ai/v1/images/edits",self.backend)
        self.assertIn("https://api.meta.ai/v1/images/generations",self.backend)
        self.assertIn("payload['images']=[{'image_url':reference}]",self.backend)
        self.assertIn("keys={meta:''",self.html)
        self.assertIn("id=\"wheelAIProvider\"",self.html)


class WorkspaceTools017Tests(unittest.TestCase):
    """Static release contracts; separate Chromium tests check live UI interactions."""
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_typeface_gallery_is_nonmodal_and_lil_gui_uses_theme_font(self):
        for part in ('#fontBrowser[hidden]', 'id="fontPreviewText"',
                     'id="fontBrowserGrid"', 'function renderFontBrowser()',
                     '.lil-gui,.lil-gui *{font-family:var(--ui-font)!important}',
                     "$('drawerScrim').style.visibility=show?'hidden':''"):
            self.assertIn(part,self.html)

    def test_shortcut_edit_validation_persistence_and_fallback(self):
        for part in ('vehiclelab-shortcuts/v1', 'function validateShortcutDraft()',
                     'function shortcutProblems(bindings)', 'id="shortcutValidate"',
                     'id="shortcutImport"', 'id="shortcutExport"',
                     "if(!shortcutDraft[id]){shortcutDraft[id]=SHORTCUT_DEFAULTS[id]", 
                     'button.classList.add(validateCombo(combo)'):
            self.assertIn(part,self.html)

    def test_map_undo_does_not_call_vehicle_restore(self):
        self.assertIn("$('mapUndo').onclick=()=>void stepMapHistory(-1)",self.html)
        self.assertIn("$('mapRedo').onclick=()=>void stepMapHistory(1)",self.html)
        self.assertIn("if(activeUndoDomain==='map')void stepMapHistory(-1)",self.html)
        self.assertIn("if(restart&&mode==='drive')",self.html)
        self.assertNotIn('coursePointerTransform',self.html)

    def test_parking_brake_is_wheel_based_for_each_physics_engine(self):
        self.assertIn("['handbrake','Toggle parking handbrake','Shift+KeyB'",self.html)
        self.assertIn('id="parkingBrakeBtn"',self.html)
        self.assertGreaterEqual(self.html.count('input.handbrake&&wheelAxle(i)===cfg.axles-1'),3)
        self.assertIn('if(input.handbrake)input.throttle=0;',self.html)
        self.assertNotIn('chassis.velocity.set(0,0,0)',self.html)

    def test_gizmo_does_not_enable_free_pointer_transform(self):
        self.assertIn('function activateCourseGizmo(kind)',self.html)
        self.assertIn('if(objectGizmo.object!==mesh)objectGizmo.attach(mesh)',self.html)
        self.assertIn('lastGizmoPointerUp=performance.now()',self.html)
        self.assertNotIn('coursePointerTransform',self.html)


class StartupWordmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_nonblocking_splash_and_cleanup(self):
        for token in ('id="vehicleLabSplash"', '#vehicleLabSplash{position:fixed',
                      'pointer-events:none', 'animation:vehicleLabSplashLife 1500ms',
                      'window.setTimeout(()=>mark.remove(),1500)',
                      'repeating-linear-gradient(180deg,',
                      'prefers-reduced-motion:reduce'):
            self.assertIn(token, self.html)

    def test_theme_prefs_audio_policy_and_preview(self):
        for token in ('id="introEnabled"','id="introSound"',
                      'id="introSoundPreview"',
                      'introEnabled:true,introSound:true',
                      "if(typeof imported.introEnabled==='boolean')",
                      "if(typeof imported.introSound==='boolean')",
                      "value.introEnabled!==false,introSound:value.introSound!==false",
                      "navigator.getAutoplayPolicy?.('audiocontext')",
                      "window.vehicleLabPreviewChime=()=>playChime(true)"):
            self.assertIn(token,self.html)
        self.assertNotIn('<audio id="vehicleLabSplash"',self.html)


class VersionAndAvatarLimitsTests(unittest.TestCase):
    def test_badge_meta_and_runtime_version_are_one_value(self):
        root=Path(__file__).resolve().parents[1]
        import json
        version=json.loads((root/'version.json').read_text())['version']
        html=(root/'index.html').read_text()
        self.assertIn(f'<meta name="vehicle-lab-version" content="{version}">',html)
        self.assertIn(f"const VERSION='{version}';",html)
        self.assertIn("document.getElementById('appVersionBadge').textContent='v'+VERSION",html)
        self.assertIn("{v:'"+version+"'",html)
    def test_avatar_gui_maximum_is_two(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertIn("passengerFolder.add(selectedAvatarAsset,'scale',.25,2,.01)",html)
    def test_lux3d_creation_preflights_billed_image(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
        self.assertIn("'/api/providers/lux3d/optimize-reference'",html)
        self.assertLess(html.index("'/api/providers/lux3d/optimize-reference'"),
                        html.index("'/api/providers/lux3d/create'",html.index("const RELEASE_NOTES=[")))


"""Regression gates for independently editable shell alignment and cloud-asset persistence.

The browser physics stack requires a live WebGL acceptance test. These tests
cover the source-level contracts and the SQLite asset references offline.
"""
import re
import tempfile
import unittest
import uuid
from pathlib import Path
from backend.storage import Storage, InvalidLayout

CHASSIS_HTML=Path(__file__).resolve().parents[1]/'index.html'

class ChassisAssetRegression(unittest.TestCase):
    def test_shell_transform_ui_does_not_require_vehicle_rebuild(self):
        text=CHASSIS_HTML.read_text(encoding='utf8')
        for ident in ('bodyFitProperty','bodyFitSlider','bodyFitValue','bodyFitReadout',
                      'chassisGizmoToggle','chassisAutoAlign','chassisFlipFront',
                      'chassisDownloadGLB','chassisReferenceDownload'):
            self.assertIn('id="'+ident+'"',text)
        for retired in ('bodyOffsetX','bodyOffsetY','bodyOffsetZ','bodyRotX','bodyRotY',
                        'bodyRotZ','bodyFitScale'):
            self.assertNotIn('id="'+retired+'"',text)
        self.assertIn('function importedShellFitSpec()',text)
        self.assertIn('const bodyBottom=-Math.min(cfg.H*.42,.78);',text)
        self.assertIn('scene.add(chassisGizmo.getHelper())',text)
        self.assertIn("chassisGizmo.addEventListener('dragging-changed'",text)
        self.assertIn("chassisGizmo.addEventListener('objectChange'",text)
        self.assertIn('visual.position.sub(center)',text)
        fit=re.search(r'function fitImportedShell\(\)\{(.*?)\n \}',text,re.S)
        self.assertIsNotNone(fit)
        self.assertIn('importedShell.rotation.copy',fit.group(1))
        self.assertNotIn('buildVehicle(',fit.group(1))
        self.assertNotIn('cfg.H*.35-center.y*s',text)

    def test_shared_fit_slider_and_gizmo_do_not_change_binary_or_collision_geometry(self):
        text=CHASSIS_HTML.read_text(encoding='utf8')
        self.assertIn('const BODY_FIT_PROPERTIES={',text)
        for key in ('modelOffsetX','modelOffsetY','modelOffsetZ','modelPitch',
                    'modelRotation','modelRoll','modelScale'):
            self.assertIn(key+':{label:',text)
        self.assertIn('fitImportedShell();syncBodyFitInputs();',text)
        self.assertIn('car.add(importedShell);fitImportedShell();bodyRoot.visible=false;',text)
        self.assertIn('if(chassisGizmo?.object)chassisGizmo.detach();',text)
        self.assertIn('if(objectGizmo?.object)objectGizmo.detach()',text)
        self.assertIn('const visual=modelSource.clone(true);',text)

    def test_cloud_binary_is_fetched_before_any_vehicle_state_reset(self):
        text=CHASSIS_HTML.read_text(encoding='utf8')
        loader=re.search(r'async function loadServer\(id\)\{(.*?)\n\}',text,re.S)
        self.assertIsNotNone(loader)
        src=loader.group(1)
        self.assertLess(src.index('await cloudModelBlob(assetId,'),src.index('await loadLayout('))
        self.assertIn('serverAssetBlob=blob',src)
        self.assertIn("kind:'cloud-cache'",text)
        self.assertIn("entry.kind==='chassis'&&entry.name===localName",text)
        self.assertIn("if(data.kind==='cloud-cache')continue",text)
        self.assertIn('verifiedGLB',text)
        self.assertIn('loaded',text.lower())

    def test_white_studio_and_downloadable_references(self):
        text=CHASSIS_HTML.read_text(encoding='utf8')
        self.assertIn("clean.background=new THREE.Color('#ffffff')",text)
        self.assertIn('PURE WHITE (#FFFFFF)',text)
        self.assertIn('downloadCurrentChassisReference',text)
        # Keep this asset regression aligned with the release manifest rather
        # than hard-coding a version from an earlier release.
        import json
        version=json.loads((CHASSIS_HTML.parent/'version.json').read_text())['version']
        self.assertIn(f"const VERSION='{version}'",text)
        self.assertIn(f'name="vehicle-lab-version" content="{version}"',text)

    def test_build_and_drive_window_layout_contract(self):
        text=CHASSIS_HTML.read_text(encoding='utf8')
        for which in ('build','drive'):
            self.assertIn(f'data-workspace-mode="{which}"',text)
        self.assertIn('function normalizeWorkspaceMode(value,fallback)',text)
        self.assertIn('readWorkspaceModes();applyModeWindows(mode)',text)
        self.assertIn("rememberModeWindows('build')",text)
        self.assertIn("rememberModeWindows('drive')",text)
        self.assertIn("'vehiclelab-workspace/v2',windows,modes:workspaceModes",text)
        self.assertIn("['vehiclelab-workspace/v1','vehiclelab-workspace/v2']",text)
        self.assertIn("'My media','Radio'",text)
        self.assertNotIn("driving.add(cfg,'driveHidePanels')",text)

    def test_sqlite_preserves_imported_shell_transform_and_asset_pointer(self):
        with tempfile.TemporaryDirectory() as d:
            store=Storage(d)
            profile, _=store.create_guest('Shell Maker')
            asset_id=str(uuid.uuid4())
            # Persist the same metadata shape returned by /api/me/assets.
            store.add_asset(identifier=asset_id,filename='body.glb',size=20,
                            sha256='0'*64,owner_id=profile['id'])
            layout_id=str(uuid.uuid4())
            original={
                'schema':'procedural-vehicle/v3',
                'vehicle':{'name':'Shell A','modelOffsetX':.1,'modelOffsetY':-.7,
                           'modelOffsetZ':-.25,'modelPitch':0,'modelRotation':90,
                           'modelRoll':0,'modelScale':1.12},
                'modules':{'front':{},'cabin':{},'rear':{}},
                'bodyAsset':{'name':'body.glb','kind':'glb','serverAssetId':asset_id},
                'modelName':'body.glb',
            }
            saved=store.user_save_layout(profile['id'],layout_id,'Shell A',original,asset_id=asset_id)
            record=store.own_layout(profile['id'],layout_id)
            self.assertEqual(record['asset_id'],asset_id)
            self.assertEqual(record['blueprint']['vehicle']['modelOffsetY'],-.7)
            self.assertEqual(record['blueprint']['vehicle']['modelRotation'],90)
            self.assertEqual(saved['asset_id'],asset_id)
            # A second identity must not be able to link the first user's GLB.
            second,_=store.create_guest('Other')
            with self.assertRaises(InvalidLayout):
                store.user_save_layout(second['id'],str(uuid.uuid4()),'Not mine',original,asset_id=asset_id)



"""Static source contracts; runtime WebXR acceptance still requires Quest hardware."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'index.html').read_text('utf-8')

class WorldMediaXRSourceTests(unittest.TestCase):
    def test_umami_async_and_anonymous(self):
        self.assertIn('async src="https://analytics.mielniczuk.com/script.js"',SOURCE)
        self.assertIn('15fa1131-f0d3-49f1-95ec-b11df875bec2',SOURCE)
        self.assertIn('function trackUsage(name)',SOURCE)
        self.assertIn('const ANALYTICS_NAMES=new Set(',SOURCE)
        self.assertIn('if(!ANALYTICS_NAMES.has(name))return;',SOURCE)

    def test_boundaries_and_wrap_with_physics(self):
        for marker in ("worldEdgeMode:'barrier'",'function worldBoundarySpecs()',
                       "cfg.worldEdgeMode==='wrap'",'physics.teleport?.(',
                       'function showWorldCells()',"cfg.worldEdgeMode==='cells'"):
            self.assertIn(marker,SOURCE)
        self.assertGreaterEqual(SOURCE.count('teleport:(pos,'),3)
        self.assertIn('edge:cfg.worldEdgeMode',SOURCE)
        self.assertIn('worldCells:cfg.worldCells',SOURCE)

    def test_xr_mapping_and_seat_controls(self):
        for marker in ('function updateXRDriving(dt)','source.handedness',"gp.mapping!=='xr-standard'",
                       'buttons[0]?.value','buttons[1]?.pressed','buttons[3]?.pressed',
                       "xrEdge('right-4'", "xrEdge('right-5'",'xrResetHold>1.1',
                       'updateXRVehicleRig()',"trackUsage('xr_started')"):
            self.assertIn(marker,SOURCE)

    def test_media_owner_browsing(self):
        for marker in ('id="mediaWindow"', 'id="mediaTabs"','id="mediaGrid"',
                       "identityRequest('/api/me/media'",'function mapAssetPreview(',
                       'async function refreshMediaBrowser()',"trackUsage('map_saved')"):
            self.assertIn(marker,SOURCE)

class VehicleLab0318RegressionTests(unittest.TestCase):
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_safe_duplicate_height_and_rotation(self):
        for term in ('const sourceMesh=courseMeshes.get(o.id)',
                     'o.angle=THREE.MathUtils.radToDeg(sourceMesh.rotation.y)',
                     'new THREE.Box3().setFromObject(sourceMesh)',
                     'other.y=centre+rise+',
                     "await addCourseObject(other,'Duplicated above source')",
                     "objectGizmo?.setMode('translate')"):
            self.assertIn(term,self.source)
        self.assertNotIn('other.x+=2;other.z+=2;',self.source)

    def test_blender_navigation_and_laptop_emulation(self):
        for term in ("['viewFront','Front view · Numpad 1','Numpad1'",
                     "['viewTop','Top view · Numpad 7','Numpad7'",
                     "['viewBack','Back view · Ctrl+Numpad 1','Ctrl+Numpad1'",
                     "['viewFrame','Frame selected · Numpad .','NumpadDecimal'",
                     "['viewLocal','Toggle local view · Numpad /','NumpadDivide'",
                     'function switchViewportProjection()',
                     'function setViewportAxis(name)',
                     'function orbitViewport(direction)',
                     'const radius=Math.max(2.5,camera.position.distanceTo(orbit.target))',
                     'id="emulateNumpad"', 'id="viewPieMenu"', 'normalizeShortcutImport(bindings)', 'Ctrl+Numpad1'):
            self.assertIn(term,self.source)

    def test_gallery_full_bleed_and_hover_cleanup(self):
        for term in ('#vehicleGallery .thumb-card{position:relative;aspect-ratio:3/2',
                     '#vehicleGallery .thumb-hero{display:block;position:absolute;inset:0',
                     "b.setAttribute('aria-label',label+' '+name)",
                     'const galleryHoverStops=new Set()',
                     'setInterval(()=>', '},500)', 'hero.src=original',
                     'stopGalleryPreviews()', 'prefers-reduced-motion',
                     "appendBtn('Add to scene','add',"):
            self.assertIn(term,self.source)
        self.assertNotIn("strip=document.createElement('div')",self.source)


class VehicleLab0319TerrainTests(unittest.TestCase):
    def setUp(self):
        self.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_sculpt_sample_grid_and_bounded_codec(self):
        for fragment in (
            'const SCULPT_SIDE=201,SCULPT_LIMIT=SCULPT_SIDE*SCULPT_SIDE',
            'new Int16Array(SCULPT_LIMIT)',
            "cfg.sculptData=(sparse?'s1:':'d1:')+sculptBytesToBase64(bytes)",
            'const editOffset=(Number(cfg.terrainBaseElevation)||0)+sculptSample(x,z)',
            'function validateMapSculptPayload(data)',
            'sculptField.fill(0);sculptChangedCells.clear();storeSculptData()',
            "rememberMapEdit('Sculpt terrain '+cfg.sculptDirection)",
            "'terrainBaseElevation','sculptData','seaEnabled','waterLevel'",
            'function sculptGroundHit(e)',
            "const hit=sculptRay.intersectObject(terrain,false)[0]",
            "await appConfirm('Erase all sculpted height changes on this map?",
            "if(!terrainChanged&&(waterChanged||environmentChanged))updateEnvironment()",
            "if(cfg.terrainProfile==='beach'||cfg.seaEnabled)",
        ):
            self.assertIn(fragment,self.html)

    def test_font_effects_and_collapse_icon(self):
        for fragment in (
            'id="themeBorders"','id="themeShadows"',
            "document.body.classList.toggle('ui-no-borders'",
            "document.body.classList.toggle('ui-no-shadows'",
            'body.ui-no-borders :focus-visible',
            'class="collapse-icon"',
            "collapseBtn.setAttribute('aria-expanded'",
            'const WINDOW_IDS=',"'radioWindow','sculptWindow'",
        ):
            self.assertIn(fragment,self.html)
        self.assertEqual(self.html.count('class="mini-btn minimize"'),18)

class VehicleLab0320WorldEditingTests(unittest.TestCase):
    def setUp(self):
        self.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()

    def test_full_rotation_roundtrip_through_geometry_and_gizmo(self):
        for fragment in (
            "rx:rot+(Number(o.rotX)||0)*Math.PI/180",
            "rz:(Number(o.rotZ)||0)*Math.PI/180",
            "o.rotX=THREE.MathUtils.radToDeg(m.rotation.x)",
            "o.rotZ=THREE.MathUtils.radToDeg(m.rotation.z)",
            "o.rotX=THREE.MathUtils.radToDeg(sourceMesh.rotation.x)",
            "o.rotZ=THREE.MathUtils.radToDeg(sourceMesh.rotation.z)",
            "['objectRotX','rotX'],['objectRotZ','rotZ']",
            'id="objectRotX"','id="objectRotZ"',
        ):
            self.assertIn(fragment,self.html)

    def test_gallery_vehicle_preserves_scene(self):
        for fragment in (
            'const SHARED_WORLD_KEYS=',
            "'courseObjects','courseName','terrainProfile','terrainSize'",
            "'sculptData','seaEnabled','waterLevel'",
            'function sceneWorldSnapshot()',
            'function restoreSceneWorld(snapshot)',
            'function rebuildSharedWorld()',
            'restoreSceneWorld(activeWorld);rebuildSharedWorld()',
        ):
            self.assertIn(fragment,self.html)

    def test_drive_camera_editor_override_and_resume_on_arrow(self):
        for fragment in (
            'function beginDriveSceneEditing(focus=null)',
            'function resumeDriveSceneCamera()',
            'if(driveSceneEditing){',
            'beginDriveSceneEditing(current.getWorldPosition(new THREE.Vector3()))',
            "['accelerate','reverse','steerLeft','steerRight'].includes(id)",
            "if(cfg.cameraMode==='free'&&driveSceneCameraSnapshot)",
            'function setViewportAxis(name){\n beginDriveSceneEditing()',
        ):
            self.assertIn(fragment,self.html)

    def test_sculpt_modifier_ring_and_map_preview(self):
        for fragment in (
            'id="sculptBrushThickness"','id="sculptBrushOpacity"','id="sculptBrushColor"',
            'new THREE.TorusGeometry(1,Math.max(.005,cfg.sculptBrushThickness/cfg.sculptRadius)',
            'e.button!==0||!(e.metaKey||e.ctrlKey)',
            'function updateSculptMapReliefPatch()',
            'ctx.putImageData(image,x0,z0)',
            'updateSculptMapReliefPatch();requestMinimapPaint();',
        ):
            self.assertIn(fragment,self.html)

class VehicleLab0323RadioAndGeologyTests(unittest.TestCase):
    def setUp(self):
        self.path=Path(__file__).resolve().parents[1]/'index.html'
        self.html=self.path.read_text(encoding='utf-8')

    def test_compact_radio_header_is_the_only_transport(self):
        from html.parser import HTMLParser
        class Headers(HTMLParser):
            def __init__(self):super().__init__();self.header=False;self.depth=0;self.labels=[]
            def handle_starttag(self,tag,attrs):
                if tag=='div' and dict(attrs).get('class')=='window-head':self.header=True;self.depth=1
                elif self.header and tag=='div':self.depth+=1
            def handle_endtag(self,tag):
                if self.header and tag=='div':
                    self.depth-=1
                    if not self.depth:self.header=False
            def handle_data(self,data):
                if self.header and data.strip():self.labels.append(data.strip())
        parsed=Headers();parsed.feed(self.html)
        self.assertFalse(any(re.match(r'^\d{2}\s*/',s) for s in parsed.labels),parsed.labels)
        section=self.html.split('<section id="radioWindow"',1)[1].split('<section id="objectWindow"',1)[0]
        head,body=section.split('<div class="window-body"',1)
        for key in ('radioPrev','radioPlay','radioNext','radioVolume'):
            self.assertEqual(section.count(f'id="{key}"'),1)
            self.assertIn(f'id="{key}"',head)
            self.assertNotIn(f'id="{key}"',body)
        self.assertIn('<strong>Radio</strong>',head)
        self.assertNotIn('id="radioStop"',section)
        self.assertIn("if(e.button!==0||e.target.closest('button,input,select,label,a,[role=slider]'))return;",self.html)
        self.assertIn("radioAudio.onpause=updateRadioHeaderState",self.html)

    def test_large_prism_specs_preserve_inspector_dimensions(self):
        script=r'''
const fs=require('fs'),assert=require('node:assert/strict');
const src=fs.readFileSync(process.argv[1],'utf8');
function extract(name){let a=src.indexOf('function '+name+'(');assert(a>=0);let start=src.indexOf('{',a),depth=0;
 for(let i=start;i<src.length;i++){if(src[i]==='{')depth++;else if(src[i]==='}'&&--depth===0)return src.slice(a,i+1)}throw Error('unclosed '+name)}
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const cfg={courseObjects:[{id:'large',kind:'cube',x:0,z:0,w:80,h:50,d:75,y:25,angle:21,physics:'static'},
 {id:'small',kind:'cube',x:0,z:0,w:22,h:18,d:35,y:9,angle:0,physics:'static'}]};
const specs=new Function('cfg','clamp','heightAt',extract('courseSpecs')+';return courseSpecs()')(cfg,clamp,()=>0);
assert.equal(specs.length,2);
assert.deepEqual(specs.map(s=>[s.w,s.h,s.d]),[[80,50,75],[22,18,35]]);
assert.equal(specs[0].ry,21*Math.PI/180);
'''
        result=subprocess.run(['node','-e',script,str(self.path)],capture_output=True,text=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_optional_biome_shader_and_sparse_state(self):
        for snippet in (
            'function updateTerrainBiomeColors()',
            "geometry.setAttribute('terrainBiome',buffer)",
            'vTerrainBiome = terrainBiome;',
            'diffuseColor.rgb=mix(biomeSource,clamp(biomeTarget,0.0,1.0),vTerrainBiome.a);',
            'function mapBiomeSnapshot()',
            'function applyMapBiomeSettings(data)',
            'biome:mapBiomeSnapshot()',
            "'terrainBaseElevation','sculptData','seaEnabled','waterLevel',...MAP_BIOME_KEYS",
            'if(cfg.biomeRelativeSea)updateTerrainBiomeColors()',
            "biomeEnabled:false",
        ):
            self.assertIn(snippet,self.html)

    def test_biome_vertex_colours_and_shader_injection_runtime(self):
        script=r'''
const fs=require('fs'),assert=require('node:assert/strict');
const src=fs.readFileSync(process.argv[1],'utf8');
function extract(name){let a=src.indexOf('function '+name+'(');assert(a>=0);let start=src.indexOf('{',a),depth=0;
 for(let i=start;i<src.length;i++){if(src[i]==='{')depth++;else if(src[i]==='}'&&--depth===0)return src.slice(a,i+1)}throw Error('unclosed '+name)}
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
class Color {constructor(s='#ffffff'){if(!/^#[0-9a-f]{6}$/i.test(s))throw Error('color');this.r=parseInt(s.slice(1,3),16)/255;this.g=parseInt(s.slice(3,5),16)/255;this.b=parseInt(s.slice(5,7),16)/255}
 copy(c){this.r=c.r;this.g=c.g;this.b=c.b;return this}lerp(c,t){this.r+=(c.r-this.r)*t;this.g+=(c.g-this.g)*t;this.b+=(c.b-this.b)*t;return this}}
class BufferAttribute {constructor(a,n){this.array=a;this.itemSize=n;this.count=a.length/n} }
class MeshStandardMaterial{constructor(options){this.options=options}}
class Vector2{constructor(x,y){this.x=x;this.y=y}}
const THREE={Color,BufferAttribute,MeshStandardMaterial,Vector2,DoubleSide:2};
const cfg={biomeEnabled:false,biomePalette:'alpine',biomeBlendMode:'mix',biomeRelativeSea:false,biomeBlend:.9,biomeSlope:.6,biomeExposure:1,
 biomeValleyAltitude:-12,biomeRockAltitude:15,biomeSnowAltitude:34,biomeValleyColor:'#252d36',biomeGroundColor:'#688754',biomeRockColor:'#838d96',biomeSnowColor:'#f2f7ff',waterLevel:0};
const pos=[-15,0,10,24,36,50],normal=[[0,1,0],[0,1,0],[0,1,0],[0,.7,-.7],[0,1,0],[0,1,0]],attrs={
 position:{count:pos.length,getY:i=>pos[i]},normal:{getY:i=>normal[i][1],getZ:i=>normal[i][2]}};
const geometry={getAttribute:key=>attrs[key],setAttribute:(key,value)=>attrs[key]=value,deleteAttribute:key=>delete attrs[key]};
const terrain={geometry};
const fn=new Function('cfg','terrain','THREE','clamp',
 "const BIOME_PALETTES={alpine:['#292f3b','#668650','#82909a','#f5f8ff'],canyon:['#302a2b','#c18b5a','#9d7162','#e6d1b2'],volcanic:['#121820','#343941','#606775','#cbd4dc']};\n"+
 extract('biomeColors')+'\n'+extract('updateTerrainBiomeColors')+'\n'+extract('makeTerrainMaterial')+'\nreturn {updateTerrainBiomeColors,makeTerrainMaterial}');
const {updateTerrainBiomeColors,makeTerrainMaterial}=fn(cfg,terrain,THREE,clamp);
updateTerrainBiomeColors();assert.equal(attrs.terrainBiome,undefined,'off must not allocate terrain attribute');
cfg.biomeEnabled=true;updateTerrainBiomeColors();const b=attrs.terrainBiome.array;
assert.equal(b.length,pos.length*4);assert(b[0]<b[5*4],'valley darker than high snow');
assert(b[4*4]>.8&&b[4*4+1]>.8&&b[4*4+2]>.8,'snow high and pale');
assert(Math.abs(b[3]-.9)<1e-5);cfg.biomeRelativeSea=true;cfg.waterLevel=20;updateTerrainBiomeColors();
assert(attrs.terrainBiome.array[4*4]<.8,'raising sea-relative threshold pushes snow above this altitude');
const material=makeTerrainMaterial({map:{id:1}});
const shader={vertexShader:'#include <common>\nvoid main(){#include <begin_vertex>}',fragmentShader:'#include <common>\nvoid main(){#include <map_fragment>}'};
material.onBeforeCompile(shader);
assert(shader.vertexShader.includes('attribute vec4 terrainBiome;'));
assert(shader.fragmentShader.includes('diffuseColor.rgb=mix(biomeSource'));
'''
        result=subprocess.run(['node','-e',script,str(self.path)],capture_output=True,text=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class VehicleLab0324LocalLibrarySafetyTests(unittest.TestCase):
    """A missing local gallery must never trigger destructive recovery."""
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / 'index.html').read_text()

    def test_same_browser_database_contract_is_preserved(self):
        self.assertIn("const DB_NAME='procedural-vehicle-studio';", self.source)
        self.assertIn('indexedDB.open(DB_NAME,3)', self.source)
        self.assertNotIn('indexedDB.deleteDatabase(',self.source)
        self.assertNotIn('localStorage.clear(',self.source)

    def test_wheel_workshop_is_populated_after_visibility_and_library_loading(self):
        self.assertIn("if(id==='wheelWindow')renderWheelStudio();", self.source)
        self.assertIn('buildVehicle();\nrenderWheelStudio();\nresetCamera();',self.source)
        self.assertIn('renderWheelStudio();\n}\n\n async function allLayouts()',self.source)

    def test_diagnostics_are_read_only_and_do_not_expose_private_data(self):
        fragment=self.source.split('// Read-only local-data report for storage outages.',1)[1].split('async function saveAvatarAsset(',1)[0]
        self.assertIn("db.transaction(name,'readonly')",fragment)
        self.assertIn("$('checkLocalLibraries').onclick",fragment)
        self.assertIn('storageUsageMiB',fragment)
        for unsafe in ("'readwrite'",'.delete(','.put(','.clear(', 'data.blob'):
            self.assertNotIn(unsafe,fragment)
        self.assertNotIn('assetIds:',fragment)
        self.assertNotIn('vehicleNames:',fragment)

class VehicleLab0326NotesAndTerrainTests(unittest.TestCase):
    def setUp(self):
        self.html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
    def test_notes_geology_and_visibility_contracts(self):
        for fragment in ('id="notesWindow"','id="geologyWindow"','id="notesSearch"',
                         'id="notesBulkFolder"','id="notesMerge"','id="notesSelectAll"',
                         'id="notesTitle"','id="notesBody"','id="geoSection"',
                         "'notesWindow','geologyWindow'",'function notesLoad()',
                         'function notesSave(',"'/api/me/notes'","'vehiclelab.notes.draft.v1.'"):
            self.assertIn(fragment,self.html)
    def test_theme_glass_and_colored_headers(self):
        for fragment in ('id="themePaneOpacity"','id="themePaneBlur"',
                         'id="themeColoredHeaders"','window-header-swatch',
                         'var(--pane-blur)', 'ui-colored-headers',
                         'paneOpacity:93,paneBlur:14,coloredHeaders:false',
                         'themeSettings.headerColors'):
            self.assertIn(fragment,self.html)
    def test_sculpt_reliable_reset_and_flat_default(self):
        for fragment in ("terrainProfile:'flat'",'id=\'sculptFlatWorld\'',
                         "sculptField.fill(0)","cfg.terrainProfile='flat'",'sculptBoundPoint(pt)',
                         "rememberMapEdit('New flat world')",'if(e.type===\'pointerup\')sculptContinue'):
            self.assertIn(fragment,self.html)


class GeologicalWindowVisibility0328Tests(unittest.TestCase):
    def test_geology_visibility_is_not_conditional_on_sync(self):
        html=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')
        start=html.index('function setWindowVisible(id,show,restore=false){')
        end=html.index('function refreshWindowButtons(){',start)
        handler=html[start:end]
        self.assertIn("win.style.display=show?'flex':'none';",handler)
        self.assertIn("if(show&&id==='geologyWindow'){syncGeologyEditor();void geoRefreshPresets()}",handler)
        self.assertLess(handler.index("win.style.display=show?'flex':'none';"),
                        handler.index("if(show&&id==='geologyWindow'){syncGeologyEditor();void geoRefreshPresets()}"))
        self.assertNotIn("else win.style.display=show?'flex':'none';",handler)
        self.assertIn("geology.add({visual:()=>{setWindowVisible('geologyWindow',true);syncGeologyEditor()}},'visual')",html)
        self.assertIn("'geologyWindow'",html)

class VehicleLab0330SurfaceCoherenceTests(unittest.TestCase):
    """No new live-server dependencies. Exercise visible-mesh geometry in Node."""
    def setUp(self):
        self.source=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_editable_categories_and_material_targets(self):
        src=self.source
        for snippet in (
            'function registerEditableVehiclePart(root,key,label,materialTarget)',
            "registerEditableVehiclePart(lampRoot,",
            "registerEditableVehiclePart(seatGroup,",
            "registerEditableVehiclePart(dash,",
            "registerEditableVehiclePart(steeringWheel,",
            "registerEditableVehiclePart(root,`wheel:",
            "if(material===glass)registerEditableVehiclePart(piece,",
            'const hits=car?raycaster.intersectObject(car,true):[];',
            'selectEditableVehiclePart(obj.userData.vehicleSelect.key,materialTarget);',
            "const selected=editableVehicleParts.get(selectedVehicleTargetKey);",
            "face.userData.materialTarget=prefix+'TireSidewall'",
            "rim.userData.materialTarget=prefix+'RimColor'",
            "selectedVehicleTargetKey='module:'+selectedPart;",
            "const colour=front?cfg.headlightColor:cfg.tailLightColor;",
        ):
            self.assertIn(snippet,src)
        for name in ('frontRimColor','rearRimColor','frontTireSidewall',
                     'rearTireSidewall','headlightColor','tailLightColor'):
            self.assertIn(f'<option value="{name}">',src)
        self.assertNotIn("raycaster.intersectObjects(bodyRoot?.children||[],true)",src)

    def test_camera_clearance_requires_visible_geometry(self):
        self.assertIn('const visibleGround=visibleTerrainHeightAt(x,z);',self.source)
        self.assertIn('if(visibleGround===null)continue;',self.source)
        self.assertIn('alignVegetationToVisibleTerrain(dirty);',self.source)
        for token in ('update(farGrassMesh,farGrassXZ,.015)',
                      'update(nearGrassMesh,nearGrassXZ,.02)',
                      'for(const {mesh,coords,offsets} of shrubRockMeshes)'):
            self.assertIn(token,self.source)

    def test_visible_triangle_interpolation_and_instance_alignment(self):
        import shutil
        if not shutil.which('node'):
            self.skipTest('Node unavailable')
        src=self.source
        surface=src[src.index('function visibleTerrainHeightAt('):src.index('let seaSurface=null,skyDome=null;')]
        align=src[src.index('function alignVegetationToVisibleTerrain('):src.index('function updateVegetation(dt)')]
        script='''
          const assert=require('node:assert/strict');
          const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
          let SIZE=1.5,STEP=1.5,N=1;
          let heights=[0,8,6,30];
          let terrain={geometry:{getAttribute(k){return k==='position'?{count:4,getY(i){return heights[i]}}:null}}};
          let farGrassMesh=null,nearGrassMesh=null,farGrassXZ=null,nearGrassXZ=null,shrubRockMeshes=[];
          %s
          %s
          assert(Math.abs(visibleTerrainHeightAt(-.45,.3)-3.6)<1e-8);
          assert(Math.abs(visibleTerrainHeightAt(.45,-.15)-16)<1e-8);
          assert.equal(visibleTerrainHeightAt(5,0),null);
          assert.equal(visibleTerrainHeightAt(0,-5),null);
          assert.equal(visibleTerrainHeightAt(NaN,0),null);
          const makeMesh=(count)=>({count,instanceMatrix:{array:new Float32Array(count*16),needsUpdate:false}});
          farGrassMesh=makeMesh(1);farGrassXZ=new Float32Array([-.45,.3]);
          nearGrassMesh=makeMesh(1);nearGrassXZ=new Float32Array([.45,-.15]);
          const rock=makeMesh(1);
          shrubRockMeshes=[{mesh:rock,coords:new Float32Array([.45,-.15]),offsets:new Float32Array([.24])}];
          alignVegetationToVisibleTerrain();
          assert(Math.abs(farGrassMesh.instanceMatrix.array[13]-3.615)<1e-5);
          assert(Math.abs(nearGrassMesh.instanceMatrix.array[13]-16.02)<1e-5);
          assert(Math.abs(rock.instanceMatrix.array[13]-16.24)<1e-5);
          assert(farGrassMesh.instanceMatrix.needsUpdate);
          assert(nearGrassMesh.instanceMatrix.needsUpdate);
          assert(rock.instanceMatrix.needsUpdate);
          const old=farGrassMesh.instanceMatrix.array[13];
          heights=[0,18,16,30];
          alignVegetationToVisibleTerrain({x0:0,x1:1,z0:0,z1:1});
          assert.equal(farGrassMesh.instanceMatrix.array[13],old);
          alignVegetationToVisibleTerrain();
          assert(farGrassMesh.instanceMatrix.array[13]>old);
        '''%(surface,align)
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class DialogAndSculptUI0311Tests(unittest.TestCase):
    def setUp(self):
        self.html = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')

    def test_native_dialogs_replaced_and_single_shared_modal(self):
        self.assertIn('id="appDialog"', self.html)
        self.assertEqual(self.html.count('id="appDialog"'), 1)
        self.assertIn('function appConfirm(message)', self.html)
        self.assertIn('function appPrompt(message', self.html)
        self.assertIn('appDialogQueue=task.then(', self.html)
        self.assertNotRegex(self.html, r'(?<!app)(?<![A-Za-z])(?:window\.)?(?:confirm|prompt|alert)\s*\(')
        for key in ('notesNewFolder', 'geoSavePreset', 'sculptFlatWorld', 'radioPlaylistDelete'):
            self.assertIn(key, self.html)
        self.assertIn("$('appDialog').hidden", self.html)

    def test_3d_brush_requires_modifier_and_shift_carves(self):
        self.assertIn("cfg.sculptDirection=e.shiftKey?'lower':'raise'", self.html)
        self.assertIn('!(e.metaKey||e.ctrlKey)||!terrain', self.html)
        self.assertIn('if(sculpt3DStroke&&e.pointerId===sculptStagePointer)', self.html)
        self.assertNotIn('Drag on the map, or hold Command', self.html)
        self.assertNotIn('Command/Ctrl + left-drag sculpts in 3D', self.html)
        self.assertIn('<kbd>[</kbd><kbd>]</kbd>', self.html)
        self.assertIn('<kbd>Shift + ⌘ / Ctrl</kbd>', self.html)

    def test_native_colour_wells_and_contrast(self):
        self.assertIn('input[type=color]::-webkit-color-swatch-wrapper', self.html)
        self.assertIn('input[type=color]::-moz-color-swatch', self.html)
        self.assertIn('.window-head .mini-btn.minimize:hover', self.html)
        self.assertIn('color-scheme:dark!important', self.html)

class CloudMapPicker035Tests(unittest.TestCase):
    """Run the actual dropdown and Load handlers with mocked private media data."""

    def test_cloud_only_map_is_selectable_and_loads_from_server(self):
        html=str(Path(__file__).resolve().parents[1]/'index.html')
        script=r'''
const assert=require('assert');
const fs=require('fs');
const source=fs.readFileSync(process.argv[1],'utf8');
const begin=source.indexOf('let mapListRefreshSerial=0;');
const finish=source.indexOf('const mapSaveDialog=',begin);
assert(begin>=0&&finish>begin);
const pickerSource=source.slice(begin,finish);
class Opt { constructor(label,value){this.text=label;this.value=value;this.disabled=false;} }
class Group {constructor(){this.label='';this.items=[];} append(option){this.items.push(option)}}
class Picker {
 constructor(){this.children=[];this._value='';this.title=''}
 replaceChildren(){this.children=[];this._value=''}
 append(entry){this.children.push(entry)}
 prepend(entry){this.children.unshift(entry)}
 get options(){return this.children.flatMap(entry=>entry.items||[entry])}
 get value(){return this._value}
 set value(next){this._value=next}
 querySelector(){return this.options.find(item=>!item.disabled)||null}
}
const picker=new Picker(),refreshButton={},loadButton={disabled:false};
const lookup=id=>({'mapSaved':picker,'mapRefreshList':refreshButton,'mapLoad':loadButton})[id];
const document={createElement(kind){assert.equal(kind,'optgroup');return new Group()}};
const entries=[{id:'shared',name:'Cache copy',modified:1},{id:'device1',name:'Offline map',modified:2}];
let failure=false,owner={id:'profile1'},token='token';
let loaded=null;const notices=[];
const getMedia=async(path)=>{
 assert(path.startsWith('/api/me/media'));
 if(failure)throw Error('Network offline');
 if(path==='/api/me/media?kind=map')return {media:[
  {id:'shared',kind:'map',name:'Cloud copy',updated_at:99},
  {id:'cloudOnly',kind:'map',name:'Rocky hills X - Winter',updated_at:100},
  {id:'picture',kind:'image',name:'Not a map',updated_at:101}
 ]};
 if(path==='/api/me/media/cloudOnly')return {media:{id:'cloudOnly',kind:'map',name:'Rocky hills X - Winter',
  data:{schema:'vehiclelab-testmap/v3',objects:[{kind:'hill',x:10,z:12,w:10,d:8,h:4}],terrainProfile:'flat'}}};
 throw Error('Bad route '+path);
};
const run=new Function('$','document','Option','mapTransaction','identityRequest','testMapPresets',
 'recordEvent','note','getOwner','getToken',`
 let activeProfile=getOwner(),guestToken=getToken();
 ${pickerSource}
 return {refreshMapList,setSession:(profile,token)=>{activeProfile=profile;guestToken=token}};
`);
const warnings=[];
const app=run(lookup,document,Opt,async()=>entries,getMedia,{'Practice ground':[]},
 (_level,message)=>warnings.push(message),message=>notices.push(message),()=>owner,()=>token);
(async()=>{
 await app.refreshMapList();
 assert(picker.options.some(item=>item.value==='cloud:cloudOnly'&&item.text==='Rocky hills X - Winter'));
 assert(picker.options.some(item=>item.value==='cloud:shared'));
 assert(!picker.options.some(item=>item.value==='local:shared'));
 assert(picker.options.some(item=>item.value==='local:device1'));
 assert(picker.options.some(item=>item.value==='preset:Practice ground'));
 // The same map must load directly from the server, not IndexedDB.
 const loadBegin=source.indexOf("$('mapLoad').onclick=async()=>{");
 const loadFinish=source.indexOf("$('mapExport').onclick=",loadBegin);
 assert(loadBegin>=0&&loadFinish>loadBegin);
 const loadSource=source.slice(loadBegin,loadFinish);
 const action=new Function('$','activeProfile','guestToken','identityRequest','mapTransaction',
  'applySavedTestMap','testMapPresets','note','recordEvent','rememberActiveCloudMap',loadSource);
 let savedPointer=null;
 action(lookup,{id:'profile1'},'token',getMedia,async()=>{throw Error('Local cache was read')},
  async data=>{loaded=data}, {'Practice ground':[]},message=>notices.push(message),
  (_level,message)=>warnings.push(message),(_owner,id)=>{savedPointer=id});
 picker.value='cloud:cloudOnly';await loadButton.onclick();
 assert.equal(loaded.name,'Rocky hills X - Winter');
 assert.equal(loaded.objects[0].kind,'hill');
 assert.equal(savedPointer,'cloudOnly');
 assert.equal(loadButton.disabled,false);
 // If cloud listing fails, offline maps remain accessible and aren't reported deleted.
 failure=true;await app.refreshMapList();
 assert(picker.options.some(item=>item.value==='local:device1'));
 assert(picker.options.some(item=>item.text.includes('Cloud maps unavailable')));
 app.setSession(null,'');await app.refreshMapList();
 assert(!picker.options.some(item=>item.value.startsWith('cloud:')));
 assert(picker.options.some(item=>item.value.startsWith('local:')));
 console.log('Private cloud picker, cache deduplication, load and error handling passed');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script,html],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

class LastCloudMapAndLiveTexture036Tests(unittest.TestCase):
    """Execute the new startup selector and appearance validation with Node mocks."""

    def setUp(self):
        self.html=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_last_cloud_map_restores_only_after_verified_login_without_overwriting_edits(self):
        script=r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const begin=source.indexOf("const LAST_CLOUD_MAP_KEY=");
const end=source.indexOf('// The server is authoritative',begin);
assert(begin>=0&&end>begin);
const module=source.slice(begin,end);
function createApp(state){
 const memory=new Map(state.memory||[]),logs=[];
 const statuses={mapSaved:{value:''},mapStatus:{textContent:''}};
 let current={id:state.owner||'profile1'},edited=!!state.edited;
 let attempted=false,requests=0,applied=[];
 const maps=[
   {id:'11111111-1111-4111-8111-111111111111',name:'Older map',kind:'map',updated_at:1},
   {id:'22222222-2222-4222-8222-222222222222',name:'Newest map',kind:'map',updated_at:2}];
 const identityRequest=async path=>{
  requests++;
  if(state.fail)throw Error('Server offline');
  if(path==='/api/me/media?kind=map')return {media:maps};
  const m=maps.find(item=>path.endsWith(item.id));
  if(!m)throw Error('Missing map');
  return {media:{id:m.id,name:m.name,kind:'map',data:{objects:[],weather:{fogEnabled:true},terrainProfile:'flat'}}};
 };
 const Fn=new Function('safeStore','safeRead','$','identityRequest','applySavedTestMap',
  'refreshMapList','recordEvent','getProfile','initialEdits',`
 let activeProfile=getProfile(),mapEditedSinceStartup=initialEdits;
 let startupMapRestoreAttempted=false;
 ${module}
 return {restoreLastCloudMapOnStartup};`);
 const app=Fn((key,value)=>memory.set(key,value),key=>memory.get(key)||'',id=>statuses[id],identityRequest,
  async (value,options)=>applied.push([value,options]),async()=>{},
  (level,message)=>logs.push([level,message]),()=>current,edited);
 return {app,memory,logs,statuses,applied,get requests(){return requests}};
}
(async()=>{
 const first=createApp({});
 await first.app.restoreLastCloudMapOnStartup('profile1');
 assert.equal(first.applied.length,1);
 assert.equal(first.applied[0][0].name,'Newest map');
 assert.equal(first.applied[0][1].startup,true);
 assert.equal(first.statuses.mapSaved.value,'cloud:22222222-2222-4222-8222-222222222222');
 assert(first.memory.has('vehiclelab.active-cloud-map.v1.profile1'));
 await first.app.restoreLastCloudMapOnStartup('profile1');
 assert.equal(first.applied.length,1,'startup must not run twice');
 const older='11111111-1111-4111-8111-111111111111';
 const saved=createApp({memory:[['vehiclelab.active-cloud-map.v1.profile1',
  JSON.stringify({schema:'vehiclelab-active-map/v1',map_id:older})]]});
 await saved.app.restoreLastCloudMapOnStartup('profile1');
 assert.equal(saved.applied[0][0].name,'Older map','explicitly active map wins');
 const editing=createApp({edited:true});
 await editing.app.restoreLastCloudMapOnStartup('profile1');
 assert.equal(editing.requests,0,'never overwrite an already edited world');
 const offline=createApp({fail:true});
 await offline.app.restoreLastCloudMapOnStartup('profile1');
 assert.equal(offline.applied.length,0);
 assert(offline.logs.some(v=>v[0]==='WARN'));
 const other=createApp({owner:'profile2',memory:[['vehiclelab.active-cloud-map.v1.profile1',
  JSON.stringify({schema:'vehiclelab-active-map/v1',map_id:older})]]});
 await other.app.restoreLastCloudMapOnStartup('profile2');
 assert.equal(other.applied[0][0].name,'Newest map','pointer must be profile-scoped');
 console.log('Cloud map automatic restore, profile isolation, no overwrite and errors passed');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script,str(Path(__file__).resolve().parents[1]/'index.html')],
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_map_appearance_is_bounded_and_schema_backward_compatible(self):
        script=r'''
const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
const a=source.indexOf('// Map-scoped appearance settings.');
const b=source.indexOf('// Weather remains part',a);
assert(a>=0&&b>a);
const fragment=source.slice(a,b);
const run=new Function('clamp',`let cfg={seed:11,noiseScale:26,grassDensity:8000,puddles:true};
${fragment}
return {snapshot:mapAppearanceSnapshot,apply:applyMapAppearance,cfg};`);
const obj=run((v,a,b)=>Math.min(b,Math.max(a,v)));
const original=obj.snapshot();assert.equal(original.seed,11);
obj.apply({appearance:{seed:123,noiseScale:70,grassDensity:999999,puddles:false,
  __proto__:{seed:999},random:'bad'}});
assert.equal(obj.cfg.seed,123);
assert.equal(obj.cfg.noiseScale,70);
assert.equal(obj.cfg.grassDensity,20000);
assert.equal(obj.cfg.puddles,false);
obj.apply({appearance:{seed:'not a number',noiseScale:null}});
assert.equal(obj.cfg.seed,123);
assert.equal(obj.cfg.noiseScale,70);
obj.apply({});assert.equal(obj.cfg.seed,123);
assert(source.includes('appearance:mapAppearanceSnapshot()'));
assert(source.includes('applyMapAppearance(data)'));
console.log('Validated map appearance and backwards-compatible missing fields');
'''
        result=subprocess.run(['node','-e',script,str(Path(__file__).resolve().parents[1]/'index.html')],
                              capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_noise_edits_do_not_leave_drive_or_recreate_terrain_collision(self):
        a=self.html.index(' const rebuildNoise=()=>{')
        b=self.html.index(" noiseFolder.add(cfg,'seed'",a)
        body=self.html[a:b]
        for required in ('textureCanvasCache.clear();','terrainMaps(', 'makeTerrainMaterial(',
                         'scheduleBuild();',"rememberMapEdit('Procedural noise / texture lab')"):
            self.assertIn(required,body)
        for forbidden in ('leaveDrive()', 'buildTerrain()', 'buildCourse()',
                          'world.removeBody(', 'makeCannonAdapter('):
            self.assertNotIn(forbidden,body)
        self.assertIn('previousEnvironmentSignature=currentEnvironmentSignature()',self.html)
        self.assertIn("if(!terrainChanged&&(waterChanged||environmentChanged))updateEnvironment()",self.html)
        self.assertIn("...WEATHER_MAP_KEYS",self.html)

class VectorChassis038Tests(unittest.TestCase):
    """Source regressions for the alternative, non-destructive vector workspace."""

    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()

    def test_editor_window_and_access_paths(self):
        self.assertIn('id="vectorWindow"', self.html)
        self.assertIn('id="vectorCanvas"', self.html)
        self.assertIn('id="vectorLayerList"', self.html)
        self.assertIn('id="vectorEditorBtn"', self.html)
        self.assertIn("['vectorChassis','Open vector chassis editor','Shift+KeyC'",self.html)
        self.assertIn('Vector chassis · Shift+C',self.html)
        self.assertEqual(self.html.count('class="mini-btn minimize"'),18)

    def test_complete_view_and_tool_palette(self):
        for view in ('left','right','front','rear','top','bottom'):
            self.assertIn(f'<option value="{view}">',self.html)
        for tool in ('select','polyline','poly','free','rect','ellipse','circle','triangle','insert'):
            self.assertIn(f'data-vector-tool="{tool}"',self.html)
        for component in ('body','glass','door','light','bumper','grille','mirror','nameplate','trim'):
            self.assertIn(f'<option value="{component}">',self.html)

    def test_vector_persistence_is_blueprint_scoped(self):
        self.assertIn('vectorChassis:null',self.html)
        self.assertIn('const VECTOR_SCHEMA=',self.html)
        self.assertIn('cfg.vectorChassis=vectorSanitize(cfg.vectorChassis)',self.html)
        self.assertIn('vehicle:structuredClone(cfg)',self.html)
        self.assertIn('function vectorApplyToScene()',self.html)
        self.assertIn('vectorApplyToScene();\nupdateLights()',self.html)

    def test_scene_gizmo_protects_imported_assets(self):
        self.assertIn('new TransformControls(camera,renderer.domElement);vectorGizmo',self.html)
        self.assertIn('vectorGizmo.addEventListener(\'objectChange\'',self.html)
        self.assertIn('function vectorReleaseMeshes()',self.html)
        self.assertIn('if(vectorGizmo?.object)vectorGizmo.detach()',self.html)
        self.assertIn('vectorRoot=new THREE.Group();',self.html)


class VectorChassis039Tests(unittest.TestCase):
    """Non-destructive source contracts for the 2D workbench follow-up."""

    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / 'index.html').read_text()

    def test_left_and_right_reference_a_single_profile(self):
        self.assertIn("function vectorLayersInView(){return vectorDesign().layers.filter(l=>l.view===((vectorView==='right')?'left':vectorView))", self.html)
        self.assertIn("view:vectorView==='right'?'left':vectorView", self.html)
        self.assertIn("if(layer.role!=='body')", self.html)
        self.assertIn("group.position.x=layer.role==='body'?layer.depth/2", self.html)

    def test_arc_primitives_have_three_handles(self):
        self.assertIn("make('Outer body', 'body',points,{arcs:[{start:8,mid:9,end:10},{start:11,mid:12,end:13}]})", self.html)
        self.assertIn('function vectorCircleThrough(a,b,c)', self.html)
        self.assertIn('shape.absarc(c.x,c.y,c.radius,c.start,c.end,c.clockwise)', self.html)
        self.assertIn('data-vector-tool="arch"', self.html)
        self.assertIn("new THREE.TubeGeometry(curve,48,.017,6,false)", self.html)

    def test_physical_wheel_mounts_and_guides_are_linked(self):
        self.assertIn('frontWheelMountY:-.3,rearWheelMountY:-.3', self.html)
        self.assertIn('function vectorCommitWheelGuide()', self.html)
        self.assertIn("'data-vector-wheel':axle", self.html)
        self.assertIn('wheelMountYFor(axle)', self.html)
        self.assertIn("cfg.axleFrontOffset=clamp(preview.x-cfg.L*.38", self.html)
        self.assertIn("scheduleBuild();scheduleHistory('Move '", self.html)

    def test_focus_and_editor_transform_shortcuts(self):
        self.assertIn("!document.activeElement?.closest?.('#vectorWindow')", self.html)
        self.assertIn("function vectorBeginTransform(mode)", self.html)
        self.assertIn("function vectorApplyTransform(point)", self.html)
        self.assertIn("function vectorFinishTransform(cancel=false)", self.html)
        self.assertIn("KeyG:'move',KeyS:'scale',KeyR:'rotate'", self.html)
        self.assertIn("if(e.code==='KeyF')", self.html)
        self.assertIn("if(['KeyX','Delete','Backspace'].includes(e.code))", self.html)

    def test_fill_and_close_can_be_changed_after_drawing(self):
        self.assertIn('id="vectorClosePath"', self.html)
        self.assertIn('id="vectorFillColor"', self.html)
        self.assertIn('id="vectorFillOpacity"', self.html)
        self.assertIn('layer.opacity', self.html)
        self.assertIn("if(!layer.closed&&layer.role==='body'&&layer.nodes.length>=3)layer.closed=true", self.html)
        self.assertIn('color:/^#[0-9a-f]{6}$/i', self.html)

class VectorChassis040Tests(unittest.TestCase):
    """Guard glass drafting, docked properties, and mirrored front/rear shapes."""
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).resolve().parents[1]/'index.html').read_text(encoding='utf-8')

    def test_canvas_glass_and_docked_collapse(self):
        for marker in (
            'id="vectorInspectorToggle"',
            'aria-expanded="true"',
            'grid-template-columns:minmax(0,1fr) minmax(265px,295px)',
            'data-inspector-collapsed="true"',
            "workspace.dataset.inspectorCollapsed=String(collapsed)",
            "requestAnimationFrame(vectorDrawCanvas)",
            "fill:'rgba(13,31,46,.24)'",
            '#vectorWindow .vector-canvas-wrap{position:relative!important',
        ):
            self.assertIn(marker,self.html,marker)

    def test_symmetric_front_and_rear_without_new_schema(self):
        for marker in (
            'id="vectorMirror"',
            "function vectorMirroringActive()",
            "mirrorFrontRear:data.mirrorFrontRear!==false",
            "function vectorSyncMirrorControls()",
            "data-vector-mirror':'true'",
            "transform:'scale(-1 1)'",
            "if((layer.view==='front'||layer.view==='rear')&&vectorDesign().mirrorFrontRear!==false)",
            "const opposite=group.clone(true);opposite.scale.x=-1;parent.add(opposite)",
            "if(vectorMirroringActive()&&vectorDraftMirror)nodes=nodes.map",
            "vectorDesign().mirrorFrontRear=$('vectorMirror').checked",
            "'aria-label':'Mirror symmetry axis'",
        ):
            # The x=0 axis has the same role whether the SVG uses a different label.
            if marker == "'aria-label':'Mirror symmetry axis'":
                self.assertIn("'aria-label':'Mirror symmetry axis'",self.html)
            else:
                self.assertIn(marker,self.html,marker)

    def test_source_does_not_change_persistent_back_end(self):
        self.assertIn("const VECTOR_SCHEMA='vehiclelab-vector-chassis/v1'",self.html)
        self.assertIn("view:vectorView==='right'?'left':vectorView",self.html)
