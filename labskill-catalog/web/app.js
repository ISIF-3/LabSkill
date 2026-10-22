import { normalizeRepo, filterRepos, paginateRepos, historyCoverageText, optionsFor, functionOptions, FUNCTIONS, AGENT_STATUSES, escapeHtml as esc, numberText, repoUrl, isCatalogNew, parseRepositoryUrl, normalizeLibrary, mergeLegacySaved, changeLibrary, createLibraryStore } from "./catalog-data.mjs";
const ICONS={
  compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5Z"/>',
  trending:'<path d="m3 17 6-6 4 4 8-10M15 5h6v6"/>',
  library:'<rect x="3" y="4" width="4" height="16" rx="1"/><rect x="10" y="4" width="4" height="16" rx="1"/><path d="m17 5 4 14M4 8h2m5 0h2"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  list:'<path d="M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  sliders:'<path d="M4 7h7m4 0h5M4 17h3m4 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  refresh:'<path d="M20 10a8 8 0 0 0-14-5L3 8m0-5v5h5M4 14a8 8 0 0 0 14 5l3-3m0 5v-5h-5"/>',
  bookmark:'<path d="M6 3h12v18l-6-4-6 4Z"/>',
  'arrow-right':'<path d="M4 12h15m-5-5 5 5-5 5"/>',
  layers:'<path d="m12 3 10 6-10 6L2 9ZM2 13l10 6 10-6M2 17l10 6 10-6"/>',
  cube:'<path d="m12 2 9 5v10l-9 5-9-5V7Zm0 10L3 7m9 5 9-5m-9 5v10"/>',
  plug:'<path d="M8 3v5m8-5v5M5 8h14v3a7 7 0 0 1-14 0Zm7 10v4"/>',
  server:'<rect x="3" y="3" width="18" height="7" rx="1"/><rect x="3" y="14" width="18" height="7" rx="1"/><path d="M7 6.5h.01M7 17.5h.01M15 6.5h3M15 17.5h3"/>',
  terminal:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3m6 0h4"/>',
  code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
  drive:'<path d="m6 4-4 11v5h20v-5L18 4Zm-4 11h20M17 18h.01m3 0h.01"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4m0 3h.01"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  'chevron-up':'<path d="m6 15 6-6 6 6"/>',
  star:'<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  external:'<path d="M14 3h7v7m0-7L10 14M9 3H3v18h18v-6"/>',
  quote:'<path d="M10 5H4v7h6v6H4m16-13h-6v7h6v6h-6"/>',
};
const icon=(name)=>`<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]||ICONS.cube}</svg>`;

document.querySelectorAll('[data-icon]').forEach(element=>element.innerHTML=icon(element.dataset.icon));
const $=selector=>document.querySelector(selector);
const readLocal=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback}catch{return fallback}};
const writeLocal=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value))}catch{notify('브라우저 저장소를 사용할 수 없어 이번 화면에서만 유지됩니다.')}};
const saved=new Set();
const state={page:1,view:'discover',collection:'all',discoveryDomain:'lit',function:'all',agentStatus:'all',client:'all',kind:'all',domain:'all',install:'all',skills:false,search:'',sort:'trending',layout:readLocal('labskill-layout','grid')==='list'?'list':'grid'};
let repos=[],taxonomy={functions:{},kinds:{},domains:{},install_methods:{}},discoveryProfiles={},historySummary=null,historyActionPending=false,catalog={repos:[]},status=null,apiError='',loading=true;
let currentDetail=null,detailTrigger=null,toastTimer,pollTimer,featuredId=null,pageCriteria='';
let library={schema_version:1,saved_ids:[],collections:[],notes:{}},libraryStore=null,libraryLoading=true,libraryError='',libraryPending=0,collectionAction='create',collectionTarget=null,manualSubmitting=false,pendingRepo=null,pollPromise=null;
const noteDrafts=new Map();
const functionIcons={code:'code',literature:'library',visualization:'grid',data:'layers',ai:'terminal',search:'search',automation:'refresh',productivity:'bookmark',media:'grid',infrastructure:'server',security:'drive',science:'cube',learning:'library',devices:'plug',other:'compass'};
const formatDate=value=>{if(!value)return '아직 수집 전';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value.replaceAll('-','. ');const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});};
const growthText=repo=>repo.current&&repo.growth!=null?`${repo.growth>=0?'+':''}${numberText(repo.growth)}`:'—';
const discoveryLabel=domain=>discoveryProfiles[domain]?.label||optionLabel(taxonomy.domains,domain);
const growthLabel=repo=>repo.current?'이번 주':repo.discoveryDomains.length?'분야별 발견':repo.history?'과거 트렌딩':'이전 수집';
const collectionBusy=()=>!!status?.running||!!historySummary?.active||historyActionPending||manualSubmitting||!!pendingRepo;
const clientLabels={all:'모든 안내',codex:'Codex',claude_code:'Claude Code',either:'Codex 또는 Claude Code',both:'두 앱 모두',unconfirmed:'지원 안내 미확인'};
const hasDetailFilters=()=>state.search||state.function!=='all'||state.agentStatus!=='all'||state.kind!=='all'||state.domain!=='all'||state.install!=='all'||state.skills||state.client!=='all';
const libraryPool=()=>state.view==='library'&&state.collection!=='all'?repos.filter(repo=>library.collections.find(collection=>collection.id===state.collection)?.repo_ids.includes(repo.id)):repos;
const visibleRepos=()=>filterRepos(libraryPool(),state,saved);
const sourcePool=()=>filterRepos(libraryPool(),{view:state.view,discoveryDomain:state.discoveryDomain},saved);
const typePool=()=>filterRepos(libraryPool(),{view:state.view,discoveryDomain:state.discoveryDomain,function:state.function},saved);
const functionLabel=value=>taxonomy.functions?.[value]?.label||FUNCTIONS[value]||value;
const functionBadges=repo=>repo.functions.map((value,index)=>`<span class="function-tag ${value==='other'?'unknown-function':''}">${esc(repo.functionLabels[index])}</span>`).join('');

function renderOptionalFilters(){
  const pool=typePool(),options=[['all','전체 저장소'],...Object.entries(AGENT_STATUSES)];
  $('#agent-status-filter').innerHTML=options.map(([value,label])=>`<option value="${value}">${label} · ${pool.filter(repo=>value==='all'||repo.agentStatus===value).length}</option>`).join('');
  $('#agent-status-filter').value=state.agentStatus;$('#client-filter').value=state.client;
  const active=[state.kind,state.domain,state.install,state.client,state.agentStatus].filter(value=>value!=='all').length+Number(state.skills);
  $('#filter-summary').textContent=active?`${active}개 적용 중`:'종류 · 지원 앱 · 설치 방법';
  const source=sourcePool(),unknown=source.filter(repo=>repo.functions.includes('other')).length;
  $('#function-summary').textContent=state.function==='all'?`${source.length.toLocaleString('ko-KR')}개 저장소를 기능별로 탐색합니다.${unknown?` 기타·미분류 ${unknown.toLocaleString('ko-KR')}개도 포함합니다.`:''} 여러 기능의 목록에 함께 나타날 수 있습니다.`:state.function==='other'?'기능을 결정할 단서가 부족한 저장소입니다. 원래 설명과 GitHub 링크를 함께 보관합니다.':`${functionLabel(state.function)} 기능을 가진 저장소입니다. 다른 기능의 목록에도 함께 나타날 수 있습니다.`;
}

