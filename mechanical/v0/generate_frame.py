"""PRP V0 assembly / fit prototype, units mm. NOT a load-certified release.

Rebuild: python generate_frame.py. Requires requirements.txt.
Hardware models are bounding envelopes, NOT manufacturer CAD.
"""
from pathlib import Path
import json, math, itertools
import cadquery as cq
import trimesh

OUT = Path(__file__).parent / 'output'
OUT.mkdir(exist_ok=True)
for sub in ('step_parts', 'stl_trial', 'stl_parts'):
    (OUT/sub).mkdir(exist_ok=True)

# Authoritative CAD values; measured/product-image values are documented separately.
P = dict(frame_length=150, frame_width=94, frame_top=65, wall=3,
         hip_x=60, hip_z=42, servo_axis_x=24, servo_mount_center_x=29.3,
         servo_hole_pitch=27.8, servo_hole_d=2.2,
         servo_panel_clearance_hole=2.4, servo_opening=(23.6,12.6),
         crank_radius=10, link_centers=36, leg_length=52,
         pivot_bore=6.25, axle_clearance=4.3,
         battery_pocket=(72,40,21), board_thickness_assumed=1.6,
         printed_sliding_clearance=0.3, nominal_leg_sweep_deg=15)
(OUT/'cad_parameters.json').write_text(json.dumps(P,indent=2),encoding='utf8')

def box(dx,dy,dz,x=0,y=0,z=0):
    return cq.Workplane('XY').box(dx,dy,dz).translate((x,y,z)).val()
def cyl(r,h,x,y,z,axis=(0,0,1)):
    return cq.Solid.makeCylinder(r,h,cq.Vector(x,y,z),cq.Vector(*axis))
def union(*ss):
    a=ss[0]
    for s in ss[1:]: a=a.fuse(s)
    return a.clean()
def cut(a,*ss):
    for s in ss: a=a.cut(s)
    return a.clean()
def rounded(dx,dy,dz,x=0,y=0,z=0,r=2):
    return cq.Workplane('XY').box(dx,dy,dz).edges('|Z').fillet(r).translate((x,y,z)).val()
def yz_prism(points,x,thick):
    return cq.Workplane('YZ').polyline(points).close().extrude(thick).translate((x,0,0)).val()
def mirror_y(s): return s.mirror('XZ')
def mirror_x(s): return s.mirror('YZ')
def slot_z(x,y,z,length,width,height,along='x'):
    c=length-width
    if along=='x':
        return union(box(c,width,height,x,y,z+height/2),cyl(width/2,height,x-c/2,y,z),cyl(width/2,height,x+c/2,y,z))
    return union(box(width,c,height,x,y,z+height/2),cyl(width/2,height,x,y-c/2,z),cyl(width/2,height,x,y+c/2,z))
def rod_y(x,z,y0,length,r): return cyl(r,length,x,y0,z,(0,1,0))
def flat_link(x0,x1,z,y,thick,r=4,hole=2.4):
    a=union(box(abs(x1-x0),thick,2*r,(x0+x1)/2,y+thick/2,z),
            rod_y(x0,z,y,thick,r),rod_y(x1,z,y,thick,r))
    return cut(a,rod_y(x0,z,y-1,thick+2,hole/2),rod_y(x1,z,y-1,thick+2,hole/2))

printed=[]; refs=[]; trials=[]
COLORS={'frame':(0.18,0.31,0.39),'deck':(0.62,0.75,0.77),'joint':(0.96,0.56,0.18),
        'leg':(0.85,0.89,0.87),'battery':(0.12,0.37,0.79),'pcb':(0.08,0.45,0.32),
        'servo':(0.22,0.35,0.74),'metal':(0.6,0.61,0.64)}
def add(name,shape,kind='frame',orient=None):
    printed.append(dict(name=name,shape=shape,kind=kind,orient=orient)); return shape
def ref(name,shape,kind='pcb'):
    refs.append(dict(name=name,shape=shape,kind=kind)); return shape

# Continuous lower rim / perforated bed; side walls transfer hip load to both decks.
base=rounded(150,94,3,z=1.5,r=5)
for x in (-57,57):
    for y in (-24,0,24): base=cut(base,rounded(19,16,5,x,y,1.5,r=3))
