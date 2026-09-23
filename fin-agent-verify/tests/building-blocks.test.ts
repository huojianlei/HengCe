// ======================================================================
// building_blocks（积木四模块聚合）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_building_blocks.py（19 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 回归基准 = 教材 04 章应用题（材料价格/人工效率/销量/制造费用四行）
//        + D1/D2/D3 三个口径决策点的逐条锁定；
//     2. 占比分母 = Σ|各模块净差额| + |未归属净差额|（D2）——占比合计恒
//        10000 基点是本测试组的核心不变量；
//     3. 模块 F/A 只信差额符号、不信行级 fa（§0.5 唯一真源规则的落地）。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（插件目录下）：
//     node --test tests/building-blocks.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import type { JimuHang } from '../../plugins/fin-agent/src/building-blocks.ts'
import { JimuCuowu, chai_jimu, cong_chayi_xiang, yingshe_mokuai } from '../../plugins/fin-agent/src/building-blocks.ts'
import type { ChayiShuru, YujingDang } from '../../plugins/fin-agent/src/variance.ts'
import { jisuan_chayi } from '../../plugins/fin-agent/src/variance.ts'

/** Python 版以位置参数构造 frozen dataclass；TS 侧以同字段名对象字面量构造。 */
function jimu_hang(
  qijian: string,
  kemu: string,
  chae_fen: number,
  fa: string,
  yujing: string,
  chalv_bps: number | null,
): JimuHang {
  return { qijian, kemu, chae_fen, fa, yujing, chalv_bps }
}

/** 构造教材 04 章应用题的四行输入（展示口径，金额元 ×100 转分）。
 *
 *  四行差额：材料价格 +8,000 元 A（超支）/ 人工效率 −1,000 元 F（节约）
 *  / 销量 +3,000 元 F（超额）/ 制造费用 +6,000 元 A（超支）。
 *  期望聚合（手算）：采购 +800,000 A、成本 +500,000 A、收入 +300,000 F、
 *  费用 0；净总差异 +1,600,000 分；高亮 = 采购模块。
 */
function jiaocai_si_hang(): JimuHang[] {
  return [
    jimu_hang('2026-Q1', '材料价格差异', 800_000, 'A', '红', 3500),
    jimu_hang('2026-Q1', '人工效率差异', -100_000, 'F', '黄', 500),
    jimu_hang('2026-Q1', '销量差异', 300_000, 'F', '无', 120),
    jimu_hang('2026-Q1', '制造费用差异', 600_000, 'A', '红', 1000),
  ]
}

describe('TestJiaocaiLiti · 教材 04 章应用题全量回归——模块差额/F-A/占比/高亮逐格对上', () => {
  // 任何改动若使本组失败，即为口径回归（对应拍板 T-05/T-21 与 D1~D3）。
  test('test_simokuai_quanliang: 四模块聚合结果 + 净总差异 + 占比分母 + 高亮全部对上例题', () => {
    const jg = chai_jimu(jiaocai_si_hang())
    // 期望值手工验算（差额=分；占比=基点）：
    //   模块净差额：收入 +300,000；成本 +600,000−100,000=+500,000；
    //   费用 0；采购 +800,000。
    //   分母 = 300,000+500,000+0+800,000 = 1,600,000（Σ|模块净差额|）。
    //   收入 300,000/1,600,000 = 18.75% → 1875 基点；
    //   成本 500,000/1,600,000 = 31.25% → 3125 基点；
    //   费用 0 → 0 基点；采购 800,000/1,600,000 = 50% → 5000 基点。
    //   模块 F/A 按方向规则：成本/采购正差 = 超支 = A；收入正差 = F。
    const qidai = [
      ['收入模块', 300_000, 'F', 1875, 1],
      ['成本模块', 500_000, 'A', 3125, 2],
      ['费用模块', 0, '—', 0, 0],
      ['采购模块', 800_000, 'A', 5000, 1],
    ]
    assert.deepEqual(
      jg.mokuai_lie.map((x) => [x.mokuai, x.chae_fen, x.fa, x.zhanbi_bps, x.hang_shu]),
      qidai,
    )
    // 净总差异 = +800,000 −100,000 +300,000 +600,000 = +1,600,000 分
    // （实际合计超基准 16,000 元——展示口径正差 = 超支）
    assert.equal(jg.jing_heji_fen, 1_600_000)
    assert.equal(jg.zhanbi_fenmu_fen, 1_600_000) // 分母=Σ|模块净差额|
    assert.equal(jg.hexin_mokuai, '采购模块') // 不利模块中 |差额| 最大
    assert.equal(jg.weiguishu_zhanbi_bps, 0) // 无未归属 → 0 基点
  })

  test('test_mingxi_shunxu: 溯源明细——成本模块两行保持输入顺序（人工效率在前）', () => {
    const jg = chai_jimu(jiaocai_si_hang())
    const chengben = jg.mokuai_lie[1]!
    // 明细只做透传与排序保持，不重排——顺序即输入顺序（溯源友好）
    assert.deepEqual(
      chengben.mingxi.map((x) => x.kemu),
      ['人工效率差异', '制造费用差异'],
    )
  })

  test('test_hang_fa_bu_yingxiang_mokuai_fa: 模块 F/A 只信差额符号——行级 fa 故意给错也不影响模块判定', () => {
    // 人工效率差异实际差额 −100,000（节约），行级 fa 却标 'A'（脏行）——
    // 模拟上游字段被污染的场景，验证模块级判定不信任行级 fa
    const hang = [jimu_hang('2026-Q1', '人工效率差异', -100_000, 'A', '黄', 500)]
    const jg = chai_jimu(hang)
    // 成本模块净额 −100,000 → 负 = 节约 = F（不信任行级 'A'）
    assert.equal(jg.mokuai_lie[1]!.fa, 'F')
  })
})

