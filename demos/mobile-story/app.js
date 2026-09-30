const $ = (selector) => document.querySelector(selector);
const esc = (value = '') => String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const avatar = (id, small = false) => `<span class="avatar${small ? ' small' : ''}" data-person="${esc(id)}" aria-hidden="true">${esc(state.people[id]?.name.slice(0, 1) || '我')}</span>`;
const storageKey = 'simpletavern-mobile-story-demo-v1';
const makeId = (prefix) => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

const examples = {
  version: 1,
  activeStory: 'tide', activeChat: 'lighthouse',
  model: '演示模型 · 平衡', connection: '演示连接', readingSize: '15',
  drafts: {}, setup: { connection: false, model: false, person: false, personId: null },
  people: {
    aiwen: { name: '艾文', subtitle: '夜航的信使', text: '艾文常在夜色中穿过港口，替不愿露面的人送信。他穿着深色旧外套，随身携带一只银色指南针。\n\n他待人温和，但总习惯先观察，再回答。谈到过去时，他会用一个问题转开话题。灯塔是他在雾中辨认方向的地方，也是他一直不肯提起的旧事。\n\n这份人物原稿可以自由写作，外貌、性格与经历不必强行拆成表格。', persona: '深色旧外套，银色指南针。只保留外貌与服饰，由我自行演绎。', opening: '今晚的灯塔，好像没有亮。' },
    lin: { name: '林汐', subtitle: '收集旧书的人', text: '林汐经营一家很小的旧书店。她记得每一本书从哪里来，却很少谈起自己。\n\n她喜欢把落在书里的票根与信件收起来，相信那些未说完的话终有一天会找到收信人。', persona: '宽松衬衫，墨绿色围裙，指尖常沾着墨迹。', opening: '你来得正好，我在一本旧书里找到了这个。' },
    keeper: { name: '守灯人', subtitle: '北境的老旅人', text: '守灯人已经离开海岸很多年。他记得星图与旧航路，手里总拿着一盏不会熄灭的小灯。\n\n他习惯用朴素、简短的句子说话。对陌生人谨慎，对同行的人却十分可靠。', persona: '灰色披风，旧皮靴，手提一盏小灯。', opening: '路还很长，但天亮之前能走到。' },
  },
  stories: [
    { id: 'tide', name: '潮汐来信', color: '#a6d2be', symbol: 'moon', people: ['aiwen'], identity: '旅人', scene: '雾港 · 旧灯塔', goal: '找到失踪的守灯人', worldBook: true, modelOverride: '',
      memory: '你与艾文在雾港相遇，决定一起寻找失踪的守灯人。\n\n守灯人最后出现于旧码头。他留下了一枚铜钥匙，钥匙柄上刻着潮汐的标记。艾文认出了这个记号，却暂时没有解释。\n\n你们已经约定：抵达灯塔之前，不向港口的巡夜人透露此行目的。',
      events: ['在旧码头发现铜钥匙。', '艾文答应一起前往灯塔。'],
      chats: [
        { id: 'lighthouse', name: '灯塔熄灭之后', scene: '雾港 · 旧灯塔', goal: '找到失踪的守灯人', messages: [
          { id: 't1', role: 'assistant', person: 'aiwen', text: '雾比刚才更浓了。艾文停在堤岸边，抬头看向远处。\n\n“今晚的灯塔没有亮。”他把那枚铜钥匙递给你，“我们最好在潮水回来之前过去。”' },
          { id: 't2', role: 'user', text: '我接过钥匙。你以前来过这里吗？' },
          { id: 't3', role: 'assistant', person: 'aiwen', variant: 0, versions: ['他没有立刻回答，只把外套的领口拢紧了一些。\n\n“来过。很久以前。”\n\n海风吹过堤岸，带来铁锈与潮湿石头的气味。他看了你一眼，终于笑了笑。\n\n“如果你愿意听，路上我可以慢慢讲。”', '艾文望着那座熄灭的灯塔，手指无意识地摩挲着指南针。\n\n“来过。”他说，“不过上一次，我是一个人。”\n\n他转过身，把靠海的一侧留给自己。“走吧。这次的故事也许会不同。”'], text: '他没有立刻回答，只把外套的领口拢紧了一些。\n\n“来过。很久以前。”\n\n海风吹过堤岸，带来铁锈与潮湿石头的气味。他看了你一眼，终于笑了笑。\n\n“如果你愿意听，路上我可以慢慢讲。”' },
        ] },
        { id: 'wharf', name: '码头的约定', scene: '雾港 · 旧码头', goal: '寻找守灯人留下的线索', messages: [{ id: 't4', role: 'assistant', person: 'aiwen', text: '艾文从码头的缝隙里捡起一枚铜钥匙。\n\n“看这个记号。”他把钥匙转向灯光，“也许我们找对地方了。”' }] },
      ] },
    { id: 'summer', name: '折页里的夏天', color: '#cfb8e4', symbol: 'feather', people: ['lin'], identity: '访客', scene: '雨天 · 旧书店', goal: '寻找一封信的收信人', worldBook: false, modelOverride: '',
      memory: '你在旧书店认识了林汐。一本诗集里夹着没有署名的信，信中提到了夏天的站台。你们决定查找诗集的旧主人。\n\n这段经历属于「折页里的夏天」，与雾港的故事互相独立。', events: ['在诗集里找到一封信。'],
      chats: [{ id: 'letter', name: '一封没有署名的信', scene: '雨天 · 旧书店', goal: '寻找一封信的收信人', messages: [
        { id: 's1', role: 'assistant', person: 'lin', text: '雨水顺着书店的玻璃缓缓滑落。林汐从诗集里抽出一张薄薄的信纸。\n\n“没有名字，也没有地址。”她把信放在你面前，“只写着：如果你还记得那个夏天。”' },
        { id: 's2', role: 'user', text: '能看看这本书最早是谁卖来的吗？' },
        { id: 's3', role: 'assistant', person: 'lin', text: '“当然。”她拉开柜台最下面的抽屉，拿出一本边角磨损的册子。\n\n“但先说好，如果找到了，你得陪我去见他。”' },
      ] }] },
    { id: 'north', name: '越过北境', color: '#dfc18a', symbol: 'compass', people: ['aiwen', 'keeper'], identity: '同行者', scene: '北境 · 雪线', goal: '在天亮前抵达山口', worldBook: false, modelOverride: '',
      memory: '这是一段独立的旅途。同样有艾文参与，但没有继承「潮汐来信」的经历。\n\n你们跟随守灯人前往山口，途中发现远处有一处废弃驿站。', events: ['在雪线发现一处旧驿站。'],
      chats: [{ id: 'snow', name: '雪线上的同行者', scene: '北境 · 雪线', goal: '在天亮前抵达山口', messages: [
        { id: 'n1', role: 'assistant', person: 'keeper', text: '守灯人把小灯举高了一点。雪地里，三个人的脚印渐渐被风掩去。\n\n“翻过前面那道山脊，就能看见驿站。今晚在那里休息。”' },
        { id: 'n2', role: 'assistant', person: 'aiwen', text: '艾文走到你身旁，指了指远处一闪而过的灯光。\n\n“那里似乎还有别人。”' },
      ] }] },
  ],
};