for x in (-22,22):
    for y in (-35,35): base=cut(base,rounded(28,13,5,x,y,1.5,r=3))
walls=[]
for side in (-1,1):
    w=box(150,3,62,0,side*45.5,34)
    # Large side windows outside servo/pivot attachment zones.
    for x in (-32,0,32): w=cut(w,box(19,7,16,x,side*45.5,15))
    w=cut(w,box(26,7,22,0,side*45.5,43))
    for x in (-29.3,29.3):
        w=cut(w,box(23.6,9,12.6,x,side*45.5,42))
        for dx in (-13.9,13.9): w=cut(w,rod_y(x+dx,42,side*45.5-6,12,1.2))
    for x in (-60,60):
        for dx in (-7,7):
            for z in (27,58): w=cut(w,rod_y(x+dx,z,side*45.5-6,12,1.65))
    walls.append(w)
frame=union(base,*walls,box(3,88,8,-73.5,0,60),box(3,88,8,73.5,0,60))
# Four pillars seat the lower board tray (top=31) and top deck (top=65).
for x,y in itertools.product((-68,68),(-34,34)):
    pillar=box(9,9,62,x,y,34)
    pillar=cut(pillar,cyl(1.65,68,x,y,-1))
    # Lower deck is installed from above, supported by a dedicated lug at y=+/-27.
    lug=box(9,10,4,x,math.copysign(28,y),29)
    lug=cut(lug,cyl(1.65,8,x,math.copysign(27,y),25))
    frame=union(frame,pillar,lug)
for x,y in itertools.product((-42,42),(-18,18)):
    frame=cut(frame,cyl(1.65,7,x,y,-1))
# Speaker mounting holes in the front beam.
for y in (-25,25): frame=cut(frame,cyl(1.65,8,-78,y,59,(1,0,0)))
add('01_main_frame',frame)

# Removable battery cradle: flat floor, rounded stops, no pressure screws on cells.
tray=rounded(90,46,2.5,z=4.25,r=3)
tray=union(tray,box(2,44,10,-37,0,10.5),box(2,44,10,37,0,10.5),
           box(72,2,10,0,-21,10.5),box(72,2,10,0,21,10.5))
for x,y in itertools.product((-42,42),(-18,18)): tray=cut(tray,cyl(1.65,6,x,y,2))
for x,y in itertools.product((-23,23),(-19.5,19.5)):
    tray=cut(tray,slot_z(x,y,2,12,3,16,'x'))
add('02_battery_cradle',tray,'deck')
ref('REF_battery_68x36x18_UNCONFIRMED_SKU',rounded(68,36,18,z=15.5,r=2),'battery')

# Lower electronics deck: slotted fixtures deliberately do not assume PCB hole pitch.
lower=rounded(144,61,3,z=32.5,r=3)
for x,y in itertools.product((-68,68),(-27,27)): lower=cut(lower,cyl(1.65,6,x,y,30))
for x,y in itertools.product((-68,68),(-34,34)): lower=cut(lower,box(9.6,9.6,8,x,y,32))
for x in (-56,-38,-20,12,30,48):
    for y in (-21,21): lower=cut(lower,slot_z(x,y,30,14,3.3,6))
for x in (-37,32): lower=cut(lower,rounded(42,16,6,x,0,32.5,r=2))
add('03_lower_electronics_deck',lower,'deck')

# Universal edge rails. Support lip = 0.7 mm; header tails stay clear below board.
def board_rail(x,y,z,length,sign=1):
    # inner edge at y, board above z+5, mounting feet outside board.
    s=union(box(length,2.4,7,x,y+sign*1.2,z+3.5),
            box(length,0.7,1.4,x,y-sign*0.35,z+4.3))
    for dx in (-length/2+7,length/2-7):
        f=box(8,9,2.5,x+dx,y+sign*4.5,z+1.25)
        f=cut(f,slot_z(x+dx,y+sign*5,z-1,6,3.3,5,'y'))
        s=union(s,f)
    return s
