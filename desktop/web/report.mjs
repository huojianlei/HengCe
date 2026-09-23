import {kpiNames} from './fields.mjs';
const printExtras='@page{@bottom-center{content:"衡策 · 内容为 AI 生成，仅供参考 · 第 " counter(page) " 页";font-family:"Microsoft YaHei";font-size:8px;color:#8598a5}}@media print{.foot{display:none}th,td{font-size:9px}.chart-legend{margin-bottom:10px}}';
export const esc=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const money=value=>value==null?'—':(value/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
export const pct=value=>value==null?'—':`${(value/100).toFixed(2)}%`;
const colors=['#148f96','#657fd0','#e6ac54','#a882b5','#93a6b4'];
export const color=value=>/^#[0-9a-f]{6}$/i.test(value||'')?value:'#8ea7b5';
export function table(headers,rows,classes=[]){return `<div class="table-wrap"><table><thead><tr>${headers.map((x,i)=>`<th class="${classes[i]||''}">${esc(x)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${row.map((x,i)=>`<td class="${classes[i]||''}">${x}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}" class="muted">暂无数据，请在对应参数区补充</td></tr>`}</tbody></table></div>`;}
function legend(items){return `<div class="chart-legend">${items.map(([c,t])=>`<span><i style="background:${c}"></i>${esc(t)}</span>`).join('')}</div>`;}
export function trend(result,selected){
 const r=result.rolling.find(x=>x.kemu===selected)||result.rolling[0];if(!r)return '<p>暂无趋势数据</p>';
 const rows=r.qijian_mingxi,max=Math.max(1,...rows.flatMap(x=>[x.shuzhi_fen,x.chushi_yusuan_fen]));
 const X=i=>65+i*520/Math.max(1,rows.length-1),Y=v=>205-v/max*163;
 let svg=`<svg viewBox="0 0 640 255" role="img" aria-label="${esc(r.kemu)}滚动预算趋势"><rect width="640" height="255" fill="white"/>`;
 for(let i=0;i<5;i++){const y=42+i*40.75;svg+=`<line x1="65" y1="${y}" x2="605" y2="${y}" stroke="#eaf0f4"/><text x="54" y="${y+4}" text-anchor="end" fill="#8799a6" font-size="10">${(max*(4-i)/4/10000/100).toFixed(1)}</text>`;}
 svg+='<text x="17" y="24" fill="#9aa8b5" font-size="10">万元</text>';
 for(const [key,c,dash] of [['chushi_yusuan_fen','#99aebd','5 5'],['shuzhi_fen','#148f96','']]){
 svg+=`<polyline points="${rows.map((r,i)=>`${X(i)},${Y(r[key])}`).join(' ')}" fill="none" stroke="${c}" stroke-width="2.5" stroke-dasharray="${dash}"/>`;
 rows.forEach((r,i)=>{svg+=`<circle cx="${X(i)}" cy="${Y(r[key])}" r="4" fill="${c}"><title>${esc(r.qijian)} ${money(r[key])} 元</title></circle>`;});}
 rows.forEach((r,i)=>{svg+=`<text x="${X(i)}" y="230" text-anchor="middle" fill="#718797" font-size="10">${esc(r.qijian)}</text>`;});
 return svg+'</svg>'+legend([['#148f96',`${r.kemu} · 滚动值（届满期为实际）`],['#99aebd','原始预算']]);
}
export function pie(result){
 const rows=result.blocks.mokuai_lie.map(x=>({name:x.mokuai,value:x.zhanbi_bps??0,amount:x.chae_fen}));
 if(result.blocks.weiguishu_zhanbi_bps)rows.push({name:'未归属',value:result.blocks.weiguishu_zhanbi_bps});
 let offset=0;const circumference=2*Math.PI*72;
 let svg='<svg viewBox="0 0 460 255" role="img" aria-label="模块净差异绝对值占比"><circle cx="130" cy="119" r="72" fill="none" stroke="#edf2f5" stroke-width="27"/>';
 rows.forEach((x,i)=>{const size=x.value/10000*circumference;if(size)svg+=`<circle cx="130" cy="119" r="72" fill="none" stroke="${colors[i]}" stroke-width="27" stroke-dasharray="${size} ${circumference-size}" stroke-dashoffset="${-offset}" transform="rotate(-90 130 119)"><title>${esc(x.name)} ${pct(x.value)}</title></circle>`;offset+=size;
 svg+=`<rect x="251" y="${43+i*35}" width="8" height="8" rx="2" fill="${colors[i]}"/><text x="267" y="${51+i*35}" fill="#657d8c" font-size="12">${esc(x.name)}</text><text x="433" y="${51+i*35}" text-anchor="end" font-size="12" fill="#294659">${pct(x.value)}</text>`;});
 svg+=`<text x="130" y="113" text-anchor="middle" fill="#21465b" font-size="24">${result.blocks.zhanbi_fenmu_fen===0?'—':'100%'}</text><text x="130" y="137" text-anchor="middle" fill="#93a4af" font-size="10">净差异绝对值占比</text></svg>`;
 return svg+'<p class="muted">占比基于各模块净差额绝对值；有利与不利方向见明细表。</p>';
}
export function heat(result){
 const periods=[...new Set(result.variance.xiang.map(x=>x.qijian))].sort();
 const names=[...new Set(result.variance.xiang.map(x=>x.kemu))];
 return table(['科目 / 期间',...periods],names.map(name=>[esc(name),...periods.map(period=>{
 const row=result.variance.xiang.find(x=>x.kemu===name&&x.qijian===period);
 if(!row)return '—';const c=row.yujing==='无'?'#e7f4ef':color(row.yan_se);
 return `<div class="heat-cell" style="background:${c};color:${row.yujing==='无'?'#3a8c7d':'#182c3e'}">${pct(row.chalv_bps)} · ${esc(row.yujing)}</div>`;})]));
}
export function comparison(result){
 const sorted=[...result.variance.xiang].sort((a,b)=>(b.chalv_bps??-1)-(a.chalv_bps??-1));
 return table(['排名','期间','科目','固定预算（元）','届满前滚动基准','实际（元）','差额（元）','差异率','方向','预警'],sorted.map((x,i)=>[i+1,esc(x.qijian),esc(x.kemu),money(x.chushi_fen),money(x.gundong_fen),money(x.shiji_fen),money(x.chae_fen),pct(x.chalv_bps),`<span class="${x.fa==='A'?'negative':'positive'}">${x.fa==='A'?'不利':x.fa==='F'?'有利':'持平'}</span>`,`<span class="badge" style="border-left:3px solid ${color(x.yan_se)}">${esc(x.yujing)}</span>`]),['','','','num','num','num','num','num']);
}
export function bscChart(result){
 const b=result.bsc;if(!b)return '<p class="muted">待补充四维达成率，暂不评分。</p>';
 const names=['财务','客户','内部流程','学习成长'],values=[b.caijing_bps,b.kehu_bps,b.neibu_bps,b.xuexi_bps],max=Math.max(10000,...values);
 return `<div class="bsc-score"><strong>${b.zongfen}</strong> 分 · ${esc(b.dengji)}</div>`+table(['维度','达成率','权重','达成表现'],names.map((n,i)=>[n,pct(values[i]),`${b.quanzhong[i]}%`,`<div class="progress-bar"><i style="width:${values[i]/max*100}%"></i></div>`]))+'<p class="muted">得分不封顶；图形长度按最大达成率缩放。</p>';
}
export function kpiTable(result){return table(['指标','结果'],Object.entries(result.kpi).map(([key,value],i)=>[kpiNames[i],value==null?'待补充':key.endsWith('_bps')?(key.includes('zhouzhuan')?`${(value/10000).toFixed(4)} 次`:pct(value)):`${value} ${key.includes('tian')?'天':'次'}`]));}
export function decisionsTable(result){return table(['期间','科目','判定','纠错要求','人工审批'],result.decisions.map(x=>[esc(x.period),esc(x.kemu),esc(x.panduan),esc(x.jiuzheng)+(x.beizhu?`<br><small>${esc(x.beizhu)}</small>`:''),x.shenpi?'需要':'无需']));}
export function correctionTable(result,interactive=false){return table(['事项','科目 / 期间','优先级','整改要求','状态'],result.correction.qingdan.map(x=>[esc(x.leixing),`${esc(x.kemu)}<br>${esc(x.qijian)}`,esc(x.youxianji),esc(x.miaoshu),interactive?`<select aria-label="${esc(x.kemu)}整改状态" data-action-id="${esc(x.id)}">${['待整改','进行中','已完成'].map(s=>`<option ${s===x.zhuangtai?'selected':''}>${s}</option>`).join('')}</select>`:esc(x.zhuangtai)]));}
export function progress(result){const c=result.correction,total=c.zong_shu,rate=total?c.wancheng_shu/total*100:0;return `<div class="progress-caption">${c.wancheng_shu} / ${total} 项已完成 <b>${rate.toFixed(0)}%</b></div><div class="progress-bar"><i style="width:${rate}%"></i></div>`;}
export function dashboard(result,selected){
 const revenue=result.variance.xiang.filter(x=>x.fangxiang==='收入类').reduce((sum,x)=>sum+x.shiji_fen,0);
 const alerts=result.variance.xiang.filter(x=>!['无','—'].includes(x.yujing)).length;
 return `<div class="metrics">${[['累计实际收入',money(revenue),'元 · 截至 '+result.meta.period],['预警项目',alerts,'含有利与不利差异'],['BSC 综合评分',result.bsc?.zongfen??'—',result.bsc?.dengji??'等待四维数据'],['待处理整改',result.correction.zong_shu-result.correction.wancheng_shu,'项 · 进入复核与整改处理']].map(([label,val,note])=>`<div class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(val)}</div><div class="metric-note">${esc(note)}</div></div>`).join('')}</div>
 ${result.warnings.length?`<div class="warn">${result.warnings.map(esc).join('；')}。</div>`:''}
 <div class="charts"><article class="card"><div class="card-heading"><h2>滚动预算趋势</h2><select id="trend-subject" aria-label="趋势图科目" style="width:150px;margin:0">${result.rolling.map(x=>`<option ${x.kemu===selected?'selected':''}>${esc(x.kemu)}</option>`).join('')}</select></div>${trend(result,selected)}</article><article class="card"><h2>模块差异占比</h2>${pie(result)}</article></div>
 <div class="card"><div class="card-heading"><h2>预算执行对比</h2><span class="small-label">差异率降序 · 金额单位：元</span></div>${comparison(result)}</div><div class="charts"><div class="card"><h2>风险预警热力图</h2>${heat(result)}</div><div class="card"><h2>平衡计分卡</h2>${bscChart(result)}</div></div><div class="card"><h2>整改完成进度</h2>${progress(result)}</div>`;
}
const reportCss=`*{box-sizing:border-box}body{font:12px/1.75 "Microsoft YaHei","Segoe UI",sans-serif;color:#294253;background:#eaf0f4;margin:0}.paper{max-width:1050px;margin:25px auto;background:white;padding:55px 55px 40px}h1{font-size:30px;letter-spacing:1px;margin:10px 0 17px}h2{font-size:18px;margin:30px 0 17px;padding-bottom:10px;border-bottom:2px solid #178b94;break-after:avoid}h3{font-size:14px;break-after:avoid}p{line-height:1.9}small,.muted{color:#7c8e9c;font-size:10px}.eyebrow{color:#148f96;letter-spacing:3px;font-size:11px}.cover{padding-bottom:25px;border-bottom:1px solid #dce6ec}.meta{display:flex;gap:25px;color:#667f90;font-size:11px;flex-wrap:wrap}.table-wrap{width:100%;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:10px;table-layout:auto}th{text-align:left;background:#eef4f6;font-weight:500;color:#587184}td,th{padding:9px 7px;border-bottom:1px solid #e5edf1}tr{break-inside:avoid}thead{display:table-header-group}th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.chart{break-inside:avoid}.chart svg{width:100%;height:auto}.chart-legend{display:flex;gap:13px;font-size:10px}.chart-legend i{display:inline-block;width:7px;height:7px;margin-right:5px}.positive{color:#188c78}.negative{color:#be5555}.badge{padding:2px 5px;background:#f0f4f6}.heat-cell{padding:5px;text-align:center}.progress-bar{height:8px;background:#edf2f4;border-radius:4px;overflow:hidden}.progress-bar i{display:block;height:100%;background:#148f96}.progress-caption{display:flex;justify-content:space-between;margin:12px 0}.bsc-score strong{font-size:28px;color:#148f96}.warn{padding:15px;background:#fff7e4;color:#8c7542}.ref{border-left:3px solid #d4e6e8;padding:7px 15px;margin:12px 0;break-inside:avoid}.ref p{margin:4px 0}.foot{margin-top:35px;border-top:1px solid #dce6ec;padding-top:15px;color:#889aa6;font-size:10px}a{color:#147f8d;text-decoration:none}.split-label{font-size:11px}.no-data{color:#8596a2;padding:12px;background:#f5f8fa}@page{size:A4;margin:15mm 12mm 17mm}@media print{body{background:white;font-size:10px;-webkit-print-color-adjust:exact;print-color-adjust:exact}.paper{padding:0;margin:0;max-width:none}h1{font-size:25px}h2{margin-top:23px}td,th{padding:6px 5px;font-size:8px}table{font-size:8px}.grid{gap:17px}.chart svg{max-height:230px}a{color:inherit}.ref{break-inside:auto}}`;
export function reportHTML(r){
 if(!r)return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><body style="font:14px Microsoft YaHei;padding:40px;color:#789">请先导入数据并运行分析，报告将在这里生成。</body></html>';
 const rollingRows=r.rolling.flatMap(s=>s.qijian_mingxi.map(x=>[esc(s.kemu),esc(x.qijian),money(x.chushi_yusuan_fen),money(x.shuzhi_fen),esc(x.zhuangtai),esc(x.laiyuan)]));
 const splitNames={yuandan_zong_fen:'原标准总差异',guihua_zong_fen:'规划总差异',zhixing_zong_fen:'执行总差异',jiage_guihua_fen:'价格规划差异',jiage_zhixing_fen:'价格执行差异',yongliang_guihua_fen:'用量规划差异',yongliang_zhixing_fen:'用量执行差异',cancha_fen:'交叉项残差'};
 const splitRows=r.splits.flatMap(s=>Object.entries(splitNames).map(([key,name])=>[esc(s.kemu),esc(s.period),name,money(s.result[key]),s.result.hengdengshi_chengli?'成立':'不成立']));
 const refs=(r.references??[]).map(x=>`<div class="ref"><b>${esc(x.dingwei)} · ${esc(x.source?.biaoti||'管理会计应用指引')}</b><p>${esc(x.neirong)}</p><small>出处：${esc(x.source?.biaoti||x.zhiyin_hao)} · 第 ${esc(x.tiao_hao)} 条${x.duan_hao?` · ${esc(x.duan_hao)}`:''} · 检索路径：${esc(x.laiyuan_lu)}</small></div>`).join('');
 const analysis=r.analysis;
 const paragraphs=analysis?`<p>${esc(analysis.jiedu)}</p>${(analysis.wenan_lie??[]).map(x=>`<p><b>${esc(x.xuhao)}. ${esc(x.leixing)} / ${esc(x.zeren_mokuai)}</b><br>${esc(x.wenan)}<br><small>核验：${esc(x.jiaoyan)}</small></p>`).join('')}`:'<p class="no-data">尚未生成 AI 解读。可在报告中心检索依据并生成解读，所有数值仍来自确定性计算。</p>';
 return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(r.meta.company)} · 预算分析报告</title><style>${reportCss}${printExtras}</style></head><body><main class="paper">
 <div class="cover"><div class="eyebrow">FINAGENT / 衡策</div><h1>智能预算差异分析<br>与风险预警报告</h1><div class="meta"><span>${esc(r.meta.company)}</span><span>${esc(r.meta.period)} · ${esc(r.meta.cycle)}</span><span>${r.meta.simulation?'模拟数据':'用户导入数据'}</span></div><p class="muted">生成时间 ${esc(r.meta.generatedAt)}<br>报告编号 ${esc(r.id)} · 金额展示为元；JSON 金额为整数分，比率为基点。</p></div>
 <h2>01 / 执行摘要与预算对比</h2><p>本次分析覆盖 ${r.variance.xiang.length} 项科目期间记录，形成 ${r.correction.zong_shu} 项整改任务；BSC 评级为 ${esc(r.bsc?.dengji??'待补充')}。</p>${r.warnings.length?`<p class="warn">${r.warnings.map(esc).join('；')}。</p>`:''}${comparison(r)}<p class="muted">比较基准优先采用届满前滚动预算快照，未提供时采用原始固定预算；绝不使用实际替换后的滚动值消除历史差异。差额＝实际－基准，F/A 有利性按科目方向判定。</p>
 <h2>02 / 动态滚动预算</h2>${r.rolling.map(x=>`<div class="chart"><h3>${esc(x.kemu)}</h3>${trend(r,x.kemu)}</div>`).join('')}${table(['科目','期间','原始预算（元）','最新滚动值（元）','状态','来源'],rollingRows)}
 <h2>03 / 差异结构与风险预警</h2><div class="chart">${pie(r)}</div>${table(['模块','净差额（元）','方向','占比'],r.blocks.mokuai_lie.map(x=>[esc(x.mokuai),money(x.chae_fen),x.fa==='A'?'不利':x.fa==='F'?'有利':'持平',pct(x.zhanbi_bps)]))}${heat(r)}<p class="muted">当前全局档位：${r.config.tiers.map(x=>`${esc(x.ming_cheng)} ≥ ${pct(x.yu_fen)}`).join('；')}。科目专属档位以附录为准，热力图采用每行实际命中的档位。</p>
 <h2>04 / 规划与执行差异拆分</h2>${table(['科目','期间','差异分量','金额（元）','恒等式校验'],splitRows)}<p class="muted">总差异＝规划差异＋执行差异。四项细分采用插件原口径，交叉项残差单列，不强行平摊。</p>
 <h2>05 / 单双环纠错判定</h2>${decisionsTable(r)}<p class="muted">噪声门限 ${pct(r.config.noise)}；显著性门限 ${pct(r.config.significance)}。结构变更仅依据页面确认登记，预算修订须经人工批准。</p>
 <h2>06 / 平衡计分卡与 KPI</h2>${bscChart(r)}${kpiTable(r)}
 <h2>07 / 财务与非财务变更溯源</h2>${table(['指标','影响率','数值方向','经营作用','影响占比'],(r.trace?.xiang??[]).map(x=>[esc(x.kpi_mingcheng),pct(x.yingxianglv_bps),esc(x.shuzhi_fangxiang),esc(x.zuoyong),pct(x.zhanbi_bps)]))}<p class="muted">影响率＝（变更后－变更前）÷原预算；原预算为零或缺失时不计算。正向 TOP3：${esc(r.trace?.zhengxiang_top3?.join('、')||'—')}；负向 TOP3：${esc(r.trace?.fuxiang_top3?.join('、')||'—')}。</p>
 <h2>08 / 整改任务与完成进度</h2>${progress(r)}${correctionTable(r)}${table(['批准时间','科目','未来期间','修订金额（元）','批准原因'],(r.revisions??[]).map(x=>[esc(x.at),esc(x.kemu),esc(x.period),money(x.amount),esc(x.reason)]))}
 <h2>09 / AI 分析与依据条例</h2>${paragraphs}${r.retrievalFailures?.length?`<p class="warn">部分检索失败：${r.retrievalFailures.map(esc).join('；')}</p>`:''}${refs||'<p class="no-data">尚未检索本地知识库，暂无可引用条例。</p>'}
 <h2>附录 / 输入与口径追踪</h2>${table(['科目','方向','归属','自定义增长率','专属档位'],r.subjects.map(x=>[esc(x.kemu),esc(x.direction),esc(x.module),x.growth==null?'使用全局':pct(x.growth),(x.tiers?.length?x.tiers.map(t=>`${esc(t.ming_cheng)}≥${pct(t.yu_fen)}`).join('；'):'使用全局')]))}<p class="muted">企业增长率 ${pct(r.config.growth)}；行业增长率 ${pct(r.config.industry)}；行业差值修正 ${r.config.industryCorrection?'启用（仅季度）':'关闭'}；启用门限 ${pct(r.config.industryThreshold)}。</p>${table(['类别','期间','科目','原始值','单位','数据来源'],['yusuan','shishi','hangye','biangeng'].flatMap(key=>(r.records[key]??[]).map(x=>[esc(x.leibie),esc(x.qijian),esc(x.kemu),x.danwei==='元'?money(x.shuzhi):x.danwei==='%'?pct(x.shuzhi):esc(x.shuzhi),esc(x.danwei),esc(x.laiyuan)])))}
 <div class="foot">衡策 · 智能预算差异分析与风险预警系统<br>数值由已核对的计算插件生成，解释内容为 AI 生成，仅供参考。缺失数据与失败核验均保留说明。</div></main></body></html>`;
}
