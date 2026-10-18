import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeRepo, filterRepos, optionsFor, functionOptions, escapeHtml, repoUrl, numberText } from '../../labskill-catalog/web/catalog-data.mjs';

const taxonomy={functions:{code:{label:'코드·개발'},literature:{label:'문헌 검색'},visualization:{label:'시각화'},ai:{label:'AI·에이전트'},other:{label:'기타·미분류'}},kinds:{app:{label:'앱'},skill:{label:'단일 스킬'}},domains:{code:{label:'코딩·개발'},lit:{label:'문헌·논문'}},install_methods:{manual:{label:'수동 설정'}}};
const entry={id:'owner/tool',title_ko:'도구',description:'Original description',summary_ko:'원문에 근거한 요약',kind:'app',domain:'code',subcategory:'역공학',install_method:'manual',stars:1234,stars_7d:12,skill_count:0,skills:[],summary_status:'needs_review',review_reason:'세부 분야 제안',in_current_trending:true,evidence:[{file:'README.md',quote:'The exact original sentence.'}]};

test('실제 카탈로그 값을 표시하되 원본 객체를 바꾸지 않는다',()=>{const before=structuredClone(entry);const repo=normalizeRepo(entry,taxonomy);assert.equal(repo.id,'owner/tool');assert.equal(repo.kindLabel,'앱');assert.equal(repo.subcategory,'역공학');assert.equal(repo.description,'원문에 근거한 요약');assert.equal(repo.stars,1234);assert.equal(repo.review,true);assert.equal(repo.status,'needs_review');assert.deepEqual(entry,before);assert.equal(repo.evidence[0].quote,'The exact original sentence.');});
test('분류 대기 항목에 종류·스타·스킬 수를 지어 넣지 않는다',()=>{const repo=normalizeRepo({id:'owner/pending',summary_status:'pending'},taxonomy);assert.equal(repo.kind,null);assert.equal(repo.kindLabel,'분류 대기');assert.equal(repo.stars,null);assert.equal(repo.skills,null);assert.equal(repo.description,'아직 저장소 설명이 없습니다.');});
test('사전에 없는 모델 문자열을 목록에서 보존하고 필터 옵션에 넣는다',()=>{const repo=normalizeRepo({...entry,kind:'새 종류',domain:'새 분야'},taxonomy);assert.equal(repo.kind,'새 종류');assert.equal(repo.kindLabel,'새 종류');const options=optionsFor(taxonomy.kinds,[repo],'kind');assert.ok(options.some(option=>option.value==='새 종류'&&option.count===1));});
test('객체 속성과 같은 이름의 미등록 분야도 고정된 커버를 사용한다',()=>{const repo=normalizeRepo({...entry,domain:'__proto__'},taxonomy);assert.equal(repo.cover,'code');});
test('검색·분야·종류·설치 방법·스킬 필터를 함께 적용한다',()=>{const repos=[normalizeRepo({...entry,kind:'skill',domain:'lit',title_ko:'논문 검색',skill_count:1,tags:['#arxiv']},taxonomy),normalizeRepo(entry,taxonomy)];assert.equal(filterRepos(repos,{view:'discover',search:'#arxiv',kind:'skill',domain:'lit',install:'manual',skills:true,sort:'trending'},new Set()).length,1);assert.equal(filterRepos(repos,{domain:'code',skills:true},new Set()).length,0);});
test('라이브러리와 검토 목록은 실제 상태를 따른다',()=>{const repos=[normalizeRepo(entry,taxonomy),normalizeRepo({...entry,id:'owner/done',summary_status:'ok',review_reason:''},taxonomy)];assert.equal(filterRepos(repos,{view:'library'},new Set(['owner/done']))[0].id,'owner/done');assert.equal(filterRepos(repos,{view:'review'},new Set()).length,1);});
test('지난주 보관 항목을 이번 주 트렌딩에 넣지 않는다',()=>{const repos=[normalizeRepo(entry,taxonomy),normalizeRepo({...entry,id:'owner/history',in_current_trending:false},taxonomy)];assert.equal(filterRepos(repos,{view:'trending'},new Set()).length,1);});
test('외부 저장소 문자열을 HTML로 실행하지 않는다',()=>{assert.equal(escapeHtml('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');});
test('GitHub 링크는 검증된 저장소 이름에서만 만든다',()=>{assert.equal(repoUrl('owner/tool'),'https://github.com/owner/tool');for(const id of ['javascript:alert(1)','../secrets','https://evil.test/a','owner/a?x=1','owner/a/b','owner/..','owner/.'])assert.equal(repoUrl(id),null,id);});
test('불완전한 근거 형식은 화면을 깨뜨리지 않는다',()=>{const repo=normalizeRepo({...entry,evidence:[null,'bad',{file:2,quote:'valid quote'}],skills:[null,{name:'skill',path:'skills/skill'}]},taxonomy);assert.equal(repo.evidence.length,1);assert.equal(repo.skillList.length,1);});
test('알 수 없는 수치는 대시로 표시하고 실제 음수 증가량은 보존한다',()=>{assert.equal(numberText(null),'—');assert.equal(numberText(0),'0');assert.equal(normalizeRepo({...entry,stars_7d:-3},taxonomy).growth,-3);});
test('분야별 발견 출처는 알려진 완전한 출처 문자열에서만 읽는다',()=>{const repo=normalizeRepo({...entry,sources:['weekly','discovery:lit','discovery:lit','discovery:code','discovery:unknown','discovery:lit:extra',null,{}]},taxonomy);assert.deepEqual(repo.discoveryDomains,['lit','code']);assert.equal(repo.domain,'code');assert.deepEqual(normalizeRepo(entry,taxonomy).discoveryDomains,[]);});
test('분야별 탐색은 추론된 분류가 아니라 실제 발견 출처로 필터링한다',()=>{const repos=[normalizeRepo({...entry,id:'owner/literature-source',domain:'code',sources:['discovery:lit']},taxonomy),normalizeRepo({...entry,id:'owner/literature-label',domain:'lit',sources:['discovery:code']},taxonomy),normalizeRepo({...entry,id:'owner/both',domain:'lit',sources:['discovery:lit','discovery:code']},taxonomy)];assert.deepEqual(filterRepos(repos,{view:'discovery',discoveryDomain:'lit',sort:'name'}).map(repo=>repo.id),['owner/literature-source','owner/both']);assert.equal(filterRepos(repos,{view:'discovery',discoveryDomain:'lit',domain:'lit'}).length,1);assert.equal(filterRepos(repos,{view:'discovery',discoveryDomain:'unknown'}).length,0);});
test('최근 업데이트순은 유효한 날짜를 앞에 두고 알 수 없는 날짜의 순서를 보존한다',()=>{const repos=[normalizeRepo({...entry,id:'owner/unknown-first',pushed_at:'not-a-date'},taxonomy),normalizeRepo({...entry,id:'owner/old',pushed_at:'2025-01-01T00:00:00Z'},taxonomy),normalizeRepo({...entry,id:'owner/unknown-second',pushed_at:''},taxonomy),normalizeRepo({...entry,id:'owner/new',pushed_at:'2026-10-18T00:00:00Z'},taxonomy)];assert.deepEqual(filterRepos(repos,{sort:'updated'}).map(repo=>repo.id),['owner/new','owner/old','owner/unknown-first','owner/unknown-second']);});
test('과거 트렌딩은 정확한 아카이브 출처와 실제 등장 정보를 보존한다',()=>{const repo=normalizeRepo({...entry,in_current_trending:false,sources:['archive:antonkomarev/github-trending-archive','discovery:lit'],trending_first_seen:'2026-04-18',trending_last_seen:'2026-10-17',appearance_days:9,best_daily_rank:2,trend_history:[{date:'2026-04-18',period:'daily'},{date:'2026-04-19',period:'daily'},{period:'unknown'},null]},taxonomy);assert.equal(repo.history,true);assert.equal(repo.historySource,'antonkomarev/github-trending-archive');assert.equal(repo.historyFirstSeen,'2026-04-18');assert.equal(repo.historyLastSeen,'2026-10-17');assert.equal(repo.appearanceDays,9);assert.equal(repo.bestDailyRank,2);assert.deepEqual(repo.historyPeriods,['daily']);assert.deepEqual(repo.discoveryDomains,['lit']);assert.equal(repo.current,false);});
test('날짜나 비슷한 출처 문자열만 있는 항목을 과거 트렌딩으로 만들지 않는다',()=>{for(const sources of [undefined,['archive:other/repo'],['archive:antonkomarev/github-trending-archive:extra']]){const repo=normalizeRepo({...entry,sources,trending_last_seen:'2026-10-17'},taxonomy);assert.equal(repo.history,false);assert.equal(repo.historySource,'');}const repo=normalizeRepo(entry,taxonomy);assert.equal(repo.appearanceDays,null);assert.equal(repo.historyLastSeen,'');});
test('기록 보기와 필터 개수는 실제 아카이브 출처의 저장소만 포함한다',()=>{const repos=[normalizeRepo({...entry,id:'owner/archive',sources:['archive:antonkomarev/github-trending-archive'],domain:'lit'},taxonomy),normalizeRepo({...entry,id:'owner/weekly',sources:['trending'],in_current_trending:true},taxonomy),normalizeRepo({...entry,id:'owner/discovery',sources:['discovery:lit'],in_current_trending:false},taxonomy)];const pool=filterRepos(repos,{view:'history'});assert.deepEqual(pool.map(repo=>repo.id),['owner/archive']);assert.equal(filterRepos(repos,{view:'history',domain:'code'}).length,0);assert.equal(optionsFor(taxonomy.domains,pool,'domain').find(option=>option.value==='lit').count,1);assert.equal(optionsFor(taxonomy.domains,pool,'domain').find(option=>option.value==='code').count,0);assert.equal(filterRepos(repos,{view:'trending'}).length,2);});
test('Python 규칙 분류 출처와 단서 문자열을 실행하거나 의미를 바꾸지 않고 보존한다',()=>{const matches=[{domain:'lit',subcategory:'문헌 검색·정리',keyword:'<img src=x onerror=alert(1)>',scope:'intro',score:4}];const repo=normalizeRepo({...entry,classification_backend:'python',classification_method:'python_rules',rule_matches:[...matches,null,{},'잘못된 문자열'],rule_confidence:'medium',confidence:'high'},taxonomy);assert.equal(repo.classificationBackend,'python');assert.equal(repo.classificationMethod,'python_rules');assert.deepEqual(repo.ruleMatches,matches);assert.equal(repo.confidence,'medium');});
test('규칙이 결정하지 못한 종류는 미분류이며 실제 결과가 없는 항목만 분류 대기다',()=>{const classified=normalizeRepo({...entry,classification_backend:'python',kind:null,summary_status:'pending',raw_classification:{kind:null}},taxonomy);assert.equal(classified.kindLabel,'미분류');assert.notEqual(classified.status,'pending');const waiting=normalizeRepo({id:'owner/waiting',classification_backend:'python',summary_status:'pending'},taxonomy);assert.equal(waiting.kindLabel,'분류 대기');assert.equal(waiting.status,'pending');const cached=normalizeRepo({...entry,classification_backend:'codex',classification_method:'codex_exec'},taxonomy);assert.equal(cached.classificationBackend,'codex');assert.equal(cached.classificationMethod,'codex_exec');});
test('종류 없는 필터는 미분류로 묶고 실제 대기 카드의 상태는 보존한다',()=>{const pending=normalizeRepo({id:'owner/waiting',summary_status:'pending'},taxonomy);const classified=normalizeRepo({...entry,id:'owner/unknown',classification_backend:'python',kind:null,summary_status:'ok',raw_classification:{kind:null}},taxonomy);const option=optionsFor(taxonomy.kinds,[pending,classified],'kind').find(item=>item.value==='__pending__');assert.equal(option.label,'미분류');assert.equal(option.count,2);assert.equal(pending.kindLabel,'분류 대기');assert.equal(classified.kindLabel,'미분류');assert.equal(filterRepos([pending,classified],{kind:'__pending__'}).length,2);});

test('별도 선별 결과를 표시하고 기존 분류와 원본 객체는 보존한다',()=>{
  const original={...entry,agent_catalog:{version:1,status:'selected',kind:'skill',domain:'lit',subcategory:'문헌 검색',title_ko:'문헌 스킬',summary_ko:'README 소개',clients:{codex:true,claude_code:null},reasons:['스킬 배포가 주목적'],evidence:[{file:'README.md',quote:'A skill for literature search.'}],classification_method:'python_agent_filter',checked_at:'2026-10-18T12:00:00Z'}};
  const before=structuredClone(original),repo=normalizeRepo(original,taxonomy);
  assert.equal(repo.agentStatus,'selected');assert.equal(repo.agentLabel,'스킬·플러그인');assert.equal(repo.kind,'skill');assert.equal(repo.domain,'lit');assert.equal(repo.subcategory,'문헌 검색');assert.equal(repo.name,'문헌 스킬');assert.equal(repo.description,'README 소개');assert.equal(repo.status,'ok');assert.equal(repo.classificationMethod,'python_agent_filter');assert.deepEqual(repo.agentClients,{codex:true,claude_code:null});assert.deepEqual(repo.agentReasons,['스킬 배포가 주목적']);assert.equal(repo.evidence[0].quote,'A skill for literature search.');assert.deepEqual(original,before);
});
test('부가 스킬과 자료 모음도 선별 상태를 보존하고 미확인에서 이전 분류를 덮어쓰지 않는다',()=>{
  for(const value of ['companion','reference','not_target'])assert.equal(normalizeRepo({...entry,agent_catalog:{version:1,status:value,kind:null,domain:null,evidence:[]}},taxonomy).agentStatus,value);
  const pending=normalizeRepo({...entry,agent_catalog:{version:1,status:'unconfirmed',kind:null,domain:null,clients:{codex:'yes',claude_code:false}}},taxonomy);
  assert.equal(pending.agentStatus,'unconfirmed');assert.equal(pending.kind,'app');assert.deepEqual(pending.agentClients,{codex:null,claude_code:false});
  for(const candidate of [null,[],{version:2,status:'selected'},{version:1,status:'other'}])assert.equal(normalizeRepo({...entry,agent_catalog:candidate},taxonomy).agentStatus,'unconfirmed');
});
test('선택적인 스킬 종류 필터와 전체 저장소 보기가 함께 동작한다',()=>{
  const repos=['selected','companion','reference','not_target','unconfirmed'].map((value,index)=>normalizeRepo({...entry,id:`owner/repo${index}`,agent_catalog:{version:1,status:value,kind:'skill',domain:'code'}},taxonomy));
  assert.deepEqual(filterRepos(repos,{view:'discover',agentStatus:'selected'}).map(repo=>repo.id),['owner/repo0']);
  assert.equal(filterRepos(repos,{agentStatus:'all'}).length,5);
  assert.equal(filterRepos(repos,{agentStatus:'companion'}).length,1);
  assert.equal(filterRepos(repos,{agentStatus:'reference',view:'trending'}).length,1);
  assert.equal(filterRepos(repos,{agentStatus:'unconfirmed',view:'library'},new Set(['owner/repo4'])).length,1);
  assert.equal(filterRepos(repos,{agentStatus:'selected',domain:'lit'}).length,0);
});
test('지원 앱 필터는 README 기반의 명시적 true만 사용한다',()=>{
  const combinations=[{codex:true,claude_code:true},{codex:true,claude_code:null},{codex:null,claude_code:true},{codex:null,claude_code:null},{codex:false,claude_code:false}];
  const repos=combinations.map((clients,index)=>normalizeRepo({...entry,id:`owner/client${index}`,supports_codex:true,agent_catalog:{version:1,status:'selected',clients}},taxonomy));
  assert.equal(filterRepos(repos,{client:'codex'}).length,2);assert.equal(filterRepos(repos,{client:'claude_code'}).length,2);assert.equal(filterRepos(repos,{client:'either'}).length,3);assert.equal(filterRepos(repos,{client:'both'}).length,1);assert.deepEqual(filterRepos(repos,{client:'unconfirmed'}).map(repo=>repo.id),['owner/client3']);
  assert.equal(filterRepos([normalizeRepo({...entry,supports_codex:true},taxonomy)],{client:'codex'}).length,0);
});

test('선별 요약이 짧아져도 원본 설명·세부 분야·분야 이름으로 검색한다',()=>{
  const repo=normalizeRepo({...entry,id:'acme/research',description:'PubMed literature search skills',agent_catalog:{version:1,status:'selected',kind:'skill',domain:'lit',subcategory:'문헌 검색·정리',summary_ko:'스킬 배포가 주목적입니다.'}},taxonomy);
  for(const search of ['PubMed','문헌 검색','문헌·논문'])assert.equal(filterRepos([repo],{agentStatus:'selected',search}).length,1,search);
  assert.equal(filterRepos([repo],{agentStatus:'selected',search:'없는 단어'}).length,0);
});


test('기능 분류는 별도 결과에서 읽고 스킬 분류와 원본을 보존한다',()=>{
  const original={...entry,function_catalog:{version:1,primary:'literature',functions:['literature','ai','literature'],confidence:'high',matched:[{function:'literature',keyword:'PubMed',source:'description'}]},agent_catalog:{version:1,status:'selected',kind:'skill',domain:'code',summary_ko:'스킬 배포'}};
  const before=structuredClone(original),repo=normalizeRepo(original,taxonomy);
  assert.deepEqual(repo.functions,['literature','ai']);assert.deepEqual(repo.functionLabels,['문헌 검색','AI·에이전트']);assert.equal(repo.primaryFunction,'literature');assert.equal(repo.functionConfidence,'high');assert.deepEqual(repo.functionMatches,[{function:'literature',keyword:'PubMed',source:'description'}]);assert.equal(repo.kind,'skill');assert.equal(repo.domain,'code');assert.deepEqual(original,before);
});
test('기능 결과가 없는 모든 원본과 손상된 기능 결과도 기타 목록에서 접근한다',()=>{
  for(const function_catalog of [undefined,null,[],{version:2,functions:['code']},{version:1,functions:['missing',null,'__proto__']}]){
    const repo=normalizeRepo({...entry,function_catalog},taxonomy);
    assert.deepEqual(repo.functions,['other']);assert.equal(repo.primaryFunction,'other');assert.deepEqual(repo.functionLabels,['기타·미분류']);assert.equal(filterRepos([repo],{function:'other'}).length,1);
  }
  assert.deepEqual(normalizeRepo(entry).functions,['other']);assert.deepEqual(functionOptions({},[normalizeRepo(entry)]),[{value:'other',label:'기타·미분류',count:1}]);
});
test('여러 기능을 중복 집계하고 기능·출처·검색·지원 앱·북마크 필터를 함께 적용한다',()=>{
  const first=normalizeRepo({...entry,id:'owner/research',description:'PubMed toolkit',sources:['archive:antonkomarev/github-trending-archive'],function_catalog:{version:1,primary:'literature',functions:['literature','ai'],confidence:'medium'},agent_catalog:{version:1,status:'not_target',clients:{codex:true}}},taxonomy);
  const second=normalizeRepo({...entry,id:'owner/visual',in_current_trending:false,function_catalog:{version:1,primary:'visualization',functions:['visualization','ai'],confidence:'high'}},taxonomy);
  const third=normalizeRepo({...entry,id:'owner/legacy'},taxonomy),repos=[first,second,third];
  assert.equal(filterRepos(repos,{}).length,3);assert.equal(filterRepos(repos,{function:'ai'}).length,2);assert.equal(filterRepos(repos,{function:'literature',view:'history',search:'PubMed',client:'codex'}).length,1);assert.equal(filterRepos(repos,{function:'literature',view:'library'},new Set([first.id])).length,1);assert.equal(filterRepos(repos,{function:'visualization',view:'trending'}).length,0);assert.equal(filterRepos(repos,{function:'literature',agentStatus:'selected'}).length,0);assert.equal(filterRepos(repos,{search:'시각화'}).length,1);
  const counts=functionOptions(taxonomy.functions,repos);assert.equal(counts.find(item=>item.value==='ai').count,2);assert.equal(counts.find(item=>item.value==='literature').count,1);assert.equal(counts.find(item=>item.value==='other').count,1);assert.equal(counts.find(item=>item.value==='code').count,0);
});
test('미분류 기능은 스킬 비대상 템플릿 대신 저장소 원래 설명을 표시한다',()=>{
  const repo=normalizeRepo({...entry,description:'A plotting library',agent_catalog:{version:1,status:'not_target',summary_ko:'스킬·플러그인 배포가 주목적이 아닙니다.'}},taxonomy);
  assert.equal(repo.description,'A plotting library');assert.equal(repo.originalDescription,'A plotting library');
});


test('기능 주 분류와 단서는 알려진 기능과 실제 문자열만 사용한다',()=>{
  const repo=normalizeRepo({...entry,function_catalog:{version:1,primary:'unknown',functions:['visualization','code'],confidence:'certain',matched:[null,'bad',{function:'unknown',keyword:'ignored',source:'description'},{function:'visualization',keyword:2},{function:'visualization',keyword:'<script>',source:'README'}]}},taxonomy);
  assert.equal(repo.primaryFunction,'visualization');assert.equal(repo.functionConfidence,'low');assert.deepEqual(repo.functionMatches,[{function:'visualization',keyword:'<script>',source:'README'}]);
  const withoutTable=normalizeRepo({...entry,function_catalog:{version:1,primary:'code',functions:['code'],confidence:'medium'}});
  assert.deepEqual(withoutTable.functionLabels,['코드·개발']);assert.deepEqual(functionOptions({},[withoutTable]),[{value:'code',label:'코드·개발',count:1}]);
});


test('부가 스킬·참고 자료는 스킬 판정 템플릿 대신 저장소 목적을 보여준다',()=>{
  for(const status of ['companion','reference','not_target']){
    const repo=normalizeRepo({...entry,title_ko:'논문 PDF에 질문하는 도구',description:'Chat with research papers',function_catalog:{version:1,primary:'literature',functions:['literature'],confidence:'high'},agent_catalog:{version:1,status,kind:'agent_tool',domain:'code',title_ko:'tool · 부가 스킬 포함',summary_ko:'스킬 파일은 있으나 주목적은 일반 도구입니다.',reasons:['주목적은 일반 도구입니다.']}},taxonomy);
    assert.equal(repo.name,'논문 PDF에 질문하는 도구');assert.equal(repo.description,'Chat with research papers');assert.equal(repo.kind,'agent_tool');assert.equal(repo.agentReasons[0],'주목적은 일반 도구입니다.');
  }
});


test('파일을 읽지 않은 빈 신호와 실제 확인한 0개를 구분한다',()=>{
  const unknown=normalizeRepo({...entry,skill_count:null,file_signals_date:null,file_signals:{plugin_manifests:[],mcp_files:[]}},taxonomy);
  assert.equal(unknown.signalsAvailable,false);assert.equal(unknown.skills,null);
  for(const known of [{skill_count:0},{skill_count:null,file_signals_date:'2026-10-18'},{skill_count:null,file_count:0}]){
    const repo=normalizeRepo({...entry,...known,file_signals:{plugin_manifests:[],mcp_files:[]}},taxonomy);
    assert.equal(repo.signalsAvailable,true);assert.equal(repo.status,unknown.status);
  }
});
