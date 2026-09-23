// ======================================================================
// xishu（判定系数输出）单元测试 —— 11 用例，全部离线、期望值手算写死
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_xishu.py（11 用例，
// 期望值逐字保留，禁止改数字迁就实现）。
//
// 口径依据：algo/xishu.py 模块头（TODO T-32：判定系数包 + 系数→提示词
// 映射表——算法层与分析层 M5 的唯一接缝；提示词=检索查询串，非分析文案）。
//
// 用例目录：
//     TestHuizong   ×4  汇总：预警计数/红行排序/完成率 half-up/空输入
//                       ——覆盖"只汇总不重算"承诺的两个例外（排序+完成率）
//     TestTishi     ×4  提示词映射：红A超支/F红方法/判定/核心模块，去重与上限
//                       ——映射表是 T-32 建议默认值，用例锁死当前口径
//     TestQuanlian  ×3  全链一致性：与 variance/loop_decision/building_blocks
//                       真实输出对接（鸭子类型契约）+ 确定性
// 夹具策略：上游结果一律用真实模块现算（与 zhenggai/kanban 测试同手法），
//     期望值全部手工推演写死，禁止现算自证。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（验证区目录下）：
//     node --test tests/xishu.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
// 被测模块与上游构造（鸭子类型契约——无需适配层，直接对接真实输出）
import type { ChayiShuru, YujingDang } from '../../plugins/fin-agent/src/variance.ts'
import { jisuan_chayi } from '../../plugins/fin-agent/src/variance.ts'
import type { PanDuanShuru } from '../../plugins/fin-agent/src/loop-decision.ts'
import { panduan_huanlu } from '../../plugins/fin-agent/src/loop-decision.ts'
import type { JimuHang } from '../../plugins/fin-agent/src/building-blocks.ts'
import { chai_jimu } from '../../plugins/fin-agent/src/building-blocks.ts'
import type { BscShuru } from '../../plugins/fin-agent/src/bsc.ts'
import { jisuan_bsc } from '../../plugins/fin-agent/src/bsc.ts'
import type { ZhenggaiShuru } from '../../plugins/fin-agent/src/zhenggai.ts'
import { shengcheng_zhenggai } from '../../plugins/fin-agent/src/zhenggai.ts'
import type { XishuShuru } from '../../plugins/fin-agent/src/xishu.ts'
import { shengcheng_xishu } from '../../plugins/fin-agent/src/xishu.ts'

// ----------------------------------------------------------------------
// 夹具区
// ----------------------------------------------------------------------

/** 三行差异夹具：红A(3500bps 说法见旧注，实为 1500bps) > 红F(1200bps) > 黄A(600bps)。
 *
 *  Python 版注释口径：红A > 红F > 黄A——排序与映射的考题。
 *  手算：采购成本 1000万→1150万：+15% → 1500 基点 A 红；
 *  营收 500万→560万：+12% → 1200 基点 F 红（收入类超额=F 但波动红）；
 *  办公费 200万→212万：+6% → 600 基点 A 黄。
 *  【2026-09-03 默认阈值改 15%/30% 后】本夹具改传自定义档位（红 10%/黄 5%）
 *  ——数据不动，档位显式传入（顺带覆盖自定义接口）。 */
