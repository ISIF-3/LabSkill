import test from 'node:test';
import assert from 'node:assert/strict';
import * as data from '../../labskill-catalog/web/catalog-data.mjs';

const rows=count=>Array.from({length:count},(_,index)=>({id:`owner/repo${index}`,name:`도구 ${index}`}));

test('빈 결과와 정확히 60개인 결과는 잘못된 범위나 빈 다음 페이지를 만들지 않는다',()=>{
  assert.equal(typeof data.paginateRepos,'function');
  assert.deepEqual(data.paginateRepos([],9),{items:[],page:1,pageCount:1,total:0,start:0,end:0});
  const result=data.paginateRepos(rows(60),2);
  assert.equal(result.page,1);assert.equal(result.pageCount,1);assert.equal(result.start,1);assert.equal(result.end,60);assert.equal(result.items.length,60);
});

test('페이지마다 최대 60개만 반환하고 마지막 부분 페이지와 범위를 정확히 계산한다',()=>{
  assert.equal(typeof data.paginateRepos,'function');
  const source=rows(121),before=structuredClone(source),middle=data.paginateRepos(source,2),last=data.paginateRepos(source,3);
  assert.equal(middle.items.length,60);assert.equal(middle.items[0].id,'owner/repo60');assert.equal(middle.start,61);assert.equal(middle.end,120);
  assert.deepEqual(last,{items:[source[120]],page:3,pageCount:3,total:121,start:121,end:121});
  assert.deepEqual(source,before);
  for(const page of [0,-2,NaN,Infinity,1.5])assert.equal(data.paginateRepos(source,page).page,1);
  assert.equal(data.paginateRepos(source,999).page,3);
});

test('수천 개의 전체 목록에서 검색·정렬한 뒤 페이지를 나누며 기능 개수는 전체 기준이다',()=>{
  assert.equal(typeof data.paginateRepos,'function');
  const repos=rows(2005).map((entry,index)=>data.normalizeRepo({...entry,title_ko:entry.name,stars:index,sources:['archive:antonkomarev/github-trending-archive'],function_catalog:{version:1,primary:'code',functions:['code']}}));
  const all=data.filterRepos(repos,{view:'history',sort:'stars'}),page=data.paginateRepos(all,2);
  assert.equal(page.total,2005);assert.equal(page.pageCount,34);assert.equal(page.items.length,60);assert.equal(page.items[0].id,'owner/repo1944');
  assert.equal(data.functionOptions({},all).find(option=>option.value==='code').count,2005);
  const search=data.paginateRepos(data.filterRepos(repos,{view:'history',search:'repo1000',sort:'stars'}),1);
  assert.equal(search.total,1);assert.equal(search.items[0].id,'owner/repo1000');
});

test('수집으로 결과가 늘어나면 현재 페이지를 유지하고 보관 취소로 마지막 페이지가 사라지면 보정한다',()=>{
  assert.equal(typeof data.paginateRepos,'function');
  const repos=rows(121).map(entry=>data.normalizeRepo(entry)),saved=new Set(repos.slice(0,61).map(repo=>repo.id));
  const library=data.filterRepos(repos,{view:'library'},saved),last=data.paginateRepos(library,2);
  assert.equal(library.length,61);assert.equal(last.items.length,1);
  saved.delete(last.items[0].id);
  const removed=data.paginateRepos(data.filterRepos(repos,{view:'library'},saved),last.page);
  assert.equal(removed.page,1);assert.equal(removed.total,60);
  const grown=data.paginateRepos(repos,last.page);
  assert.equal(grown.page,2);assert.equal(grown.total,121);assert.equal(grown.items.length,60);
});

test('기록 범위 옆에 원본이 있는 날짜 수와 빠진 날짜 수를 표시한다',()=>{
  assert.equal(typeof data.historyCoverageText,'function');
  assert.equal(data.historyCoverageText({expected_days:366,available_days:365,nonempty_days:365,missing_dates:['2026-10-22']}),'365/366일 기록 · 원본 없는 날짜 1일');
  assert.equal(data.historyCoverageText({expected_days:2,available_days:2,missing_dates:[]}),'2/2일 기록 · 원본 없는 날짜 0일');
});

test('coverage가 없는 이전 기록이나 잘못된 수치에는 날짜 수를 만들어 표시하지 않는다',()=>{
  assert.equal(typeof data.historyCoverageText,'function');
  for(const coverage of [undefined,null,{}, {expected_days:366,available_days:'365',missing_dates:['2026-10-22']}, {expected_days:366,available_days:365,missing_dates:[]}, {expected_days:0,available_days:0,missing_dates:[]}])assert.equal(data.historyCoverageText(coverage),'');
});
