'use strict';
'require baseclass';
'require rpc';
'require ui';
'require modem5g.cellular_v1 as cellular';

const dashboard = rpc.declare({ object: 'luci.modem5g', method: 'get_dashboard', expect: {} });
const rates = rpc.declare({ object: 'luci.modem5g', method: 'get_rates', expect: {} });
const getApn = rpc.declare({ object: 'luci.modem5g', method: 'get_apn', expect: {} });
const saveApn = rpc.declare({ object: 'luci.modem5g', method: 'set_apn', params: ['values', 'apply'], expect: {} });
const getIdentity = rpc.declare({ object: 'luci.modem5g', method: 'get_sim_identity', params: ['reveal'], expect: {} });
const setRadio = rpc.declare({ object: 'luci.modem5g', method: 'set_radio', params: ['enabled'], expect: {} });
const connect = rpc.declare({ object: 'luci.modem5g', method: 'ifup', expect: {} });
const disconnect = rpc.declare({ object: 'luci.modem5g', method: 'ifdown', expect: {} });
const getCells = rpc.declare({ object: 'luci.modem5g', method: 'get_cells', expect: {} });
const getRadioDetails = rpc.declare({ object: 'luci.modem5g', method: 'get_radio_details', expect: {} });

return baseclass.extend({
 dashboard, rates, getApn, saveApn, getIdentity, setRadio, connect, disconnect, getCells, getRadioDetails, cellular,
 mbps(value) {return value == null ? '未获取' : (value / 1e6).toLocaleString('zh-CN',{maximumFractionDigits:3})+' Mbit/s';},
 value(v, unit) { return v == null || v === '' ? '未获取' : String(v) + (unit || ''); },
 bytes(v) { if (v == null) return '未获取'; const u = ['B','KiB','MiB','GiB','TiB']; let i=0; while(v>=1024&&i<4){v/=1024;i++;} return `${v.toFixed(i ? 2 : 0)} ${u[i]}`; },
 elapsed(v) { if(v==null)return '未获取'; v=Math.floor(v); return `${Math.floor(v/86400)}天 ${Math.floor(v%86400/3600)}小时 ${Math.floor(v%3600/60)}分`; },
 delta(a,b) { if(!a||!b||a.boot_id!==b.boot_id||a.device!==b.device||b.at<=a.at||a.rx==null||a.tx==null||b.rx==null||b.tx==null||b.rx<a.rx||b.tx<a.tx)return null; return {rx:(b.rx-a.rx)/(b.at-a.at),tx:(b.tx-a.tx)/(b.at-a.at)}; },
 cpu(a,b) { if(!a||!b||b.total<=a.total||b.idle<a.idle)return null; const v=100*(1-(b.idle-a.idle)/(b.total-a.total));return v>=0&&v<=100?v:null; },
 card(title,content){ return E('section',{'class':'cpe-card'},[E('h3',{},title),content]); },
 metric(label,value){ return E('div',{'class':'cpe-metric'},[E('small',{},label),E('strong',{},value==null?'未获取':String(value))]); },
 rows(items){ return E('dl',{'class':'cpe-rows'},items.flatMap(([name,value])=>[E('dt',{},name),E('dd',{},value==null||value===''?'未获取':String(value))])); },
 table(headers,rows){return E('div',{'class':'cpe-scroll'},E('table',{'class':'cpe-table'},[E('thead',{},E('tr',{},headers.map(h=>E('th',{},h)))),E('tbody',{},rows.length?rows.map(row=>E('tr',{},row.map(value=>E('td',{},value==null?'未获取':String(value))))):E('tr',{},E('td',{colspan:headers.length},'暂无数据')))]));},
 unavailable(message){return E('p',{'class':'cpe-note'},message);},
 async action(title,message,operation,refresh){
  return ui.showModal(title,[E('p',{},message),E('div',{'class':'right'},[
   E('button',{'class':'btn',click:ui.hideModal},'取消'),
   E('button',{'class':'btn cbi-button-action',click:async function(ev){
    const button=ev.currentTarget; if(button.disabled)return;button.disabled=true;
    try{const result=await operation();if(result?.code)throw Error(result.error||result.output||'操作失败');ui.hideModal();ui.addNotification(null,E('p',{},result?.output||'请求已完成，请核对实际状态'),'info');if(refresh)await refresh();}
    catch(error){ui.addNotification(null,E('p',{},error.message||String(error)),'error');button.disabled=false;}
   }},'确认执行')])]);
 },
 style(){return E('style',{},`
 .cpe{width:100%;max-width:1400px;margin:auto;color:var(--text,inherit);container-type:inline-size}
 .cpe *{box-sizing:border-box}.cpe-card{padding:1rem;margin:1rem 0;border:1px solid var(--hairline,#8885);border-radius:var(--radius-base,.8rem);background:var(--surface,transparent);min-width:0}
 .cpe-card h3{margin:0 0 1rem}.cpe-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(15rem,100%),1fr));gap:.8rem}.cpe-metric{padding:.9rem;border:1px solid var(--hairline,#8884);border-radius:.6rem;min-width:0}.cpe-metric small{display:block;opacity:.7}.cpe-metric strong{display:block;font-size:1.25rem;overflow-wrap:anywhere;margin-top:.3rem}
 .cpe-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}.cpe-hero strong{font-size:1.8rem;color:var(--brand,#009f9d)}.cpe-note{opacity:.72;white-space:pre-wrap;overflow-wrap:anywhere}.cpe-rows{display:grid;grid-template-columns:minmax(8rem,.6fr) minmax(0,1fr);gap:.7rem}.cpe-rows dt,.cpe-rows dd{margin:0;border-bottom:1px dashed var(--hairline,#8884);padding:.4rem;overflow-wrap:anywhere}
 .cpe-scroll{max-width:100%;overflow-x:auto}.cpe-table{width:100%;border-collapse:collapse}.cpe-table th,.cpe-table td{padding:.6rem;text-align:left;border-bottom:1px solid var(--hairline,#8884);overflow-wrap:anywhere}.cpe-actions{display:flex;flex-wrap:wrap;gap:.6rem}.cpe-actions .btn{white-space:normal}.cpe-chart{width:100%;height:64px;display:block;color:var(--brand,#009f9d)}.cpe-chart polyline{fill:none;stroke:currentColor;stroke-width:2;vector-effect:non-scaling-stroke}
 .cpe-form{display:grid;grid-template-columns:minmax(8rem,.4fr) minmax(0,1fr);gap:.8rem;align-items:center}.cpe-form input,.cpe-form select{width:100%;min-width:0}.cpe-header{display:flex;flex-wrap:wrap;gap:.7rem;align-items:center;justify-content:space-between}.cpe-private{font-family:monospace}.cpe-badge{display:inline-block;padding:.15rem .45rem;border:1px solid var(--hairline,#8885);border-radius:.4rem}
 @container(max-width:650px){.cpe-form,.cpe-rows{grid-template-columns:minmax(0,1fr)}.cpe-card{padding:.75rem}.cpe-table th,.cpe-table td{padding:.4rem .2rem}.cpe-actions .btn{flex:1 1 8rem}.cpe-hero strong{font-size:1.4rem}}
 `);}
});