let state = structuredClone(examples);
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
  if (saved?.version === 1 && Array.isArray(saved.stories) && saved.people && saved.drafts && saved.setup && saved.stories.some((story) => story.id === saved.activeStory && story.chats.some((chat) => chat.id === saved.activeChat))) state = saved;
} catch { /* The demo also works without browser storage. */ }

let views = [];
let composeDraft = null;
let firstRun = false;
let pending = null;
let replyTimer;
let toastTimer;
let returnFocus;
let historyQuery = '';
let personFilter = 'all';
let storyFilter = 'all';
let scrollPositions = {};
const currentStory = () => state.stories.find((story) => story.id === state.activeStory);
const currentChat = () => currentStory().chats.find((chat) => chat.id === state.activeChat);
const chatPeople = (story, chat) => chat.people ?? story.people;
const currentSession = () => {
  const story = currentStory();
  const chat = currentChat();
  return { ...story, people: chatPeople(story, chat), identity: chat.identity ?? story.identity, worldBook: chat.worldBook ?? story.worldBook, modelOverride: chat.modelOverride || '' };
};
const effectiveModel = () => currentChat().modelOverride || state.model;
state.tasks ||= {};
for (const story of state.stories) for (const chat of story.chats) for (const message of chat.messages) if (message.role === 'user' && !message.identity) message.identity = chat.identity ?? story.identity;
const persist = () => { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch { /* Optional persistence. */ } };
const names = (ids) => ids.map((id) => state.people[id]?.name).filter(Boolean).join('、') || '自由写作';
const formField = (label, id, value, { help = '', rows = 2, long = false } = {}) => `<label class="field" for="${id}"><span>${label}</span><textarea id="${id}" rows="${rows}"${long ? ' class="long-text"' : ''}>${esc(value)}</textarea>${help ? `<small>${help}</small>` : ''}</label>`;
const row = (action, label, subtitle, symbol = 'chevron', extra = '') => `<button class="summary-row" data-action="${action}" ${extra}><div class="person-copy"><strong>${label}</strong><small>${subtitle}</small></div>${icon(symbol)}</button>`;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 2600);
}

function renderMain(scroll = false) {
  const story = currentSession();
  const chat = currentChat();
  $('#device').style.setProperty('--story', story.color);
  $('#device').style.setProperty('--reading-size', `${state.readingSize}px`);
  $('#context-summary').hidden = firstRun;
  $('.composer-area').hidden = firstRun;
  if (firstRun) {
    $('#chat-header').innerHTML = `<button class="icon-button" data-action="return-demo" aria-label="回到示例故事">${icon('back')}</button><div class="heading-copy"><strong>第一次打开</strong><small>基础配置就能开始</small></div>`;
    $('#conversation').innerHTML = `<div class="welcome"><h2>从一个人物，<br>开始你的第一段故事。</h2><p>添加一个连接，选好模型，再写下人设。<br>开场白和其他资料都可以以后再加。</p></div>
      <button class="setup-step" data-action="connection"><span class="step-index">${state.setup.connection ? icon('check') : '1'}</span><div class="person-copy"><strong>添加连接</strong><small>${state.setup.connection ? esc(state.connection) : '填写服务地址与密钥的位置'}</small></div>${icon('chevron')}</button>
      <button class="setup-step" data-action="global-model"><span class="step-index">${state.setup.model ? icon('check') : '2'}</span><div class="person-copy"><strong>选择模型</strong><small>${state.setup.model ? esc(state.model) : '选择一个可用的聊天模型'}</small></div>${icon('chevron')}</button>
      <button class="setup-step" data-action="create-person"><span class="step-index">${state.setup.person ? icon('check') : '3'}</span><div class="person-copy"><strong>创建人物</strong><small>${state.setup.person ? esc(state.people[state.setup.personId]?.name) : '名字、人设，以及可选开场白'}</small></div>${icon('chevron')}</button>
      <button class="primary" style="width:100%;margin-top:26px" data-action="start-first"${Object.values(state.setup).slice(0, 3).every(Boolean) ? '' : ' disabled'}>开始聊天</button><p class="help">这三项可以按任意顺序完成。Demo 中保存的是示例配置。</p><button class="text-button" data-action="return-demo">直接看看已有故事</button>`;
    return;
  }
  $('#chat-header').innerHTML = `<button class="icon-button" data-action="history" aria-label="打开故事与会话历史" aria-haspopup="dialog">${icon('menu')}</button><button class="story-heading" data-action="context"><span class="story-mark">${icon(story.symbol)}</span><span class="heading-copy"><strong>${esc(chat.name)}</strong><small>${esc(story.name)}</small></span></button><button class="memory-button" data-action="memory" aria-label="查看故事记忆">${icon('book')}<span>记忆</span></button>`;
  $('#context-summary').innerHTML = `<span class="avatar-stack">${story.people.slice(0, 2).map((id) => avatar(id, true)).join('') || icon('feather')}</span><span class="context-copy"><strong>${esc(chat.scene || '自由开场')} · ${esc(chat.goal || '随心继续')}</strong><small>${esc(names(story.people))} × ${esc(story.identity || '我')} · 点开查看情境</small></span>${icon('chevron')}`;
  $('#conversation').innerHTML = chat.messages.length ? `<p class="scene-intro">${esc(chat.scene || '故事从这里开始')}</p>${chat.messages.map(renderMessage).join('')}` : `<div class="empty-chat">${icon(story.symbol)}<h2>这一段，由你开场。</h2><p>${esc(names(story.people))}已经在这里。<br>${esc(chat.scene || '写下第一句话，故事就会开始。')}</p><button class="text-button" data-action="compose">${icon('plus')} 调整人物与情境</button></div>`;
  $('#composer-meta').innerHTML = `<button data-action="model">${esc(effectiveModel())} · ${story.modelOverride ? '本会话设置' : '沿用默认'}${icon('chevron')}</button>`;
  $('#message-input').value = state.drafts[chat.id] || '';
  updateComposer();
  if (scroll) $('#conversation').scrollTop = $('#conversation').scrollHeight;
  else $('#conversation').scrollTop = scrollPositions[chat.id] || 0;
}