# Rails are replaceable fit fixtures, not claimed to clamp over populated PCB areas.
for label,x,width,length in [('PCA',-37,25,60),('ESP',32,27.94,57.15)]:
    for side in (-1,1):
        add('04_'+label+'_edge_rail_'+str(side),board_rail(x,side*(width/2+0.3),34,52,side),'deck')
    total=63.389 if label=='ESP' else length
    ref('REF_'+label+'_board_outline',box(total,width,1.6,x,0,39.8))
    # component envelope inset from board edge, so it does not imply full solid PCB volume.
    ref('REF_'+label+'_component_height_ASSUMED',box(length-8,width-5,10,x,0,45.6))

top=rounded(144,80,3,z=66.5,r=3)
for x,y in itertools.product((-68,68),(-34,34)): top=cut(top,cyl(1.65,6,x,y,64))
for x in (-60,-34,-8,8,34,60):
    for y in (-30,-6,18,30): top=cut(top,slot_z(x,y,64,13,3.3,6))
for x in (-34,34): top=cut(top,rounded(40,15,6,x,-18,66.5,r=2))
add('05_upper_power_deck',top,'deck')

# Two adjustable converter sleds, following the larger submitted image envelope.
def converter_sled(x):
    s=rounded(66,36,2,x,-18,69,r=2)
    s=cut(s,rounded(43,16,5,x,-18,69,r=2))
    for dx,dy in itertools.product((-26.5,26.5),(-12,12)):
        s=union(s,cyl(3.5,4,x+dx,-18+dy,70))
        s=cut(s,slot_z(x+dx,-18+dy,67,6,3.3,10,'x'))
    for dx in (-25,25): s=cut(s,slot_z(x+dx,-18,67,10,3.3,6,'y'))
    return s
for x in (-34,34):
    add('06_converter_sled_'+str(x),converter_sled(x),'deck')
    ref('REF_converter_60x30x16_UNCONFIRMED_SKU_'+str(x),box(60,30,16,x,-18,82))
# Small generic accessory tray: amp, microphone, protected distribution/charging space.
accessory=rounded(123,31,2,0,21.5,69,r=2)
for x in (-53,-27,0,27,53):
    for y in (13,30): accessory=cut(accessory,slot_z(x,y,67,12,3.3,5))
add('07_accessory_strip',accessory,'deck')
ref('REF_MAX98357_18x19_height_ASSUMED',box(18,19,10,-47,21.5,77))
ref('REF_microphone_RESERVE_20x20x10',box(20,20,10,-18,21.5,77))
ref('REF_power_switch_fuse_BMS_RESERVE_48x22x15',box(48,22,15,26,21.5,79.5))

# Independent hip: M4 axle through fork; 6OD/4ID metal bushing inside moving leg.
# Axle/bushing/washer are purchased components. Servo moves leg through a 36 mm link.
def fork(x):
    s=box(28,4,48,x,49,40)
    s=union(s,box(28,33,4,x,63.5,62),
            box(24,4,32,x,58,46),box(24,4,32,x,78,46))
    for dx in (-12,8):
        s=union(s,yz_prism([(47,16),(47,64),(80,64)],x+dx,4))
    s=cut(s,rod_y(x,42,45,38,2.15),box(32,4,14,x,62,52))
    for dx,z in itertools.product((-7,7),(27,58)):
        s=cut(s,rod_y(x+dx,z,44,10,1.65))
    return s
def leg(x):
    s=union(rod_y(x,42,63.75,9.5,8),box(9,9.5,50,x,68.5,15),
            rod_y(x,52,63.75,9.5,4.7),box(8,9.5,10,x,68.5,47),
            rounded(25,23,6,x,68.5,-11,r=4))
    s=cut(s,rod_y(x,42,62,13,3.125),rod_y(x,52,62,13,1.2))
    # Blind tread strap slots; feet accept bonded rubber pads (not printed rubber).
    for dx in (-7,7): s=cut(s,box(3,16,3,x+dx,68.5,-13.5))
    return s
