// ======================================================================
// llm_clean（LLM 格式归一化前置层）单元测试 —— 全部用注入的假模型，不联网。
// 转写自 D:\AppProject\algo\tests\test_llm_clean.py（15 用例）。
// ======================================================================
//
// 设计原则：
//     1. 假模型 = 普通函数（Callable 注入的 TS 形态），按剧本返回好/坏翻译；
//     2. 每条红线（数字照抄 / 不豁免校验 / 可降级）至少一个专测用例；
//     3. 智能分流的"直解不调模型"用调用计数器断言（token 成本关注点）。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音（2026-08-23）。
// 运行方式（验证区目录下）：node --test tests/llm-clean.test.ts
// ======================================================================

import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

// 被测模块（智能分流总入口 / 提示词构造 / 幻觉防线）
import { gouzao_tishi, shuzi_yuansu_jiaoyan, zhineng_fenliu } from '../../plugins/fin-agent/src/llm-clean.ts'

/** 标准表头（与 data_ingest 的 BIXU_LIE 一致的独立抄本，防自证） */
const BIAOTOU = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'

/** 好模型剧本：把脏表忠实地翻译成标准 8 列（数字一律照抄）。
 *  注意：这是普通代码字符串（不是 doctest），换行直接写 \n 转义即可。 */
function hao_moxing(tishi: string): string {
  return (
    '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\n' +
    '预算基础,2026-Q1,营收,220000,元,人工整理,2026-01-15,'
  )
}

// ======================================================================
// TestZhinengFenliu —— 智能分流三级路由：直解 / 模型归一化 / 降级
// ======================================================================

describe('TestZhinengFenliu', () => {
  // 覆盖触发条件的全部边界：什么时候该花 token、什么时候不该；
  // 以及模型路径的自纠错重试（2026-08-23 真模型实测后加入）。

  it('test_zhijie_chenggong_bu_diao_moxing', () => {
    // 标准 CSV 直解成功：模型函数一次都不被调用（零 token）。
    const diaoyong: number[] = [] // 调用计数器：直解路径必须保持为空
    const jia_moxing = (tishi: string): string => {
      diaoyong.push(1) // 只要被调就记录
      return ''
    }
    const wenben = BIAOTOU + '\n预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,'
    const fl = zhineng_fenliu(wenben, jia_moxing)
    assert.equal(fl.lujing, '直解')
    assert.equal(fl.chenggong, true)
    assert.equal(fl.jieguo.ruku_shu, 1)
    assert.equal(diaoyong.length, 0) // 关键断言：模型没被调用
  })

  it('test_kong_wenjian_zhijie', () => {
    // 只有表头的空文件：直解成功（入库 0、拒绝 0，不惊动模型）。
    const fl = zhineng_fenliu(BIAOTOU + '\n', hao_moxing)
    assert.equal(fl.lujing, '直解')
    assert.equal(fl.jieguo.ruku_shu, 0)
  })

  it('test_biaotou_bu_fu_zou_moxing', () => {
    // 表头级错误（两列脏表）→ 触发模型归一化 → 入库成功。
    const luan = '科目,金额,日期\n营收,220000,2026-01-15'
    const fl = zhineng_fenliu(luan, hao_moxing)
    assert.equal(fl.lujing, '模型归一化')
    assert.equal(fl.chenggong, true)
    assert.equal(fl.jieguo.ruku_shu, 1)
    // 好翻译的数字被原样保留：220000 元 = 22000000 分
    assert.equal(fl.jieguo.yusuan[0].shuzhi, 22_000_000)
    // 审计留痕：归一化文本被带回
    assert.ok(fl.guiyi_wenben.includes('数据类别'))
  })

  it('test_quanbu_jujue_ye_chufa_moxing', () => {
    // 表头正确但数据行全残（7 列）→ 全军覆没 = 格式不对 → 走模型。
    const canwen = BIAOTOU + '\n预算基础,2026-Q1,营收,220000,元,预算表,2026-01-15' // 缺备注列
    const fl = zhineng_fenliu(canwen, hao_moxing)
    assert.equal(fl.lujing, '模型归一化')
    assert.equal(fl.jieguo.ruku_shu, 1)
  })

  it('test_bufen_chenggong_bu_zou_moxing', () => {
    // 部分行被拒、部分入库 → 视为直解成功（拒绝清单本就交人工复核）。
    let hunwen = BIAOTOU + '\n预算基础,2026-Q1,营收,220000,元,预算表V3,2026-01-15,'
    hunwen += '\n实时经营,2026-02,营收,abc,元,ERP,2026-02-01,坏数值行' // 此行进拒绝清单
    const fl = zhineng_fenliu(hunwen, hao_moxing)
    assert.equal(fl.lujing, '直解')
    assert.equal(fl.jieguo.ruku_shu, 1)
    assert.equal(fl.jieguo.jujue.length, 1)
  })
})

