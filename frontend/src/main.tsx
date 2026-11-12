import React, {useCallback, useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {actionId, request, type Project, type Run, type Workspace} from './api';
import './style.css';

const labels:Record<string,string>={queued:'等待执行',running:'执行中',paused:'已暂停',waiting_input:'待处理',
  finished:'工程任务完成',cancelled:'已取消',stale:'输入已变化',succeeded:'工程检查通过',failed:'执行失败',
  candidate:'候选',accepted:'工程候选已核对',rejected:'候选未通过',passed:'已通过',not_run:'未运行',
  program:'程序检查',semantic:'独立语义审核',human:'人工验收'};

function App(){
  const [projects,setProjects]=useState<Project[]>([]);
  const [selected,setSelected]=useState('');
  const [workspace,setWorkspace]=useState<Workspace|null>(null);
  const [page,setPage]=useState('运行与候选');
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [events,setEvents]=useState<{id:number;kind:string;payload:unknown}[]>([]);
  const [projectName,setProjectName]=useState('');
  const [sourceText,setSourceText]=useState('服务期为三年；仅在用户确认后生效，未经批准不得增加承诺。');
  const [scenario,setScenario]=useState('normal');
  const cursors=useRef<Record<string,number>>({});
  const eventCache=useRef<Record<string,{id:number;kind:string;payload:unknown}[]>>({});
  const loadTicket=useRef(0);
  const selection=useRef(selected); selection.current=selected;
  const load=useCallback(async(projectId:string,signal?:AbortSignal)=>{
    const ticket=++loadTicket.current;
    const value=await request<Workspace>(`/projects/${projectId}/workspace`,undefined,signal);
    if(selection.current===projectId&&ticket===loadTicket.current) setWorkspace(value);
  },[]);
  useEffect(()=>{const abort=new AbortController();
    request<Project[]>('/projects',undefined,abort.signal).then(items=>{setProjects(items);
      const saved=localStorage.getItem('bid-project');
      setSelected(items.find(item=>item.id===saved)?.id??items[0]?.id??'');})
      .catch(e=>{if(!abort.signal.aborted)setError(String(e));});return()=>abort.abort();},[]);
  useEffect(()=>{if(!selected)return;localStorage.setItem('bid-project',selected);
    const abort=new AbortController();setWorkspace(null);setEvents(eventCache.current[selected]??[]);
    load(selected,abort.signal).catch(e=>{if(!abort.signal.aborted)setError(String(e));});
    const params=new URLSearchParams({after:String(cursors.current[selected]??0)});
    const source=new EventSource(`/api/projects/${selected}/events?${params}`);
    const receive=(event:MessageEvent)=>{if(selection.current!==selected)return;
      const row=JSON.parse(event.data);cursors.current[selected]=row.id;
      const next=[...(eventCache.current[selected]??[]),row].slice(-30);eventCache.current[selected]=next;
      setEvents(next);load(selected,abort.signal).catch(e=>{if(!abort.signal.aborted)setError(String(e));});};
    source.addEventListener('business',receive);return()=>{abort.abort();source.close();};},[selected,load]);

  async function act(work:()=>Promise<void>){setBusy(true);setError('');try{await work();}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function createProject(event:React.FormEvent){event.preventDefault();await act(async()=>{
    const result=await request<{id:string}>('/projects',{name:projectName,customer:'合成客户',enterprise:'合成企业'});
    setProjects(await request<Project[]>('/projects'));setSelected(result.id);setProjectName('');});}
  async function addSource(event:React.FormEvent){event.preventDefault();const target=selected;await act(async()=>{
    await request(`/projects/${target}/revisions`,{request_id:actionId(),logical_id:`source-${actionId()}`,kind:'source',
      payload:{synthetic:true,text:sourceText,locator:'人工录入的合成工程资料'},actor:'本机用户',reason:'导入合成工程资料'});
    await load(target);});}
  async function runProbe(){if(!workspace)return;const target=selected;
    const sourceIds=workspace.revisions.filter(r=>r.kind==='source').slice(-8).map(r=>r.id);
    await act(async()=>{await request(`/projects/${target}/runs`,{request_id:actionId(),expected_generation:workspace.project.generation,
      source_ids:sourceIds,scenario});await load(target);});}
  async function control(run:Run,action:string){const target=selected;await act(async()=>{
    await request(`/projects/${target}/runs/${run.id}/control`,{request_id:actionId(),expected_revision:run.revision,action});await load(target);});}

  return <div className="workbench">
    <header className="app-header"><div><span className="brand-mark" aria-hidden="true">标</span><strong>标书工作台</strong></div>
      <span className="environment">本机工程验收 / 合成资料</span><span className="release-state">真实业务验收未运行</span></header>
    <nav className="project-rail" aria-label="项目导航"><h2>项目</h2>
      <label className="field-label" htmlFor="project-select">当前项目</label>
      <select id="project-select" value={selected} onChange={e=>setSelected(e.target.value)}>
        {!projects.length&&<option value="">尚未创建项目</option>}
        {projects.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select>
      <form onSubmit={createProject}><label htmlFor="project-name">新项目名称</label>
        <input id="project-name" value={projectName} onChange={e=>setProjectName(e.target.value)} maxLength={120} required/>
        <button disabled={busy||!projectName.trim()}>创建合成项目</button></form>
      <div className="page-nav">{['运行与候选','资料与版本','执行设置','交付验收'].map(name=><button key={name}
        aria-current={page===name?'page':undefined} onClick={()=>setPage(name)}>{name}</button>)}</div>
      <p className="rail-note">资料、版本和验收分别保存。任务结束后仍需完成内容、文件和人工验收。</p>
    </nav>
    <main><div className="project-heading"><div><p className="context-label">{workspace?.project.volume??'技术卷工程底座'}</p>
      <h1>{workspace?.project.name??'开始一个项目'}</h1><p>{workspace?`当前资料基线 ${workspace.project.generation}，所有候选绑定此次输入。`:'创建项目后添加合成资料，验证任务执行与恢复。'}</p></div></div>
      {error&&<div role="alert" className="error-banner">{error}<button onClick={()=>setError('')} aria-label="关闭错误提示">关闭</button></div>}
      {workspace&&page==='运行与候选'&&<>
        <section className="command-strip"><div><h2>执行工程检查</h2><p>实际运行固定 Harness、读取来源并保存候选。</p></div>
          <label>场景<select value={scenario} onChange={e=>setScenario(e.target.value)}>
            <option value="normal">正常提交</option><option value="retry">临时故障与重试</option>
            <option value="slow">慢请求与取消</option><option value="bad_reference">无效引用拒绝</option>
            <option value="forbidden_tool">越权工具拒绝</option></select></label>
          <button className="primary" onClick={runProbe} disabled={busy||!workspace.revisions.some(r=>r.kind==='source')}>运行合成检查</button></section>
        {!workspace.revisions.some(r=>r.kind==='source')&&<p className="notice">请先在“资料与版本”添加合成来源。</p>}
        <section><h2>任务与候选</h2>{!workspace.runs.length&&<div className="empty-state"><h3>尚未运行任务</h3><p>先保存来源，再运行合成检查。真实标书生成将在后续阶段接入。</p></div>}
          {workspace.runs.slice().reverse().map(run=><article className="run-record" key={run.id}>
            <div className="run-heading"><h3>{labels[run.status]??run.status}</h3><span className="short-id">{run.id.slice(0,8)}</span>
              <div className="run-actions">{!['finished','failed','cancelled'].includes(run.status)&&<>
                {run.status==='paused'||run.status==='waiting_input'?<button disabled={busy} onClick={()=>control(run,'resume')}>恢复</button>
                  :<button disabled={busy} onClick={()=>control(run,'pause')}>暂停</button>}
                <button disabled={busy} onClick={()=>control(run,'cancel')}>取消</button></>}</div></div>
            {workspace.tasks.filter(t=>t.run_id===run.id).map(task=><div key={task.id}>
              {task.error&&<p className="task-error">停止原因：{task.error}</p>}
              <details><summary>查看本次任务范围</summary><pre>{JSON.stringify(task.contract,null,2)}</pre></details>
              {workspace.candidates.filter(c=>c.task_id===task.id).map(candidate=><div className="candidate-sheet" key={candidate.id}>
                <p className="candidate-status">{labels[candidate.status]??candidate.status}，适用范围：工程协议检查</p>
                {candidate.payload.blocks.map(block=><p key={block.block_id}>{block.text}</p>)}
                <small>文件指纹 {candidate.blob_hash.slice(0,16)}</small></div>)}
            </div>)}
          </article>)}</section>
        <section><h2>分层检查记录</h2>{workspace.receipts.length?<ul className="receipts">{workspace.receipts.map(r=><li key={r.id}>
          <span>{labels[r.layer]}</span><span className={`status-${r.status}`}>{labels[r.status]}</span></li>)}</ul>:<p>尚无检查记录。模型输出不会自动登记为已验收。</p>}</section>
      </>}
      {workspace&&page==='资料与版本'&&<section><h2>合成资料</h2><p>本阶段仅导入带合成标识的文字。每次保存形成独立版本并使旧输入失效。</p>
        <form className="source-form" onSubmit={addSource}><label htmlFor="source-text">来源原文</label>
          <textarea id="source-text" rows={6} value={sourceText} onChange={e=>setSourceText(e.target.value)} required maxLength={12000}/>
          <button className="primary" disabled={busy||!sourceText.trim()}>保存合成来源</button></form>
        {workspace.revisions.filter(r=>r.kind==='source').map(r=><article className="source-record" key={r.id}>
          <h3>{r.logical_id}</h3><p>{String(r.payload.text)}</p><small>来源编号 {r.id}</small></article>)}</section>}
      {workspace&&page==='执行设置'&&<section><h2>当前执行配置</h2><dl className="settings-list">
        <dt>执行底座</dt><dd>DeepSeek Harness 0.2.2-rc.2，固定源码构建</dd><dt>模型</dt><dd>本机确定性替身，未配置真实提供商</dd>
        <dt>外发范围</dt><dd>仅本机合成资料，图片及 Files 用途关闭</dd><dt>预算</dt><dd>上限 {workspace.budget.max_requests} 次发送，{workspace.budget.max_cost} 合成计量单位</dd>
        <dt>真实模型能力</dt><dd>未测试，不能启动真实调用</dd></dl></section>}
      {workspace&&page==='交付验收'&&<section><h2>当前版本尚不可放行</h2><p>工程检查只验证运行协议。资料导入、设计、写作、独立审核、编辑和文件导出将在第二阶段接通。</p>
        <ul className="receipts">{['真实内容验收','Word / PDF 与全页检查','具名人工最终放行'].map(x=><li key={x}><span>{x}</span><span>未运行</span></li>)}</ul></section>}
    </main>
    <aside className="activity-panel" aria-label="运行详情"><h2>运行详情</h2><p className="context-label">{workspace?'当前项目':'等待项目'}</p>
      <section className="budget"><h3>请求与预算</h3><p>{workspace?.budget.requests??0} / {workspace?.budget.max_requests??0} 次发送</p>
        <progress max={workspace?.budget.max_requests||1} value={workspace?.budget.requests??0}/>
        <dl><dt>已结算</dt><dd>{workspace?.budget.charged??0}</dd><dt>预留及未知</dt><dd>{workspace?.budget.held??0}</dd>
          <dt>未知用量</dt><dd>{workspace?.budget.unknown??0} 笔</dd></dl><small>合成计量单位，未产生模型费用。</small></section>
      <h3>持久事件</h3><ol className="event-list">{events.map(event=><li key={event.id}><span>{event.kind}</span><small>事件 {event.id}</small></li>)}</ol>
      {!events.length&&<p>执行动作后显示记录。断线重连会从已保存的事件位置补读。</p>}
    </aside>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
