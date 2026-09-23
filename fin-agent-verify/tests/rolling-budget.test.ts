// ======================================================================
// rolling-budget（滚动预算模块）单元测试 —— 期望值全部手工验算的整数（分）
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_rolling_budget.py（11 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 期望值一律"手算后写死"，禁止在测试里用被测函数现算（自证循环）；
//     2. 每个用例只验证一个口径点，失败信息能直接定位到口径条款；
//     3. 覆盖四类场景：定稿例题回归 / 常规月度 / 口径A 三情形 / 边界与校验。
//
// 口径基准例题：Broad Co（定稿 v2.1 §1，四舍五入逐期累进）。
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音（2026-08-23）。
// 运行方式（插件目录下）：
//     node --test tests/rolling-budget.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import type { QijianJine } from '../../plugins/fin-agent/src/rolling-budget.ts'
import { GunDongCuowu, GunDongShezhi, fen_zhuan_yuan, gengxin_gundong_yusuan } from '../../plugins/fin-agent/src/rolling-budget.ts'

/** 构造一行期间金额的简写助手（预算行与实际行共用）。
 *
 *  参数顺序刻意与 Python dataclass 字段顺序相反——让"金额在前"贴合会计
 *  阅读习惯；所有测试金额一律以"分"书写（下划线分隔千位），与被测模块
 *  纪律一致。 */
function q(jine_fen: number, qijian: string): QijianJine {
  return { qijian, jine_fen }
}

describe('TestBroadCoJidu · Broad Co 季度滚动（口径 B）——定稿例题回归基准', () => {
  // 全模块最重要的用例：任何改动若使本用例失败，即为口径回归。
  // 对应口径条款：定稿 #1（全额替换制）+ v2.1 §1 例题数字。
  test('test_broadco: 例题全流程——Q1 实际替换 + Q2~Q4 累进重算 + 总额/差额/修正标志', () => {
    // 默认口径回归：口径 A 为默认（用户拍板 T-02，2026-08-23）
    assert.equal(GunDongShezhi('季度', 100).hangye_xiuzheng, 'A')
    // 场景：年度初始各季预算 220,000 元；Q1 实际 210,000 元；最新增长率 1%；
    // 行业增速同为 1%（差值 0 → 口径A不修正 → 例题数字保持原样）
    const yusuan = [1, 2, 3, 4].map((i) => q(22_000_000, `2026-Q${i}`))
    const shiji = [q(21_000_000, '2026-Q1')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      shiji,
      GunDongShezhi('季度', 100, { hangye_zengzhanglv_jidian: 100 }),
    )

    // 逐期断言：期间/状态/来源/金额（分）全部与例题一致；
    // 四要素逐一比对，任何一字段漂移都会被抓住
    assert.deepEqual(
      jieguo.qijian_mingxi.map((t) => [t.qijian, t.zhuangtai, t.laiyuan, t.shuzhi_fen]),
      [
        ['2026-Q1', '已届满', '实际', 21_000_000], // 实际替换 210,000 元
        ['2026-Q2', '剩余期', '重算', 22_220_000], // 222,200 元
        ['2026-Q3', '剩余期', '重算', 22_442_200], // 224,422 元
        ['2026-Q4', '剩余期', '重算', 22_666_622], // 226,666.22 元
      ],
    )
    // 总额与差额：原 880,000；滚动 883,288.22；Δ +3,288.22
    // （差额为展示口径：滚动总额 − 初始总额，见定稿 §0.5）
    assert.equal(jieguo.chushi_zonge_fen, 88_000_000)
    assert.equal(jieguo.gundong_zonge_fen, 88_328_822)
    assert.equal(jieguo.chae_fen, 328_822)
    // 口径 B：行业修正必须关闭
    assert.equal(jieguo.hangye_xiuzheng_qiyong, false)
    // 展示层换算抽查（元字符串，两位小数）
    assert.equal(fen_zhuan_yuan(jieguo.gundong_zonge_fen), '883288.22')
  })
})