// ======================================================================
// TestHuanjueFangxian —— 红线 1：数字照抄——幻觉防线整批拒绝
// ======================================================================

describe('TestHuanjueFangxian', () => {
  // 含规范化规则专测：全角 / 千分位 / 前导零只比数学值，不误报。

  it('test_bianzao_shuzi_zhengpi_jujue', () => {
    // 模型编造 999999 → 溯源命中 → 降级 + 幻觉标记。
    const luan = '科目,金额\n营收,220000'
    const huai_moxing = (tishi: string): string => {
      // 999999 原文没有；日期数字 2026/01/15 原文也没有（同样属编造）
      return BIAOTOU + '\n预算基础,2026-Q1,营收,999999,元,x,2026-01-15,'
    }
    const fl = zhineng_fenliu(luan, huai_moxing)
    assert.equal(fl.lujing, '降级')
    assert.equal(fl.chenggong, false)
    // 拒绝清单带幻觉标记，且入库数为 0
    assert.ok(fl.jieguo.jujue[0].yuanyin.includes('LLM幻觉嫌疑'))
    assert.equal(fl.jieguo.ruku_shu, 0)
  })

  it('test_suyan_guize_quanijiao_qianfenwei', () => {
    // 溯源比"数学值"不比"写法"：全角数字、千分位、前导零都不误报。
    // 原文全角'２２００００'，译文'220000'——数值相同，不应判幻觉
    assert.deepEqual(shuzi_yuansu_jiaoyan('２２００００', '220000'), [])
    // 千分位 vs 无千分位：'1,234.56' 与 '1234.56' 等价
    assert.deepEqual(shuzi_yuansu_jiaoyan('1,234.56', '1234.56'), [])
    // 前导零：'01' 与 '1' 等价
    assert.deepEqual(shuzi_yuansu_jiaoyan('期间01', '期间1'), [])
    // 反向：译文里的数字原文确实没有 → 报幻觉（'100.5' ≠ '100'）
    assert.deepEqual(shuzi_yuansu_jiaoyan('营收 100', '营收 100.5'), ['100.5'])
  })

  it('test_chongfu_chuxian_bu_suan_huanjue', () => {
    // 集合语义：同一数字重复出现（如年份拆进两列）不算幻觉。
    // 原文一次 100，译文两次 100——结构重排，放行（去重由确定性层兜底）
    assert.deepEqual(shuzi_yuansu_jiaoyan('金额100', '金额100 合计100'), [])
    // 但"原文没有的新数字"依然要抓（如 100 → 100.5 属于改值）
    assert.deepEqual(shuzi_yuansu_jiaoyan('金额100', '金额100.5'), ['100.5'])
  })
})

// ======================================================================
// TestJiangji —— 红线 3：模型不可用 / 出错 / 翻译不合格时的降级路径
// ======================================================================