function notify(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}

async function getJSON(path,options={}){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch(path,{...options,signal:controller.signal,cache:'no-store'});
    const data=await response.json();
    if(!response.ok){const error=new Error(typeof data.error==='string'?data.error:`서버 응답 ${response.status}`);error.status=response.status;throw error;}
    return data;
  }finally{clearTimeout(timeout);}
}

const postJSON=(path,document)=>getJSON(path,{method:'POST',headers:{'Content-Type':'application/json','X-LabSkill-Request':'1'},body:JSON.stringify(document)});
const newBadge=repo=>isCatalogNew(repo)?'<span class="new-badge" title="최근 7일 안에 새로 추가되었거나 README·스킬 내용이 갱신됨">New!</span>':'';

function syncLibrary(document){
  library=document;saved.clear();for(const id of document.saved_ids)saved.add(id);
  if(state.collection!=='all'&&!document.collections.some(collection=>collection.id===state.collection))state.collection='all';
}

async function loadLibrary(){
  if(libraryPending)return;
  libraryLoading=true;renderLibrary();
  try{
    const stored=normalizeLibrary(await getJSON('/api/library'));
    libraryStore=createLibraryStore(stored,document=>postJSON('/api/library',document));syncLibrary(stored);
    const legacy=readLocal('labskill-saved-repos',[]),merged=mergeLegacySaved(stored,legacy);
    if(merged.saved_ids.length!==stored.saved_ids.length)syncLibrary(await libraryStore.update(()=>merged));
    try{localStorage.removeItem('labskill-saved-repos');}catch{}
    libraryError='';
  }catch(error){libraryError=`라이브러리를 불러오지 못했습니다. 기존 보관 정보는 유지됩니다. ${error.message}`;}
  finally{libraryLoading=false;render();if(currentDetail)renderDetail(currentDetail);}
}

async function saveLibrary(action,message){
  if(!libraryStore||libraryLoading){notify('라이브러리를 불러온 뒤 다시 저장해주세요.');return false;}
  libraryPending++;renderLibrary();updateLibraryButtons();
  try{
    const stored=await libraryStore.update(document=>changeLibrary(document,action));syncLibrary(stored);libraryError='';
    if(action.type==='note'&&noteDrafts.get(action.repoId)===action.note)noteDrafts.delete(action.repoId);
    if(message)notify(message);
    return true;
  }catch(error){libraryError=`저장하지 못했습니다. 마지막 저장 상태를 유지합니다. ${error.message}`;notify(libraryError);return false;}
  finally{libraryPending--;render();if(currentDetail)renderDetail(currentDetail);}
}

function updateLibraryButtons(){
  document.querySelectorAll('[data-save],[data-detail-save],#feature-save,[data-collection-remove],[data-note-save]').forEach(button=>button.disabled=libraryLoading||!libraryStore||libraryPending>0);
  document.querySelectorAll('[data-detail-collection]').forEach(input=>input.disabled=libraryLoading||!libraryStore||libraryPending>0);
}

function renderLibrary(){
  $('#library-panel').hidden=state.view!=='library';
  $('#library-notice').hidden=!libraryError;$('#library-notice-message').textContent=libraryError;$('#library-retry').disabled=libraryLoading||libraryPending>0;
  $('#collection-select').innerHTML='<option value="all">보관한 모든 도구</option>'+library.collections.map(collection=>`<option value="${esc(collection.id)}">${esc(collection.name)} · ${collection.repo_ids.length}</option>`).join('');$('#collection-select').value=state.collection;
  const selected=library.collections.find(collection=>collection.id===state.collection),locked=libraryLoading||!libraryStore||libraryPending>0;
  for(const id of ['collection-create','collection-select','collection-rename','collection-delete','collection-add-repo'])$(`#${id}`).disabled=locked;
  $('#collection-rename').hidden=!selected;$('#collection-delete').hidden=!selected;$('#collection-add-controls').hidden=!selected;
  const available=selected?library.saved_ids.filter(id=>!selected.repo_ids.includes(id)):[];
  $('#collection-repo-select').innerHTML=available.length?available.map(id=>`<option value="${esc(id)}">${esc(repos.find(repo=>repo.id===id)?.name||id)}</option>`).join(''):'<option value="">추가할 보관 도구가 없습니다</option>';
  $('#collection-repo-select').disabled=locked||!available.length;$('#collection-add-repo').disabled=locked||!available.length;
  $('#library-save-status').textContent=libraryLoading?'라이브러리를 불러오는 중…':libraryPending?'이 컴퓨터에 저장 중…':'북마크 · 컬렉션 · 메모는 이 컴퓨터에 저장됩니다.';
}

function allOptions(table,key,pool=repos){return [{value:'all',label:key==='kind'?'전체 종류':'전체',count:pool.length},...optionsFor(table,pool,key)];}
function optionLabel(table,key){return key==='all'?'전체':key==='__pending__'?'미분류':Object.hasOwn(table,key)?table[key].label:key;}

function renderDiscovery(){
  $('#discovery-panel').hidden=state.view!=='discovery';
  const options=Object.entries(discoveryProfiles).map(([value,profile])=>`<option value="${esc(value)}">${esc(profile.label)}</option>`).join('');
  if($('#discovery-domain').innerHTML!==options)$('#discovery-domain').innerHTML=options;
  $('#discovery-domain').value=state.discoveryDomain;
  $('#discovery-domain').disabled=loading||!Object.keys(discoveryProfiles).length;
  const profile=discoveryProfiles[state.discoveryDomain];
  $('#discovery-description').textContent=profile?.description||'분야 목록을 불러오고 있습니다.';
  $('#discovery-button').disabled=loading||collectionBusy()||!profile;
  $('#discovery-button span:last-child').textContent=collectionBusy()?'수집 중…':'분야 도구 찾기';
}

function renderHistory(){
  $('#history-panel').hidden=state.view!=='history';
  const available=historySummary?.available===true,active=historySummary?.active===true;
  const range=historySummary?.range,coverage=historyCoverageText(historySummary?.coverage);
  $('#history-range').textContent=available&&range?.start&&range?.end?`기록 범위: ${formatDate(range.start)} ~ ${formatDate(range.end)}${coverage?` · ${coverage}`:''}`:loading?'기록을 불러오고 있습니다.':'아직 가져온 과거 트렌딩 기록이 없습니다.';
  const sourceUrl=repoUrl(historySummary?.source_repository);
  $('#history-source').hidden=!sourceUrl;if(sourceUrl)$('#history-source').href=sourceUrl;
  for(const key of ['total','enriched','classified','pending','remaining','failed']){const value=historySummary?.[key];$(`#history-${key}`).textContent=typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('ko-KR'):'—';}
  $('#history-functions').textContent=repos.filter(repo=>repo.history&&!repo.functions.includes('other')).length.toLocaleString('ko-KR');
  const progress=$('#history-progress'),total=historySummary?.total,enriched=historySummary?.enriched;
  if(Number.isFinite(total)&&total>0&&Number.isFinite(enriched)){progress.max=total;progress.value=Math.min(total,Math.max(0,enriched));}else{progress.max=1;progress.value=0;}
  const progressState=!available?'기록을 가져오면 여기에 진행 상황을 표시합니다.':active?(historySummary.pause_requested?'현재 묶음의 결과를 저장한 뒤 멈춥니다.':'정보와 분류를 묶음별로 저장하며 정리하고 있습니다.'):historySummary.needs_resume?'남은 저장소는 이어서 정리할 수 있습니다.':'가져온 기록의 정리를 마쳤습니다.';
  $('#history-progress-label').textContent=`${available&&Number.isFinite(total)&&Number.isFinite(enriched)?`정보 수집 ${enriched.toLocaleString('ko-KR')} / ${total.toLocaleString('ko-KR')} · `:''}${progressState}`;
  $('#history-resume').disabled=loading||historyActionPending||collectionBusy()||!available||!historySummary?.needs_resume;
  $('#history-resume span:last-child').textContent=active?'정리 중…':'정리 이어가기';
  $('#history-pause').hidden=!active;$('#history-pause').disabled=historyActionPending||historySummary?.pause_requested===true;
  $('#history-pause').textContent=historySummary?.pause_requested?'현재 묶음 뒤에 멈춥니다':'현재 묶음까지 정리하고 멈추기';
}

