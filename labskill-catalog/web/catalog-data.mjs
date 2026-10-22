const text=value=>typeof value==='string'?value:'';
const numeric=value=>typeof value==='number'&&Number.isFinite(value)?value:null;
const label=(table,value,missing='분류 대기')=>value==null?missing:Object.hasOwn(table||{},value)?text(table[value]?.label)||value:value;
const COVERS={lit:'papers',mat:'research',data:'code',verify:'papers',code:'agents'};
export const FUNCTIONS={code:'코드·개발',literature:'문헌 검색',visualization:'시각화',data:'데이터 분석',ai:'AI·에이전트',search:'검색·자료 수집',automation:'자동화',productivity:'문서·업무',media:'이미지·영상·음성',infrastructure:'서버·배포',security:'보안·역공학',science:'과학·공학',learning:'학습·자료',devices:'기기·시스템',other:'기타·미분류'};
const HISTORY_SOURCE='antonkomarev/github-trending-archive';
export const AGENT_STATUSES={selected:'스킬·플러그인',companion:'부가 스킬',reference:'가이드·자료 모음',not_target:'일반 저장소',unconfirmed:'미확인'};
const updatedTime=repo=>{const timestamp=Date.parse(repo.pushedAt);return Number.isFinite(timestamp)?timestamp:null;};

function matchesClient(repo,client){
  const codex=repo.agentClients?.codex,claude=repo.agentClients?.claude_code;
  if(!client||client==='all')return true;
  if(client==='codex')return codex===true;
  if(client==='claude_code')return claude===true;
  if(client==='either')return codex===true||claude===true;
  if(client==='both')return codex===true&&claude===true;
  return client==='unconfirmed'&&codex!==true&&claude!==true&&(codex==null||claude==null);
}

export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}

export function repoUrl(id){
  if(typeof id!=='string'||! /^[A-Za-z0-9][A-Za-z0-9-]*\/[A-Za-z0-9._-]+$/.test(id))return null;
  if(['.','..'].includes(id.split('/')[1]))return null;
  return `https://github.com/${id}`;
}

export function numberText(value){if(numeric(value)===null)return '—';return Math.abs(value)>=1000?`${(value/1000).toFixed(1).replace(/\.0$/,'')}k`:String(value);}

