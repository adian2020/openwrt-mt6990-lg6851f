'use strict';
'require view';
'require rpc';
'require ui';

const read = rpc.declare({object: 'luci.lg6851f-led', method: 'get_status', expect: {}});
const update = rpc.declare({
	object: 'luci.lg6851f-led', method: 'set_mode',
	params: ['key', 'mode', 'color', 'interval'], expect: {}
});
const modes = {auto: '自动', on: '开启', off: '熄灭', blink: '闪烁'};
const colors = {green: '绿色', blue: '蓝色', red: '红色'};
const intervals = {250: '0.25 秒', 500: '0.5 秒', 1000: '1 秒'};

function optionSelect(label, values, current, labels, disabledValues = []) {
	const select = E('select', { 'class': 'cbi-input-select', 'aria-label': label },
		values.map(value => E('option', { value, disabled: disabledValues.includes(value) ? '' : null }, labels[value])));
	select.value = current;
	return select;
}

return view.extend({
	load: read,
	render(data) {
		const rows = E('div', {'class': 'cbi-section'});
		const message = E('p', { role: 'status' });
		const paint = status => {
			rows.replaceChildren(...(status.leds || []).map(led => {
				const mode = optionSelect(led.label + '模式', Object.keys(modes), led.mode, modes,
					led.blink_available ? [] : ['blink']);
				const color = optionSelect(led.label + '颜色', led.colors, led.color, colors);
				const rate = optionSelect(led.label + '闪烁间隔', Object.keys(intervals), led.interval, intervals);
				const availability = () => {
					mode.disabled = !led.available;
					color.disabled = !led.available || led.colors.length < 2 || !['on', 'blink'].includes(mode.value);
					rate.disabled = !led.available || mode.value !== 'blink';
				};
				mode.addEventListener('change', availability);
				availability();
				const apply = E('button', {
					type: 'button', class: 'btn cbi-button cbi-button-apply', disabled: led.available ? null : '',
					click: ui.createHandlerFn(this, async () => {
						message.textContent = '';
						const result = await update(led.key, mode.value, color.value, +rate.value);
						if (result.status) paint(result.status);
						message.textContent = result.success ? '已保存 ' + led.label + ' 指示灯设置' : result.error || '灯光设置失败';
					})
				}, '应用');
				const active = (led.active_colors || []).map(value => colors[value]).join('、');
				return E('section', {class: 'cbi-value'}, [
					E('label', {class: 'cbi-value-title'}, led.label),
					E('div', {class: 'cbi-value-field'}, [
						E('div', {style: 'display:flex; flex-wrap:wrap; align-items:center; gap:.4rem'}, [mode, color, rate, apply]),
						E('div', {class: 'cbi-value-description'}, !led.available ? '驱动接口未就绪' :
							active ? active + (led.blinking ? '闪烁' : '亮起') : '当前熄灭')
					])
				]);
			}));
		};
		paint(data);
		return E('div', [E('h2', '灯光控制'), rows, data.supported ? null : E('p', '灯光控制接口未就绪'), message]);
	},
	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
