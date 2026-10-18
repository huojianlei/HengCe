/**
 * 衡策界面演示数据。
 * 所有企业、人员、业务事项均为虚构，不含真实法规引用。
 * 金额以整数分存储；百分比以整数基点存储（100 基点 = 1%）。
 * 采购是独立管理视角，不应与成本、费用重复计入利润计算。
 */
const money = (yuan) => Math.round(yuan * 100);

const rawRows = [
  ['r01', '企业软件许可', '收入', '企业业务部', 'business', 5200000, 4080000, '单环纠错', '两项已签约项目的验收时间顺延，影响本月收入确认；优先跟进交付和验收节点。', '收入表!D18'],
  ['r02', '订阅服务', '收入', '企业业务部', 'business', 3600000, 3780000, '持续观察', '存量客户续订率提高，新增订阅按计划落地。', '收入表!D19'],
  ['r03', '实施与交付服务', '收入', '产品研发部', 'product', 1800000, 1500000, '单环纠错', '客户侧测试资源不足导致阶段交付延后，需更新交付排期和责任人。', '收入表!D20'],
  ['r04', '运维服务', '收入', '运营支持部', 'operations', 900000, 960000, '持续观察', '重点客户新增服务需求，服务收入略高于预算。', '收入表!D21'],
  ['r05', '云资源成本', '成本', '产品研发部', 'product', 1200000, 1310000, '持续观察', '测试环境短时扩容带来资源用量上升，当前偏差未达到预警门限。', '成本表!D12'],
  ['r06', '项目交付人工', '成本', '产品研发部', 'product', 2400000, 2580000, '持续观察', '关键交付节点增加人员投入，继续追踪工时与项目验收进度。', '成本表!D13'],
  ['r07', '第三方集成服务', '成本', '企业业务部', 'business', 680000, 780000, '持续观察', '新增客户接口适配工作，偏差接近关注门限。', '成本表!D14'],
  ['r08', '售后服务成本', '成本', '运营支持部', 'operations', 520000, 495000, '持续观察', '远程支持占比提高，现场服务成本下降。', '成本表!D15'],
  ['r09', '研发费用', '费用', '产品研发部', 'product', 2200000, 2240000, '持续观察', '研发投入与年度计划基本一致。', '费用表!D8'],
  ['r10', '市场推广费用', '费用', '企业业务部', 'business', 820000, 1100000, '单环纠错', '行业活动与推广投放集中发生，新增线索转化未达目标；需复核渠道投放效率。', '费用表!D9'],
  ['r11', '行政办公费用', '费用', '运营支持部', 'operations', 460000, 435000, '持续观察', '集中采购与场地统筹节约日常支出。', '费用表!D10'],
  ['r12', '差旅费用', '费用', '企业业务部', 'business', 320000, 395000, '单环纠错', '跨区域项目支持频次增加，需合并出差安排并核查费用标准。', '费用表!D11'],
  ['r13', '生产服务器采购', '采购', '产品研发部', 'product', 1400000, 1890000, '双环纠错', '供应商更新报价，采购数量维持原计划，单价较预算上涨 35%；需复核未来期间的采购价格假设。', '采购表!D16'],
  ['r14', '软件授权采购', '采购', '产品研发部', 'product', 720000, 765000, '持续观察', '研发协作工具新增授权席位，采购支出略高于预算。', '采购表!D17'],
  ['r15', '办公设备采购', '采购', '运营支持部', 'operations', 360000, 324000, '持续观察', '集中议价降低采购单价，数量和规格均按计划执行。', '采购表!D18'],
  ['r16', '专业服务采购', '采购', '运营支持部', 'operations', 280000, 292000, '持续观察', '新增一项专项服务工作，支出保持在正常波动范围内。', '采购表!D19'],
];

const rows = rawRows.map(([id, subject, module, department, departmentId, budgetYuan, actualYuan, decision, reason, cell]) => {
  const budget = money(budgetYuan);
  const actual = money(actualYuan);
  const variance = actual - budget;
  const rate = Math.round(variance / budget * 10000);
  const direction = (module === '收入' ? variance >= 0 : variance <= 0) ? 'favorable' : 'unfavorable';
  const adverseRate = direction === 'unfavorable' ? Math.abs(rate) : 0;
  return {
    id, subject, module, department, departmentId, period: '2027-06', budget, actual,
    variance, rate, risk: adverseRate >= 3000 ? 'high' : adverseRate >= 1500 ? 'watch' : 'normal',
    direction, decision, reason, source: `演示-实时经营.xlsx / ${cell}`,
  };
});

