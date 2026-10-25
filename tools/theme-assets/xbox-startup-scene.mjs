// Original offline-rendered geometry and shaders; reference video is never sampled.
import * as THREE from '/tools/livery-inspector/vendor/three/build/three.module.min.js';

const W=1280,H=720;
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.setSize(W,H);renderer.setPixelRatio(1);renderer.setClearColor(0);
renderer.outputColorSpace=THREE.SRGBColorSpace;
renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.9;
const canvas=document.querySelector('#output'),ctx=canvas.getContext('2d');
const smooth=(a,b,t)=>{const x=Math.max(0,Math.min(1,(t-a)/(b-a)));return x*x*(3-2*x);};
const scene=new THREE.Scene();scene.fog=new THREE.FogExp2(0x000500,.075);
const camera=new THREE.PerspectiveCamera(48,W/H,.05,80);
const chamber=new THREE.Group();scene.add(chamber);
const steel=new THREE.MeshStandardMaterial({color:0x1d251b,metalness:.83,roughness:.29});
const edge=new THREE.MeshStandardMaterial({color:0x45503d,metalness:.86,roughness:.25});
const dark=new THREE.MeshStandardMaterial({color:0x070b06,metalness:.6,roughness:.37});
const black=new THREE.MeshStandardMaterial({color:0x010201,metalness:.32,roughness:.48});
const lamp=new THREE.MeshStandardMaterial({color:0x8ab82a,emissive:0x64cd0b,emissiveIntensity:0});
const ambient=new THREE.AmbientLight(0x314327,.25);scene.add(ambient);
const key=new THREE.PointLight(0x8fff25,0,15,2);scene.add(key);
const rim=new THREE.PointLight(0x3a661e,12,20,2);rim.position.set(-3,3,4);scene.add(rim);
const back=new THREE.PointLight(0x6fa532,6,16,2);back.position.set(1,-3,-3);scene.add(back);

function mesh(geo,mat,parent,x=0,y=0,z=0){const m=new THREE.Mesh(geo,mat);m.position.set(x,y,z);parent.add(m);return m;}
function cylinder(parent,r1,r2,h,y,mat=steel){return mesh(new THREE.CylinderGeometry(r1,r2,h,64,1,false),mat,parent,0,y,0);}
function ring(parent,r,t,y,mat=edge){const m=mesh(new THREE.TorusGeometry(r,t,10,72),mat,parent,0,y,0);m.rotation.x=Math.PI/2;return m;}
function pipe(parent,points,r,mat=steel){return mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),32,r,8,false),mat,parent);}
const rotors=[];
for(const sign of [1,-1]){
 const unit=new THREE.Group();unit.position.y=sign*2.7;unit.scale.setScalar(1.22);if(sign<0)unit.rotation.z=Math.PI;chamber.add(unit);
 cylinder(unit,.79,.66,1.45,.18);cylinder(unit,.6,.8,.32,-.68,edge);
 cylinder(unit,.52,.52,.04,-.87,black);
 for(let i=0;i<9;i++)ring(unit,.805+(i%2)*.035,.038,-.2+i*.15,i%2?dark:edge);
 ring(unit,.55,.047,-.9,edge);ring(unit,.62,.035,-.83,dark);
 const rotor=new THREE.Group();unit.add(rotor);rotors.push(rotor);
 for(let j=0;j<8;j++){
  const a=j*Math.PI/4,c=Math.cos(a),s=Math.sin(a);
  pipe(rotor,[[c*.74,.95,s*.74],[c*1.08,.5,s*1.08],[c*.97,-.25,s*.97],[c*.61,-.87,s*.61]],.075,steel);
  mesh(new THREE.CylinderGeometry(.075,.075,.025,16),lamp,unit,c*.35,-.914,s*.35);
  mesh(new THREE.BoxGeometry(.08,.24,.12),edge,unit,c*.86,.3,s*.86).rotation.y=-a;
 }
 mesh(new THREE.CylinderGeometry(.115,.115,.025,24),lamp,unit,0,-.917,0);
 cylinder(unit,.47,.37,1.2,1.48,dark);
 for(let i=0;i<5;i++)ring(unit,.49,.035,1+i*.22);
}
// Outer supports, cable bundles, ribbed wall and mechanical seams give real parallax.
for(let j=0;j<7;j++){
 const a=Math.PI+j*Math.PI/6,x=Math.cos(a)*2.8,z=Math.sin(a)*2.8;
 const p=new THREE.Group();p.position.set(x,0,z);chamber.add(p);
 cylinder(p,.145,.145,8,0,steel);
 for(let k=0;k<15;k++){ring(p,.17,.025,-3.5+k*.5,k%3?steel:edge);}
 for(const sign of [-1,1])pipe(chamber,[[x,sign*3,z],[x*.75,sign*2.9,z*.75],[x*.42,sign*2.5,z*.42]],.1,dark);
}
const wall=mesh(new THREE.CylinderGeometry(3.65,3.65,15,96,1,true),new THREE.MeshStandardMaterial({color:0x091108,metalness:.44,roughness:.57,side:THREE.BackSide}),chamber);
for(let y=-6;y<=6;y+=1.15){const arc=mesh(new THREE.TorusGeometry(3.53,.09,8,48,Math.PI),dark,chamber,0,y,0);arc.rotation.x=-Math.PI/2;}
for(let i=0;i<16;i++){
 const a=i*Math.PI/8;
 if(Math.sin(a)>.01)continue;
 mesh(new THREE.BoxGeometry(.045,13,.13),dark,chamber,Math.cos(a)*3.5,0,Math.sin(a)*3.5).rotation.y=-a;
}

