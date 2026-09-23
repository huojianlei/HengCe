// ======================================================================
// variance（差异计算模块）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_variance.py（10 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 回归基准 = 定稿 v2.1 §2.3 的 E&G Co 弹性预算全表（六行 + 合计）；
//     2. 每条口径（方向/F-A/三档预警/基准退化/除零/校验）各一组用例；
//     3. 差异率基点手工换算（如 5,000/105,000 = 4.7619% → 476 基点）。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（插件目录下）：
//     node --test tests/variance.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import type { ChayiShuru } from '../../plugins/fin-agent/src/variance.ts'
import { ChayiCuowu, jisuan_chayi } from '../../plugins/fin-agent/src/variance.ts'

/** 构造 E&G Co 六行输入（预算 3,000 件 / 实际 3,500 件的弹性对比）。
 *
 *  数据与期望输出来自定稿 v2.1 §2.3 表格，金额元 ×100 转分；
 *  Python 版以位置参数构造 dataclass，TS 侧以同字段名对象字面量构造。 */
function eg_liu_hang(): ChayiShuru[] {
  // 六行依次：直接材料 / 直接人工 / 间接人工 / 电力 / 物料 / 固定成本
  return [
    { qijian: '2026-01', kemu: '直接材料', fangxiang: '成本类', chushi_fen: 9_000_000, gundong_fen: 10_500_000, shiji_fen: 11_000_000 },
    { qijian: '2026-01', kemu: '直接人工', fangxiang: '成本类', chushi_fen: 7_500_000, gundong_fen: 8_750_000, shiji_fen: 8_750_000 },
    { qijian: '2026-01', kemu: '间接人工', fangxiang: '成本类', chushi_fen: 6_000_000, gundong_fen: 7_000_000, shiji_fen: 7_100_000 },
    { qijian: '2026-01', kemu: '电力', fangxiang: '成本类', chushi_fen: 1_500_000, gundong_fen: 1_750_000, shiji_fen: 1_480_000 },
    { qijian: '2026-01', kemu: '物料', fangxiang: '成本类', chushi_fen: 2_400_000, gundong_fen: 2_800_000, shiji_fen: 2_640_000 },
    { qijian: '2026-01', kemu: '固定成本', fangxiang: '成本类', chushi_fen: 5_500_000, gundong_fen: 5_500_000, shiji_fen: 5_500_000 },
  ]
}

describe('TestEHuiGui · E&G Co 全表回归——与定稿例题逐行逐格一致（最重要的用例组）', () => {
  // 任何改动若使本组失败，即为口径回归（对应定稿 v2.1 §2.3）。
  test('test_quanbiao: 六行差异（差额/差异率/F-A/预警）与合计全部对上例题', () => {
    const jg = jisuan_chayi(eg_liu_hang())
    // 期望值手工验算（差额=分；差异率=基点 half-up）；
    // 预警阈值【2026-09-03 三档分割】= 黄 15%（1500 基点）/ 红 30%（3000 基点）：
    //   材料 +500 元 A；476 基点（4.76%）< 15% → 无
    //   人工 0 '—'；无
    //   间接 +100 元 A；143 基点 → 无
    //   电力 −270 元 F；1543 基点（15.43%）≥ 15% → 黄
    //   物料 −160 元 F；571 基点（5.71%）< 15% → 无
    //   固定 0 '—'；无
    const qidai = [
      [500_000, 476, 'A', '无'],
      [0, 0, '—', '无'],
      [100_000, 143, 'A', '无'],
      [-270_000, 1543, 'F', '黄'],
      [-160_000, 571, 'F', '无'],
      [0, 0, '—', '无'],
    ]
    assert.deepEqual(
      jg.xiang.map((x) => [x.chae_fen, x.chalv_bps, x.fa, x.yujing]),
      qidai,
    )
    // 合计：36,470 − 36,300 = +170 元 → A（全表同向成本类）
    assert.equal(jg.heji_chae_fen, 170_000)
    assert.equal(jg.heji_fa, 'A')
    // 预警计数：红 0、黄 1（电力）、无 5、无法定级 0（阈值 15%/30%）
    assert.deepEqual([jg.hong_shu, jg.huang_shu, jg.wu_shu, jg.wufa_shu], [0, 1, 5, 0])
  })
})

describe('TestFangxiang · 方向规则：成本类与收入类的 F-A 映射相反（§0.5）', () => {
  test('test_shouru_chaoe_shi_F: 收入类正差额 = 超额 = 有利 F（与成本类相反）', () => {
    const jg = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '营收', fangxiang: '收入类', chushi_fen: 5_000_000, gundong_fen: 5_200_000, shiji_fen: 5_350_000 },
    ])
    const x = jg.xiang[0]!
    assert.equal(x.chae_fen, 150_000) // 超收 1,500 元
    assert.equal(x.fa, 'F')
    // 1500/52000 = 2.88% → 288 基点 → 无（< 15% 新阈值）
    assert.equal(x.chalv_bps, 288)
    assert.equal(x.yujing, '无')
  })

  test('test_shouru_weida_shi_A: 收入类负差额 = 未达标 = 不利 A', () => {
    const jg = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '营收', fangxiang: '收入类', chushi_fen: 5_000_000, gundong_fen: 5_200_000, shiji_fen: 5_000_000 },
    ])
    assert.equal(jg.xiang[0]!.fa, 'A')
  })

  test('test_hunhe_fangxiang_heji_wu_panding: 成本/收入混合输入——合计 F/A 无意义 → \'—\'（明细仍逐项判定）', () => {
    const jg = jisuan_chayi([
      { qijian: '2026-01', kemu: '营收', fangxiang: '收入类', chushi_fen: 5_000_000, gundong_fen: 5_200_000, shiji_fen: 5_350_000 },
      { qijian: '2026-01', kemu: '直接材料', fangxiang: '成本类', chushi_fen: 9_000_000, gundong_fen: 10_500_000, shiji_fen: 11_000_000 },
    ])
    assert.equal(jg.heji_fa, '—')
  })
})

