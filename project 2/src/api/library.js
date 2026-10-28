'use strict';
const $ = id => document.getElementById(id);
const canvas = $('library'), screen = canvas.getContext('2d');
const W = 768, H = 512, motion = matchMedia('(prefers-reduced-motion: reduce)');
const scene = document.createElement('canvas'); scene.width = W; scene.height = H;
const ctx = scene.getContext('2d');
const reader = Object.freeze({x:384,y:404});
const shelves = [
  {book:'I',x:156,y:68,w:132,h:128,stop:[247,221],color:'#c6a15c',name:'Commerce',ladder:true},
  {book:'II',x:316,y:68,w:141,h:128,stop:[441,221],color:'#bb7952',name:'Fonds de commerce',ladder:true},
  {book:'III',x:486,y:68,w:129,h:128,stop:[594,221],color:'#6a9e94',name:'Effets de commerce',ladder:true},
  {book:'IV',x:64,y:216,w:89,h:117,stop:[162,326],color:'#8c7ca1',name:'Procédures collectives'},
  {book:'V',x:618,y:216,w:88,h:117,stop:[610,326],color:'#7697b4',name:'Contrats'},
];
const catalogue = {x:364,y:244,w:40,h:26,stop:[394,285],name:'Archives'};
const research = {x:210,y:259,w:130,h:58,stop:[275,339]};
const home=[513,400], delivery=[492,400];
const actor={x:home[0],y:home[1],dir:'left',path:[],carry:false,walking:false,lift:0,pose:'idle'};
let busy=false, citations=[], activeShelf=null, delivered=0, sourceIndex=0;
let history=[], requestId=0, controller=null;
let candidates=[], evidenceAt=0, progress='', speech='';
let outcome='welcome', last=0, frame=0, camera=reader.x*.65+home[0]*.35, cameraY=0, arrival=0, walkDistance=0;
let view={scale:1,x:0,y:0}, selectedShelves=[], sourceRequest=0;
const articleCache=new Map(), backdrop=new Image();
backdrop.src='/assets/midnight-library.png';
backdrop.addEventListener('load',()=>draw());
backdrop.addEventListener('error',()=>{$('status').hidden=false;$('status').textContent='La salle n’a pas pu être chargée. Actualisez la page.';draw();});

function rect(g,x,y,w,h,color){g.fillStyle=color;g.fillRect(Math.round(x),Math.round(y),w,h);}
function text(g,value,x,y,color='#e7cca0',size=10){g.fillStyle=color;g.font=`${size}px LibraryPixel`;g.textAlign='center';g.fillText(value,Math.round(x),Math.round(y));}
function noise(n){return Math.abs(Math.sin(n*73.37)*1949)%1;}
function book(g,x,y,color='#7d3c35',number='',angle=0){
  g.save();g.translate(Math.round(x),Math.round(y));if(angle)g.rotate(angle);
  rect(g,-9,-12,18,23,'#171c26');rect(g,-8,-12,16,21,color);rect(g,-5,-9,11,15,'#c59d5b');rect(g,-4,-8,9,13,color);rect(g,-7,-11,2,19,'#d5b474');rect(g,-5,9,12,2,'#c3b18d');
  if(number)text(g,number,1,3,'#f1d99b',8);g.restore();
}
function makeLight(radius,color){
  const light=document.createElement('canvas');light.width=light.height=radius*2;
  const g=light.getContext('2d');
  for(let y=-radius;y<radius;y+=2)for(let x=-radius;x<radius;x+=2){const d=Math.hypot(x,y)/radius;if(d<1){g.globalAlpha=(1-d)**2*.22;rect(g,x+radius,y+radius,2,2,color);}}
  return light;
}
const amber=makeLight(88,'#f2ad45'), moon=makeLight(100,'#438bc1');
function light(g,stamp,x,y,intensity=1){g.save();g.globalCompositeOperation='screen';g.globalAlpha=intensity;g.drawImage(stamp,Math.round(x-stamp.width/2),Math.round(y-stamp.height/2));g.restore();}