def horn_adapter(x):
    s=union(rod_y(x,42,58.5,2,6),rod_y(x,52,58.5,2,4),box(8,2,10,x,59.5,47))
    s=cut(s,rod_y(x,42,57,5,2.5),rod_y(x,52,57,5,1.2))
    # Radial slots for screws through the ORIGINAL SG90 horn; no printed spline.
    for z in (36,46): s=cut(s,box(2.3,5,4,x,59.5,z))
    return s
for x in (-60,60):
    sx=math.copysign(24,x)
    for side in (-1,1):
        transform=(lambda s:s) if side==1 else mirror_y
        suffix=('front' if x<0 else 'rear')+('_L' if side==1 else '_R')
        add('08_hip_fork_'+suffix,transform(fork(x)),'joint',('X',90))
        add('09_leg_'+suffix,transform(leg(x)),'leg',('X',90))
        add('10_link_'+suffix,transform(flat_link(sx,x,52,61,2,r=3.8)),'joint',('X',90))
        add('11_horn_adapter_'+suffix,transform(horn_adapter(sx)),'joint',('X',90))
        # SG90 envelope from drawing: body 23x12, height 23.2, flange at 16.3.
        cx=math.copysign(29.3,x)
        servo=union(box(23,23.2,12,cx,42.3,42),box(32.5,2,12,cx,48,42),
                    rod_y(sx,42,53.9,4.1,5.5))
        for dx in (-13.9,13.9): servo=cut(servo,rod_y(cx+dx,42,46,5,1.1))
        ref('REF_SG90_'+suffix,transform(servo),'servo')
        bush=cut(rod_y(x,42,63.5,10,3),rod_y(x,42,63,11,2))
        ref('REF_metal_bushing_6OD_4ID_10L_'+suffix,transform(bush),'metal')
        ref('REF_M4_axle_'+suffix,transform(rod_y(x,42,54,29,2)),'metal')

# Tail SG90 mount outside the rear wall, shaft vertical; tail uses original horn.
tail=union(box(42,28,3,97,0,59.5),box(4,64,3,77,0,59.5))
tail=cut(tail,box(23.6,12.6,8,95,0,59.5))
for x in (95-13.9,95+13.9): tail=cut(tail,cyl(1.2,8,x,0,56))
# Attach with two brackets to rear beam, accessible horizontally.
for y in (-27,27):
    tail=union(tail,box(4,10,9,77,y,55.5))
    tail=cut(tail,cyl(1.65,10,71,y,57,(1,0,0)))
    frame=cut(frame,cyl(1.65,10,70,y,57,(1,0,0)))
printed[0]['shape']=frame
add('12_tail_servo_mount',tail,'deck')
ts=union(box(23,12,23.2,95,0,56.3),box(32.5,12,2,95,0,62),cyl(5.5,4.1,89.7,0,67.9))
for x in (95-13.9,95+13.9): ts=cut(ts,cyl(1.1,5,x,0,60))
ref('REF_SG90_tail',ts,'servo')
ta=rounded(46,10,3,108.7,0,74,r=4)
ta=cut(ta,cyl(2.5,6,89.7,0,71),slot_z(98,0,71,9,2.4,6),cyl(2,6,126,0,71))
add('13_tail_horn_arm',ta,'joint')

# Speaker removable front cage. 35x25 footprint; 9 mm depth provisionally.
sp=box(12,45,31,-83,0,70)
sp=cut(sp,box(11,36,26,-81.5,0,70),box(16,30,20,-83,0,70))
for y in (-25,25):
    sp=union(sp,box(4,11,10,-77,y,59))
    sp=cut(sp,cyl(1.65,8,-81,y,59,(1,0,0)))
add('14_speaker_front_cage',sp,'deck',('Y',90))
ref('REF_speaker_35x25x7p8_allowance',box(7.8,35,25,-82.1,0,70),'metal')
# Two retaining tabs cross the outer rim only, not the diaphragm.
for side in (-1,1):
    cap=box(2,7,18,-76,side*19.5,76)
    for z in (69,82):
        cap=cut(cap,cyl(1.2,6,-79,side*20,z,(1,0,0)))
        sp=cut(sp,cyl(1.0,9,-85,side*20,z,(1,0,0)))
    add('15_speaker_retainer_'+str(side),cap,'deck',('Y',90))
