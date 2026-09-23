// ======================================================================
// kanban（看板数据接口）单元测试 —— 纯组装层：只验透传与形态，不重算
// ======================================================================
// 转写自 D:\AppProject\algo\tests\test_kanban.py（12 用例，
// 期望值逐字保留，禁止改数字迁就实现）。
//
// 设计原则：
//     1. 组装契约：五区输出与上游模块结果逐字段透传（数值以本源模块为准）；
//     2. 容错契约：上游缺省（null）→ 对应块为空结构，绝不抛错；
//     3. 派生结构：热力图矩阵（期间×科目）维度与取值逐一锁定。
//
// 夹具策略：上游结果一律用真实模块现算（与 Python 版同手法——看板测试即
// 端到端组装的「半程演练」）。kpi / suyuan 两模块尚未转写（属其他批次），
// 其夹具以【鸭子类型假对象】构造：字段名与 kanban.ts 最小结构 interface
// 逐字一致（= kpi.py / suyuan.py dataclass 字段名），数值为 Python 版
// 手算期望值的原样誊写（10714 / 6000），不算现算自证。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音。
// 运行方式（验证区目录下）：
//     node --test tests/kanban.test.ts
// ======================================================================

import { describe, test } from 'node:test'
import assert from 'node:assert/strict'
// 上游模块在此全部引入——鸭子类型契约：kanban 不 import 上游，测试侧自由组合
import type { ChayiShuru, YujingDang } from '../../plugins/fin-agent/src/variance.ts'
import { jisuan_chayi } from '../../plugins/fin-agent/src/variance.ts'
import type { JimuHang } from '../../plugins/fin-agent/src/building-blocks.ts'
import { chai_jimu, cong_chayi_xiang } from '../../plugins/fin-agent/src/building-blocks.ts'
import type { GunDongShezhi as GunDongShezhiXing, QijianJine } from '../../plugins/fin-agent/src/rolling-budget.ts'
import { GunDongShezhi, gengxin_gundong_yusuan } from '../../plugins/fin-agent/src/rolling-budget.ts'
import type { BscShuru } from '../../plugins/fin-agent/src/bsc.ts'
import { jisuan_bsc } from '../../plugins/fin-agent/src/bsc.ts'
import type { PanDuanShuru } from '../../plugins/fin-agent/src/loop-decision.ts'
import { panduan_huanlu } from '../../plugins/fin-agent/src/loop-decision.ts'
import type { ZhenggaiShuru } from '../../plugins/fin-agent/src/zhenggai.ts'
import { shengcheng_zhenggai } from '../../plugins/fin-agent/src/zhenggai.ts'
import type { KpiJieguoYang, KanbanShuru, SuyuanJieguoYang } from '../../plugins/fin-agent/src/kanban.ts'
import { shengcheng_kanban } from '../../plugins/fin-agent/src/kanban.ts'

// ----------------------------------------------------------------------
// 夹具区
// ----------------------------------------------------------------------

/** 两行差异：材料价格（红）+ 办公费（黄）——覆盖两档预警与两科目。 */
function chayi_lianghang() {
  // 材料价格差异率 10%（红）、办公费 5%（黄）——自定义档位（默认已改 15%/30%）
  const dang_lie: [YujingDang, YujingDang] = [
    { ming_cheng: '红', yan_se: '红', yu_fen: 1000 },
    { ming_cheng: '黄', yan_se: '黄', yu_fen: 500 },
  ]
  const hang_lie: ChayiShuru[] = [
    { qijian: '2026-Q1', kemu: '材料价格差异', fangxiang: '成本类',
      chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 11_000_000 },
    { qijian: '2026-Q2', kemu: '办公费', fangxiang: '成本类',
      chushi_fen: 10_000_000, gundong_fen: 10_000_000, shiji_fen: 10_500_000 },
  ]
  return jisuan_chayi(hang_lie, dang_lie)
}

/** KPI 15 项假对象（鸭子类型）。
 *
 *  kpi 模块尚未转写（属其他批次）——按 kpi.py KpiJieguo 字段名手工构造。
 *  营收达成率 = 15,000,000 ÷ 14,000,000 = 107.142857% → half-up 10714 基点
 *  （Python 测试手算期望值的原样誊写）；其余 14 项缺数 → null。 */
