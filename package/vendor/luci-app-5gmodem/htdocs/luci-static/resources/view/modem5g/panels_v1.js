'use strict';
'require view';
'require poll';
'require modem5g.cpe_v1 as C';

const titles={cpu:'CPU 设置',device:'设备管理',sim:'SIM 卡管理',settings:'适配设置',ttl:'TTL',battery:'电池与电量',forward:'短信转发',traffic:'流量池'};
return view.extend({
 load(){return C.dashboard();},
 render(data){
  const path=L.env.requestpath||[],key=path[path.length-1]||'settings',title=titles[key]||'平台能力';
  const root=E('div',{'class':'cpe'},[C.style(),E('h2',{},title)]),m=data.modem||{};
  if(key==='cpu'){
   root.append(C.card('CPU 频率',C.table(['策略','当前频率','硬件最高频率'],(data.frequencies||[]).map(p=>[p.policy,C.value(p.current_mhz,' MHz'),C.value(p.maximum_mhz,' MHz')]))),
    C.card('CPU 温度',C.table(['传感器','温度'],(data.temperatures||[]).filter(t=>/^cpu_/.test(t.name)).map(t=>[t.name,t.celsius.toFixed(1)+' °C']))),
    C.unavailable('当前支持查看 CPU 状态。频率、电压和核心数量调整暂不支持。'));
  }else if(key==='sim'){
   const details=E('div');const paint=identity=>details.replaceChildren(C.rows([['SIM 状态',identity.sim],['运营商 / PLMN',identity.operator||m.operator],['IMEI',identity.imei],['IMSI',identity.imsi],['ICCID',identity.iccid]]));
   paint(m);let revealed=false;
   const reveal=E('button',{'class':'btn',click:async()=>{reveal.disabled=true;try{const state=await C.getIdentity(!revealed);revealed=!revealed;paint(state);reveal.textContent=revealed?'隐藏完整号码':'显示完整号码';}finally{reveal.disabled=false;}}},'显示完整号码');
   root.append(C.card('当前 SIM',details),reveal,C.unavailable('当前支持查看 SIM 状态，暂不支持卡槽切换或 eSIM 管理。'));
  }else if(key==='device'){
   root.append(C.card('本机',C.rows([['型号',data.model],['板型',data.board],['LAN',(data.lan?.['ipv4-address']||[]).map(a=>a.address+'/'+a.mask).join(' · ')]])),
    C.card('USB 控制器',C.table(['控制器','状态'],(data.usb||[]).map(d=>[d.controller,d.state]))),
    C.unavailable('当前支持查看设备和 USB 状态，暂不支持切换 USB 连接模式。'));
  }else if(key==='traffic'){
   const counters=E('div');
   const refresh=async()=>{const sample=await C.rates();counters.replaceChildren(C.rows([['接口',sample?.device],['接收累计',C.bytes(sample?.rx)],['发送累计',C.bytes(sample?.tx)]]));};
   refresh();poll.add(refresh,5);
   root.append(C.card('当前接口累计',counters),
    C.unavailable('计数来自内核接口，本机重启或接口重建后可能归零。当前尚未保存跨重启历史，不能作为套餐用量或运营商账单。'));
  }else if(key==='forward'){
   root.append(C.card('短信转发状态',C.rows([['自动转发','关闭'],['发送后台','未接入可靠的本地短信事件池']])),
    C.unavailable('短信自动转发尚未开放。查看与发送短信请使用“短信”页面。'));
  }else if(key==='ttl'){
   root.append(C.card('IP 数据包 TTL',C.rows([['当前 IPv4 默认 TTL',data.network_defaults?.ipv4_ttl],['当前 IPv6 默认 Hop Limit',data.network_defaults?.ipv6_hop_limit]])),
    C.unavailable('本页显示路由器本机发包的默认值，不代表转发流量的值。转发 TTL 重写暂不支持。'));
  }else if(key==='battery'){
   root.append(C.card('电源信息',C.table(['设备','类型','状态','容量'],(data.power_supplies||[]).map(d=>[d.name,d.type,d.status,C.value(d.capacity,'%')]))),
    C.unavailable('仅支持查看系统电源信息，暂不支持调整充电策略。'));
  }else{
   root.append(C.card('MT6990 平台适配',C.rows([['板型',data.board],['固件提交',data.firmware_id],['蜂窝协议',data.network?.proto],['实际数据接口',data.network?.l3_device],['AT 所有者','现有 atcid / modem5g-at'],['RIL 控制','现有 mipc_wan_cli / qlril，复用控制锁'],['采集模式','状态页只读缓存，不新增周期 AT 查询']])),
    C.unavailable('平台接口由固件维护，不提供任意串口、shell 命令或展锐后台的切换选项。'));
  }
  return root;
 },handleSaveApply:null,handleSave:null,handleReset:null
});