for item in printed:
    if item['name']=='14_speaker_front_cage': item['shape']=sp

# Strap bridges: route cable ties/Velcro across accessories, never over mic aperture.
# Repeated fit clips allow clamping small PCBs without unverified hole coordinates.
def clip():
    s=union(box(10,12,2.5,z=1.25),box(10,3,8,0,4.5,4),box(10,6,2,0,3,7))
    return cut(s,slot_z(0,-2,-1,6,3.3,5,'y'))
trials.append(dict(name='T01_SG90_panel',shape=cut(box(43,3,23,0,0,0),box(23.6,7,12.6),
               rod_y(-13.9,0,-3,6,1.2),rod_y(13.9,0,-3,6,1.2)),orient=('X',90)))
coupon=box(46,20,4,z=2)
for x,d in zip((-16,-5,7,18),(2.4,3.3,4.3,6.25)): coupon=cut(coupon,cyl(d/2,6,x,0,-1))
trials.append(dict(name='T02_holes_2p4_3p3_4p3_6p25',shape=coupon,orient=None))
trials.append(dict(name='T03_accessory_edge_clip',shape=clip(),orient=None))
trials.append(dict(name='T04_original_horn_adapter',shape=horn_adapter(0),orient=('X',90)))
trials.append(dict(name='T05_leg_pivot_bushing_fit',shape=cut(cyl(8,10,0,0,0),cyl(3.125,12,0,0,-1)),orient=None))

def print_pose(shape,orientation):
    s=shape
    if orientation:
        axis,angle=orientation
        s=s.rotate((0,0,0),{'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}[axis],angle)
    b=s.BoundingBox()
    return s.translate((-(b.xmin+b.xmax)/2,-(b.ymin+b.ymax)/2,-b.zmin))

assembly=cq.Assembly(name='PRP_V0_FIT_PROTOTYPE_NOT_LOAD_VALIDATED')
bare=cq.Assembly(name='PRP_V0_PRINTED_FRAME_ASSEMBLED')
report={'status':'FIT_PROTOTYPE_NOT_LOAD_VALIDATED','parts':[],'trials':[],
        'limitations':['SKU mismatch battery/converter','PCB heights / some hole diameters unverified',
        'Horn pattern/spline height require physical fit','No load, fatigue, heat, or physical gait tests'],
        'cad_engine':cq.__version__}
for item in printed+refs:
    shape=item['shape']; name=item['name']
    assert shape.isValid(), name+' invalid BREP'
    color=cq.Color(*COLORS[item['kind']])
    assembly.add(shape,name=name,color=color)
    if item in printed:
        bare.add(shape,name=name,color=color)
        assert len(shape.Solids())==1, name+' disconnected solids'
        cq.exporters.export(shape,str(OUT/'step_parts'/(name+'.step')))
        posed=print_pose(shape,item['orient'])
        path=OUT/'stl_parts'/(name+'.stl')
        cq.exporters.export(posed,str(path),tolerance=0.08,angularTolerance=0.15)
        mesh=trimesh.load_mesh(path)
        b=posed.BoundingBox(); dims=[b.xlen,b.ylen,b.zlen]
        assert max(dims)<=200, name+' exceeds printer'
        assert mesh.is_watertight and mesh.is_winding_consistent, name+' invalid STL'
        report['parts'].append(dict(name=name,bbox_mm=[round(v,3) for v in dims],
            volume_mm3=round(shape.Volume(),2),solid_PLA_mass_g=round(shape.Volume()*0.00124,2),
            brep_valid=True,solids=1,stl_watertight=True))
for item in trials:
    s=print_pose(item['shape'],item['orient'])
    assert s.isValid() and len(s.Solids())==1,item['name']
    path=OUT/'stl_trial'/(item['name']+'.stl')
    cq.exporters.export(s,str(path),tolerance=0.06,angularTolerance=0.12)
    assert trimesh.load_mesh(path).is_watertight,item['name']
    cq.exporters.export(s,str(OUT/'stl_trial'/(item['name']+'.step')))
    report['trials'].append(item['name'])
assembly.save(str(OUT/'PRP_V0_with_hardware.step'))
bare.save(str(OUT/'PRP_V0_frame_only.step'))

# Pairwise collision audit distinguishes references (boxes) from printable solids.
def overlaps(items):
    result=[]
    for a,b in itertools.combinations(items,2):
        aa=a['shape'].BoundingBox(); bb=b['shape'].BoundingBox()
        if aa.xmax<=bb.xmin+1e-5 or bb.xmax<=aa.xmin+1e-5 or aa.ymax<=bb.ymin+1e-5 or bb.ymax<=aa.ymin+1e-5 or aa.zmax<=bb.zmin+1e-5 or bb.zmax<=aa.zmin+1e-5: continue
        vol=a['shape'].intersect(b['shape']).Volume()
        if vol>0.05: result.append(dict(a=a['name'],b=b['name'],volume_mm3=round(vol,3)))
    return result
report['printed_part_intersections']=overlaps(printed)
report['all_envelope_intersections']=overlaps(printed+refs)
report['leg_sweep_intersections']=[]
for angle in (-15,-7.5,7.5,15):
    moved=[]
    for item in printed:
        s=item['shape']; name=item['name']
        if name.startswith(('09_leg_','11_horn_adapter_')):
            x=(-60 if 'front' in name else 60) if name.startswith('09') else (-24 if 'front' in name else 24)
            s=s.rotate((x,0,42),(x,1,42),angle)
        elif name.startswith('10_link_'):
            t=math.radians(angle); s=s.translate((10*math.sin(t),0,10*(math.cos(t)-1)))
        moved.append(dict(name=name,shape=s))
    for hit in overlaps(moved): report['leg_sweep_intersections'].append(dict(angle=angle,**hit))
report['solid_PLA_total_g']=round(sum(i['solid_PLA_mass_g'] for i in report['parts']),2)
report['NOTE_mass']='100% CAD solid density estimate; not slicer mass or measured mass'
bounds=assembly.toCompound().BoundingBox()
report['assembly_bbox_mm']=[round(v,3) for v in (bounds.xlen,bounds.ylen,bounds.zlen)]
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k not in ('parts','all_envelope_intersections')},ensure_ascii=False,indent=2))