function renderMessage(message) {
  const user = message.role === 'user';
  const name = user ? message.identity || currentSession().identity || '我' : state.people[message.person]?.name || '叙述';
  return `<article class="message ${user ? 'user' : 'assistant'}" aria-label="${esc(name)}的消息"><div class="message-header">${user ? '' : avatar(message.person || 'self')}<span>${esc(name)}</span></div><p class="message-body">${esc(message.text || '正在写下回应…')}</p>${!user && message.text ? `<div class="message-tools"><button data-action="edit-message" data-id="${esc(message.id)}" aria-label="编辑这条回复">${icon('edit')}修订</button><button data-action="rewrite" data-id="${esc(message.id)}" aria-label="换一种示例回复">${icon('refresh')}改写</button>${message.versions ? `<button data-action="version" data-id="${esc(message.id)}">版本 ${(message.variant || 0) + 1}/${message.versions.length}</button>` : ''}</div>` : ''}</article>`;
}

function updateComposer() {
  const input = $('#message-input');
  input.style.height = 'auto';
  input.style.height = `${Math.min(110, Math.max(44, input.scrollHeight))}px`;
  $('#send-button').disabled = !pending && !input.value.trim();
  $('#send-button').setAttribute('aria-label', pending ? '停止示例回复' : '发送消息');
  $('#send-button').innerHTML = icon(pending ? 'stop' : 'arrow');
  $('#generation-state').textContent = pending ? '正在演示回复 · 可随时停止' : '';
}

function prepareComposition(independent = false) {
  const story = currentSession();
  composeDraft = { sourceChat: state.activeChat, mode: independent ? 'independent' : 'continue', people: [...story.people], identity: story.identity, scene: currentChat().scene, goal: currentChat().goal, name: '', worldBook: story.worldBook };
}

function openView(kind, params = {}, replace = false) {
  if (!views.length) returnFocus = document.activeElement;
  if (replace) views = [];
  views.push({ kind, params });
  renderSheet();
}

function backView() {
  views.pop();
  renderSheet();
}

function closeViews() {
  views = [];
  renderSheet();
}

function renderSheet() {
  const layer = $('#sheet-layer');
  const hasViews = views.length > 0;
  layer.hidden = !hasViews;
  $('#app-content').inert = hasViews;
  $('.preview-guide').inert = hasViews;
  if (!hasViews) {
    layer.innerHTML = '';
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    else $('#message-input').focus({ preventScroll: true });
    return;
  }
  const view = views.at(-1);
  const content = panelContent(view);
  layer.dataset.kind = view.kind;
  layer.innerHTML = `<button class="scrim" data-action="close" aria-label="关闭面板" tabindex="-1"></button><section class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" tabindex="-1"><div class="sheet-handle" aria-hidden="true"></div><header class="sheet-heading">${views.length > 1 ? `<button class="icon-button" data-action="back" aria-label="返回上一层">${icon('back')}</button>` : ''}<div class="heading-text"><h2 id="sheet-title">${content.title}</h2><small>${content.scope}</small></div><button class="icon-button" data-action="close" aria-label="关闭面板">${icon('close')}</button></header><div class="sheet-body">${content.body}</div>${content.footer ? `<footer class="sheet-footer">${content.footer}</footer>` : ''}</section>`;
  $('.sheet').focus({ preventScroll: true });
}