describe('TestYueduLianshi · 月度滚动：届满替换 + 累进重算（定稿 #1 月度规则）', () => {
  // 口径要点：月度为纯企业内部修正——不叠加行业对标（见口径A用例）。
  test('test_yuedu: 6 个月、前 3 个月实际、g=0.5%——验证累进基数与逐期舍入', () => {
    // 构造 6 期预算（每月 10,000 元）与 3 期实际（金额故意互有高低）
    // 月度模式不受口径 A 影响（纯企业内部修正——定稿 #1）
    const yusuan = [1, 2, 3, 4, 5, 6].map((i) => q(1_000_000, `2026-0${i}`))
    const shiji = [q(950_000, '2026-01'), q(1_010_000, '2026-02'), q(990_000, '2026-03')]
    const jieguo = gengxin_gundong_yusuan(yusuan, shiji, GunDongShezhi('月度', 50))

    // 期望值手工验算（分）——链法①逐期接力（数值与 (1.005)^期距 读法恰同）：
    //   M4 = 1,000,000 × 1.005 = 1,005,000
    //   M5 = 上一期滚动值 1,005,000 × 1.005 = 1,010,025
    //   M6 = 上一期滚动值 1,010,025 × 1.005 = 1,015,075.125 → half-up 1,015,075
    assert.deepEqual(
      jieguo.qijian_mingxi.map((t) => t.shuzhi_fen),
      [950_000, 1_010_000, 990_000, 1_005_000, 1_010_025, 1_015_075],
    )
    // 总额与差额（负差：滚动总额低于原预算，允许为负——
    // 实际数据低迷 + 低增长重算的组合结果）
    assert.equal(jieguo.gundong_zonge_fen, 5_980_100)
    assert.equal(jieguo.chae_fen, -19_900)
  })
})

describe('TestKoujingA · 口径 A（增长率差值法）三情形：达阈值启用 / 未达阈值 / 月度不生效', () => {
  // 口径条款：系数 = 1 + (企业增长率 − 行业增长率)，仅季度生效；
  // 启用条件 |差值| ≥ 阈值（默认 50 基点）——本组用例逐一验证三条边界。
  // 2026-08-23 口径 A 已成为默认（用户拍板 T-02），本组权重相应提升。
  test('test_chazhi_da_yuzhi_qiyong: 企业 1% vs 行业 0.5%，|差|=50 基点恰好达默认阈值 → 启用修正', () => {
    // 两期预算 + Q1 实际，聚焦 Q2 单期结果即可判定口径；
    // 显式口径 A（现为默认，写显式只是防未来默认值再变）
    const yusuan = [q(10_000_000, '2026-Q1'), q(10_000_000, '2026-Q2')]
    const shiji = [q(9_800_000, '2026-Q1')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      shiji,
      GunDongShezhi('季度', 100, { hangye_xiuzheng: 'A', hangye_zengzhanglv_jidian: 50 }),
    )
    // Q2 = 10,000,000×1.01 = 10,100,000；再 ×(1+0.5%) = 10,150,500（口径A 一次性乘子）
    assert.equal(jieguo.qijian_mingxi[1]!.shuzhi_fen, 10_150_500)
    // 启用标志必须为 true（差值恰达默认阈值 50 基点——边界即启用）
    assert.equal(jieguo.hangye_xiuzheng_qiyong, true)
  })

  test('test_chazhi_wei_da_yuzhi_bu_qiyong: 企业 1% vs 行业 0.8%，|差|=20 基点 < 50 → 不启用（防抖动条款）', () => {
    const yusuan = [q(10_000_000, '2026-Q1'), q(10_000_000, '2026-Q2')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      [q(9_800_000, '2026-Q1')],
      GunDongShezhi('季度', 100, { hangye_xiuzheng: 'A', hangye_zengzhanglv_jidian: 80 }),
    )
    // 仅企业增长率累进：Q2 = 10,100,000
    assert.equal(jieguo.qijian_mingxi[1]!.shuzhi_fen, 10_100_000)
    assert.equal(jieguo.hangye_xiuzheng_qiyong, false)
  })

  test('test_yuedu_yongyuan_bu_shengxiao: 定稿 #1——月度纯企业内部修正，口径 A 传了参数也不生效', () => {
    const yusuan = [q(1_000_000, '2026-01'), q(1_000_000, '2026-02')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      [],
      GunDongShezhi('月度', 100, { hangye_xiuzheng: 'A', hangye_zengzhanglv_jidian: 0 }),
    )
    // 修正标志必须为 false（口径 A 的参数在月度下被忽略）
    assert.equal(jieguo.hangye_xiuzheng_qiyong, false)
    // 无实际数据时全期重算：M1=1,010,000；M2=链上 1,010,000×1.01=1,020,100
    assert.equal(jieguo.qijian_mingxi[1]!.shuzhi_fen, 1_020_100)
  })
})