describe('TestWeiguishu · 未归属行：不静默丢弃、进清单、占分母（D1 兜底 + D2 分母口径）', () => {
  test('test_weiguishu_ruqingdan: 映射不中的科目 → 未归属清单 1 行，占比按 D2 分母计算', () => {
    const jg = chai_jimu(
      jiaocai_si_hang().concat([jimu_hang('2026-Q1', '其他业务', 200_000, 'A', '黄', 300)]),
    )
    assert.equal(jg.weiguishu_lie.length, 1)
    // 分母 = 1,600,000 + |+200,000| = 1,800,000；
    // 未归属 200,000/1,800,000 = 11.11% → 1111 基点（half-up）
    assert.equal(jg.zhanbi_fenmu_fen, 1_800_000)
    assert.equal(jg.weiguishu_zhanbi_bps, 1111)
    // 四模块占比随分母变化（手算）：
    //   收入 300,000/1,800,000 = 16.67% → 1667；
    //   成本 500,000/1,800,000 = 27.78% → 2778；
    //   采购 800,000/1,800,000 = 44.44% → 4444。
    assert.deepEqual(
      jg.mokuai_lie.map((x) => x.zhanbi_bps),
      [1667, 2778, 0, 4444],
    )
    // 核心不变量：占比合计恒 10000 基点（1667+2778+4444+1111）
    const zonghe = jg.mokuai_lie.reduce((he, x) => he + x.zhanbi_bps!, 0) + jg.weiguishu_zhanbi_bps!
    assert.equal(zonghe, 10000)
    // 高亮不受未归属影响（仍为 A 中最大的采购模块）
    assert.equal(jg.hexin_mokuai, '采购模块')
  })

  test('test_zidingyi_feifa_mokuai_ru_weiguishu: 自定义映射返回非法模块名 → 该行进未归属（不静默丢弃）', () => {
    // 自定义映射是 T-24 科目编码落地后的接线点；返回值不在四模块内
    // 时按未归属处理——宁可交人工，也不猜测归属
    const jg = chai_jimu(jiaocai_si_hang(), () => '随便模块')
    assert.equal(jg.weiguishu_lie.length, 4)
    assert.equal(jg.jing_heji_fen, 1_600_000) // 全部行仍计入净合计
  })
})

describe('TestHexin · 核心问题模块高亮（D3）：A 模块中 |差额| 最大；全 F 时 null', () => {
  test('test_quanbu_F_wu_hexin: 全部有利 → hexin_mokuai 为 null（展示层显示"无"）', () => {
    const jg = chai_jimu([jimu_hang('2026-Q1', '营收', 500_000, 'F', '黄', 300)])
    assert.equal(jg.hexin_mokuai, null)
    assert.equal(jg.mokuai_lie[0]!.fa, 'F')
    // 唯一一行 → 分母=500,000，收入独占 100% = 10000 基点
    assert.equal(jg.mokuai_lie[0]!.zhanbi_bps, 10000)
  })

  test('test_binglie_qu_mokuai_shunxu: 并列最大不利——取四模块顺序靠前者（收入先于采购）', () => {
    // 两边 |差额| 相等（300,000）且同为 A → 按 MOKUAI_SHUNXU 取先者：
    // 收入模块排在采购模块之前，故高亮收入模块
    const jg = chai_jimu([
      jimu_hang('2026-Q1', '营收', -300_000, 'A', '红', 1000), // 收入 A
      jimu_hang('2026-Q1', '材料价格差异', 300_000, 'A', '红', 1000), // 采购 A
    ])
    assert.equal(jg.hexin_mokuai, '收入模块') // 顺序靠前
  })

  test('test_quan_ling_chae: 全部零差额——分母 0 → 占比全 null；高亮 null；F/A 全 \'—\'', () => {
    // 除零纪律（与 variance 一致）：分母 0 时不臆造占比，交人工
    const jg = chai_jimu([
      jimu_hang('2026-Q1', '营收', 0, '—', '无', 0),
      jimu_hang('2026-Q1', '材料用量差异', 0, '—', '无', 0),
    ])
    assert.equal(jg.zhanbi_fenmu_fen, 0)
    assert.equal(jg.mokuai_lie.every((x) => x.zhanbi_bps === null), true)
    assert.equal(jg.weiguishu_zhanbi_bps, null)
    assert.equal(jg.hexin_mokuai, null)
    assert.equal(jg.jing_heji_fen, 0)
  })
})