function panelContent(view) {
  const story = currentSession();
  const chat = currentChat();
  const primary = (action, label) => `<button class="primary" data-action="${action}">${label}</button>`;
  switch (view.kind) {
    case 'compose': {
      const draft = composeDraft;
      return { title: '组合这一次的故事', scope: draft.mode === 'continue' ? `继续「${esc(story.name)}」` : '复用人物，开启独立经历',
        body: `<div class="segmented" aria-label="故事连续性"><button data-action="compose-mode" data-mode="continue" aria-pressed="${draft.mode === 'continue'}">继续故事</button><button data-action="compose-mode" data-mode="independent" aria-pressed="${draft.mode === 'independent'}">独立开场</button></div><p class="scope-note">${draft.mode === 'continue' ? '保留这段故事已有的经历，只调整当前会话的情境。' : '带上人物资料，从空白记忆开始。原来的故事仍会保留。'}</p><h3 class="section-title">谁在这里</h3>${Object.entries(state.people).map(([id, person]) => `<div class="person-option"><label class="person-label"><input type="checkbox" data-field="person" value="${esc(id)}"${draft.people.includes(id) ? ' checked' : ''}>${avatar(id)}<span class="person-copy"><strong>${esc(person.name)}</strong><small>${esc(person.subtitle)}</small></span></label><button class="text-button" data-action="profile" data-id="${esc(id)}">资料</button></div>`).join('')}<label class="field" for="identity"><span>我来扮演</span><select id="identity" data-field="identity">${[...new Set([draft.identity, '旅人', '我自己', '林汐 · 仅外貌与服饰', '不指定身份'])].map((name) => `<option${name === draft.identity ? ' selected' : ''}>${esc(name)}</option>`).join('')}</select><small>身份是可选的，不用先写一份我方人设。</small></label>${draft.mode === 'independent' ? `<label class="field" for="story-name"><span>故事名 <small>可选</small></span><input id="story-name" data-field="name" value="${esc(draft.name)}" placeholder="留空就用场景命名" maxlength="60"></label>` : ''}${formField('发生在哪里', 'scene', draft.scene)}${formField('这次想发生什么', 'goal', draft.goal)}<details><summary>需要时，再加入资料</summary><label class="check-row"><input type="checkbox" data-field="world-book"${draft.worldBook ? ' checked' : ''}>港城手札 · 用于这次会话</label><p class="help">可选资料。无需配置资料也能开始。</p></details>`,
        footer: primary('apply-composition', draft.mode === 'continue' ? '应用到当前会话' : '开始独立故事') };
    }
    case 'history': return { title: '故事与会话', scope: '按人物找回，按故事延续',
      body: `<label class="search-box">${icon('search')}<span class="sr-only">搜索故事或会话</span><input id="history-search" placeholder="搜索故事或会话" value="${esc(historyQuery)}"></label><div class="filter-row" aria-label="人物筛选"><button class="chip" data-action="filter-person" data-id="all" aria-pressed="${personFilter === 'all'}">全部人物</button>${Object.entries(state.people).map(([id, person]) => `<button class="chip" data-action="filter-person" data-id="${esc(id)}" aria-pressed="${personFilter === id}">${esc(person.name)}</button>`).join('')}</div><div class="filter-row" aria-label="故事筛选"><button class="chip" data-action="filter-story" data-id="all" aria-pressed="${storyFilter === 'all'}">全部故事</button>${state.stories.map((item) => `<button class="chip" data-action="filter-story" data-id="${esc(item.id)}" aria-pressed="${storyFilter === item.id}" style="--story:${item.color}">${icon(item.symbol)}${esc(item.name)}</button>`).join('')}</div><div id="history-results">${historyResults()}</div><div class="history-navigation"><button data-action="library">${icon('person')}人物与资料</button><button data-action="settings">${icon('settings')}应用设置</button><button data-action="first-run">${icon('arrow')}看看首次使用</button></div>`,
      footer: `<button class="secondary" data-action="new-chat">新会话 · 继续故事</button>${primary('new-story', '独立开场')}` };
    case 'context': return { title: '此刻的情境', scope: `${esc(story.name)} · 当前会话`,
      body: `<h3 class="section-title">人物与身份</h3>${story.people.map((id) => `<button class="summary-row" data-action="profile" data-id="${esc(id)}">${avatar(id)}<span class="person-copy"><strong>${esc(state.people[id]?.name)}</strong><small>使用人物资料 · ${esc(state.people[id]?.subtitle)}</small></span>${icon('chevron')}</button>`).join('')}<div class="summary-row">${avatar('self')}<span class="person-copy"><strong>${esc(story.identity || '我')}</strong><small>我来扮演</small></span></div>${row('compose', '人物、场景与目标', `${esc(chat.scene)} · ${esc(chat.goal)}`)}<h3 class="section-title">这段故事带着什么</h3>${row('memory', '故事记忆', story.memory ? '已有经历 · 只在这条故事内延续' : '空白记忆 · 独立的经历', 'book')}${row('model', esc(effectiveModel()), story.modelOverride ? '已单独设置 · 仅当前会话' : '沿用应用默认 · 可以单独设置')}${row('materials', '本次使用的资料', story.worldBook ? '港城手札 · 已启用' : '没有加入资料')}<p class="help">人物资料可以复用；故事经历按故事分开保存。点人物筛选历史，不会合并他们的记忆。</p>`, footer: primary('context-compose', '调整当前组合') };
    case 'memory': return { title: '故事记忆', scope: `属于「${esc(story.name)}」 · 本故事内延续`,
      body: `<p class="scope-note">换一个聊天窗口仍可继续这些经历。独立开场会从空白记忆开始。</p>${formField('已经发生的事', 'memory-text', view.params.draft ?? story.memory, { rows: 8, help: '你可以直接修订这份记忆。这个 Demo 不会自动总结。' })}<h3 class="section-title">最近的经历</h3><ul class="memory-events">${story.events.length ? story.events.map((event, i) => `<li>${esc(event)}<small>故事记录 ${i + 1}</small></li>`).join('') : '<li>还没有记录，从第一句话开始。</li>'}</ul>`, footer: primary('save-memory', '保存故事记忆') };
    case 'model':
    case 'global-model': {
      const global = view.kind === 'global-model';
      const model = global ? state.model : effectiveModel();
      return { title: global ? '默认聊天模型' : '这次用哪个模型', scope: global ? '应用默认 · 未单独指定的会话使用' : '只调整当前会话，下次回复使用',
        body: `<p class="scope-note">${esc(state.connection)} · 示例模型列表</p>${['演示模型 · 平衡', '演示模型 · 创作'].map((name) => `<button class="choice-row" data-action="choose-model" data-id="${name}" data-scope="${global ? 'global' : 'chat'}" aria-pressed="${model === name}"><span class="person-copy"><strong>${name}</strong><small>${esc(state.connection)}</small></span>${icon(model === name ? 'check' : 'chevron')}</button>`).join('')}${!global ? row('inherit-model', '恢复沿用应用默认', esc(state.model), 'refresh') : ''}<p class="help">这是可切换的界面示例，发送消息使用预写的演示回复。</p>`, footer: '' };
    }
    case 'library': return { title: '人物与资料', scope: '可复用的原稿 · 与故事记忆分开',
      body: `<p class="scope-note">完整保留人物原稿，再为不同用途准备版本。无需先把长文拆成许多字段。</p>${Object.entries(state.people).map(([id, person]) => `<button class="summary-row" data-action="profile" data-id="${esc(id)}">${avatar(id)}<span class="person-copy"><strong>${esc(person.name)}</strong><small>${esc(person.subtitle)}</small></span>${icon('chevron')}</button>`).join('')}`,
      footer: primary('create-person', '创建一个人物') };
    case 'profile': {
      const person = state.people[view.params.id];
      return { title: esc(person.name), scope: '人物资料 · 复用于不同故事',
        body: `<div class="summary-row">${avatar(view.params.id)}<span class="person-copy"><strong>${esc(person.subtitle)}</strong><small>编辑这里，会更新 Demo 中的共享人物资料。</small></span></div>${formField('人物原稿', 'person-text', view.params.draft ?? person.text, { rows: 9, long: true })}<details><summary>不同用途的版本</summary>${formField('用作我的身份', 'persona-text', view.params.persona ?? person.persona, { rows: 3, help: '这是一份明确保存的独立版本，不会自动删改原稿。' })}</details>`,
        footer: `<button class="secondary" data-action="use-person" data-id="${esc(view.params.id)}">用来独立开场</button>${primary('save-person', '保存人物资料')}` };
    }
    case 'create-person': return { title: '创建人物', scope: '先写基础人设，更多内容以后再加',
      body: `<label class="field" for="person-name"><span>人物名字</span><input id="person-name" maxlength="30" required placeholder="怎么称呼这个人物？" value="${esc(view.params.name || '')}"></label>${formField('人设', 'new-person-text', view.params.text || '', { rows: 6, help: '可以是一句话，也可以是完整的长文。' })}${formField('开场白 · 可选', 'new-person-opening', view.params.opening || '')}`,
      footer: primary('save-new-person', '保存人物') };
    case 'settings': return { title: '应用设置', scope: '应用默认 · 与当前故事设置分开',
      body: `<div class="settings-group"><h3>开始聊天</h3>${row('connection', '模型与连接', `${esc(state.connection)} · ${esc(state.model)}`)}</div><div class="settings-group"><h3>阅读与创作</h3>${row('reading', '外观与交互', `深色 · 正文字号 ${esc(state.readingSize)}`)}${row('defaults', '对话与创作', '按任务组织回复、标题与总结')}${row('library', '人物与资料', `${Object.keys(state.people).length} 位人物 · 自由原稿`)}</div><div class="settings-group"><h3>更深入</h3>${row('extensions', '工具与扩展', '需要时再启用')}${row('data', '数据与应用', '演示数据 · 保存在这个浏览器')}</div>`, footer: '' };
    case 'connection': return { title: '模型与连接', scope: '应用默认 · 演示配置',
      body: `<label class="field" for="connection-name"><span>连接名称</span><input id="connection-name" maxlength="50" value="${esc(view.params.name ?? state.connection)}" required></label><p class="help">正式版会在这里填写服务地址与密钥。当前演示无需密钥，不建立真实连接。</p>${row('global-model', '默认聊天模型', esc(state.model))}`, footer: primary('save-connection', '保存示例连接') };
    case 'reading': return { title: '外观与交互', scope: '应用偏好 · 即时预览',
      body: `<label class="field" for="reading-size"><span>正文字号</span><select id="reading-size"><option${state.readingSize === '14' ? ' selected' : ''}>14</option><option${state.readingSize === '15' ? ' selected' : ''}>15</option><option${state.readingSize === '17' ? ' selected' : ''}>17</option></select></label><p class="message-body" id="reading-preview" style="margin-top:24px;font-size:${esc(state.readingSize)}px">海风吹过堤岸，带来铁锈与潮湿石头的气味。故事继续，正文始终留得安静。</p><p class="help">字号应用到 Demo 的聊天正文。动效跟随系统的减少动态效果设置。</p>`, footer: '' };
    case 'materials': return { title: '本次使用的资料', scope: '当前会话 · 可选',
      body: `<label class="check-row"><input id="active-world-book" type="checkbox"${story.worldBook ? ' checked' : ''}>港城手札</label><p class="help">雾港的地名、航路与灯塔背景。这里展示会话里加入资料的位置与状态。</p><details><summary>查看资料内容</summary><p class="help">雾港每逢涨潮便被浓雾笼罩。旧灯塔曾为夜航者指路，如今由一位守灯人照料。</p></details>`, footer: primary('save-materials', '保存当前资料选择') };
    case 'edit-message': return { title: '修订这条回复', scope: '只修改这一条消息', body: formField('回复正文', 'edited-message', view.params.draft, { rows: 10, long: true }), footer: primary('save-message', '保存修订') };
    case 'defaults': return { title: '对话与创作', scope: '应用默认 · 任务配置示意', body: `${row('task-reply', '默认回复', '模型、回复长度与生成参数一起调整')}${row('task-title', '标题生成', '开关、模型和标题要求放在同一处')}${row('task-memory', '记忆总结', '触发策略、模型和总结要求放在同一处')}<p class="help">这几页演示层级与返回位置，选项不参与真实生成。</p>`, footer: '' };
    case 'task': {
      const task = view.params.task ||= structuredClone(state.tasks[view.params.title] || { enabled: true, model: '沿用默认聊天模型', instructions: '用简洁的语言保留故事中的重要信息。' });
      return { title: esc(view.params.title), scope: '应用默认 · 示例任务设置', body: `<label class="check-row"><input id="task-enabled" type="checkbox"${task.enabled ? ' checked' : ''}>启用此任务</label><label class="field" for="task-model"><span>使用模型</span><select id="task-model">${['沿用默认聊天模型', '演示模型 · 创作'].map((model) => `<option${model === task.model ? ' selected' : ''}>${model}</option>`).join('')}</select></label>${formField('任务要求', 'task-instructions', task.instructions)}<p class="help">任务相关选项放在同一页。这个 Demo 展示配置组织方式。</p>`, footer: primary('save-task', '保存示例设置') };
    }
    case 'extensions': return { title: '工具与扩展', scope: '应用能力 · 按需发现', body: `<p class="scope-note">基础聊天不依赖扩展。需要时，再来这里了解与管理。</p>${row('extension-tools', '工具', '给特定任务使用的能力')}${row('extension-skills', '技能与提示模板', '保存可复用的创作方法')}${row('extension-workspace', '工作区', '文件与资料的独立管理空间')}`, footer: '' };
    case 'extension-detail': return { title: esc(view.params.title), scope: '扩展入口示意 · 默认不启用', body: `<p class="scope-note">这是「${esc(view.params.title)}」的管理位置，后续可以从这里加入、编辑和分配给具体任务。</p><p class="help">当前 Demo 只呈现分层入口。返回后仍然回到刚才的扩展列表。</p>`, footer: '' };
    case 'data': return { title: '数据与应用', scope: '仅此 Demo 的虚构数据', body: `${row('export-demo', '导出这份演示', '下载人物、故事和修改过的示例内容')}${row('first-run', '首次使用预览', '保留已有示例，看看基础配置路径')}<p class="help">演示修改保存在这个浏览器，不会写入 SimpleTavern 的正式数据。</p>`, footer: '' };
    default: return { title: '返回故事', scope: '', body: '', footer: primary('close', '返回') };
  }
}