const demoData = {
  schemaVersion: '1.0',
  demo: true,
  meta: {
    company: '恒暻科技有限公司', period: '2027-06', scenario: '年度经营计划',
    generatedAt: '2027-07-05T09:42:00+08:00', runId: 'demo-202706-01',
  },
  config: {
    cycle: '月度', period: '2027-06', growth: 500, industry: 300,
    industryCorrection: false, industryThreshold: 50, noise: 2500, significance: 2500,
    tiers: [
      { name: '关注', color: '#b7791f', threshold: 1500 },
      { name: '高风险', color: '#c54d57', threshold: 3000 },
    ],
  },
  entities: [
    { id: 'all', name: '全部部门' },
    { id: 'business', name: '企业业务部' },
    { id: 'product', name: '产品研发部' },
    { id: 'operations', name: '运营支持部' },
  ],
  files: [
    { id: 'f01', name: '演示-预算基础.xlsx', category: '预算基础', status: 'valid', checks: 12, rows: 192, size: '42 KB', entity: '恒暻科技有限公司' },
    { id: 'f02', name: '演示-实时经营.xlsx', category: '实时经营', status: 'valid', checks: 18, rows: 96, size: '38 KB', entity: '恒暻科技有限公司' },
    { id: 'f03', name: '演示-行业对标.xlsx', category: '行业对标', status: 'valid', checks: 6, rows: 24, size: '18 KB', entity: '恒暻科技有限公司' },
    { id: 'f04', name: '演示-经营变更.xlsx', category: '经营变更', status: 'valid', checks: 8, rows: 3, size: '16 KB', entity: '恒暻科技有限公司' },
  ],
  rows,
  trend: [
    ['2027-01', 9000000, 8850000, null],
    ['2027-02', 8600000, 8980000, null],
    ['2027-03', 10400000, 10100000, null],
    ['2027-04', 10800000, 11160000, null],
    ['2027-05', 11200000, 10950000, null],
    ['2027-06', 11500000, 10320000, null],
    ['2027-07', 12200000, null, 11800000],
    ['2027-08', 12500000, null, 12160000],
    ['2027-09', 13400000, null, 12920000],
    ['2027-10', 13900000, null, 13650000],
    ['2027-11', 14500000, null, 14200000],
    ['2027-12', 15600000, null, 15400000],
  ].map(([period, budget, actual, rolling]) => ({
    period, budget: money(budget), actual: actual === null ? null : money(actual),
    rolling: rolling === null ? null : money(rolling),
  })),
  actions: [
    {
      id: 'a01', rowId: 'r13', title: '复核服务器价格假设', department: '产品研发部', owner: '周宁',
      due: '2027-07-12', status: 'pending', priority: 'high', type: 'revision',
      description: '核对供应商报价及替代方案；如价格变化具有持续性，提请修订 7—12 月采购预算。当前尚未提交修订，6 月金额保留原记录。',
    },
    {
      id: 'a02', rowId: 'r10', title: '调整低效渠道投放', department: '企业业务部', owner: '林悦',
      due: '2027-07-10', status: 'doing', priority: 'high', type: 'execution',
      description: '按活动和渠道核对支出与有效线索，暂停低效投放，将后续安排纳入月度复盘。',
    },
    {
      id: 'a03', rowId: 'r01', title: '推进延期项目验收', department: '企业业务部', owner: '陈越',
      due: '2027-07-12', status: 'doing', priority: 'watch', type: 'execution',
      description: '梳理两项已签约项目的验收阻碍，与交付团队确认客户测试时间，并每周更新进展。',
    },
    {
      id: 'a04', rowId: 'r03', title: '确认阶段交付排期', department: '产品研发部', owner: '周宁',
      due: '2027-07-09', status: 'pending', priority: 'watch', type: 'execution',
      description: '与客户确认测试人员和可用时间，补齐阶段验收资料，明确每一项交付的责任人。',
    },
    {
      id: 'a05', rowId: 'r12', title: '合并跨区域出差安排', department: '企业业务部', owner: '林悦',
      due: '2027-07-04', status: 'done', priority: 'watch', type: 'execution',
      description: '已汇总下一期差旅行程并合并同区域现场支持，执行效果将在下次分析中复核。',
    },
  ],
  revisions: [],
  reports: [
    { id: 'report-202706', title: '2027 年 6 月经营分析报告（演示）', period: '2027-06', createdAt: '2027-07-05T10:15:00+08:00', status: 'ready', format: 'PDF', pages: null },
  ],
  history: [
    { id: 'demo-202706-01', period: '2027-06', createdAt: '2027-07-05T09:42:00+08:00', company: '恒暻科技有限公司', status: 'done', riskCount: 5 },
  ],
  kpis: [
    { name: '收入达成率', value: Math.round(10320000 / 11500000 * 10000), unit: '%', note: '6 月实际收入 ÷ 6 月预算收入；由当前演示数据计算。' },
    { name: '销售毛利率', value: Math.round((10320000 - 5165000) / 10320000 * 10000), unit: '%', note: '（实际收入 − 实际成本）÷ 实际收入；采购单列展示。' },
    { name: '费用收入比', value: Math.round(4170000 / 10320000 * 10000), unit: '%', note: '实际费用 ÷ 实际收入；仅用于演示经营效率指标。' },
    { name: '客户续约率', value: null, unit: '%', note: '缺少客户合同明细，补充数据后可计算。' },
  ],
  background: {
    changeStatus: 'yes',
    text: '【演示经营背景】6 月两项企业软件项目验收延后；服务器供应商报价上调，采购数量未变；市场推广活动集中开展。以上均为虚构事项，用于演示差异解释、整改跟踪与未来预算修订流程。',
  },
};

/** 每次返回独立的数据副本，避免演示操作影响下一次初始化。 */
export function createDemoData() {
  return structuredClone(demoData);
}