let audio=null, master=null, noiseBuffer=null, soundEnabled=false;
async function toggleSound(){
  const button=$('ambience');
  try{
    if(!audio){
      const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error('Audio unavailable');
      audio=new Audio();master=audio.createGain();master.gain.value=0;master.connect(audio.destination);
      const buffer=audio.createBuffer(1,audio.sampleRate*3,audio.sampleRate),data=buffer.getChannelData(0);
      for(let i=0;i<data.length;i++)data[i]=(Math.random()*2-1)*.3;
      noiseBuffer=buffer;
      const rain=audio.createBufferSource(),filter=audio.createBiquadFilter();rain.buffer=buffer;rain.loop=true;filter.type='lowpass';filter.frequency.value=1100;rain.connect(filter);filter.connect(master);rain.start();
    }
    await audio.resume();soundEnabled=!soundEnabled;master.gain.setTargetAtTime(soundEnabled ? .12 : 0,audio.currentTime,.15);
    button.setAttribute('aria-pressed',String(soundEnabled));button.setAttribute('aria-label',soundEnabled?'Couper l’ambiance sonore':'Activer l’ambiance sonore');button.title=button.getAttribute('aria-label');
  }catch{button.setAttribute('aria-pressed','false');button.title='Le son est indisponible dans ce navigateur.';soundEnabled=false;}
}
function cue(kind){
  if(!soundEnabled||!audio||audio.state!=='running'||document.hidden)return;
  if(kind==='page'){
    const page=audio.createBufferSource(),filter=audio.createBiquadFilter(),gain=audio.createGain(),now=audio.currentTime;
    page.buffer=noiseBuffer;filter.type='bandpass';filter.frequency.value=2400;filter.Q.value=.6;
    gain.gain.setValueAtTime(.001,now);gain.gain.exponentialRampToValueAtTime(.55,now+.035);gain.gain.exponentialRampToValueAtTime(.001,now+.18);
    page.connect(filter);filter.connect(gain);gain.connect(master);page.start(now,Math.random()*2,.2);page.onended=()=>{page.disconnect();filter.disconnect();gain.disconnect();};return;
  }
  const tone=audio.createOscillator(),gain=audio.createGain(),now=audio.currentTime;
  const [frequency,duration,volume]=kind==='step'?[130,.06,.35]:kind==='softstep'?[75,.05,.1]:[630,.22,.15];
  tone.type=kind.endsWith('step')?'triangle':'sine';tone.frequency.setValueAtTime(frequency,now);tone.frequency.exponentialRampToValueAtTime(frequency*.55,now+duration);
  gain.gain.setValueAtTime(.001,now);gain.gain.exponentialRampToValueAtTime(volume,now+.01);gain.gain.exponentialRampToValueAtTime(.001,now+duration);tone.connect(gain);gain.connect(master);tone.start();tone.stop(now+duration+.02);
  tone.onended=()=>{tone.disconnect();gain.disconnect();};
}
$('ambience').addEventListener('click',toggleSound);

