// ======================================================================
// bsc（平衡计分卡四维评分）单元测试 —— 期望值全部手工验算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_bsc.py（13 用例，
// 期望数字逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 回归基准 = 定稿 v2.1 §6 例题（40/30/20/10 权重 × 75/80/70/60 得分
//        → 总分 74 → 合格）+ 完整版五档等级九点边界；
//     2. 不封顶（T-05 拍板）：达成率 >100% 时得分 >100 原样保留——单独用例锁定；
//     3. 权重合计必须 = 100%（人工设定、系统只计算——定稿 §6）。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（插件目录下）：
//     node --test tests/bsc.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
import type { BscShuru, SiYuanzu } from '../../plugins/fin-agent/src/bsc.ts'
import { BscCuowu, QUANZHONG_MOREN, jisuan_bsc } from '../../plugins/fin-agent/src/bsc.ts'

/** Python 版以位置参数构造 frozen dataclass；TS 侧以同字段名对象字面量构造。 */
function bsc_shuru(
  caijing_bps: number,
  kehu_bps: number,
  neibu_bps: number,
  xuexi_bps: number,
  quanzhong: SiYuanzu | null = null,
): BscShuru {
  return { caijing_bps, kehu_bps, neibu_bps, xuexi_bps, quanzhong }
}

describe('TestLiti · 定稿 §6 例题回归——总分 74 → 合格（最重要的用例）', () => {
  test('test_dinggao_liti: 四维得分 75/80/70/60 + 默认权重 → 总分 74 → 合格', () => {
    const jg = jisuan_bsc(bsc_shuru(7500, 8000, 7000, 6000))
    // 得分 = 达成率 ÷ 100（half-up）：7500 基点 → 75 分，以此类推
    assert.deepEqual(
      [jg.caijing_defen, jg.kehu_defen, jg.neibu_defen, jg.xuexi_defen],
      [75, 80, 70, 60],
    )
    // 总分 = (40×75 + 30×80 + 20×70 + 10×60) ÷ 100 = 7400 ÷ 100 = 74
    assert.equal(jg.zongfen, 74)
    assert.equal(jg.dengji, '合格') // 70~79 档
    assert.deepEqual(jg.quanzhong, QUANZHONG_MOREN) // 默认权重回显
  })
})

describe('TestBufengding · 不封顶（T-05 拍板）：超 100% 达成率得分原样保留、不裁剪', () => {
  test('test_danwei_chaoguo_100: 财务达成率 120% → 得分 120 保留 → 总分 92 → 优秀', () => {
    const jg = jisuan_bsc(bsc_shuru(12000, 8000, 7000, 6000))
    assert.equal(jg.caijing_defen, 120) // 不裁剪到 100
    // 总分 = (40×120 + 30×80 + 20×70 + 10×60) ÷ 100 = 9200 ÷ 100 = 92
    assert.equal(jg.zongfen, 92)
    assert.equal(jg.dengji, '优秀')
  })

  test('test_quanwei_chaoguo_100: 四维全部超 100%——得分全部保留，总分 129 → 优秀', () => {
    const jg = jisuan_bsc(bsc_shuru(15000, 12000, 11000, 10500))
    // 得分 150/120/110/105；总分 = (6000+3600+2200+1050)÷100 = 128.5 → 129
    assert.deepEqual(
      [jg.caijing_defen, jg.kehu_defen, jg.neibu_defen, jg.xuexi_defen],
      [150, 120, 110, 105],
    )
    assert.equal(jg.zongfen, 129)
    assert.equal(jg.dengji, '优秀')
  })
})

describe('TestQuanzhong · 权重：默认 40/30/20/10；自定义可微调但合计必须 = 100', () => {
  test('test_zidingyi_quanzhong: 自定义权重（20, 30, 30, 20）→ 总分 72 → 合格', () => {
    const jg = jisuan_bsc(bsc_shuru(7500, 8000, 7000, 6000, [20, 30, 30, 20]))
    // 总分 = (20×75 + 30×80 + 30×70 + 20×60) ÷ 100 = 7200 ÷ 100 = 72
    assert.equal(jg.zongfen, 72)
    assert.equal(jg.dengji, '合格')
    assert.deepEqual(jg.quanzhong, [20, 30, 30, 20])
  })

  test('test_heji_fei_100_jujue: 权重合计 ≠ 100 → 拒绝（定稿：权重人工设定、合计 100%）', () => {
    const huai_lie: unknown[] = [[40, 30, 20, 5], [40, 30, 20, 11], [39, 30, 20, 10]]
    for (const huai of huai_lie) {
      assert.throws(
        () => jisuan_bsc(bsc_shuru(7500, 8000, 7000, 6000, huai as SiYuanzu)),
        BscCuowu,
        `${JSON.stringify(huai)} 应被拒绝`,
      )
    }
  })

  test('test_quanzhong_xingtai: 单维超 100 / 负数 / 布尔 / 长度不足 → 拒绝', () => {
    // 【转写偏差说明】Python 原版本组还有一个 '[40, 30, 20, 10] 列表被拒'
    // 子用例——Python 靠 isinstance(tuple) 区分元组/列表；TS 运行时四元组与
    // 普通数组同为 Array、无法区分（插件约定 quanzhong 走 JSON 时也只会是
    // 数组），故该子用例不适用，其余脏形态逐个保留。
    const huai_lie: unknown[] = [[40, 30, 20, 15], [-1, 30, 20, 51], [40, 30, 20, true], [40, 30, 20]]
    for (const huai of huai_lie) {
      assert.throws(
        () => jisuan_bsc(bsc_shuru(7500, 8000, 7000, 6000, huai as SiYuanzu)),
        BscCuowu,
        `${JSON.stringify(huai)} 应被拒绝`,
      )
    }
  })
})