function jia_kpi(): KpiJieguoYang {
  return {
    yingshou_dachenglv_bps: 10714, // 手算：1500/1400 万 → 10714 基点（half-up）
    chengben_kongzhilv_bps: null,
    feiyong_pianchalv_bps: null,
    maolilv_bps: null,             // 毛利率缺数 → None（用例 7 锁定透传）
    jinglirunlv_bps: null,
    xiaoshou_lirunlv_bps: null,
    zichan_zhouzhuanlv_bps: null,
    zijin_zhouzhuanlv_bps: null,
    caigou_chengben_bian_donglv_bps: null,
    gongyinglian_lvyuelv_bps: null,
    channeng_liyonglv_bps: null,
    jiaofu_zhouqi_tian: null,
    kehu_manyilv_bps: null,
    yewu_jindu_bps: null,
    yichang_shijian_shu: null,
  }
}

/** 溯源结果假对象（鸭子类型）。
 *
 *  suyuan 模块尚未转写（属其他批次）——按 suy.py SuyuanJieguo 字段名构造。
 *  数值 = Python 测试手算期望值的原样誊写：交付周期 5→8 天、基准 5 天
 *  → 影响率 (8−5)/5 = +60% = 6000 基点（负向作用；单项占比 10000 基点）。 */
function jia_suyuan(): SuyuanJieguoYang {
  return {
    xiang: [
      {
        kpi_mingcheng: '交付周期',
        yingxianglv_bps: 6000,      // 手算：(8−5)/5 = 60% → 6000 基点
        shuzhi_fangxiang: '上升',   // 5 → 8 天
        zuoyong: '负向作用',        // 交付周期上升 = 负向（偏好表判定）
        zhanbi_bps: 10000,          // 单项 → 占比 100%
      },
    ],
    zhengxiang_top3: [],
    fuxiang_top3: ['交付周期'],
    yingxiang_fenmu_bps: 6000,      // 分母 = Σ|各 KPI 净影响率| = 6000
  }
}

// ----------------------------------------------------------------------
// TestDuibiYuYujing · ① 对比表 + ② 预警汇总：variance 全字段透传
// ----------------------------------------------------------------------
describe('TestDuibiYuYujing · ① 对比表 + ② 预警汇总：variance 全字段透传', () => {
  // 契约：duibi_biao 每行 11 键 = ChayiXiang 全字段（UI 层翻译成中文列名）

  test('test_duibi_touzhuan: 两行对比表逐字段透传（键 = ChayiXiang 字段名）', () => {
    // 组装层不重算：对比表数值以 variance 为准，这里只验透传不失真
    const jg = shengcheng_kanban({ chayi: chayi_lianghang() } as KanbanShuru)
    assert.equal(jg.duibi_biao.length, 2)
    // 第一行：材料价格差异 红（差异率 1000 基点）
    assert.equal(jg.duibi_biao[0]!.kemu, '材料价格差异')
    assert.equal(jg.duibi_biao[0]!.chae_fen, 1_000_000)
    assert.equal(jg.duibi_biao[0]!.yujing, '红')
    assert.equal(jg.duibi_biao[0]!.fa, 'A')
  })

  test('test_yujing_huizong: 四档计数：红 1、黄 1、无 0、无法定级 0', () => {
    // 计数来自 variance.ChayiJieguo 的四档字段——直接透传
    const jg = shengcheng_kanban({ chayi: chayi_lianghang() } as KanbanShuru)
    assert.deepEqual(jg.yujing_huizong,
      { hong_shu: 1, huang_shu: 1, wu_shu: 0, wufa_shu: 0 })
  })
})

// ----------------------------------------------------------------------
// TestRelitu · ② 热力图：期间 × 科目 差异率矩阵（派生结构）
// ----------------------------------------------------------------------
describe('TestRelitu · ② 热力图：期间 × 科目 差异率矩阵（派生结构）', () => {
  // 矩阵取值 = chalv_bps（缺组合 null）——热力着色由 UI 层按预警档完成

  test('test_juzhen_weidu: 两期间 × 两科目 → 2×2 矩阵，取值与行对应', () => {
    // 热力图派生结构：期间/科目排序去重，缺组合填 null（显示「无」）
    const jg = shengcheng_kanban({ chayi: chayi_lianghang() } as KanbanShuru)
    assert.deepEqual(jg.relitu.qijian_lie, ['2026-Q1', '2026-Q2'])
    assert.deepEqual(jg.relitu.kemu_lie, ['办公费', '材料价格差异'])
    // 矩阵：Q1 行 = [null(办公费无此期), 1000]；Q2 行 = [500, null]
    assert.deepEqual(jg.relitu.juzhen, [[null, 1000], [500, null]])
  })
})