function rain(time){
  const windows=[[117,2,126],[236,2,61],[385,2,61],[539,2,61],[657,2,126]];
  ctx.save();ctx.globalAlpha=.32;
  for(const [cx,top,bottom] of windows){
    ctx.save();ctx.beginPath();ctx.moveTo(cx-29,bottom);ctx.lineTo(cx-29,27);ctx.lineTo(cx-20,12);ctx.lineTo(cx,top+3);ctx.lineTo(cx+20,12);ctx.lineTo(cx+29,27);ctx.lineTo(cx+29,bottom);ctx.closePath();ctx.clip();
    for(let i=0;i<16;i++){const x=cx-29+noise(i+cx)*58,y=top+(i*17+(motion.matches?0:time/48))%(bottom-top);rect(ctx,x,y,1,3+noise(i)*3,'#76a4c5');}
    ctx.restore();
  }
  ctx.restore();
}
function character(g,x,y,dir,librarian,time,walking){
  x=Math.round(x);y=Math.round(y);
  const phase=Math.floor(time/115)%4,stride=walking?[0,2,0,-2][phase]:0;
  const outline='#151b28',coat=librarian?'#9d7343':'#344b64',lightCoat=librarian?'#c09a5c':'#55758a',hair=librarian?'#cbc2a2':'#26303a';
  rect(g,x-12,y-2,24,4,'#0b122575');rect(g,x-8,y-8+Math.max(0,stride),6,7,outline);rect(g,x+2,y-8+Math.max(0,-stride),6,7,outline);rect(g,x-7,y-7+Math.max(0,stride),4,3,'#5e5143');rect(g,x+3,y-7+Math.max(0,-stride),4,3,'#5e5143');
  rect(g,x-11,y-27,22,20,outline);rect(g,x-8,y-26,16,18,coat);rect(g,x-8,y-26,3,16,lightCoat);rect(g,x+6,y-25,2,17,'#554738');
  rect(g,x-12,y-24+stride,4,13,coat);rect(g,x+8,y-24-stride,4,13,coat);rect(g,x-12,y-13+stride,4,4,'#c69d70');rect(g,x+8,y-13-stride,4,4,'#c69d70');
  if(librarian){rect(g,x-4,y-26,9,14,'#435e58');rect(g,x,y-24,1,13,'#d2bc80');rect(g,x-1,y-23,2,3,'#d6ad54');rect(g,x-6,y-26,3,8,'#d1bc8b');rect(g,x+4,y-26,3,8,'#bca573');}
  const breath=motion.matches||walking?0:Math.floor(Math.sin(time/950)*.65);
  const glance=!librarian&&Math.abs(actor.x-reader.x)>35?Math.sign(actor.x-reader.x):0;
  const hx=x+glance,hy=y-43+breath;
  rect(g,hx-10,hy,20,19,outline);rect(g,hx-8,hy+2,16,15,'#cfa77a');rect(g,hx-9,hy,18,6,hair);rect(g,hx-7,hy-1,14,2,hair);rect(g,hx-9,hy+5,3,9,hair);rect(g,hx+6,hy+5,3,9,hair);rect(g,hx-6,hy+1,11,2,librarian?'#e2d5af':'#35424d');
  if(dir==='up'){rect(g,hx-7,hy+5,14,10,hair);rect(g,hx-5,hy+15,10,3,librarian?'#a7997b':'#1d2734');if(glance)rect(g,hx+(glance>0?7:-9),hy+10,2,3,'#cfa77a');}
  else if(dir==='down'){
    if(librarian){rect(g,hx-7,hy+9,6,4,'#5a6058');rect(g,hx+1,hy+9,6,4,'#5a6058');rect(g,hx-1,hy+10,2,1,'#b9a370');rect(g,hx-6,hy+10,4,1,'#d5d5b2');rect(g,hx+2,hy+10,4,1,'#d5d5b2');}
    else{rect(g,hx-5,hy+10,2,2,outline);rect(g,hx+3,hy+10,2,2,outline);}rect(g,hx-2,hy+15,4,1,'#9f704d');
  }else{const right=dir==='right';rect(g,hx+(right?3:-5),hy+10,2,2,outline);rect(g,hx+(right?8:-10),hy+11,2,3,'#e2b986');rect(g,hx+(right?-8:3),hy+5,6,10,hair);if(librarian){rect(g,hx+(right?1:-7),hy+9,6,4,'#697367');rect(g,hx+(right?2:-6),hy+10,4,1,'#d2d3b0');}}
  if(librarian&&actor.carry)book(g,x+10,y-18,'#785443');
  else if(librarian&&actor.pose==='reading'){
    rect(g,x-9,y-21,20,11,'#433526');rect(g,x-8,y-21,9,9,'#ead7a5');rect(g,x+1,y-21,9,9,'#cfba8d');rect(g,x,y-21,1,10,'#947747');rect(g,x-5,y-18,4,1,'#997e56');rect(g,x+3,y-18,4,1,'#997e56');
  }else if(librarian&&!busy&&!actor.path.length&&outcome==='invalid'){
    rect(g,x+7,y-22,13,11,'#d0bd95');rect(g,x+10,y-20,2,7,'#985d4b');rect(g,x+8,y-18,7,2,'#985d4b');
  }else if(librarian&&!walking&&Math.floor(time/1000)%11===8){rect(g,x+(dir==='left'?-10:7),y-32,4,5,'#cfa77a');}
}
function sourceBooks(){
  const books=new Map();citations.forEach((citation,index)=>{if(!books.has(citation.record_id))books.set(citation.record_id,{citation,index});});return [...books.values()];
}
function bookPosition(index){return {x:419+index%3*18,y:342+Math.floor(index/3)*26};}
function researchPosition(index){return {x:224+index%5*24,y:279+Math.floor(index/5)*25};}
function researchTable(time){
  rect(ctx,research.x,research.y,research.w,research.h,'#171c26');rect(ctx,212,261,126,53,'#68472d');rect(ctx,215,264,120,47,'#342b29');
  for(let i=0;i<8;i++)rect(ctx,219+i*15,267,1,40,i%2?'#3c302a':'#302827');
  rect(ctx,214,262,122,1,'#bb965d');for(const x of [213,334])for(const y of [262,312])rect(ctx,x,y,2,2,'#c4a267');
  rect(ctx,212,314,126,3,'#b1894e');rect(ctx,214,317,5,6,'#251f24');rect(ctx,331,317,5,6,'#251f24');
  rect(ctx,225,247,100,11,'#202933');text(ctx,candidates.length?`${candidates.length} LIVRES REPÉRÉS`:'TABLE DE LECTURE',275,255,'#d6bb7f',8);
  candidates.forEach((candidate,index)=>{
    const cited=citations.findIndex(c=>c.record_id===candidate.record_id);
    if(cited>=0&&(actor.carry||delivered))return;
    const target=researchPosition(index),shelf=section(candidate),p=motion.matches?1:Math.max(0,Math.min(1,(time-evidenceAt-index*35)/650));
    const start={x:shelf.x+shelf.w/2,y:shelf.y+shelf.h/2};
    ctx.save();ctx.globalAlpha=!busy&&outcome!=='welcome'&&cited<0?.3:1;
    book(ctx,start.x+(target.x-start.x)*p,start.y+(target.y-start.y)*p-Math.sin(p*Math.PI)*22,shelf.color||'#997348',cited>=0?String(cited+1):'');
    if(cited>=0&&p===1){rect(ctx,target.x-11,target.y+12,22,2,'#efcf7b');}
    ctx.restore();
  });
}
function thought(){
  if(!speech||(!busy&&!actor.path.length))return;
  ctx.font='10px LibraryPixel';
  const lines=[''];for(const word of speech.split(' ')){const last=lines.length-1,test=lines[last]?`${lines[last]} ${word}`:word;if(ctx.measureText(test).width>180&&lines[last])lines.push(word);else lines[last]=test;}
  const w=Math.ceil(Math.max(...lines.map(line=>ctx.measureText(line).width)))+16,h=lines.length*12+12;
  const x=Math.max(4,Math.min(W-w-4,Math.round(actor.x-w/2))),y=Math.round(actor.y-52-actor.lift-h);
  rect(ctx,x,y,w,h,'#17202b');rect(ctx,x+2,y+2,w-4,h-4,'#d7c495');rect(ctx,actor.x-3,y+h,6,5,'#17202b');rect(ctx,actor.x-1,y+h-2,2,5,'#d7c495');
  ctx.textAlign='left';ctx.fillStyle='#403727';lines.forEach((line,i)=>ctx.fillText(line,x+8,y+14+i*12));
}
function deskBooks(time){
  const books=sourceBooks();
  for(let i=0;i<Math.min(delivered,books.length);i++){
    const p=motion.matches?1:Math.min(1,Math.max(0,(time-arrival-i*120)/550));
    const {x:endX,y:endY}=bookPosition(i);
    const x=actor.x+(endX-actor.x)*p,y=actor.y-20+(endY-actor.y+20)*p-Math.sin(p*Math.PI)*24;
    book(ctx,x,y,section(books[i].citation).color||'#997348',String(books[i].index+1));
    if(p===1&&time-arrival<1400&&!motion.matches){rect(ctx,endX-13,endY-14,2,2,'#e9cb7c');rect(ctx,endX+12,endY-6,2,2,'#e9cb7c');}
  }
}
function evidence(time){
  if(!candidates.length&&!citations.length)return;
  for(const s of selectedShelves){
    ctx.save();ctx.globalAlpha=s===activeShelf ? .65 : .25;
    rect(ctx,s.x+4,s.y+s.h-2,s.w-8,2,'#efc975');
    const cx=s.x+s.w/2,y=s.y+9-(motion.matches?0:Math.floor(time/500)%2);
    rect(ctx,cx-1,y-5,2,10,'#f3cf7c');rect(ctx,cx-5,y-1,10,2,'#f3cf7c');ctx.restore();
  }
  if(citations.length&&activeShelf){
    ctx.save();ctx.globalAlpha=.22;
    const points=[research.stop,[190,339],[190,236],[566,236],[566,400],delivery];
    for(let j=1;j<points.length;j++){
      const [x1,y1]=points[j-1],[x2,y2]=points[j],dist=Math.hypot(x2-x1,y2-y1);
      for(let d=0;d<dist;d+=8){const t=d/dist;rect(ctx,x1+(x2-x1)*t,y1+(y2-y1)*t,2,1,'#efcb76');}
    }
    ctx.restore();
  }
}
function draw(time=performance.now()){
  rect(ctx,0,0,W,H,'#101c30');
  if(backdrop.complete&&backdrop.naturalWidth){ctx.imageSmoothingEnabled=false;ctx.drawImage(backdrop,0,0,W,H);}else{text(ctx,'Les Archives de Minuit',384,200,'#d2b475',14);text(ctx,'La salle s’éveille…',384,230,'#8b9aab');}
  rain(time);evidence(time);researchTable(time);
  character(ctx,actor.x,actor.y-actor.lift,actor.dir,true,time,actor.walking||actor.lift>0);
  if(backdrop.naturalWidth)for(const s of shelves.filter(s=>!s.ladder)){
    if(actor.y<s.y+s.h&&actor.x+13>s.x&&actor.x-13<s.x+s.w)ctx.drawImage(backdrop,s.x*2,s.y*2,s.w*2,s.h*2,s.x,s.y,s.w,s.h);
  }
  character(ctx,reader.x,reader.y,'up',false,time,false);
  // The chair back sits in front of the seated reader's lower body.
  if(backdrop.naturalWidth)ctx.drawImage(backdrop,720,766,100,104,360,383,50,52);
  deskBooks(time);
  for(const s of shelves){rect(ctx,s.x+s.w/2-11,s.y+s.h-12,22,10,'#242a2de0');text(ctx,s.book,s.x+s.w/2,s.y+s.h-3,'#c9ae76',9);}
  light(ctx,moon,116,177,.6);light(ctx,moon,657,177,.6);
  for(const [x,y] of [[174,30],[469,31],[590,30],[119,151],[683,148]])light(ctx,amber,x,y,motion.matches?.8:.78+Math.sin(time/530+x)*.1);
  light(ctx,amber,314,345,busy?1.55:1.1);light(ctx,amber,reader.x,reader.y-17,busy?.48:.28);
  light(ctx,amber,275,288,candidates.length?.35:.12);
  ctx.save();
  for(let i=0;i<32;i++){
    const x=140+noise(i+6)*490+Math.sin((motion.matches?0:time)/3100+i)*3,y=205+(noise(i+87)*230-(motion.matches?0:time/550)+2300)%230;
    ctx.globalAlpha=.15+noise(i+16)*.35;rect(ctx,x,y,1,i%5===0?2:1,i%3?'#d4b778':'#84b3cf');
  }
  ctx.restore();
  if(speech&&(busy||actor.path.length))thought();
  else if(!actor.path.length&&(outcome==='missing'||outcome==='invalid')){text(ctx,outcome==='invalid'?'!':'?',actor.x,actor.y-52,'#e5bc73',12);}
  const panel=[$('form'),$('loading'),$('result')].find(el=>!el.hidden),space=Math.max(canvas.height*.3,(panel.getBoundingClientRect().top-28)/2);
  const scale=Math.max(canvas.width/W,space/(reader.y+26)),visible=canvas.width/scale;
  const target=busy||actor.path.length?(reader.x+actor.x)/2:reader.x*.65+actor.x*.35;
  camera=motion.matches?target:camera+(target-camera)*.09;
  const center=Math.max(visible/2,Math.min(W-visible/2,camera));
  let y=Math.min(0,space-(reader.y+18)*scale);
  if(busy||actor.path.length)y=Math.max(y,Math.min(0,12-(actor.y-104-actor.lift)*scale));
  cameraY=motion.matches?y:cameraY+(y-cameraY)*.18;
  view={scale,x:Math.round(canvas.width/2-center*scale),y:Math.round(cameraY)};
  screen.imageSmoothingEnabled=false;rect(screen,0,0,canvas.width,canvas.height,'#101c30');screen.drawImage(scene,view.x,view.y,Math.round(W*scale),Math.round(H*scale));
}

