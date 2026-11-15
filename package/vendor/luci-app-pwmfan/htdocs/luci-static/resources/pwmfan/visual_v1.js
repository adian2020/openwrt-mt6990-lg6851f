'use strict';
'require baseclass';
'require rpc';

// A shared, read-only visual: all changes to the hardware stay in the existing control page.
const read = rpc.declare({object:'luci.pwmfan',method:'get_status',nobatch:true,expect:{'':{}}});
const periods = [1.8, 1.35, .8];
const labels = ['安静', '标准模式', '强风'];
const css = `
@property --lgfan-hue{syntax:'<number>';inherits:true;initial-value:185}
@property --lgfan-shift{syntax:'<number>';inherits:true;initial-value:0}
@property --lgfan-warp{syntax:'<angle>';inherits:true;initial-value:0deg}
.lgfan{--lgfan-play:paused;--lgfan-base:var(--surface,var(--background,#fff));position:relative;width:100%;aspect-ratio:1;background:transparent!important;isolation:isolate;contain:layout style}
.lgfan-rim{position:absolute;inset:7%;border-radius:50%;animation:lgfan-chameleon 5.6s linear infinite;animation-play-state:var(--lgfan-play);background:transparent;filter:drop-shadow(0 0 2px hsl(var(--lgfan-hue) 90% 65% / .45)) drop-shadow(0 0 5px hsl(calc(var(--lgfan-hue) + 160) 90% 60% / .20))}
.lgfan-rim:before{content:'';position:absolute;inset:0;border-radius:50%;background:conic-gradient(from -90deg,hsl(var(--lgfan-hue) 88% 63%) 0deg,hsl(calc(var(--lgfan-hue) + 70 + var(--lgfan-shift)) 88% 62%) calc(80deg + var(--lgfan-warp)),hsl(calc(var(--lgfan-hue) + 158 - var(--lgfan-shift)) 88% 61%) calc(174deg - var(--lgfan-warp)),hsl(calc(var(--lgfan-hue) + 263 + var(--lgfan-shift)) 88% 62%) calc(268deg + var(--lgfan-warp)),hsl(var(--lgfan-hue) 88% 63%) 360deg);-webkit-mask:radial-gradient(farthest-side,transparent 94%,#000 95%);mask:radial-gradient(farthest-side,transparent 94%,#000 95%)}
.lgfan-rotor{position:absolute;inset:13%;animation:lgfan-spin 1.8s linear infinite;animation-play-state:var(--lgfan-play);will-change:transform}
.lgfan-blade{position:absolute;inset:0;transform:rotate(var(--lgfan-angle))}
.lgfan-blade:before,.lgfan-blade:after{content:'';position:absolute;left:45%;top:3%;width:34%;height:45%;border-radius:22% 65% 40% 9%;clip-path:polygon(0 100%,0 20%,50% 0,100% 22%,68% 70%,17% 100%)}
.lgfan-blade:before{background:repeating-linear-gradient(128deg,#d4f3ff1c 0 1px,transparent 1px 4px),linear-gradient(145deg,#17283b 0%,#7ca2b7 18%,#2b435e 33%,#101c30 70%,#4c708b 100%)}
.lgfan-blade:after{background:linear-gradient(127deg,transparent 0 22%,#b8fff7 22% 24%,#17cfda 24% 29%,transparent 29% 57%,#b374ff 57% 60%,#f2aaff 60% 61%,transparent 61%);filter:drop-shadow(0 0 1px #3de4f6)}
.lgfan-hub{position:absolute;inset:38%;border-radius:50%;background:radial-gradient(circle at 32% 22%,#93b2c8,#344c67 37%,#102136 72%);box-shadow:inset 0 0 0 1px #b4dfff70,0 0 0 1px #12283db3,0 2px 5px #0003}
.lgfan-hub:before{content:'';position:absolute;inset:18%;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);background:conic-gradient(from 30deg,#86fff1,#15a9cf,#9c76ff,#ed9aff,#86fff1)}
.lgfan-hub:after{content:'';position:absolute;inset:25%;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);background:linear-gradient(125deg,#182b43 0 34%,#81fff1 34% 41%,#102339 41% 57%,#bb8fff 57% 64%,#182b43 64%)}
.lgfan[data-level='0'],.lgfan[data-level='1'],.lgfan[data-level='2']{--lgfan-play:running}
.lgfan[data-level='unknown'] .lgfan-rim{opacity:.3}
.lgfan-hidden .lgfan-rotor,.lgfan-hidden .lgfan-rim{animation-play-state:paused!important}
@keyframes lgfan-spin{to{transform:rotate(360deg)}}
@keyframes lgfan-chameleon{0%{--lgfan-hue:185;--lgfan-shift:0;--lgfan-warp:0deg}25%{--lgfan-hue:275;--lgfan-shift:30;--lgfan-warp:16deg}50%{--lgfan-hue:365;--lgfan-shift:0;--lgfan-warp:0deg}75%{--lgfan-hue:455;--lgfan-shift:-30;--lgfan-warp:-16deg}100%{--lgfan-hue:545;--lgfan-shift:0;--lgfan-warp:0deg}}
@media(prefers-reduced-motion:reduce){.lgfan-rotor,.lgfan-rim{animation:none!important}}
`;

