'use strict';
'require baseclass';
'require rpc';
'require ui';
var CSS = `
/* Bootstrap exposes a different token family. Only activate this bridge when
 * Aurora's --surface token is absent, so existing Aurora styling wins intact.
 * Bootstrap's data-darkmode switch updates these aliases without a reload. */
html.mud-bootstrap-theme{--surface:var(--background-color-high);--surface-sunken:var(--background-color-low);--brand-subtle:color-mix(in srgb,var(--primary-color-high) 10%,var(--background-color-high));--hairline:var(--border-color-low);--text:var(--text-color-high);--text-muted:var(--text-color-medium);--text-subtle:var(--text-color-low);--brand:var(--primary-color-high);--success:var(--success-color-high);--warning:var(--warn-color-high);--danger:var(--error-color-high);--info:var(--primary-color-high);--on-brand:var(--on-primary-color);--hover-faint:var(--background-color-medium)}
.mud{color:var(--text,#222);font-size:.85rem;line-height:1.45}
.mud-sim-selector{color:var(--text,#222)}
.mud-sim-options{padding-top:12px}
.mud-sim-select-label{display:flex;flex-direction:column;gap:8px;font-weight:600}
.mud-sim-select-label select{width:100%;min-height:36px}
.mud-sim-options>.mud-note{margin:12px 0 0;font-size:.78rem}
.mud-hero{position:relative}
.mud-hero-meta{display:flex;align-items:center;flex-wrap:wrap;gap:5px}
.mud-sim-hero{position:relative;display:inline-block;margin-left:7px;font-size:.74rem;line-height:1.3;z-index:10}
.mud-sim-hero>.mud-sim-toggle{display:flex;align-items:center;gap:7px;list-style:none;cursor:pointer;white-space:nowrap;padding:4px 9px;border:1px solid var(--hairline,var(--border,#ddd));border-radius:999px;background:var(--surface,var(--background,#fff));font-weight:600;user-select:none}
.mud-sim-hero>.mud-sim-toggle::-webkit-details-marker{display:none}
.mud-sim-hero>.mud-sim-toggle::after{content:'';width:5px;height:5px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(45deg);margin-top:-3px}
.mud-sim-hero>.mud-sim-toggle:focus-visible{outline:2px solid var(--brand,var(--primary,#2f7bf6));outline-offset:3px}
.mud-sim-hero[open]>.mud-sim-toggle{border-color:var(--brand,var(--primary,#2f7bf6))}
.mud-sim-hero[open]>.mud-sim-toggle::after{transform:rotate(225deg);margin-top:3px}
.mud-sim-hero>.mud-sim-options{position:absolute;top:calc(100% + 8px);left:0;box-sizing:border-box;width:280px;max-width:calc(100vw - 32px);padding:16px;border:1px solid var(--hairline,var(--border,#ddd));border-radius:calc(var(--radius-base,.5rem) + .375rem);background:var(--surface,var(--background,#fff));box-shadow:var(--app-shadow-md,0 8px 28px rgba(0,0,0,.15))}
@media(max-width:600px){.mud-hero-meta{padding-right:78px}.mud-sim-hero{position:absolute;right:14px;top:12px;margin:0}.mud-sim-hero>.mud-sim-options{left:auto;right:0}}

.mud *{box-sizing:border-box}
.mud-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px;margin-top:6px}
.mud-card{background:var(--surface,var(--background-alt,var(--background,#fff)));border:1px solid var(--hairline,var(--border,#e3e6ea));border-radius:calc(var(--radius-base,.5rem) + .375rem);padding:14px 16px;box-shadow:var(--app-shadow-sm,0 1px 3px rgba(0,0,0,.04));transition:border-color .15s}
.mud-card:hover{border-color:color-mix(in oklab,var(--brand,var(--primary,#2f7bf6)) 30%,var(--hairline,var(--border,#e3e6ea)))}
.mud .mud-sim-toggle,.mud .mud-sim-toggle:hover{background:transparent}
.mud-card>h3{margin:0 0 8px;font-size:.7rem;font-weight:600;color:var(--text-muted,var(--text-light,#787d85));letter-spacing:.08em}
.mud-card>h3::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6));margin-right:7px;vertical-align:1px}
.mud-hero{display:flex;flex-wrap:wrap;gap:12px 28px;align-items:center;background:var(--brand-subtle,var(--surface,#fff));margin-bottom:12px;padding:16px 20px}
.mud-sec{padding:2px 2px 6px}
.mud-sec>h3{margin:16px 0 10px;font-size:.7rem;font-weight:600;color:var(--text-muted,var(--text-light,#787d85));letter-spacing:.08em}
.mud-sec>h3::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6));margin-right:7px;vertical-align:1px}
.mud-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:0 28px}
.mud-client-cols{grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px 28px;margin-top:16px;align-items:start}
.mud-client-cols>div{min-width:0}
.mud-client-cols .mud-cli .t{flex-wrap:wrap;overflow-wrap:anywhere}
.mud-client-cols .mud-cli .s{overflow-wrap:anywhere}
.mud-body>.mud-sec+.mud-sec{border-top:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 60%,transparent);margin-top:14px;padding-top:2px}
/* 首屏骨架：卡片正常占位，只让待填字段呼吸；第一份快照到达后停止。 */
@keyframes mudpulse{0%,100%{opacity:1}50%{opacity:.35}}
.mud-booting .mud-v,.mud-booting .mud-kpi b,.mud-booting .mud-rsrp,.mud-booting .mud-rat,.mud-booting .mud-temp span{animation:mudpulse 1.1s ease-in-out infinite}
/* 紧凑键值行：键与值相邻排布（不两端对齐拉开），用于驻网参照等 */
.mud-srvline{display:flex;flex-wrap:wrap;gap:4px 10px;padding:2px 0;font-size:.84rem}
.mud-srvline .k{color:var(--text-muted,var(--text-light,#777));flex:0 0 auto}
.mud-srvline .v{font-variant-numeric:tabular-nums;font-weight:500}
.mud-charts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.mud-chart{background:transparent;border-radius:var(--radius-base,.5rem);padding:2px 4px 0}
.mud-chart .t{display:flex;align-items:baseline;gap:8px}
.mud-chart .t b{font-size:1.2rem;font-weight:700;font-variant-numeric:tabular-nums}
.mud-chart .t span{font-size:.72rem;color:var(--text-muted,var(--text-light,#777))}
.mud-chart .c{height:40px;margin-top:2px}
.mud-chart .c svg{display:block;width:100%;height:100%}
.mud-lockbtn{padding:0 10px;border-radius:99px;border:1px solid var(--hairline,var(--border,#ccc));background:var(--surface,var(--background,#fff));color:var(--text,#222);font-size:.72rem;cursor:pointer;line-height:1.7}
.mud-lockbtn.on,.mud-lockbtn:active{background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-lockbtn.locked{opacity:.45;pointer-events:none;background:var(--surface-sunken,rgba(127,127,127,.1));color:var(--text-muted,var(--text-light,#888));border-color:transparent}
.mud-hero-l{flex:1 1 260px;min-width:0;display:flex;flex-direction:column;gap:5px}
.mud-hero-r{flex:0 0 auto;text-align:right;display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.mud-rat{font-size:1.7rem;font-weight:700;line-height:1.1;letter-spacing:.01em}
.mud-op{color:var(--text-muted,var(--text-light,#777));font-size:.85rem}
.mud-cellline{font-size:.78rem;color:var(--text-muted,var(--text-light,#777));font-variant-numeric:tabular-nums;line-height:1.55}
.mud-rsrp{font-size:2.3rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.mud-rsrp small{font-size:.9rem;font-weight:500}
.mud-chips{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}
.mud-imei-label{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap}
.mud-k.mud-imei-label{flex:1 1 0;min-width:0;overflow-wrap:anywhere}
.mud-imei-label + .mud-v{flex:0 0 auto;white-space:nowrap}
.mud-imei-active{display:inline-flex;align-items:center;padding:1px 6px;border-radius:99px;font-size:.68rem;font-weight:600;line-height:1.4;color:var(--success,#2fbf71);background:color-mix(in srgb,var(--success,#2fbf71) 14%,transparent);white-space:nowrap}
.mud-imei-active[hidden]{display:none}
.mud-tag{display:inline-block;padding:1px 8px;border-radius:99px;background:var(--surface-sunken,rgba(127,127,127,.1));font-size:.74rem;font-weight:600;font-variant-numeric:tabular-nums}
.mud-q{display:inline-block;min-width:3em;padding:1px 8px;border-radius:99px;font-size:.74rem;font-weight:600;text-align:center}
.mud-rows{display:grid;gap:2px}
.mud-r{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 55%,transparent)}
.mud-r:last-child{border-bottom:none}
.mud-k{color:var(--text-muted,var(--text-light,#777));flex:0 0 auto}
.mud-v{font-variant-numeric:tabular-nums;text-align:right;word-break:break-all;font-weight:500}
.mud-bars{display:inline-flex;align-items:flex-end;gap:2px;height:16px;margin-left:8px;vertical-align:baseline}
.mud-bars i{width:3px;border-radius:1px;background:var(--hairline,var(--border,#ccc))}
.mud-bars i.on{background:currentColor}
.mud-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(122px,1fr));gap:10px;margin-bottom:10px}
.mud-kpi{background:var(--surface-sunken,rgba(127,127,127,.06));border-radius:var(--radius-base,.5rem);padding:9px 12px}
.mud-kpi b{display:block;font-size:1.05rem;font-variant-numeric:tabular-nums;font-weight:700;line-height:1.25}
.mud-kpi span{font-size:.68rem;color:var(--text-muted,var(--text-light,#777))}
.mud-sub{font-size:.68rem;color:var(--text-subtle,var(--text-light,#999));font-variant-numeric:tabular-nums}
.mud-meter{height:5px;border-radius:3px;background:var(--surface-sunken,rgba(127,127,127,.15));overflow:hidden;margin:3px 0 1px}
.mud-meter i{display:block;height:100%;border-radius:3px}
.mud-freq{display:flex;align-items:center;font-size:.76rem;font-variant-numeric:tabular-nums;padding:1px 0}
.mud-freq .mud-k{flex:0 0 2.4em}
.mud-manual-cell{margin:12px 0;max-width:720px;min-width:0}
.mud-manual-cell summary{cursor:pointer;padding:8px 0;font-size:.85rem;font-weight:600}
.mud-manual-cell form{margin:4px 0 12px}
.mud-manual-cell-fields{display:flex;flex-wrap:wrap;align-items:end;gap:12px}
.mud-manual-cell-fields label{display:flex;flex:1 1 140px;flex-direction:column;gap:6px;margin:0;min-width:0;font-size:.82rem}
.mud-manual-cell-fields input,.mud-manual-cell-fields select{box-sizing:border-box;width:100%;max-width:100%;min-width:0;min-height:38px;margin:0;padding:8px 10px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font:inherit}
.mud-manual-cell-fields button{min-height:38px;margin:0;white-space:normal}
.mud-manual-cell-fields input:focus,.mud-manual-cell-fields select:focus{outline:2px solid var(--brand,var(--primary,#37a));outline-offset:1px}
.mud-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:7px 12px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-size:.82rem;cursor:pointer;user-select:none}
.mud-btn:active{transform:scale(.97)}
.mud-voice-row{align-items:center;gap:12px;padding:8px 0}
.mud-voice-row .mud-v{flex:1;text-align:right;min-width:0;overflow-wrap:anywhere}
.mud-btn.mud-voice-switch{flex:0 0 48px;min-height:36px;padding:6px;border:0;border-radius:18px;background:transparent;color:var(--text,#222)}
.mud-voice-switch:focus-visible{outline:2px solid var(--brand,var(--primary,#2f7bf6));outline-offset:2px}
.mud-voice-track{position:relative;display:block;width:36px;height:22px;flex:0 0 36px;border-radius:12px;background:var(--muted,#777);transition:background .18s}
.mud-voice-track:after{content:"";position:absolute;left:3px;top:3px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0003;transition:transform .18s}
.mud-voice-switch.on .mud-voice-track{background:var(--brand,var(--primary,#2f7bf6))}
.mud-voice-switch.on .mud-voice-track:after{transform:translateX(14px)}
@media(prefers-reduced-motion:reduce){.mud-voice-track,.mud-voice-track:after{transition:none}}

.mud-btn.on:not(.mud-voice-switch){background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-btn.warn{border-color:color-mix(in oklab,var(--danger,#E25555) 55%,transparent);color:var(--danger,#E25555)}
.mud-btn[disabled]{opacity:.4;pointer-events:none}
.mud-ctl{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px}
.mud-note{font-size:.72rem;color:var(--text-subtle,var(--text-light,#999));margin-top:7px}
.mud-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.8rem}
.mud-table th{font-weight:500;color:var(--text-muted,var(--text-light,#777));text-align:right;padding:1px 4px;border-bottom:1px solid var(--hairline,var(--border,#ddd));font-size:.72rem;position:sticky;top:0;background:var(--surface,var(--background-alt,var(--background,#fff)))}
.mud-table td{text-align:right;padding:3px 6px;border-bottom:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 5%,transparent)}
.mud-table th:first-child,.mud-table td:first-child{text-align:left}
.mud-scroll{max-height:230px;overflow:auto;border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 45%,transparent);border-radius:var(--radius-base,.5rem);padding:4px}
.mud-cli{padding:4px 8px;border-radius:var(--radius-base,.5rem);border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 55%,transparent);margin-bottom:5px}
.mud-cli .t{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.mud-cli .s{font-size:.72rem;color:var(--text-muted,var(--text-light,#888));font-variant-numeric:tabular-nums;margin-top:1px}
/* ---- 聊天式短信 ---- */
.mud-chat{display:flex;gap:12px;min-height:420px}
.mud-convs{flex:0 0 240px;overflow:auto;max-height:520px}
.mud-conv{padding:7px 9px;border-radius:var(--radius-base,.5rem);cursor:pointer;margin-bottom:4px;border:1px solid transparent}
.mud-conv:hover{background:var(--hover-faint,rgba(127,127,127,.06))}
.mud-conv.sel{background:var(--brand-subtle,var(--surface-sunken,rgba(127,127,127,.08)));border-color:color-mix(in oklab,var(--brand,var(--primary,#2f7bf6)) 30%,transparent)}
.mud-conv .n{display:flex;justify-content:space-between;gap:6px;font-weight:600;font-size:.84rem}
.mud-conv .p{font-size:.74rem;color:var(--text-muted,var(--text-light,#888));white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.mud-thread{flex:1;display:flex;flex-direction:column;min-width:0;border-left:1px solid var(--hairline,var(--border,#ddd));padding-left:12px}
.mud-msgs{flex:1;overflow:auto;max-height:460px;padding:4px 2px;display:flex;flex-direction:column;gap:6px}
.mud-bub{max-width:78%;padding:6px 11px;border-radius:calc(var(--radius-base,.5rem) + .25rem);font-size:.85rem;white-space:pre-wrap;word-break:break-word;align-self:flex-start;background:var(--surface-sunken,rgba(127,127,127,.08))}
.mud-bub.out{align-self:flex-end;background:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-bub .tm{display:block;font-size:.64rem;opacity:.65;margin-top:2px;text-align:right;font-variant-numeric:tabular-nums}
.mud-comp{display:flex;gap:8px;margin-top:8px}
.mud-comp input,.mud-comp textarea{padding:7px 11px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-family:inherit}
.mud-comp input{flex:0 0 170px}
.mud-comp textarea{flex:1;resize:none;min-height:40px;max-height:120px}
@media(max-width:700px){.mud-chat{flex-direction:column}.mud-convs{flex:none;max-height:150px}.mud-thread{border-left:none;padding-left:0;border-top:1px solid var(--hairline,var(--border,#ddd));padding-top:8px}}
/* ---- 专业 AT 终端 ---- */
.mud-at-grid{display:grid;grid-template-columns:1fr 220px;gap:10px}
.mud-at-grid .mud-scroll{max-height:340px}
@media(max-width:700px){.mud-at-grid{grid-template-columns:1fr}.mud-term{height:300px}.mud-at-grid .mud-scroll{max-height:120px}}
.mud-term{font-family:var(--font-mono,monospace);font-size:.8rem;line-height:1.5;background:color-mix(in oklab,var(--surface,#14161a) 92%,var(--brand,#2f7bf6) 3%);color:var(--text,#d5d9de);border:1px solid var(--hairline,var(--border,#2a2d33));border-radius:var(--radius-base,.5rem);padding:12px;height:380px;overflow:auto;white-space:pre-wrap;word-break:break-all}
.mud-term .ln-cmd{color:var(--brand,#6ab0ff);font-weight:600}
.mud-term .ln-ok{color:var(--success,#57c98a);font-weight:600}
.mud-term .ln-err{color:var(--danger,#ff7b72);font-weight:600}
.mud-term .ln-data{color:var(--text,#d5d9de)}
.mud-term .ln-meta{color:var(--text-subtle,#7d8590);font-style:italic}
.mud-term .ln-ms{float:right;color:var(--text-subtle,#7d8590);font-size:.7rem}
.mud-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--text-subtle,#8A8F98);margin-right:6px;vertical-align:1px}
.mud-dot.on{background:var(--success,#2FBF71)}
.mud-temp{display:inline-flex;gap:5px;flex-wrap:wrap}
.mud-temp span{padding:1px 8px;border-radius:var(--radius-base,.5rem);background:var(--surface-sunken,rgba(127,127,127,.08));font-variant-numeric:tabular-nums;font-size:.76rem}
.mud-at-in{display:flex;gap:7px;margin-bottom:7px}
.mud-at-in input{flex:1;min-width:0;padding:6px 10px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-family:var(--font-mono,monospace)}
.mud-out{font-family:var(--font-mono,monospace);font-size:.78rem;white-space:pre-wrap;background:var(--surface-sunken,rgba(127,127,127,.07));border-radius:var(--radius-base,.5rem);padding:9px;max-height:260px;overflow:auto;margin:7px 0 0}
.mud-chiprow{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.mud-chip{padding:2px 9px;border-radius:99px;border:1px solid var(--hairline,var(--border,#ccc));font-size:.72rem;font-family:var(--font-mono,monospace);cursor:pointer}
.mud-chip.on{background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-sms-item{padding:6px 8px;border-radius:var(--radius-base,.5rem);border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 60%,transparent);margin-bottom:6px;cursor:pointer}
.mud-sms-item:hover{background:var(--hover-faint,rgba(127,127,127,.05))}
.mud-sms-top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.mud-badge{display:flex;align-items:center;justify-content:center;font-size:.68rem;padding:0 7px;min-width:20px;height:20px;box-sizing:border-box;border-radius:99px;background:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
/* 手机端 hero 与锁定页一致：信息块在上、RSRP 块自然换行到下一行（右对齐） */
@media(max-width:600px){
.mud-hero{gap:8px}
.mud-hero-l{flex:1 1 100%}
.mud-hero-r{flex:1 0 100%;flex-direction:row;justify-content:space-between;align-items:baseline;text-align:left}
.mud-rsrp{font-size:1.9rem}
.mud-chips{justify-content:flex-end}}
/* ---- 顶部 toast 与按钮忙碌态（各页共用的反馈框架） ---- */
.mud-toasts{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;width:max-content;max-width:min(92vw,560px)}
.mud-toast{pointer-events:auto;display:flex;align-items:center;gap:9px;padding:9px 16px;border-radius:99px;background:var(--surface,var(--background,#fff));border:1px solid var(--hairline,var(--border,#ddd));box-shadow:0 6px 24px rgba(0,0,0,.14);font-size:.82rem;color:var(--text,#222);animation:mudtoast-in .22s ease-out;max-width:100%}
.mud-toast.out{animation:mudtoast-out .25s ease-in forwards}
.mud-toast .mud-tico{flex:0 0 auto;width:8px;height:8px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6))}
.mud-toast.success .mud-tico{background:var(--success,#2FBF71)}
.mud-toast.error .mud-tico{background:var(--danger,#E25555)}
.mud-toast.busy .mud-tico{width:12px;height:12px;background:transparent;border:2px solid color-mix(in oklab,var(--brand,#2f7bf6) 30%,transparent);border-top-color:var(--brand,#2f7bf6);animation:mudspin .7s linear infinite}
@keyframes mudtoast-in{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:none}}
@keyframes mudtoast-out{to{opacity:0;transform:translateY(-8px)}}
@keyframes mudspin{to{transform:rotate(360deg)}}
.mud-toast.notify{flex-direction:row;align-items:center;max-width:340px;text-align:left;border-radius:calc(var(--radius-base,.5rem) + .375rem)}
.mud-toast.notify .mud-nb{display:flex;flex-direction:column;gap:2px;min-width:0}
.mud-toast.notify .mud-nb b{font-size:.82rem;font-weight:700}
.mud-toast.notify .mud-nb span{font-size:.76rem;color:var(--text-muted,var(--text-light,#888));overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.mud-progress.is-loading::before{content:'';display:inline-block;margin-right:6px;vertical-align:middle}
.mud-locks .mud-lock-heading{display:flex;align-items:center;gap:8px;min-width:0}
.mud-locks .mud-lock-heading::before{flex-shrink:0;margin-right:0}
.mud-locks .mud-heading-label{flex:1 1 auto;min-width:0}
/* Keep an identical title-side slot for idle, loading and errors. No row is
 * inserted or removed on each live AT poll, including on narrow screens. */
.mud-locks .mud-lock-progress{flex:0 0 11em;max-width:50%;min-width:0;height:1.4em;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.7rem;font-weight:400;letter-spacing:normal;text-align:right;color:var(--text-muted,var(--text-light,#777))}
.mud-locks .mud-lock-progress:empty{visibility:hidden}
.mud-locks .mud-hero .mud-heading-label{flex:0 1 auto}
.mud-locks .mud-hero .mud-lock-progress{text-align:left}
.mud-progress.is-loading::before,.mud-btn .mud-spin,.mud-lockbtn .mud-spin{flex:0 0 auto;width:12px;height:12px;border-radius:50%;border:2px solid color-mix(in oklab,currentColor 30%,transparent);border-top-color:currentColor;animation:mudspin .7s linear infinite}
.mud-btn.busy,.mud-lockbtn.busy{pointer-events:none;opacity:.75}
/* ---- 主题化对话框（替代浏览器 confirm/alert） ---- */
.mud-dlg-wrap{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.42);animation:mudfade-in .16s ease-out;padding:20px}
.mud-dlg{background:var(--surface,var(--background,#fff));border:1px solid var(--hairline,var(--border,#ddd));border-radius:calc(var(--radius-base,.5rem) + .5rem);box-shadow:0 18px 50px rgba(0,0,0,.28);max-width:420px;width:100%;padding:18px 20px 16px;animation:muddlg-in .2s cubic-bezier(.2,.9,.3,1.15)}
.mud-dlg h4{margin:0 0 8px;font-size:.95rem;font-weight:700;color:var(--text,#222)}
.mud-dlg .mud-dlg-msg{font-size:.84rem;line-height:1.6;color:var(--text-muted,var(--text-light,#666));white-space:pre-wrap;word-break:break-word}
.mud-dlg .mud-dlg-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:16px;flex-wrap:wrap}
/* 短信气泡的删除按钮：红色垃圾桶，平时隐淡、悬停显形；正文留出右侧空间防重叠 */
.mud-bub{position:relative;padding-right:28px}
.mud-del{position:absolute;top:2px;right:2px;display:flex;align-items:center;justify-content:center;width:24px;height:24px;padding:0;border:none;background:transparent;color:var(--danger,#E25555);opacity:.4;cursor:pointer;border-radius:50%}
.mud-del:hover{opacity:.9;background:color-mix(in oklab,var(--danger,#E25555) 12%,transparent)}
.mud-del svg{display:block}
/* 预览 -> 全文回填的过渡动画，消除首载的生硬跳变 */
@keyframes mudfadein{from{opacity:.25}to{opacity:1}}
.mud-bub .bd.fadein{animation:mudfadein .25s ease-out}
@keyframes muddlg-in{from{opacity:0;transform:scale(.94) translateY(10px)}to{opacity:1;transform:none}}
@keyframes mudfade-in{from{opacity:0}to{opacity:1}}
/* 手机端锁定页 hero：RSRP 数字左对齐（其余屏幕保持右对齐） */
@media(max-width:600px){
.mud-rsrp{text-align:left}}
`;

