export interface Project {id:string; name:string; customer:string; enterprise:string; volume:string; generation:number; baseline_id:string}
export interface Revision {id:string; logical_id:string; kind:string; payload:Record<string,unknown>; blob_hash:string}
export interface Run {id:string; status:string; revision:number; outcome:string|null}
export interface Task {id:string; status:string; run_id:string; error:string|null; family_id:string; contract:Record<string,unknown>}
export interface Candidate {id:string; task_id:string; status:string; payload:{blocks:{block_id:string;text:string}[]}; blob_hash:string}
export interface Workspace {project:Project;revisions:Revision[];runs:Run[];tasks:Task[];candidates:Candidate[];
  receipts:{id:string;layer:string;status:string;checks:Record<string,unknown>}[];
  budget:{requests:number;max_requests:number;max_cost:number;charged:number;held:number;unknown:number}}

export async function request<T>(path:string, body?:unknown, signal?:AbortSignal):Promise<T> {
  const response=await fetch(`/api${path}`,{method:body===undefined?'GET':'POST',signal,
    headers:{'content-type':'application/json','x-bid-local':'1'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error??data.detail??`请求失败 ${response.status}`);
  return data;
}

export const actionId=()=>crypto.randomUUID();