describe('TestZhanbi · 占比口径：half-up 舍入 + D2 分母取模块净额（内部冲抵不进分母）', () => {
  test('test_half_up_sheru: 1/3 → 3333 基点、2/3 → 6667 基点（half-up，合计恒 10000）', () => {
    // 1/3 = 0.3333… → 3333.33 基点 → 3333（小数部分不足一半）；
    // 2/3 = 0.6666… → 6666.67 基点 → 6667（小数部分过半进一）
    const jg = chai_jimu([
      jimu_hang('2026-01', '销量差异', 1, 'F', '无', 0), // 收入
      jimu_hang('2026-01', '材料用量差异', 2, 'A', '无', 0), // 成本
    ])
    assert.deepEqual(
      jg.mokuai_lie.slice(0, 2).map((x) => x.zhanbi_bps),
      [3333, 6667],
    )
    assert.equal(jg.mokuai_lie.reduce((he, x) => he + x.zhanbi_bps!, 0), 10000)
  })

  test('test_jingque_zhengchu: 1/4 → 2500 基点、3/4 → 7500 基点（整除路径）', () => {
    const jg = chai_jimu([
      jimu_hang('2026-01', '销量差异', 1, 'F', '无', 0),
      jimu_hang('2026-01', '材料用量差异', 3, 'A', '无', 0),
    ])
    assert.deepEqual(
      jg.mokuai_lie.slice(0, 2).map((x) => x.zhanbi_bps),
      [2500, 7500],
    )
  })

  test('test_neibu_chongdi_bu_jin_fenmu: D2——模块内部 F/A 冲抵只反映在净差额，行级 |100,000| 不进分母', () => {
    const jg = chai_jimu(jiaocai_si_hang())
    // 成本模块两行：+600,000 A 与 −100,000 F → 净 +500,000；
    // 分母 = 300,000 + 500,000 + 800,000 = 1,600,000
    // （若按行级绝对值会得 1,800,000——那是被 D2 否掉的口径）
    assert.equal(jg.zhanbi_fenmu_fen, 1_600_000)
    assert.equal(jg.mokuai_lie[1]!.zhanbi_bps, 3125)
  })
})

describe('TestYingshe · 默认关键词映射：顺序保证（材料价格→采购先于材料→成本等）', () => {
  test('test_guizhi: 已知科目池 → 期望模块（含关键词顺序陷阱的回归锁定）', () => {
    // 顺序陷阱说明：'材料价格' 若排在 '材料' 之后会误入成本模块；
    // '销售费用' 若排在 '销售' 之后会误入收入模块——测试锁定顺序
    const anli: Array<[string, string]> = [
      ['材料价格差异', '采购模块'], // 必须在"材料→成本"之前命中
      ['原材料采购', '采购模块'],
      ['供应商议价', '采购模块'],
      ['材料用量差异', '成本模块'],
      ['直接人工', '成本模块'],
      ['人力薪酬', '成本模块'], // 人力归成本——T-21
      ['制造费用差异', '成本模块'],
      ['电力', '成本模块'],
      ['管理费用', '费用模块'],
      ['销售费用', '费用模块'], // 必须在"销售→收入"之前命中
      ['期间费用', '费用模块'],
      ['营收', '收入模块'],
      ['销量差异', '收入模块'],
      ['毛利', '收入模块'],
      ['销售价格差异', '收入模块'],
    ]
    for (const [kemu, qidai] of anli) {
      assert.equal(yingshe_mokuai(kemu), qidai, `科目 '${kemu}' 应归 ${qidai}`)
    }
  })

  test('test_bu_mingzhong: 不命中任何关键词 → null（未归属，交人工）', () => {
    assert.equal(yingshe_mokuai('未知科目XYZ'), null)
  })
})

