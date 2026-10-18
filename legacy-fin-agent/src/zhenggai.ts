// ======================================================================
// zhenggai（整改数据底座）—— 方案B 步骤 8 的【整改清单结构化】确定性核心
//（FR-14 计算部分）
// ======================================================================
// 转写自 D:\AppProject\algo\zhenggai.py（Python 版为唯一行为准绳；
// 对应测试 algo/tests/test_zhenggai.py → 插件 tests/zhenggai.test.ts）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/01-需求说明.md v2.0 §3 FR-14（分部门分模块整改方案——用户拍板拆分：
//         【整改数据底座 = 计算层】本模块先做；文案起草 = AI 层后接，[043]/T-28）
//     docs/textbook/finagent-算法核对文档-定稿.md v2.1 §4（判定输出→纠错指令）
//         / §9 步骤 8（整改方案 + 双环预算修订案人工审批闭环）
//     docs/proposal-full-extract.txt 行 60~66（整改闭环区输出清单）
//
// 模块定位（[043] 分层拆分后的职责边界）：
//     本模块把【确定性规则】可推出的整改事项全部结构化——红/黄预警行、
//     单双环判定指令、核心问题模块责任定位——输出"整改清单"（问题、
//     责任模块、整改类型、优先级、审批标志、进度状态）。AI 层（dsh 部署后）
//     只负责把 qingdan 喂给 LLM 起草整改文案——本模块不产出一句自然语言。
//
// 整改规则（确定性，全部可测试）：
//     ① 判定 ∈ {双环, 混合纠错模式} → 预算修订案（优先级高、必人工审批）；
//     ② 判定 = 单环 → 行为整改指令（优先级中）；
//     ③ 判定 = 复核提示 → 人工复核项（优先级中）；
//     ④ 差异红预警行 → 强制整改（优先级高）；
//     ⑤ 差异黄预警行 → 关注整改（优先级中）；
//     ⑥ 责任模块 = 科目→模块映射（复用 building_blocks 默认映射）+ 核心
//        问题模块（积木高亮）；映射不中 → '未归属'；
//     ⑦ 清单按优先级排序（高 → 中 → 低），同优先级按生成顺序。
//
// 进度状态：所有条目初始 '待整改'；整改进度 = 四状态计数（供看板进度字段）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     ZhenggaiShuru       整改输入（差异结果/积木结果/判定结果，可缺省 null）
//     ZhenggaiXiang       整改项（类型/优先级/责任模块/描述/审批/进度）
//     ZhenggaiJieguo      整改结果（清单 + 优先级计数 + 整改进度计数）
//     shengcheng_zhenggai 生成整改（主函数）
//     leixing             整改类型（预算修订案/行为整改指令/人工复核/强制整改/关注整改）
//     youxianji           优先级（高/中/低）
//     zeren_mokuai        责任模块（四模块名/未归属/无）
//     shenpi              是否需人工审批（预算修订案必 true）
//     zhuangtai           进度状态（待整改/进行中/已完成）
//     gao_shu / zhong_shu / di_shu       高/中/低优先级计数
//     daizhenggai_shu / jinxingzhong_shu / wancheng_shu   整改进度三态计数
//
// 与上下游的关系：
//     上游：variance（红/黄预警行）、loop_decision（判定指令）、
//           building_blocks（核心问题模块 + 科目→模块映射）——全部鸭子类型；
//     下游：看板数据接口（整改闭环区/整改进度）、AI 层（清单→LLM 文案起草）。
//
// 建立：2026-08-23（Python）｜ TS 转写：2026-09-05 ｜ FinAgent dsh 插件批次F
// ======================================================================

// 【转写裁决】Python 版在 _zeren_mokuai 内延迟 `from building_blocks import
// yingshe_mokuai` 并捕 ImportError 降级 '未归属'——那是 Python 打包形态的
// 容错（允许本模块在无积木模块的环境独立跑）。dsh 插件是【单包】形态，
// building-blocks.ts 与本文件同目录必然可导入，ImportError 分支不可能发生，
// 故改为顶部静态 import（降级语义保留在"映射不中 → '未归属'"本身）。
import { yingshe_mokuai } from './building-blocks.ts'

// ======================================================================
// 常量区（数据值用中文——整改类型/优先级/进度状态）
// ======================================================================

