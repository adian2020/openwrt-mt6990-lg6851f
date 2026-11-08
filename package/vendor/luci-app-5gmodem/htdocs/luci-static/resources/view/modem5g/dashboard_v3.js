'use strict';
'require view';
'require poll';
'require rpc';
'require ui';
'require modem5g.cpe_v2 as C';
'require modem5g.mu_v1 as M';
// 布局取自 MU300（MIT），数据与控制只接 MT6990 既有接口。
const rateCacheKey='lg6851f-dashboard-rates-v1';
function validSample(sample){return !!sample?.device&&!!sample?.boot_id&&['at','rx','tx'].every(key=>Number.isFinite(sample[key])&&sample[key]>=0);}
function readRateCache(){try{return JSON.parse(sessionStorage.getItem(rateCacheKey));}catch(error){return null;}}
function recentRate(cache,current){
 return validSample(current)&&validSample(cache?.sample)&&cache.sample.boot_id===current.boot_id&&cache.sample.device===current.device&&
  current.at>=cache.sample.at&&current.at-cache.sample.at<=10&&current.rx>=cache.sample.rx&&current.tx>=cache.sample.tx&&
  ['rx','tx'].every(key=>Number.isFinite(cache.rate?.[key])&&cache.rate[key]>=0)?cache.rate:null;
}
function saveRateCache(sample,rate,cpu){try{sessionStorage.setItem(rateCacheKey,JSON.stringify({sample,rate,cpu}));}catch(error){}}