describe('TestShipeiqi · 适配器：variance.ChayiXiang 鸭子类型转换后与直接构造结果一致', () => {
  test('test_cong_chayi_xiang: variance 输出 → 适配 → 积木聚合：与直接输入等价', () => {
    // variance 行：基准 100,000 元、实际 108,000 元 → 差额 +800,000 分
    // （超支 8,000 元 → 成本类正差 = A）；差异率 8% = 800 基点 → 黄
    // 自定义档位（红 10%/黄 5%，默认已改 15%/30%）
    const dang_lie: YujingDang[] = [
      { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
      { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
    ]
    const shuru: ChayiShuru[] = [
      {
        qijian: '2026-Q1',
        kemu: '材料价格差异',
        fangxiang: '成本类',
        chushi_fen: 10_000_000,
        gundong_fen: 10_000_000,
        shiji_fen: 10_800_000,
      },
    ]
    const jg_chayi = jisuan_chayi(shuru, dang_lie)
    const hang = cong_chayi_xiang(jg_chayi.xiang[0]!)
    assert.equal(hang.chae_fen, 800_000)
    const jg_jimu = chai_jimu([hang])
    // 采购模块 +800,000 A，独占 100%
    assert.equal(jg_jimu.mokuai_lie[3]!.chae_fen, 800_000)
    assert.equal(jg_jimu.mokuai_lie[3]!.zhanbi_bps, 10000)
    // 与直接构造 JimuHang 的结果完全一致（结构化深比较，等值 dataclass；
    // 注意方差行的 yujing 是 '黄'（800 基点=8%，自定义档黄阈 500），
    // 不是 '红'——chae_fen 同为 800,000 但预警随明细透传）
    const zhijie = chai_jimu([jimu_hang('2026-Q1', '材料价格差异', 800_000, 'A', '黄', 800)])
    assert.deepStrictEqual(jg_jimu, zhijie)
  })
})

describe('TestJiaoyan · 输入校验：脏数据必须被拒绝（与全项目异常约定一致）', () => {
  test('test_feifa_shuru: 空列表 / 非 JimuHang 元素 / 空科目 / 空期间 → 拒绝', () => {
    // 空输入 = 结构性错误（与 variance 的"非空列表"纪律一致）
    assert.throws(() => chai_jimu([]), JimuCuowu)
    // 非 JimuHang 元素：整批输入的形态问题，直接拒绝而非逐行跳过
    assert.throws(() => chai_jimu(['不是行'] as unknown as JimuHang[]), JimuCuowu)
    // 科目/期间为空：无法做映射与去重，同样拒绝
    assert.throws(() => chai_jimu([jimu_hang('2026-Q1', '', 1, 'F', '无', 0)]), JimuCuowu)
    assert.throws(() => chai_jimu([jimu_hang('', '营收', 1, 'F', '无', 0)]), JimuCuowu)
  })

  test('test_feifa_chae: 布尔 / 浮点 / 超上限差额 → 拒绝（整数分纪律）', () => {
    // bool 是 int 子类，须显式排除；上限与 variance 同口径 9×10^11 分
    const huai_lie: unknown[] = [true, 100.5, 9 * 10 ** 11 + 1]
    for (const huai of huai_lie) {
      assert.throws(
        () => chai_jimu([jimu_hang('2026-Q1', '营收', huai as number, 'F', '无', 0)]),
        JimuCuowu,
        `${String(huai)} 应被拒绝`,
      )
    }
  })

  test('test_feifa_fa_yujing_chalv: 非法 F/A / 预警 / 负差异率 → 拒绝', () => {
    assert.throws(() => chai_jimu([jimu_hang('2026-Q1', '营收', 1, 'X', '无', 0)]), JimuCuowu)
    assert.throws(() => chai_jimu([jimu_hang('2026-Q1', '营收', 1, 'F', 'X', 0)]), JimuCuowu)
    assert.throws(() => chai_jimu([jimu_hang('2026-Q1', '营收', 1, 'F', '无', -1)]), JimuCuowu)
  })

  test('test_chongfu_jian: （期间, 科目）重复 → 拒绝（防双计）', () => {
    assert.throws(
      () =>
        chai_jimu([
          jimu_hang('2026-Q1', '营收', 1, 'F', '无', 0),
          jimu_hang('2026-Q1', '营收', 2, 'F', '无', 0),
        ]),
      JimuCuowu,
    )
  })

  test('test_quedingxing: 确定性——同输入两次调用结果完全一致（结构化深比较）', () => {
    const hang = jiaocai_si_hang()
    assert.deepStrictEqual(chai_jimu(hang), chai_jimu(hang))
  })
})