/** 整改类型（①②③④⑤ 规则对应的五种，见模块头） */
export const LEIXING_YUSUAN_XIUDING = '预算修订案'
export const LEIXING_XINGWEI_ZHENGGAI = '行为整改指令'
export const LEIXING_RENGONG_FUHE = '人工复核'
export const LEIXING_QIANGZHI = '强制整改'
export const LEIXING_GUANZHU = '关注整改'

/** 优先级 */
export const YOUXIANJI_GAO = '高'
export const YOUXIANJI_ZHONG = '中'
export const YOUXIANJI_DI = '低'

/** 进度状态 */
export const ZHUANGTAI_DAI = '待整改'
export const ZHUANGTAI_JINXING = '进行中'
export const ZHUANGTAI_WANCHENG = '已完成'

/** 责任模块兜底（科目映射不中——交人工补映射） */
export const ZEREN_WEIGUISHU = '未归属'
/** 责任模块缺省（无积木结果时的占位） */
export const ZEREN_WU = '无'

// ======================================================================
// 鸭子类型上游接口区（最小结构形状，字段名与所有权模块导出 interface 逐字一致）
// ======================================================================

/**
 * variance.ChayiXiang 的最小结构形状（鸭子类型）。
 *
 * Python 契约（ZhenggaiShuru.chayi 字段说明）：行须有 qijian/kemu/chae_fen/
 * fa/yujing/chalv_bps 属性——六个字段名与 variance.ts 导出的 ChayiXiang
 * 逐字一致；TS 结构类型天然兼容，无需 import variance。
 */
export interface ChayiXiangYang {
  readonly qijian: string
  readonly kemu: string
  readonly chae_fen: number
  readonly fa: string
  readonly yujing: string
  readonly chalv_bps: number | null
}

/** variance.ChayiJieguo 的最小结构形状：须有 .xiang 列表（预警行来源）。 */
export interface ChayiJieguoYang {
  readonly xiang: readonly ChayiXiangYang[]
}

/** building_blocks.JimuJieguo 的最小结构形状：须有 .hexin_mokuai（核心问题模块）。 */
export interface JimuJieguoYang {
  readonly hexin_mokuai: string | null
}

/** loop_decision.PanDuanJieguo 的最小结构形状：须有 .panduan（判定取值）。 */
export interface PanDuanJieguoYang {
  readonly panduan: string
}

// ======================================================================
// 数据结构区（frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 整改输入：上游结果对象（鸭子类型；null = 该来源不参与）。
 *
 *  字段说明：
 *      chayi:   variance.ChayiJieguo（红/黄预警行来源）。
 *      jimu:    building_blocks.JimuJieguo（核心问题模块）。
 *      panduan: loop_decision.PanDuanJieguo（判定指令）。
 *
 *  Python dataclass 三字段均缺省 None；TS 侧以可选字段 + null 表达，
 *  调用方按 Python 关键字风格传子集（如 `{ chayi }`）。 */
export interface ZhenggaiShuru {
  readonly chayi?: ChayiJieguoYang | null
  readonly jimu?: JimuJieguoYang | null
  readonly panduan?: PanDuanJieguoYang | null
}

/** 整改项：一条结构化整改指令（AI 层文案起草的输入行）。
 *
 *  字段说明：
 *      leixing:       整改类型（五种枚举，见模块头）。
 *      youxianji:     优先级（高/中/低）。
 *      zeren_mokuai:  责任模块（四模块名/未归属/无）。
 *      kemu:          科目名（差异行来源；判定项为 ''）。
 *      qijian:        期间键（差异行来源；判定项为 ''）。
 *      miaoshu:       结构化描述（"期间 科目 差额元 预警档"拼接，
 *                     无自然语言——文案由 AI 层起草）。
 *      shenpi:        是否需人工审批（预算修订案必 true，其余 false）。
 *      zhuangtai:     进度状态（初始 '待整改'）。 */
export interface ZhenggaiXiang {
  readonly leixing: string
  readonly youxianji: string
  readonly zeren_mokuai: string
  readonly kemu: string
  readonly qijian: string
  readonly miaoshu: string
  readonly shenpi: boolean
  readonly zhuangtai: string
}

/** 整改结果：清单（按优先级排序）+ 优先级计数 + 整改进度计数。
 *
 *  字段说明：
 *      qingdan:          整改项列表（高 → 中 → 低）。
 *      gao_shu / zhong_shu / di_shu:  优先级计数。
 *      zong_shu:         清单总数。
 *      daizhenggai_shu / jinxingzhong_shu / wancheng_shu:  进度三态计数。 */