const address=rows=>(rows||[]).map(r=>r.address+'/'+r.mask).join(' · ');
const text=v=>v==null||v===''?'未获取':String(v);
const radioRead=rpc.declare({object:'luci.modem5g',method:'request_radio_details',nobatch:true,expect:{'':{}}});
const action=rpc.declare({object:'luci.modem5g',method:'dashboard_action',params:['operation'],nobatch:true,expect:{'':{}}});
return view.extend({
 async load(){
  const [data,first]=await Promise.all([C.dashboard(),C.rates().catch(()=>null)]),cached=readRateCache(),rate=recentRate(cached,first);
  if(rate)return {data,current:first,rate,cpu:C.cpu(cached.sample.cpu,first.cpu)??cached.cpu??null,cached:true};
  if(validSample(first)){
   await new Promise(resolve=>setTimeout(resolve,250));
   const current=await C.rates().catch(()=>null),measured=validSample(current)?C.delta(first,current):null;
   return {data,current,rate:measured,cpu:C.cpu(first.cpu,current?.cpu),cached:false};
  }
  return {data,current:first,rate:null,cpu:null,cached:false};
 },

 render({data,current,rate,cpu,cached}){
  M.injectCss();this.root=document.createElement('div');this.root.className='mud';
  this.root.innerHTML=`
<div class="mud-card mud-hero">
  <div class="mud-hero-l">
    <div class="mud-hero-meta" style="font-size:.78rem;color:var(--text-muted,var(--text-light,#777))">
      <span class="mud-dot" id="mud-dot"></span><b id="mud-host" style="color:var(--text,#222)">--</b>
      <span id="mud-uptime"></span></div>
    <div class="mud-rat" id="mud-rat">--<span class="mud-bars" id="mud-bars"><i style="height:25%"></i><i style="height:45%"></i><i style="height:65%"></i><i style="height:85%"></i><i style="height:100%"></i></span></div>
    <div class="mud-op" id="mud-op">--</div>
    <div class="mud-cellline" id="mud-cellline"></div>
  </div>
  <div class="mud-hero-r">
    <div class="mud-rsrp" id="mud-rsrp">--</div>
    <div class="mud-chips" id="mud-metric-chips"></div>
  </div>
</div>

<div class="mud-card mud-body">

<div class="mud-sec">
  <h3>链路与流量</h3>
  <div class="mud-charts">
    <div class="mud-chart" style="color:var(--brand,var(--primary,#2f7bf6))">
      <div class="t"><b id="mud-dl">--</b><span>下行速率</span></div>
      <div class="c" id="mud-spark-dl"></div>
    </div>
    <div class="mud-chart" style="color:var(--success,#2FBF71)">
      <div class="t"><b id="mud-ul">--</b><span>上行速率</span></div>
      <div class="c" id="mud-spark-ul"></div>
    </div>
  </div>
  <div class="mud-kpis">
    <div class="mud-kpi"><b id="mud-rx">--</b><span>累计接收</span></div>
    <div class="mud-kpi"><b id="mud-tx">--</b><span>累计发送</span></div>
    <div class="mud-kpi"><b id="mud-tr-day">--</b><span>今日流量</span></div>
    <div class="mud-kpi"><b id="mud-tr-month">--</b><span>当月流量</span></div>
    <div class="mud-kpi"><b id="mud-tr-left">--</b><span>套餐剩余</span></div>
  </div>
  <p class="mud-note" id="mud-traffic-warning"></p>
  <div class="mud-cols">
    <div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">IPv4 / IPv6</span><span class="mud-v" id="mud-ip">--</span></div>
        <div class="mud-r"><span class="mud-k">APN</span><span class="mud-v" id="mud-apn">--</span></div>
        <div class="mud-r"><span class="mud-k">数据漫游</span><span class="mud-v" id="mud-roaming">--</span></div>
        <div class="mud-r"><span class="mud-k">会话时长</span><span class="mud-v" id="mud-sess">--</span></div>
        <div class="mud-r"><span class="mud-k">注册状态</span><span class="mud-v" id="mud-reg">--</span></div>
        <div class="mud-r"><span class="mud-k">DNS</span><span class="mud-v" id="mud-dns">--</span></div>
      </div>
    </div>
    <div>
      <div class="mud-rows" id="mud-lteanchor"></div>
      <div class="mud-rows" id="mud-radio-metrics">
        <div class="mud-r"><span class="mud-k">调制方式 下/上</span><span class="mud-v">-- / --</span></div>
        <div class="mud-r"><span class="mud-k">载波聚合</span><span class="mud-v">-- / --</span></div>
        <div class="mud-r"><span class="mud-k">BLER 下/上</span><span class="mud-v">-- / --</span></div>
      </div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">频宽</span><span class="mud-v" id="mud-bw">--</span></div>
        <div class="mud-r"><span class="mud-k">QCI</span><span class="mud-v" id="mud-qci">--</span></div>
        <div class="mud-r"><span class="mud-k">AMBR 下/上</span><span class="mud-v" id="mud-ambr">--</span></div>
      </div>
    </div>
  </div>
</div>


<div class="mud-sec">
  <h3>无线 · 局域网 · 设备 · SIM</h3>
  <div class="mud-temp" id="mud-temps"></div>
  <div class="mud-kpis" style="margin-top:8px">
    <div class="mud-kpi"><b id="mud-cpu">--</b><span>CPU 占用</span><div class="mud-meter"><i id="mud-cpu-bar" style="background:var(--brand,var(--primary,#3b82f6))"></i></div></div>
    <div class="mud-kpi"><b id="mud-ram">--</b><span>内存 · <span class="mud-sub" id="mud-ram-sub">--</span></span><div class="mud-meter"><i id="mud-ram-bar" style="background:var(--info,#0ea5e9)"></i></div></div>
    <div class="mud-kpi"><b id="mud-disk">--</b><span>存储</span><div class="mud-meter"><i id="mud-disk-bar" style="background:var(--warning,#f59e0b)"></i></div></div>
  </div>
  <div id="mud-freqs" class="mud-freqs"></div>
  <div class="mud-cols">
    <div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">SSID</span><span class="mud-v" id="mud-ssid">--</span></div>
        <div class="mud-r"><span class="mud-k">信道</span><span class="mud-v" id="mud-chan">--</span></div>
        <div class="mud-r"><span class="mud-k">加密</span><span class="mud-v" id="mud-wenc">--</span></div>
        <div class="mud-r"><span class="mud-k">隐藏 SSID</span><span class="mud-v" id="mud-whid">--</span></div>
        <div class="mud-r"><span class="mud-k">国家</span><span class="mud-v" id="mud-wcountry">--</span></div>
        <div class="mud-r"><span class="mud-k">AP 状态</span><span class="mud-v" id="mud-whostapd">--</span></div>
        <div class="mud-r"><span class="mud-k">连接跟踪</span><span class="mud-v" id="mud-conntrack">--</span></div>
        <div class="mud-r"><span class="mud-k">LAN 地址</span><span class="mud-v" id="mud-lanip">--</span></div>
        <div class="mud-r"><span class="mud-k">系统</span><span class="mud-v" id="mud-fwos">--</span></div>
      </div>
    </div>
    <div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">设备型号</span><span class="mud-v" id="mud-model">--</span></div>
        <div class="mud-r"><span class="mud-k">调制解调器</span><span class="mud-v" id="mud-modem">--</span></div>
        <div class="mud-r"><span class="mud-k">运营商</span><span class="mud-v" id="mud-carr">--</span></div>
        <div class="mud-r"><span class="mud-k">PLMN</span><span class="mud-v" id="mud-plmn">--</span></div>
        <div class="mud-r"><span class="mud-k">IMEI</span><span class="mud-v" id="mud-imei">--</span></div>
        <div class="mud-r"><span class="mud-k">IMSI</span><span class="mud-v" id="mud-imsi">--</span></div>
        <div class="mud-r"><span class="mud-k">ICCID</span><span class="mud-v" id="mud-iccid">--</span></div>
        <div class="mud-r"><span class="mud-k">本机号码</span><span class="mud-v" id="mud-msisdn">--</span></div>
        <div class="mud-r"><span class="mud-k">模组</span><span class="mud-v" id="mud-fwmodel">--</span></div>
        <div class="mud-r"><span class="mud-k">固件</span><span class="mud-v" id="mud-fw">--</span></div>
      </div>
      <div class="mud-chiprow"><span class="mud-chip" id="mud-reveal">显示卡号信息</span></div>
    </div>
  </div>
  <div class="mud-cols mud-client-cols">
    <div>
      <div class="mud-r"><span class="mud-k">无线客户端</span><span class="mud-v" id="mud-wcl">--</span></div>
      <div id="mud-clist" style="margin-top:8px"></div>
    </div>
    <div>
      <div class="mud-r"><span class="mud-k">DHCP 租约</span><span class="mud-v" id="mud-wleases">--</span></div>
      <div id="mud-leases" style="margin-top:8px"></div>
    </div>
  </div>
</div>


<div class="mud-sec">
  <h3>快捷控制</h3>
  <div class="mud-ctl" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
    <button class="mud-btn" id="mud-btn-data">数据连接</button>
    <button class="mud-btn" id="mud-btn-radio">蜂窝射频</button>
    <button class="mud-btn" id="mud-btn-wifi">Wi-Fi 热点</button>
    <button class="mud-btn warn" id="mud-btn-modem">重启调制解调器</button>
    <button class="mud-btn warn" id="mud-btn-reboot">重启</button>
  </div>
</div>
<div class="mud-sec">
  <h3>邻区</h3>
  <button class="mud-btn" id="mud-btn-radio-read">读取无线参数</button>
  <div class="mud-note mud-progress" id="mud-slow-progress" role="status"></div>
  <div class="mud-scroll">
  <table class="mud-table"><thead><tr><th>制式/频段</th><th>PCI</th><th>频点</th><th>RSRP</th><th>RSRQ</th><th>SINR</th><th></th></tr></thead>
  <tbody id="mud-neigh"><tr><td colspan="7" style="color:var(--text-muted,var(--text-light,#777))">--</td></tr></tbody></table>
  </div>
</div>

</div><!-- /mud-body -->`;
  this.previous=current;this.history={rx:[],tx:[]};this.disposed=false;this.identShown=false;
  this.root.querySelector('.mud-hero-meta').append(E('span',{'class':'mud-chip',title:'单 SIM，使用 modem5g 数据接口'},'当前 SIM'));
  this.paint(data);this.paintRates(current,rate,cpu,cached);this.wire();
  this.refreshTask=()=>this.refresh();this.sampleTask=()=>this.sample();
  poll.add(this.refreshTask,10);poll.add(this.sampleTask,2);return this.root;
 },
 unload(){this.disposed=true;poll.remove(this.refreshTask);poll.remove(this.sampleTask);},
 q(id){return this.root.querySelector('#mud-'+id);},
 set(id,value){this.q(id).textContent=text(value);},
 pair(a,b,unit=''){return text(a)+(a==null?'':unit)+' / '+text(b)+(b==null?'':unit);},
 async refresh(){if(this.busy||this.disposed)return;this.busy=true;try{const data=await C.dashboard();if(!this.disposed)this.paint(data);}finally{this.busy=false;}},
 async sample(){
  if(this.sampling||this.disposed)return;this.sampling=true;
  try{const current=await C.rates(),rate=C.delta(this.previous,current),cached=rate?null:recentRate(readRateCache(),current);
   if(!this.disposed)this.paintRates(current,rate||cached,C.cpu(this.previous?.cpu,current?.cpu),!rate&&!!cached);this.previous=current;
  }finally{this.sampling=false;}
 },
 paintRates(current,rate,cpu,cached){
  if(rate&&!cached)saveRateCache(current,rate,cpu);
  ['rx','tx'].forEach((key,n)=>{
   const el=this.q(n?'ul':'dl');el.textContent=rate?C.bytes(rate[key])+'/s':'未获取';el.title=cached?'最近一次真实速率':'实时速率';
   if(rate){this.history[key].push(rate[key]);if(this.history[key].length>40)this.history[key].shift();}
   const values=this.history[key],svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),line=document.createElementNS(svg.namespaceURI,'polyline');
   svg.setAttribute('viewBox','0 0 240 40');svg.style.cssText='width:100%;height:40px';const max=Math.max(1,...values);
   line.setAttribute('points',values.map((v,i)=>(i*240/Math.max(1,values.length-1))+','+(39-v*38/max)).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','currentColor');svg.append(line);this.q(n?'spark-ul':'spark-dl').replaceChildren(svg);
  });
  if(cpu!=null){this.set('cpu',cpu.toFixed(1)+'%');this.q('cpu-bar').style.width=cpu+'%';}
 },
 paint(data){
  const systemCpu=C.cpu(this.systemTicks,data.cpu_ticks);this.systemTicks=data.cpu_ticks;
  if(systemCpu!=null){this.set('cpu',systemCpu.toFixed(1)+'%');this.q('cpu-bar').style.width=systemCpu+'%';}
  this.data=data;const m=data.modem||{},n=data.network||{},radio=data.radio_details?.parsed;
  const cells=C.cellular.parseCells({...data.cells?.serving,carriers:radio?.carriers||data.cells?.serving?.carriers}),serving=cells.find(x=>x.serving),sig=serving||m;
  const carriers=radio?.carriers||[],primary=carriers.find(x=>x.type==='NR PCC')||carriers[0];
  const label=M.qLabel(sig.rsrp,sig.rsrq,sig.sinr),score=M.qScore(sig),color=M.qCol(label);
  this.set('host',data.hostname||'OpenWrt');this.set('uptime','已运行 '+C.elapsed(data.uptime));this.q('dot').classList.toggle('on',!!n.up);
  const currentRat=['4G','5G'].includes(m.rat)?m.rat:serving?.rat==='nr'?'5G':serving?.rat==='lte'?'4G':'正在注册';
  this.q('rat').firstChild.nodeValue=(currentRat==='5G'&&radio?.sa_nsa?'5G '+radio.sa_nsa:currentRat);this.q('rat').style.color=color;
  [...this.q('bars').children].forEach((el,i)=>el.classList.toggle('on',score!=null&&i<Math.round(score/2)));
  this.set('op',text(m.operator)+(score==null?'':' · 信号 '+label+' '+score.toFixed(1)+' 分'));
  this.set('cellline',serving?serving.band+' · PCI '+text(serving.pci)+' · ARFCN '+text(serving.arfcn)+(primary?.dl_bandwidth_mhz==null?'':' · '+primary.dl_bandwidth_mhz+' MHz'):(n.up?'小区数据更新中':'蜂窝未连接'));
  this.q('rsrp').replaceChildren(document.createTextNode(sig.rsrp==null?'未获取':sig.rsrp.toFixed(1)),E('small',{},sig.rsrp==null?'':' dBm'));this.q('rsrp').style.color=color;
  this.q('metric-chips').replaceChildren(...[['',label],['RSRQ',sig.rsrq],['SINR',sig.sinr]].map(([k,v])=>E('span',{'class':'mud-tag'},k+' '+text(v))));
  const traffic=data.traffic;
  ['rx','tx'].forEach(k=>this.set(k,M.fmtTrafficBytes(traffic?.totals?.[k])));
  this.set('tr-day',traffic?.clock_ok?M.fmtTrafficBytes(traffic.today_used):null);
  this.set('tr-month',traffic?.clock_ok?M.fmtTrafficBytes(traffic.month_used):null);
  this.set('tr-left',!traffic?.clock_ok?null:traffic.remaining==null?'不限量':M.fmtTrafficBytes(traffic.remaining));
  const trafficAge=Date.now()/1000-traffic?.updated_at;
  this.q('traffic-warning').textContent=!traffic?'流量统计服务尚未就绪':traffic.storage_error?'统计保存失败，请检查可写存储':!traffic.clock_ok?'系统时间未同步，今日和月度数据尚不能归档':!(trafficAge>=0&&trafficAge<30)?'流量统计暂未更新，当前显示上次记录':!traffic.available?'蜂窝统计网卡暂不可用，保留已记录用量':'';
  this.set('ip',address(n['ipv4-address'])+' / '+(data.ipv6_global?.join(' · ')||'未取得全球 IPv6'));
  this.set('apn',data.apn?.apn);this.set('dns',n['dns-server']?.join(' · '));this.set('sess',C.elapsed(n.uptime));
  this.set('roaming',m.roaming);this.set('reg',m.registered?'已注册'+(serving?.tac?' · TAC '+serving.tac:''):'未注册');
  const rows=carriers.length?carriers:[{}];this.q('radio-metrics').replaceChildren(...rows.flatMap(r=>[
   [r.type||'','调制方式 下/上',this.pair(r.dl_modulation_code,r.ul_modulation_code)+'（原始编码）'],
   [r.type||'','载波聚合',(r.band?(r.rat==='lte'?'B':'n')+r.band+' '+text(r.arfcn):'未获取')],
   [r.type||'','BLER 下/上',this.pair(r.dl_bler,r.ul_bler,'%')]
  ].map(([prefix,key,val])=>E('div',{'class':'mud-r'},[E('span',{'class':'mud-k'},prefix+' '+key),E('span',{'class':'mud-v'},val)]))));
  this.set('bw',primary?.dl_bandwidth_mhz!=null && primary.dl_bandwidth_mhz===primary.ul_bandwidth_mhz?primary.dl_bandwidth_mhz+' MHz':this.pair(primary?.dl_bandwidth_mhz,primary?.ul_bandwidth_mhz,' MHz'));
  this.set('qci',data.qos?.cid==+n.data?.cid ? data.qos?.value : null);
  const ambr=radio?.ambr?.network;this.set('ambr',C.mbps(ambr?.dl?.bps)+' / '+C.mbps(ambr?.ul?.bps));
  this.q('lteanchor').replaceChildren(...carriers.filter(r=>r.rat==='lte').map(r=>E('div',{'class':'mud-r'},[E('span',{'class':'mud-k'},'LTE 链路'),E('span',{'class':'mud-v'},'B'+r.band+' · PCI '+r.pci+' · EARFCN '+r.arfcn)])));
  const memory=data.memory||{},storage=data.storage||{};
  this.set('ram',C.value(memory.percent?.toFixed(1),'%'));this.set('ram-sub','共 '+C.bytes(memory.total)+' · 余 '+C.bytes(memory.available));this.q('ram-bar').style.width=(memory.percent||0)+'%';
  this.set('disk',C.value(storage.percent,'%'));this.q('disk-bar').style.width=(storage.percent||0)+'%';
  const temps=data.temperatures||[],pick=rx=>temps.filter(t=>rx.test(t.label||t.name)).map(t=>t.celsius).filter(Number.isFinite);
  const group=(name,values)=>E('span',{style:'color:#e9bf68;background:#0c111b;border-radius:999px;padding:3px 9px'},name+' '+(values.length?Math.max(...values).toFixed(1)+'°C':'未获取'));
  this.q('temps').replaceChildren(group('SoC',pick(/^soc_max$/i)),group('CPU',pick(/^cpu_/i)),group('WiFi',pick(/^mt(?:76|79)[a-z0-9_.-]*/i)),group('调制解调器',pick(/^md[0-9]+$/i)));
  this.q('freqs').replaceChildren(...(data.frequencies||[]).map(f=>E('div',{'class':'mud-freq'},[
   E('span',{'class':'mud-k'},f.policy),E('div',{'class':'mud-meter',style:'flex:1;margin:4px 8px'},E('i',{style:'width:'+(f.maximum_mhz?100*f.current_mhz/f.maximum_mhz:0)+'%'})),
   E('span',{'class':'mud-v'},C.value(f.current_mhz)+' / '+C.value(f.maximum_mhz)+' MHz')])));
  const wireless=data.wireless||[],preferred=wireless.find(w=>w.frequency>=4900&&w.frequency<5925)||wireless[0],unique=key=>[...new Set(wireless.map(w=>w[key]).filter(v=>v!=null&&v!==''))].join(' · ');
  this.set('ssid',unique('ssid'));this.set('chan',preferred?text(preferred.channel)+' ('+(preferred.frequency>=4900?'5 GHz':'2.4 GHz')+(preferred.width?'-'+preferred.width:'')+')':null);
  this.set('wenc',preferred?.encryption);this.set('whid',preferred?(preferred.hidden?'是':'否'):null);this.set('wcountry',preferred?.country?.toLowerCase());
  this.set('whostapd',wireless.length?wireless.some(w=>w.up)?'运行中':'未运行':null);
  this.set('conntrack',this.pair(data.conntrack?.count,data.conntrack?.maximum));this.set('lanip',address(data.lan?.['ipv4-address']));
  this.set('fwos',data.release?.match(/DISTRIB_DESCRIPTION=['"]([^'"]+)/)?.[1]||data.release);this.set('model',data.model);this.set('modem',m.updated?'在线':'未取得状态');this.set('carr',m.operator);this.set('plmn',m.plmn);
  this.paintIdentity();
  const leases=data.leases||[],clients=data.clients||[];this.set('wcl',clients.length+' 台');this.set('wleases',leases.length+' 条');
  const client=(name,detail)=>E('div',{'class':'mud-cli'},[E('div',{'class':'t'},E('b',{},name)),E('div',{'class':'s'},detail)]);
  this.q('clist').replaceChildren(...clients.map(c=>{const l=leases.find(l=>l.mac?.toLowerCase()===c.mac?.toLowerCase());return client((l?.hostname&&l.hostname!=='*'?l.hostname:l?.address)||c.mac,[l?.address,c.mac,C.value(c.signal,' dBm'),'↑'+C.value(c.rx_kbit==null?null:(c.rx_kbit/1000).toFixed(1),' Mbps'),'↓'+C.value(c.tx_kbit==null?null:(c.tx_kbit/1000).toFixed(1),' Mbps')].filter(Boolean).join(' · '));}));
  this.q('leases').replaceChildren(...leases.map(l=>client((l.hostname&&l.hostname!=='*'?l.hostname:l.address),[l.address,l.mac,l.expires==null?'剩余时间未获取':l.expires===0?'永久':C.elapsed(Math.max(0,l.expires-Date.now()/1000))].join(' · '))));
  this.q('neigh').replaceChildren(...(cells.length?cells.map(row=>E('tr',{},[
   ...[row.band+(row.serving?' *':''),row.pci,row.arfcn,row.rsrp,row.rsrq,row.sinr].map(v=>E('td',{},text(v))),E('td',{},E('a',{'class':'mud-btn',href:L.url('admin/modem5g/lock')},'锁定'))
  ])):[E('tr',{},E('td',{colspan:7},'暂无小区数据'))]));
  const requestAge=Date.now()/1000-data.radio_request?.updated,readExpired=data.radio_request?.status==='reading' && !(requestAge>=0 && requestAge<75);
  this.q('btn-radio-read').disabled=data.radio_request?.status==='reading' && !readExpired;
  this.q('slow-progress').textContent=(readExpired?'后台读取未完成，请重新读取':data.radio_request?.message) || (data.initializing?'后台正在采集状态':data.collector_stale?'后台采集暂未更新，当前显示缓存数据':'');
  this.q('btn-modem').disabled=data.modem_restart==='running';
  if(data.modem_restart==='failed')this.q('slow-progress').textContent='模组协议栈重启失败，请查看模组重启日志';
  if(data.radio_details?.stale || data.cells?.stale)this.q('slow-progress').textContent+=' · 显示上次有效数据，后台继续更新';
  this.q('btn-data').classList.toggle('on',!!n.up);this.q('btn-radio').classList.toggle('on',/STATE_ON/.test(m.radio||''));this.q('btn-wifi').classList.toggle('on',wireless.some(w=>w.up));
 },
 paintIdentity(){
  const m=this.identity||this.data.modem||{};
  for(const [id,key] of [['imei','imei'],['imsi','imsi'],['iccid','iccid']])this.set(id,m[key]);
  this.set('msisdn',m.phone||this.data.modem?.phone);this.set('fwmodel',this.data.modem?.model);this.set('fw',this.data.modem?.firmware);
 },
 wire(){
  const confirm=(button,title,body,invoke)=>{button.onclick=async()=>{
   if(this.pending)return;this.pending=true;
   try{if(this.disposed||!await M.confirmBox(title,body)||this.disposed)return;M.busy(button,true);const r=await invoke();if(r?.code||r?.ok===0)throw Error(r.error||r.output||'操作失败');M.toast(r.output||'请求已提交，请确认实际状态');await this.refresh();}
   catch(e){M.toast(e.message,{type:'error'});}finally{this.pending=false;M.busy(button,false);}
  };};
  confirm(this.q('btn-data'),'切换数据连接','蜂窝连接会短暂中断。',()=>this.data.network?.up?C.disconnect():C.connect());
  confirm(this.q('btn-radio'),'切换蜂窝射频','关闭射频后无法收发短信或使用蜂窝网络。',()=>C.setRadio(!/STATE_ON/.test(this.data.modem?.radio||'')));
  confirm(this.q('btn-wifi'),'切换 Wi-Fi 热点','关闭后无线客户端会断开，需重新连接才能管理设备。',()=>action((this.data.wireless||[]).some(w=>w.up)?'wifi_off':'wifi_on'));
  confirm(this.q('btn-reboot'),'重启设备','所有连接会断开，请等待设备重新启动。',()=>action('reboot'));
  confirm(this.q('btn-modem'),'重启调制解调器','将重新启动模组无线协议栈并重建蜂窝连接，期间蜂窝网络会中断。WiFi保持开启。',()=>action('modem_restart'));
  this.q('btn-radio-read').onclick=async()=>{try{const r=await radioRead();if(r.code)throw Error(r.error);M.toast(r.output);}catch(e){M.toast(e.message,{type:'error'});}};
  this.q('reveal').onclick=async()=>{if(this.identityBusy)return;this.identityBusy=true;
   try{const reveal=!this.identShown;this.identity=await C.getIdentity(reveal);this.identShown=reveal;this.q('reveal').textContent=reveal?'隐藏卡号信息':'显示卡号信息';this.paintIdentity();}catch(e){M.toast(e.message,{type:'error'});}finally{this.identityBusy=false;}
  };
 }
});