describe('TestJiangji', () => {
  // 降级 = 系统仍可用：返回合成拒绝结果与人工建议，绝不崩溃。

  it('test_wu_moxing_jiangji', () => {
    // 未提供模型函数 → 降级，拒绝原因里带人工修格式建议。
    const fl = zhineng_fenliu('随便,表头\n1,2', null) // 第二参缺省 = 无模型
    assert.equal(fl.lujing, '降级')
    assert.ok(fl.jieguo.jujue[0].yuanyin.includes('另存为 CSV'))
  })

  it('test_moxing_paocuo_jiangji', () => {
    // 模型函数抛异常（模拟超时/断网）→ 降级而非崩溃。
    const bao_moxing = (tishi: string): string => {
      throw new Error('模拟超时')
    }
    const fl = zhineng_fenliu('随便,表头\n1,2', bao_moxing)
    assert.equal(fl.lujing, '降级')
    assert.ok(fl.jieguo.jujue[0].yuanyin.includes('模型调用失败'))
  })

  it('test_fanyi_reng_buhege_jiangji', () => {
    // 红线 2：模型两次输出都不合格 → 降级（自纠错重试后仍失败）。
    const diaoyong: number[] = [] // 调用计数（验证确实重试了两次）
    const fei_moxing = (tishi: string): string => {
      diaoyong.push(1)
      return '还是,乱,格式\n1,2,3' // 翻译了个寂寞
    }
    const fl = zhineng_fenliu('随便,表头\n1,2', fei_moxing)
    assert.equal(fl.lujing, '降级')
    assert.ok(fl.jieguo.jujue[0].yuanyin.includes('仍不符合要求'))
    assert.equal(diaoyong.length, 2) // 首次 + 一次自纠错重试
  })

  it('test_zijiaocuo_chongshi_chenggong', () => {
    // 自纠错重试：首次期间留空被拒 → 反馈后第二次修正 → 入库。
    const luan = '科目,金额,日期\n营收,220000,2026-01-15'
    const tishi_liebiao: string[] = [] // 录制两次收到的提示词
    const huihe_moxing = (tishi: string): string => {
      tishi_liebiao.push(tishi)
      if (tishi_liebiao.length === 1) { // 第一回合：期间空 → 全军覆没
        return BIAOTOU + '\n实时经营,,营收,220000,元,LLM归一化,2026-01-15,备注'
      }
      // 第二回合：按反馈修正（期间取原文日期 2026-01）
      return BIAOTOU + '\n实时经营,2026-01,营收,220000,元,LLM归一化,2026-01-15,备注'
    }
    const fl = zhineng_fenliu(luan, huihe_moxing)
    assert.equal(fl.lujing, '模型归一化')
    assert.equal(fl.jieguo.ruku_shu, 1)
    // 第二次的提示词必须带上首次拒绝原因（自纠错的证据）
    assert.ok(tishi_liebiao[1].includes('上次的输出被系统拒绝'))
    assert.ok(tishi_liebiao[1].includes('期间格式非法'))
  })

  it('test_daimakuai_baozhuang_beiboli', () => {
    // 模型爱用 ```csv 包裹输出：剥离后正常入库（防御性兼容）。
    const luan = '科目,金额,日期\n营收,220000,2026-01-15'
    const baozhuang_moxing = (tishi: string): string => {
      return '```csv\n' + hao_moxing(tishi) + '\n```'
    }
    const fl = zhineng_fenliu(luan, baozhuang_moxing)
    assert.equal(fl.lujing, '模型归一化')
    assert.equal(fl.jieguo.ruku_shu, 1)
  })

  it('test_moxing_lou_biaotou_zidong_bu', () => {
    // 模型只回数据行漏表头（真模型实测场景）→ 自动补头后入库。
    const luan = '科目,金额,日期\n营收,220000,2026-01-15'
    const wutou_moxing = (tishi: string): string => {
      // 列数恰为 8 的裸数据行（无表头）——_bu_biaotou 应前插标准表头
      return '实时经营,2026-01,营收,220000,元,LLM归一化,2026-01-15,类别待人工确认'
    }
    const fl = zhineng_fenliu(luan, wutou_moxing)
    assert.equal(fl.lujing, '模型归一化')
    assert.equal(fl.jieguo.ruku_shu, 1)
    // 数字照抄核验：220000 元 → 22000000 分
    assert.equal(fl.jieguo.shishi[0].shuzhi, 22_000_000)
  })
})

// ======================================================================
// TestTishi —— 提示词构造：铁律必须写死在提示里（模型侧的第一道约束）
// ======================================================================

describe('TestTishi', () => {
  // 模型行为不可直接断言，但给它的指令是确定性的——指令错了必改这里。

  it('test_tishi_han_guize', () => {
    // 提示词包含：8 列表头、数字照抄铁律、枚举值与原文。
    const tishi = gouzao_tishi('科目,金额\n营收,220000')
    assert.ok(tishi.includes('数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'))
    assert.ok(tishi.includes('原样照抄'))    // 数字照抄铁律
    assert.ok(tishi.includes('营收,220000')) // 原文完整带入
    assert.ok(tishi.includes('预算基础'))    // 类别枚举
  })
})