function renderNavigation(){
  const pool=typePool(),functionPool=filterRepos(libraryPool(),{...state,function:'all'},saved);
  const functions=[{value:'all',label:'모든 기능',count:functionPool.length},...functionOptions(taxonomy.functions,functionPool)];
  $('#function-navigation').innerHTML=functions.map(({value,label,count})=>`<button class="side-item function-item ${state.function===value?'selected':''} ${count?'':'zero-count'}" data-function="${esc(value)}" aria-pressed="${state.function===value}" title="${esc(label)}">${icon(value==='all'?'grid':functionIcons[value]||'cube')}<span class="nav-label">${esc(label)}</span><span class="kind-count">${count}</span></button>`).join('');
  $('#function-filter').innerHTML=functions.map(({value,label,count})=>`<option value="${esc(value)}">${esc(label)} · ${count}</option>`).join('');$('#function-filter').value=state.function;
  for(const [key,table] of [['kind',taxonomy.kinds],['domain',taxonomy.domains]]){const select=$(`#${key}-filter`);select.innerHTML=allOptions(table,key,pool).map(({value,label})=>`<option value="${esc(value)}">${esc(label)}</option>`).join('');select.value=state[key];}
  const installOptions=[{value:'all',label:'모든 설치 방법'},...optionsFor(taxonomy.install_methods,pool,'install')];
  $('#install-filter').innerHTML=installOptions.map(({value,label})=>`<option value="${esc(value)}">${esc(label)}</option>`).join('');
  $('#install-filter').value=state.install;$('#skills-only').checked=state.skills;
  document.querySelectorAll('[data-view]').forEach(element=>{const active=element.dataset.view===state.view;element.classList.toggle(element.classList.contains('primary-link')?'active':'selected',active);element.setAttribute('aria-current',active?'page':'false');});
  document.querySelectorAll('.saved-count').forEach(element=>element.textContent=repos.filter(repo=>saved.has(repo.id)).length);
}

function renderFeature(){
  const featured=filterRepos(repos,{...state,view:'trending',sort:'trending'},saved)[0]||filterRepos(repos,state,saved)[0];
  featuredId=featured?.id||null;
  $('#feature').hidden=!featured||state.view!=='trending'||!!hasDetailFilters();
  if(!featured)return;
  $('#feature h2').textContent=featured.name;
  $('#feature p').textContent=featured.description;
  $('.feature-caption strong').textContent=featured.wordmark;
  $('.feature-caption div>span').textContent=featured.functionLabels.join(' · ');
  $('#feature-rank').textContent=featured.current&&featured.rank?`WEEKLY #${featured.rank}`:'';
  const isSaved=saved.has(featured.id);$('#feature-save').classList.toggle('saved',isSaved);$('#feature-save').setAttribute('aria-pressed',isSaved);$('#feature-save').setAttribute('aria-label',isSaved?'주목할 저장소를 라이브러리에서 삭제':'주목할 저장소를 라이브러리에 저장');
}

function renderCards(visible){
  const pagination=paginateRepos(visible,state.page);state.page=pagination.page;
  $('#catalog').classList.toggle('list-mode',state.layout==='list');
  $('#catalog').innerHTML=pagination.items.map(repo=>`<article class="repo-card" data-repo="${esc(repo.id)}"><button class="repo-open" data-open="${esc(repo.id)}" aria-label="${esc(repo.name)} 상세 보기"><div class="repo-cover"><img src="assets/${repo.cover}.svg" alt="" loading="lazy"><span class="cover-wordmark">${esc(repo.wordmark)}<small>${esc(repo.subtitle)}</small></span>${repo.skills>0?`<span class="skill-badge">${icon('cube')}SKILL ${repo.skills}</span>`:''}</div><div class="repo-body"><h3 title="${esc(repo.name)}">${newBadge(repo)}${esc(repo.name)}</h3><div class="repo-owner">${esc(repo.repo)}</div><p class="repo-description">${esc(repo.description)}</p><div class="repo-taxonomy">${functionBadges(repo)}${repo.kind!=null?`<span class="kind-tag">${esc(repo.kindLabel)}</span>`:''}${repo.history&&repo.discoveryDomains.length?'<span class="domain-tag source-tag">과거 트렌딩</span>':''}</div></div></button><button class="icon-button card-save ${saved.has(repo.id)?'saved':''}" data-save="${esc(repo.id)}" aria-label="${esc(repo.name)} ${saved.has(repo.id)?'보관 취소':'보관'}" aria-pressed="${saved.has(repo.id)}">${icon('bookmark')}</button><div class="card-metrics"><span class="star-count">${icon('star')}${numberText(repo.stars)}</span><span class="growth ${repo.current?'':'historical'}">${growthText(repo)}<small>${growthLabel(repo)}</small></span>${state.view==='library'&&state.collection!=='all'?`<button class="collection-remove" data-collection-remove="${esc(repo.id)}" aria-label="${esc(repo.name)}을 이 컬렉션에서 제거">제거</button>`:''}</div></article>`).join('');
  $('#catalog-pagination').hidden=pagination.pageCount<=1;
  $('#pagination-summary').textContent=`${pagination.start.toLocaleString('ko-KR')}–${pagination.end.toLocaleString('ko-KR')} / 전체 ${pagination.total.toLocaleString('ko-KR')}개 · ${pagination.page} / ${pagination.pageCount}페이지`;
  $('#page-previous').disabled=pagination.page===1;$('#page-next').disabled=pagination.page===pagination.pageCount;
  $('#page-previous').setAttribute('aria-label',pagination.page===1?'이전 페이지 없음':`이전 페이지 (${pagination.page-1}페이지)`);
  $('#page-next').setAttribute('aria-label',pagination.page===pagination.pageCount?'다음 페이지 없음':`다음 페이지 (${pagination.page+1}페이지)`);
  $('#result-count').textContent=pagination.total;
  $('#result-announcement').textContent=pagination.total?`검색 결과 ${pagination.total}개 중 ${pagination.start}번째부터 ${pagination.end}번째까지 표시합니다. ${pagination.page} / ${pagination.pageCount}페이지입니다.`:'조건에 맞는 저장소가 없습니다.';
  $('#empty-state').hidden=visible.length>0;
  const hasFilters=hasDetailFilters();
  const emptyLibrary=state.view==='library'&&!hasFilters;
  const emptyCollection=emptyLibrary&&state.collection!=='all';
  const emptyDiscovery=state.view==='discovery'&&!hasFilters;
  const emptyHistory=state.view==='history'&&!hasFilters;
  const isInitial=!repos.length&&!hasFilters&&!emptyLibrary;
  $('#empty-state h3').textContent=emptyCollection?'이 컬렉션에 도구를 모아보세요':emptyLibrary?'나만의 도구를 모아보세요':emptyHistory?'아직 표시할 과거 트렌딩 기록이 없습니다':emptyDiscovery?`${discoveryLabel(state.discoveryDomain)} 도구를 찾아보세요`:isInitial?(status?.running?'이번 주의 도구를 찾고 있습니다':loading?'카탈로그를 불러오고 있습니다':'아직 수집된 저장소가 없어요'):'조건에 맞는 도구가 없어요';
  $('#empty-description').textContent=emptyCollection?'위에서 보관한 도구를 추가하거나 상세 화면에서 컬렉션을 지정하세요.':emptyLibrary?'카드의 북마크를 눌러 라이브러리에 저장할 수 있습니다.':emptyHistory?'가져온 기록은 현재 저장소 정보와 연결되는 대로 여기에 표시합니다.':emptyDiscovery?'이 분야에서 아직 발견한 저장소가 없습니다. GitHub에서 도구를 찾아 여기에 모읍니다.':isInitial?(status?.running?'README와 파일 목록을 확인한 뒤, 분류가 끝나면 여기에 표시합니다.':apiError||status?.last_error||'새로고침을 누르면 GitHub 주간 트렌딩을 수집합니다.'):'검색어나 필터를 조금 바꿔보세요.';
  $('#reset-filters').textContent=emptyLibrary?'도구 둘러보기':emptyHistory?(collectionBusy()?'정리 중…':'정리 이어가기'):emptyDiscovery?(collectionBusy()?'수집 중…':'분야 도구 찾기'):isInitial?(status?.running?'수집 중…':'수집 시작'):'필터 초기화';
  $('#reset-filters').disabled=((isInitial||emptyDiscovery||emptyHistory)&&(loading||collectionBusy()))||(emptyHistory&&(!historySummary?.available||!historySummary?.needs_resume));
}