function historyResults() {
  const matches = state.stories.map((story) => ({ story, chats: story.chats.filter((chat) => `${story.name} ${chat.name} ${chat.scene} ${names(chatPeople(story, chat))}`.toLowerCase().includes(historyQuery.toLowerCase()) && (personFilter === 'all' || chatPeople(story, chat).includes(personFilter))) })).filter(({ story, chats }) => chats.length && (storyFilter === 'all' || story.id === storyFilter));
  return matches.length ? matches.map(({ story, chats }) => `<section class="story-group" style="--story:${story.color}"><button class="story-group-heading" data-action="filter-story" data-id="${esc(story.id)}">${icon(story.symbol)}<span>${esc(story.name)}</span><small>${story.chats.length} 段会话</small></button><div class="chapter-chain">${chats.map((chat) => `<button class="chapter-row" data-action="open-chat" data-story="${esc(story.id)}" data-id="${esc(chat.id)}" aria-current="${chat.id === state.activeChat}"><strong>${esc(chat.name)}</strong><p>${esc(names(chatPeople(story, chat)))} · ${esc(chat.scene || '自由开场')}</p>${chat.id === state.activeChat ? '<small>正在这里</small>' : ''}</button>`).join('')}</div></section>`).join('') : '<p class="scope-note">没有找到相符的会话。试试其他关键词，或点“全部人物”“全部故事”。</p>';
}