function route(points){
  actor.path=points.map(p=>({x:p[0],y:p[1],pause:p[2]||0,duration:p[2]||0,shelf:p[3],pickup:p[4]}));actor.lift=0;
  if(motion.matches){const end=points.at(-1);if(end){actor.x=end[0];actor.y=end[1];}actor.path=[];actor.walking=false;finishRoute();draw();}
}
function aisle(){
  if(actor.x<350&&actor.y>236)return [[190,actor.y],[190,236]];
  if(actor.y>315)return actor.x<220?[[190,actor.y],[190,236]]:actor.x>590?[[578,actor.y],[578,236]]:[[566,actor.y],[566,236]];
  return [[430,actor.y],[430,236]];
}
function goHome(){route([...aisle(),[566,236],[566,400],delivery]);}
function finishRoute(){
  actor.dir='left';actor.pose=busy?'reading':'idle';actor.lift=0;
  if(!busy&&actor.carry){delivered=sourceBooks().length;arrival=performance.now();actor.carry=false;cue('book');}
}
function search(){delivered=0;activeShelf=null;selectedShelves=[];actor.carry=false;actor.pose='walking';route([...aisle(),[430,236],[430,285],catalogue.stop]);$('scene-caption').textContent='Le bibliothécaire consulte le catalogue.';}
function section(citation){const roman=(citation.heading_path||[]).join(' ').match(/Livre (IV|III|II|V|I)\b/);return shelves.find(s=>s.book===roman?.[1])||catalogue;}
function collect(items){
  selectedShelves=[...new Set(items.map(section))];actor.carry=false;activeShelf=selectedShelves[0]||null;
  if(!selectedShelves.length){goHome();$('scene-caption').textContent=outcome==='clarification'?'Le bibliothécaire attend une précision.':outcome==='invalid'?'Le passage ne peut pas être vérifié.':'Les archives ne suffisent pas à répondre.';return;}
  const atTable=Math.abs(actor.x-research.stop[0])<1&&Math.abs(actor.y-research.stop[1])<1;
  const path=atTable?[]:[...aisle(),[190,236],[190,339]];
  path.push([...research.stop,.45,null,true],[190,339],[190,236],[566,236],[566,400],delivery);route(path);
  if(motion.matches){delivered=sourceBooks().length;actor.carry=false;arrival=performance.now();draw();}
  $('scene-caption').textContent='Votre réponse est prête. Le bibliothécaire apporte les livres cités.';
}
function advance(dt){
  actor.walking=false;actor.lift=0;
  let remaining=Math.min(dt,.25);
  while(remaining>0&&actor.path.length){
    const target=actor.path[0],dx=target.x-actor.x,dy=target.y-actor.y,distance=Math.abs(dx)+Math.abs(dy);
    if(distance>.05){
      const travel=Math.min(distance,remaining*165);
      if(Math.abs(dx)>.05){const amount=Math.min(travel,Math.abs(dx));actor.x+=Math.sign(dx)*amount;remaining-=amount/165;actor.dir=dx>0?'right':'left';walkDistance+=amount;}
      else{const amount=Math.min(travel,Math.abs(dy));actor.y+=Math.sign(dy)*amount;remaining-=amount/165;actor.dir=dy>0?'down':'up';walkDistance+=amount;}
      actor.walking=true;actor.pose='walking';
      if(walkDistance>36){walkDistance=0;cue(actor.x>201&&actor.x<576&&actor.y>254&&actor.y<466?'softstep':'step');}
    }else if(target.pause>0){
      const used=Math.min(remaining,target.pause);target.pause-=used;remaining-=used;
      if(target.shelf){activeShelf=target.shelf;const progress=1-target.pause/target.duration;actor.dir=target.shelf===catalogue?'down':'up';actor.pose='reading';actor.lift=target.shelf.ladder?Math.round(Math.sin(progress*Math.PI)*34):0;if(progress>.55)actor.carry=true;}
      if(target.pickup){actor.dir='up';actor.pose='reading';if(target.pause<target.duration/2)actor.carry=true;}
    }else actor.path.shift();
  }
  if(!actor.path.length)finishRoute();
}
function tick(now){frame=requestAnimationFrame(tick);if(now-last<32)return;const dt=(now-last)/1000;last=now;advance(dt);draw(now);}
function animate(){cancelAnimationFrame(frame);last=performance.now();if(!motion.matches&&!document.hidden)frame=requestAnimationFrame(tick);else draw();}
function resize(){const bounds=$('game').getBoundingClientRect();canvas.width=Math.ceil(bounds.width/2);canvas.height=Math.ceil(bounds.height/2);draw();}
function show(id){for(const panel of ['form','loading','result'])$(panel).hidden=panel!==id;draw();}
function newQuestion(){show('form');$('status').hidden=true;$('question').value='';$('question').focus({preventScroll:true});cue('page');}
function resetConversation(){
  requestId++;controller?.abort();controller=null;history=[];busy=false;citations=[];candidates=[];progress='';speech='';evidenceAt=0;selectedShelves=[];activeShelf=null;delivered=0;sourceIndex=0;arrival=0;walkDistance=0;outcome='welcome';
  Object.assign(actor,{x:home[0],y:home[1],dir:'left',path:[],carry:false,walking:false,lift:0,pose:'idle'});
  sourceRequest++;if($('source-dialog').open)$('source-dialog').close();
  for(const id of ['answer','book-title','book-quote','book-claim','book-page','book-section','book-number','book-article','article-title','article-status'])$(id).replaceChildren();
  $('publisher').removeAttribute('href');$('publisher').hidden=true;$('open-book').hidden=true;
  $('submit').disabled=false;$('question').readOnly=false;$('scene-caption').textContent='Un nouveau carnet est ouvert. La bibliothèque vous accueille.';
  newQuestion();$('status').textContent='';
}
$('reset').addEventListener('click',resetConversation);
const observer=new ResizeObserver(resize);for(const id of ['game','form','loading','result'])observer.observe($(id));
resize();animate();document.fonts.ready.then(()=>draw());
motion.addEventListener('change',()=>{
  if(motion.matches&&actor.path.length){const end=actor.path.at(-1);actor.x=end.x;actor.y=end.y;actor.path=[];actor.walking=false;if(!busy&&citations.length){delivered=sourceBooks().length;actor.carry=false;}finishRoute();}animate();
});
document.addEventListener('visibilitychange',()=>{if(master)master.gain.setTargetAtTime(soundEnabled&&!document.hidden ? .12 : 0,audio.currentTime,.15);animate();});

