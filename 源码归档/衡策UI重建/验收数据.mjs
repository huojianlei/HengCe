import { createDemoData } from './src/演示数据.mjs';

const data = createDemoData();
function check(condition, message) {
  if (!condition) throw new Error(message);
}

for (const row of data.rows) {
  check([row.budget, row.actual, row.variance].every(Number.isSafeInteger), `${row.id} 金额须为整数分`);
  check(row.actual - row.budget === row.variance, `${row.id} 差额不一致`);
}
const sum = (module, key) => data.rows.filter(row => row.module === module).reduce((total, row) => total + row[key], 0);
const june = data.trend.find(point => point.period === data.meta.period);
check(june && june.budget === sum('收入', 'budget') && june.actual === sum('收入', 'actual'), '当期趋势与收入明细合计不一致');

const rowIds = new Set(data.rows.map(row => row.id));
for (const item of [...data.actions, ...data.revisions]) {
  check(rowIds.has(item.rowId), `${item.id} 引用了不存在的明细`);
}

const untouched = createDemoData();
const serialized = JSON.stringify(untouched);
data.rows[0].actual += 100;
data.config.tiers[0].threshold += 1;
data.actions[0].status = 'done';
data.reports.push({ id: 'isolation-check' });
check(JSON.stringify(untouched) === serialized && JSON.stringify(createDemoData()) === serialized, '演示数据副本共享了可变状态');

const original = createDemoData();
const actualTotal = module => original.rows.filter(row => row.module === module).reduce((total, row) => total + row.actual, 0);
const operatingBalance = actualTotal('收入') - actualTotal('成本') - actualTotal('费用');
check(operatingBalance === 98500000, '经营结余参考值不一致，请检查是否重复扣除了采购');
console.log(`通过：${original.rows.length} 条明细金额与差额、当期收入趋势、整改引用及副本隔离。`);
console.log(`口径提示：收入 − 成本 − 费用 = ${(operatingBalance / 10000 / 100).toFixed(2)} 万元；采购为独立管理视角，不再次扣入利润。`);