function applyComposition() {
  stopReply(false);
  const draft = composeDraft;
  if (draft.mode === 'independent') {
    const symbol = ['moon', 'feather', 'compass'][state.stories.length % 3];
    const color = ['#a6d2be', '#cfb8e4', '#dfc18a'][state.stories.length % 3];
    const chat = { id: makeId('chat'), name: '新的开场', scene: draft.scene, goal: draft.goal, messages: [] };
    const story = { id: makeId('story'), name: draft.name.trim() || draft.scene.trim() || '未命名故事', symbol, color, people: [...draft.people], identity: draft.identity, scene: draft.scene, goal: draft.goal, memory: '', events: [], worldBook: draft.worldBook, modelOverride: '', chats: [chat] };
    state.stories.unshift(story);
    state.activeStory = story.id;
    state.activeChat = chat.id;
    if (draft.people.length === 1 && state.people[draft.people[0]].opening) chat.messages.push({ id: makeId('message'), role: 'assistant', person: draft.people[0], text: state.people[draft.people[0]].opening });
    toast('独立故事已开始，记忆从空白开始。');
  } else {
    currentChat().people = [...draft.people];
    currentChat().identity = draft.identity;
    currentChat().worldBook = draft.worldBook;
    currentChat().scene = draft.scene;
    currentChat().goal = draft.goal;
    toast('当前组合已更新，原有故事经历保留。');
  }
  firstRun = false;
  composeDraft = null;
  persist();
  closeViews();
  renderMain(true);
}

function stopReply(showToast = true) {
  if (!pending) return;
  clearTimeout(replyTimer);
  const chat = state.stories.find((story) => story.id === pending.story)?.chats.find((item) => item.id === pending.chat);
  const message = chat?.messages.find((item) => item.id === pending.message);
  if (message && !message.text) chat.messages = chat.messages.filter((item) => item.id !== message.id);
  pending = null;
  persist();
  renderMain(true);
  if (showToast) toast('已停止，已经出现的文字会保留。');
}