function scrollArticle(){requestAnimationFrame(()=>{const article=$('book-article'),mark=article.querySelector('mark');if($('source-dialog').open&&article.clientHeight&&mark)article.scrollTop+=mark.getBoundingClientRect().top-article.getBoundingClientRect().top-40;});}
function bookPage(page){$('source-dialog').dataset.page=page;$('show-quote').setAttribute('aria-pressed',String(page==='quote'));$('show-article').setAttribute('aria-pressed',String(page==='article'));if(page==='article')scrollArticle();cue('page');}
$('show-quote').addEventListener('click',()=>bookPage('quote'));$('show-article').addEventListener('click',()=>bookPage('article'));
function fillArticle(article,citation){
  $('article-title').textContent=article.article;$('book-article').replaceChildren();
  const escaped=citation.quote.trim().split(/\s+/).map(word=>word.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('\\s+');
  const match=escaped?new RegExp(escaped,'u').exec(article.text):null;
  const sameSource=article.article===citation.article
    &&article.pdf_page===citation.pdf_page
    &&article.source_url===citation.source_url
    &&JSON.stringify(article.heading_path||[])===JSON.stringify(citation.heading_path||[]);
  if(!match||!sameSource){
    $('book-article').textContent='Le texte intégral disponible ne correspond pas au passage cité. Consultez le passage et sa source publiée.';
    $('article-status').textContent='Versions des sources non concordantes. Le passage cité reste consultable.';
    return;
  }
  const mark=document.createElement('mark');mark.textContent=match[0];
  $('book-article').append(document.createTextNode(article.text.slice(0,match.index)),mark,document.createTextNode(article.text.slice(match.index+match[0].length)));
  scrollArticle();
  const edition=(article.source_edition||'').match(/\b(?:19|20)\d{2}\b/)?.[0]||'non précisée';
  $('article-status').textContent=`Corpus ${edition} · page PDF ${article.pdf_page}`;$('article-status').title=article.source_edition||'';
}
async function openSource(index){
  const c=citations[index];if(!c)return;sourceIndex=index;const request=++sourceRequest;activeShelf=section(c);
  $('book-title').textContent=c.article;$('book-quote').textContent=c.quote;$('book-claim').textContent=c.text;
  $('book-page').textContent=`Page PDF ${c.pdf_page} · passage ${index+1}`;$('book-section').textContent=(c.heading_path||[]).join(' / ');
  $('book-number').textContent=`${index+1} / ${citations.length}`;$('previous-book').disabled=index===0;$('next-book').disabled=index===citations.length-1;
  try{const url=new URL(c.source_url,location.href);$('publisher').hidden=!['http:','https:'].includes(url.protocol);if(!$('publisher').hidden)$('publisher').href=url.href;}catch{$('publisher').hidden=true;}
  $('book-article').textContent='';$('article-title').textContent='Le texte intégral';$('article-status').textContent='Ouverture de l’article…';
  if(!$('source-dialog').open){bookPage('quote');$('source-dialog').showModal();}else cue('page');draw();
  try{
    if(!articleCache.has(c.record_id))articleCache.set(c.record_id,fetch(`/articles/${encodeURIComponent(c.record_id)}`).then(async response=>{if(!response.ok)throw new Error('Article unavailable');const article=await response.json();if(article.record_id!==c.record_id||typeof article.text!=='string')throw new Error('Invalid article');return article;}).catch(error=>{articleCache.delete(c.record_id);throw error;}));
    const article=await articleCache.get(c.record_id);
    if(request===sourceRequest&&$('source-dialog').open)fillArticle(article,c);
  }catch{if(request===sourceRequest){$('article-status').textContent='Texte intégral indisponible. Le passage cité reste consultable.';}}
}
$('close-book').addEventListener('click',()=>$('source-dialog').close());
$('source-dialog').addEventListener('close',()=>{sourceRequest++;cue('page');});
$('source-dialog').addEventListener('click',event=>{if(event.target===$('source-dialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
$('previous-book').addEventListener('click',()=>openSource(sourceIndex-1));$('next-book').addEventListener('click',()=>openSource(sourceIndex+1));
$('open-book').addEventListener('click',()=>openSource(0));$('new-question').addEventListener('click',newQuestion);
canvas.addEventListener('click',event=>{
  if(busy)return;const r=canvas.getBoundingClientRect(),x=((event.clientX-r.left)*canvas.width/r.width-view.x)/view.scale,y=((event.clientY-r.top)*canvas.height/r.height-view.y)/view.scale;
  if(x>=298&&x<=330&&y>=318&&y<=354){toggleSound();return;}
  const books=sourceBooks();
  for(let i=Math.min(delivered,books.length)-1;i>=0;i--){const {x:bx,y:by}=bookPosition(i);if(x>=bx-9&&x<=bx+9&&y>=by-12&&y<=by+11){openSource(books[i].index);return;}}
  if(x>=293&&x<=478&&y>=319&&y<=450)newQuestion();
});
function showAnswer(data){
  citations=data.citations;outcome=data.abstain?(data.reason==='clarification'?'clarification':data.reason==='invalid_output'?'invalid':'missing'):'answer';$('answer').replaceChildren();
  $('reply-speaker').textContent=outcome==='clarification'?'Une précision ?':outcome==='invalid'?'Réponse non validée':outcome==='missing'?'Archives insuffisantes':'Le bibliothécaire';
  progress='result';speech=outcome==='clarification'?'Pouvez-vous préciser ?':outcome==='invalid'?'La réponse ne passe pas le contrôle.':outcome==='missing'?'Les passages ne suffisent pas.':'Voici les passages cités.';
  for(const part of data.answer_fr.split(/(\[\d+\])/g)){
    const n=/^\[(\d+)\]$/.exec(part);
    if(n&&citations[Number(n[1])-1]){const button=document.createElement('button');button.className='reference';button.type='button';button.textContent=part;button.setAttribute('aria-label',`Ouvrir la source ${n[1]}`);button.addEventListener('click',()=>openSource(Number(n[1])-1));$('answer').append(button);}
    else $('answer').append(document.createTextNode(part));
  }
  $('answer').scrollTop=0;$('open-book').hidden=!citations.length;show('result');collect(citations);$('result').focus({preventScroll:true});cue('book');
}
function showProgress(event){
  const messages={rewrite:'Je précise votre recherche…',retrieval:'Je cherche les passages utiles…',evidence:'Voici les pistes retrouvées…',generation:'Je prépare une réponse à partir des textes…',validation:'Je contrôle la réponse et ses références…'};
  if(!messages[event.type])return;progress=event.type;speech=messages[progress];
  if(progress==='rewrite'){actor.path=[];actor.walking=false;actor.pose='reading';}
  if(progress==='retrieval')search();
  if(progress==='evidence'){
    candidates=[...new Map(event.passages.map(p=>[p.record_id,p])).values()];evidenceAt=performance.now();selectedShelves=[...new Set(candidates.map(section))];activeShelf=null;
    speech=event.passages.length?`${event.passages.length} passages repérés dans les archives.`:'Aucun passage suffisant trouvé.';
  }
  if(progress==='generation')route([...aisle(),[190,236],[190,339],research.stop]);
  if(progress==='validation'&&!actor.path.length)actor.pose='reading';
  $('loading-message').textContent=speech;$('scene-caption').textContent=speech;draw();
}
async function readProgress(response,request){
  if(!response.body||!response.headers.get('content-type')?.includes('application/x-ndjson'))throw new Error('Le flux de réponse est indisponible. Réessayez.');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',complete=false;
  try{
    while(true){
      const {value,done}=await reader.read();if(request!==requestId)return null;
      buffer+=decoder.decode(value,{stream:!done});const lines=buffer.split('\n');buffer=done?'':lines.pop();
      for(const line of lines){
        if(!line.trim())continue;let event;
        try{event=JSON.parse(line);}catch{throw new Error('La progression reçue est illisible. Réessayez.');}
        if(event.type==='error')throw new Error(typeof event.detail==='string'?event.detail:'Le service est interrompu. Réessayez.');
        if(event.type==='result'){complete=true;return event.answer;}
        showProgress(event);
      }
      if(done)throw new Error('La réponse a été interrompue. Réessayez.');
    }
  }finally{if(!complete)await reader.cancel().catch(()=>{});reader.releaseLock();}
}
$('form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;const question=$('question').value.trim();if(!question){$('question').focus();return;}
  const request=++requestId;controller=new AbortController();
  busy=true;outcome='search';citations=[];candidates=[];selectedShelves=[];activeShelf=null;delivered=0;progress='waiting';speech='Je transmets votre question…';actor.path=[];actor.walking=false;actor.carry=false;actor.lift=0;actor.pose='idle';$('submit').disabled=true;$('question').readOnly=true;$('loading-message').textContent=speech;show('loading');$('question').blur();
  try{
    const response=await fetch('/ask/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,history}),signal:controller.signal});
    if(request!==requestId)return;
    if(!response.ok){const error=await response.json().catch(()=>null);throw new Error(typeof error?.detail==='string'?error.detail:response.status===401?'Accès réservé. Actualisez la page pour vous connecter.':'La question ne peut pas être traitée. Réessayez.');}
    const data=await readProgress(response,request);if(request!==requestId)return;
    if(!data||typeof data.answer_fr!=='string'||typeof data.abstain!=='boolean'||!Array.isArray(data.citations))throw new Error('Le service a renvoyé une réponse illisible. Réessayez.');
    busy=false;showAnswer(data);
    history=[...history,{role:'user',content:question},{role:'assistant',content:data.answer_fr.slice(0,1000)}].slice(-4);
    while(history.reduce((n,turn)=>n+turn.content.length,0)>6000)history.splice(0,2);
  }catch(error){
    if(request!==requestId)return;
    busy=false;outcome='error';progress='error';speech='Le service est interrompu.';show('form');$('status').hidden=false;$('status').textContent=error instanceof TypeError?'Le service est inaccessible. Réessayez.':error.message;$('scene-caption').textContent='Le service est interrompu. Vous pouvez réessayer.';actor.carry=false;goHome();$('question').focus({preventScroll:true});
  }finally{if(request===requestId){busy=false;controller=null;$('submit').disabled=false;$('question').readOnly=false;draw();}}
});
$('question').addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();if(!busy)$('form').requestSubmit();}});