// ----------------------------------------------------------------------
// TestBingtu · ③ 饼图：积木四模块 + 未归属透传
// ----------------------------------------------------------------------
describe('TestBingtu · ③ 饼图：积木四模块 + 未归属透传', () => {
  // 饼图数据 = 四模块占比（合计恒 10000 基点的不变量在上游保证）

  test('test_bingtu_touzhuan: 四模块占比/高亮/净合计逐字段透传', () => {
    // 材料价格→采购、办公费→费用；净合计 = 1,000,000+500,000 分
    const chayi = chayi_lianghang()
    const jimu = chai_jimu(chayi.xiang.map((x) => cong_chayi_xiang(x)))
    const jg = shengcheng_kanban({ chayi, jimu } as KanbanShuru)
    // 材料价格→采购、办公费→费用：净合计 1,500,000 分；高亮=采购
    assert.equal(jg.bingtu.mokuai_lie.length, 4)
    assert.equal(jg.bingtu.mokuai_lie[3]!.mokuai, '采购模块')
    assert.equal(jg.bingtu.mokuai_lie[3]!.chae_fen, 1_000_000)
    assert.equal(jg.bingtu.hexin_mokuai, '采购模块')
    assert.equal(jg.bingtu.jing_heji_fen, 1_500_000)
  })
})

// ----------------------------------------------------------------------
// TestZhexian · ③ 折线：滚动预算逐期透传
// ----------------------------------------------------------------------
describe('TestZhexian · ③ 折线：滚动预算逐期透传', () => {
  // 折线序列 = 滚动预算逐期（届满=实际、剩余=重算），UI 直接连线

  test('test_zhexian_touzhuan: 两期滚动：届满替换 + 剩余重算的逐期数据透传', () => {
    // 增长 100 基点：剩余期 10,000,000×1.01 = 10,100,000 分
    const yusuan: QijianJine[] = [
      { qijian: '2026-01', jine_fen: 10_000_000 },
      { qijian: '2026-02', jine_fen: 10_000_000 },
    ]
    const shiji: QijianJine[] = [{ qijian: '2026-01', jine_fen: 10_500_000 }]
    const shezhi: GunDongShezhiXing = GunDongShezhi('月度', 100, { hangye_xiuzheng: 'B' })
    const gundong = gengxin_gundong_yusuan(yusuan, shiji, shezhi)
    const jg = shengcheng_kanban({ gundong } as KanbanShuru)
    assert.equal(jg.zhexian.length, 2)
    // 1 月届满 = 实际 10,500,000；2 月剩余 = 10,000,000×1.01 = 10,100,000
    assert.equal(jg.zhexian[0]!.zhuangtai, '已届满')
    assert.equal(jg.zhexian[0]!.shuzhi_fen, 10_500_000)
    assert.equal(jg.zhexian[1]!.zhuangtai, '剩余期')
    assert.equal(jg.zhexian[1]!.shuzhi_fen, 10_100_000)
  })
})

