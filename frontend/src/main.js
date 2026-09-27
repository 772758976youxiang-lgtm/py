import './style.css';
import { createIcons, PanelLeft, SquarePen, Search, Sparkles, Upload, Settings2, ChevronRight, FileCode2, Download, Trash2, Terminal, Eraser, Square, Play, MessageSquareX, SlidersHorizontal, ArrowUp, X, Cpu, Database, Sun, Moon, Monitor, Plus, Archive, BookOpen, Unplug, ArrowUpRight, Settings, PlayCircle, ChevronDown } from 'lucide';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { api, connect } from './api.js';
import { dictionaries } from './i18n.js';
hljs.registerLanguage('python', python);
const $ = id => document.getElementById(id);
const icons = {PanelLeft,SquarePen,Search,Sparkles,Upload,Settings2,ChevronRight,FileCode2,Download,Trash2,Terminal,Eraser,Square,Play,MessageSquareX,SlidersHorizontal,ArrowUp,X,Cpu,Database,Sun,Moon,Monitor,Plus,Archive,BookOpen,Unplug,ArrowUpRight,Settings,PlayCircle,ChevronDown};
const iconize = () => createIcons({icons});
const state = {notes:[], active:null, settings:{language:'zh',theme:'system',fontSize:13.5,tabSize:4,timeout:30}, providers:[], dirty:new Map(),
  saving:false, settingsDirty:false, settingsSaving:false, messages:[], pendingChat:null, run:null, runCode:'', runNote:null, editingProvider:null, ready:false};
