'use strict';
'require view';
'require poll';
'require ui';
'require modem5g.cpe_v1 as C';

function graph(values){
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 240 64');svg.setAttribute('class','cpe-chart');
 const line=document.createElementNS(svg.namespaceURI,'polyline'),top=Math.max(1,...values);
 line.setAttribute('points',values.map((v,i)=>`${i*240/Math.max(1,values.length-1)},${62-v*60/top}`).join(' '));svg.append(line);return svg;
}
const address=rows=>(rows||[]).map(row=>`${row.address}/${row.mask}`).join(' · ');
const bandwidth=(row,dir)=>row[dir+'_bandwidth_mhz'] == null ? (row[dir+'_bandwidth_code'] == null ? '未获取' : '编码 '+row[dir+'_bandwidth_code']) : C.value(row[dir+'_bandwidth_mhz'],' MHz');
const rateCacheKey='lg6851f-dashboard-rates-v1';
function validSample(sample){return !!sample?.device&&!!sample?.boot_id&&['at','rx','tx'].every(key=>Number.isFinite(sample[key])&&sample[key]>=0);}
function readRateCache(){try{return JSON.parse(sessionStorage.getItem(rateCacheKey));}catch(error){return null;}}
function recentRate(cache,current){
 return validSample(current)&&validSample(cache?.sample)&&cache.sample.boot_id===current.boot_id&&cache.sample.device===current.device&&
  current.at>=cache.sample.at&&current.at-cache.sample.at<=10&&current.rx>=cache.sample.rx&&current.tx>=cache.sample.tx&&
  ['rx','tx'].every(key=>Number.isFinite(cache.rate?.[key])&&cache.rate[key]>=0)?cache.rate:null;
}
function saveRateCache(sample,rate){try{sessionStorage.setItem(rateCacheKey,JSON.stringify({sample,rate}));}catch(error){}}
return view.extend({
 async load(){
  const [data,first]=await Promise.all([C.dashboard(),C.rates().catch(()=>null)]),cached=readRateCache(),rate=recentRate(cached,first);
  if(rate)return {data,current:first,rate,cpu:null,cached:true};
  if(validSample(first)){
   await new Promise(resolve=>setTimeout(resolve,250));
   const current=await C.rates().catch(()=>null),measured=validSample(current)?C.delta(first,current):null;
   return {data,current,rate:measured,cpu:C.cpu(first.cpu,current?.cpu),cached:false};
  }
  return {data,current:first,rate:null,cpu:null,cached:false};
 },
 render({data,current,rate,cpu,cached}){
  this.previous=current;this.history={rx:[],tx:[]};this.busy=false;this.readingRadio=false;
  this.body=E('div');this.rates=E('div',{'class':'cpe-grid'});
  const root=E('div',{'class':'cpe'},[C.style(),E('div',{'class':'cpe-header'},[E('h2',{},'状态看板'),E('button',{'class':'btn',click:()=>this.refresh()},'刷新状态')]),this.rates,this.body]);
  this.paint(data);
  this.paintRates(current,rate,cpu,cached);
  poll.add(()=>this.refresh(),10);poll.add(()=>this.sample(),2);return root;
 },
 async refresh(){if(this.busy)return;this.busy=true;try{this.paint(await C.dashboard());}finally{this.busy=false;}},
 async readRadioDetails(){
  if(this.readingRadio)return;
  this.readingRadio=true;this.paint(this.data);
  const previousTimeout=L.env.rpctimeout;
  try{
   L.env.rpctimeout=60;
   const result=await C.getRadioDetails();
   if(result?.code)throw Error(result.error||result.output||'高级参数读取失败');
  }catch(error){ui.addNotification(null,E('p',{},error.message||String(error)),'error');}
  finally{L.env.rpctimeout=previousTimeout;this.readingRadio=false;await this.refresh();}
 },
 async sample(){
  if(this.sampling)return;this.sampling=true;
  try{
   const current=await C.rates(),delta=validSample(this.previous)&&validSample(current)?C.delta(this.previous,current):null,cpu=C.cpu(this.previous?.cpu,current?.cpu);
   const cached=delta?null:recentRate(readRateCache(),current);
   this.paintRates(current,delta||cached,cpu,!delta&&!!cached);this.previous=current;
  }finally{this.sampling=false;}
 },
 paintRates(current,rate,cpu,cached){
   if(!rate)this.history={rx:[],tx:[]};
   if(rate&&!cached)saveRateCache(current,rate);
   const cards=['rx','tx'].map((key,index)=>{
    if(rate){this.history[key].push(rate[key]);if(this.history[key].length>40)this.history[key].shift();}
    return C.card(index?'上传速率':'下载速率',E('div',{},[C.metric(cached?'最近一次速率':'实时速率',rate?C.bytes(rate[key])+'/s':'未获取'),graph(this.history[key]),C.unavailable(cached?'显示最近一次有效速率，新数据将在下次刷新时更新':rate?'按蜂窝实际接口字节差与采样时间差计算':'尚未取得有效的蜂窝接口流量计数')]));
   });
   cards.push(C.card('CPU',C.metric('当前利用率',cpu==null?'等待采样':cpu.toFixed(1)+'%')));
   this.rates.replaceChildren(...cards);
 },
 paint(data){
  this.data=data;
  const m=data.modem||{},n=data.network||{},lan=data.lan||{};
  const radio=data.radio_details,details=radio?.parsed,carriers=details?.carriers||[];
  const cells = C.cellular.parseCells(data.cells?.serving);
  const serving = !data.cells?.stale && cells.find(row=>row.serving);
  const signal = serving || m;
  const header=C.card('当前连接',E('div',{'class':'cpe-hero'},[
   E('div',{},[E('strong',{},`${m.rat||'未获取'} · ${m.operator||'运营商未获取'}`),C.unavailable(`${n.up?'数据接口在线':'数据接口未连接'} · ${n.l3_device||'接口未获取'} · ${data.cached_modem_stale?'蜂窝缓存未就绪或已过期':'蜂窝缓存 '+data.cache_age+' 秒前更新'}`)]),
   E('div',{},[E('strong',{},C.value(signal.rsrp,' dBm')),C.unavailable(`RSRQ ${C.value(signal.rsrq,' dB')} · SINR ${C.value(signal.sinr,' dB')}${serving?' · 小区采样 '+data.cells.age+' 秒前':''}`)])]));
  if(data.initializing)header.append(C.unavailable('后台正在采集状态，页面会自动更新。'));
  else if(data.collector_stale)header.append(C.unavailable('后台采集暂未更新，当前显示缓存数据。'));
  const memory=data.memory||{},storage=data.storage||{};
  const devices=C.card('系统与设备',E('div',{},[E('div',{'class':'cpe-grid'},[
   C.metric('内存使用率',memory.percent==null?'未获取':memory.percent.toFixed(1)+'%'),C.metric('内存已用 / 总量',C.bytes(memory.used)+' / '+C.bytes(memory.total)),
   C.metric('可写存储使用率',C.value(storage.percent,'%')),C.metric('设备运行时间',C.elapsed(data.uptime))]),
   C.rows([['设备型号',data.model],['CPU频率',data.frequencies?.length?data.frequencies.map(p=>`${p.policy}: ${C.value(p.current_mhz)} / ${C.value(p.maximum_mhz)} MHz`).join(' · '):'当前内核未提供 cpufreq 数值'],['系统版本',data.release],['固件源码',data.firmware_id],['LAN 地址',address(lan['ipv4-address'])],['Linux 连接跟踪',C.value(data.conntrack?.count)+' / '+C.value(data.conntrack?.maximum)]]) ]));
  const network=C.card('链路与流量',C.rows([
   ['APN',data.apn?.apn],['IPv4',address(n['ipv4-address'])],['全球 IPv6',data.ipv6_global?.join(' · ')||'未取得全球 IPv6 地址'],['DNS',(n['dns-server']||[]).join(' · ')],['连接时长',C.elapsed(n.uptime)],['PLMN',m.plmn],['SIM 状态',m.sim],['注册状态',m.registered?'已注册':'未确认注册'],['当前 SA / NSA',!radio?.stale?details?.sa_nsa:null],['QCI','未获取'],['PPE0 / PPE1','未获取']
  ]));
  const radioCard=C.card('载波与网络参数',E('div',{},[
   E('button',{'class':'btn',disabled:this.readingRadio,click:()=>this.readRadioDetails()},this.readingRadio?'读取中…':'读取高级参数'),
   C.unavailable(radio?`采样于 ${radio.age} 秒前${radio.stale?'（已过期，点击重新读取）':''}；本次报告 ${carriers.length} 条载波记录。`:'尚无采样，点击读取带宽、载波、MCS 和 AMBR。'),
   C.table(['载波 / 频段','PCI / ARFCN','带宽 下 / 上','MCS 下 / 上','CQI'],carriers.map(row=>[
    `${row.type} / ${row.rat==='nr'?'n':'B'}${row.band}`,`${row.pci} / ${row.arfcn}`,
    bandwidth(row,'dl')+' / '+bandwidth(row,'ul'),C.value(row.dl_mcs)+' / '+C.value(row.ul_mcs),row.cqi
   ])),
   C.rows([
    ['网络 AMBR 下 / 上',C.mbps(details?.ambr?.network?.dl?.bps)+' / '+C.mbps(details?.ambr?.network?.ul?.bps)],
    ['IMS AMBR 下 / 上',C.mbps(details?.ambr?.ims?.dl?.bps)+' / '+C.mbps(details?.ambr?.ims?.ul?.bps)],
    ['EN-DC 可用 / DCNR 限制标志',C.value(details?.endc?.available)+' / '+C.value(details?.endc?.restricted)],
    ['厂商数据注册制式',details?.data_registration?.ok?details.data_registration.radio_tech:null]
   ]),
   C.unavailable('AMBR 是网络返回的速率参数，不是实测下载/上传速度；EN-DC 标志是状态，不是开启开关。'),
   E('details',{},[E('summary',{},'载波原始编码'),C.table(['载波','调制 下 / 上','MIMO 下 / 上','BWP 带宽编码 下 / 上'],carriers.map(row=>[
    row.type,C.value(row.dl_modulation_code)+' / '+C.value(row.ul_modulation_code),C.value(row.dl_mimo_code)+' / '+C.value(row.ul_mimo_code),C.value(row.dl_bwp_bandwidth_code)+' / '+C.value(row.ul_bwp_bandwidth_code)
   ])),C.unavailable('这些编码尚未确认映射，暂不换算为调制名称、天线组合或 BWP MHz。')])
  ]));
  const temperature=C.card('温度传感器',C.table(['来源','传感器','温度'],(data.temperatures||[]).map(row=>[row.kind,row.name+(row.label?' / '+row.label:''),row.celsius.toFixed(1)+' °C'])));
  const wifi=C.card('无线网络',C.table(['接口 / SSID','信道','频率','功率','加密'],(data.wireless||[]).map(row=>[`${row.device} / ${row.ssid||'未获取'}`,row.channel,C.value(row.frequency,' MHz'),C.value(row.txpower,' dBm'),row.encryption])));
  const clients=C.card('无线客户端',C.table(['设备','MAC','信号','接收协商速率','发送协商速率'],(data.clients||[]).map(row=>[row.device,row.mac,C.value(row.signal,' dBm'),C.value(row.rx_kbit==null?null:row.rx_kbit/1000,' Mbit/s'),C.value(row.tx_kbit==null?null:row.tx_kbit/1000,' Mbit/s')])));
  const leases=C.card('DHCP 租约',C.table(['名称','地址','MAC'],(data.leases||[]).map(row=>[row.hostname,row.address,row.mac])));
  const cellCard = C.card('当前小区与邻区',E('div',{},[
   E('button',{'class':'btn',click:async ev=>{const button=ev.currentTarget;button.disabled=true;try{const result=await C.getCells();if(result?.initializing||result?.serving?.code)throw Error(result?.serving?.output||'小区读取尚未就绪');await this.refresh();}catch(error){ui.addNotification(null,E('p',{},error.message||String(error)),'error');}finally{button.disabled=false;}}},'刷新小区'),
   C.unavailable(data.cells ? `采样于 ${data.cells.age} 秒前${data.cells.stale ? '（已过期，点击刷新）' : ''}；频段为按频点计算的候选范围。` : '尚无小区采样，点击刷新读取。'),
   C.table(['类型','候选频段','PCI','ARFCN','RSRP','RSRQ','SINR'],cells.map(row=>[row.serving?'服务小区':'邻区',row.band,row.pci,row.arfcn,C.value(row.rsrp,' dBm'),C.value(row.rsrq,' dB'),C.value(row.sinr,' dB')]))
  ]));
  const masks=C.cellular.lockMasks(data.bands?.output);
  const bandCard=C.card('频段限制',C.rows([
   ['当前允许 LTE',masks.current?.lte.map(v=>'B'+v).join(' · ')],['当前允许 NR',masks.current?.nr.map(v=>'n'+v).join(' · ')],
   ['能力 / 采样',masks.supported?`LTE ${masks.supported.lte.length} 个 / NR ${masks.supported.nr.length} 个；${data.bands.age} 秒前${data.bands.stale?'（已过期）':''}`:'请在“蜂窝 → 网络锁定”读取频段']
  ]));
  const controls=C.card('快捷控制',E('div',{'class':'cpe-actions'},[
   E('button',{'class':'btn',click:()=>C.action('建立数据连接','将按已保存的 APN 建立连接。',C.connect,()=>this.refresh())},'连接数据'),
   E('button',{'class':'btn',click:()=>C.action('断开数据连接','蜂窝网络会中断。',C.disconnect,()=>this.refresh())},'断开数据'),
   E('button',{'class':'btn',click:()=>C.action('开启射频','将开启蜂窝射频，并按现有配置请求拨号。',()=>C.setRadio(true),()=>this.refresh())},'开启射频'),
   E('button',{'class':'btn',click:()=>C.action('关闭射频','蜂窝连接、短信等服务可能中断。',()=>C.setRadio(false),()=>this.refresh())},'关闭射频')
  ]));
  this.body.replaceChildren(header,network,radioCard,cellCard,bandCard,devices,temperature,wifi,clients,leases,controls,C.unavailable('温度按系统提供的传感器名称展示。无线客户端速率为协商速率，实际传输速度请查看上方流量曲线。'));
 },
 handleSaveApply:null,handleSave:null,handleReset:null
});