function renderFilters(){
  const chips=[];
  if(state.function!=='all')chips.push(['function',functionLabel(state.function)]);
  if(state.agentStatus!=='all')chips.push(['agentStatus',AGENT_STATUSES[state.agentStatus]]);
  if(state.kind!=='all')chips.push(['kind',optionLabel(taxonomy.kinds,state.kind)]);
  if(state.domain!=='all')chips.push(['domain',optionLabel(taxonomy.domains,state.domain)]);
  if(state.install!=='all')chips.push(['install',optionLabel(taxonomy.install_methods,state.install)]);
  if(state.client!=='all')chips.push(['client',clientLabels[state.client]]);
  if(state.skills)chips.push(['skills','SKILL.md 포함']);if(state.search)chips.push(['search',`검색: ${state.search}`]);
  $('#active-filters').innerHTML=chips.map(([key,label])=>`<button class="filter-chip" data-clear="${key}" aria-label="${esc(label)} 필터 해제">${esc(label)}${icon('close')}</button>`).join('')+(chips.length?'<button class="clear-all" data-clear="all">모두 초기화</button>':'');
  $('#mobile-filters-button').setAttribute('aria-label',`필터 열기${chips.length?` · ${chips.length}개 적용`:''}`);
}

function renderStatus(){
  renderDiscovery();renderHistory();
  const running=status?.running===true||!!pendingRepo;const failure=apiError||(!pendingRepo&&status?.last_error);const partial=(status?.report?.failed?.length||0)>0;
  const needsCodexLogin=status?.classification_backend==='codex'&&(status?.classification_available===false||status?.codex_available===false);
  const needsLogin=needsCodexLogin||status?.github_authenticated===false;
  const showPanel=running||!!failure||partial||needsLogin;
  $('#collection-panel').hidden=!showPanel;$('#collection-panel').classList.toggle('error',!!failure&&!running);$('#collection-panel').classList.toggle('working',running);
  $('#collection-message').textContent=running?(status?.running?`${status.discovery_domain?`${discoveryLabel(status.discovery_domain)} · `:''}${status.message}`:'추가한 저장소 정보를 확인하고 있습니다'):failure?'수집 상태를 확인해주세요':partial?'일부 저장소를 확인하지 못했습니다':status?.github_authenticated===false?'GitHub 로그인이 필요합니다':'Codex 로그인이 필요합니다';
  $('#collection-detail').textContent=running?(pendingRepo?`${pendingRepo.id} · 저장된 목록은 계속 탐색할 수 있습니다.`:status?.repo?`${status.current} / ${status.total} · ${status.repo}`:'저장된 목록은 계속 탐색할 수 있습니다.'):failure|| (partial?`${status.report.failed.length}개 조회 실패 · 항목은 카탈로그에 보존했습니다.`:status?.github_authenticated===false?'터미널에서 gh auth login을 실행한 뒤 새로고침하세요.':'터미널에서 codex login을 실행하면 저장소 분류를 이어갈 수 있습니다.');
  const progress=$('#collection-progress');progress.hidden=!running;if(status?.total>0){progress.max=status.total;progress.value=status.current||0;}else progress.removeAttribute('value');
  $('#refresh-button').disabled=historyActionPending||collectionBusy()||(state.view==='discovery'&&!discoveryProfiles[state.discoveryDomain])||(state.view==='history'&&(!historySummary?.available||!historySummary?.needs_resume));$('#refresh-button').classList.toggle('working',collectionBusy());
  $('#refresh-button').title=collectionBusy()?'수집이 진행 중입니다':state.view==='history'?'과거 트렌딩 정리 이어가기':state.view==='discovery'?`${discoveryLabel(state.discoveryDomain)} 도구 다시 찾기`:'GitHub 주간 트렌딩 다시 수집';
  $('#add-repo-button').disabled=loading||collectionBusy();$('#submit-add-repo').disabled=manualSubmitting||!!pendingRepo;$('#submit-add-repo').textContent=manualSubmitting?'접수 중…':'저장소 추가';
  const generatedAt=catalog.generated_at||status?.generated_at;
  $('#collection-status').textContent=running?(pendingRepo?`${pendingRepo.id} 추가 중…`:status.message):failure?'수집 실패 · 마지막 저장 목록 표시':`마지막 갱신 ${formatDate(generatedAt)}`;
  $('.status-indicator').classList.toggle('failed',!!failure);$('.status-indicator').classList.toggle('running',running);
  $('#footer-count').textContent=`${repos.length}개 저장소`;
  $('#classification-mode').hidden=status?.classification_backend!=='python';
  $('#python-classification-help').hidden=status?.classification_backend!=='python';
}