export interface ZhenggaiJieguo {
  readonly qingdan: ZhenggaiXiang[]
  readonly gao_shu: number
  readonly zhong_shu: number
  readonly di_shu: number
  readonly zong_shu: number
  readonly daizhenggai_shu: number
  readonly jinxingzhong_shu: number
  readonly wancheng_shu: number
}

// ======================================================================
// 内部工具函数区
// ======================================================================

/** Python f-string `{x!r}`（repr）的 TS 对应：字符串/对象走 JSON 化，
 *  其余 String 化。仅用于报错文案里的非法值回显。 */
function _repr(x: unknown): string {
  if (typeof x === 'string') return JSON.stringify(x)
  if (typeof x === 'object' && x !== null) return JSON.stringify(x)
  return String(x)
}

/** 整数千分位（Python f'{n:,}' 的等价实现——手工插逗号，不依赖 ICU locale）。 */
function _qianfenwei(n: number): string {
  const s = String(n)
  let out = ''
  for (let i = 0; i < s.length; i++) {
    const sheng = s.length - i // 含当前位还剩几位
    out += s[i]
    if (sheng > 1 && (sheng - 1) % 3 === 0) out += ','
  }
  return out
}

/** 分 → 元显示（两位小数 + 千分位；整数运算实现，零浮点）。
 *
 *  T-29#8 应用：对外报告统一主单位元——描述文本不再出现"分"。
 *  Python 本地实现逐字照搬（divmod(v, 100) 后拼千分位 + 两位小数）。 */
function _yuan_xianshi(fen: number): string {
  const fu = fen < 0
  const v = fu ? -fen : fen
  const zheng = Math.floor(v / 100) // divmod 商（整数分 → 元整数部分）
  const xiao = v - zheng * 100      // divmod 余数（分的小数部分）
  const s = `${_qianfenwei(zheng)}.${String(xiao).padStart(2, '0')}`
  return fu ? `-${s}` : s
}

/** 科目 → 责任模块（复用 building_blocks 默认关键词映射，契约式）。
 *
 *  映射不中 → '未归属'（不静默丢弃，交人工补映射——与积木模块同纪律）。
 *  【转写裁决】见文件头：Python 的 ImportError 降级是打包容错，
 *  插件单包内不需要——静态 import 顶部完成。 */
function _zeren_mokuai(kemu: string): string {
  const mokuai = yingshe_mokuai(kemu)
  return mokuai ?? ZEREN_WEIGUISHU
}

// ======================================================================
// 对外接口区（唯一的计算入口）
// ======================================================================

/** 生成整改清单（方案B 步骤 8 的计算部分；纯函数）。
 *
 *  参数：shuru —— ZhenggaiShuru（差异/积木/判定结果，均可缺省 null）。
 *
 *  返回：ZhenggaiJieguo（按优先级排序的整改清单 + 计数 + 整改进度）。
 *
 *  处理顺序：
 *      ① 判定指令项（预算修订案/行为整改指令/人工复核）→ ② 差异预警项
 *      （红=强制/黄=关注）→ ③ 责任模块定位 → ④ 优先级排序 → ⑤ 计数。
 */