// ----------------------------------------------------------------------
// TestBscKpiSuyuanPanduan · ③④块：BSC/KPI/溯源/判定 逐字段透传
// ----------------------------------------------------------------------
describe('TestBscKpiSuyuanPanduan · ③④块：BSC/KPI/溯源/判定 逐字段透传', () => {
  // 各块独立透传：任一上游缺省都不影响其他块（容错契约）

  test('test_bsc_touzhuan: BSC 四维得分/总分/等级透传（74 分合格例题）', () => {
    // 74 分 = 定稿 §6 例题：40/30/20/10 权重 × 75/80/70/60 得分
    const shuru: BscShuru = {
      caijing_bps: 7500, kehu_bps: 8000, neibu_bps: 7000, xuexi_bps: 6000,
      quanzhong: null,
    }
    const bsc = jisuan_bsc(shuru)
    const jg = shengcheng_kanban({ bsc } as KanbanShuru)
    assert.equal(jg.bsc_block.zongfen, 74)
    assert.equal(jg.bsc_block.dengji, '合格')
    assert.deepEqual(jg.bsc_block.quanzhong, [40, 30, 20, 10])
  })

  test('test_kpi_shiwuxiang: KPI 15 项：中文名顺序 = 定稿 §8 清单；缺数 None 透传', () => {
    // 15 项顺序即 KPI_MING 常量顺序（财务 9 + 非财务 6）
    const jg = shengcheng_kanban({ kpi: jia_kpi() } as KanbanShuru)
    assert.equal(jg.kpi_block.length, 15)
    assert.equal(jg.kpi_block[0]!.mingcheng, '营收达成率')
    assert.equal(jg.kpi_block[0]!.zhi, 10714)
    assert.equal(jg.kpi_block[3]!.zhi, null) // 毛利率缺数 → None
  })

  test('test_suyuan_touzhuan: 溯源逐项影响/TOP3/分母透传', () => {
    // 交付周期 5→8 天、基准 5 天：影响率 +60% = 6000 基点（负向作用）
    const jg = shengcheng_kanban({ suyuan: jia_suyuan() } as KanbanShuru)
    assert.equal(jg.suyuan_block.xiang[0]!.yingxianglv_bps, 6000)
    assert.deepEqual(jg.suyuan_block.fuxiang_top3, ['交付周期'])
  })

  test('test_panduan_touzhuan: 判定结果透传（混合纠错模式 + 审批标志）', () => {
    // 规划 9% 与执行 1% 双显著 + 已登记 → 判定表情形 4 = 混合纠错模式（非双环）
    const shuru_pd: PanDuanShuru = {
      chalv_bps: 1000, guihua_zong_fen: 900_000, zhixing_zong_fen: 100_000,
      yuandan_cbf_fen: 10_000_000, jie_gou_biangeng: true, bianma: '供应商涨价',
    }
    const panduan = panduan_huanlu(shuru_pd, 100, 100)
    const jg = shengcheng_kanban({ panduan } as KanbanShuru)
    assert.equal(jg.panduan_block.panduan, '混合纠错模式')
    assert.equal(jg.panduan_block.shenpi, true)
  })
})

// ----------------------------------------------------------------------
// TestZhenggaiKuai · ⑤ 整改闭环区：清单与计数透传
// ----------------------------------------------------------------------
describe('TestZhenggaiKuai · ⑤ 整改闭环区：清单与计数透传', () => {
  // 整改清单是 AI 层文案起草的输入——透传完整性即验收标准

  test('test_zhenggai_touzhuan: 整改清单逐项 + 优先级/进度计数透传', () => {
    // 红 1 条强制整改 + 黄 1 条关注整改 → 高 1 中 1 共 2
    const chayi = chayi_lianghang()
    const zhenggai = shengcheng_zhenggai({ chayi } as ZhenggaiShuru)
    const jg = shengcheng_kanban({ chayi, zhenggai } as KanbanShuru)
    assert.equal(jg.zhenggai_block.qingdan.length, 2)
    assert.equal(jg.zhenggai_block.qingdan[0]!.leixing, '强制整改')
    assert.equal(jg.zhenggai_block.gao_shu, 1)
    assert.equal(jg.zhenggai_block.zong_shu, 2)
  })
})

// ----------------------------------------------------------------------
// TestRongcuo · 容错契约：上游缺省 → 空结构，绝不抛错
// ----------------------------------------------------------------------
describe('TestRongcuo · 容错契约：上游缺省 → 空结构，绝不抛错', () => {
  // 空结构 = 合法输出：UI 显示「无」、AI 层跳过——端到端脚本不中断的前提

  test('test_kong_shuru: 全部缺省：各区空结构（看板显示「无」的数据基础）', () => {
    // 容错契约：端到端任何阶段缺料，看板数据都必须合法可序列化
    const jg = shengcheng_kanban({} as KanbanShuru)
    assert.deepEqual(jg.duibi_biao, [])
    assert.deepEqual(jg.bingtu.mokuai_lie, [])
    assert.deepEqual(jg.zhexian, [])
    assert.deepEqual(jg.relitu, { qijian_lie: [], kemu_lie: [], juzhen: [] })
    assert.equal(jg.kpi_block.length, 15) // KPI 15 项全 None
    assert.ok(jg.kpi_block.every((x) => x.zhi === null))
    assert.deepEqual(jg.zhenggai_block.qingdan, [])
  })

  test('test_quedingxing: 确定性：同输入两次调用结果完全一致（纯函数纪律）', () => {
    // 组装层也须纯函数：顺序稳定是 UI/AI 消费的前提（深比较全字段）
    const chayi = chayi_lianghang()
    const jimu = chai_jimu(chayi.xiang.map((x) => cong_chayi_xiang(x)))
    const shuru = { chayi, jimu } as KanbanShuru
    assert.deepEqual(shengcheng_kanban(shuru), shengcheng_kanban(shuru))
  })
})
