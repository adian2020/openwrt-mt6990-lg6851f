'use strict';
'require view';
'require poll';
'require modem5g.cpe_v1 as C';

const titles={device:'设备管理',settings:'适配设置',ttl:'TTL',battery:'电池与电量'};
return view.extend({
 load(){return C.dashboard();},
 render(data){
  const path=L.env.requestpath||[],key=path[path.length-1]||'settings',title=titles[key]||'平台能力';
  const root=E('div',{'class':'cpe'},[C.style(),E('h2',{},title)]),m=data.modem||{};
  if(key==='device'){
   root.append(C.card('本机',C.rows([['型号',data.model],['板型',data.board],['LAN',(data.lan?.['ipv4-address']||[]).map(a=>a.address+'/'+a.mask).join(' · ')]])),
    C.card('USB 控制器',C.table(['控制器','状态'],(data.usb||[]).map(d=>[d.controller,d.state]))),
    C.unavailable('当前支持查看设备和 USB 状态，暂不支持切换 USB 连接模式。'));
  }else if(key==='ttl'){
   root.append(C.card('IP 数据包 TTL',C.rows([['当前 IPv4 默认 TTL',data.network_defaults?.ipv4_ttl],['当前 IPv6 默认 Hop Limit',data.network_defaults?.ipv6_hop_limit]])),
    C.unavailable('本页显示路由器本机发包的默认值，不代表转发流量的值。转发 TTL 重写暂不支持。'));
  }else if(key==='battery'){
   root.append(C.card('电源信息',C.table(['设备','类型','状态','容量'],(data.power_supplies||[]).map(d=>[d.name,d.type,d.status,C.value(d.capacity,'%')]))),
    C.unavailable('仅支持查看系统电源信息，暂不支持调整充电策略。'));
  }else{
   root.append(C.card('MT6990 平台适配',C.rows([['板型',data.board],['固件提交',data.firmware_id],['蜂窝协议',data.network?.proto],['实际数据接口',data.network?.l3_device],['AT 所有者','现有 atcid / modem5g-at'],['RIL 控制','现有 mipc_wan_cli / qlril，复用控制锁'],['采集模式','状态页只读缓存，不新增周期 AT 查询']])),
    C.unavailable('平台接口由固件维护。状态页读取缓存；启用短信转发后按配置周期读取收件箱。不提供任意串口或展锐后台切换。'));
  }
  return root;
 },handleSaveApply:null,handleSave:null,handleReset:null
});