const t = key => dictionaries[state.settings.language]?.[key] ?? dictionaries.zh[key] ?? key;
const esc = value => String(value).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const activeNote = () => state.notes.find(n=>n.id===state.active);
let toastTimer, saveTimer, settingsTimer, pollTimer;
function toast(text) { $('toast').textContent=text; $('toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),6000); }
function fail(error) { toast(error.message || String(error)); }
function handle(id, event, fn) { $(id).addEventListener(event, async e=>{try{await fn(e);}catch(error){fail(error);}}); }
function confirmAction(title,message) {
  $('confirm-title').textContent=title; $('confirm-message').textContent=message;
  const dialog=$('confirm-dialog'); dialog.showModal();
  return new Promise(resolve=>{
    const finish=value=>{dialog.close();$('confirm-yes').onclick=null;$('confirm-no').onclick=null;dialog.oncancel=null;resolve(value);};
    $('confirm-yes').onclick=()=>finish(true);$('confirm-no').onclick=()=>finish(false);dialog.oncancel=e=>{e.preventDefault();finish(false);};
  });
}
function date(value, short=false) {
  const d=new Date(value);
  if(state.settings.language==='zh')return short?`${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`:`${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日 ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  return new Intl.DateTimeFormat('en-US',short?{hour:'2-digit',minute:'2-digit'}:{dateStyle:'medium',timeStyle:'short'}).format(d);
}
function applySettings() {
  const s=state.settings;
  document.documentElement.lang=s.language==='zh'?'zh-CN':'en';
  document.documentElement.dataset.theme=s.theme==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):s.theme;
  document.documentElement.style.setProperty('--editor-font-size',`${s.fontSize}px`);
  document.documentElement.style.setProperty('--editor-line-height',`${Math.round(s.fontSize*1.75)}px`);
  document.documentElement.style.setProperty('--tab-size',s.tabSize);$('editor').style.tabSize=s.tabSize; $('highlight').style.tabSize=s.tabSize;
  document.querySelectorAll('[data-zh]').forEach(el=>el.textContent=el.dataset[s.language==='zh'?'zh':'en']);
  document.querySelectorAll('[data-placeholder-zh]').forEach(el=>el.placeholder=el.dataset[s.language==='zh'?'placeholderZh':'placeholderEn']);
  document.querySelectorAll('[data-t]').forEach(el=>el.textContent=t(el.dataset.t));
  document.querySelectorAll('[data-placeholder]').forEach(el=>el.placeholder=t(el.dataset.placeholder));
  document.querySelectorAll('[data-title]').forEach(el=>{el.title=t(el.dataset.title);el.setAttribute('aria-label',t(el.dataset.title));});
  $('setting-language').value=s.language;$('setting-font').value=s.fontSize;$('font-value').textContent=Number(s.fontSize).toFixed(1);
  $('setting-tab').value=s.tabSize;$('setting-timeout').value=s.timeout;
  document.querySelectorAll('.theme-options [data-theme]').forEach(el=>{el.classList.toggle('active',el.dataset.theme===s.theme);el.setAttribute('aria-pressed',String(el.dataset.theme===s.theme));el.classList.toggle('border-2',el.dataset.theme===s.theme);el.classList.toggle('border',el.dataset.theme!==s.theme);el.classList.toggle('border-gray-900',el.dataset.theme===s.theme);el.classList.toggle('border-gray-200',el.dataset.theme!==s.theme);});
  $('indent-label').textContent=`${s.tabSize} ${t('spaces')}`;
  if(state.ready){$('connection').innerHTML=`<b></b><span>${t('online')}</span>`;renderNotes();renderProviders();renderChat();setSaveStatus();if(state.run)renderRun(state.run);}
  iconize();
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if(state.settings.theme==='system')applySettings();});
function settingsChanged(patch) {
  Object.assign(state.settings,patch);state.settingsDirty=true;applySettings();
  clearTimeout(settingsTimer);settingsTimer=setTimeout(saveSettings,250);
}
async function saveSettings() {
  if(state.settingsSaving)return;
  state.settingsSaving=true;
  try{
    while(state.settingsDirty){
      const snapshot=JSON.stringify(state.settings);
      await api('/settings',{method:'PUT',body:JSON.parse(snapshot)});
      if(JSON.stringify(state.settings)===snapshot)state.settingsDirty=false;
    }
  }catch(e){toast(`${t('settingsFailed')} ${e.message}`);}finally{state.settingsSaving=false;}
}
function renderNotes() {
  const query=$('search').value.toLowerCase();
  const notes=state.notes.filter(n=>(n.title+'\n'+n.content).toLowerCase().includes(query));
  $('note-count').textContent=`${state.notes.length} ${t('scriptCount')}`;
  let lastDay='';
  $('note-list').innerHTML=notes.map(n=>{
    const day=new Date(n.updated_at).toLocaleDateString();
    const group=day!==lastDay?`<div class="notes-group">${day===new Date().toLocaleDateString()?(state.settings.language==='zh'?'今天':'Today'):esc(day)}</div>`:'';lastDay=day;
    const lines=n.content.split('\n').filter(l=>l.trim());
    const title=n.title===t('newTitle')?(lines[0]?.replace(/^[#\s]+/,'')||t('newTitle')):n.title;
    return group+`<button class="note-item ${n.id===state.active?'active':''}" data-id="${n.id}" aria-current="${n.id===state.active?'page':'false'}"><strong>${esc(title)}</strong><small><time>${esc(date(n.updated_at,true))}</time><span class="snippet">${esc(lines[1]?.trim()||(state.settings.language==='zh'?'无更多文本':'No additional text'))}</span></small></button>`;
  }).join('') || `<p class="text-center text-xs text-gray-400 p-4">${t(state.notes.length?'noMatch':'noNotes')}</p>`;
  $('note-list').querySelectorAll('button').forEach(b=>{b.onclick=()=>selectNote(b.dataset.id).catch(fail);b.oncontextmenu=async e=>{e.preventDefault();await selectNote(b.dataset.id);showContextMenu(e);};});
  if(activeNote())$('note-date').textContent=date(activeNote().updated_at);
}
async function selectNote(id) {
  state.active=id;
  const note=activeNote();
  $('editor').value=note?.content||'';$('note-title').value=note?.title||'';
  $('editor').disabled=!note;$('note-title').disabled=!note;
  for(const control of ['export-note','delete-note','send'])$(control).disabled=!note;
  $('run').disabled=!note||state.run?.status==='running';
  $('editor').scrollTop=0;$('editor').scrollLeft=0;
  state.messages=[];renderNotes();updateEditor();setSaveStatus();renderChat();
  if(innerWidth<768)$('left-panel').classList.add('collapsed');
  if(note){
    const messages=await api(`/notes/${id}/messages`);
    if(state.active===id){state.messages=messages;renderChat();}
  }
}
function updateEditor() {
  const text=$('editor').value;
  $('highlight').innerHTML=hljs.highlight(text+(text.endsWith('\n')?' ':''),{language:'python'}).value;
  $('gutter').textContent=Array.from({length:Math.max(1,text.split('\n').length)},(_,i)=>i+1).join('\n');
  syncScroll();updateCursor();
}
function syncScroll(){ $('highlight').scrollTop=$('editor').scrollTop;$('highlight').scrollLeft=$('editor').scrollLeft;$('gutter').scrollTop=$('editor').scrollTop; }
function updateCursor(){const before=$('editor').value.slice(0,$('editor').selectionStart).split('\n');$('cursor').textContent=`Ln ${before.length}, Col ${before.at(-1).length+1}`;}
function editNote(){
  const note=activeNote();if(!note)return;
  note.content=$('editor').value;note.title=$('note-title').value.trim()||t('newTitle');note.updated_at=new Date().toISOString();
  state.dirty.set(note.id,(state.dirty.get(note.id)||0)+1);updateEditor();renderNotes();setSaveStatus();
  clearTimeout(saveTimer);saveTimer=setTimeout(flushNotes,500);
}
function setSaveStatus(){
  $('save-status').textContent=t(state.saving?'saving':state.dirty.has(state.active)?'unsaved':'saved');
  $('save-status').style.color=state.dirty.has(state.active)?'#ba8b40':'';
  $('note-date').title=$('save-status').textContent;
}
let savePromise=Promise.resolve(true);
function flushNotes(){
  if(state.saving)return savePromise;
  state.saving=true;setSaveStatus();
  savePromise=(async()=>{
    try{
      while(state.dirty.size){
        const [id,version]=state.dirty.entries().next().value;const note=state.notes.find(n=>n.id===id);
        if(!note){state.dirty.delete(id);continue;}
        const saved=await api(`/notes/${id}`,{method:'PUT',body:{title:note.title,content:note.content,revision:note.revision}});
        note.revision=saved.revision;
        if(state.dirty.get(id)===version){state.dirty.delete(id);note.updated_at=saved.updated_at;}
      }
      return true;
    }catch(e){toast(`${t('saveFailed')} ${e.message}`);return false;}
    finally{state.saving=false;setSaveStatus();renderNotes();}
  })();return savePromise;
}
async function createNote(content='',title=t('newTitle')){
  const note=await api('/notes',{method:'POST',body:{title,content}});state.notes.unshift(note);$('search').value='';await selectNote(note.id);$('editor').focus();
}
function download(name,text,type='text/plain'){
  const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function exportCurrent(){const n=activeNote();if(n)download(n.title.replace(/[\\/:*?"<>|]/g,'_').replace(/\.py$/,'')+'.py',n.content);}
async function backup(){
  // Export in-memory edits too, including those that could not be saved.
  const data={version:1,exported_at:new Date().toISOString(),notes:state.notes.map(n=>({title:n.title,content:n.content}))};
  download(`python-scripts-${new Date().toISOString().slice(0,10)}.json`,JSON.stringify(data,null,2),'application/json');toast(t('backupDone'));
}
async function importFiles(files){
  const notes=[];let total=0;
  for(const file of files){
    total+=file.size;if(total>8*1024*1024)throw new Error(t('fileTooBig'));
    const text=await file.text();
    if(file.name.toLowerCase().endsWith('.py'))notes.push({title:file.name.replace(/\.py$/i,'').slice(0,120)||t('newTitle'),content:text});
    else {
      let data;try{data=JSON.parse(text);}catch{throw new Error(t('importInvalid'));}
      const rows=Array.isArray(data)?data:data.notes;
      if(!Array.isArray(rows))throw new Error(t('importInvalid'));
      for(const n of rows){if(!n||typeof n.content!=='string')throw new Error(t('importInvalid'));notes.push({title:String(n.title||t('newTitle')).slice(0,120),content:n.content});}
    }
  }
  if(!notes.length)return;
  const result=await api('/import',{method:'POST',body:{notes}});
  const fresh=await api('/notes');
  // Merge server additions without replacing unsaved local edits.
  const known=new Set(state.notes.map(n=>n.id));state.notes.unshift(...fresh.filter(n=>!known.has(n.id)));
  $('search').value='';await selectNote(result.ids[0]);toast(`${t('imported')} (${notes.length})`);
}
function updateModels(){
  $('chat-provider').innerHTML=state.providers.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')||`<option value="">${t('noProvider')}</option>`;
  if(state.providers.some(p=>p.id===state.settings.providerId))$('chat-provider').value=state.settings.providerId;
  else $('chat-provider').value='';
  $('chat-model').value=state.settings.model||'';
  const p=state.providers.find(p=>p.id===$('chat-provider').value);
  $('model-options').innerHTML=(p?.models||[]).map(m=>`<option value="${esc(m)}"></option>`).join('');
}
function renderProviders(){
  $('provider-list').innerHTML=state.providers.map(p=>`<div class="provider-card"><div><strong>${esc(p.name)}</strong><span class="provider-dot"></span></div><button data-id="${esc(p.id)}">${t('edit')}</button></div>`).join('');
  $('provider-list').querySelectorAll('button').forEach(b=>b.onclick=()=>openProvider(b.dataset.id));
}
function openProvider(id=null){
  state.editingProvider=id;const p=state.providers.find(p=>p.id===id);
  $('provider-form-title').textContent=t(id?'editProvider':'addProvider');$('provider-id').value=p?.id||'';$('provider-id').disabled=!!id;
  $('provider-name').value=p?.name||'';$('provider-url').value=p?.url||'';$('provider-protocol').value=p?.protocol||'openai-chat';
  $('provider-key').value='';$('provider-clear-key').checked=false;$('provider-models').value=p?.models.join('\n')||'';
  $('provider-list-view').classList.add('hidden');$('provider-form').classList.remove('hidden');$('provider-name').focus();$('delete-provider').classList.toggle('hidden',!id);$('fetch-provider-models').disabled=!id;$('save-provider').textContent=id?t('save'):(state.settings.language==='zh'?'创建提供商':'Create provider');
}
function closeProvider(){state.editingProvider=null;$('provider-key').value='';$('provider-form').classList.add('hidden');$('provider-list-view').classList.remove('hidden');}
function openSettings(tab='general'){
  setTab(tab);if(!$('settings-dialog').open)$('settings-dialog').showModal();
}
function setTab(tab){
  document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.classList.toggle('bg-gray-200/70',b.dataset.tab===tab);b.classList.toggle('text-gray-900',b.dataset.tab===tab);b.classList.toggle('text-gray-600',b.dataset.tab!==tab);});
  document.querySelectorAll('.tab-panel').forEach(el=>el.classList.toggle('hidden',el.id!==`tab-${tab}`));
}
function chatBubble(role, content){
  const bubble=document.createElement('div');bubble.className=`bubble ${role}`;
  if(role==='user'){bubble.textContent=content;return bubble;}
  bubble.innerHTML=DOMPurify.sanitize(marked.parse(content,{breaks:true}),{FORBID_TAGS:['img','style','form','input','button','iframe']});
  bubble.querySelectorAll('a').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer';});
  bubble.querySelectorAll('pre>code').forEach(code=>{
    const raw=code.textContent;
    if(code.classList.contains('language-python'))code.innerHTML=hljs.highlight(raw,{language:'python'}).value;
    const actions=document.createElement('div');actions.className='code-actions';
    const copy=document.createElement('button');copy.textContent=t('copy');copy.onclick=()=>navigator.clipboard.writeText(raw).then(()=>toast(t('copied'))).catch(fail);
    const insert=document.createElement('button');insert.textContent=t('insert');insert.onclick=async()=>{
      if(!activeNote())return;
      if($('editor').value.trim()&&!await confirmAction(t('replaceTitle'),t('replaceHint')))return;
      $('editor').value=raw;editNote();$('editor').focus();
    };
    actions.append(copy,insert);code.parentElement.before(actions);
  });return bubble;
}
function renderChat(){
  const container=$('chat-messages');container.replaceChildren();
  for(const m of state.messages)container.append(chatBubble(m.role,m.content));
  if(state.pendingChat?.id===state.active){
    container.append(chatBubble('user',state.pendingChat.message));
    const loading=document.createElement('div');loading.className='thinking';loading.textContent=t('thinking');container.append(loading);
  }
  $('send').disabled=!!state.pendingChat||!state.active;$('clear-chat').disabled=state.pendingChat?.id===state.active;
  container.scrollTop=container.scrollHeight;iconize();
}
async function sendChat(message=$('chat-input').value.trim(), codeOverride){
  if(!message||!state.active||state.pendingChat)return;
  const id=state.active;const provider=state.providers.find(p=>p.id===$('chat-provider').value);
  if(!provider){openSettings('providers');toast(t('noProvider'));return;}
  const model=$('chat-model').value.trim();if(!model){openUtility();$('chat-model').focus();toast(t('modelRequired'));return;}
  if(!provider.has_key&&!/^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(?=[:/]|$)/.test(provider.url)){openSettings('providers');openProvider(provider.id);toast(t('keyMissing'));return;}
  const code=codeOverride??($('attach-code').checked?activeNote().content:'');
  state.pendingChat={id,message};$('chat-input').value='';renderChat();
  try{
    const result=await api(`/notes/${id}/chat`,{method:'POST',body:{message,code,provider_id:provider.id,model}});
    if(state.active===id)state.messages=result.messages;
  }catch(e){
    if(state.active===id&&!$('chat-input').value)$('chat-input').value=message;
    toast(`${t('chatFailed')}: ${e.message}`);
  }finally{state.pendingChat=null;renderChat();}
}
function renderRun(job){
  state.run=job;
  const running=job.status==='running';
  $('clear-output').disabled=running;
  $('run').disabled=running||!state.active;$('stop').classList.toggle('hidden',!running);$('stdin-form').classList.toggle('hidden',!running||job.stdin_closed);
  $('terminal-hint').classList.add('hidden');$('stdout').textContent=job.stdout;
  let suffix='';if(job.status==='timeout')suffix=t('runTimeoutHint');if(job.status==='output_limit')suffix=t('runOutputHint');if(job.status==='stopped')suffix=t('runStoppedHint');
  $('stderr').textContent=job.stderr+(suffix?'\n'+suffix:'');
  $('run-status').classList.remove('hidden');
  $('run-status').textContent=`${t(job.status==='timeout'?'timeoutStatus':job.status)} · ${job.duration.toFixed(1)}s`;
  $('explain-error').classList.toggle('hidden',!['error','timeout','output_limit'].includes(job.status));
}
async function pollRun(){
  if(!state.run||state.run.status!=='running')return;
  try{
    const output=$('terminal-output');const atBottom=output.scrollHeight-output.scrollTop-output.clientHeight<45;
    const job=await api(`/runs/${state.run.id}`);renderRun(job);if(atBottom)output.scrollTop=output.scrollHeight;
    if(job.status==='running')pollTimer=setTimeout(pollRun,250);
  }catch(e){
    if(e.status===404){renderRun({...state.run,status:'error',stderr:state.run.stderr+'\n'+e.message});return;}
    toast(t('runLost'));$('run-status').textContent=t('runLost');pollTimer=setTimeout(pollRun,2500);
  }
}
async function runCode(){
  if(state.run?.status==='running')return;
  const code=$('editor').value;if(!code.trim()){toast(t('blankCode'));return;}
  $('run').disabled=true;
  try{
    state.runCode=code;state.runNote=state.active;
    const job=await api('/runs',{method:'POST',body:{code,timeout:state.settings.timeout,note_id:state.active}});
    renderRun(job);clearTimeout(pollTimer);pollRun();
  }catch(e){$('run').disabled=false;throw e;}
}
const examples={
  hello:`# 变量与输出 / Variables and output\nname = "Python"\nlearning_days = 7\n\nprint(f"你好，{name}！")\nprint(f"这是学习的第 {learning_days} 天。")\n\n# 试一试：修改变量，再运行一次\nfor day in range(1, 4):\n    print(f"Day {day}: 每天进步一点点")\n`,
  loop:`# 循环与列表 / Loops and lists\nscores = [85, 92, 78, 96, 88]\n\nfor index, score in enumerate(scores, start=1):\n    print(f"第 {index} 次成绩：{score}")\n\naverage = sum(scores) / len(scores)\nprint(f"平均分：{average:.1f}")\nprint("高于平均分：", [s for s in scores if s > average])\n`,
  input:`# 点击运行，然后在终端底部输入内容\n# Click Run, then type in the terminal input below.\nname = input("你的名字 / Your name: ")\nprint(f"你好，{name}！")\n\ntry:\n    age = int(input("你的年龄 / Your age: "))\n    print(f"明年你就 {age + 1} 岁了。")\nexcept ValueError:\n    print("请输入整数 / Please enter an integer.")\n`,
  function:`# 函数与异常 / Functions and exceptions\ndef divide(a, b):\n    if b == 0:\n        raise ValueError("除数不能为零 / Cannot divide by zero")\n    return a / b\n\nfor divisor in [2, 0, 5]:\n    try:\n        result = divide(10, divisor)\n        print(f"10 / {divisor} = {result}")\n    except ValueError as error:\n        print(f"提示：{error}")\n`
};
handle('new-note','click',()=>createNote());
handle('search','input',renderNotes);
handle('editor','input',editNote);handle('note-title','input',editNote);
handle('editor','scroll',syncScroll);handle('editor','click',updateCursor);handle('editor','keyup',updateCursor);
handle('save-status','click',async()=>{await flushNotes();if(state.settingsDirty)await saveSettings();});
handle('export-note','click',exportCurrent);handle('backup','click',backup);
handle('delete-note','click',async()=>{
  const note=activeNote();if(!note)return;
  if(!await confirmAction(t('deleteTitle'),`${note.title}\n${t('deleteHint')}`))return;
  // Finish an in-flight write before deleting to avoid a late save recreating dirty state.
  await savePromise;
  await api(`/notes/${note.id}`,{method:'DELETE'});state.dirty.delete(note.id);state.notes=state.notes.filter(n=>n.id!==note.id);
  await selectNote(state.notes[0]?.id||null);
});
for(const id of ['import-note','restore'])handle(id,'click',()=>$('file-input').click());
handle('file-input','change',async e=>{try{await importFiles(e.target.files);}finally{e.target.value='';}});
handle('toggle-left','click',()=>{$('left-panel').classList.toggle('collapsed');if(innerWidth<768)$('right-panel').classList.add('collapsed');});
handle('toggle-right','click',()=>{$('right-panel').classList.toggle('collapsed');if(innerWidth<768)$('left-panel').classList.add('collapsed');});
handle('open-settings','click',()=>openSettings());handle('configure-ai','click',()=>{$('utility-dialog').close();openSettings('providers');});
handle('close-settings','click',()=>{saveSettings();$('settings-dialog').close();closeProvider();});
$('settings-dialog').addEventListener('close',()=>{saveSettings();closeProvider();});
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
document.querySelectorAll('.theme-options [data-theme]').forEach(b=>b.onclick=()=>settingsChanged({theme:b.dataset.theme}));
handle('setting-language','change',e=>{settingsChanged({language:e.target.value});updateModels();});
handle('setting-font','input',e=>settingsChanged({fontSize:Number(e.target.value)}));
handle('setting-tab','change',e=>settingsChanged({tabSize:Number(e.target.value)}));
handle('setting-timeout','change',e=>{const v=Math.round(Number(e.target.value));settingsChanged({timeout:Math.max(2,Math.min(60,v||30))});});
handle('add-provider','click',()=>openProvider());handle('cancel-provider','click',closeProvider);
handle('provider-form','submit',async e=>{
  e.preventDefault();const button=e.submitter;button.disabled=true;
  try{
    const id=$('provider-id').value.trim();
    const body={id,name:$('provider-name').value.trim(),url:$('provider-url').value.trim(),protocol:$('provider-protocol').value,
      key:$('provider-key').value.trim()||null,clear_key:$('provider-clear-key').checked,models:$('provider-models').value.split('\n').map(x=>x.trim()).filter(Boolean)};
    await api(state.editingProvider?`/providers/${state.editingProvider}`:'/providers',{method:state.editingProvider?'PUT':'POST',body});
    state.providers=await api('/providers');
    if(!state.providers.some(p=>p.id===state.settings.providerId))settingsChanged({providerId:id,model:body.models[0]||''});
    closeProvider();renderProviders();updateModels();toast(t('providerSaved'));
  }finally{button.disabled=false;}
});
handle('chat-provider','change',e=>{const p=state.providers.find(p=>p.id===e.target.value);settingsChanged({providerId:e.target.value,model:p?.models[0]||''});updateModels();});
handle('chat-model','input',e=>{state.settings.model=e.target.value.trim();state.settingsDirty=true;clearTimeout(settingsTimer);settingsTimer=setTimeout(saveSettings,250);});
handle('chat-form','submit',e=>{e.preventDefault();return sendChat();});
handle('chat-input','keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();return sendChat();}});
handle('clear-chat','click',async()=>{const id=state.active;if(!id)return;if(!await confirmAction(t('clearChatTitle'),t('clearChatHint')))return;await api(`/notes/${id}/messages`,{method:'DELETE'});if(state.active===id){state.messages=[];renderChat();}});
handle('run','click',runCode);
handle('stop','click',async()=>{if(!state.run)return;const job=await api(`/runs/${state.run.id}/stop`,{method:'POST'});clearTimeout(pollTimer);renderRun(job);});
handle('clear-output','click',()=>{
  if(state.run?.status==='running')return;
  state.run=null;$('stdout').textContent='';$('stderr').textContent='';$('run-status').textContent='';$('run-status').classList.add('hidden');$('terminal-hint').classList.remove('hidden');$('explain-error').classList.add('hidden');
});
handle('stdin-form','submit',async e=>{e.preventDefault();if(!state.run)return;await api(`/runs/${state.run.id}/input`,{method:'POST',body:{text:$('stdin').value+'\n'}});$('stdin').value='';$('stdin').focus();});
handle('stdin-eof','click',async()=>{if(!state.run)return;renderRun(await api(`/runs/${state.run.id}/input`,{method:'POST',body:{eof:true}}));});
handle('explain-error','click',async()=>{
  if(!state.run)return;
  if(state.runNote!==state.active){if(!state.notes.some(n=>n.id===state.runNote))return;await selectNote(state.runNote);}
  $('right-panel').classList.remove('collapsed');
  return sendChat(`${t('chatPrompt')}\n${$('stderr').textContent}`,state.runCode);
});
handle('load-example','click',async()=>{const key=$('example-select').value;await createNote(examples[key],t({hello:'exampleHello',loop:'exampleLoop',input:'exampleInput',function:'exampleFunction'}[key]));$('settings-dialog').close();$('utility-dialog').close();});
handle('editor','keydown',e=>{
  if(e.isComposing)return;
  if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();return runCode();}
  if(e.key==='Tab'){
    e.preventDefault();const editor=$('editor'),start=editor.selectionStart,end=editor.selectionEnd,text=editor.value,spaces=' '.repeat(state.settings.tabSize);
    if(start===end&&!e.shiftKey){editor.setRangeText(spaces,start,end,'end');}
    else{
      const lineStart=text.lastIndexOf('\n',start-1)+1;
      const original=text.slice(lineStart,end),lines=original.split('\n');
      let firstDelta=0,totalDelta=0;
      const changed=lines.map((line,i)=>{if(i===lines.length-1&&!line&&end>start)return line;const next=e.shiftKey?line.replace(new RegExp(`^( {1,${state.settings.tabSize}}|\\t)`),''):spaces+line;const d=next.length-line.length;if(i===0)firstDelta=d;totalDelta+=d;return next;}).join('\n');
      editor.setRangeText(changed,lineStart,end,'select');editor.setSelectionRange(Math.max(lineStart,start+firstDelta),Math.max(lineStart,end+totalDelta));
    }
    editNote();
  }else if(e.key==='Enter'){
    e.preventDefault();const editor=$('editor'),start=editor.selectionStart,end=editor.selectionEnd;
    const line=editor.value.slice(0,start).split('\n').at(-1);let indent=line.match(/^\s*/)[0];
    if(line.trimEnd().endsWith(':'))indent+=' '.repeat(state.settings.tabSize);
    editor.setRangeText('\n'+indent,start,end,'end');editNote();
  }
});
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();flushNotes();saveSettings();}
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('search').focus();}
});
window.addEventListener('beforeunload',e=>{if(state.dirty.size||state.settingsDirty||state.pendingChat||state.run?.status==='running'){e.preventDefault();e.returnValue='';}});
async function init(){
  $('retry').disabled=true;
  try{
    await connect();
    const [notes,settings,providers,health,recoveredRun]=await Promise.all([api('/notes'),api('/settings'),api('/providers'),api('/health'),api('/runs/active')]);
    state.notes=notes;state.settings=settings;state.providers=providers;state.ready=true;
    $('connection-error').classList.add('hidden');$('connection').classList.add('online');$('connection').title=`Python ${health.python}`;
    applySettings();updateModels();
    if(!notes.length)await createNote();else await selectNote(notes[0].id);
    if(recoveredRun.run){state.runCode=recoveredRun.code;state.runNote=recoveredRun.note_id;renderRun(recoveredRun.run);pollRun();}
    // A legacy app served from this same origin can migrate without touching its old data.
    let legacy;
    try{legacy=JSON.parse(localStorage.getItem('macos_notes_python_storage_v4')||'null');}catch{}
    if(Array.isArray(legacy)&&legacy.length&&!localStorage.getItem('python_lab_migrated')){
      if(await confirmAction(t('legacyTitle'),t('legacyFound'))){
        await importFiles([new File([JSON.stringify(legacy)],'legacy.json',{type:'application/json'})]);localStorage.setItem('python_lab_migrated','1');
      }
    }
  }catch(e){$('connection-error').classList.remove('hidden');$('connection').classList.remove('online');fail(e);}
  finally{$('retry').disabled=false;}
}
handle('retry','click',init);
if(innerWidth<768)$('right-panel').classList.add('collapsed');if(innerWidth<768)$('left-panel').classList.add('collapsed');
applySettings();init();

