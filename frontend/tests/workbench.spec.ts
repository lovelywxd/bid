import {test,expect,type Page} from '@playwright/test';

async function project(page:Page,name:string){
  await page.goto('/');
  await page.getByLabel('新项目名称').fill(name);
  await page.getByRole('button',{name:'创建合成项目'}).click();
  await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
}
async function source(page:Page){
  await page.getByRole('button',{name:'资料与版本',exact:true}).click();
  await page.getByLabel('来源原文').fill('合成测试：服务期三年；未经批准，不得自动承诺。');
  await page.getByRole('button',{name:'保存合成来源'}).click();
  await expect(page.getByText('合成测试：服务期三年；未经批准，不得自动承诺。',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'运行与候选',exact:true}).click();
}

test('创建、合成来源、真实 Harness 组合、事件与刷新恢复',async({page})=>{
  const name=`浏览器正常-${Date.now()}`;
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await project(page,name);
  await expect(page.getByRole('button',{name:'运行合成检查'})).toBeDisabled();
  await source(page);
  await page.getByRole('button',{name:'运行合成检查'}).click();
  await expect(page.getByRole('heading',{name:'工程任务完成',exact:true})).toBeVisible();
  await expect(page.getByText('工程候选已核对，适用范围：工程协议检查')).toBeVisible();
  await expect(page.getByText('task.committed',{exact:true})).toBeVisible();
  await expect(page.getByText('未运行',{exact:true})).toHaveCount(2);
  await page.screenshot({path:'../evals/results/stage1/workbench-desktop.png',fullPage:true});
  await page.reload();
  await expect(page.getByRole('heading',{name,exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'工程任务完成',exact:true})).toBeVisible();
  await expect(page.getByText('task.committed',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('慢请求取消后无候选提交',async({page})=>{
  await project(page,`浏览器取消-${Date.now()}`);await source(page);
  await page.getByLabel('场景').selectOption('slow');
  await page.getByRole('button',{name:'运行合成检查'}).click();
  await expect(page.getByRole('heading',{name:'执行中',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  await expect(page.getByRole('heading',{name:'已取消',exact:true})).toBeVisible();
  await expect(page.locator('.candidate-sheet')).toHaveCount(0);
});

test('项目切换隔离、网络错误可见、窄屏可操作',async({page})=>{
  const first=`浏览器隔离甲-${Date.now()}`,second=`浏览器隔离乙-${Date.now()}`;
  await project(page,first);await source(page);
  await page.getByLabel('新项目名称').fill(second);
  await page.getByRole('button',{name:'创建合成项目'}).click();
  await expect(page.getByRole('heading',{name:second,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'运行合成检查'})).toBeDisabled();
  await page.getByLabel('当前项目').selectOption({label:first});
  await expect(page.getByRole('heading',{name:first,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'运行合成检查'})).toBeEnabled();
  await page.route('**/api/projects/*/runs',route=>route.fulfill({status:409,
    contentType:'application/json',body:JSON.stringify({error:'REVISION_CONFLICT'})}));
  await page.getByRole('button',{name:'运行合成检查'}).click();
  await expect(page.getByRole('alert')).toContainText('REVISION_CONFLICT');
  await page.getByRole('button',{name:'关闭错误提示'}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'执行设置',exact:true}).click();
  await expect(page.getByRole('heading',{name:'当前执行配置'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:'../evals/results/stage1/workbench-mobile.png',fullPage:true});
});
