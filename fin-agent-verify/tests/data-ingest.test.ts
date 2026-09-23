// ======================================================================
// data_ingest（数据录入模块）单元测试 —— 期望值全部手工写死。
// 转写自 D:\AppProject\algo\tests\test_data_ingest.py（11 用例）。
// ======================================================================
//
// 设计原则：
//     1. 每个用例只验证一条校验/换算规则，失败即可定位到口径条款；
//     2. CSV 文本现场构造（贴近真实导入场景）；
//     3. 拒绝清单必须"带原因、带行号"——断言里检查原因关键词。
//
// 本项目强制规则：注释率 ≥ 40%；标识符全拼音（2026-08-23）。
// 运行方式（插件目录下）：node --test tests/data-ingest.test.ts
// ======================================================================

import { describe, it } from 'node:test'
import assert from 'node:assert/strict'

import { JiexiCuowu, daoru_csv } from '../../plugins/fin-agent/src/data-ingest.ts'

/** 标准表头（与模块内 BIXU_LIE 一致；测试里独立抄一份，
 *  避免直接引用被测常量导致"表头错了测试也跟着错"的自证问题） */
const BIAOTOU = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'

/** 拼一个完整 CSV 文本：表头 + 若干数据行（省得每个用例重复写表头）。 */
function pinbiao(...zhengwen_hang: string[]): string {
  return [BIAOTOU, ...zhengwen_hang].join('\n')
}

describe('TestJiexiBiaotou', () => {
  // 解析级问题：表头 / 空文件 / BOM 头。
  // 解析级 = 整个文件的问题（一行都处理不了），必须抛 JiexiCuowu；
  // 与"逐行拒绝"（进拒绝清单）严格区分，见被测模块 JiexiCuowu 说明。

  it('test_bom_he_zhengchang_biaotou', () => {
    // Windows 记事本导出的 BOM 头必须被剥掉，正常解析不受影响。
    // 模拟记事本/Excel 另存的 CSV：文件开头带 \ufeff 三个隐形字符
    const wenben = '\ufeff' + pinbiao('预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,')
    const jieguo = daoru_csv(wenben) // 若 BOM 未剥掉，表头第一列会带上 BOM 而报错
    assert.equal(jieguo.ruku_shu, 1)
  })

  it('test_cuowu_biaotou_zhengwenjian_jujue', () => {
    // 表头列名/顺序不符 → 整文件拒绝（JiexiCuowu）。
    const huai = '类别,期间,科目,数值,单位,来源,时间,备注' // 列名全错
    // 表头错就不该处理任何数据行——断言抛解析级异常
    assert.throws(() => {
      daoru_csv(huai + '\n预算基础,2026-Q1,营收,100,元,s,2026-01-15,')
    }, JiexiCuowu)
  })

  it('test_kong_csv_jujue', () => {
    // 空文本（连表头都没有）→ JiexiCuowu。
    assert.throws(() => {
      daoru_csv('')
    }, JiexiCuowu)
  })
})

describe('TestZhengchangLujing', () => {
  // 正常路径：四类混合导入，各归各档、数值换算正确。
  // 这是本模块的"主干道"用例——四类各进各档、三种单位换算各验一例。

  it('test_silei_fendang_huansuan', () => {
    // 四类各一条：分档正确 + 元→分、%→基点、个→整数 三种换算。
    // 四行分别覆盖：元（两位小数）/ 元（带 5 尾数）/ % / 计数
    const wenben = pinbiao(
      '预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,年初定稿', // → 22000000 分
      '实时经营,2026-Q1,营收,210000.50,元,ERP导出,2026-04-02,Q1实际',    // → 21000050 分
      '行业对标,2026-Q1,行业毛利率,40.00,%,行业报告A,2026-04-01,均值',   // → 4000 基点
      '经营变更,2026-05,供应商更换,2,个,人工登记,2026-05-10,更换为乙厂', // → 2 个
    )
    const jieguo = daoru_csv(wenben)
    // 无拒绝、四类各一条
    assert.equal(jieguo.ruku_shu, 4)
    assert.equal(jieguo.jujue.length, 0)
    // 分档：四类清单各 1 条
    assert.equal(jieguo.yusuan.length, 1)
    assert.equal(jieguo.shishi.length, 1)
    assert.equal(jieguo.hangye.length, 1)
    assert.equal(jieguo.biangeng.length, 1)
    // 换算：元→分（×100）、%→基点（×100）、计数原样
    assert.equal(jieguo.yusuan[0].shuzhi, 22_000_000)
    assert.equal(jieguo.shishi[0].shuzhi, 21_000_050)
    assert.equal(jieguo.hangye[0].shuzhi, 4_000)
    assert.equal(jieguo.biangeng[0].shuzhi, 2)
    // 行号：数据行从 2 起（第 1 行是表头）
    assert.equal(jieguo.yusuan[0].hanghao, 2)
  })

  it('test_xiaoshu_buling', () => {
    // 小数位补零规则：'123'元→12300 分；'123.4'元→12340 分。
    const wenben = pinbiao(
      '预算基础,2026-01,办公费,123,元,预算表V3,2026-01-15,',
      '预算基础,2026-02,办公费,123.4,元,预算表V3,2026-01-15,',
    )
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.jujue.length, 0)
    assert.equal(jieguo.yusuan[0].shuzhi, 12_300)
    assert.equal(jieguo.yusuan[1].shuzhi, 12_340)
  })
})