function render(){
  const {page,layout,...criteria}=state,serialized=JSON.stringify(criteria);
  if(serialized!==pageCriteria){state.page=1;pageCriteria=serialized;}
  renderOptionalFilters();renderNavigation();renderFeature();const visible=visibleRepos();renderCards(visible);renderFilters();renderStatus();renderLibrary();updateLibraryButtons();
  const titles={discover:'기능별 도구',history:'과거 트렌딩 기록',trending:'이번 주 트렌딩',discovery:'분야별 도구',library:'내 라이브러리'};
  $('#page-title').innerHTML=`${titles[state.view]}<span class="heading-dot">.</span>`;
  $('#catalog-title').textContent=state.function!=='all'?functionLabel(state.function):state.view==='library'?(library.collections.find(collection=>collection.id===state.collection)?.name||'내가 모아둔 도구'):state.view==='history'?'과거 트렌딩에서 발견한 도구':state.view==='discovery'?`${discoveryLabel(state.discoveryDomain)}에서 발견한 도구`:state.view==='trending'?'이번 주 GitHub 트렌딩':'모든 기능의 저장소';
  $('#catalog-scope').value=state.view;
  $('#main-content').classList.toggle('saved-page',state.view!=='discover');$('#main-content').classList.toggle('filtered-page',!!hasDetailFilters());
  for(const layout of ['grid','list']){$(`#${layout}-view`).classList.toggle('active',state.layout===layout);$(`#${layout}-view`).setAttribute('aria-pressed',state.layout===layout);}
  const sortOptions=['discovery','history'].includes(state.view)?[['stars','전체 스타순'],['updated','최근 업데이트순'],['name','이름순']]:[['trending','이번 주 급상승순'],['stars','전체 스타순'],['name','이름순']];
  $('#sort').innerHTML=sortOptions.map(([value,label])=>`<option value="${value}">${label}</option>`).join('');$('#sort').value=state.sort;
  $('.footnote-demo').textContent=state.view==='history'?'Trending Archive':state.view==='discovery'?'GitHub Search':state.view==='trending'?'GitHub Weekly':'GitHub 카탈로그';
}

function clearFilters(){Object.assign(state,{function:'all',agentStatus:'all',kind:'all',domain:'all',install:'all',skills:false,search:'',client:'all'});$('#search').value='';}
function changeView(view){if(view!==state.view)state.sort=['discovery','history'].includes(view)?'stars':'trending';state.view=view;clearFilters();$('#main-content').scrollTop=0;render();}
async function toggleSaved(id){
  if(libraryPending)return;
  const included=!saved.has(id),fromDetail=document.activeElement?.hasAttribute('data-detail-save');
  await saveLibrary({type:'saved',repoId:id,included},included?'내 라이브러리에 보관했습니다':'보관을 취소했습니다 · 개인 메모는 남아 있습니다');
  if(currentDetail&&fromDetail)$('[data-detail-save]')?.focus();
  else{const button=Array.from(document.querySelectorAll('[data-save]')).find(element=>element.dataset.save===id);if(button)button.focus();else $('.primary-link.active')?.focus();}
}

function personalLibraryHTML(repo){
  const note=noteDrafts.get(repo.id)??library.notes[repo.id]??'';
  return `<section class="detail-section personal-library"><h3>${icon('library')}내 컬렉션</h3><p class="section-note">컬렉션에 넣으면 라이브러리에도 보관합니다. 여기서 빼면 보관 상태와 메모는 유지됩니다.</p><div class="detail-collections">${library.collections.length?library.collections.map(collection=>`<label><input type="checkbox" data-detail-collection="${esc(collection.id)}" data-repo-id="${esc(repo.id)}" ${collection.repo_ids.includes(repo.id)?'checked':''}><span>${esc(collection.name)}</span></label>`).join(''):'<p>내 라이브러리에서 컬렉션을 만들 수 있습니다.</p>'}</div><label class="note-label" for="personal-note">개인 메모</label><textarea id="personal-note" data-note-repo="${esc(repo.id)}" maxlength="4000" rows="5" placeholder="이 도구를 어디에 쓰고 싶은지 적어두세요." ${libraryLoading||!libraryStore?'disabled':''}>${esc(note)}</textarea><div class="note-actions"><span id="note-count">${[...note].length} / 4000</span><button class="button secondary" data-note-save="${esc(repo.id)}">메모 저장</button></div><p class="section-note">메모는 이 컴퓨터에 저장됩니다. 보관을 취소해도 남습니다.</p></section>`;
}

function openCollectionDialog(action){
  if(libraryLoading||libraryPending||!libraryStore)return;
  collectionAction=action;collectionTarget=state.collection;
  const collection=library.collections.find(item=>item.id===collectionTarget);if(action!=='create'&&!collection)return;
  $('#collection-dialog-title').textContent=action==='create'?'새 컬렉션':action==='rename'?'컬렉션 이름 변경':`‘${collection.name}’ 삭제`;
  $('#collection-name-field').hidden=action==='delete';$('#collection-name').required=action!=='delete';$('#collection-name').value=action==='rename'?collection.name:'';
  $('#collection-dialog-help').textContent=action==='delete'?'컬렉션만 삭제합니다. 보관한 도구와 개인 메모는 그대로 남습니다.':'보관한 도구를 주제별로 모아보세요.';
  $('#collection-submit').textContent=action==='create'?'만들기':action==='rename'?'이름 저장':'컬렉션 삭제';$('#collection-submit').disabled=false;$('#collection-form-error').hidden=true;
  $('#collection-dialog').showModal();if(action!=='delete')$('#collection-name').focus();
}