function _zao_chayi() {
  const dang_lie: [YujingDang, YujingDang] = [
    { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
    { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
  ]
  const hang_lie: ChayiShuru[] = [
    { qijian: '2026-Q1', kemu: '采购成本', fangxiang: '成本类',
      chushi_fen: 10_000_000, gundong_fen: null, shiji_fen: 11_500_000 },
    { qijian: '2026-Q1', kemu: '营收', fangxiang: '收入类',
      chushi_fen: 5_000_000, gundong_fen: null, shiji_fen: 5_600_000 },
    { qijian: '2026-Q1', kemu: '办公费', fangxiang: '成本类',
      chushi_fen: 2_000_000, gundong_fen: null, shiji_fen: 2_120_000 },
  ]
  return jisuan_chayi(hang_lie, dang_lie)
}

// ----------------------------------------------------------------------
// TestHuizong · 汇总面：预警计数、红行排序、完成率、空输入
// ----------------------------------------------------------------------
describe('TestHuizong · 汇总面：预警计数、红行排序、完成率、空输入', () => {
  // 四条用例各守一个汇总契约：计数是透传、排序是本模块唯一重排、
  // 完成率是本模块唯一计算（half-up 整数基点）、空输入零臆造——
  // 后两条直接对应全项目"缺数交人工"的纪律。

  test('test_yujing_jishu_yu_paixu: 红/黄/无计数 + 红行按差异率降序', () => {
    // 手算：本夹具红行 = 采购成本 1500(A)、营收 1200(F) → 降序即此序；
    // 黄 1 行（办公费），无 0 行。
    const bao = shengcheng_xishu({ chayi: _zao_chayi() } as XishuShuru)
    assert.deepEqual([bao.hong_shu, bao.huang_shu, bao.wu_shu], [2, 1, 0])
    assert.deepEqual(bao.hong_hang_lie,
      [['2026-Q1', '采购成本', 1500, 'A'], ['2026-Q1', '营收', 1200, 'F']])
  })

  test('test_wanchenglv_ban_shang: 整体完成率 = Σ实际 ÷ Σ基准（基点，half-up）', () => {
    // 手算：Σ实际 = 1150+560+212 = 1922 万；Σ基准 = 1000+500+200 = 1700 万；
    // 1922/1700 = 113.06% → half-up 11306 基点（11305.88… 进位）。
    const bao = shengcheng_xishu({ chayi: _zao_chayi() } as XishuShuru)
    assert.equal(bao.wanchenglv_bps, 11306)
  })

  test('test_kong_shuru_kong_bao: 全空输入：计数为 0、完成率 None、结论 None、零提示词', () => {
    // 缺数不臆造：上游缺哪块，系数包对应字段为 None/空
    const bao = shengcheng_xishu({} as XishuShuru)
    assert.deepEqual([bao.hong_shu, bao.huang_shu, bao.wu_shu], [0, 0, 0])
    assert.equal(bao.wanchenglv_bps, null)
    assert.equal(bao.panduan_jielun, null)
    assert.equal(bao.hexin_mokuai, null)
    assert.equal(bao.tishi_lie.length, 0)
  })

  test('test_ling_jizhun_jiao_rengong: 全部行的基准为 0：完成率无法定义 → None', () => {
    // 零基准不是"完成率 0%"——无法定义和有定义是两回事，
    // 系数包必须诚实交 None 让分析层明示"缺数"（与 variance 除零纪律一致）。
    const chayi = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '营收', fangxiang: '收入类',
        chushi_fen: 0, gundong_fen: null, shiji_fen: 1 },
    ])
    const bao = shengcheng_xishu({ chayi } as XishuShuru)
    assert.equal(bao.wanchenglv_bps, null)
  })
})

// ----------------------------------------------------------------------
// TestTishi · 提示词映射：A/F 方向、判定结论、核心模块、去重与上限
// ----------------------------------------------------------------------
describe('TestTishi · 提示词映射：A/F 方向、判定结论、核心模块、去重与上限', () => {
  // 映射是"系数 → 检索查询串"的合同：算法层只产出查询串、不产出分析
  // ——查询串的措辞属于 T-32 建议默认值，M5 研究后可调，届时改用例。

  test('test_hong_A_chaozhi: 红A 行 → "{科目} 预算超支 管控措施"（按来源标签定位）', () => {
    const bao = shengcheng_xishu({ chayi: _zao_chayi() } as XishuShuru)
    const di_yi = bao.tishi_lie.find((t) => t.laiyuan === '红预警-采购成本')!
    assert.equal(di_yi.chaxun_ciyu, '采购成本 预算超支 管控措施')
  })

  test('test_hong_F_fangfa: 红F 行（超额但波动过大）→ "{科目} 预算差异 分析方法"', () => {
    const bao = shengcheng_xishu({ chayi: _zao_chayi() } as XishuShuru)
    const ciyu_lie = bao.tishi_lie.map((t) => t.chaxun_ciyu)
    assert.ok(ciyu_lie.includes('营收 预算差异 分析方法'))
  })

  test('test_panduan_yu_mokuai_yingshe: 双环/混合 → "预算调整 审批程序"；核心模块 → 模块领域词', () => {
    // 夹具走真实 loop_decision + building_blocks（同 doctest 的
    // 混合纠错模式场景）——顺带验证鸭子类型对接无适配层。
    const chayi = jisuan_chayi([
      { qijian: '2026-Q1', kemu: '采购成本', fangxiang: '成本类',
        chushi_fen: 10_000_000, gundong_fen: null, shiji_fen: 11_500_000 },
    ])
    const shuru_pd: PanDuanShuru = {
      chalv_bps: 1500, guihua_zong_fen: 900_000, zhixing_zong_fen: 250_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: true,
    }
    const panduan = panduan_huanlu(shuru_pd, 100, 100)
    const hang: JimuHang = { qijian: '2026-Q1', kemu: '采购成本',
      chae_fen: 1_500_000, fa: 'A', yujing: '红', chalv_bps: 1500 }
    const jimu = chai_jimu([hang])
    const bao = shengcheng_xishu({ chayi, panduan, jimu } as XishuShuru)
    const ciyu_lie = bao.tishi_lie.map((t) => t.chaxun_ciyu)
    assert.ok(ciyu_lie.includes('预算调整 审批程序'))
    assert.ok(ciyu_lie.includes('采购成本控制 制度'))
    assert.equal(bao.panduan_jielun, '混合纠错模式')
    assert.equal(bao.shenpi, true)
  })

  test('test_quchong_yu_shangxian: 同查询串去重；条数封顶 TISHI_SHANGXIAN=8', () => {
    // 构造 6 个红行 + 双环 + 核心模块 = 8 条去重前有重复的空间——
    // 断言：无重复、总条数 ≤ 8。
    // （默认档位 15%/30% 下：科目1号 20%→黄、科目2号 30%→红、科目3号 40%→红）
    const hang_lie: ChayiShuru[] = []
    for (const i of [1, 2]) {
      for (let q = 1; q <= 3; q++) {
        hang_lie.push({
          qijian: `2026-Q${i}`, kemu: `科目${q}号`, fangxiang: '成本类',
          chushi_fen: 1_000_000, gundong_fen: null,
          shiji_fen: 1_000_000 + (q + 1) * 100_000,
        })
      }
    }
    const chayi = jisuan_chayi(hang_lie) // 6 行全部预警（20%/30%/40% 各两期）
    const panduan = panduan_huanlu(
      { chalv_bps: 1500, jie_gou_biangeng: true } as PanDuanShuru, 100, 100,
    )
    const bao = shengcheng_xishu({ chayi, panduan } as XishuShuru)
    const ciyu_lie = bao.tishi_lie.map((t) => t.chaxun_ciyu)
    assert.equal(ciyu_lie.length, new Set(ciyu_lie).size) // 无重复
    assert.ok(ciyu_lie.length <= 8)                       // 封顶
  })
})