const coreUniforms={time:{value:0},energy:{value:0}};
const coreMaterial=new THREE.ShaderMaterial({uniforms:coreUniforms,
 vertexShader:`uniform float time; varying vec3 vP; varying vec3 vLocal;
 float wave(vec3 p){return .17*sin(p.x*4.2+time*2.1)*cos(p.y*3.6-time*1.6)+.13*sin(p.z*5.1+time*1.8)+.07*sin((p.x+p.y-p.z)*7.-time*3.1);}
 void main(){vec3 p=position*(1.+wave(normal));vLocal=p;vec4 mv=modelViewMatrix*vec4(p,1.);vP=mv.xyz;gl_Position=projectionMatrix*mv;}`,
 fragmentShader:`uniform float time;uniform float energy;varying vec3 vP;varying vec3 vLocal;
 void main(){vec3 n=normalize(cross(dFdx(vP),dFdy(vP)));vec3 v=normalize(-vP);
 float face=abs(dot(n,v));float spec=pow(max(0.,dot(reflect(normalize(vec3(.4,-.7,-1.)),n),v)),22.);
 float vein=.5+.5*sin(vLocal.x*12.+sin(vLocal.y*8.+time*2.)+vLocal.z*9.-time*3.);
 float deep=pow(1.-face,1.8);vec3 c=mix(vec3(.26,.8,.025),vec3(.73,1.,.27),face*.6+energy*.25);
 c*=.8+vein*.2;c=mix(c,vec3(.025,.23,.003),deep*.83);c+=spec*vec3(.8,.95,.55);
 gl_FragColor=vec4(c,1.);}`});
const core=new THREE.Mesh(new THREE.SphereGeometry(1,96,64),coreMaterial);scene.add(core);
const skin=new THREE.Mesh(new THREE.SphereGeometry(1,64,32),new THREE.MeshPhysicalMaterial({color:0x66bf13,metalness:.35,roughness:.1,transparent:true,opacity:.16,side:THREE.BackSide,depthWrite:false}));core.add(skin);skin.scale.setScalar(1.09);