describe('TestDachenglv · 达成率校验：非负整数基点 + 合理性上限（上限 ≠ 得分封顶）', () => {
  test('test_feifa_dachenglv: 负数 / 浮点 / 布尔 / 超上限 → 拒绝（整数基点纪律）', () => {
    const huai_lie: unknown[] = [-1, 100.5, true, 1_000_001]
    for (const huai of huai_lie) {
      assert.throws(
        () => jisuan_bsc(bsc_shuru(huai as number, 0, 0, 0)),
        BscCuowu,
        `${String(huai)} 应被拒绝`,
      )
    }
  })

  test('test_ling_dachenglv: 达成率 0 合法——得分 0、总分 0 → 严重不合格', () => {
    const jg = jisuan_bsc(bsc_shuru(0, 0, 0, 0))
    assert.equal(jg.zongfen, 0)
    assert.equal(jg.dengji, '严重不合格')
  })
})

describe('TestDengji · 等级五档边界：59/60/69/70/79/80/89/90/100 逐点锁定', () => {
  test('test_wudang_bianjie: 四维同分构造恰好整数总分，逐点对照等级表', () => {
    // 权重全 25%（自定义 (25,25,25,25)）时总分 = 四维得分平均——
    // 每档边界得分 x 即总分 x，期望等级手查五档表
    const quanzhong_25: SiYuanzu = [25, 25, 25, 25]
    const anli: Array<[number, string]> = [
      [59, '严重不合格'],
      [60, '预警'], // 60 起进入预警档
      [69, '预警'],
      [70, '合格'], // 70 起进入合格档
      [79, '合格'],
      [80, '良好'], // 80 起进入良好档
      [89, '良好'],
      [90, '优秀'], // 90 起进入优秀档
      [100, '优秀'],
    ]
    for (const [defen, qidai] of anli) {
      // 达成率 = 得分 × 100 基点（整数换算，无舍入干扰）
      const jg = jisuan_bsc(
        bsc_shuru(defen * 100, defen * 100, defen * 100, defen * 100, quanzhong_25),
      )
      assert.equal(jg.zongfen, defen, `得分 ${defen} 的总分应恰为 ${defen}`)
      assert.equal(jg.dengji, qidai, `总分 ${defen} 应评为 ${qidai}`)
    }
  })
})

describe('TestSheru · half-up 舍入：维度得分与总分两处整数化逐例验算', () => {
  test('test_defen_half_up: 达成率 75.5% → 76 分；74.5% → 75 分；74.49% → 74 分', () => {
    // 7450 基点 = 74.5%：half-up 进位到 75；7449 基点 = 74.49% 不进位
    assert.equal(jisuan_bsc(bsc_shuru(7550, 0, 0, 0)).caijing_defen, 76)
    assert.equal(jisuan_bsc(bsc_shuru(7450, 0, 0, 0)).caijing_defen, 75)
    assert.equal(jisuan_bsc(bsc_shuru(7449, 0, 0, 0)).caijing_defen, 74)
  })

  test('test_zongfen_half_up: 总分 0.5 → 1（进位）；0.4 → 0（舍去）；0.8 → 1（进位）', () => {
    // (1,0,0,1)：Σ权重×得分 = 40+10 = 50 → 0.5 → half-up 1
    assert.equal(jisuan_bsc(bsc_shuru(100, 0, 0, 100)).zongfen, 1)
    // (1,0,0,0)：Σ = 40 → 0.4 → 0（小数不足一半舍去）
    assert.equal(jisuan_bsc(bsc_shuru(100, 0, 0, 0)).zongfen, 0)
    // (2,0,0,0)：Σ = 80 → 0.8 → 1（小数过半进位）
    assert.equal(jisuan_bsc(bsc_shuru(200, 0, 0, 0)).zongfen, 1)
  })
})

describe('TestJiaoyan · 输入校验与确定性', () => {
  test('test_feifa_shuru_leixing: 非 BscShuru 输入 → 拒绝', () => {
    assert.throws(() => jisuan_bsc('不是输入' as unknown as BscShuru), BscCuowu)
  })

  test('test_quedingxing: 确定性——同输入两次调用结果完全一致（结构化深比较）', () => {
    const shuru = bsc_shuru(7500, 8000, 7000, 6000)
    assert.deepStrictEqual(jisuan_bsc(shuru), jisuan_bsc(shuru))
  })
})