function renderDetail(id){
  const repo=repos.find(item=>item.id===id);if(!repo)return;
  const editing=$('#personal-note'),restoreNote=editing===document.activeElement,selection=restoreNote?[editing.selectionStart,editing.selectionEnd]:null,scroll=$('#detail-dialog').scrollTop;
  const evidence=repo.evidence.map(item=>`<blockquote class="evidence-box"><p>${esc(item.quote)}</p><cite>${esc(item.file||'README')} · ${repo.evidenceValid?'원문 일치 확인':'README 원문'}</cite></blockquote>`).join('');
  const signalPairs=[['SKILL.md',repo.skills==null?'미확인':`${repo.skills}개`],['플러그인 매니페스트',Array.isArray(repo.signals.plugin_manifests)&&repo.signals.plugin_manifests.length?'발견':repo.signalsAvailable?'없음':'미확인'],['MCP 설정',Array.isArray(repo.signals.mcp_files)&&repo.signals.mcp_files.length?'발견':repo.signalsAvailable?'없음':'미확인']];
  const historyInfo=repo.history?`<section class="detail-section"><h3>${icon('library')}트렌딩 등장 기록</h3><dl class="signal-list"><div><dt>최근 트렌딩 등장</dt><dd>${esc(repo.historyLastSeen?formatDate(repo.historyLastSeen):'정보 없음')}</dd></div><div><dt>첫 트렌딩 등장</dt><dd>${esc(repo.historyFirstSeen?formatDate(repo.historyFirstSeen):'정보 없음')}</dd></div><div><dt>등장일수</dt><dd>${repo.appearanceDays==null?'—':`${numberText(repo.appearanceDays)}일`}</dd></div><div><dt>기록 단위</dt><dd>${repo.historyPeriods.map(period=>period==='daily'?'일간 트렌딩':'주간 트렌딩').join(', ')||'정보 없음'}</dd></div>${repo.bestDailyRank!=null?`<div><dt>일간 최고 순위</dt><dd>${numberText(repo.bestDailyRank)}위</dd></div>`:''}<div><dt>기록 출처</dt><dd><a href="${repoUrl(repo.historySource)}" target="_blank" rel="noopener noreferrer">${esc(repo.historySource)}</a></dd></div></dl><p class="section-note">등장일수는 아카이브에 기록된 날짜 수입니다. 이번 주 스타 증가량과는 별개입니다.</p></section>`:'';
  const confidenceLabels={high:'높음',medium:'보통',low:'낮음'};
  const functionInfo=`<section class="detail-section function-detail"><h3>${icon('grid')}기능별 목록</h3><div class="repo-taxonomy">${functionBadges(repo)}</div><p>${repo.primaryFunction==='other'?'기능을 결정할 단서가 부족해 기타·미분류에 보관합니다.':`주 기능: ${esc(functionLabel(repo.primaryFunction))}`}</p>${repo.functionMatches.length?`<p class="section-note">분류 단서: ${repo.functionMatches.map(match=>`${esc(match.keyword)} (${esc(match.source)})`).join(' · ')}</p>`:''}</section>`;
  const classificationInfo=repo.agentAssessed||Object.values(repo.agentClients).some(value=>value!==null)?`<section class="detail-section selection-detail"><h3>${icon('sliders')}${esc(repo.agentAssessed?repo.agentLabel:'지원 앱')}</h3>${(repo.agentAssessed?repo.agentReasons:[]).map(reason=>`<p>${esc(reason)}</p>`).join('')}<dl class="signal-list">${[['codex','Codex'],['claude_code','Claude Code']].map(([key,label])=>`<div><dt>${label}</dt><dd>${repo.agentClients[key]===true?'README 안내 있음':repo.agentClients[key]===false?'지원 안 함으로 명시':'안내 미확인'}</dd></div>`).join('')}</dl><p class="section-note">지원 앱은 README 안내 기준입니다. Python으로 선별했으며 실행 호환성을 시험한 결과는 아닙니다.${repo.agentCheckedAt?` 확인 ${esc(formatDate(repo.agentCheckedAt))}`:''}</p></section>`:repo.classificationBackend==='python'&&repo.status!=='pending'?`<div class="classification-provenance"><strong>Python 규칙 분류</strong>${repo.confidence?`<span>규칙 일치도 ${esc(Object.hasOwn(confidenceLabels,repo.confidence)?confidenceLabels[repo.confidence]:repo.confidence)}</span>`:''}${repo.ruleMatches.length?`<p>단서: ${esc([...new Set(repo.ruleMatches.map(match=>match.keyword))].join(', '))}</p>`:''}</div>`:'';
  $('#detail-content').innerHTML=`<div class="detail-cover"><img src="assets/${repo.cover}.svg" alt=""><span class="cover-wordmark">${esc(repo.wordmark)}<small>${esc(repo.subtitle)}</small></span><button class="icon-button dialog-close" data-close-detail aria-label="상세 화면 닫기">${icon('close')}</button></div><div class="detail-body"><p class="detail-eyebrow">GITHUB REPOSITORY</p><h2 id="detail-title">${newBadge(repo)}${esc(repo.name)}</h2><div class="detail-owner">${esc(repo.repo)}</div><div class="repo-taxonomy">${functionBadges(repo)}${repo.kind!=null?`<span class="kind-tag">${esc(repo.kindLabel)}</span>`:''}${repo.domain!=null?`<span class="domain-tag">${esc(repo.domainLabel)}</span>`:''}${repo.subcategory?`<span class="domain-tag">${esc(repo.subcategory)}</span>`:''}</div><p class="detail-summary">${esc(repo.description)}</p>${functionInfo}${classificationInfo}<div class="detail-actions"><button class="button primary" data-detail-save="${esc(repo.id)}" aria-pressed="${saved.has(repo.id)}">${icon(saved.has(repo.id)?'check':'bookmark')}${saved.has(repo.id)?'라이브러리에 저장됨':'라이브러리에 저장'}</button>${repo.url?`<a class="button secondary" href="${esc(repo.url)}" target="_blank" rel="noopener noreferrer">${icon('external')}GitHub에서 보기</a>`:''}</div>${personalLibraryHTML(repo)}<dl class="detail-metrics"><div><dt>전체 스타</dt><dd>${numberText(repo.stars)}</dd></div><div><dt>${repo.current?'이번 주 증가':repo.history||repo.discoveryDomains.length?'발견 경로':'이전 수집'}</dt><dd class="green">${repo.current?growthText(repo):repo.discoveryDomains.length?'분야별 발견':repo.history?'과거 트렌딩':'—'}</dd></div><div><dt>설치 방법</dt><dd class="install-method-value">${esc(repo.installLabel)}</dd></div></dl>${historyInfo}${repo.status==='pending'&&repo.primaryFunction==='other'?`<p class="pending-notice detail-pending">${icon('refresh')}<span>분류 대기${repo.reviewReason?` · ${esc(repo.reviewReason)}`:''}</span></p>`:''}<section class="detail-section"><h3>${icon('quote')}README 근거</h3>${evidence||'<p>보관된 README 인용 근거가 없습니다.</p>'}</section>${repo.skillList.length?`<section class="detail-section"><h3>${icon('layers')}포함된 스킬 <span class="muted">${repo.skills??repo.skillList.length}</span></h3><div class="detail-skill-list">${repo.skillList.map(skill=>`<span class="skill-detail" title="${esc(skill.description||skill.path)}"><code>${esc(skill.name)}</code>${skill.description?`<small>${esc(skill.description)}</small>`:''}</span>`).join('')}</div>${repo.skills>repo.skillList.length?`<p class="section-note">전체 ${repo.skills}개 중 ${repo.skillList.length}개를 표시합니다. 본문은 최대 10개까지 읽습니다.</p>`:''}</section>`:''}<section class="detail-section"><h3>${icon('drive')}파일 신호</h3><dl class="signal-list">${signalPairs.map(([key,value])=>`<div><dt>${key}</dt><dd>${value}</dd></div>`).join('')}</dl></section><section class="detail-section"><h3>${icon('info')}설치 방법 정보</h3><p>${esc(repo.installLabel)}</p>${repo.installEvidence?`<pre class="install-evidence">${esc(repo.installEvidence.quote)}</pre>`:''}<p class="section-note">README의 안내를 정보로만 표시합니다.</p></section><section class="detail-section"><h3>${icon('code')}저장소 정보</h3><dl class="signal-list"><div><dt>언어</dt><dd>${esc(repo.language||'정보 없음')}</dd></div><div><dt>라이선스</dt><dd>${esc(repo.license||'정보 없음')}</dd></div><div><dt>최근 업데이트</dt><dd>${esc(formatDate(repo.pushedAt))}</dd></div><div><dt>수집 시각</dt><dd>${esc(formatDate(repo.fetchedAt))}</dd></div></dl></section><div class="local-note">이 컴퓨터의 카탈로그에 보관된 정보입니다. ${repo.current?'이번 주 트렌딩에서 발견했습니다.':repo.history?'과거 트렌딩 아카이브에 등장한 저장소입니다.':repo.discoveryDomains.length?'':'이전 수집에서 보관한 저장소입니다.'}${repo.discoveryDomains.length?` 분야별 탐색(${esc(repo.discoveryDomains.map(discoveryLabel).join(', '))})에서 발견했습니다.`:''}</div></div>`;
  updateLibraryButtons();
  if(restoreNote){$('#personal-note').focus({preventScroll:true});$('#personal-note').setSelectionRange(...selection);$('#detail-dialog').scrollTop=scroll;}
}
function openDetail(id){detailTrigger=document.activeElement;currentDetail=id;renderDetail(id);$('#detail-dialog').showModal();$('#detail-dialog').scrollTop=0;}
$('#detail-dialog').addEventListener('close',()=>{const id=currentDetail;currentDetail=null;const fallback=Array.from(document.querySelectorAll('[data-open]')).find(element=>element.dataset.open===id);const target=detailTrigger?.isConnected?detailTrigger:fallback;if(target)target.focus();else $('.primary-link.active')?.focus();detailTrigger=null;});
$('#detail-dialog').addEventListener('click',event=>{if(event.target===$('#detail-dialog')&&event.clientX<event.target.getBoundingClientRect().left)$('#detail-dialog').close();});