function flareTexture(){
 const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');
 const f=g.createRadialGradient(64,64,0,64,64,64);
 f.addColorStop(0,'rgba(255,255,240,1)');f.addColorStop(.12,'rgba(200,255,100,.7)');f.addColorStop(.32,'rgba(80,220,10,.2)');f.addColorStop(1,'rgba(0,100,0,0)');
 g.fillStyle=f;g.fillRect(0,0,128,128);return new THREE.CanvasTexture(c);
}
const flareMap=flareTexture();
const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:flareMap,transparent:true,blending:THREE.AdditiveBlending,depthWrite:false,depthTest:false,opacity:.7}));glow.renderOrder=10;scene.add(glow);
const filaments=[];
for(let i=0;i<5;i++){
 const positions=new Float32Array(64*3);const colors=new Float32Array(64*3);
 for(let j=0;j<64;j++){const b=Math.sin(j/63*Math.PI);colors.set([.18*b,.65*b,.025*b],j*3);}
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(positions,3));geo.setAttribute('color',new THREE.BufferAttribute(colors,3));
 const line=new THREE.Line(geo,new THREE.LineBasicMaterial({vertexColors:true,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false}));scene.add(line);filaments.push(line);
}

// The reveal is the full product name, never an isolated replacement initial.
const brandScene=new THREE.Scene();
const brandCamera=new THREE.PerspectiveCamera(38,W/H,.01,100);brandCamera.position.z=6;
const brand=new THREE.Group();brandScene.add(brand);
const brandKey=new THREE.DirectionalLight(0xeaffc1,4);brandKey.position.set(-2,4,4);brandScene.add(brandKey);
const brandFill=new THREE.DirectionalLight(0x86bf25,2);brandFill.position.set(3,-1,5);brandScene.add(brandFill);
brandScene.add(new THREE.AmbientLight(0x6e9125,.65));
const brandMat=new THREE.MeshStandardMaterial({color:0x8ac51e,metalness:.55,roughness:.31,emissive:0x1b3300,emissiveIntensity:.25});
const brandEdge=new THREE.MeshStandardMaterial({color:0x31450f,metalness:.68,roughness:.29});
const letters=[
 [[3,4],[12,4],[12,27],[35,4],[47,4],[21,31],[49,60],[36,60],[12,36],[12,60],[3,60]],
 [[58,4],[103,4],[103,12],[67,12],[67,28],[96,28],[96,36],[67,36],[67,60],[58,60]],
 [[114,4],[150,4],[161,15],[161,30],[150,41],[123,41],[123,60],[114,60]],
 [[183,4],[235,4],[235,12],[186,12],[182,16],[182,26],[224,26],[235,37],[235,49],[224,60],[173,60],[173,52],[221,52],[226,47],[226,40],[183,35],[173,25],[173,14]]
];
letters.forEach((points,i)=>{
 const shape=new THREE.Shape();points.forEach(([x,y],j)=>j?shape.lineTo((x-119)*.017,(32-y)*.010):shape.moveTo((x-119)*.017,(32-y)*.010));shape.closePath();
 if(i===2){const h=new THREE.Path();[[123,12],[123,33],[147,33],[152,28],[152,17],[147,12]].forEach(([x,y],j)=>j?h.lineTo((x-119)*.017,(32-y)*.010):h.moveTo((x-119)*.017,(32-y)*.010));h.closePath();shape.holes.push(h);}
 const geo=new THREE.ExtrudeGeometry(shape,{depth:.055,bevelEnabled:true,bevelSize:.015,bevelThickness:.018,bevelSegments:3,steps:1});
 brand.add(new THREE.Mesh(geo,[brandMat,brandEdge]));
});
const sampleState={};
window.renderFrame=(seconds)=>{
 const t=Math.max(0,seconds),charge=smooth(.3,4.5,t),burst=smooth(4.2,4.8,t);
 const pulse=Math.pow(.5+.5*Math.sin(t*7.5+Math.sin(t*3.7)),5);
 coreUniforms.time.value=t;coreUniforms.energy.value=charge;
 const size=.16+charge*.34+pulse*(.025+charge*.04)+burst*.8;
 core.scale.setScalar(size);core.rotation.set(t*.39,t*.78,t*.28);
 core.position.set(Math.sin(t*2.1)*.025,Math.cos(t*1.6)*.03,0);
 glow.position.copy(core.position);glow.scale.setScalar(size*(5.5+charge*2));glow.material.opacity=.25+charge*.35+pulse*.08;
 key.position.copy(core.position);key.intensity=.6+charge*32+pulse*charge*14+burst*120;
 lamp.emissiveIntensity=smooth(.7,2.3,t)*(.55+charge*.9+pulse*.3);
 rotors[0].rotation.y=t*.29;rotors[1].rotation.y=-t*.23+.4;
 for(let i=0;i<filaments.length;i++){
  const line=filaments[i],p=line.geometry.attributes.position;
  for(let j=0;j<64;j++){
   const u=j/63,a=u*4.8+t*(i%2?-1.8:1.5)+i*1.26;
   const r=size*(1.15+.22*Math.sin(a*2.+t));
   p.setXYZ(j,Math.cos(a)*r,Math.sin(a)*r*.6,Math.sin(a*1.5+i)*r*.7);
  }
  p.needsUpdate=true;line.material.opacity=.15+charge*.55;
 }
 const orbit=t*.13+smooth(1.0,4.3,t)*.28;
 const distance=10.6-charge*3.7-burst*4.9;
 camera.position.set(Math.sin(orbit)*distance*.5,Math.sin(t*.5)*.35,Math.cos(orbit*.5)*distance);
 camera.lookAt(core.position);camera.rotateZ(-.07+Math.sin(t*.8)*.06+charge*.16);
 ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.fillStyle='#000';ctx.fillRect(0,0,W,H);
 const reveal=smooth(4.68,5.0,t);
 if(reveal<1){
  renderer.render(scene,camera);ctx.drawImage(renderer.domElement,0,0);
  ctx.save();ctx.globalCompositeOperation='screen';ctx.globalAlpha=.28;ctx.filter='blur(12px)';ctx.drawImage(renderer.domElement,0,0);ctx.restore();
 }
 if(reveal>0){
  const settle=smooth(4.72,5.6,t);brand.scale.setScalar(.82+(1-settle)*7);
  brand.rotation.set((1-settle)*.16,(1-settle)*-.13,(1-settle)*-.025);
  renderer.render(brandScene,brandCamera);ctx.globalAlpha=reveal;ctx.drawImage(renderer.domElement,0,0);ctx.globalAlpha=1;
 }
 // Broad exposure bloom is tied to the one rising energy pulse, not repeating flashes.
 const flash=smooth(4.25,4.64,t)*(1-smooth(4.7,5.17,t));
 if(flash>0){ctx.fillStyle=`rgba(181,255,91,${flash*.95})`;ctx.fillRect(0,0,W,H);}
 const entrance=smooth(0,.4,t),exit=1-smooth(11.0,11.72,t);
 if(t>6.5){
  ctx.save();ctx.globalAlpha=smooth(7.55,8.05,t)*.8;
  ctx.fillStyle='#9eb77c';ctx.font='500 15px Arial';ctx.textAlign='center';
  ctx.fillText("KLOUDY'S FORZA PAINTER SUITE",640,455);ctx.restore();
 }
 ctx.fillStyle=`rgba(0,0,0,${1-entrance*exit})`;ctx.fillRect(0,0,W,H);
 Object.assign(sampleState,{time:t,camera:camera.position.toArray(),coreSize:size,rotors:rotors.map(r=>r.rotation.y),drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles});
 return canvas.toDataURL('image/png').split(',')[1];
};
window.motionSnapshot=()=>({...sampleState});
window.renderFrame(0);window.ready=true;