function describe(data) {
 const values={};
 String(data?.controller||'').split('\n').forEach(line=>{const n=line.indexOf('=');if(n>0)values[line.slice(0,n)]=line.slice(n+1);});
 let level=null,manual=null;
 const pwm=Number(values[values.active]??data?.pwm);
 if(values.fan_type==='3wire'&&values.status!=='register-failsafe'){
  level=({low:0,medium:1,high:2})[String(values.speed_point||'').replace('-10khz','')]??null;
  if(/^manual-/.test(values.status||''))manual=[115,180,220][level]??null;
 }else if(values.status==='manual'){
  const index=[115,180,220].indexOf(pwm);level=index<0?null:index;if(level!=null)manual=pwm;
 }else if(values.status==='automatic'&&Number.isFinite(pwm)&&pwm>0){
  level=values.direction==='inverse'?(pwm>=170?0:pwm>100?1:2):(pwm<=125?0:pwm<=200?1:2);
 }
 const stopped=!!data?.stalled||values.status==='stalled'||(data?.tach_available&&data.rpm===0);
 if(!data?.available||stopped)level=null;
 return {level,manual,stopped,name:!data?.available?'未获取':stopped?'已停止':level==null?'检测中':labels[level]};
}

function inject() {
 if(document.getElementById('lgfan-visual-style'))return;
 const style=document.createElement('style');style.id='lgfan-visual-style';style.textContent=css;document.head.append(style);
 const visibility=()=>document.documentElement.classList.toggle('lgfan-hidden',document.hidden);
 document.addEventListener('visibilitychange',visibility);visibility();
}

function create() {
 inject();
 const blades=Array.from({length:9},(_,i)=>E('span',{'class':'lgfan-blade',style:'--lgfan-angle:'+(i*40)+'deg'}));
 return E('div',{'class':'lgfan','data-level':'unknown',role:'img','aria-label':'风扇状态：未获取'},[
  E('div',{'class':'lgfan-rim'}),E('div',{'class':'lgfan-rotor'},blades),E('div',{'class':'lgfan-hub'})
 ]);
}

function update(node,data) {
 const state=describe(data);
 if(!node)return state;
 node.dataset.level=state.level??'unknown';
 node.dataset.period=state.level==null?'':String(periods[state.level]);
 node.setAttribute('aria-label','风扇状态：'+state.name);
 // Playback-rate changes preserve phase; changing CSS durations would jump the rotor.
 const apply=()=>{
  if(!node.isConnected)return;
  const level=Number(node.dataset.level),period=periods[level];
  if(!period)return;
  const animation=node.querySelector('.lgfan-rotor').getAnimations()[0];
  if(animation&&animation.playbackRate!==1.8/period){
   if(animation.updatePlaybackRate)animation.updatePlaybackRate(1.8/period);
   else animation.playbackRate=1.8/period;
  }
 };
 apply();requestAnimationFrame(apply);
 return state;
}

return baseclass.extend({read,create,update,describe,periods});