assert not report['printed_part_intersections'], 'Printed-part interference'
assert not report['all_envelope_intersections'], 'Hardware-envelope interference'
assert not report['leg_sweep_intersections'], 'Discrete pose interference'

# Headless render of exact triangulated solids; no CAD app automation involved.
import vtk
from vtk.util.numpy_support import numpy_to_vtk
import numpy as np
renderer=vtk.vtkRenderer(); renderer.SetBackground(0.96,0.97,0.98)
for item in printed+refs:
    verts,faces=item['shape'].tessellate(0.25,0.18)
    pts=vtk.vtkPoints(); pts.SetData(numpy_to_vtk(np.array([v.toTuple() for v in verts])))
    cells=vtk.vtkCellArray()
    for face in faces:
        cells.InsertNextCell(3)
        for j in face: cells.InsertCellPoint(j)
    poly=vtk.vtkPolyData(); poly.SetPoints(pts); poly.SetPolys(cells)
    mapper=vtk.vtkPolyDataMapper(); mapper.SetInputData(poly)
    actor=vtk.vtkActor(); actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*COLORS[item['kind']])
    actor.GetProperty().SetOpacity(0.65 if item in refs else 1)
    renderer.AddActor(actor)
win=vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.AddRenderer(renderer); win.SetSize(1500,1100)
camera=renderer.GetActiveCamera(); camera.SetPosition(-240,-300,235); camera.SetFocalPoint(5,0,35); camera.SetViewUp(0,0,1)
renderer.ResetCamera(); camera.Zoom(1.18); win.Render()
capture=vtk.vtkWindowToImageFilter(); capture.SetInput(win); capture.Update()
writer=vtk.vtkPNGWriter(); writer.SetFileName(str(OUT/'assembly_preview.png')); writer.SetInputConnection(capture.GetOutputPort()); writer.Write()
win.Finalize()
print('CAD export / mesh validation / render finished')
