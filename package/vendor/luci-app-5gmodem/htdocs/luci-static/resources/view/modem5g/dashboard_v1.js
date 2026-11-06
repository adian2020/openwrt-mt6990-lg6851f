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
return view.extend({
 load(){return C.dashboard();},
 render(data){
  this.previous=null;this.history={rx:[],tx:[]};this.busy=false;
  this.body=E('div');this.rates=E('div',{'class':'cpe-grid'});
  const root=E('div',{'class':'cpe'},[C.style(),E('div',{'class':'cpe-header'},[E('h2',{},'状态看板'),E('button',{'class':'btn',click:()=>this.refresh()},'刷新状态')]),this.rates,this.body]);
  this.paint(data);
  poll.add(()=>this.refresh(),10);poll.add(()=>this.sample(),2);this.sample();return root;
 },
 async refresh(){if(this.busy)return;this.busy=true;try{this.paint(await C.dashboard());}finally{this.busy=false;}},
 async sample(){
  if(this.sampling)return;this.sampling=true;
  try{
   const current=await C.rates(),delta=C.delta(this.previous,current),cpu=C.cpu(this.previous?.cpu,current?.cpu);
   if(!delta)this.history={rx:[],tx:[]};
   const cards=['rx','tx'].map((key,index)=>{
    if(delta){this.history[key].push(delta[key]);if(this.history[key].length>40)this.history[key].shift();}
    return C.card(index?'上传速率':'下载速率',E('div',{},[C.metric(delta?'实时速率':'等待第二次采样',delta?C.bytes(delta[key])+'/s':'未获取'),graph(this.history[key]),C.unavailable('按蜂窝实际接口字节差与采样时间差计算')]));
   });
   cards.push(C.card('CPU',C.metric('当前利用率',cpu==null?'等待采样':cpu.toFixed(1)+'%')));
   this.rates.replaceChildren(...cards);this.previous=current;
  }finally{this.sampling=false;}
 },
 paint(data){
  const m=data.modem||{},n=data.network||{},lan=data.lan||{};
  const cells = C.cellular.parseCells(data.cells?.serving);
  const serving = !data.cells?.stale && cells.find(row=>row.serving);
  const signal = serving || m;
  const header=C.card('当前连接',E('div',{'class':'cpe-hero'},[
   E('div',{},[E('strong',{},`${m.rat||'未获取'} · ${m.operator||'运营商未获取'}`),C.unavailable(`${n.up?'数据接口在线':'数据接口未连接'} · ${n.l3_device||'接口未获取'} · ${data.cached_modem_stale?'蜂窝缓存未就绪或已过期':'蜂窝缓存 '+data.cache_age+' 秒前更新'}`)]),
   E('div',{},[E('strong',{},C.value(signal.rsrp,' dBm')),C.unavailable(`RSRQ ${C.value(signal.rsrq,' dB')} · SINR ${C.value(signal.sinr,' dB')}${serving?' · 小区采样 '+data.cells.age+' 秒前':''}`)])]));
  const memory=data.memory||{},storage=data.storage||{};
  const devices=C.card('系统与设备',E('div',{},[E('div',{'class':'cpe-grid'},[
   C.metric('内存使用率',memory.percent==null?'未获取':memory.percent.toFixed(1)+'%'),C.metric('内存已用 / 总量',C.bytes(memory.used)+' / '+C.bytes(memory.total)),
   C.metric('可写存储使用率',C.value(storage.percent,'%')),C.metric('设备运行时间',C.elapsed(data.uptime))]),
   C.rows([['设备型号',data.model],['CPU频率',data.frequencies?.length?data.frequencies.map(p=>`${p.policy}: ${C.value(p.current_mhz)} / ${C.value(p.maximum_mhz)} MHz`).join(' · '):'当前内核未提供 cpufreq 数值'],['系统版本',data.release],['固件源码',data.firmware_id],['LAN 地址',address(lan['ipv4-address'])],['Linux 连接跟踪',C.value(data.conntrack?.count)+' / '+C.value(data.conntrack?.maximum)]]) ]));
  const network=C.card('链路与流量',C.rows([
   ['APN',data.apn?.apn],['IPv4',address(n['ipv4-address'])],['全球 IPv6',data.ipv6_global?.join(' · ')||'未取得全球 IPv6 地址'],['DNS',(n['dns-server']||[]).join(' · ')],['连接时长',C.elapsed(n.uptime)],['PLMN',m.plmn],['SIM 状态',m.sim],['注册状态',m.registered?'已注册':'未确认注册'],['当前 SA / NSA','未获取'],['CA / MCS / AMBR / QCI','未获取'],['PPE0 / PPE1','未获取']
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
  this.body.replaceChildren(header,network,cellCard,bandCard,devices,temperature,wifi,clients,leases,controls,C.unavailable('温度按系统提供的传感器名称展示。无线客户端速率为协商速率，实际传输速度请查看上方流量曲线。'));
 },
 handleSaveApply:null,handleSave:null,handleReset:null
});