describe('TestBianjie · 边界行为：无实际数据 / 全部届满——两种退化情形的正确姿态', () => {
  // 退化情形的口径：算法不报错、不臆造，按定义自然退化。
  test('test_wu_shiji_quanbu_chongsuan: 尚无实际数据——全部期间按给定增长率累进重算', () => {
    // 说明：此时增长率为外生输入（管理员/LLM 给定），非系统推导；
    // 行业增速取持平（差值 0 → 口径A默认下不修正，数字与旧例一致）
    const yusuan = [q(1_000_000, '2026-Q1'), q(1_000_000, '2026-Q2')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      [],
      GunDongShezhi('季度', 100, { hangye_zengzhanglv_jidian: 100 }),
    )
    // Q1 = 1,010,000；Q2 = 1,020,100；Δ = +30,100
    assert.deepEqual(jieguo.qijian_mingxi.map((t) => t.shuzhi_fen), [1_010_000, 1_020_100])
    assert.equal(jieguo.chae_fen, 30_100)
  })

  test('test_quan_bu_jieman_dengyu_shiji_heji: 全部届满——总额 = 实际合计，无剩余期（滚动退化为实际汇总）', () => {
    // 年度结束后的终态——不再有任何"剩余期"可重算
    const yusuan = [q(1_000_000, '2026-Q1'), q(1_000_000, '2026-Q2')]
    const shiji = [q(500_000, '2026-Q1'), q(600_000, '2026-Q2')]
    const jieguo = gengxin_gundong_yusuan(
      yusuan,
      shiji,
      GunDongShezhi('季度', 100, { hangye_zengzhanglv_jidian: 100 }),
    )
    // 状态全部为已届满（年度终态），总额恰为实际之和
    assert.equal(jieguo.qijian_mingxi.every((t) => t.zhuangtai === '已届满'), true)
    assert.equal(jieguo.gundong_zonge_fen, 1_100_000)
  })
})

describe('TestJiaoyan · 输入校验：脏数据必须被拒绝——错误数据不允许进入算法层', () => {
  // 口径：抛 GunDongCuowu（Python 侧 ValueError 子类），调用方按脏数据统一处理。
  // 校验范围：期间存在性 / 唯一性 / 金额形态 / 枚举与参数完备性——
  // 这四类正是真实 Excel 导入中最常见的事故形态；
  // 口径 A 成为默认后，"季度缺行业增长率"也纳入完备性校验。
  test('test_shiji_qijian_bu_zai_yusuan: 实际期间不在预算表中（录入错位）→ 拒绝', () => {
    // 典型事故：Excel 行错位导致实际数挂到不存在的期间
    assert.throws(
      () =>
        gengxin_gundong_yusuan(
          [q(1_000_000, '2026-Q1')],
          [q(1_000_000, '2026-Q9')],
          GunDongShezhi('季度', 0),
        ),
      GunDongCuowu,
    )
  })

  test('test_qijian_chongfu: 期间键重复（同一期出现两行）→ 拒绝', () => {
    // 重复期间会使"届满/剩余"判断出现二义性，必须在入口拦截
    const chongfu = [q(1_000_000, '2026-Q1'), q(1_000_000, '2026-Q1')]
    assert.throws(() => gengxin_gundong_yusuan(chongfu, [], GunDongShezhi('季度', 0)), GunDongCuowu)
  })

  test('test_fushu_he_xiaoshu_jine: 负金额 / 小数金额（非整数分）→ 拒绝', () => {
    // 负数：金额语义上不允许（方向由"指标性质"表达，不由符号表达）
    assert.throws(() => gengxin_gundong_yusuan([q(-1, '2026-Q1')], [], GunDongShezhi('季度', 0)), GunDongCuowu)
    // 100.5 不是合法的整数分——浮点金额一律不许进门（数值纪律）
    assert.throws(
      () =>
        gengxin_gundong_yusuan(
          [{ qijian: '2026-Q1', jine_fen: 100.5 }],
          [],
          GunDongShezhi('季度', 0),
        ),
      GunDongCuowu,
    )
  })

  test('test_feifa_zhouqi_he_cankoujingA_quecan: 非法周期值 / 口径 A 缺行业参数 → 拒绝', () => {
    // '年度' 不在两模式枚举内
    assert.throws(
      () => gengxin_gundong_yusuan([q(1_000_000, '2026-Q1')], [], GunDongShezhi('年度', 0)),
      GunDongCuowu,
    )
    // 口径 A + 季度，但没给 hangye_zengzhanglv_jidian
    assert.throws(
      () =>
        gengxin_gundong_yusuan(
          [q(1_000_000, '2026-Q1'), q(1_000_000, '2026-Q2')],
          [],
          GunDongShezhi('季度', 100, { hangye_xiuzheng: 'A' }),
        ),
      GunDongCuowu,
    )
  })
})