export function shengcheng_zhenggai(shuru: ZhenggaiShuru): ZhenggaiJieguo {
  // 门禁（Python isinstance 门禁逐字保留）：非 ZhenggaiShuru 形状 → TypeError
  if (typeof shuru !== 'object' || shuru === null || Array.isArray(shuru)) {
    throw new TypeError(`输入必须是 ZhenggaiShuru：${_repr(shuru)}`)
  }

  const qingdan: ZhenggaiXiang[] = []

  // ① 判定指令项（loop_decision 输出 → 纠错指令，定稿 §4/§9 步骤 8）
  const hexin = shuru.jimu != null ? shuru.jimu.hexin_mokuai : null
  if (shuru.panduan != null) {
    const panduan = shuru.panduan.panduan
    const zeren = hexin !== null ? hexin : ZEREN_WU
    if (panduan === '双环' || panduan === '混合纠错模式') {
      // 混合纠错模式（原名双轨，T-29#3 更名）与双环同出口：
      // 预算修订案——必人工审批（定稿 §9 步骤 8 人工审批环节）
      qingdan.push({
        leixing: LEIXING_YUSUAN_XIUDING, youxianji: YOUXIANJI_GAO,
        zeren_mokuai: zeren, kemu: '', qijian: '',
        miaoshu: `判定 ${panduan}：预算修订案（人工审批后下周期生效）`,
        shenpi: true, zhuangtai: ZHUANGTAI_DAI,
      })
    } else if (panduan === '单环') {
      // 行为整改指令：不修改预算基准，仅纠正当下业务执行动作
      qingdan.push({
        leixing: LEIXING_XINGWEI_ZHENGGAI, youxianji: YOUXIANJI_ZHONG,
        zeren_mokuai: zeren, kemu: '', qijian: '',
        miaoshu: '判定 单环：输出行为整改指令（不改预算基准）',
        shenpi: false, zhuangtai: ZHUANGTAI_DAI,
      })
    } else if (panduan === '复核提示') {
      // 复核提示：疑似结构变动交人工确认（护栏 FR-8 的落地出口）
      qingdan.push({
        leixing: LEIXING_RENGONG_FUHE, youxianji: YOUXIANJI_ZHONG,
        zeren_mokuai: zeren, kemu: '', qijian: '',
        miaoshu: '判定 复核提示：疑似结构变动，交人工确认补录',
        shenpi: false, zhuangtai: ZHUANGTAI_DAI,
      })
    }
  }

  // ② 差异预警项（红=强制整改、黄=关注整改——定稿 #3 三档预警的落地出口）
  if (shuru.chayi != null) {
    for (const x of shuru.chayi.xiang) {
      if (x.yujing === '红') {
        qingdan.push({
          leixing: LEIXING_QIANGZHI, youxianji: YOUXIANJI_GAO,
          zeren_mokuai: _zeren_mokuai(x.kemu), kemu: x.kemu,
          qijian: x.qijian,
          miaoshu: `${x.qijian} ${x.kemu} 差额 ${_yuan_xianshi(x.chae_fen)} 元 预警 红`,
          shenpi: false, zhuangtai: ZHUANGTAI_DAI,
        })
      } else if (x.yujing === '黄') {
        qingdan.push({
          leixing: LEIXING_GUANZHU, youxianji: YOUXIANJI_ZHONG,
          zeren_mokuai: _zeren_mokuai(x.kemu), kemu: x.kemu,
          qijian: x.qijian,
          miaoshu: `${x.qijian} ${x.kemu} 差额 ${_yuan_xianshi(x.chae_fen)} 元 预警 黄`,
          shenpi: false, zhuangtai: ZHUANGTAI_DAI,
        })
      }
    }
  }

  // ③ 核心问题模块追加高亮提示（积木 D3 高亮 ≠ 预警行——单独一条）
  //   去重规则：已有同责任模块的强制整改项则不重复追加（清单干净）
  if (
    hexin !== null && !qingdan.some(
      (x) => x.leixing === LEIXING_QIANGZHI && x.zeren_mokuai === hexin,
    )
  ) {
    qingdan.push({
      leixing: LEIXING_GUANZHU, youxianji: YOUXIANJI_ZHONG,
      zeren_mokuai: hexin, kemu: '', qijian: '',
      miaoshu: `积木核心问题模块：${hexin}（不利差异最大，优先整改）`,
      shenpi: false, zhuangtai: ZHUANGTAI_DAI,
    })
  }

  // ④ 优先级排序（高 → 中 → 低；同优先级保持生成顺序——Array.sort 规范
  //   自 ES2019 起稳定，与 Python sort 的稳定性语义一致）
  const youxian_xu: Record<string, number> = {
    [YOUXIANJI_GAO]: 0, [YOUXIANJI_ZHONG]: 1, [YOUXIANJI_DI]: 2,
  }
  qingdan.sort((a, b) => youxian_xu[a.youxianji] - youxian_xu[b.youxianji])

  // ⑤ 计数（优先级 + 整改进度三态——初始全为待整改）
  return {
    qingdan,
    gao_shu: qingdan.filter((x) => x.youxianji === YOUXIANJI_GAO).length,
    zhong_shu: qingdan.filter((x) => x.youxianji === YOUXIANJI_ZHONG).length,
    di_shu: qingdan.filter((x) => x.youxianji === YOUXIANJI_DI).length,
    zong_shu: qingdan.length,
    daizhenggai_shu: qingdan.filter((x) => x.zhuangtai === ZHUANGTAI_DAI).length,
    jinxingzhong_shu: qingdan.filter((x) => x.zhuangtai === ZHUANGTAI_JINXING).length,
    wancheng_shu: qingdan.filter((x) => x.zhuangtai === ZHUANGTAI_WANCHENG).length,
  }
}