describe('TestJizhun · 基准规则：滚动优先、缺省退化、除零保护', () => {
  // 除零是唯一"无法定级"的场景——预警记 '—' 交人工（口径见模块头）。
  test('test_gundong_quexing_tuihua_chushi: 未提供滚动预算（None）——基准 = 初始（固定）预算', () => {
    const jg = jisuan_chayi([
      { qijian: '2026-02', kemu: '办公费', fangxiang: '成本类', chushi_fen: 3_000_000, gundong_fen: null, shiji_fen: 3_100_000 },
    ])
    const x = jg.xiang[0]!
    assert.equal(x.jizhun_fen, 3_000_000) // 基准退化到固定预算
    assert.equal(x.chae_fen, 100_000) // 超支 1,000 元
    assert.equal(x.fa, 'A')
  })

  test('test_jizhun_ling_chalv_None: 基准为 0——差异率 None、预警 \'—\'（交人工，不臆造定级）', () => {
    // 场景：新科目尚无任何预算（两列基准都是 0）但已有实际发生
    const jg = jisuan_chayi([
      { qijian: '2026-03', kemu: '新科目', fangxiang: '成本类', chushi_fen: 0, gundong_fen: 0, shiji_fen: 500_000 },
    ])
    const x = jg.xiang[0]!
    assert.equal(x.chalv_bps, null)
    assert.equal(x.yujing, '—')
    // 差额本身仍可算（500,000 分 = 超支 5,000 元）
    assert.equal(x.chae_fen, 500_000)
  })

  test('test_yujing_sandang_bianjie: 三档边界（2026-09-03 阈值）——恰 1500=黄、2999=黄、3000=红、1499=无', () => {
    // 基准统一 10,000,000 分（=10 万元）；偏差=基点×基准÷10000：
    // 1499 基点→1,499,000 分；1500→1,500,000；2999→2,999,000；3000→3,000,000
    const jg = jisuan_chayi([
      { qijian: '2026-01', kemu: '边界1499', fangxiang: '成本类', chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_499_000 },
      { qijian: '2026-02', kemu: '边界1500', fangxiang: '成本类', chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_500_000 },
      { qijian: '2026-03', kemu: '边界2999', fangxiang: '成本类', chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 12_999_000 },
      { qijian: '2026-04', kemu: '边界3000', fangxiang: '成本类', chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 13_000_000 },
    ])
    // 1,499,000/10,000,000 = 14.99% = 1499 基点 → 无
    assert.equal(jg.xiang[0]!.yujing, '无')
    assert.equal(jg.xiang[1]!.yujing, '黄') // 恰达 15% 阈值
    assert.equal(jg.xiang[2]!.yujing, '黄')
    assert.equal(jg.xiang[3]!.yujing, '红') // 恰达 30% 阈值
  })
})

describe('TestJiaoyan · 输入校验：脏数据必须被拒绝', () => {
  // 校验范围：方向枚举 / 金额形态（负数、浮点、布尔）/ 键唯一 / 非空。
  test('test_feifa_fangxiang: 未知方向 → 拒绝', () => {
    assert.throws(
      () => jisuan_chayi([{ qijian: '2026-01', kemu: 'x', fangxiang: '随便', chushi_fen: 1, gundong_fen: 1, shiji_fen: 1 }]),
      ChayiCuowu,
    )
  })

  test('test_feifa_jine: 负数 / 浮点 / 布尔金额 → 拒绝（整数分纪律）', () => {
    // 三种典型脏形态逐个试（bool 是 int 子类，须单独排除——
    // TS 侧 typeof x === 'number' 校验天然覆盖，true 用 as any 照样传入断言抛错）
    for (const huai of [-1, 100.5, true as any]) {
      assert.throws(
        () =>
          jisuan_chayi([
            { qijian: '2026-01', kemu: 'x', fangxiang: '成本类', chushi_fen: huai, gundong_fen: 1, shiji_fen: 1 },
          ]),
        ChayiCuowu,
        `${String(huai)} 应被拒绝`,
      )
    }
  })

  test('test_chongfu_he_kong: （期间, 科目）重复 / 空列表 → 拒绝', () => {
    assert.throws(
      () =>
        jisuan_chayi([
          { qijian: '2026-01', kemu: 'x', fangxiang: '成本类', chushi_fen: 1, gundong_fen: 1, shiji_fen: 1 },
          { qijian: '2026-01', kemu: 'x', fangxiang: '成本类', chushi_fen: 2, gundong_fen: 2, shiji_fen: 2 }, // 同键重复
        ]),
      ChayiCuowu,
    )
    assert.throws(() => jisuan_chayi([]), ChayiCuowu)
  })
})
