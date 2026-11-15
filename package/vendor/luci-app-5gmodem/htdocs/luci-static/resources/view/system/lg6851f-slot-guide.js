'use strict';
'require view';
'require modem5g.slot_guide_v1 as G';

return view.extend({
 handleSaveApply:null,handleSave:null,handleReset:null,
 render:function(){return E('div',{'class':'cbi-map'},[
  E('h2',{},'原厂固件切换到自编译固件说明'),G.content(true)
 ]);}
});