document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view)changeView(button.dataset.view);
  if(button.dataset.function){state.function=button.dataset.function;$('#main-content').scrollTop=0;render();}
  if(button.dataset.open)openDetail(button.dataset.open);
  if(button.dataset.save)toggleSaved(button.dataset.save);
  if(button.dataset.detailSave)toggleSaved(button.dataset.detailSave);
  if(button.dataset.collectionRemove&&!libraryPending)saveLibrary({type:'membership',collectionId:state.collection,repoId:button.dataset.collectionRemove,included:false},'컬렉션에서 제거했습니다 · 도구와 메모는 보관됩니다');
  if(button.dataset.noteSave&&!libraryPending)saveLibrary({type:'note',repoId:button.dataset.noteSave,note:noteDrafts.get(button.dataset.noteSave)??library.notes[button.dataset.noteSave]??''},'개인 메모를 저장했습니다');
  if(button.hasAttribute('data-close-detail'))$('#detail-dialog').close();
  if(button.hasAttribute('data-close-help'))$('#help-dialog').close();
  if(button.dataset.clear){const key=button.dataset.clear;if(key==='all')clearFilters();else if(key==='search'){state.search='';$('#search').value='';}else state[key]=key==='skills'?false:'all';render();}
});
$('.brand').addEventListener('click',event=>{event.preventDefault();changeView('discover');});
for(const [id,step] of [['page-previous',-1],['page-next',1]])$(`#${id}`).addEventListener('click',()=>{
  state.page+=step;render();$('#catalog-title').focus({preventScroll:true});$('.catalog-heading').scrollIntoView({block:'start'});
});
$('#search').addEventListener('input',event=>{state.search=event.target.value;render();});
$('#catalog-scope').addEventListener('change',event=>{if(['discover','history','trending','discovery','library'].includes(event.target.value))changeView(event.target.value);});
$('#agent-status-filter').addEventListener('change',event=>{if(event.target.value!=='all'&&!Object.hasOwn(AGENT_STATUSES,event.target.value))return;state.agentStatus=event.target.value;render();});
$('#function-filter').addEventListener('change',event=>{state.function=event.target.value;render();});
for(const key of ['kind','domain'])$(`#${key}-filter`).addEventListener('change',event=>{state[key]=event.target.value;render();});
$('#client-filter').addEventListener('change',event=>{if(!Object.hasOwn(clientLabels,event.target.value))return;state.client=event.target.value;render();});
$('#skills-only').addEventListener('change',event=>{state.skills=event.target.checked;render();});
$('#install-filter').addEventListener('change',event=>{state.install=event.target.value;render();});
$('#sort').addEventListener('change',event=>{state.sort=event.target.value;render();});
for(const layout of ['grid','list'])$(`#${layout}-view`).addEventListener('click',()=>{state.layout=layout;writeLocal('labskill-layout',layout);render();});
$('#feature-open').addEventListener('click',()=>{if(featuredId)openDetail(featuredId);});
$('#feature-save').addEventListener('click',()=>{if(featuredId)toggleSaved(featuredId);});
$('#help-button').addEventListener('click',()=>$('#help-dialog').showModal());
$('#workspace-button').addEventListener('click',()=>$('#help-dialog').showModal());
$('#shortcuts-button').addEventListener('click',()=>{$('#search').focus();$('#search').select();});
$('#reset-filters').addEventListener('click',()=>{const hasFilters=hasDetailFilters();if(['discovery','history'].includes(state.view)&&!hasFilters){refresh();return;}if(!repos.length&&state.view!=='library'){refresh();return;}if(state.view==='library')state.view='discover';clearFilters();render();});
$('#discovery-domain').addEventListener('change',event=>{if(!Object.hasOwn(discoveryProfiles,event.target.value))return;state.discoveryDomain=event.target.value;clearFilters();render();});
$('#discovery-button').addEventListener('click',refresh);
$('#history-resume').addEventListener('click',()=>historyCommand('process'));
$('#history-pause').addEventListener('click',()=>historyCommand('pause'));
$('#library-retry').addEventListener('click',loadLibrary);
$('#collection-select').addEventListener('change',event=>{state.collection=event.target.value;clearFilters();render();});
$('#collection-create').addEventListener('click',()=>openCollectionDialog('create'));
$('#collection-rename').addEventListener('click',()=>openCollectionDialog('rename'));
$('#collection-delete').addEventListener('click',()=>openCollectionDialog('delete'));
$('#close-collection-dialog').addEventListener('click',()=>$('#collection-dialog').close());
$('#collection-add-repo').addEventListener('click',()=>{const repoId=$('#collection-repo-select').value;if(repoId&&!libraryPending)saveLibrary({type:'membership',collectionId:state.collection,repoId,included:true},'컬렉션에 추가했습니다');});
$('#collection-form').addEventListener('submit',async event=>{
  event.preventDefault();if(libraryPending)return;
  const collectionId=collectionAction==='create'?crypto.randomUUID():collectionTarget,action={type:collectionAction,collectionId,name:$('#collection-name').value};
  if(collectionAction!=='delete'&&!action.name.trim()){$('#collection-form-error').textContent='컬렉션 이름을 입력해주세요.';$('#collection-form-error').hidden=false;return;}
  $('#collection-submit').disabled=true;
  const stored=await saveLibrary(action,collectionAction==='delete'?'컬렉션만 삭제했습니다 · 도구와 메모는 보관됩니다':collectionAction==='rename'?'컬렉션 이름을 저장했습니다':'컬렉션을 만들었습니다');
  if(stored){if(collectionAction==='create'){state.collection=collectionId;render();}$('#collection-dialog').close();}
  else{$('#collection-form-error').textContent=libraryError||'저장하지 못했습니다. 다시 시도해주세요.';$('#collection-form-error').hidden=false;}
  $('#collection-submit').disabled=false;
});
document.addEventListener('input',event=>{if(event.target.id==='personal-note'){noteDrafts.set(event.target.dataset.noteRepo,event.target.value);$('#note-count').textContent=`${[...event.target.value].length} / 4000`;}});
document.addEventListener('change',async event=>{
  if(!event.target.hasAttribute('data-detail-collection'))return;
  const input=event.target,collectionId=input.dataset.detailCollection,repoId=input.dataset.repoId;
  await saveLibrary({type:'membership',collectionId,repoId,included:input.checked},input.checked?'컬렉션에 추가하고 보관했습니다':'컬렉션에서 제거했습니다 · 도구는 보관됩니다');
  Array.from(document.querySelectorAll('[data-detail-collection]')).find(element=>element.dataset.detailCollection===collectionId)?.focus();
});
$('#add-repo-button').addEventListener('click',()=>{$('#add-repo-error').hidden=true;$('#add-repo-dialog').showModal();$('#add-repo-url').focus();});
$('#close-add-repo').addEventListener('click',()=>$('#add-repo-dialog').close());
$('#add-repo-form').addEventListener('submit',async event=>{
  event.preventDefault();if(manualSubmitting||pendingRepo)return;
  const parsed=parseRepositoryUrl($('#add-repo-url').value);
  if(!parsed){$('#add-repo-error').textContent='github.com/소유자/저장소 링크 또는 /tree/40자리 커밋 SHA 링크를 입력해주세요.';$('#add-repo-error').hidden=false;return;}
  manualSubmitting=true;$('#add-repo-error').hidden=true;renderStatus();
  try{
    const accepted=await postJSON('/api/repos',{url:parsed.url});
    pendingRepo={id:typeof accepted.id==='string'?accepted.id:parsed.id};apiError='';$('#add-repo-dialog').close();notify('저장소 추가를 시작했습니다. 목록은 계속 둘러볼 수 있습니다.');
    renderStatus();await poll();
  }catch(error){
    $('#add-repo-error').textContent=error.status===409?`이미 등록된 저장소이거나 다른 수집이 진행 중입니다. ${error.message}`:error.status===400?`GitHub 링크를 확인해주세요. ${error.message}`:`저장소를 추가하지 못했습니다. ${error.message}`;
    $('#add-repo-error').hidden=false;
    if(!$('#add-repo-dialog').open)notify($('#add-repo-error').textContent);
  }finally{manualSubmitting=false;renderStatus();}
});
$('#mobile-filters-button').addEventListener('click',()=>{const pool=typePool();$('#mobile-kind').innerHTML=allOptions(taxonomy.kinds,'kind',pool).map(({value,label})=>`<option value="${esc(value)}">${esc(label)}</option>`).join('');$('#mobile-install').innerHTML=$('#install-filter').innerHTML;$('#mobile-kind').value=state.kind;$('#mobile-install').value=state.install;$('#mobile-skills').checked=state.skills;$('#filter-dialog').showModal();});
$('#close-filters').addEventListener('click',()=>$('#filter-dialog').close());
$('#apply-mobile-filters').addEventListener('click',()=>{state.kind=$('#mobile-kind').value;state.install=$('#mobile-install').value;state.skills=$('#mobile-skills').checked;render();$('#filter-dialog').close();});
document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'&&!$('#add-repo-dialog').open&&!$('#collection-dialog').open){event.preventDefault();for(const selector of ['#detail-dialog','#help-dialog','#filter-dialog'])if($(selector).open)$(selector).close();$('#search').focus();$('#search').select();}if((event.metaKey||event.ctrlKey)&&['1','2'].includes(event.key)&&!document.querySelector('dialog[open]')){event.preventDefault();changeView(event.key==='1'?'discover':'library');}});