function qLabel(rsrp, rsrq, sinr) {
	if (rsrp == null && sinr == null && rsrq == null) return '未知';
	if (rsrp != null) {
		if (rsrp >= -90) return '优秀';
		if (rsrp >= -100) return '良好';
		if (rsrp >= -110) return '一般';
		return '较差';
	}
	if (sinr != null) {
		if (sinr >= 20) return '优秀';
		if (sinr >= 13) return '良好';
		if (sinr >= 0) return '一般';
		return '较差';
	}
	if (rsrq >= -8) return '优秀';
	if (rsrq >= -11) return '良好';
	if (rsrq >= -14) return '一般';
	return '较差';
}
function qCol(label) {
	switch (label) {
		case '优秀': return 'var(--success, #2FBF71)';
		case '良好': return 'color-mix(in oklab, var(--success, #7BC96F) 62%, var(--text, #444))';
		case '一般': return 'var(--warning, #F2B544)';
		case '较差': return 'var(--danger, #E25555)';
		default:     return 'var(--text-subtle, var(--text-light, #8A8F98))';
	}
}
/* 10 分制：RSRP 40% / RSRQ 25% / SINR 35%，锚点插值，缺项权重重分配 */
function interp(v, pts) {
	if (v == null) return null;
	for (var i = 0; i < pts.length - 1; i++)
		if (v <= pts[i][0])
			return pts[i][1] + (v - pts[i][0]) * (pts[i+1][1] - pts[i][1]) / (pts[i+1][0] - pts[i][0]);
	return pts[pts.length - 1][1];
}
function qScore(s) {
	var parts = [
		[ interp(s.rsrp, [ [ -120, 0 ], [ -110, 3.5 ], [ -100, 6.5 ], [ -90, 8.5 ], [ -80, 10 ] ]), 0.40 ],
		[ interp(s.rsrq, [ [ -20, 0 ], [ -14, 3.5 ], [ -11, 6.5 ], [ -8, 8.5 ], [ -3, 10 ] ]), 0.25 ],
		[ interp(s.sinr, [ [ -5, 0 ], [ 0, 3.5 ], [ 13, 6.5 ], [ 20, 8.5 ], [ 30, 10 ] ]), 0.35 ]
	];
	var sum = 0, w = 0;
	parts.forEach(function(p) { if (p[0] != null) { sum += p[0] * p[1]; w += p[1]; } });
	return w == 0 ? null : Math.max(0, Math.min(10, sum / w));
}