describe('TestShuzhiGuize', () => {
  // 数值规则：空值 / 负数 / 非数字 / 小数位超限 / 计数带小数。
  // 口径分歧回归点：空值"不填 0、进拒绝清单"——若未来会计拍板改口径，
  // 本组用例是第一个要改的地方（模块头"口径分歧"注释有索引）。

  it('test_huaishuzhi_quanbu_jujue_dai_yuanyin', () => {
    // 四种坏数值全部进拒绝清单，且原因可读。
    // 每行一种坏法；行号 2~5 与拒绝清单一一对应
    const wenben = pinbiao(
      '实时经营,2026-01,办公费,,元,ERP,2026-02-01,空值',            // 空值
      '实时经营,2026-01,差旅费,-50.00,元,ERP,2026-02-01,负数',      // 负数
      '实时经营,2026-01,招待费,abc,元,ERP,2026-02-01,字母',         // 非数字
      '实时经营,2026-01,水电费,100.123,元,ERP,2026-02-01,三位小数', // 超两位
    )
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.ruku_shu, 0)
    assert.equal(jieguo.jujue.length, 4)
    // 逐行核对拒绝原因关键词（顺序与输入行一致）
    const yuanyin = jieguo.jujue.map((x) => x.yuanyin)
    assert.ok(yuanyin.some((s) => s.includes('缺失')))
    assert.ok(yuanyin.some((s) => s.includes('负数')))
    assert.ok(yuanyin.some((s) => s.includes('不是合法数字')))
    assert.ok(yuanyin.some((s) => s.includes('小数位超过')))
    // 行号正确（第 2~5 数据行）
    assert.deepEqual(jieguo.jujue.map((x) => x.hanghao), [2, 3, 4, 5])
  })

  it('test_jishu_danwei_bixu_zhengshu', () => {
    // 计数单位（个）不允许小数：'2.5 个' → 拒绝。
    const wenben = pinbiao('经营变更,2026-05,供应商更换,2.5,个,人工登记,2026-05-10,')
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.jujue.length, 1)
    assert.ok(jieguo.jujue[0].yuanyin.includes('小数位超过'))
  })
})

describe('TestZiduanGuize', () => {
  // 字段规则：期间格式 / 类别 / 单位 / 来源与时间 / 去重。
  // 覆盖 8 列里除"数值"外所有字段的校验分支（数值归 TestShuzhiGuize）。

  it('test_huaiqijian_leibie_danwei', () => {
    // 期间 2026-13、类别"随便"、单位"吨" → 各自进拒绝并带原因。
    // 四行分别踩：月份越界 / 非法类别 / 季度越界 / 未知单位
    const wenben = pinbiao(
      '实时经营,2026-13,营收,100,元,ERP,2026-02-01,月份13不存在',
      '随便,2026-01,营收,100,元,ERP,2026-02-01,类别不合法',
      '实时经营,2026-Q5,营收,100,元,ERP,2026-02-01,季度5不存在',
      '实时经营,2026-01,煤耗,100,吨,ERP,2026-02-01,单位不支持',
    )
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.ruku_shu, 0)
    assert.equal(jieguo.jujue.length, 4)
    const quanbu = jieguo.jujue.map((x) => x.yuanyin).join('｜')
    assert.ok(quanbu.includes('期间格式非法'))
    assert.ok(quanbu.includes('未知类别'))
    assert.ok(quanbu.includes('未知单位'))
  })

  it('test_laiyuan_shijian_wei_kong_jujue', () => {
    // 来源/时间为空 → 拒绝（台账追溯字段强制非空）。
    const wenben = pinbiao(
      '实时经营,2026-01,营收,100,元,,2026-02-01,来源为空',
      '实时经营,2026-02,营收,100,元,ERP,,时间为空',
    )
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.jujue.length, 2)
    assert.ok(jieguo.jujue[0].yuanyin.includes('数据来源为空'))
    assert.ok(jieguo.jujue[1].yuanyin.includes('更新时间为空'))
  })

  it('test_chongfu_houyidao_jujue', () => {
    // 去重：同（类别,期间,科目）第二条被拒，保留先到者。
    // 两行同键不同值：证明"保留的是先到者"而非"后来居上"
    const wenben = pinbiao(
      '预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,先到',
      '预算基础,2026-Q1,营收,225000.00,元,预算表V4,2026-02-20,后到重复',
    )
    const jieguo = daoru_csv(wenben)
    // 只入库第一条，其值为先到者的值
    assert.equal(jieguo.ruku_shu, 1)
    assert.equal(jieguo.yusuan[0].shuzhi, 22_000_000)
    // 第二条进拒绝清单并说明"保留先到者"
    assert.equal(jieguo.jujue.length, 1)
    assert.ok(jieguo.jujue[0].yuanyin.includes('重复'))
    assert.equal(jieguo.jujue[0].hanghao, 3)
  })

  it('test_lieshu_buqi_jujue', () => {
    // 列数不齐（少了备注列）→ 该行进拒绝清单，其余行不受影响。
    // 第一行 7 列（缺备注），第二行 8 列正常——验证"坏行不连累好行"
    let wenben = BIAOTOU + '\n实时经营,2026-01,营收,100,元,ERP,2026-02-01' // 只有 7 列
    wenben += '\n实时经营,2026-02,营收,200,元,ERP,2026-03-01,正常行'
    const jieguo = daoru_csv(wenben)
    assert.equal(jieguo.ruku_shu, 1)     // 正常行入库
    assert.equal(jieguo.jujue.length, 1) // 残行列被拒
    assert.ok(jieguo.jujue[0].yuanyin.includes('列数不符'))
  })
})
