import { startAppearance } from './appearance.js'

const { invoke } = window.__TAURI__.core
const el = id => document.getElementById(id)
const phases = { loading:'正在读取服务状态',first:'开始使用 SimpleTavern',importing:'正在复制旧版数据',
  starting:'正在启动酒馆',running:'酒馆正在运行',waiting:'正在等待任务完成',stopping:'正在停止服务',
  stopped:'酒馆已停止',failed:'聊天服务未能运行',fatal:'管理器启动失败' }
let previousPhase, state, voicesKey, logKey, lastSeen = 0
let following = true
async function act(name, options = {}) {
  el('feedback').textContent = ''
  try { await invoke('action', { name, options }); }
  catch { el('feedback').textContent = '操作失败，请重新打开管理器' }
}
document.querySelectorAll('[data-action]').forEach(button => {
  button.onclick = () => { el('serviceMenu').open = false; act(button.dataset.action) }
})
function bind(id, title, action) {
  const btn = el(id)
  btn.hidden = !title
  if (title) { btn.textContent = title; btn.onclick = action }
}
el('copy').onclick = async () => {
  try { await navigator.clipboard.writeText(state.url); el('copy').textContent='已复制' }
  catch { const r=document.createRange(); r.selectNodeContents(el('url')); getSelection().removeAllRanges(); getSelection().addRange(r) }
}
el('ports').onsubmit = event => {
  event.preventDefault(); act('ports',{port:el('port').valueAsNumber,apiPort:el('apiPort').valueAsNumber})
}
function voiceRows() {
  const key = JSON.stringify(state.voices)
  if (key === voicesKey) return
  voicesKey = key
  el('voices').replaceChildren()
  for (const service of state.voices || []) {
    const row=document.createElement('div'); row.className='row'
    const label=document.createElement('strong'); label.textContent=service.name+' · '+service.provider
    const badge=document.createElement('span'); badge.className='badge'
    badge.textContent=({owned:'运行中',idle:'按需启动',external:'外部网关',external_ready:'外部运行',unreachable:'连接失败'})[service.state]
    row.append(label,badge)
    const actions = service.owned ? [['停止','stop']] : service.managed ? [['启动','start']] : []
    for (const [title,op] of [...actions,['检查连接','health']]) {
      const b=document.createElement('button'); b.className='btn btn-secondary'; b.textContent=title
      b.onclick=()=>{b.disabled=true; act('voice',{id:service.id,op}); setTimeout(()=>{b.disabled=false},1500)}
      row.append(b)
    }
    el('voices').append(row)
  }
}
function logView(force=false) {
  if (!el('logs').open || !state) return
  const list=(state.logs||[]).filter(item=>(el('source').selectedIndex===0||item.source===el('source').value)&&(!el('errors').checked||item.level==='错误'))
  const newest=list.at(-1)?.id||0
  const key=[newest,list.length,el('source').value,el('errors').checked].join('/')
  if(!following && !force) {
    const n=list.filter(row=>row.id>lastSeen).length
    el('follow').hidden=!n; el('follow').textContent='查看最新 '+n+' 条'; return
  }
  if(key===logKey&&!force)return
  logKey=key; lastSeen=newest
  const block=document.createDocumentFragment()
  for(const item of list) {
    const line=document.createElement('div'); if(item.level==='错误')line.className='error'
    line.textContent=[item.time,item.source,item.level,item.text].join('  ');block.append(line)
  }
  if (!list.length) {
    block.append(state.phase === 'first' ? '启动服务后，运行记录会显示在这里。' : '暂无符合条件的日志')
  }
  el('entries').replaceChildren(block)
  if(following)el('entries').scrollTop=el('entries').scrollHeight
  el('follow').hidden=true
}
function follow(value) { following=value; el('pause').textContent=value?'暂停滚动':'继续跟随'; logView(value) }
el('entries').onscroll=()=>{const box=el('entries');if(box.scrollTop+box.clientHeight<box.scrollHeight-5)follow(false)}
el('entries').onpointerdown=()=>follow(false)
el('pause').onclick=()=>follow(!following)
el('follow').onclick=()=>follow(true)
el('errors').onchange=el('source').onchange=el('logs').ontoggle=()=>logView(true)

function render(next) {
  state=next; const p=state.phase
  el('status').textContent=phases[p]||phases.loading
  el('detail').textContent=state.detail||''
  el('trayTip').hidden=!state.trayTip
  el('address').hidden=p!=='running'
  el('url').textContent=state.url||''
  el('serviceState').textContent=({running:'运行中',first:'待启动',failed:'失败',starting:'启动中',stopped:'已停止',waiting:'等待中',stopping:'停止中'})[p]||'准备中'
  el('serviceMenu').hidden=p!=='running'
  const primary=({first:['开始使用','start'],running:['打开聊天','open'],failed:['重新启动','start'],stopped:['启动服务','start']})[p]
  bind('primary',primary?.[0],()=>act(primary[1]))
  bind('secondary',state.waiting?'继续运行':p==='first'?'导入旧版数据':null,()=>act(state.waiting?'cancel':'import'))
  el('ports').hidden=!['failed','stopped'].includes(p)
  if(previousPhase!==p) {
    el('port').value=state.port||9081; el('apiPort').value=state.apiPort||9091
    if(p==='failed'){el('logs').open=true;el('errors').checked=true;el('source').value='聊天服务';follow(true)}
  }
  previousPhase=p
  voiceRows(); logView()
  const u=state.update||{}
  el('version').textContent=u.version?'v'+u.version:''
  el('updateMessage').textContent=u.message||''
  const up=({available:['退出时更新','download'],ready:['立即重启更新','restart'],waiting:['取消重启','cancel'],idle:['检查更新','check'],error:['重试检查','check']})[u.phase]
  bind('update',up?.[0],()=>act(up[1]))
}
async function tick() {
  try {render(await invoke('snapshot'))}
  catch {el('feedback').textContent='无法读取管理器状态'}
  setTimeout(tick,500)
}
tick()
startAppearance().catch(error => {
  console.error('Unable to initialize manager appearance', error)
  el('feedback').textContent = '无法读取管理器外观'
})