function fmtTrafficBytes(b) {
	if (b == null || b === '' || !Number.isFinite(Number(b)) || Number(b) < 0) return '--';
	b = Number(b);
	var u = [ 'B', 'KB', 'MB', 'GB', 'TB' ], i = 0;
	while (b >= 1000 && i < u.length - 1) { b /= 1000; i++; }
	var value = Number(b.toFixed(i === 0 ? 0 : 2));
	if (value >= 1000 && i < u.length - 1) { value = 1; i++; }
	return value + ' ' + u[i];
}

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function injectCss(){
 document.documentElement.classList.remove('mud-bootstrap-theme');
 const t=getComputedStyle(document.documentElement);
 document.documentElement.classList.toggle('mud-bootstrap-theme',!t.getPropertyValue('--surface').trim()&&!!t.getPropertyValue('--background-color-high').trim());
 if(document.getElementById('mud-style'))return;
 const s=document.createElement('style');s.id='mud-style';s.textContent=CSS+'\n.mud{min-width:0}.mud-cols>*{min-width:0}.mud-r .mud-v{overflow-wrap:anywhere}.mud-btn:disabled{opacity:.5;cursor:default}';document.head.append(s);
}
function confirmBox(title,message,opts={}){return new Promise(resolve=>{
 let done=false;const finish=yes=>{if(done)return;done=true;document.removeEventListener('keydown',escape);ui.hideModal();resolve(yes);};
 const escape=e=>{if(e.key==='Escape'){e.preventDefault();finish(false);}};
 document.addEventListener('keydown',escape);
 ui.showModal(title,[E('p',{},message),opts.content||E('span'),E('div',{'class':'right'},[
 E('button',{'class':'btn',click:()=>finish(false)},'取消'),E('button',{'class':'btn cbi-button-action',click:()=>finish(true)},opts.okText||'确认')])]);
});}
function toast(text,opts={}){
 const node=E('p',{},text),box=ui.addNotification(null,node,opts.type==='error'?'error':'info');
 const close=()=>{if(box?.remove)box.remove();};if(opts.timeout!==0)setTimeout(close,opts.timeout||4000);
 return {close,update(value){node.textContent=value;}};
}
const call=(method,params=[])=>rpc.declare({object:'luci.modem5g',method,params,nobatch:true,expect:{'':{}}});
return baseclass.extend({injectCss,esc,confirmBox,toast,fmtTrafficBytes,qLabel,qCol,qScore,
 translate:s=>s,localize:()=>{},localizeMenu:()=>{},simSelector:()=>{},busy:(b,on)=>{if(b)b.disabled=!!on;},
 callTrafficGet:call('traffic_get'),callTrafficSet:call('traffic_set',['payload']),callTrafficClear:call('traffic_clear',['confirm'])
});