function syntheticReply(story, chat) {
  const person = story.people[0];
  if (person === 'lin') return { person, text: '林汐把那封信小心地折好，夹回书页。\n\n“那就一起去看看吧。”她拿起门边的伞，“有些故事，只有走出去才能知道下一页。”' };
  if (story.id === 'tide') return { person, text: '艾文点了点头，与你并肩向灯塔走去。\n\n“那枚钥匙，原本属于我的一位朋友。”他轻声说，“我一直以为，今晚会等到他的回信。”\n\n潮声渐近，远处的门缝里，忽然透出一点微弱的光。' };
  return { person, text: `${person ? `${state.people[person]?.name || '同行的人'}停下脚步，看向你。` : '故事有了新的起点。'}\n\n${chat.scene ? `在「${chat.scene}」里，` : ''}你刚才的回应让这一刻有了新的方向。${chat.goal ? `关于「${chat.goal}」的线索，正在前方等待。` : '还未写下的经历，可以从这里慢慢展开。'}\n\n“那么，我们继续吧。”` };
}

function sendMessage(event) {
  event.preventDefault();
  if (pending) { stopReply(); return; }
  const input = $('#message-input');
  const text = input.value.trim();
  if (!text) return;
  const story = currentSession();
  const chat = currentChat();
  chat.messages.push({ id: makeId('message'), role: 'user', text, identity: story.identity });
  state.drafts[chat.id] = '';
  if (chat.name === '新的开场' || chat.name === '新的一段') chat.name = text.slice(0, 12) + (text.length > 12 ? '…' : '');
  const reply = syntheticReply(story, chat);
  const message = { id: makeId('message'), role: 'assistant', person: reply.person, text: '' };
  chat.messages.push(message);
  pending = { story: story.id, chat: chat.id, message: message.id };
  input.value = '';
  renderMain(true);
  let step = 0;
  function reveal() {
    if (!pending) return;
    step += 1;
    message.text = reply.text.slice(0, Math.ceil(reply.text.length * step / 3));
    if (step >= 3) { pending = null; persist(); }
    renderMain(true);
    if (pending) replyTimer = setTimeout(reveal, 450);
  }
  replyTimer = setTimeout(reveal, 500);
  persist();
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  const id = button.dataset.id;
  const view = views.at(-1);
  switch (action) {
    case 'close': closeViews(); break;
    case 'back': backView(); break;
    case 'history': openView('history', {}, true); break;
    case 'context': openView('context', {}, true); break;
    case 'context-compose': prepareComposition(); openView('compose'); break;
    case 'compose': if (!composeDraft || composeDraft.sourceChat !== state.activeChat) prepareComposition(); openView('compose', {}, views.length === 0); break;
    case 'new-story': prepareComposition(true); openView('compose', {}, true); break;
    case 'compose-mode': composeDraft.mode = button.dataset.mode; renderSheet(); break;
    case 'apply-composition': applyComposition(); break;
    case 'memory': openView('memory'); break;
    case 'save-memory': currentStory().memory = $('#memory-text').value; persist(); backView(); toast('故事记忆已保存。'); break;
    case 'filter-person': personFilter = id; renderSheet(); break;
    case 'filter-story': storyFilter = storyFilter === id && id !== 'all' ? 'all' : id; renderSheet(); break;
    case 'open-chat': stopReply(false); scrollPositions[state.activeChat] = $('#conversation').scrollTop; state.activeStory = button.dataset.story; state.activeChat = id; firstRun = false; persist(); closeViews(); renderMain(); break;
    case 'new-chat': {
      stopReply(false);
      const session = currentSession();
      const chat = { id: makeId('chat'), name: '新的一段', scene: currentChat().scene, goal: currentChat().goal, people: [...session.people], identity: session.identity, worldBook: session.worldBook, modelOverride: session.modelOverride, messages: [] };
      currentStory().chats.unshift(chat); state.activeChat = chat.id; persist(); closeViews(); renderMain(); toast('新会话已开始，继续这条故事的记忆。'); break;
    }
    case 'model': openView('model'); break;
    case 'global-model': openView('global-model'); break;
    case 'choose-model': if (button.dataset.scope === 'global') { state.model = id; state.setup.model = true; } else currentChat().modelOverride = id; persist(); renderMain(); backView(); toast(button.dataset.scope === 'global' ? '应用默认模型已更新。' : '已为当前会话单独设置模型。'); break;
    case 'inherit-model': currentChat().modelOverride = ''; persist(); renderMain(); backView(); toast('当前会话已恢复沿用默认。'); break;
    case 'profile': openView('profile', { id }); break;
    case 'library': openView('library'); break;
    case 'save-person': state.people[view.params.id].text = $('#person-text').value; state.people[view.params.id].persona = $('#persona-text').value; persist(); toast('共享人物资料已保存。'); break;
    case 'use-person': prepareComposition(true); composeDraft.people = [id]; openView('compose', {}, true); break;
    case 'create-person': openView('create-person'); break;
    case 'save-new-person': {
      const input = $('#person-name');
      if (!input.value.trim()) { input.setCustomValidity('请给人物起一个名字。'); input.reportValidity(); break; }
      const newId = makeId('person');
      state.people[newId] = { name: input.value.trim(), text: $('#new-person-text').value, opening: $('#new-person-opening').value, persona: '', subtitle: '新写下的人物原稿' };
      state.setup.person = true; state.setup.personId = newId; persist(); backView(); renderMain(); toast('人物已保存，可以开始聊天。'); break;
    }
    case 'settings': openView('settings'); break;
    case 'connection': openView('connection'); break;
    case 'save-connection': if ($('#connection-name').value.trim()) { state.connection = $('#connection-name').value.trim(); state.setup.connection = true; persist(); backView(); renderMain(); toast('示例连接已保存。'); } else { $('#connection-name').setCustomValidity('请填写连接名称。'); $('#connection-name').reportValidity(); } break;
    case 'materials': openView('materials'); break;
    case 'save-materials': currentChat().worldBook = $('#active-world-book').checked; persist(); backView(); toast('当前会话的资料选择已保存。'); break;
    case 'reading': openView('reading'); break;
    case 'edit-message': { const message = currentChat().messages.find((item) => item.id === id); openView('edit-message', { id, draft: message.text }); break; }
    case 'save-message': { const message = currentChat().messages.find((item) => item.id === view.params.id); message.text = $('#edited-message').value; if (message.versions) message.versions[message.variant || 0] = message.text; persist(); renderMain(); backView(); toast('这条回复已修订。'); break; }
    case 'rewrite':
    case 'version': {
      if (pending) { toast('先停止当前回复，再切换消息版本。'); break; }
      const message = currentChat().messages.find((item) => item.id === id);
      if (!message.versions) message.versions = [message.text, syntheticReply(currentSession(), currentChat()).text];
      message.variant = ((message.variant || 0) + 1) % message.versions.length; message.text = message.versions[message.variant]; persist(); renderMain(); toast(`已切换到示例版本 ${message.variant + 1}。`); break;
    }
    case 'first-run': stopReply(false); firstRun = true; closeViews(); renderMain(); break;
    case 'return-demo': firstRun = false; closeViews(); renderMain(); break;
    case 'start-first': prepareComposition(true); composeDraft.people = [state.setup.personId]; composeDraft.scene = ''; composeDraft.goal = ''; composeDraft.name = `${state.people[state.setup.personId].name}的故事`; composeDraft.worldBook = false; applyComposition(); break;
    case 'defaults': openView('defaults'); break;
    case 'task-reply': openView('task', { title: '默认回复' }); break;
    case 'task-title': openView('task', { title: '标题生成' }); break;
    case 'task-memory': openView('task', { title: '记忆总结' }); break;
    case 'save-task': state.tasks[view.params.title] = { enabled: $('#task-enabled').checked, model: $('#task-model').value, instructions: $('#task-instructions').value }; persist(); toast('示例设置已保存，仅用于展示页面层级。'); backView(); break;
    case 'extensions': openView('extensions'); break;
    case 'extension-tools': openView('extension-detail', { title: '工具' }); break;
    case 'extension-skills': openView('extension-detail', { title: '技能与提示模板' }); break;
    case 'extension-workspace': openView('extension-detail', { title: '工作区' }); break;
    case 'data': openView('data'); break;
    case 'export-demo': {
      const link = document.createElement('a');
      const url = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }));
      link.href = url; link.download = 'simpletavern-demo.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Demo 数据已导出。'); break;
    }
  }
});