export function normalizeRepo(entry,taxonomy={}){
  const candidate=entry.agent_catalog;
  const agent=candidate&&candidate.version===1&&Object.hasOwn(AGENT_STATUSES,candidate.status)?candidate:null;
  const agentStatus=agent?.status||'unconfirmed',agentAssessed=!!agent&&agentStatus!=='unconfirmed';
  const originalEntry=entry;
  const functionCandidate=entry.function_catalog;
  const functionCatalog=functionCandidate&&functionCandidate.version===1&&!Array.isArray(functionCandidate)?functionCandidate:null;
  const functions=[...new Set((Array.isArray(functionCatalog?.functions)?functionCatalog.functions:[]).filter(value=>typeof value==='string'&&(Object.hasOwn(FUNCTIONS,value)||Object.hasOwn(taxonomy.functions||{},value))))];
  if(!functions.length)functions.push('other');
  const functionLabels=functions.map(value=>text(taxonomy.functions?.[value]?.label)||FUNCTIONS[value]||value);
  const primaryFunction=functions.includes(functionCatalog?.primary)?functionCatalog.primary:functions[0];
  if(agentAssessed){
    entry={...entry};
    for(const key of ['kind','domain','subcategory',...(agentStatus==='selected'?['title_ko','summary_ko']:[])])if(Object.hasOwn(agent,key))entry[key]=agent[key];
    entry.evidence=agent.evidence;
  }
  const kind=typeof entry.kind==='string'?entry.kind:null;
  const domain=typeof entry.domain==='string'?entry.domain:null;
  const install=typeof entry.install_method==='string'?entry.install_method:null;
  const skillList=(Array.isArray(entry.skills)?entry.skills:[]).filter(skill=>skill&&typeof skill==='object').map(skill=>({name:text(skill.name)||text(skill.path)||'이름 없음',description:text(skill.description),path:text(skill.path),hasScripts:skill.has_scripts===true}));
  const evidence=(Array.isArray(entry.evidence)?entry.evidence:[]).filter(item=>item&&typeof item.quote==='string').map(item=>({file:text(item.file),quote:item.quote}));
  const summaryStatus=text(entry.summary_status)||'pending';
  const skills=numeric(entry.skill_count);
  const classificationBackend=agentAssessed?'python':text(entry.classification_backend),classificationMethod=agentAssessed?'python_agent_filter':text(entry.classification_method);
  const hasPythonResult=classificationBackend==='python'&&entry.raw_classification&&typeof entry.raw_classification==='object'&&!Array.isArray(entry.raw_classification);
  const status=agentAssessed||summaryStatus==='ok'?'ok':summaryStatus==='pending'&&!hasPythonResult?'pending':'needs_review';
  const missingLabel=classificationBackend==='python'&&status!=='pending'?'미분류':'분류 대기';
  const sources=Array.isArray(entry.sources)?entry.sources:[];
  const history=sources.includes(`archive:${HISTORY_SOURCE}`);
  return {
    id:text(entry.id),repo:text(entry.id),url:repoUrl(entry.id),name:text(entry.title_ko)||text(entry.id),
    description:(agentAssessed&&agentStatus!=='selected'?text(originalEntry.description)||text(originalEntry.summary_ko):'')||text(entry.summary_ko)||text(entry.description)||'아직 저장소 설명이 없습니다.',
    originalDescription:text(originalEntry.description),functions,functionLabels,primaryFunction,functionConfidence:['high','medium','low'].includes(functionCatalog?.confidence)?functionCatalog.confidence:'low',
    functionMatches:(Array.isArray(functionCatalog?.matched)?functionCatalog.matched:[]).filter(match=>match&&functions.includes(match.function)&&typeof match.keyword==='string').map(match=>({function:match.function,keyword:match.keyword,source:text(match.source)})),
    kind,kindLabel:label(taxonomy.kinds,kind,missingLabel),domain,domainLabel:label(taxonomy.domains,domain,missingLabel),
    subcategory:text(entry.subcategory),install,installLabel:label(taxonomy.install_methods,install,missingLabel),
    classificationBackend,classificationMethod,ruleMatches:(Array.isArray(entry.rule_matches)?entry.rule_matches:[]).filter(match=>match&&typeof match==='object'&&typeof match.keyword==='string').map(match=>({domain:text(match.domain),subcategory:text(match.subcategory),keyword:match.keyword,scope:text(match.scope),score:numeric(match.score)})),confidence:text(entry.rule_confidence),
    agentStatus,agentLabel:AGENT_STATUSES[agentStatus],agentAssessed,agentChecked:!!agent,agentReasons:(Array.isArray(agent?.reasons)?agent.reasons:[]).filter(reason=>typeof reason==='string'),agentCheckedAt:text(agent?.checked_at),
    agentClients:{codex:typeof agent?.clients?.codex==='boolean'?agent.clients.codex:null,claude_code:typeof agent?.clients?.claude_code==='boolean'?agent.clients.claude_code:null},
    stars:numeric(entry.stars),growth:numeric(entry.stars_7d),skills,skillList,evidence,
    tags:(Array.isArray(entry.tags)?entry.tags:[]).filter(tag=>typeof tag==='string'),
    review:summaryStatus!=='ok'||!!entry.review_reason,status,reviewReason:text(entry.review_reason),
    evidenceValid:!agentAssessed&&originalEntry.evidence_valid===true,installEvidence:entry.install_evidence&&typeof entry.install_evidence.quote==='string'?entry.install_evidence:null,
    language:text(entry.language),license:text(entry.license),commit:text(entry.commit),
    pushedAt:text(entry.pushed_at),fetchedAt:text(entry.fetched_at)||text(entry.last_seen),catalogUpdatedAt:text(entry.catalog_updated_at),
    current:entry.in_current_trending===true,rank:numeric(entry.trending?.weekly_rank),
    discoveryDomains:[...new Set(sources.filter(source=>typeof source==='string'&&source.startsWith('discovery:')&&Object.hasOwn(COVERS,source.slice(10))).map(source=>source.slice(10)))],
    history,historySource:history?HISTORY_SOURCE:'',historyFirstSeen:text(entry.trending_first_seen),historyLastSeen:text(entry.trending_last_seen),appearanceDays:numeric(entry.appearance_days),bestDailyRank:numeric(entry.best_daily_rank),
    historyPeriods:[...new Set((Array.isArray(entry.trend_history)?entry.trend_history:[]).map(item=>item?.period).filter(period=>['daily','weekly'].includes(period)))],
    cover:Object.hasOwn(COVERS,domain)?COVERS[domain]:'code',
    wordmark:text(entry.id).split('/').slice(1).join('/')||'Repository',
    subtitle:text(entry.id).split('/')[0],signals:entry.file_signals&&typeof entry.file_signals==='object'?entry.file_signals:{},signalsAvailable:!!text(entry.file_signals_date)||skills!==null||numeric(entry.file_count)!==null,
    warnings:Array.isArray(entry.prescan?.warnings)?entry.prescan.warnings:[],
  };
}