// ----------------------------------------------------------------------
// TestQuanlian · 与上游真实输出的对接契约 + 确定性
// ----------------------------------------------------------------------
describe('TestQuanlian · 与上游真实输出的对接契约 + 确定性', () => {
  // 三条用例证明：系数包对上游是【透传】不加工（整改计数/BSC 评分
  // 原样带出）、对调用方是【确定】的（同输入同输出）——
  // 这是"算法层零加工、分析层可信赖"的结构保证。

  test('test_zhenggai_jishu_touming: 整改计数透传：zhenggai 的高/中计数进系数包', () => {
    const chayi = _zao_chayi()
    const shuru_pd: PanDuanShuru = {
      chalv_bps: 1500, guihua_zong_fen: 900_000, zhixing_zong_fen: 250_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: true,
    }
    const panduan = panduan_huanlu(shuru_pd, 100, 100)
    const hang: JimuHang = { qijian: '2026-Q1', kemu: '采购成本',
      chae_fen: 1_500_000, fa: 'A', yujing: '红', chalv_bps: 1500 }
    const zhenggai = shengcheng_zhenggai({ chayi, panduan, jimu: chai_jimu([hang]) } as ZhenggaiShuru)
    const bao = shengcheng_xishu({ chayi, panduan, zhenggai } as XishuShuru)
    assert.equal(bao.zhenggai_gao_shu, zhenggai.gao_shu)     // 透传一致
    assert.equal(bao.zhenggai_zhong_shu, zhenggai.zhong_shu)
  })

  test('test_bsc_touming: BSC 总分/等级透传：上游给什么系数包就带什么', () => {
    // 74 分 = 定稿 §6 例题（40/30/20/10 权重 × 75/80/70/60 得分）
    const shuru: BscShuru = {
      caijing_bps: 7500, kehu_bps: 8000, neibu_bps: 7000, xuexi_bps: 6000,
      quanzhong: null,
    }
    const bsc = jisuan_bsc(shuru)
    const bao = shengcheng_xishu({ bsc } as XishuShuru)
    assert.deepEqual([bao.bsc_zongfen, bao.bsc_dengji], [74, '合格'])
  })

  test('test_quedingxing: 确定性：同输入两次生成，系数包逐字段一致（纯函数纪律）', () => {
    // asdict 全字段对比——不只挑几个字段，任何隐藏状态都会现形
    //（TS 侧用深比较对象等价，覆盖全部字段含 tishi_lie 元组）。
    const shuru = { chayi: _zao_chayi() } as XishuShuru
    assert.deepEqual(shengcheng_xishu(shuru), shengcheng_xishu(shuru))
  })
})