document.addEventListener('input', (event) => {
  const input = event.target;
  const view = views.at(-1);
  if (input.id === 'message-input') { state.drafts[state.activeChat] = input.value; persist(); updateComposer(); }
  if (input.id === 'history-search') { historyQuery = input.value; $('#history-results').innerHTML = historyResults(); }
  if (view?.kind === 'compose') {
    if (input.dataset.field === 'person') composeDraft.people = [...document.querySelectorAll('[data-field="person"]:checked')].map((item) => item.value);
    if (input.dataset.field === 'identity') composeDraft.identity = input.value;
    if (input.dataset.field === 'name') composeDraft.name = input.value;
    if (input.dataset.field === 'world-book') composeDraft.worldBook = input.checked;
    if (input.id === 'scene') composeDraft.scene = input.value;
    if (input.id === 'goal') composeDraft.goal = input.value;
  }
  if (view?.kind === 'memory' && input.id === 'memory-text') view.params.draft = input.value;
  if (view?.kind === 'profile' && input.id === 'person-text') view.params.draft = input.value;
  if (view?.kind === 'profile' && input.id === 'persona-text') view.params.persona = input.value;
  if (view?.kind === 'create-person') { if (input.id === 'person-name') { view.params.name = input.value; input.setCustomValidity(''); } if (input.id === 'new-person-text') view.params.text = input.value; if (input.id === 'new-person-opening') view.params.opening = input.value; }
  if (view?.kind === 'connection' && input.id === 'connection-name') { view.params.name = input.value; input.setCustomValidity(''); }
  if (view?.kind === 'edit-message' && input.id === 'edited-message') view.params.draft = input.value;
  if (view?.kind === 'task') { if (input.id === 'task-instructions') view.params.task.instructions = input.value; if (input.id === 'task-enabled') view.params.task.enabled = input.checked; if (input.id === 'task-model') view.params.task.model = input.value; }
});

document.addEventListener('change', (event) => {
  if (event.target.id === 'reading-size') { state.readingSize = event.target.value; persist(); $('#reading-preview').style.fontSize = `${state.readingSize}px`; renderMain(); }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && views.length) { event.preventDefault(); backView(); }
  if (event.key === 'Tab' && views.length) {
    const focusable = [...$('.sheet').querySelectorAll('button:not(:disabled), input, textarea, select, summary, [tabindex="0"]')].filter((element) => element.getClientRects().length);
    const first = focusable[0]; const last = focusable.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === $('.sheet'))) { event.preventDefault(); last?.focus(); }
    if (!event.shiftKey && (document.activeElement === last || document.activeElement === $('.sheet'))) { event.preventDefault(); first?.focus(); }
  }
  if (event.target.id === 'message-input' && event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!$('#send-button').disabled) $('#message-form').requestSubmit(); }
});

$('#conversation').addEventListener('scroll', () => { if (!firstRun) scrollPositions[state.activeChat] = $('#conversation').scrollTop; });
$('#message-form').addEventListener('submit', sendMessage);
renderMain(true);