export function filterRepos(repos,state={},saved=new Set()){
  const query=text(state.search).toLowerCase().replace(/^#/,'');
  return repos.filter(repo=>
    (state.view!=='library'||saved.has(repo.id))&&(state.view!=='review'||repo.review)&&(state.view!=='trending'||repo.current)&&
    (state.view!=='discovery'||repo.discoveryDomains?.includes(state.discoveryDomain))&&
    (state.view!=='history'||repo.history===true)&&
    (!state.agentStatus||state.agentStatus==='all'||repo.agentStatus===state.agentStatus)&&
    matchesClient(repo,state.client)&&
    (!state.function||state.function==='all'||repo.functions?.includes(state.function))&&
    (!state.kind||state.kind==='all'||(state.kind==='__pending__'?repo.kind==null:repo.kind===state.kind))&&
    (!state.domain||state.domain==='all'||(state.domain==='__pending__'?repo.domain==null:repo.domain===state.domain))&&
    (!state.install||state.install==='all'||(state.install==='__pending__'?repo.install==null:repo.install===state.install))&&
    (!state.skills||repo.skills>0)&&`${repo.name} ${repo.repo} ${repo.description} ${repo.originalDescription} ${(repo.functionLabels||[]).join(' ')} ${repo.domainLabel} ${repo.subcategory} ${repo.tags.join(' ')}`.toLowerCase().includes(query)
  ).sort((a,b)=>state.sort==='name'?a.name.localeCompare(b.name,'ko'):state.sort==='stars'?(b.stars??-1)-(a.stars??-1):state.sort==='updated'?((updatedTime(b)??-Infinity)-(updatedTime(a)??-Infinity)||0):Number(b.current)-Number(a.current)||(b.current&&a.current&&a.rank!=null&&b.rank!=null?a.rank-b.rank:(b.growth??-Infinity)-(a.growth??-Infinity))||(b.stars??-1)-(a.stars??-1));
}

export function paginateRepos(repos,page=1){
  const total=repos.length,pageCount=Math.max(1,Math.ceil(total/60));
  const current=Math.min(pageCount,Math.max(1,Number.isInteger(page)?page:1)),offset=(current-1)*60;
  return {items:repos.slice(offset,offset+60),page:current,pageCount,total,start:total?offset+1:0,end:Math.min(offset+60,total)};
}

export function historyCoverageText(coverage){
  if(!Number.isInteger(coverage?.expected_days)||coverage.expected_days<=0||!Number.isInteger(coverage.available_days)||coverage.available_days<0||!Array.isArray(coverage.missing_dates)||coverage.available_days+coverage.missing_dates.length!==coverage.expected_days)return '';
  return `${coverage.available_days}/${coverage.expected_days}일 기록 · 원본 없는 날짜 ${coverage.missing_dates.length}일`;
}

export function optionsFor(table={},repos=[],key){
  const result=Object.entries(table).map(([value,item])=>({value,label:text(item?.label)||value,count:repos.filter(repo=>repo[key]===value).length}));
  for(const repo of repos){const value=repo[key]??'__pending__';if(!result.some(option=>option.value===value))result.push({value,label:value==='__pending__'?'미분류':value,count:repos.filter(item=>(item[key]??'__pending__')===value).length});}
  return result;
}

export function functionOptions(table={},repos=[]){
  const values=[...new Set([...Object.keys(table),...repos.flatMap(repo=>repo.functions||['other'])])];
  return values.map(value=>({value,label:text(table[value]?.label)||FUNCTIONS[value]||value,count:repos.filter(repo=>repo.functions?.includes(value)).length}));
}

export function isCatalogNew(repo,now=Date.now()){
  const updated=Date.parse(repo.catalogUpdatedAt);
  return Number.isFinite(updated)&&updated<=now&&now-updated<=7*24*60*60*1000;
}

export function parseRepositoryUrl(value){
  try{
    const input=String(value).trim(),url=new URL(input.includes('://')?input:`https://${input}`);
    if(url.protocol!=='https:'||url.hostname!=='github.com'||url.port||url.username||url.password||url.search||url.hash)return null;
    const match=url.pathname.replace(/\/$/,'').match(/^\/([^/]+\/[^/]+)(?:\/tree\/([a-fA-F0-9]{40}))?$/);
    if(!match||!repoUrl(match[1]))return null;
    return {id:match[1],url:`${repoUrl(match[1])}${match[2]?`/tree/${match[2]}`:''}`};
  }catch{return null;}
}

export function normalizeLibrary(document){
  const fail=()=>{throw new Error('라이브러리 파일 형식을 확인해주세요.');};
  if(!document||document.schema_version!==1||!Array.isArray(document.saved_ids)||!Array.isArray(document.collections)||!document.notes||typeof document.notes!=='object'||Array.isArray(document.notes))fail();
  const ids=values=>{if(!Array.isArray(values)||values.some(id=>!repoUrl(id)))fail();return [...new Set(values)];};
  const collectionIds=new Set();
  const collections=document.collections.map(collection=>{
    if(!collection||typeof collection.id!=='string'||!collection.id||collectionIds.has(collection.id)||typeof collection.name!=='string'||!collection.name.trim())fail();
    collectionIds.add(collection.id);
    return {id:collection.id,name:collection.name.trim(),repo_ids:ids(collection.repo_ids)};
  });
  const notes=Object.fromEntries(Object.entries(document.notes).map(([id,note])=>{if(!repoUrl(id)||typeof note!=='string'||[...note].length>4000)fail();return [id,note];}));
  return {schema_version:1,saved_ids:[...new Set([...ids(document.saved_ids),...collections.flatMap(collection=>collection.repo_ids)])],collections,notes};
}

export function mergeLegacySaved(document,legacy){
  const result=normalizeLibrary(document);
  result.saved_ids=[...new Set([...result.saved_ids,...(Array.isArray(legacy)?legacy:[]).filter(id=>repoUrl(id))])];
  return result;
}

export function changeLibrary(document,action){
  const result=normalizeLibrary(document),collection=result.collections.find(item=>item.id===action.collectionId);
  if(['saved','membership','note'].includes(action.type)&&!repoUrl(action.repoId))throw new Error('저장소 이름을 확인해주세요.');
  if(['rename','delete','membership'].includes(action.type)&&!collection)throw new Error('컬렉션을 찾을 수 없습니다.');
  if(['create','rename'].includes(action.type)){
    const name=typeof action.name==='string'?action.name.trim():'';
    if(!name)throw new Error('컬렉션 이름을 입력해주세요.');
    if(action.type==='create'){
      if(typeof action.collectionId!=='string'||!action.collectionId||collection)throw new Error('컬렉션 이름을 다시 입력해주세요.');
      result.collections.push({id:action.collectionId,name,repo_ids:[]});
    }else collection.name=name;
  }else if(action.type==='delete')result.collections=result.collections.filter(item=>item.id!==action.collectionId);
  else if(action.type==='saved'){
    result.saved_ids=action.included?[...new Set([...result.saved_ids,action.repoId])]:result.saved_ids.filter(id=>id!==action.repoId);
    if(!action.included)for(const item of result.collections)item.repo_ids=item.repo_ids.filter(id=>id!==action.repoId);
  }else if(action.type==='membership'){
    collection.repo_ids=action.included?[...new Set([...collection.repo_ids,action.repoId])]:collection.repo_ids.filter(id=>id!==action.repoId);
    if(action.included)result.saved_ids=[...new Set([...result.saved_ids,action.repoId])];
  }else if(action.type==='note'){
    if(typeof action.note!=='string'||[...action.note].length>4000)throw new Error('메모는 4000자까지 저장할 수 있습니다.');
    if(action.note)result.notes[action.repoId]=action.note;else delete result.notes[action.repoId];
  }else throw new Error('라이브러리 변경 내용을 확인해주세요.');
  return result;
}

export function createLibraryStore(initial,persist){
  let document=normalizeLibrary(initial),queue=Promise.resolve();
  return {
    get:()=>structuredClone(document),
    update(change){
      const operation=queue.then(async()=>{const next=normalizeLibrary(change(structuredClone(document)));const stored=normalizeLibrary(await persist(next));document=stored;return structuredClone(stored);});
      queue=operation.catch(()=>{});
      return operation;
    },
  };
}