async function loadCatalog(){
  const [doc,table,discovery,history]=await Promise.all([getJSON('/api/catalog'),getJSON('/api/taxonomy'),getJSON('/api/discovery'),getJSON('/api/history')]);
  if(!Array.isArray(doc.repos)||!table.kinds||!table.domains||!table.install_methods)throw new Error('카탈로그 형식을 확인해주세요.');
  discoveryProfiles=Object.fromEntries(Object.entries(discovery.profiles||{}).filter(([key,profile])=>['code','lit','mat','data','verify'].includes(key)&&profile&&typeof profile.label==='string'&&typeof profile.description==='string'));
  if(!Object.hasOwn(discoveryProfiles,state.discoveryDomain))state.discoveryDomain=Object.keys(discoveryProfiles)[0]||'lit';
  catalog=doc;taxonomy=table;historySummary=history;repos=doc.repos.filter(entry=>entry&&typeof entry.id==='string').map(entry=>normalizeRepo(entry,table));loading=false;apiError='';render();
  if(currentDetail)renderDetail(currentDetail);
}

async function poll(){
  if(pollPromise)return pollPromise;
  clearTimeout(pollTimer);
  const pendingAtStart=pendingRepo;
  pollPromise=(async()=>{
    try{
      const previous=status;[status,historySummary]=await Promise.all([getJSON('/api/status'),getJSON('/api/history')]);apiError='';
      const addedFinished=pendingAtStart&&pendingAtStart===pendingRepo&&!status.running;
      if(addedFinished||(status.generated_at&&status.generated_at!==catalog.generated_at)||(previous?.running&&!status.running))await loadCatalog();
      if(addedFinished){
        const added=repos.find(repo=>repo.id.toLowerCase()===pendingRepo.id.toLowerCase()),id=pendingRepo.id;pendingRepo=null;
        if(added&&!status.last_error){$('#add-repo-url').value='';notify(`${id} 저장소를 추가했습니다.`);if(!document.querySelector('dialog[open]'))openDetail(added.id);}
        else{apiError=status.last_error||'저장소 정보를 가져오지 못했습니다. GitHub 링크와 연결 상태를 확인해주세요.';notify(`추가하지 못했습니다: ${apiError}`);}
      }
      renderStatus();if(!repos.length)renderCards(visibleRepos());
    }catch(error){apiError=`로컬 서버에 연결할 수 없습니다. 앱 실행 창을 확인해주세요. (${error.message})`;loading=false;render();}
  })();
  try{await pollPromise;}finally{pollPromise=null;pollTimer=setTimeout(poll,collectionBusy()?1800:15000);}
}

async function historyCommand(action){
  if(historyActionPending||(action==='process'&&(collectionBusy()||!historySummary?.available||!historySummary?.needs_resume)))return;
  historyActionPending=true;renderStatus();
  try{await getJSON(`/api/history/${action}`,{method:'POST',headers:{'Content-Type':'application/json','X-LabSkill-Request':'1'},body:'{}'});apiError='';await poll();}catch(error){apiError=error.message;notify(`트렌딩 기록 정리를 ${action==='pause'?'멈출':'이어갈'} 수 없습니다: ${error.message}`);}finally{historyActionPending=false;renderStatus();}
}

async function refresh(){
  if(state.view==='history')return historyCommand('process');
  if(collectionBusy())return;
  if(state.view==='discovery'&&!Object.hasOwn(discoveryProfiles,state.discoveryDomain))return;
  const request=state.view==='discovery'?{discovery_domain:state.discoveryDomain}:{};
  try{status=await getJSON('/api/refresh',{method:'POST',headers:{'Content-Type':'application/json','X-LabSkill-Request':'1'},body:JSON.stringify(request)});apiError='';render();await poll();}catch(error){apiError=error.message;renderStatus();notify(`수집을 시작할 수 없습니다: ${error.message}`);}
}
$('#refresh-button').addEventListener('click',refresh);
render();
await Promise.all([loadLibrary(),(async()=>{try{await loadCatalog();}catch(error){loading=false;apiError=`저장된 카탈로그를 불러오지 못했습니다: ${error.message}`;render();}})()]);
await poll();
