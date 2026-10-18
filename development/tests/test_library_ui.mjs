import test from 'node:test';
import assert from 'node:assert/strict';
import * as data from '../../labskill-catalog/web/catalog-data.mjs';

const empty=()=>({schema_version:1,saved_ids:[],collections:[],notes:{}});

test('새 표시에는 카탈로그 내용 갱신 시각만 사용하며 7일과 미래 시각을 구분한다',()=>{
  assert.equal(typeof data.isCatalogNew,'function');
  const now=Date.parse('2026-10-18T12:00:00Z');
  assert.equal(data.isCatalogNew(data.normalizeRepo({id:'a/b',catalog_updated_at:'2026-10-11T12:00:00Z'}),now),true);
  for(const timestamp of [undefined,'invalid','2026-10-11T11:59:59Z','2026-10-18T12:00:01Z'])assert.equal(data.isCatalogNew(data.normalizeRepo({id:'a/b',catalog_updated_at:timestamp,pushed_at:'2026-10-18T11:00:00Z',fetched_at:'2026-10-18T12:00:00Z'}),now),false);
});

test('GitHub 저장소 링크와 고정 커밋 링크만 추가 입력으로 받는다',()=>{
  assert.equal(typeof data.parseRepositoryUrl,'function');
  assert.deepEqual(data.parseRepositoryUrl(' github.com/Owner/tool/ '),{id:'Owner/tool',url:'https://github.com/Owner/tool'});
  const commit='a'.repeat(40);
  assert.deepEqual(data.parseRepositoryUrl(`https://github.com/a/b/tree/${commit}`),{id:'a/b',url:`https://github.com/a/b/tree/${commit}`});
  for(const url of ['https://evil.test/a/b','https://github.com/a/b/tree/main','https://github.com/a/b/issues','https://github.com/a/b?x=1','https://user@github.com/a/b','http://github.com/a/b','https://github.com/a/..'])assert.equal(data.parseRepositoryUrl(url),null,url);
});

test('브라우저 북마크를 서버 북마크와 합치며 알 수 없는 저장소도 잃지 않는다',()=>{
  assert.equal(typeof data.mergeLegacySaved,'function');
  const original={...empty(),saved_ids:['server/tool'],collections:[{id:'c1',name:'논문',repo_ids:['collection/tool']}],notes:{'memo/tool':'기억'}};
  const result=data.mergeLegacySaved(original,['browser/tool','server/tool','gone/tool','bad']);
  assert.deepEqual(result.saved_ids,['server/tool','collection/tool','browser/tool','gone/tool']);
  assert.deepEqual(original.saved_ids,['server/tool']);
  assert.equal(result.notes['memo/tool'],'기억');
});

test('컬렉션에 넣으면 보관하고 보관 해제는 모든 컬렉션에서만 제거하며 메모는 보존한다',()=>{
  assert.equal(typeof data.changeLibrary,'function');
  let doc={...empty(),collections:[{id:'c1',name:'논문',repo_ids:[]},{id:'c2',name:'분석',repo_ids:[]}],notes:{'a/tool':'개인 메모'}};
  doc=data.changeLibrary(doc,{type:'membership',collectionId:'c1',repoId:'a/tool',included:true});
  doc=data.changeLibrary(doc,{type:'membership',collectionId:'c2',repoId:'a/tool',included:true});
  assert.deepEqual(doc.saved_ids,['a/tool']);
  doc=data.changeLibrary(doc,{type:'membership',collectionId:'c1',repoId:'a/tool',included:false});
  assert.deepEqual(doc.saved_ids,['a/tool']);
  doc=data.changeLibrary(doc,{type:'saved',repoId:'a/tool',included:false});
  assert.ok(doc.collections.every(collection=>collection.repo_ids.length===0));
  assert.equal(doc.notes['a/tool'],'개인 메모');
});

test('컬렉션 이름 변경과 삭제는 북마크와 메모를 보존하고 메모는 4000자까지 저장한다',()=>{
  assert.equal(typeof data.changeLibrary,'function');
  const original={...empty(),saved_ids:['a/tool'],collections:[{id:'c1',name:'논문',repo_ids:['a/tool']}],notes:{'a/tool':'보존'}};
  const renamed=data.changeLibrary(original,{type:'rename',collectionId:'c1',name:' 새 이름 '});
  assert.equal(renamed.collections[0].name,'새 이름');assert.equal(original.collections[0].name,'논문');
  const deleted=data.changeLibrary(renamed,{type:'delete',collectionId:'c1'});
  assert.deepEqual(deleted,{...empty(),saved_ids:['a/tool'],notes:{'a/tool':'보존'}});
  assert.equal(data.changeLibrary(deleted,{type:'note',repoId:'a/tool',note:'가'.repeat(4000)}).notes['a/tool'].length,4000);
  assert.throws(()=>data.changeLibrary(deleted,{type:'note',repoId:'a/tool',note:'가'.repeat(4001)}));
  assert.throws(()=>data.changeLibrary(deleted,{type:'create',collectionId:'c2',name:' '}));
});

test('서버 문서가 손상되었으면 빈 문서로 덮어쓰지 않는다',()=>{
  assert.equal(typeof data.normalizeLibrary,'function');
  for(const doc of [null,{}, {...empty(),schema_version:2},{...empty(),saved_ids:'bad'},{...empty(),collections:[{id:'c',name:'n',repo_ids:'bad'}]}])assert.throws(()=>data.normalizeLibrary(doc));
});

test('빠른 연속 변경은 마지막 저장 상태에 순서대로 적용하고 실패 뒤에도 이어간다',async()=>{
  assert.equal(typeof data.createLibraryStore,'function');
  let release;
  const firstWrite=new Promise(resolve=>release=resolve),writes=[];
  const store=data.createLibraryStore(empty(),async document=>{writes.push(structuredClone(document));if(writes.length===1)await firstWrite;if(writes.length===2)throw new Error('disk full');return document;});
  const first=store.update(doc=>data.changeLibrary(doc,{type:'saved',repoId:'a/one',included:true}));
  const second=store.update(doc=>data.changeLibrary(doc,{type:'saved',repoId:'a/two',included:true}));
  const third=store.update(doc=>data.changeLibrary(doc,{type:'note',repoId:'a/one',note:'남길 메모'}));
  const rejected=assert.rejects(second,/disk full/);
  await Promise.resolve();assert.equal(writes.length,1);release();
  await first;await rejected;await third;
  assert.deepEqual(store.get().saved_ids,['a/one']);
  assert.equal(store.get().notes['a/one'],'남길 메모');
  assert.deepEqual(writes[2].saved_ids,['a/one']);
});