function openUtility(){if(!$('utility-dialog').open)$('utility-dialog').showModal();}
function showContextMenu(e){
  e.preventDefault();const menu=$('context-menu');menu.classList.remove('hidden');
  menu.style.left=Math.min(e.clientX,innerWidth-180)+'px';menu.style.top=Math.min(e.clientY,innerHeight-85)+'px';
}
handle('open-settings','contextmenu',showContextMenu);
handle('toggle-right','contextmenu',showContextMenu);
handle('context-manage','click',()=>{openUtility();$('context-menu').classList.add('hidden');});
handle('context-models','click',()=>{openSettings('providers');$('context-menu').classList.add('hidden');});
handle('close-utility','click',()=>{$('utility-dialog').close();saveSettings();});
document.addEventListener('click',e=>{if(!$('context-menu').contains(e.target))$('context-menu').classList.add('hidden');});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('context-menu').classList.add('hidden');});
$('settings-dialog').addEventListener('click',e=>{if(e.target===$('settings-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
handle('fetch-provider-models','click',async()=>{
  const id=state.editingProvider;if(!id)return;
  const button=$('fetch-provider-models');button.disabled=true;
  try{const result=await api(`/providers/${id}/models`,{method:'POST'});$('provider-models').value=result.models.join('\n');state.providers=await api('/providers');updateModels();toast(t('modelsFetched'));}finally{button.disabled=false;}
});
handle('add-provider-model','click',()=>{$('provider-models').focus();if($('provider-models').value&&!$('provider-models').value.endsWith('\n'))$('provider-models').value+='\n';});
handle('delete-provider','click',async()=>{
  const id=state.editingProvider;if(!id||!await confirmAction(t('deleteProvider'),t('deleteProviderHint')))return;
  await api(`/providers/${id}`,{method:'DELETE'});
  if(state.settings.providerId===id)settingsChanged({providerId:'',model:''});
  state.providers=await api('/providers');closeProvider();renderProviders();updateModels();
});
